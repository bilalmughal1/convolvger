"""The archival package produced by the JSON export.

The Markdown renderer is a dissemination package and may omit content.
This is the archival package: it omits nothing the canonical model holds.

Extraction findings and the retrieval time describe the capture event
rather than the conversation, so they sit beside the conversation here,
matching ``ParseResult`` rather than contradicting it. ``conversation``
alone round-trips back to an equal ``Conversation``.
"""

import json
from datetime import datetime
from importlib.metadata import PackageNotFoundError, version

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from convolvger.core.errors import ConvolvgerError
from convolvger.core.findings import Finding
from convolvger.core.models import Conversation

SCHEMA_VERSION = 2
"""Bumped only when a change would stop an older reader loading a file.

Version 2 replaced the ``warnings`` list of strings with ``findings``.
Adding a field is safe for a reader that allows unknown ones; removing
or renaming one is not.
"""


class ArchiveError(ConvolvgerError):
    """Raised when a file cannot be read as an archive of this version.

    Lives here rather than in ``errors`` for the same reason
    ``ParseError`` lives beside the parser: it belongs to the format it
    guards.
    """


def _tool_version() -> str:
    try:
        return version("convolvger")
    except PackageNotFoundError:
        return "unknown"


class ArchiveEnvelope(BaseModel):
    """A conversation together with the provenance of its capture.

    ``extra="allow"``, unlike every other model here. An archive is a
    permanent file that a later version of this tool must be able to
    read: forbidding unknown fields would make every future addition a
    breaking change, and ignoring them would drop them on
    re-serialisation. Allowing them preserves a field this version does
    not model. The canonical models keep ``forbid`` -- they guard an
    internal invariant, not a file format.
    """

    model_config = ConfigDict(extra="allow")

    schema_version: int = SCHEMA_VERSION
    tool: str = "convolvger"
    tool_version: str = Field(default_factory=_tool_version)
    retrieved_at: datetime | None = None
    findings: list[Finding] = Field(default_factory=list)
    conversation: Conversation


def load_archive(text: str) -> ArchiveEnvelope:
    """Read an archive this version can vouch for, or refuse it.

    The declared schema version is checked before anything else is
    trusted, because the envelope alone will not refuse a file it cannot
    truthfully represent. A version 1 archive validates quite happily:
    its ``warnings`` list survives as an unknown field and ``findings``
    defaults to empty, so a reader that skipped this check would
    pronounce a file recording real damage entirely clean. Refusal is
    the only honest answer for a format this version cannot read as its
    own.

    Nothing here touches the filesystem. The caller owns reading the
    file, as it already owns writing one.
    """
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as error:
        raise ArchiveError(f"Not JSON: {error}") from error

    if not isinstance(payload, dict):
        raise ArchiveError(
            f"Not an archive: expected an object, found {type(payload).__name__}"
        )

    declared = payload.get("schema_version")
    if not isinstance(declared, int):
        raise ArchiveError("Not an archive: no schema_version")
    if declared != SCHEMA_VERSION:
        raise ArchiveError(
            f"Archive declares schema version {declared}; "
            f"this version reads {SCHEMA_VERSION}"
        )

    try:
        return ArchiveEnvelope.model_validate(payload)
    except ValidationError as error:
        raise ArchiveError(f"Archive is not a valid envelope: {error}") from error
