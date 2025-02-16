from __future__ import annotations

import base64
from collections.abc import Iterator
from enum import Enum
from typing import Any, Literal, Optional, Set, Union

from pydantic import BaseModel, Field, TypeAdapter, field_validator


class MessageLabel(str, Enum):
    SYSTEM = "system"
    USER_INPUT = "user_input"
    SCREENSHOT = "screenshot"
    AGENT_MODEL_RESPONSE = "agent_model_response"


MAX_MESSAGES_FOR_CONTEXT_WINDOW = {
    MessageLabel.SCREENSHOT: 1,
}


class MessageContent(BaseModel):
    pass


class Text(MessageContent):
    type: Literal["text"] = Field(default="text", init=False)
    text: str


class ImageUrl(BaseModel):
    url: str


class Image(MessageContent):
    type: Literal["image_url"] = Field(default="image_url", init=False)
    image_url: ImageUrl


class Message(BaseModel):
    label: Optional[MessageLabel] = None
    content: list[Union[Text, Image]] = Field(default_factory=list)

    class Config:
        use_enum_values = True

    @property
    def images(self) -> list[Image]:
        return [content for content in self.content if isinstance(content, Image)]

    @property
    def texts(self) -> list[Text]:
        return [content for content in self.content if isinstance(content, Text)]

    @property
    def first_image(self) -> Optional[Image]:
        return self.images[0] if self.images else None

    @property
    def first_text(self) -> Optional[Text]:
        return self.texts[0] if self.texts else None

    def __len__(self):
        return len(self.content)

    @classmethod
    def from_media(
        cls,
        text: Optional[str] = None,
        image: Optional[bytes | str] = None,
        is_base64: bool = False,
    ) -> Message:
        if text is not None:
            text = Text(text=text)
        if image is not None:
            base64_image = image if is_base64 else base64.b64encode(image).decode("utf-8")
            data_url = f"data:image/jpeg;base64,{base64_image}"
            image = Image(image_url=ImageUrl(url=data_url))
            content = [text, image] if text is not None else [image]
        else:
            content = [text]
        return cls(content=content)


class SystemMessage(Message):
    role: Literal["system"] = Field(default="system", init=False)


class UserMessage(Message):
    role: Literal["user"] = Field(default="user", init=False)


class ToolCall(BaseModel):
    id: str
    type: str
    function: dict[str, Any]


class AssistantMessage(Message):
    role: Literal["assistant"] = Field(default="assistant", init=False)
    tool_calls: list[ToolCall] = Field(default_factory=list)

    def model_dump(self, **kwargs):
        data = super().model_dump(**kwargs)
        if not self.tool_calls:
            data.pop("tool_calls")
        return data

    @field_validator("tool_calls", mode="before")
    @classmethod
    def ensure_list(cls, v):
        return [] if v is None else v


class ToolMessage(Message):
    role: Literal["tool"] = Field(default="tool", init=False)
    tool_call_id: str


MessageTypes = Union[SystemMessage, UserMessage, AssistantMessage, ToolMessage]
MessageAdapter = TypeAdapter(MessageTypes)


class MessageHistory(BaseModel):
    messages: list[MessageTypes] = Field(default_factory=list)

    def append(self, message: MessageTypes, label: Optional[str] = None):
        if label is not None:
            message.label = label
        self.messages.append(message)

    def pop(self) -> MessageTypes:
        return self.messages.pop()

    def extend(self, history: MessageHistory):
        self.messages.extend(history.messages)

    def __reversed__(self):
        return MessageHistory(messages=self.messages[::-1])

    def __getitem__(self, index):
        return self.messages[index]

    def __len__(self):
        return len(self.messages)

    def __iter__(self) -> Iterator[MessageTypes]:
        return iter(self.messages)

    def to_dict(self, exclude: Set[str] | None = None) -> list[dict]:
        exclude = exclude or set()
        return [message.model_dump(exclude=exclude) for message in self.messages]

    def history_view(
        self,
        limits: dict = MAX_MESSAGES_FOR_CONTEXT_WINDOW,
    ) -> MessageHistory:
        """Context window management.

        Filters messages in reverse order, retaining a limited number of recent screenshots and prompts.
        """
        label_counts = {label: 0 for label in limits}
        filtered_messages = []
        for message in reversed(self.messages):
            if message.label in limits:
                maximum_count = limits[message.label]
                if label_counts[message.label] < maximum_count:
                    filtered_messages.append(message)
                    label_counts[message.label] += 1
            else:
                filtered_messages.append(message)
        return MessageHistory(messages=reversed(filtered_messages))

    def __add__(self, other: MessageHistory) -> MessageHistory:
        new_history = MessageHistory()
        new_history.extend(self)
        new_history.extend(other)
        return new_history

    def __iadd__(self, other: MessageHistory) -> MessageHistory:
        self.extend(other)
        return self
