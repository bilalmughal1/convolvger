"""Mapping of a decoded ChatGPT share snapshot onto a Conversation."""

from datetime import UTC, datetime
from typing import Any

from convolvger.core.models import Conversation, Message, MessageRole
from convolvger.core.results import ParseError, ParseResult
from convolvger.core.source import RawSource
from convolvger.providers.chatgpt._content import to_blocks
from convolvger.providers.chatgpt._turbostream import decode_html

PROVIDER = "chatgpt"
PASSTHROUGH_KEYS = ("channel", "end_turn")


def _timestamp(value: Any) -> datetime | None:
    if isinstance(value, int | float):
        return datetime.fromtimestamp(value, tz=UTC)
    return None


def _role(raw: Any, warnings: list[str]) -> MessageRole:
    try:
        return MessageRole(raw)
    except ValueError:
        warnings.append(f"unrecognised role preserved as unknown: {raw!r}")
        return MessageRole.UNKNOWN


def _active(weight: Any, warnings: list[str]) -> bool:
    if weight in (0, 0.0):
        return False
    if weight in (1, 1.0):
        return True
    warnings.append(f"unexpected message weight treated as active: {weight!r}")
    return True


def _share_payload(decoded: dict[str, Any], warnings: list[str]) -> dict[str, Any]:
    loader = decoded.get("loaderData")
    if not isinstance(loader, dict):
        raise ParseError("Snapshot has no loaderData", warnings)

    for value in loader.values():
        if isinstance(value, dict) and "serverResponse" in value:
            server = value["serverResponse"]
            if isinstance(server, dict) and isinstance(server.get("data"), dict):
                return server["data"]

    raise ParseError("Snapshot contains no shared conversation payload", warnings)


def _message(node: dict[str, Any], warnings: list[str]) -> Message | None:
    raw = node.get("message")
    if not isinstance(raw, dict):
        return None

    author = raw.get("author") or {}
    metadata = raw.get("metadata") or {}
    content = to_blocks(raw.get("content"), warnings)
    if not content:
        content_type = (raw.get("content") or {}).get("content_type")
        warnings.append(
            f"message {raw.get('id')} produced no content blocks "
            f"(content_type={content_type!r})"
        )
    passthrough = {
        key: raw[key] for key in PASSTHROUGH_KEYS if raw.get(key) is not None
    }

    return Message(
        id=raw.get("id"),
        role=_role(author.get("role"), warnings),
        author=author.get("name"),
        timestamp=_timestamp(raw.get("create_time")),
        content=content,
        visible=not metadata.get("is_visually_hidden_from_conversation", False),
        active=_active(raw.get("weight"), warnings),
        status=raw.get("status"),
        recipient=raw.get("recipient"),
        provider_metadata=passthrough,
    )


def parse(source: RawSource) -> ParseResult:
    """Convert a fetched ChatGPT share snapshot into a Conversation."""
    decoded = decode_html(source.content)
    warnings = list(decoded.warnings)

    payload = _share_payload(decoded.value, warnings)
    nodes = payload.get("linear_conversation")
    if not isinstance(nodes, list):
        raise ParseError("Snapshot has no linear_conversation", warnings)

    messages = [
        message
        for node in nodes
        if isinstance(node, dict) and (message := _message(node, warnings)) is not None
    ]
    if not messages:
        raise ParseError("Snapshot contains no messages", warnings)

    conversation = Conversation(
        id=payload.get("conversation_id") or payload.get("id"),
        provider=PROVIDER,
        source_url=source.url,
        title=payload.get("title"),
        created_at=_timestamp(payload.get("create_time")),
        updated_at=_timestamp(payload.get("update_time")),
        messages=messages,
    )
    return ParseResult(conversation=conversation, warnings=warnings)
