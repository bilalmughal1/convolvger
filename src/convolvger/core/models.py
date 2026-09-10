from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"
    UNKNOWN = "unknown"


class ContentBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    content: str


class Message(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str | None = None
    role: MessageRole
    author: str | None = None
    timestamp: datetime | None = None
    content: list[ContentBlock] = Field(default_factory=list)


class Conversation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str | None = None
    provider: str
    source_url: str
    title: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    messages: list[Message] = Field(default_factory=list)
