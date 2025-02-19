import json
import logging
from abc import ABC, abstractmethod
from enum import Enum
from functools import cached_property
from typing import Any, Literal, Optional, Self

from pydantic import BaseModel

from proxy_lite.history import ToolCall
from proxy_lite.tools import Tool, ToolExecutionResponse


class EventType(str, Enum):
    OBSERVATION = "observation"
    ACTION = "action"
    MESSAGE = "message"


class Event(BaseModel):
    type: EventType


class State(BaseModel):
    text: Optional[str] = None
    image: Optional[str] = None  # base64 encoded image
    html: Optional[str] = None
    tool_responses: Optional[list[ToolExecutionResponse]] = None


class Observation(Event):
    type: Literal[EventType.OBSERVATION] = EventType.OBSERVATION
    state: State
    terminated: bool
    reward: Optional[float] = None
    info: Optional[dict[str, Any]] = None


class Action(Event):
    type: Literal[EventType.ACTION] = EventType.ACTION
    text: Optional[str] = None
    tool_calls: Optional[list[ToolCall]] = None
    info: Optional[dict[str, Any]] = None


class BaseEnvironmentConfig(BaseModel): ...


class BaseEnvironment(BaseModel, ABC):
    config: BaseEnvironmentConfig
    logger: logging.Logger | None = None

    class Config:
        arbitrary_types_allowed = True

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        pass

    @property
    @abstractmethod
    def info_for_user(self) -> str: ...

    @cached_property
    @abstractmethod
    def tools(self) -> list[Tool]: ...

    @abstractmethod
    async def initialise(self) -> Observation: ...

    @abstractmethod
    async def execute_action(self, action: Action) -> Observation: ...

    @abstractmethod
    async def observe(self) -> Observation: ...

    @abstractmethod
    async def evaluate(self, **kwargs: dict[str, Any]) -> dict[str, Any]: ...

    async def execute_tool(self, tool_call: ToolCall) -> None:
        function = tool_call.function
        for tool in self.tools:
            if hasattr(tool, function["name"]):
                arguments = json.loads(function["arguments"])
                if isinstance(arguments, str):
                    arguments = json.loads(arguments)
                return await getattr(tool, function["name"])(
                    **arguments,
                )
        msg = f'No tool function with name "{function["name"]}"'
        raise ValueError(msg)

    async def get_info(self) -> dict[str, Any]:
        return {}


class Environments:
    _environment_registry: dict[str, type[BaseEnvironment]] = {}
    _environment_config_registry: dict[str, type[BaseEnvironmentConfig]] = {}

    @classmethod
    def register_environment(cls, name: str):
        """
        Decorator to register an Environment class under a given name.

        Example:
            @Environments.register_environment("my_environment")
            class MyEnvironment(BaseEnvironment):
                ...
        """

        def decorator(env_cls: type[BaseEnvironment]) -> type[BaseEnvironment]:
            cls._environment_registry[name] = env_cls
            return env_cls

        return decorator

    @classmethod
    def register_environment_config(cls, name: str):
        """
        Decorator to register an Environment configuration class under a given name.

        Example:
            @Environments.register_environment_config("my_environment")
            class MyEnvironmentConfig(BaseEnvironmentConfig):
                ...
        """

        def decorator(config_cls: type[BaseEnvironmentConfig]) -> type[BaseEnvironmentConfig]:
            cls._environment_config_registry[name] = config_cls
            return config_cls

        return decorator

    @classmethod
    def get(cls, name: str) -> type[BaseEnvironment]:
        """
        Retrieve a registered Environment class by its name.

        Raises:
            ValueError: If no such environment is found.
        """
        try:
            return cls._environment_registry[name]
        except KeyError:
            raise ValueError(f"Environment '{name}' not found.")

    @classmethod
    def get_config(cls, name: str) -> type[BaseEnvironmentConfig]:
        """
        Retrieve a registered Environment configuration class by its name.

        Raises:
            ValueError: If no such configuration is found.
        """
        try:
            return cls._environment_config_registry[name]
        except KeyError:
            raise ValueError(f"Environment config for '{name}' not found.")
