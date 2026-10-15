"""Mapping of a Kimi share payload onto a Conversation.

The payload is the JSON form of a protobuf message, measured as::

    {"share": {"id", "chat": {"id", "name", "createTime", "updateTime"},
               "messages": [{"id", "parentId", "role", "status",
                             "blocks": [...], ...}, ...],
               "creator": {"name", "avatarUrl"}, "createTime"}}

Being protobuf, it omits a field whose value is empty: the last message
of a conversation has no ``childrenMessageIds`` key at all. An absent
field therefore means empty, never damage, and is read that way here.
Enums arrive as their names, such as ``MESSAGE_STATUS_COMPLETED``.

A message is a list of blocks, each holding exactly one kind of content
beside its own ids and time. ``text`` is the prose a reader sees and
becomes a text block. ``multiStage`` and ``stage`` record the progress
of generation and describe the answer rather than adding to it. ``think``
holds the model's working notes as shown on the share page: its
``content``, and in one measured block a ``summary``. It becomes a
reasoning block, as ChatGPT's thoughts do, with the summary as its label
-- but only when it carries nothing else, so a shape not yet seen is
kept and flagged rather than half read. ``tool`` holds a search the
model ran with every result it got back; it is not modelled by this
version, so it is kept and flagged, as Grok's reasoning trace is. Every
block that is
not text, and everything a text block carries beside its text, is kept
in ``provider_metadata`` under its position, so nothing served is lost.

Citations are not marked inside the text. Each is a ``references`` entry
naming the span of the answer it supports and the search result behind
it. The results they name become the message's citations, numbered in
the order the references list them, so the document can say what the
answer drew on; the text is left as served, since a marker placed at a
quoted span would be text the provider never sent, and the span can
occur more than once. The entries themselves are kept in
``provider_metadata`` with the rest, and a reference naming no search
the message carries is reported.

``creator`` names the account that shared the conversation. It is kept
in ``provider_metadata`` for the reason Claude's is: the JSON export is
the archival record and omits nothing served, and no renderer reads it,
so the Markdown does not carry it.

Times carry nanoseconds, and the canonical fields hold microseconds, so
the served strings are kept beside them rather than rounded away.
"""

import json
from datetime import datetime
from typing import Any, TypeGuard

from convolvger.core import jsonload
from convolvger.core.citations import Sources
from convolvger.core.findings import Finding, collapse, finding
from convolvger.core.models import (
    ContentBlock,
    Conversation,
    Message,
    MessageRole,
    ReasoningBlock,
    TextBlock,
)
from convolvger.core.results import ParseError, ParseResult
from convolvger.core.source import RawSource

PROVIDER = "kimi"

ROLES = {"user": MessageRole.USER, "assistant": MessageRole.ASSISTANT}
"""The only two roles observed. Anything else is recorded, not guessed."""

COMPLETED = "MESSAGE_STATUS_COMPLETED"

BLOCK_ENVELOPE = frozenset({"id", "parentId", "messageId", "createTime"})
"""What every block carries beside its one kind of content."""

PROGRESS_KINDS = frozenset({"multiStage", "stage"})
UNMODELLED_KINDS = frozenset({"tool"})
THINK_KEYS = frozenset({"content", "summary"})

BLOCKS_KEY = "block_extras"
"""Where each block's unmodelled fields land, keyed by its position."""


def carries_nothing(payload: Any) -> bool:
    """True for a well-formed share that holds no messages.

    Protobuf omits an empty list, so a share with none has no
    ``messages`` key at all rather than an empty one.
    """
    if not isinstance(payload, dict):
        return False
    share = payload.get("share")
    return isinstance(share, dict) and not share.get("messages")


def _timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _kind(block: dict[str, Any]) -> str | None:
    kinds = [key for key in block if key not in BLOCK_ENVELOPE]
    return kinds[0] if len(kinds) == 1 else None


def _readable_thought(thought: Any) -> TypeGuard[dict[str, str]]:
    """True for a ``think`` body holding only text this version reads."""
    return (
        isinstance(thought, dict)
        and set(thought) <= THINK_KEYS
        and all(isinstance(value, str) for value in thought.values())
    )


def _reasoning(
    thought: dict[str, str],
) -> tuple[ReasoningBlock | None, dict[str, str]]:
    """Return the reasoning a ``think`` body holds, and what it does not.

    The text is the content, labelled with the summary. A thought with
    only a summary is shown as its text, as ChatGPT's are. A served value
    no block holds exactly -- an empty string -- is returned to be kept.
    """
    body = thought.get("content", "")
    summary = thought.get("summary", "")
    unheld: dict[str, str]
    if body:
        reasoning = ReasoningBlock(text=body, label=summary or None)
        unheld = {"summary": summary} if "summary" in thought and not summary else {}
    elif summary:
        reasoning = ReasoningBlock(text=summary)
        unheld = {"content": body} if "content" in thought else {}
    else:
        return None, dict(thought)
    return reasoning, unheld


def _search_results(raw: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """The search results a message's tool blocks carry, by their id."""
    results: dict[str, dict[str, Any]] = {}
    blocks = raw.get("blocks")
    for block in blocks if isinstance(blocks, list) else []:
        tool = block.get("tool") if isinstance(block, dict) else None
        contents = tool.get("contents") if isinstance(tool, dict) else None
        for item in contents if isinstance(contents, list) else []:
            found = item.get("searchResult") if isinstance(item, dict) else None
            ident = found.get("id") if isinstance(found, dict) else None
            base = found.get("base") if isinstance(found, dict) else None
            if isinstance(ident, str) and isinstance(base, dict):
                results.setdefault(ident, base)
    return results


def _cited(
    raw: dict[str, Any], findings: list[Finding], message_id: str | None
) -> Sources:
    """The search results a message's references name, in the order named."""
    results = _search_results(raw)

    def described(ref: str) -> tuple[str | None, str | None]:
        url, title = results[ref].get("url"), results[ref].get("title")
        return (
            url if isinstance(url, str) and url else None,
            title if isinstance(title, str) and title else None,
        )

    sources = Sources(described)
    references = raw.get("references")
    for reference in references if isinstance(references, list) else []:
        items = reference.get("items") if isinstance(reference, dict) else None
        for item in items if isinstance(items, list) else []:
            search = item.get("search") if isinstance(item, dict) else None
            ref = search.get("id") if isinstance(search, dict) else None
            if isinstance(ref, str) and ref in results:
                sources.number(ref)
            else:
                findings.append(
                    finding(
                        "unmodelled_content_type",
                        "reference names no search result, preserved in "
                        "provider_metadata",
                        message_id,
                    )
                )
    return sources


def _blocks(
    raw: Any, findings: list[Finding], message_id: str | None
) -> tuple[list[ContentBlock], dict[str, Any]]:
    """Return the text blocks of a message and everything else it carried."""
    content: list[ContentBlock] = []
    extras: dict[str, Any] = {}
    for index, block in enumerate(raw if isinstance(raw, list) else []):
        position = str(index)
        if not isinstance(block, dict):
            extras[position] = block
            findings.append(
                finding(
                    "unmodelled_content_type",
                    f"{type(block).__name__} block preserved in provider_metadata",
                    message_id,
                )
            )
            continue

        kind = _kind(block)
        body = block.get("text")
        if (
            kind == "text"
            and isinstance(body, dict)
            and isinstance(body.get("content"), str)
        ):
            rest = {key: value for key, value in block.items() if key != "text"}
            others = {key: value for key, value in body.items() if key != "content"}
            if body["content"]:
                content.append(TextBlock(text=body["content"]))
            else:
                # No text block holds an empty string, so it is kept here.
                others["content"] = body["content"]
            if others:
                rest["text"] = others
            if rest:
                extras[position] = rest
            continue

        thought = block.get("think")
        if kind == "think" and _readable_thought(thought):
            reasoning, unheld = _reasoning(thought)
            if reasoning is not None:
                content.append(reasoning)
            rest = {key: value for key, value in block.items() if key != "think"}
            if unheld:
                rest["think"] = unheld
            if rest:
                extras[position] = rest
            continue

        extras[position] = block
        if kind in PROGRESS_KINDS:
            continue
        label = kind if kind is not None else "unrecognised"
        findings.append(
            finding(
                "unmodelled_content_type",
                f"{label} block preserved in provider_metadata",
                message_id,
            )
        )
    return content, extras


def _message(raw: dict[str, Any], findings: list[Finding]) -> Message:
    identifier = raw.get("id")
    message_id = identifier if isinstance(identifier, str) and identifier else None
    content, extras = _blocks(raw.get("blocks"), findings, message_id)
    sources = _cited(raw, findings, message_id)

    if not content:
        findings.append(finding("message_has_no_content", "no text block", message_id))

    status = raw.get("status")
    if status != COMPLETED:
        findings.append(
            finding("message_content_withheld", f"status {status!r}", message_id)
        )

    role_value = raw.get("role")
    role = ROLES.get(role_value) if isinstance(role_value, str) else None
    if role is None:
        findings.append(
            finding(
                "unrecognised_role", f"{role_value!r} preserved as unknown", message_id
            )
        )

    mapped = {"blocks"}
    if message_id is not None:
        mapped.add("id")
    if role is not None:
        mapped.add("role")
    if isinstance(status, str):
        mapped.add("status")
    metadata = {key: value for key, value in raw.items() if key not in mapped}
    if extras:
        metadata[BLOCKS_KEY] = extras

    return Message(
        id=message_id,
        role=role or MessageRole.UNKNOWN,
        timestamp=_timestamp(raw.get("createTime")),
        content=content,
        status=status if isinstance(status, str) else None,
        citations=sources.citations,
        provider_metadata=metadata,
    )


def parse(source: RawSource) -> ParseResult:
    """Convert a Kimi share payload into a Conversation."""
    try:
        payload = jsonload.loads(source.content)
    except json.JSONDecodeError as exc:
        raise ParseError(f"Share payload is not valid JSON: {exc}") from exc
    except jsonload.JSONNestingError as exc:
        raise ParseError(f"Share payload is refused: {exc}") from exc

    if not isinstance(payload, dict):
        raise ParseError("Share payload is not a JSON object")

    share = payload.get("share")
    if not isinstance(share, dict):
        code = payload.get("code")
        said = f" (the provider answered {code!r})" if isinstance(code, str) else ""
        raise ParseError(f"Share payload has no share{said}")

    if carries_nothing(payload):
        raise ParseError(
            "Share carried no conversation (deleted, never existed, or made private)"
        )

    raw_messages = share.get("messages")
    if not isinstance(raw_messages, list):
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

    served_chat = share.get("chat")
    chat = served_chat if isinstance(served_chat, dict) else {}
    identifier = chat.get("id")
    title = chat.get("name")
    held = {key for key in ("id", "name") if isinstance(chat.get(key), str)}

    metadata: dict[str, Any] = {
        key: value for key, value in share.items() if key not in ("chat", "messages")
    }
    if isinstance(served_chat, dict):
        metadata["chat"] = {
            key: value for key, value in chat.items() if key not in held
        }
    elif "chat" in share:
        metadata["chat"] = served_chat
    envelope = {key: value for key, value in payload.items() if key != "share"}
    if envelope:
        metadata["envelope"] = envelope
    if unreadable:
        metadata["unreadable_messages"] = unreadable

    conversation = Conversation(
        id=identifier if isinstance(identifier, str) else None,
        provider=PROVIDER,
        source_url=source.url,
        title=title if isinstance(title, str) else None,
        created_at=_timestamp(chat.get("createTime")),
        updated_at=_timestamp(chat.get("updateTime")),
        messages=messages,
        provider_metadata=metadata,
    )
    return ParseResult(conversation=conversation, findings=collapse(findings))
