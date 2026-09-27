"""Mapping of a DeepSeek share payload onto a Conversation.

The payload is keyed JSON inside two envelopes, measured as::

    {"code": 0, "msg": "", "data": {"biz_code": 0, "biz_msg": "",
     "biz_data": {"title", "model_type",
                  "messages": [{"message_id", "parent_id", "role",
                                "status", "inserted_at", "fragments",
                                ...}, ...]}}}

An unknown share id answers with the same status and shape, ``biz_code``
1 and ``biz_data`` null, so the envelope is read rather than the status.

The title a share carries was measured as the generic "Shared
Conversation", not the conversation's own title. It is kept as served:
inventing one from the first message would put words in the archive the
provider did not.

Messages are taken in the order served, which follows ``parent_id``.
They are not sorted by ``inserted_at``: an answer was measured with a
time three milliseconds earlier than the question it answers.

A message is a list of fragments. ``REQUEST`` and ``RESPONSE`` carry the
text a reader sees. ``SEARCH`` carries the queries the model ran and the
results it got back, kept in ``provider_metadata`` as Gemini's are. Any
other fragment -- a model's thinking, when enabled, was not observed --
is kept there too and flagged.

An answer cites its results inline as ``[citation:N]``, where N is a
result's ``cite_index`` in the same message. A marker that resolves is
lifted out of the visible text, and the fragment's served text is kept
verbatim beside it; one that does not resolve is left and reported. A
marker inside code is content and is never touched.
"""

import json
import re
from datetime import UTC, datetime
from typing import Any

from convolvger.core.citations import lift
from convolvger.core.findings import Finding, collapse, finding
from convolvger.core.models import (
    ContentBlock,
    Conversation,
    Message,
    MessageRole,
    TextBlock,
)
from convolvger.core.results import ParseError, ParseResult
from convolvger.core.source import RawSource

PROVIDER = "deepseek"

ROLES = {"USER": MessageRole.USER, "ASSISTANT": MessageRole.ASSISTANT}
"""The only two roles observed. Anything else is recorded, not guessed."""

FINISHED = "FINISHED"
TEXT_KINDS = frozenset({"REQUEST", "RESPONSE"})
SEARCH_KIND = "SEARCH"
CITATION = re.compile(r"\[citation:(\d+)\]")

FRAGMENTS_KEY = "fragment_extras"
"""Where each fragment's unmodelled fields land, keyed by its position."""


def _body(payload: Any) -> Any:
    data = payload.get("data") if isinstance(payload, dict) else None
    return data.get("biz_data") if isinstance(data, dict) else None


def carries_nothing(payload: Any) -> bool:
    """True for a well-formed answer that holds no conversation.

    Measured: an unknown or empty share id answers ``biz_code`` 1,
    "share does not exist", with ``biz_data`` null and the same status as
    a real share.
    """
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), dict):
        return False
    body = _body(payload)
    return body is None or (isinstance(body, dict) and not body.get("messages"))


def _cited(fragments: list[Any]) -> set[str]:
    """Return the citation numbers a message's search results answer to."""
    numbers: set[str] = set()
    for fragment in fragments:
        if isinstance(fragment, dict) and fragment.get("type") == SEARCH_KIND:
            for result in fragment.get("results") or []:
                index = result.get("cite_index") if isinstance(result, dict) else None
                if isinstance(index, int) and not isinstance(index, bool):
                    numbers.add(str(index))
    return numbers


def _fragments(
    raw: Any, findings: list[Finding], message_id: str | None
) -> tuple[list[ContentBlock], dict[str, Any]]:
    fragments = raw if isinstance(raw, list) else []
    cited = _cited(fragments)
    content: list[ContentBlock] = []
    extras: dict[str, Any] = {}

    for index, fragment in enumerate(fragments):
        position = str(index)
        kind = fragment.get("type") if isinstance(fragment, dict) else None
        text = fragment.get("content") if isinstance(fragment, dict) else None

        if isinstance(fragment, dict) and kind in TEXT_KINDS and isinstance(text, str):
            visible = text
            if kind == "RESPONSE":
                outcome = lift(text, CITATION, cited.__contains__)
                visible = outcome.text
                for marker in outcome.unresolved:
                    findings.append(
                        finding(
                            "unmodelled_content_type",
                            f"{marker} names no search result, preserved in text",
                            message_id,
                        )
                    )
            if visible:
                content.append(TextBlock(text=visible))
            rest = {key: value for key, value in fragment.items() if key != "content"}
            if visible != text or not visible:
                # Kept whenever no text block holds the served string exactly.
                rest["content"] = text
            extras[position] = rest
            continue

        extras[position] = fragment
        if kind == SEARCH_KIND:
            continue
        label = kind if isinstance(kind, str) else type(fragment).__name__
        findings.append(
            finding(
                "unmodelled_content_type",
                f"{label} fragment preserved in provider_metadata",
                message_id,
            )
        )
    return content, extras


def _timestamp(value: Any) -> datetime | None:
    if isinstance(value, int | float) and not isinstance(value, bool):
        return datetime.fromtimestamp(value, tz=UTC)
    return None


def _message(raw: dict[str, Any], findings: list[Finding]) -> Message:
    served_id = raw.get("message_id")
    message_id = (
        str(served_id)
        if isinstance(served_id, int | str) and not isinstance(served_id, bool)
        else None
    )
    content, extras = _fragments(raw.get("fragments"), findings, message_id)

    if not content:
        findings.append(
            finding("message_has_no_content", "no text fragment", message_id)
        )

    status = raw.get("status")
    if status != FINISHED:
        findings.append(
            finding("message_content_withheld", f"status {status!r}", message_id)
        )
    if raw.get("incomplete_message") is not None:
        findings.append(
            finding("message_content_withheld", "marked incomplete", message_id)
        )
    if raw.get("has_pending_fragment") is True:
        findings.append(
            finding(
                "message_content_withheld", "a fragment was still pending", message_id
            )
        )

    role_value = raw.get("role")
    role = ROLES.get(role_value) if isinstance(role_value, str) else None
    if role is None:
        findings.append(
            finding(
                "unrecognised_role", f"{role_value!r} preserved as unknown", message_id
            )
        )

    # The id and time change type on the way in, so the served values
    # are kept; role, status and fragments are held exactly.
    mapped = {"fragments"}
    if role is not None:
        mapped.add("role")
    if isinstance(status, str):
        mapped.add("status")
    metadata = {key: value for key, value in raw.items() if key not in mapped}
    if extras:
        metadata[FRAGMENTS_KEY] = extras

    return Message(
        id=message_id,
        role=role or MessageRole.UNKNOWN,
        timestamp=_timestamp(raw.get("inserted_at")),
        content=content,
        status=status if isinstance(status, str) else None,
        provider_metadata=metadata,
    )


def parse(source: RawSource) -> ParseResult:
    """Convert a DeepSeek share payload into a Conversation."""
    try:
        payload = json.loads(source.content)
    except json.JSONDecodeError as exc:
        raise ParseError(f"Share payload is not valid JSON: {exc}") from exc

    if not isinstance(payload, dict) or not isinstance(payload.get("data"), dict):
        raise ParseError("Share payload is not a DeepSeek share answer")

    if carries_nothing(payload):
        said = payload["data"].get("biz_msg")
        detail = f": {said}" if isinstance(said, str) and said else ""
        raise ParseError(
            "Share carried no conversation (deleted, never existed, or made private)"
            + detail
        )

    body = _body(payload)
    raw_messages = body.get("messages") if isinstance(body, dict) else None
    if not isinstance(body, dict) or not isinstance(raw_messages, list):
        raise ParseError("Share payload has no message list")

    findings: list[Finding] = []
    messages: list[Message] = []
    unreadable: list[Any] = []
    for raw in raw_messages:
        if isinstance(raw, dict):
            messages.append(_message(raw, findings))
        else:
            unreadable.append(raw)
            findings.append(
                finding(
                    "unmodelled_content_type",
                    f"{type(raw).__name__} message preserved in provider_metadata",
                )
            )

    title = body.get("title")
    metadata: dict[str, Any] = {
        key: value for key, value in body.items() if key not in ("messages", "title")
    }
    if not isinstance(title, str) and "title" in body:
        metadata["title"] = title
    metadata["envelope"] = {
        "outer": {key: value for key, value in payload.items() if key != "data"},
        "data": {
            key: value for key, value in payload["data"].items() if key != "biz_data"
        },
    }
    if unreadable:
        metadata["unreadable_messages"] = unreadable

    stamps = [
        message.timestamp for message in messages if message.timestamp is not None
    ]
    conversation = Conversation(
        id=None,
        provider=PROVIDER,
        source_url=source.url,
        title=title if isinstance(title, str) else None,
        created_at=min(stamps) if stamps else None,
        updated_at=max(stamps) if stamps else None,
        messages=messages,
        provider_metadata=metadata,
    )
    return ParseResult(conversation=conversation, findings=collapse(findings))
