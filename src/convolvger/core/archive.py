"""The archival package produced by the JSON export.

The Markdown renderer is a dissemination package and may omit content.
This is the archival package: it omits nothing the canonical model holds.

Extraction warnings and the retrieval time describe the capture event
rather than the conversation, so they sit beside the conversation here,
matching ``ParseResult`` rather than contradicting it. ``conversation``
alone round-trips back to an equal ``Conversation``.
"""

from datetime import datetime
from importlib.metadata import PackageNotFoundError, version

from pydantic import BaseModel, ConfigDict, Field

from convolvger.core.models import Conversation

SCHEMA_VERSION = 1
"""Bumped only when a change would stop an older reader loading a file."""


def _tool_version() -> str:
    try:
        return version("convolvger")
    except PackageNotFoundError:
        return "unknown"


class ArchiveEnvelope(BaseModel):
    """A conversation together with the provenance of its capture."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = SCHEMA_VERSION
    tool: str = "convolvger"
    tool_version: str = Field(default_factory=_tool_version)
    retrieved_at: datetime | None = None
    warnings: list[str] = Field(default_factory=list)
    conversation: Conversation
