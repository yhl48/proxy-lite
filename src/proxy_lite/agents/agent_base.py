import json
import logging
from abc import ABC, abstractmethod
from contextlib import AsyncExitStack
from functools import cached_property
from typing import Any, Optional, Type, cast

from pydantic import BaseModel, Field
from tenacity import before_sleep_log, retry, stop_after_attempt, wait_exponential

from proxy_lite.client import BaseClient, ClientConfigTypes, OpenAIClientConfig
from proxy_lite.history import (
    AssistantMessage,
    MessageHistory,
    MessageLabel,
    SystemMessage,
    Text,
    ToolCall,
    ToolMessage,
    UserMessage,
)
from proxy_lite.logger import logger
from proxy_lite.tools import Tool

# if TYPE_CHECKING:
#     from proxy_lite.tools import Tool


class BaseAgentConfig(BaseModel):
    client: ClientConfigTypes = Field(default_factory=OpenAIClientConfig)
    history_messages_limit: dict[MessageLabel, int] = Field(default_factory=lambda: dict())
    history_messages_include: Optional[dict[MessageLabel, int]] = Field(
        default=None,
        description="If set, overrides history_messages_limit by setting all message types to 0 except those specified",
    )

    def model_post_init(self, __context: Any) -> None:
        if self.history_messages_include is not None:
            self.history_messages_limit = {label: 0 for label in MessageLabel}
            self.history_messages_limit.update(self.history_messages_include)


class BaseAgent(BaseModel, ABC):
    config: BaseAgentConfig
    temperature: float = Field(default=0.7, ge=0, le=2)
    history: MessageHistory = Field(default_factory=MessageHistory)
    client: Optional[BaseClient] = None
    env_tools: list[Tool] = Field(default_factory=list)
    task: Optional[str] = Field(default=None)
    seed: Optional[int] = Field(default=None)

    class Config:
        arbitrary_types_allowed = True

    def __init__(self, **data) -> None:
        super().__init__(**data)
        self._exit_stack = AsyncExitStack()
        self._tools_init_task = None

    def model_post_init(self, __context: Any) -> None:
        super().model_post_init(__context)
        self.client = BaseClient.create(self.config.client)

    @property
    @abstractmethod
    def system_prompt(self) -> str: ...

    @cached_property
    @abstractmethod
    def tools(self) -> list[Tool]: ...

    @cached_property
    def tool_descriptions(self) -> str:
        tool_descriptions = []
        for tool in self.tools:
            func_descriptions = "\n".join("- {name}: {description}".format(**schema) for schema in tool.schema)
            tool_title = f"{tool.__class__.__name__}:\n" if len(self.tools) > 1 else ""
            tool_descriptions.append(f"{tool_title}{func_descriptions}")
        return "\n\n".join(tool_descriptions)

    async def get_history_view(self) -> MessageHistory:
        return MessageHistory(
            messages=[SystemMessage(content=[Text(text=self.system_prompt)])],
        ) + self.history.history_view(
            limits=self.config.history_messages_limit,
        )

    @retry(
        wait=wait_exponential(multiplier=1, min=4, max=10),
        stop=stop_after_attempt(3),
        reraise=True,
        before_sleep=before_sleep_log(logger, logging.ERROR),
    )
    async def generate_output(
        self,
        use_tool: bool = False,
        response_format: Optional[type[BaseModel]] = None,
        append_assistant_message: bool = True,
    ) -> AssistantMessage:
        messages: MessageHistory = await self.get_history_view()
        response_content = (
            await self.client.create_completion(
                messages=messages,
                temperature=self.temperature,
                seed=self.seed,
                response_format=response_format,
                tools=self.tools if use_tool else None,
            )
        ).model_dump()
        response_content = response_content["choices"][0]["message"]
        assistant_message = AssistantMessage(
            role=response_content["role"],
            content=[Text(text=response_content["content"])] if response_content["content"] else [],
            tool_calls=response_content["tool_calls"],
        )
        if append_assistant_message:
            self.history.append(message=assistant_message, label=self.message_label)
        return assistant_message

    def receive_user_message(
        self,
        text: Optional[str] = None,
        image: list[bytes] = None,
        label: MessageLabel = None,
        is_base64: bool = False,
    ) -> None:
        message = UserMessage.from_media(
            text=text,
            image=image,
            is_base64=is_base64,
        )
        self.history.append(message=message, label=label)

    def receive_system_message(
        self,
        text: Optional[str] = None,
        label: MessageLabel = None,
    ) -> None:
        message = SystemMessage.from_media(text=text)
        self.history.append(message=message, label=label)

    def receive_assistant_message(
        self,
        content: Optional[str] = None,
        tool_calls: Optional[list[ToolCall]] = None,
        label: MessageLabel = None,
    ) -> None:
        message = AssistantMessage(
            content=[Text(text=content)] if content else [],
            tool_calls=tool_calls,
        )
        self.history.append(message=message, label=label)

    async def use_tool(self, tool_call: ToolCall):
        function = tool_call.function
        for tool in self.tools:
            if hasattr(tool, function["name"]):
                return await getattr(tool, function["name"])(
                    **json.loads(function["arguments"]),
                )
        msg = f'No tool function with name "{function["name"]}"'
        raise ValueError(msg)

    async def receive_tool_message(
        self,
        text: str,
        tool_id: str,
        label: MessageLabel = None,
    ) -> None:
        self.history.append(
            message=ToolMessage(content=[Text(text=text)], tool_call_id=tool_id),
            label=label,
        )


class Agents:
    _agent_registry: dict[str, type[BaseAgent]] = {}
    _agent_config_registry: dict[str, type[BaseAgentConfig]] = {}

    @classmethod
    def register_agent(cls, name: str):
        """
        Decorator to register an Agent class under a given name.

        Example:
            @Agents.register_agent("browser")
            class BrowserAgent(BaseAgent):
                ...
        """

        def decorator(agent_cls: type[BaseAgent]) -> type[BaseAgent]:
            cls._agent_registry[name] = agent_cls
            return agent_cls

        return decorator

    @classmethod
    def register_agent_config(cls, name: str):
        """
        Decorator to register a configuration class under a given name.

        Example:
            @Agents.register_agent_config("browser")
            class BrowserAgentConfig(BaseAgentConfig):
                ...
        """

        def decorator(config_cls: type[BaseAgentConfig]) -> type[BaseAgentConfig]:
            cls._agent_config_registry[name] = config_cls
            return config_cls

        return decorator

    @classmethod
    def get(cls, name: str) -> type[BaseAgent]:
        """
        Retrieve a registered Agent class by its name.

        Raises:
            ValueError: If no such agent is found.
        """
        try:
            return cast(Type[BaseAgent], cls._agent_registry[name])
        except KeyError:
            raise ValueError(f"Agent '{name}' not found.")

    @classmethod
    def get_config(cls, name: str) -> type[BaseAgentConfig]:
        """
        Retrieve a registered Agent configuration class by its name.

        Raises:
            ValueError: If no such config is found.
        """
        try:
            return cast(type[BaseAgentConfig], cls._agent_config_registry[name])
        except KeyError:
            raise ValueError(f"Agent config for '{name}' not found.")
