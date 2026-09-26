"""Markdown rendering of a canonical conversation.

This renderer produces a reader-facing document, not a complete record.
Following the OAIS distinction between an archival package and a
dissemination package, it may omit content the provider itself withheld
(hidden messages) or deactivated (branched-away messages). Every
omission is reported in the provenance header, so the rendered file
stays a trustworthy representation of what the snapshot contained.

The header also names what the provider itself did not serve. Those
are the findings bearing on completeness, and they answer the question
a reader of this file actually has. Findings bearing on fidelity are
counted rather than named: they record what this tool could not model,
which is a fact about the extraction and belongs to the JSON archive.
Observations are merged across messages for display, because the
message id that keeps them apart in the record is not shown here and
cannot be: this file has no anchor a reader could follow. The counts
are summed, so nothing is lost -- only the attribution, which the JSON
still carries.
No verdict is rendered here -- ``convolvger verify`` recomputes one
from the archive on demand, and a verdict written into a file would
outlive the reasoning behind it.

Nothing here is provider-specific.
"""

import json
from datetime import datetime
from typing import Any

from convolvger.core.findings import Finding, Level, collapse
from convolvger.core.models import (
    CodeBlock,
    ContentBlock,
    Conversation,
    Message,
    MessageRole,
    ReasoningBlock,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UnknownBlock,
)
from convolvger.validation.aspects import ASPECTS, Aspect

ROLE_HEADINGS = {
    MessageRole.USER: "User",
    MessageRole.ASSISTANT: "Assistant",
    MessageRole.SYSTEM: "System",
    MessageRole.TOOL: "Tool",
    MessageRole.UNKNOWN: "Unknown",
}


def _reference(raw: dict[str, Any]) -> str | None:
    """A readable label for an unmodelled block, from what it carries.

    A block this version does not model may still hold a title and a
    link the provider served, and dropping them leaves the reader a
    placeholder where a source was. The keys are read generically
    rather than per provider: nothing here knows what a ``knowledge``
    block is, only that a string ``title`` or ``url`` is worth showing.
    Neither present means there is nothing to say, and the block keeps
    its placeholder rather than inventing one.
    """
    title = raw.get("title")
    url = raw.get("url")
    if isinstance(title, str) and title.strip():
        title = " ".join(title.split())
    else:
        title = None
    url = url.strip() if isinstance(url, str) and url.strip() else None
    if title and url:
        safe = title.replace("[", "\\[").replace("]", "\\]")
        return f"[{safe}](<{url}>)"
    return title or url


def _quote(text: str) -> str:
    return "\n".join(f"> {line}" if line else ">" for line in text.splitlines())


def _render_block(block: ContentBlock) -> str:
    if isinstance(block, TextBlock):
        return block.text
    if isinstance(block, CodeBlock):
        fence = f"```{block.language}" if block.language else "```"
        return f"{fence}\n{block.text}\n```"
    if isinstance(block, ReasoningBlock):
        label = f"**Reasoning — {block.label}**" if block.label else "**Reasoning**"
        return f"{label}\n{_quote(block.text)}"
    if isinstance(block, ToolUseBlock):
        header = f"**Tool call — `{block.name}`**"
        if not block.input:
            return f"{header}\n> (no arguments recorded)"
        arguments = json.dumps(block.input, indent=2, ensure_ascii=False)
        return f"{header}\n```json\n{arguments}\n```"
    if isinstance(block, ToolResultBlock):
        named = f" — `{block.name}`" if block.name else ""
        header = f"**Tool result{named}**"
        if block.is_error:
            header = f"{header} (the provider reported an error)"
        if not block.content:
            return f"{header}\n> (the shared snapshot carried no result)"
        body = "\n\n".join(_render_block(item) for item in block.content)
        return f"{header}\n{body}"
    if isinstance(block, UnknownBlock):
        header = f"**Unrendered content — `{block.type}`**"
        if block.text:
            return f"{header}\n{_quote(block.text)}"
        reference = _reference(block.raw)
        if reference:
            return (
                f"{header}\n> {reference}\n"
                "> (the full block is preserved in the JSON export)"
            )
        return f"{header}\n> (preserved in the JSON export)"
    raise TypeError(f"Unsupported content block: {type(block).__name__}")


def _heading(message: Message) -> str:
    heading = ROLE_HEADINGS.get(message.role, "Unknown")
    if message.author:
        heading = f"{heading} ({message.author})"
    notes = []
    if not message.visible:
        notes.append("hidden")
    if not message.active:
        notes.append("deactivated")
    if message.recipient and message.recipient != "all":
        notes.append(f"to {message.recipient}")
    suffix = f" — {', '.join(notes)}" if notes else ""
    return f"## {heading}{suffix}"


def _render_message(message: Message) -> str:
    parts = [_heading(message)]
    if message.timestamp:
        parts.append(f"*{message.timestamp.isoformat()}*")
    parts.extend(_render_block(block) for block in message.content)
    return "\n\n".join(parts)


def _provenance(
    conversation: Conversation,
    rendered: int,
    omitted_hidden: int,
    omitted_inactive: int,
    omitted_empty: int,
    findings: list[Finding] | None,
    fetched_at: datetime | None,
) -> str:
    lines = [
        f"# {conversation.title or 'Untitled conversation'}",
        "",
        f"- Source: {conversation.source_url}",
        f"- Provider: {conversation.provider}",
    ]
    if conversation.id:
        lines.append(f"- Conversation id: {conversation.id}")
    if conversation.created_at:
        lines.append(f"- Snapshot created: {conversation.created_at.isoformat()}")
    if fetched_at:
        lines.append(f"- Retrieved: {fetched_at.isoformat()}")
    lines.append(
        f"- Messages: {len(conversation.messages)} in snapshot, {rendered} rendered"
    )
    if omitted_hidden:
        lines.append(f"- Omitted as hidden by the provider: {omitted_hidden}")
    if omitted_inactive:
        lines.append(f"- Omitted as deactivated branches: {omitted_inactive}")
    if omitted_empty:
        lines.append(f"- Omitted as carrying no renderable content: {omitted_empty}")
    if omitted_hidden or omitted_inactive or omitted_empty:
        lines.append("- Omitted messages are preserved in full in the JSON export.")
    withheld = collapse(
        item.model_copy(update={"message_id": None})
        for item in findings or []
        if ASPECTS.get(item.code) is Aspect.COMPLETENESS
    )
    if withheld:
        lines.append("- Referenced by the snapshot but not served:")
        for item in withheld:
            seen = f" (x{item.occurrences})" if item.occurrences > 1 else ""
            lines.append(f"  - {item.code}: {item.message}{seen}")
    for level in (Level.WARNING, Level.NOTE):
        count = sum(1 for item in findings or [] if item.level is level)
        if count:
            lines.append(f"- Extraction {level.value}s: {count}")
    if findings:
        lines.append("- Every finding is recorded in full in the JSON export.")
    lines.extend(
        [
            "",
            (
                "> **Note on snapshots.** A provider's public share page can "
                "change after it is published: content present when a "
                "conversation was shared may be withheld or altered later. "
                "This archive records what the snapshot contained when it "
                "was retrieved, and nothing more."
            ),
        ]
    )
    return "\n".join(lines)


def render_markdown(
    conversation: Conversation,
    *,
    include_hidden: bool = False,
    include_inactive: bool = False,
    findings: list[Finding] | None = None,
    fetched_at: datetime | None = None,
) -> str:
    """Render a conversation as Markdown.

    Hidden and deactivated messages are omitted by default and the
    omission is recorded in the header. Pass the flags to include them.
    """
    selected: list[Message] = []
    omitted_hidden = 0
    omitted_inactive = 0
    omitted_empty = 0

    for message in conversation.messages:
        if not message.visible and not include_hidden:
            omitted_hidden += 1
            continue
        if not message.active and not include_inactive:
            omitted_inactive += 1
            continue
        if not message.content:
            omitted_empty += 1
            continue
        selected.append(message)

    sections = [
        _provenance(
            conversation,
            len(selected),
            omitted_hidden,
            omitted_inactive,
            omitted_empty,
            findings,
            fetched_at,
        )
    ]
    sections.extend(_render_message(message) for message in selected)
    return "\n\n".join(sections) + "\n"
