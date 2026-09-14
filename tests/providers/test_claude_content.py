"""The Claude content mapper: what it maps, and what it refuses to drop."""

from typing import Any

from convolvger.core.findings import Finding, collapse
from convolvger.core.models import (
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UnknownBlock,
)
from convolvger.providers.claude._content import TEXT_EXTRAS_KEY, to_blocks


def _map(
    blocks: Any, message_id: str | None = None
) -> tuple[list[Any], list[Finding], dict[str, Any]]:
    findings: list[Finding] = []
    metadata: dict[str, Any] = {}
    mapped = to_blocks(blocks, findings, metadata, message_id)
    return mapped, findings, metadata


def test_a_text_block_becomes_a_text_block() -> None:
    mapped, findings, metadata = _map([{"type": "text", "text": "hello"}])

    assert mapped == [TextBlock(text="hello")]
    assert findings == []
    assert metadata == {}


def test_a_text_blocks_unmodelled_fields_are_kept_on_the_message() -> None:
    """Every real text block carries these; TextBlock has nowhere to put them."""
    mapped, _, metadata = _map(
        [
            {
                "type": "text",
                "text": "cited prose",
                "citations": [{"url": "https://example.test", "title": "T"}],
                "citations_grouping_mode": "combine",
                "flags": None,
                "start_timestamp": "2026-09-13T00:00:00.000000Z",
            }
        ]
    )

    assert mapped == [TextBlock(text="cited prose")]
    assert metadata[TEXT_EXTRAS_KEY]["0"]["citations"] == [
        {"url": "https://example.test", "title": "T"}
    ]
    assert metadata[TEXT_EXTRAS_KEY]["0"]["citations_grouping_mode"] == "combine"
    assert metadata[TEXT_EXTRAS_KEY]["0"]["flags"] is None


def test_two_text_blocks_keep_their_own_extras() -> None:
    _, _, metadata = _map(
        [
            {"type": "text", "text": "one", "uuid": "a"},
            {"type": "text", "text": "two", "uuid": "b"},
        ]
    )

    assert metadata[TEXT_EXTRAS_KEY] == {"0": {"uuid": "a"}, "1": {"uuid": "b"}}


def test_a_tool_call_maps_its_name_identifier_and_arguments() -> None:
    mapped, findings, _ = _map(
        [
            {
                "type": "tool_use",
                "name": "web_search",
                "id": "u1",
                "input": {"query": "x"},
            }
        ]
    )

    assert mapped == [
        ToolUseBlock(name="web_search", id="u1", input={"query": "x"})
    ]
    assert findings == []


def test_a_tool_calls_presentation_fields_are_preserved_in_raw() -> None:
    mapped, _, _ = _map(
        [
            {
                "type": "tool_use",
                "name": "web_search",
                "id": "u1",
                "input": {},
                "tool_origin": "first_party",
                "icon_name": "search",
                "is_mcp_app": False,
            }
        ]
    )

    block = mapped[0]
    assert isinstance(block, ToolUseBlock)
    assert block.raw == {
        "tool_origin": "first_party",
        "icon_name": "search",
        "is_mcp_app": False,
    }


def test_an_omitted_field_stays_omitted_rather_than_becoming_null() -> None:
    """Half this provider's tool blocks carry tool_origin and half do not."""
    without, _, _ = _map([{"type": "tool_use", "name": "a", "id": "u1", "input": {}}])
    with_null, _, _ = _map(
        [{"type": "tool_use", "name": "a", "id": "u1", "input": {}, "tool_origin": None}]
    )

    first, second = without[0], with_null[0]
    assert isinstance(first, ToolUseBlock)
    assert isinstance(second, ToolUseBlock)
    assert "tool_origin" not in first.raw
    assert second.raw == {"tool_origin": None}


def test_an_unexpectedly_shaped_argument_survives_in_raw() -> None:
    mapped, _, _ = _map([{"type": "tool_use", "name": "a", "input": ["not", "a", "map"]}])

    block = mapped[0]
    assert isinstance(block, ToolUseBlock)
    assert block.input == {}
    assert block.raw["input"] == ["not", "a", "map"]


def test_a_tool_result_nests_the_blocks_it_carried() -> None:
    mapped, findings, _ = _map(
        [
            {
                "type": "tool_result",
                "tool_use_id": "u1",
                "name": "web_search",
                "is_error": False,
                "content": [{"type": "text", "text": "inner"}],
                "structured_content": None,
            }
        ]
    )

    block = mapped[0]
    assert isinstance(block, ToolResultBlock)
    assert block.content == [TextBlock(text="inner")]
    assert findings == []


def test_an_unmodelled_inner_block_is_preserved_verbatim() -> None:
    mapped, findings, _ = _map(
        [
            {
                "type": "tool_result",
                "tool_use_id": "u1",
                "name": "web_search",
                "content": [
                    {
                        "type": "knowledge",
                        "title": "T",
                        "url": "https://example.test",
                        "is_missing": False,
                        "metadata": {},
                    }
                ],
            }
        ]
    )

    block = mapped[0]
    assert isinstance(block, ToolResultBlock)
    inner = block.content[0]
    assert isinstance(inner, UnknownBlock)
    assert inner.type == "knowledge"
    assert inner.raw["url"] == "https://example.test"
    assert inner.raw["is_missing"] is False
    assert [item.code for item in findings] == ["unmodelled_content_type"]


def test_repeated_unmodelled_inner_types_collapse_to_one_count() -> None:
    """Eighty-two identical observations should read as one finding with a count."""
    _, findings, _ = _map(
        [
            {
                "type": "tool_result",
                "tool_use_id": "u1",
                "name": "web_search",
                "content": [{"type": "knowledge", "title": str(n)} for n in range(82)],
            }
        ]
    )

    collapsed = collapse(findings)

    assert len(collapsed) == 1
    assert collapsed[0].occurrences == 82


def test_a_tool_result_carrying_nothing_is_recorded_against_its_message() -> None:
    _, findings, _ = _map(
        [
            {
                "type": "tool_result",
                "tool_use_id": "u1",
                "name": "memory_read",
                "content": [],
                "structured_content": None,
            }
        ],
        message_id="m1",
    )

    assert [(item.code, item.message_id) for item in findings] == [
        ("tool_result_has_no_content", "m1")
    ]
    assert "memory_read" in findings[0].message


def test_a_tool_result_with_structured_content_is_not_called_empty() -> None:
    _, findings, _ = _map(
        [
            {
                "type": "tool_result",
                "tool_use_id": "u1",
                "name": "memory_read",
                "content": [],
                "structured_content": {"rows": 2},
            }
        ]
    )

    assert findings == []


def test_a_citation_nested_in_a_tool_result_records_where_it_was_found() -> None:
    _, _, metadata = _map(
        [
            {"type": "text", "text": "top"},
            {
                "type": "tool_result",
                "tool_use_id": "u1",
                "content": [
                    {"type": "text", "text": "inner", "uuid": "deep"},
                ],
                "structured_content": None,
            },
        ]
    )

    assert metadata[TEXT_EXTRAS_KEY] == {"1.0": {"uuid": "deep"}}


def test_an_unmodelled_block_type_is_preserved_with_a_finding() -> None:
    mapped, findings, _ = _map([{"type": "thinking", "thinking": "elsewhere"}])

    block = mapped[0]
    assert isinstance(block, UnknownBlock)
    assert block.type == "thinking"
    assert block.raw == {"thinking": "elsewhere"}
    assert [item.code for item in findings] == ["unmodelled_content_type"]


def test_a_block_that_is_not_an_object_is_still_preserved() -> None:
    mapped, findings, _ = _map(["just a string"])

    block = mapped[0]
    assert isinstance(block, UnknownBlock)
    assert block.raw == {"block": "just a string"}
    assert [item.code for item in findings] == ["unmodelled_content_type"]
