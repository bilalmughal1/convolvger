"""Mapping of Claude snapshot content blocks onto canonical blocks.

A Claude ``content`` entry carries more than this model names. Every
text block arrives with citations and streaming timestamps, and a tool
block with a dozen presentation fields. None of it is dropped: tool
blocks keep their extras in ``raw``, and a text block has no ``raw``,
so its extras are handed back to the caller for
``Message.provider_metadata``.

Absent and null stay distinct. A key the snapshot omitted is simply
missing from the extras; a key it sent as null is preserved as null.
Folding the two together would make an omitted ``tool_origin`` look
like one the provider sent empty, and which of those happened is
evidence about the provider.
"""

from typing import Any

from convolvger.core.findings import Finding, finding
from convolvger.core.models import (
    ContentBlock,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UnknownBlock,
)

TEXT_KEYS = frozenset({"type", "text"})
TOOL_USE_KEYS = frozenset({"type", "name", "id", "input"})
TOOL_RESULT_KEYS = frozenset({"type", "tool_use_id", "name", "is_error", "content"})

TEXT_EXTRAS_KEY = "text_block_extras"
"""Where a text block's unmodelled fields land in ``provider_metadata``.

Keyed by the block's position within the message, so two text blocks
cannot overwrite each other and one nested inside a tool result keeps a
path recording where it was found.
"""


def _extras(block: dict[str, Any], consumed: frozenset[str]) -> dict[str, Any]:
    return {key: value for key, value in block.items() if key not in consumed}


def _unknown(block: dict[str, Any], findings: list[Finding]) -> ContentBlock:
    kind = block.get("type")
    text = block.get("text")
    findings.append(finding("unmodelled_content_type", f"{kind} preserved verbatim"))
    return UnknownBlock(
        type=kind if isinstance(kind, str) else "content_block",
        text=text if isinstance(text, str) else None,
        raw=_extras(block, frozenset({"type"})),
    )


def _text(
    block: dict[str, Any],
    findings: list[Finding],
    metadata: dict[str, Any],
    path: str,
) -> ContentBlock:
    text = block.get("text")
    if not isinstance(text, str):
        return _unknown(block, findings)
    extras = _extras(block, TEXT_KEYS)
    if extras:
        held = metadata.setdefault(TEXT_EXTRAS_KEY, {})
        held[path] = extras
    return TextBlock(text=text)


def _tool_use(block: dict[str, Any]) -> ContentBlock:
    consumed = set(TOOL_USE_KEYS)

    name = block.get("name")
    if not isinstance(name, str):
        consumed.discard("name")
        name = ""

    identifier = block.get("id")
    if not isinstance(identifier, str):
        consumed.discard("id")
        identifier = None

    arguments = block.get("input")
    if not isinstance(arguments, dict):
        consumed.discard("input")
        arguments = {}

    return ToolUseBlock(
        name=name,
        id=identifier,
        input=arguments,
        raw=_extras(block, frozenset(consumed)),
    )


def _tool_result(
    block: dict[str, Any],
    findings: list[Finding],
    metadata: dict[str, Any],
    message_id: str | None,
    path: str,
) -> ContentBlock:
    consumed = set(TOOL_RESULT_KEYS)

    tool_use_id = block.get("tool_use_id")
    if not isinstance(tool_use_id, str):
        consumed.discard("tool_use_id")
        tool_use_id = None

    name = block.get("name")
    if not isinstance(name, str):
        consumed.discard("name")
        name = None

    is_error = block.get("is_error")
    if not isinstance(is_error, bool):
        consumed.discard("is_error")
        is_error = False

    carried = block.get("content")
    if isinstance(carried, list):
        inner = to_blocks(carried, findings, metadata, message_id, path)
    else:
        if carried is not None:
            consumed.discard("content")
        inner = []

    if not inner and block.get("structured_content") is None:
        findings.append(
            finding(
                "tool_result_has_no_content",
                f"{name or 'tool'} result carried no payload",
                message_id,
            )
        )

    return ToolResultBlock(
        tool_use_id=tool_use_id,
        name=name,
        is_error=is_error,
        content=inner,
        raw=_extras(block, frozenset(consumed)),
    )


def to_blocks(
    blocks: Any,
    findings: list[Finding],
    metadata: dict[str, Any],
    message_id: str | None = None,
    prefix: str = "",
) -> list[ContentBlock]:
    """Convert one Claude ``content`` list into canonical blocks.

    ``findings`` and ``metadata`` are filled in place. Findings are not
    collapsed here: a repeated observation can span messages, so
    counting them is the whole parse's job, not one message's.
    """
    if not isinstance(blocks, list):
        return []

    mapped: list[ContentBlock] = []
    for index, block in enumerate(blocks):
        path = f"{prefix}.{index}" if prefix else str(index)
        if not isinstance(block, dict):
            findings.append(
                finding(
                    "unmodelled_content_type",
                    f"{type(block).__name__} preserved verbatim",
                )
            )
            mapped.append(UnknownBlock(type="content_block", raw={"block": block}))
            continue

        kind = block.get("type")
        if kind == "text":
            mapped.append(_text(block, findings, metadata, path))
        elif kind == "tool_use":
            mapped.append(_tool_use(block))
        elif kind == "tool_result":
            mapped.append(_tool_result(block, findings, metadata, message_id, path))
        else:
            mapped.append(_unknown(block, findings))
    return mapped
