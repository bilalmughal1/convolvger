"""JSON rendering of a canonical conversation.

Where Markdown is a dissemination package that may omit content, this is
the archival package: it omits nothing the canonical model holds. Hidden
messages, deactivated branches, messages with no renderable content,
provider_metadata and unrecognised blocks are all written out.

No serialisation exclude flags are used here, and none should be added.
exclude_defaults in particular drops an UnknownBlock's empty raw, which
is the only field stopping that block from validating as a TextBlock on
reload, so the block would silently change type.

Nothing here is provider-specific.
"""

from datetime import datetime

from convolvger.core.archive import ArchiveEnvelope
from convolvger.core.findings import Finding
from convolvger.core.models import Conversation


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
    return envelope.model_dump_json(indent=2) + "\n"
