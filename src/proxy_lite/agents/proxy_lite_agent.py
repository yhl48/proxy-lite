from functools import cached_property
from typing import Literal

from pydantic import Field

from proxy_lite.history import MessageHistory, MessageLabel, SystemMessage, Text
from proxy_lite.tools import Tool

from .agent_base import Agents, BaseAgent, BaseAgentConfig

MODEL_SYSTEM_PROMPT = """You are Proxy-Lite, an AI assistant that can perform actions on a computer screen.
You were developed by Convergence AI.
The user will instuct you to perform a task.
You will be shown a screen as well as relevant interactable elements highlighted by mark_ids and you will be given a set of tools to use to perform the task.
You should make observations about the screen, putting them in <observation></observation> tags.
You should then reason about what needs to be done to complete the task, putting your thoughts in <thinking></thinking> tags.
You should then use the tools to perform the task, putting the tool calls in <tool_call></tool_call> tags.
"""  # noqa: E501

MAX_MESSAGES_FOR_CONTEXT_WINDOW = {
    MessageLabel.SCREENSHOT: 1,
}


@Agents.register_agent_config("proxy_lite")
class ProxyLiteAgentConfig(BaseAgentConfig):
    name: Literal["proxy_lite"] = "proxy_lite"
    history_messages_limit: dict[MessageLabel, int] = Field(
        default_factory=lambda: MAX_MESSAGES_FOR_CONTEXT_WINDOW,
    )


@Agents.register_agent("proxy_lite")
class ProxyLiteAgent(BaseAgent):
    config: ProxyLiteAgentConfig
    message_label: MessageLabel = MessageLabel.AGENT_MODEL_RESPONSE

    def __init__(self, **data):
        super().__init__(**data)

    @property
    def system_prompt(self) -> str:
        return MODEL_SYSTEM_PROMPT

    @cached_property
    def tools(self) -> list[Tool]:
        return self.env_tools

    async def get_history_view(self) -> MessageHistory:
        return MessageHistory(
            messages=[SystemMessage(content=[Text(text=self.system_prompt)])],
        ) + self.history.history_view(
            limits=self.config.history_messages_limit,
        )
