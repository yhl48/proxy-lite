import itertools
from abc import ABC, abstractmethod

from pydantic import BaseModel

from proxy_lite.history import MessageAdapter, MessageHistory
from proxy_lite.tools import Tool


class BaseSerializer(BaseModel, ABC):
    """Base class for serializers.

    Serializers are responsible for converting between the internal MessageHistory/Tool
    objects and the external API format. Deserialise is not always possible, so raise
    appropriate warnings.
    """

    @abstractmethod
    def serialize_messages(self, message_history: MessageHistory) -> list[dict]: ...

    @abstractmethod
    def deserialize_messages(self, data: list[dict]) -> MessageHistory: ...

    @abstractmethod
    def serialize_tools(self, tools: list[Tool]) -> list[dict]: ...


class OpenAICompatibleSerializer(BaseSerializer):
    def serialize_messages(self, message_history: MessageHistory) -> list[dict]:
        return message_history.to_dict(exclude={"label"})

    def deserialize_messages(self, data: list[dict]) -> MessageHistory:
        return MessageHistory(
            messages=[MessageAdapter.validate_python(message) for message in data],
        )

    def serialize_tools(self, tools: list[Tool]) -> list[dict]:
        tool_schemas = [[{"type": "function", "function": schema} for schema in tool.schema] for tool in tools]
        return list(itertools.chain.from_iterable(tool_schemas))
