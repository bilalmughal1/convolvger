"""Mapping of a decoded ChatGPT share snapshot onto a Conversation."""

from datetime import UTC, datetime
from typing import Any

from convolvger.core.findings import Finding, finding
from convolvger.core.models import Conversation, Message, MessageRole
from convolvger.core.results import ParseError, ParseResult
from convolvger.core.source import RawSource
from convolvger.providers.chatgpt._content import to_blocks
from convolvger.providers.chatgpt._turbostream import decode_html

PROVIDER = "chatgpt"
PASSTHROUGH_KEYS = ("channel", "end_turn")

SCAFFOLDING_RECIPIENTS = (None, "all", "assistant")
"""Recipients that address a message inside the conversation.

A recipient outside this set names a tool, so an empty message sent
there is content the snapshot did not carry. An empty message
addressed inside the conversation is expected instead: OpenAI does
not share custom instructions with share-link viewers, so those
nodes arrive empty in every such capture.
"""


def _timestamp(value: Any) -> datetime | None:
    if isinstance(value, int | float):
        return datetime.fromtimestamp(value, tz=UTC)
    return None


def _role(raw: Any, findings: list[Finding]) -> MessageRole:
    try:
        return MessageRole(raw)
    except ValueError:
        findings.append(
            finding("unrecognised_role", f"{raw!r} preserved as unknown")
        )
        return MessageRole.UNKNOWN


_ABSENT = object()
"""Marks a weight the snapshot did not carry at all.

``dict.get`` cannot tell an omitted key from an explicit null, and the
two mean different things: one is a field this snapshot never had, the
other is a value ChatGPT was not expected to send.
"""


def _active(
    weight: Any, findings: list[Finding], message_id: str | None = None
) -> bool:
    if weight is _ABSENT:
        findings.append(
            finding(
                "message_weight_absent",
                "no weight in snapshot; recorded as active",
                message_id,
            )
        )
        return True
    if weight in (0, 0.0):
        return False
    if weight in (1, 1.0):
        return True
    findings.append(
        finding(
            "unexpected_message_weight", f"{weight!r} treated as active"
        )
    )
    return True


def _share_payload(
    decoded: dict[str, Any], findings: list[Finding]
) -> dict[str, Any]:
    loader = decoded.get("loaderData")
    if not isinstance(loader, dict):
        raise ParseError("Snapshot has no loaderData", findings)

    for value in loader.values():
        if isinstance(value, dict) and "serverResponse" in value:
            server = value["serverResponse"]
            if isinstance(server, dict) and isinstance(server.get("data"), dict):
                return server["data"]

    raise ParseError("Snapshot contains no shared conversation payload", findings)


def _message(node: dict[str, Any], findings: list[Finding]) -> Message | None:
    raw = node.get("message")
    if not isinstance(raw, dict):
        return None

    author = raw.get("author") or {}
    metadata = raw.get("metadata") or {}
    content = to_blocks(raw.get("content"), findings)
    if not content:
        content_type = (raw.get("content") or {}).get("content_type")
        withheld = raw.get("recipient") not in SCAFFOLDING_RECIPIENTS
        findings.append(
            finding(
                "message_content_withheld" if withheld else "message_has_no_content",
                f"no content blocks (content_type={content_type!r})",
                raw.get("id"),
            )
        )
    passthrough = {
        key: raw[key] for key in PASSTHROUGH_KEYS if raw.get(key) is not None
    }

    return Message(
        id=raw.get("id"),
        role=_role(author.get("role"), findings),
        author=author.get("name"),
        timestamp=_timestamp(raw.get("create_time")),
        content=content,
        visible=not metadata.get("is_visually_hidden_from_conversation", False),
        active=_active(raw.get("weight", _ABSENT), findings, raw.get("id")),
        status=raw.get("status"),
        recipient=raw.get("recipient"),
        provider_metadata=passthrough,
    )


def parse(source: RawSource) -> ParseResult:
    """Convert a fetched ChatGPT share snapshot into a Conversation."""
    decoded = decode_html(source.content)
    findings = list(decoded.findings)

    payload = _share_payload(decoded.value, findings)
    nodes = payload.get("linear_conversation")
    if not isinstance(nodes, list):
        raise ParseError("Snapshot has no linear_conversation", findings)

    messages = [
        message
        for node in nodes
        if isinstance(node, dict) and (message := _message(node, findings)) is not None
    ]
    if not messages:
        raise ParseError("Snapshot contains no messages", findings)

    conversation = Conversation(
        id=payload.get("conversation_id") or payload.get("id"),
        provider=PROVIDER,
        source_url=source.url,
        title=payload.get("title"),
        created_at=_timestamp(payload.get("create_time")),
        updated_at=_timestamp(payload.get("update_time")),
        messages=messages,
    )
    return ParseResult(conversation=conversation, findings=findings)
