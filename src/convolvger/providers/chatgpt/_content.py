"""Mapping of ChatGPT content payloads onto canonical content blocks.

Each ``content_type`` carries its text under a different key, so the
mapping is explicit per type. Unrecognised types are preserved verbatim
as ``UnknownBlock`` rather than dropped.
"""

from typing import Any

from convolvger.core.models import (
    CodeBlock,
    ContentBlock,
    ReasoningBlock,
    TextBlock,
    UnknownBlock,
)


def _text_blocks(content: dict[str, Any]) -> list[ContentBlock]:
    blocks: list[ContentBlock] = []
    for part in content.get("parts") or []:
        if isinstance(part, str):
            if part:
                blocks.append(TextBlock(text=part))
        else:
            blocks.append(UnknownBlock(type="text_part", raw={"part": part}))
    return blocks


def _code_blocks(content: dict[str, Any]) -> list[ContentBlock]:
    text = content.get("text")
    if not isinstance(text, str) or not text:
        return []
    language = content.get("language")
    if language in (None, "", "unknown"):
        language = None
    return [CodeBlock(text=text, language=language)]


def _thought_blocks(content: dict[str, Any]) -> list[ContentBlock]:
    blocks: list[ContentBlock] = []
    for thought in content.get("thoughts") or []:
        if not isinstance(thought, dict):
            blocks.append(UnknownBlock(type="thoughts", raw={"thought": thought}))
            continue
        summary = thought.get("summary") or None
        body = thought.get("content") or ""
        extras = {
            key: value
            for key, value in thought.items()
            if key not in ("summary", "content") and value not in (None, [], {}, "")
        }
        if not body and not summary:
            continue
        if extras:
            blocks.append(
                UnknownBlock(type="thoughts", text=body or summary, raw=thought)
            )
        else:
            blocks.append(ReasoningBlock(text=body, label=summary))
    return blocks


def _recap_blocks(content: dict[str, Any]) -> list[ContentBlock]:
    text = content.get("content")
    if not isinstance(text, str) or not text:
        return []
    return [ReasoningBlock(text=text, label="recap")]


def to_blocks(
    content: dict[str, Any] | None,
    warnings: list[str],
) -> list[ContentBlock]:
    """Convert one ChatGPT content payload into canonical blocks."""
    if not content:
        return []

    content_type = content.get("content_type")
    if content_type == "text":
        return _text_blocks(content)
    if content_type == "code":
        return _code_blocks(content)
    if content_type == "thoughts":
        return _thought_blocks(content)
    if content_type == "reasoning_recap":
        return _recap_blocks(content)

    remainder = {
        key: value for key, value in content.items() if key != "content_type"
    }
    if not any(value not in (None, "", [], {}) for value in remainder.values()):
        return []

    warnings.append(f"unmodelled content_type preserved verbatim: {content_type}")
    return [UnknownBlock(type=str(content_type), raw=remainder)]
