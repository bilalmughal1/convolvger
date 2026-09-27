"""Mapping of a Qwen share payload onto a Conversation.

The payload is keyed JSON, measured as::

    {"success": true, "request_id",
     "data": {"id", "title", "user_id", "created_at", "updated_at",
              "currentId", "chat": {"history": {"messages": {<id>: node},
                                                "currentId"},
                                    "messages": [node, ...], "models"}}}

The conversation is a tree. ``history.messages`` maps each id to a node
with its ``parentId`` and ``childrenIds``, so a regenerated answer is a
second child rather than a replacement, and ``currentId`` names the last
message on the branch the sharer was looking at. The tree is walked from
its roots in the order the nodes list their children; a message off the
path to ``currentId`` is kept and marked inactive, as a deactivated
ChatGPT branch is. The one capture had no branches, so that handling has
been exercised only on synthetic payloads.

``chat.messages`` repeats the nodes on the current path as a flat list.
In the capture every node was identical to its copy in the tree, so the
list is passed over -- but only after checking that it still is; a flat
list that disagrees with the tree is kept and reported rather than
silently ignored.

An assistant node's ``content`` was measured empty: the answer is in its
``content_list``, a sequence of parts each with a ``phase``. The
``answer`` phase is the text a reader sees. ``web_search`` parts hold the
searches run and their results, kept in ``provider_metadata`` as other
providers' search results are. ``thinking_summary`` parts hold the
model's summarised reasoning, which this version does not model; they
are kept and flagged, as Grok's reasoning trace is.

An answer cites its results inline as ``[[N]]``. The results are
numbered from 1 straight across every search in the message: measured,
the first search's results carried the labels 1 to 17 and the second's
18 to 34 in the search's own observation text. A marker that resolves is
lifted out of the visible text and the part's served text kept verbatim
beside it; one that does not resolve is left and reported. A marker
inside code -- ``[[1]]`` is also a nested list in Python -- is content
and is never touched.

``user_id`` identifies the account that shared the conversation. It is
kept in ``provider_metadata``, as Claude's ``creator`` is, and no
renderer reads it.
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

PROVIDER = "qwen"

ROLES = {"user": MessageRole.USER, "assistant": MessageRole.ASSISTANT}
"""The only two roles observed. Anything else is recorded, not guessed."""

ANSWER = "answer"
SEARCH = "web_search"
CITATION = re.compile(r"\[\[(\d+)\]\]")

PARTS_KEY = "part_extras"
"""Where each ``content_list`` part's unmodelled fields land, by position."""

MAPPED_NODE_KEYS = frozenset({"id", "role", "content_list"})


def _tree(payload: Any) -> Any:
    data = payload.get("data") if isinstance(payload, dict) else None
    chat = data.get("chat") if isinstance(data, dict) else None
    history = chat.get("history") if isinstance(chat, dict) else None
    return history.get("messages") if isinstance(history, dict) else None


def carries_nothing(payload: Any) -> bool:
    """True for a well-formed answer that holds no conversation.

    Measured: an unknown or malformed id answers 200 with ``success``
    false and a ``Not_Found`` code, so the status alone cannot tell a
    missing share from a present one.
    """
    if not isinstance(payload, dict) or "success" not in payload:
        return False
    return payload.get("success") is False or not _tree(payload)


def _timestamp(value: Any) -> datetime | None:
    if isinstance(value, int | float) and not isinstance(value, bool):
        return datetime.fromtimestamp(value, tz=UTC)
    return None


def _resolvable(parts: list[Any]) -> set[str]:
    """Return every citation number a message's searches answer to."""
    total = 0
    for part in parts:
        if isinstance(part, dict) and part.get("phase") == SEARCH:
            extra = part.get("extra")
            results = extra.get("web_search_info") if isinstance(extra, dict) else None
            if isinstance(results, list):
                total += len(results)
    return {str(number) for number in range(1, total + 1)}


def _parts(
    raw: Any, findings: list[Finding], message_id: str | None
) -> tuple[list[ContentBlock], dict[str, Any]]:
    parts = raw if isinstance(raw, list) else []
    numbers = _resolvable(parts)
    content: list[ContentBlock] = []
    extras: dict[str, Any] = {}

    for index, part in enumerate(parts):
        position = str(index)
        phase = part.get("phase") if isinstance(part, dict) else None
        text = part.get("content") if isinstance(part, dict) else None

        if isinstance(part, dict) and phase == ANSWER and isinstance(text, str):
            outcome = lift(text, CITATION, numbers.__contains__)
            for marker in outcome.unresolved:
                findings.append(
                    finding(
                        "unmodelled_content_type",
                        f"{marker} names no search result, preserved in text",
                        message_id,
                    )
                )
            if outcome.text:
                content.append(TextBlock(text=outcome.text))
            rest = {key: value for key, value in part.items() if key != "content"}
            if outcome.text != text or not outcome.text:
                # Kept whenever no text block holds the served string exactly.
                rest["content"] = text
            extras[position] = rest
            continue

        extras[position] = part
        if phase == SEARCH:
            continue
        label = phase if isinstance(phase, str) else type(part).__name__
        findings.append(
            finding(
                "unmodelled_content_type",
                f"{label} part preserved in provider_metadata",
                message_id,
            )
        )
    return content, extras


def _message(node: dict[str, Any], active: bool, findings: list[Finding]) -> Message:
    identifier = node.get("id")
    message_id = identifier if isinstance(identifier, str) else None
    mapped = set(MAPPED_NODE_KEYS)
    if message_id is None:
        mapped.discard("id")

    content, extras = _parts(node.get("content_list"), findings, message_id)
    served = node.get("content")
    if not content and isinstance(served, str) and served:
        content.append(TextBlock(text=served))
        mapped.add("content")

    if not content:
        findings.append(finding("message_has_no_content", "no answer text", message_id))

    reasoning = node.get("reasoning_content")
    if reasoning:
        findings.append(
            finding(
                "unmodelled_content_type",
                "reasoning_content preserved in provider_metadata",
                message_id,
            )
        )

    files = node.get("files")
    if isinstance(files, list) and files:
        findings.append(
            finding(
                "attachment_withheld",
                f"{len(files)} files declared, none carried",
                message_id,
            )
        )

    if node.get("error"):
        findings.append(
            finding(
                "message_content_withheld", "the provider recorded an error", message_id
            )
        )
    if node.get("role") == "assistant" and node.get("done") is False:
        findings.append(
            finding("message_content_withheld", "marked not done", message_id)
        )
    if node.get("is_stop") is True:
        findings.append(
            finding("message_content_withheld", "stopped before finishing", message_id)
        )

    role_value = node.get("role")
    role = ROLES.get(role_value) if isinstance(role_value, str) else None
    if role is None:
        mapped.discard("role")
        findings.append(
            finding(
                "unrecognised_role", f"{role_value!r} preserved as unknown", message_id
            )
        )

    metadata = {key: value for key, value in node.items() if key not in mapped}
    if extras:
        metadata[PARTS_KEY] = extras

    return Message(
        id=message_id,
        role=role or MessageRole.UNKNOWN,
        timestamp=_timestamp(node.get("timestamp")),
        content=content,
        active=active,
        provider_metadata=metadata,
    )


def _order(tree: dict[str, Any]) -> list[str]:
    """Return every node id, roots first, each followed by its children."""
    ordered: list[str] = []
    seen: set[str] = set()

    def visit(node_id: str) -> None:
        stack = [node_id]
        while stack:
            current = stack.pop()
            if current in seen or current not in tree:
                continue
            seen.add(current)
            ordered.append(current)
            node = tree[current]
            children = node.get("childrenIds") if isinstance(node, dict) else None
            if isinstance(children, list):
                stack.extend(
                    child for child in reversed(children) if isinstance(child, str)
                )

    for node_id, node in tree.items():
        parent = node.get("parentId") if isinstance(node, dict) else None
        if parent is None or parent not in tree:
            visit(node_id)
    for node_id in tree:
        visit(node_id)
    return ordered


def _current_path(tree: dict[str, Any], current: Any) -> set[str]:
    path: set[str] = set()
    while isinstance(current, str) and current in tree and current not in path:
        path.add(current)
        node = tree[current]
        current = node.get("parentId") if isinstance(node, dict) else None
    return path


def parse(source: RawSource) -> ParseResult:
    """Convert a Qwen share payload into a Conversation."""
    try:
        payload = json.loads(source.content)
    except json.JSONDecodeError as exc:
        raise ParseError(f"Share payload is not valid JSON: {exc}") from exc

    if not isinstance(payload, dict) or not isinstance(payload.get("data"), dict):
        raise ParseError("Share payload is not a Qwen share answer")

    if carries_nothing(payload):
        said = payload["data"].get("details") or payload["data"].get("code")
        detail = f": {said}" if isinstance(said, str) and said else ""
        raise ParseError(
            "Share carried no conversation (deleted, never existed, or made private)"
            + detail
        )

    data = payload["data"]
    chat = data["chat"]
    history = chat["history"]
    tree = history["messages"]
    if not isinstance(tree, dict):
        raise ParseError("Share payload's message tree is not an object")

    findings: list[Finding] = []
    path = _current_path(tree, history.get("currentId") or data.get("currentId"))
    messages: list[Message] = []
    for node_id in _order(tree):
        node = tree[node_id]
        if isinstance(node, dict):
            messages.append(_message(node, not path or node_id in path, findings))
        else:
            findings.append(
                finding(
                    "unmodelled_content_type",
                    f"{type(node).__name__} message preserved in provider_metadata",
                )
            )

    chat_extras: dict[str, Any] = {
        key: value for key, value in chat.items() if key not in ("history", "messages")
    }
    chat_extras["history"] = {
        key: value for key, value in history.items() if key != "messages"
    }
    unreadable = {key: node for key, node in tree.items() if not isinstance(node, dict)}
    if unreadable:
        chat_extras["history"]["unreadable_messages"] = unreadable
    flat = chat.get("messages")
    in_step = isinstance(flat, list) and all(
        isinstance(item, dict) and tree.get(item.get("id")) == item for item in flat
    )
    if not in_step:
        chat_extras["messages"] = flat
        findings.append(
            finding(
                "unmodelled_content_type",
                "flat message list disagrees with the tree, preserved in provider_metadata",
            )
        )

    title = data.get("title")
    identifier = data.get("id")
    held = {"chat"}
    if isinstance(title, str):
        held.add("title")
    if isinstance(identifier, str):
        held.add("id")
    metadata: dict[str, Any] = {
        key: value for key, value in data.items() if key not in held
    }
    metadata["chat"] = chat_extras
    metadata["envelope"] = {
        key: value for key, value in payload.items() if key != "data"
    }

    conversation = Conversation(
        id=identifier if isinstance(identifier, str) else None,
        provider=PROVIDER,
        source_url=source.url,
        title=title if isinstance(title, str) else None,
        created_at=_timestamp(data.get("created_at")),
        updated_at=_timestamp(data.get("updated_at")),
        messages=messages,
        provider_metadata=metadata,
    )
    return ParseResult(conversation=conversation, findings=collapse(findings))
