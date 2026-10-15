"""Mapping of a Perplexity thread payload onto a Conversation.

The payload is what the share page reads from ``/rest/thread/<id>``,
measured as::

    {"status", "entries": [...], "first_entry", "latest_entry",
     "has_next_page", "next_cursor", "background_entries",
     "thread_metadata": {"title", "created_at", "author_name", ...}}

Each entry is one turn: the question in ``query_str`` and the answer in
``blocks``. The answer is not one string. ``structured_answer_block_usages``
named the ``workflow_root`` block, whose steps are a search -- the
queries run and the sources found -- followed by text items, each a
piece of the answer, in order. Those items become the answer's text
blocks. Their ``chunks`` were measured joining to their ``text`` exactly.

The other blocks restate what the workflow holds or describe the page:
``plan`` lists goals that were each measured equal to a step's title or
to the answer's text, ``web_results`` and ``sources_answer_mode`` list
the results found, ``answer_tabs`` and ``pending_followups`` the page's
controls. None adds content, so none is flagged. A block of any other
kind, a text item of any other variant, and an image inside the answer
are kept and flagged: content this version does not model.

The answer cites results as ``[n]``. The ``sources_answer_mode`` block
lists the results again, and on each one the answer cites it carries
``citation: n`` -- measured, exactly the numbers the text used. Those
become the message's citations, renumbered by first citation as every
provider's are; one that names no such result is left and reported.

The entry is kept whole in ``provider_metadata`` of the answer, blocks
and all, apart from the question, which the question's text block holds
exactly. That includes ``author_name``, ``author_username``,
``author_id`` and ``author_image`` -- the account that shared the
thread, on the thread and on every entry -- kept as Claude's ``creator``
is, and read by no renderer.

``first_entry`` was measured equal to the first of ``entries``, and is
passed over only after checking it still is. A thread longer than one
page (``has_next_page``) arrives without its later entries; that is
reported, not hidden.

Times on an entry carry an offset. The thread's do not, and were
measured within a tenth of a second of its first entry's time in UTC,
so they are read as UTC; the served strings are kept either way.
"""

import json
import re
from datetime import UTC, datetime
from typing import Any

from convolvger.core import jsonload
from convolvger.core.citations import Sources, lift
from convolvger.core.findings import Finding, collapse, finding
from convolvger.core.models import (
    Citation,
    ContentBlock,
    Conversation,
    Message,
    MessageRole,
    TextBlock,
)
from convolvger.core.results import ParseError, ParseResult
from convolvger.core.source import RawSource

PROVIDER = "perplexity"

COMPLETED = "COMPLETED"
CITATION = re.compile(r"\[(\d+)\]")

WORKFLOW = "workflow_block"
SOURCES_BLOCK = "sources_mode_block"
KNOWN_BLOCKS = frozenset(
    {
        "plan_block",
        WORKFLOW,
        "web_result_block",
        "answer_tabs_block",
        SOURCES_BLOCK,
        "pending_followups_block",
    }
)

TEXT_ITEM = "WORKFLOW_ITEM_TEXT"
SEARCH_ITEMS = frozenset({"WORKFLOW_ITEM_QUERIES", "WORKFLOW_ITEM_SOURCES"})
ANSWER = "answer"
TEXT_KEYS = frozenset({"chunks", "is_streaming", "text", "variant"})

PAGE_KEYS = frozenset({"entries", "first_entry", "thread_metadata"})


def _time(value: Any, *, naive_is_utc: bool = False) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC) if naive_is_utc else None
    return parsed


def _blocks(entry: dict[str, Any]) -> list[dict[str, Any]]:
    blocks = entry.get("blocks")
    return (
        [block for block in blocks if isinstance(block, dict)]
        if isinstance(blocks, list)
        else []
    )


def _cited(entry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """The results the answer cites, by the number it cites them with."""
    cited: dict[str, dict[str, Any]] = {}
    for block in _blocks(entry):
        rows = (
            block.get(SOURCES_BLOCK, {}).get("rows")
            if isinstance(block.get(SOURCES_BLOCK), dict)
            else None
        )
        for row in rows if isinstance(rows, list) else []:
            number = row.get("citation") if isinstance(row, dict) else None
            result = row.get("web_result") if isinstance(row, dict) else None
            if (
                isinstance(number, int)
                and not isinstance(number, bool)
                and isinstance(result, dict)
            ):
                cited.setdefault(str(number), result)
    return cited


def _described(result: dict[str, Any]) -> tuple[str | None, str | None]:
    url, name = result.get("url"), result.get("name")
    return (
        url if isinstance(url, str) and url else None,
        name if isinstance(name, str) and name else None,
    )


def _answer(
    entry: dict[str, Any], findings: list[Finding], message_id: str | None
) -> tuple[list[ContentBlock], list[Citation]]:
    cited = _cited(entry)
    sources = Sources(lambda ref: _described(cited[ref]))
    content: list[ContentBlock] = []

    for block in _blocks(entry):
        kinds = [key for key in block if key != "intended_usage"]
        kind = kinds[0] if len(kinds) == 1 else None
        if kind not in KNOWN_BLOCKS:
            label = block.get("intended_usage") or kind or "unrecognised"
            findings.append(
                finding(
                    "unmodelled_content_type",
                    f"{label} block preserved in provider_metadata",
                    message_id,
                )
            )
            continue
        if kind != WORKFLOW:
            continue

        steps = (
            block[WORKFLOW].get("steps") if isinstance(block[WORKFLOW], dict) else None
        )
        for step in steps if isinstance(steps, list) else []:
            items = step.get("items") if isinstance(step, dict) else None
            for item in items if isinstance(items, list) else []:
                item_type = item.get("type") if isinstance(item, dict) else None
                if item_type in SEARCH_ITEMS:
                    continue
                payload = item.get("payload") if isinstance(item, dict) else None
                text = (
                    payload.get("text_payload") if isinstance(payload, dict) else None
                )
                if item_type == TEXT_ITEM and isinstance(text, dict):
                    if text.get("images"):
                        findings.append(
                            finding(
                                "unmodelled_content_type",
                                "image in the answer preserved in provider_metadata",
                                message_id,
                            )
                        )
                    readable = (
                        set(text) - {"images"} <= TEXT_KEYS
                        and text.get("variant") == ANSWER
                        and isinstance(text.get("text"), str)
                    )
                    if readable:
                        outcome = lift(
                            text["text"], CITATION, cited.__contains__, sources.marker
                        )
                        for marker in outcome.unresolved:
                            findings.append(
                                finding(
                                    "unmodelled_content_type",
                                    f"{marker} names no cited result, preserved in text",
                                    message_id,
                                )
                            )
                        if outcome.text:
                            content.append(TextBlock(text=outcome.text))
                        continue
                    label = f"{text.get('variant')!r} text item"
                else:
                    label = (
                        f"{item_type!r} item"
                        if isinstance(item_type, str)
                        else "workflow item"
                    )
                findings.append(
                    finding(
                        "unmodelled_content_type",
                        f"{label} preserved in provider_metadata",
                        message_id,
                    )
                )
    return content, sources.citations


def _messages(entry: dict[str, Any], findings: list[Finding]) -> list[Message]:
    query_id = entry.get("uuid") if isinstance(entry.get("uuid"), str) else None
    answer_id = (
        entry.get("backend_uuid")
        if isinstance(entry.get("backend_uuid"), str)
        else None
    )

    query = entry.get("query_str")
    question: list[ContentBlock] = []
    if isinstance(query, str) and query:
        question.append(TextBlock(text=query))
    else:
        findings.append(finding("message_has_no_content", "no question text", query_id))

    content, citations = _answer(entry, findings, answer_id)
    if not content:
        findings.append(finding("message_has_no_content", "no answer text", answer_id))

    status = entry.get("status")
    if status != COMPLETED:
        findings.append(
            finding("message_content_withheld", f"status {status!r}", answer_id)
        )

    # The question's text block holds query_str exactly; everything else
    # the entry served, the answer's blocks included, is kept here whole.
    kept = {
        key: value
        for key, value in entry.items()
        if not (key == "query_str" and question)
    }
    return [
        Message(
            id=query_id,
            role=MessageRole.USER,
            timestamp=_time(entry.get("entry_created_datetime")),
            content=question,
        ),
        Message(
            id=answer_id,
            role=MessageRole.ASSISTANT,
            timestamp=_time(entry.get("entry_updated_datetime")),
            content=content,
            status=status if isinstance(status, str) else None,
            citations=citations,
            provider_metadata=kept,
        ),
    ]


def parse(source: RawSource) -> ParseResult:
    """Convert a Perplexity thread payload into a Conversation."""
    try:
        payload = jsonload.loads(source.content)
    except json.JSONDecodeError as exc:
        raise ParseError(f"Thread payload is not valid JSON: {exc}") from exc
    except jsonload.JSONNestingError as exc:
        raise ParseError(f"Thread payload is refused: {exc}") from exc

    if not isinstance(payload, dict):
        raise ParseError("Thread payload is not a JSON object")
    entries = payload.get("entries")
    metadata = payload.get("thread_metadata")
    if not isinstance(entries, list) or not isinstance(metadata, dict):
        raise ParseError("Thread payload is not a Perplexity thread")
    entries = [entry for entry in entries if isinstance(entry, dict)]
    if not entries:
        raise ParseError("Thread carries no entries")

    findings: list[Finding] = []
    messages = [message for entry in entries for message in _messages(entry, findings)]

    envelope: dict[str, Any] = {
        key: value for key, value in payload.items() if key not in PAGE_KEYS
    }
    if payload.get("first_entry") != entries[0]:
        envelope["first_entry"] = payload.get("first_entry")
        findings.append(
            finding(
                "unmodelled_content_type",
                "first_entry differs from the first of entries, preserved in "
                "provider_metadata",
            )
        )
    if payload.get("has_next_page") is True:
        findings.append(
            finding(
                "message_content_withheld",
                f"the thread continues past its first page of {len(entries)} "
                "entries, which were all that was read",
            )
        )

    title = metadata.get("title")
    thread = {
        key: value
        for key, value in metadata.items()
        if not (key == "title" and isinstance(title, str))
    }
    slug = entries[0].get("thread_url_slug")

    conversation = Conversation(
        id=slug if isinstance(slug, str) and slug else None,
        provider=PROVIDER,
        source_url=source.url,
        title=title if isinstance(title, str) else None,
        created_at=_time(metadata.get("created_at"), naive_is_utc=True),
        updated_at=_time(metadata.get("updated_at"), naive_is_utc=True),
        messages=messages,
        provider_metadata={"thread_metadata": thread, **envelope},
    )
    return ParseResult(conversation=conversation, findings=collapse(findings))
