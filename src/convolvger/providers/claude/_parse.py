"""Mapping of a saved Claude snapshot onto a Conversation.

The snapshot is plain JSON: no stream to decode, no index references to
resolve. The work here is deciding what the envelope's fields mean and
recording what it declared but did not serve.

Nothing is dropped. Every envelope or message key this version does not
model canonically is preserved in ``provider_metadata`` -- including
``created_by`` and ``creator``, which name the account that shared the
snapshot. The JSON export is the archival package and omits nothing;
the Markdown export never reads ``provider_metadata``, so a shared
document does not carry them. A tool that reports what a provider
withheld cannot quietly withhold in turn.
"""

import json
from datetime import datetime
from typing import Any

from convolvger.core.findings import Finding, collapse, finding
from convolvger.core.models import Conversation, Message, MessageRole
from convolvger.core.results import ParseError, ParseResult
from convolvger.core.source import RawSource
from convolvger.providers.claude._content import to_blocks

PROVIDER = "claude"

ROLES = {"human": MessageRole.USER, "assistant": MessageRole.ASSISTANT}
"""The only two senders observed. Anything else is recorded, not guessed."""

ENVELOPE_MAPPED_KEYS = frozenset(
    {"uuid", "snapshot_name", "created_at", "updated_at", "chat_messages"}
)
MESSAGE_MAPPED_KEYS = frozenset(
    {"uuid", "sender", "created_at", "content", "stop_reason"}
)


def _extras(source: dict[str, Any], mapped: frozenset[str]) -> dict[str, Any]:
    return {key: value for key, value in source.items() if key not in mapped}


def _timestamp(value: Any) -> datetime | None:
    """Read an ISO 8601 instant, or record nothing rather than guess."""
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _role(sender: Any, findings: list[Finding], message_id: str | None) -> MessageRole:
    known = ROLES.get(sender) if isinstance(sender, str) else None
    if known is not None:
        return known
    findings.append(
        finding("unrecognised_role", f"{sender!r} preserved as unknown", message_id)
    )
    return MessageRole.UNKNOWN


def _message(raw: dict[str, Any], findings: list[Finding]) -> Message:
    message_id = raw.get("uuid") if isinstance(raw.get("uuid"), str) else None
    metadata = _extras(raw, MESSAGE_MAPPED_KEYS)
    content = to_blocks(raw.get("content"), findings, metadata, message_id)

    if not content:
        findings.append(
            finding("message_has_no_content", "no content blocks", message_id)
        )

    declared = raw.get("file_count")
    if (
        isinstance(declared, int)
        and not isinstance(declared, bool)
        and declared > 0
        and not raw.get("files")
        and not raw.get("attachments")
    ):
        findings.append(
            finding(
                "attachment_withheld",
                f"{declared} declared, none carried",
                message_id,
            )
        )

    status = raw.get("stop_reason")
    return Message(
        id=message_id,
        role=_role(raw.get("sender"), findings, message_id),
        timestamp=_timestamp(raw.get("created_at")),
        content=content,
        status=status if isinstance(status, str) else None,
        provider_metadata=metadata,
    )


def parse(source: RawSource) -> ParseResult:
    """Convert a saved Claude chat snapshot into a Conversation."""
    try:
        envelope = json.loads(source.content)
    except json.JSONDecodeError as exc:
        raise ParseError(f"Snapshot is not valid JSON: {exc}") from exc

    if not isinstance(envelope, dict):
        raise ParseError("Snapshot is not a JSON object")

    raw_messages = envelope.get("chat_messages")
    if not isinstance(raw_messages, list):
        raise ParseError("Snapshot has no chat_messages")

    findings: list[Finding] = []
    messages = [
        _message(raw, findings) for raw in raw_messages if isinstance(raw, dict)
    ]
    if not messages:
        raise ParseError("Snapshot contains no messages", findings)

    identifier = envelope.get("uuid")
    title = envelope.get("snapshot_name")
    conversation = Conversation(
        id=identifier if isinstance(identifier, str) else None,
        provider=PROVIDER,
        source_url=source.url,
        title=title if isinstance(title, str) else None,
        created_at=_timestamp(envelope.get("created_at")),
        updated_at=_timestamp(envelope.get("updated_at")),
        messages=messages,
        provider_metadata=_extras(envelope, ENVELOPE_MAPPED_KEYS),
    )
    return ParseResult(conversation=conversation, findings=collapse(findings))
