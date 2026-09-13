from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from convolvger.core.models import (
    CodeBlock,
    ContentBlock,
    Message,
    MessageRole,
    ReasoningBlock,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UnknownBlock,
)

adapter: TypeAdapter[Any] = TypeAdapter(ContentBlock)


def test_code_block_preserves_language() -> None:
    block = CodeBlock(text="print(1)", language="python")

    assert block.language == "python"


def test_reasoning_block_is_distinct_from_text() -> None:
    reasoning = ReasoningBlock(text="Worked for a couple of seconds")

    assert reasoning.type == "reasoning"
    assert TextBlock(text="same words").type == "text"


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"type": "text", "text": "hi"}, TextBlock),
        ({"type": "code", "text": "ls", "language": "bash"}, CodeBlock),
        ({"type": "reasoning", "text": "thinking"}, ReasoningBlock),
    ],
)
def test_known_types_round_trip(payload: dict[str, Any], expected: type) -> None:
    assert isinstance(adapter.validate_python(payload), expected)


def test_unknown_type_falls_back_instead_of_raising() -> None:
    block = adapter.validate_python(
        {
            "type": "model_editable_context",
            "raw": {"model_set_context": ""},
        }
    )

    assert isinstance(block, UnknownBlock)
    assert block.type == "model_editable_context"
    assert block.raw == {"model_set_context": ""}


def test_unknown_block_preserves_raw_payload() -> None:
    raw = {"thoughts": [{"summary": "Searching 3 websites", "finished": True}]}
    block = UnknownBlock(type="thoughts", raw=raw)

    assert block.raw == raw


def test_malformed_known_type_still_raises() -> None:
    """A known type with a bad field must not silently become Unknown."""
    with pytest.raises(ValidationError):
        adapter.validate_python({"type": "code", "language": "python"})


def test_blocks_serialise_with_their_type_tag() -> None:
    message = Message(
        role=MessageRole.ASSISTANT,
        content=[
            TextBlock(text="Here is the code"),
            CodeBlock(text="print(1)", language="python"),
            ReasoningBlock(text="Considered options", label="Thinking"),
            UnknownBlock(type="future_type", raw={"a": 1}),
        ],
    )

    dumped = message.model_dump()

    assert [block["type"] for block in dumped["content"]] == [
        "text",
        "code",
        "reasoning",
        "future_type",
    ]


def test_message_round_trips_through_json() -> None:
    message = Message(
        role=MessageRole.ASSISTANT,
        content=[
            CodeBlock(text="print(1)", language="python"),
            UnknownBlock(type="future_type", text=None, raw={"a": 1}),
        ],
    )

    restored = Message.model_validate_json(message.model_dump_json())

    assert restored == message


def test_a_tool_call_keeps_its_name_and_arguments() -> None:
    block = adapter.validate_python(
        {"type": "tool_use", "name": "web_search", "id": "u1", "input": {"query": "x"}}
    )

    assert isinstance(block, ToolUseBlock)
    assert block.name == "web_search"
    assert block.input == {"query": "x"}


def test_a_tool_result_nests_canonical_blocks() -> None:
    block = adapter.validate_python(
        {
            "type": "tool_result",
            "tool_use_id": "u1",
            "content": [{"type": "text", "text": "found it"}],
        }
    )

    assert isinstance(block, ToolResultBlock)
    assert [type(item) for item in block.content] == [TextBlock]


def test_a_tool_result_that_carried_no_payload_is_not_an_error() -> None:
    """A result the snapshot emptied is not a tool that failed."""
    block = adapter.validate_python({"type": "tool_result", "name": "memory_read"})

    assert isinstance(block, ToolResultBlock)
    assert block.content == []
    assert block.is_error is False


def test_a_nested_unknown_block_does_not_reload_as_a_known_block() -> None:
    """The existing top-level guard, one level further down."""
    original = ToolResultBlock(content=[UnknownBlock(type="knowledge", text="a title")])

    reloaded = adapter.validate_python(original.model_dump(mode="json"))

    assert isinstance(reloaded, ToolResultBlock)
    assert type(reloaded.content[0]) is UnknownBlock
