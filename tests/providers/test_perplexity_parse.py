import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from convolvger.core.models import Message, MessageRole, TextBlock
from convolvger.core.results import ParseError
from convolvger.core.source import RawSource
from convolvger.providers.base import FetchUnsupportedError
from convolvger.providers.perplexity import PerplexityProvider, _parse
from convolvger.renderers import render_json, render_markdown

FIXTURE = (
    Path(__file__).parent.parent / "fixtures" / "perplexity" / "share-minimal.json"
)
SHARE_URL = "https://www.perplexity.ai/search/00000000-0000-4000-8000-000000000001"


def source(payload: object) -> RawSource:
    return RawSource(url=SHARE_URL, content=json.dumps(payload))


def texts(message: Message) -> list[str]:
    return [block.text for block in message.content if isinstance(block, TextBlock)]


@pytest.fixture
def minimal() -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(FIXTURE.read_text(encoding="utf-8"))
    # Measured equal on the real page; one object keeps them equal when a test
    # changes the first entry.
    assert loaded["first_entry"] == loaded["entries"][0]
    loaded["first_entry"] = loaded["entries"][0]
    return loaded


def blocks(payload: dict[str, Any], entry: int, usage: str) -> dict[str, Any]:
    found: dict[str, Any] = next(
        block
        for block in payload["entries"][entry]["blocks"]
        if block["intended_usage"] == usage
    )
    return found


def text_items(payload: dict[str, Any], entry: int) -> list[dict[str, Any]]:
    workflow = blocks(payload, entry, "workflow_root")["workflow_block"]
    return [
        item
        for step in workflow["steps"]
        for item in step["items"]
        if item["type"] == "WORKFLOW_ITEM_TEXT"
    ]


def test_the_thread_maps_onto_a_conversation(minimal: dict[str, Any]) -> None:
    conversation = _parse.parse(source(minimal)).conversation
    assert conversation.provider == "perplexity"
    assert conversation.id == "00000000-0000-4000-8000-000000000001"
    assert conversation.title == "Example Perplexity thread"
    assert conversation.created_at == datetime(2026, 1, 1, 10, 0, tzinfo=UTC)


def test_each_entry_is_a_question_and_its_answer(minimal: dict[str, Any]) -> None:
    result = _parse.parse(source(minimal))
    messages = result.conversation.messages
    assert [m.role for m in messages] == [
        MessageRole.USER,
        MessageRole.ASSISTANT,
    ] * 2
    assert texts(messages[0]) == ["How does a kettle work?"]
    assert texts(messages[3]) == [
        "A thermostat switches it off.[1]",
        "\n\n## Safety\n\nIt also cuts out when dry.[2]",
    ]
    assert messages[0].id == "00000000-0000-4000-8000-000000000010"
    assert messages[1].id == "00000000-0000-4000-8000-000000000020"
    assert messages[1].timestamp == datetime(2026, 1, 1, 10, 0, 20, tzinfo=UTC)
    assert result.findings == []


def test_a_citation_names_the_result_marked_with_its_number(
    minimal: dict[str, Any],
) -> None:
    """The second answer cites the third result first: by its mark, not its place."""
    messages = _parse.parse(source(minimal)).conversation.messages
    assert [(c.number, c.ref, c.url, c.title) for c in messages[3].citations] == [
        (1, "1", "https://example.com/source-3", "Example source 3"),
        (2, "2", "https://example.com/source-1", "Example source 1"),
    ]


def test_a_number_inside_code_is_not_a_citation(minimal: dict[str, Any]) -> None:
    answer = texts(_parse.parse(source(minimal)).conversation.messages[1])[0]
    assert answer.startswith("Kettles heat water with an element.[1][2]")
    assert "x = [1]" in answer


def test_a_number_no_result_is_marked_with_is_left_and_reported(
    minimal: dict[str, Any],
) -> None:
    text_items(minimal, 0)[0]["payload"]["text_payload"]["text"] = "A claim.[7]"
    result = _parse.parse(source(minimal))
    assert texts(result.conversation.messages[1]) == ["A claim.[7]"]
    assert ("[7] names no cited result, preserved in text") in [
        f.message for f in result.findings
    ]


def test_the_sharer_and_uncited_results_stay_out_of_the_document(
    minimal: dict[str, Any],
) -> None:
    result = _parse.parse(source(minimal))
    document = render_markdown(result.conversation, findings=result.findings)
    archive = render_json(result.conversation, findings=result.findings)
    for sharer in ("Example Sharer", "example-sharer", "example.com/avatar.png"):
        assert sharer not in document
        assert sharer in archive
    assert (
        "**Sources**\n\n1. [Example source 1](<https://example.com/source-1>)"
        in document
    )
    assert "Invented snippet" not in document


def test_the_entry_is_kept_whole_beside_the_answer(minimal: dict[str, Any]) -> None:
    """Everything but the question, which its own text block holds exactly."""
    message = _parse.parse(source(minimal)).conversation.messages[1]
    served = minimal["entries"][0]
    assert message.provider_metadata == {
        key: value for key, value in served.items() if key != "query_str"
    }


def test_a_block_of_an_unseen_kind_is_kept_and_flagged(minimal: dict[str, Any]) -> None:
    minimal["entries"][0]["blocks"].append(
        {"intended_usage": "canvas", "canvas_block": {"cells": []}}
    )
    result = _parse.parse(source(minimal))
    assert [(f.code, f.message) for f in result.findings] == [
        ("unmodelled_content_type", "canvas block preserved in provider_metadata")
    ]


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (
            {
                "payload": {
                    "text_payload": {"text": "Thinking.", "variant": "reasoning"}
                }
            },
            "'reasoning' text item preserved in provider_metadata",
        ),
        (
            {"type": "WORKFLOW_ITEM_CHART", "payload": {"chart_payload": {}}},
            "'WORKFLOW_ITEM_CHART' item preserved in provider_metadata",
        ),
    ],
)
def test_an_item_of_an_unseen_kind_is_kept_and_flagged(
    minimal: dict[str, Any], change: dict[str, Any], message: str
) -> None:
    text_items(minimal, 0)[0].update(change)
    result = _parse.parse(source(minimal))
    assert ("unmodelled_content_type", message) in [
        (f.code, f.message) for f in result.findings
    ]
    assert texts(result.conversation.messages[1]) == []


def test_an_image_in_the_answer_is_kept_and_flagged(minimal: dict[str, Any]) -> None:
    text_items(minimal, 0)[0]["payload"]["text_payload"]["images"] = [
        {"url": "https://example.com/image.png"}
    ]
    result = _parse.parse(source(minimal))
    assert [(f.code, f.message) for f in result.findings] == [
        (
            "unmodelled_content_type",
            "image in the answer preserved in provider_metadata",
        )
    ]
    assert texts(result.conversation.messages[1])


def test_a_thread_longer_than_its_first_page_says_so(minimal: dict[str, Any]) -> None:
    minimal["has_next_page"] = True
    result = _parse.parse(source(minimal))
    assert [(f.code, f.message_id) for f in result.findings] == [
        ("message_content_withheld", None)
    ]
    assert "first page of 2 entries" in result.findings[0].message


def test_a_first_entry_that_differs_from_the_first_of_entries_is_kept(
    minimal: dict[str, Any],
) -> None:
    minimal["first_entry"] = {"uuid": "elsewhere"}
    result = _parse.parse(source(minimal))
    assert result.conversation.provider_metadata["first_entry"] == {"uuid": "elsewhere"}
    assert [f.code for f in result.findings] == ["unmodelled_content_type"]


def test_a_first_entry_equal_to_the_first_of_entries_is_not_kept_twice(
    minimal: dict[str, Any],
) -> None:
    assert (
        "first_entry"
        not in _parse.parse(source(minimal)).conversation.provider_metadata
    )


def test_an_answer_not_completed_is_reported(minimal: dict[str, Any]) -> None:
    minimal["entries"][1]["status"] = "FAILED"
    result = _parse.parse(source(minimal))
    assert [(f.code, f.message) for f in result.findings] == [
        ("message_content_withheld", "status 'FAILED'")
    ]


@pytest.mark.parametrize(
    ("content", "reason"),
    [
        ("not json", "not valid JSON"),
        ("[]", "not a JSON object"),
        ('{"entries": []}', "not a Perplexity thread"),
        ('{"entries": [], "thread_metadata": {}}', "carries no entries"),
    ],
)
def test_a_payload_that_is_not_a_thread_is_refused(content: str, reason: str) -> None:
    with pytest.raises(ParseError, match=reason):
        _parse.parse(RawSource(url=SHARE_URL, content=content))


def test_the_provider_matches_shares_and_refuses_to_fetch() -> None:
    provider = PerplexityProvider()
    assert provider.matches(SHARE_URL)
    assert not provider.matches("https://claude.ai/share/x")
    with pytest.raises(FetchUnsupportedError, match="--capture"):
        provider.fetch(SHARE_URL)
