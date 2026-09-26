import json
import re
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path
from typing import Any

import pytest

from convolvger.core.models import Message, MessageRole, TextBlock
from convolvger.core.results import ParseError
from convolvger.core.source import RawSource
from convolvger.providers.grok import _parse
from convolvger.renderers import render_json, render_markdown

FIXTURES = Path(__file__).parent.parent / "fixtures" / "grok"
SHARE_URL = "https://grok.com/share/bGVnYWN5_00000000-0000-4000-8000-000000000001"


CITATION = re.compile(r"<grok:render\b([^>]*)>.*?</grok:render>", re.DOTALL)
"""Written here rather than imported, so the parser is checked against an
independent reading of the markup rather than against itself."""


def without_carried_citations(message: str, cards: list[str]) -> str:
    """Remove each inline citation whose card the response carries."""
    carried = {json.loads(card)["id"] for card in cards}

    def drop(match: re.Match[str]) -> str:
        opening = match.group(1)
        card = re.search(r'card_id="([^"]*)"', opening)
        cited = 'type="render_inline_citation"' in opening
        return "" if cited and card and card.group(1) in carried else match.group(0)

    return CITATION.sub(drop, message)


def text_of(message: Message) -> str:
    block = message.content[0]
    assert isinstance(block, TextBlock)
    return block.text


def source(payload: object) -> RawSource:
    return RawSource(url=SHARE_URL, content=json.dumps(payload))


@pytest.fixture
def minimal() -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(
        (FIXTURES / "share-minimal.json").read_text(encoding="utf-8")
    )
    return loaded


def codes(payload: object) -> list[str]:
    return [item.code for item in _parse.parse(source(payload)).findings]


def without_steps(payload: dict[str, Any]) -> dict[str, Any]:
    """The fixture minus its reasoning trace, which is flagged by design."""
    payload["responses"][3]["steps"] = []
    return payload


def test_maps_the_envelope_onto_a_conversation(minimal: dict[str, Any]) -> None:
    conversation = _parse.parse(source(minimal)).conversation
    assert conversation.provider == "grok"
    assert conversation.source_url == SHARE_URL
    assert conversation.title == "Example Grok conversation"
    assert conversation.id == "00000000-0000-4000-8000-000000000001"
    assert conversation.created_at == datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
    assert conversation.updated_at == datetime(2026, 1, 2, 12, 0, 5, tzinfo=UTC)


def test_every_sender_casing_is_folded_into_a_role(minimal: dict[str, Any]) -> None:
    """human, ASSISTANT and assistant were all seen in one conversation."""
    messages = _parse.parse(source(minimal)).conversation.messages
    assert [message.role for message in messages] == [
        MessageRole.USER,
        MessageRole.ASSISTANT,
        MessageRole.USER,
        MessageRole.ASSISTANT,
    ]


def test_the_served_sender_is_kept(minimal: dict[str, Any]) -> None:
    """Folding the casing must not erase which casing the provider sent."""
    messages = _parse.parse(source(minimal)).conversation.messages
    assert [m.provider_metadata["sender"] for m in messages] == [
        "human",
        "ASSISTANT",
        "human",
        "assistant",
    ]


def test_an_unknown_sender_is_recorded_not_guessed(minimal: dict[str, Any]) -> None:
    minimal["responses"][0]["sender"] = "system"
    result = _parse.parse(source(minimal))
    assert result.conversation.messages[0].role is MessageRole.UNKNOWN
    assert "unrecognised_role" in [item.code for item in result.findings]


def test_response_ids_and_times_are_mapped(minimal: dict[str, Any]) -> None:
    messages = _parse.parse(source(minimal)).conversation.messages
    assert messages[0].id == "00000000-0000-4000-8000-000000000010"
    assert messages[0].timestamp == datetime(2026, 1, 1, 10, 0, 0, 100000, tzinfo=UTC)


def test_the_parent_chain_is_preserved(minimal: dict[str, Any]) -> None:
    messages = _parse.parse(source(minimal)).conversation.messages
    for earlier, later in pairwise(messages):
        assert later.provider_metadata["parentResponseId"] == earlier.id


def test_a_parent_outside_the_share_is_kept_and_not_reported(
    minimal: dict[str, Any],
) -> None:
    """Seen on a copied share: the first parent names the original's response."""
    result = _parse.parse(source(without_steps(minimal)))
    first = result.conversation.messages[0]
    assert first.provider_metadata["parentResponseId"] == (
        "00000000-0000-4000-8000-000000000009"
    )
    assert result.findings == []


def test_citation_markup_is_lifted_out_of_the_text(minimal: dict[str, Any]) -> None:
    answer = text_of(_parse.parse(source(minimal)).conversation.messages[3])
    assert "<grok:" not in answer
    assert answer.startswith(
        "Kettles boil water by passing current through a heating element.\n\n"
    )
    assert "| Element | Heats |" in answer


def test_the_served_text_is_kept_whenever_citations_are_lifted(
    minimal: dict[str, Any],
) -> None:
    message = _parse.parse(source(minimal)).conversation.messages[3]
    served = message.provider_metadata["message"]
    assert served == minimal["responses"][3]["message"]
    assert served.count("<grok:render") == 2

    cards = message.provider_metadata["cardAttachmentsJson"]
    assert without_carried_citations(served, cards) == text_of(message)


def test_a_message_without_citations_keeps_no_second_copy(
    minimal: dict[str, Any],
) -> None:
    metadata = _parse.parse(source(minimal)).conversation.messages[1].provider_metadata
    assert "message" not in metadata


def test_a_citation_whose_card_is_absent_stays_in_the_text(
    minimal: dict[str, Any],
) -> None:
    minimal["responses"][3]["cardAttachmentsJson"] = minimal["responses"][3][
        "cardAttachmentsJson"
    ][:1]
    result = _parse.parse(source(without_steps(minimal)))
    answer = text_of(result.conversation.messages[3])
    assert answer.count("<grok:render") == 1
    assert [item.message for item in result.findings] == [
        "grok:render whose card was not carried preserved in text"
    ]


def test_markup_of_an_unknown_type_is_flagged_and_kept(
    minimal: dict[str, Any],
) -> None:
    minimal["responses"][1]["message"] += (
        '<grok:render type="render_chart"><argument name="x">1</argument></grok:render>'
    )
    result = _parse.parse(source(without_steps(minimal)))
    assert "render_chart" in text_of(result.conversation.messages[1])
    assert [item.code for item in result.findings] == ["unmodelled_content_type"]


def test_unclosed_markup_is_flagged_and_kept(minimal: dict[str, Any]) -> None:
    minimal["responses"][1]["message"] += '<grok:render type="render_inline_citation">'
    result = _parse.parse(source(without_steps(minimal)))
    assert "<grok:render" in text_of(result.conversation.messages[1])
    assert [item.message for item in result.findings] == [
        "unrecognised grok markup preserved in text"
    ]


def test_search_results_cards_and_model_are_kept_out_of_the_document(
    minimal: dict[str, Any],
) -> None:
    result = _parse.parse(source(minimal))
    metadata = result.conversation.messages[3].provider_metadata
    assert len(metadata["webSearchResults"]) == 2
    assert len(metadata["cardAttachmentsJson"]) == 2
    assert metadata["model"] == "grok-3"
    assert metadata["citedXposts"] == []

    document = render_markdown(result.conversation, findings=result.findings)
    assert "example.com/source-1" not in document
    assert "grok-3" not in document
    assert "<grok:" not in document


def test_the_json_archive_keeps_what_the_document_leaves_out(
    minimal: dict[str, Any],
) -> None:
    result = _parse.parse(source(minimal))
    archive = render_json(result.conversation, findings=result.findings)
    assert "<grok:render" in archive
    assert "example.com/source-1" in archive
    assert "UNIFIED" in archive


def test_the_reasoning_trace_is_kept_and_flagged(minimal: dict[str, Any]) -> None:
    result = _parse.parse(source(minimal))
    assert len(result.conversation.messages[3].provider_metadata["steps"]) == 2
    assert [(item.code, item.message) for item in result.findings] == [
        ("unmodelled_content_type", "steps preserved in provider_metadata")
    ]


def test_envelope_fields_are_preserved(minimal: dict[str, Any]) -> None:
    metadata = _parse.parse(source(minimal)).conversation.provider_metadata
    assert metadata["isPublic"] is True
    assert metadata["allowIndexing"] is True
    assert metadata["sharedSubagents"] == []
    assert metadata["conversation"]["kind"] == "CONVERSATION_KIND_UNSPECIFIED"
    assert "title" not in metadata["conversation"]


def test_a_value_the_model_cannot_hold_stays_in_metadata(
    minimal: dict[str, Any],
) -> None:
    minimal["conversation"]["modifyTime"] = "not a time"
    minimal["responses"][0]["responseId"] = 7
    conversation = _parse.parse(source(minimal)).conversation
    assert conversation.updated_at is None
    assert conversation.provider_metadata["conversation"]["modifyTime"] == "not a time"
    assert conversation.messages[0].id is None
    assert conversation.messages[0].provider_metadata["responseId"] == 7


@pytest.mark.parametrize(
    "key",
    ["fileAttachments", "imageAttachments", "generatedImageUrls", "imageEditUris"],
)
def test_attachments_declared_but_not_served_are_reported(
    minimal: dict[str, Any], key: str
) -> None:
    minimal["responses"][0][key] = ["00000000-0000-4000-8000-000000000099"]
    result = _parse.parse(source(without_steps(minimal)))
    assert [(item.code, item.message) for item in result.findings] == [
        ("attachment_withheld", f"1 {key} declared, none carried")
    ]
    assert result.findings[0].message_id == "00000000-0000-4000-8000-000000000010"


def test_a_partial_response_is_reported(minimal: dict[str, Any]) -> None:
    minimal["responses"][1]["partial"] = True
    minimal["responses"][1]["streamErrors"] = [{"code": "x"}]
    assert codes(without_steps(minimal)) == [
        "message_content_withheld",
        "message_content_withheld",
    ]


@pytest.mark.parametrize("key", ["toolResponses", "inputChunks", "outputChunks"])
def test_other_unmodelled_content_is_flagged(minimal: dict[str, Any], key: str) -> None:
    minimal["responses"][1][key] = [{"anything": 1}]
    result = _parse.parse(source(without_steps(minimal)))
    assert [item.message for item in result.findings] == [
        f"{key} preserved in provider_metadata"
    ]
    assert result.conversation.messages[1].provider_metadata[key] == [{"anything": 1}]


def test_shared_subagents_are_flagged(minimal: dict[str, Any]) -> None:
    minimal["sharedSubagents"] = [{"id": "s"}]
    assert codes(without_steps(minimal)) == ["unmodelled_content_type"]


def test_an_empty_message_is_recorded_not_dropped(minimal: dict[str, Any]) -> None:
    minimal["responses"][1]["message"] = ""
    result = _parse.parse(source(without_steps(minimal)))
    assert len(result.conversation.messages) == 4
    assert result.conversation.messages[1].content == []
    assert [item.code for item in result.findings] == ["message_has_no_content"]


def test_a_served_empty_message_is_kept(minimal: dict[str, Any]) -> None:
    """No text block holds "", so it is not mapped and must not vanish."""
    minimal["responses"][1]["message"] = ""
    result = _parse.parse(source(without_steps(minimal)))
    assert result.conversation.messages[1].provider_metadata["message"] == ""
    assert [item.code for item in result.findings] == ["message_has_no_content"]


def test_a_response_that_is_not_an_object_is_kept(minimal: dict[str, Any]) -> None:
    minimal["responses"].append("stray")
    result = _parse.parse(source(without_steps(minimal)))
    assert result.conversation.provider_metadata["unreadable_responses"] == ["stray"]
    assert [item.code for item in result.findings] == ["unmodelled_content_type"]


def test_a_share_with_no_responses_is_refused(minimal: dict[str, Any]) -> None:
    """Measured: a public share can answer with a title and nothing else."""
    minimal["responses"] = []
    with pytest.raises(ParseError, match="carried no conversation"):
        _parse.parse(source(minimal))


@pytest.mark.parametrize(
    "content",
    [
        "not json",
        "[]",
        json.dumps({"responses": []}),
        json.dumps({"conversation": {}, "responses": {}}),
    ],
)
def test_a_payload_that_is_not_a_share_is_refused(content: str) -> None:
    with pytest.raises(ParseError):
        _parse.parse(RawSource(url=SHARE_URL, content=content))
