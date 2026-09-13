from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"
    UNKNOWN = "unknown"


class TextBlock(BaseModel):
    """Plain prose or Markdown authored by a participant."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["text"] = "text"
    text: str


class CodeBlock(BaseModel):
    """Source code, a command, or a tool invocation payload."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["code"] = "code"
    text: str
    language: str | None = None


class ReasoningBlock(BaseModel):
    """A reasoning summary exposed by the provider's public snapshot.

    This is not hidden chain-of-thought. It holds only what the snapshot
    itself discloses, kept separate from assistant output so renderers
    never present the two as equivalent.
    """

    model_config = ConfigDict(extra="forbid")

    type: Literal["reasoning"] = "reasoning"
    text: str
    label: str | None = None


class UnknownBlock(BaseModel):
    """A block whose type this version does not model.

    Unrecognised content is preserved verbatim in ``raw`` rather than
    dropped, so an archive never loses recoverable content to a provider
    format that changed after this release.
    """

    model_config = ConfigDict(extra="forbid")

    type: str
    text: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class ToolUseBlock(BaseModel):
    """A tool the assistant invoked, as the snapshot recorded it."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["tool_use"] = "tool_use"
    name: str
    id: str | None = None
    input: dict[str, Any] = Field(default_factory=dict)
    raw: dict[str, Any] = Field(default_factory=dict)


class ToolResultBlock(BaseModel):
    """What a tool returned, as the snapshot carried it.

    ``content`` is empty when the snapshot carried no payload. That is
    not the same as a tool that returned nothing, and the distinction
    is not recoverable from the data, so it is recorded as a finding
    rather than decided here.
    """

    model_config = ConfigDict(extra="forbid")

    type: Literal["tool_result"] = "tool_result"
    tool_use_id: str | None = None
    name: str | None = None
    is_error: bool = False
    content: list["ContentBlock"] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)


KnownBlock = Annotated[
    TextBlock | CodeBlock | ReasoningBlock | ToolUseBlock | ToolResultBlock,
    Field(discriminator="type"),
]

ContentBlock = Annotated[
    KnownBlock | UnknownBlock,
    Field(union_mode="left_to_right"),
]

ToolResultBlock.model_rebuild()


class Message(BaseModel):
    """A single turn in a conversation.

    ``provider_metadata`` holds source fields this version does not model
    canonically, so nothing recoverable is lost. Renderers must not read
    it; it exists for validation and lossless export only.
    """

    model_config = ConfigDict(extra="forbid")

    id: str | None = None
    role: MessageRole
    author: str | None = None
    timestamp: datetime | None = None
    content: list[ContentBlock] = Field(default_factory=list)
    visible: bool = True
    active: bool = True
    status: str | None = None
    recipient: str | None = None
    provider_metadata: dict[str, Any] = Field(default_factory=dict)


class Conversation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str | None = None
    provider: str
    source_url: str
    title: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    messages: list[Message] = Field(default_factory=list)
