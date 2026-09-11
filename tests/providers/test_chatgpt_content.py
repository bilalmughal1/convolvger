from typing import Any

from convolvger.core.models import (
    CodeBlock,
    ReasoningBlock,
    TextBlock,
    UnknownBlock,
)
from convolvger.providers.chatgpt._content import to_blocks


def convert(content: dict[str, Any] | None) -> tuple[list[Any], list[str]]:
    warnings: list[str] = []
    return to_blocks(content, warnings), warnings


def test_text_becomes_a_text_block() -> None:
    blocks, warnings = convert({"content_type": "text", "parts": ["Hello"]})

    assert blocks == [TextBlock(text="Hello")]
    assert warnings == []


def test_multiple_parts_become_multiple_blocks() -> None:
    blocks, _ = convert({"content_type": "text", "parts": ["one", "two"]})

    assert [block.text for block in blocks] == ["one", "two"]


def test_empty_text_part_produces_no_block() -> None:
    blocks, warnings = convert({"content_type": "text", "parts": [""]})

    assert blocks == []
    assert warnings == []


def test_non_string_part_is_preserved_as_unknown() -> None:
    blocks, _ = convert(
        {"content_type": "text", "parts": [{"asset_pointer": "sediment://x"}]}
    )

    assert isinstance(blocks[0], UnknownBlock)
    assert blocks[0].raw == {"part": {"asset_pointer": "sediment://x"}}


def test_code_keeps_its_language() -> None:
    blocks, _ = convert(
        {"content_type": "code", "language": "python", "text": "print(1)"}
    )

    assert blocks == [CodeBlock(text="print(1)", language="python")]


def test_code_language_unknown_becomes_none() -> None:
    """ChatGPT writes the literal string 'unknown', which is not a language."""
    blocks, _ = convert(
        {"content_type": "code", "language": "unknown", "text": 'search("x")'}
    )

    assert blocks[0].language is None
    assert blocks[0].text == 'search("x")'


def test_thoughts_map_summary_to_label() -> None:
    blocks, _ = convert(
        {
            "content_type": "thoughts",
            "thoughts": [{"summary": "Considering options", "content": "Body text"}],
        }
    )

    assert blocks == [ReasoningBlock(text="Body text", label="Considering options")]


def test_thought_with_extra_fields_is_preserved_verbatim() -> None:
    thought = {"summary": "Searching", "content": "", "chunks": ["a"], "finished": True}
    blocks, _ = convert({"content_type": "thoughts", "thoughts": [thought]})

    assert isinstance(blocks[0], UnknownBlock)
    assert blocks[0].raw == thought


def test_empty_thought_produces_no_block() -> None:
    blocks, _ = convert(
        {
            "content_type": "thoughts",
            "thoughts": [{"summary": "", "content": "", "chunks": [], "finished": True}],
        }
    )

    assert blocks == []


def test_reasoning_recap_is_labelled() -> None:
    blocks, _ = convert(
        {"content_type": "reasoning_recap", "content": "Worked for a few seconds"}
    )

    assert blocks == [ReasoningBlock(text="Worked for a few seconds", label="recap")]


def test_unknown_type_with_payload_warns_and_preserves() -> None:
    blocks, warnings = convert(
        {"content_type": "multimodal_text", "parts": ["x"], "extra": 1}
    )

    assert isinstance(blocks[0], UnknownBlock)
    assert blocks[0].type == "multimodal_text"
    assert blocks[0].raw == {"parts": ["x"], "extra": 1}
    assert any("multimodal_text" in warning for warning in warnings)


def test_empty_unknown_type_produces_no_block_and_no_warning() -> None:
    """model_editable_context with an empty context carries nothing to keep."""
    blocks, warnings = convert(
        {"content_type": "model_editable_context", "model_set_context": ""}
    )

    assert blocks == []
    assert warnings == []


def test_missing_content_produces_no_blocks() -> None:
    assert convert(None) == ([], [])
