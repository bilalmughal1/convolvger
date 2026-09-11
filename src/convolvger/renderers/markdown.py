"""Markdown rendering of a canonical conversation.

This renderer produces a reader-facing document, not a complete record.
Following the OAIS distinction between an archival package and a
dissemination package, it may omit content the provider itself withheld
(hidden messages) or deactivated (branched-away messages). Every
omission is reported in the provenance header, so the rendered file
stays a trustworthy representation of what the snapshot contained.

Nothing here is provider-specific.
"""

from datetime import datetime

from convolvger.core.models import (
    CodeBlock,
    ContentBlock,
    Conversation,
    Message,
    MessageRole,
    ReasoningBlock,
    TextBlock,
    UnknownBlock,
)

ROLE_HEADINGS = {
    MessageRole.USER: "User",
    MessageRole.ASSISTANT: "Assistant",
    MessageRole.SYSTEM: "System",
    MessageRole.TOOL: "Tool",
    MessageRole.UNKNOWN: "Unknown",
}


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
    if isinstance(block, UnknownBlock):
        header = f"**Unrendered content — `{block.type}`**"
        if block.text:
            return f"{header}\n{_quote(block.text)}"
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
    warnings: list[str] | None,
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
        lines.append(
            "- Omitted messages are preserved in full in the JSON export."
        )
    if warnings:
        lines.append(f"- Extraction warnings: {len(warnings)}")
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
    warnings: list[str] | None = None,
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
            warnings,
            fetched_at,
        )
    ]
    sections.extend(_render_message(message) for message in selected)
    return "\n\n".join(sections) + "\n"
