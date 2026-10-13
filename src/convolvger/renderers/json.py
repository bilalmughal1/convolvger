"""JSON rendering of a canonical conversation.

Where Markdown is a dissemination package that may omit content, this is
the archival package: it omits nothing the canonical model holds. Hidden
messages, deactivated branches, messages with no renderable content,
provider_metadata and unrecognised blocks are all written out.

No serialisation exclude flags are used here, and none should be added.
exclude_defaults in particular drops an UnknownBlock's empty raw, which
is the only field stopping that block from validating as a TextBlock on
reload, so the block would silently change type.

A conversation the serialiser cannot write is refused with a
``RenderError``. Sources are held to a depth that every platform
measured can serialise (see ``core.jsonload``), so this is not expected
to happen; it is here because that depth belongs to pydantic-core and
differs by platform -- 98 levels on Windows, 254 on Linux, measured on
2.46.5 -- and a later release could lower it.

Nothing here is provider-specific.
"""

from datetime import datetime

from convolvger.core.archive import ArchiveEnvelope
from convolvger.core.errors import ConvolvgerError
from convolvger.core.findings import Finding
from convolvger.core.models import Conversation


class RenderError(ConvolvgerError):
    """Raised when a conversation cannot be written as an archive."""


def render_json(
    conversation: Conversation,
    *,
    findings: list[Finding] | None = None,
    fetched_at: datetime | None = None,
) -> str:
    """Render a conversation as a complete, portable archival record."""
    envelope = ArchiveEnvelope(
        retrieved_at=fetched_at,
        findings=list(findings or []),
        conversation=conversation,
    )
    # A refusal from the serialiser is pydantic-core's
    # PydanticSerializationError, a ValueError. It is caught by that base
    # so this module needs nothing pydantic does not itself export.
    try:
        return envelope.model_dump_json(indent=2) + "\n"
    except ValueError as error:
        raise RenderError(f"The archive could not be written: {error}") from error
