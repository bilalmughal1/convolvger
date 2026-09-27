import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from convolvger.core.models import Message, MessageRole, TextBlock
from convolvger.core.results import ParseError
from convolvger.core.source import RawSource
from convolvger.providers.kimi import _parse
from convolvger.renderers import render_json, render_markdown

FIXTURE = Path(__file__).parent.parent / "fixtures" / "kimi" / "share-minimal.json"
SHARE_URL = "https://www.kimi.ai/share/00000000-0000-4000-8000-000000000002"


def source(payload: object) -> RawSource:
    return RawSource(url=SHARE_URL, content=json.dumps(payload))


def text_of(message: Message) -> str:
    block = message.content[0]
    assert isinstance(block, TextBlock)
    return block.text


@pytest.fixture
def minimal() -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return loaded


def without_reasoning(payload: dict[str, Any]) -> dict[str, Any]:
    """The fixture minus its think and tool blocks, which are flagged by design."""
    for message in payload["share"]["messages"]:
        message["blocks"] = [
            block
            for block in message["blocks"]
            if "think" not in block and "tool" not in block
        ]
    return payload


def codes(payload: object) -> list[str]:
    return [item.code for item in _parse.parse(source(payload)).findings]


def test_maps_the_envelope_onto_a_conversation(minimal: dict[str, Any]) -> None:
    conversation = _parse.parse(source(minimal)).conversation
    assert conversation.provider == "kimi"
    assert conversation.source_url == SHARE_URL
    assert conversation.title == "Example Kimi conversation"
    assert conversation.id == "00000000-0000-4000-8000-000000000001"
    assert conversation.created_at == datetime(2026, 1, 1, 10, 0, 0, 650352, tzinfo=UTC)


def test_messages_keep_their_order_roles_and_text(minimal: dict[str, Any]) -> None:
    messages = _parse.parse(source(minimal)).conversation.messages
    assert [m.role for m in messages] == [
        MessageRole.USER,
        MessageRole.ASSISTANT,
        MessageRole.USER,
        MessageRole.ASSISTANT,
    ]
    assert text_of(messages[0]) == "How does a kettle work?"
    assert "| Element | Heats |" in text_of(messages[1])
    assert messages[1].status == "MESSAGE_STATUS_COMPLETED"


def test_nanosecond_times_are_read_and_the_served_string_kept(
    minimal: dict[str, Any],
) -> None:
    """The model holds microseconds; the served nanoseconds are not rounded away."""
    message = _parse.parse(source(minimal)).conversation.messages[0]
    assert message.timestamp == datetime(2026, 1, 1, 10, 0, 1, 123456, tzinfo=UTC)
    assert message.provider_metadata["createTime"] == "2026-01-01T10:00:01.123456789Z"


def test_a_missing_children_list_is_read_as_empty_not_damage(
    minimal: dict[str, Any],
) -> None:
    """Protobuf JSON omits an empty list; the last message has none."""
    assert "childrenMessageIds" not in minimal["share"]["messages"][-1]
    result = _parse.parse(source(without_reasoning(minimal)))
    assert result.findings == []


def test_reasoning_and_searches_are_kept_and_flagged(minimal: dict[str, Any]) -> None:
    result = _parse.parse(source(minimal))
    assert sorted((f.code, f.message, f.occurrences) for f in result.findings) == [
        ("unmodelled_content_type", "think block preserved in provider_metadata", 1),
        ("unmodelled_content_type", "think block preserved in provider_metadata", 2),
        ("unmodelled_content_type", "tool block preserved in provider_metadata", 1),
    ]
    extras = result.conversation.messages[3].provider_metadata["block_extras"]
    assert extras["2"]["think"]["summary"] == "Checking the switch"
    assert len(extras["3"]["tool"]["contents"]) == 3


def test_every_block_is_accounted_for(minimal: dict[str, Any]) -> None:
    """Text blocks become content; everything else is kept by position."""
    for served, message in zip(
        minimal["share"]["messages"],
        _parse.parse(source(minimal)).conversation.messages,
        strict=True,
    ):
        extras = message.provider_metadata.get("block_extras", {})
        texts = iter(
            block.text for block in message.content if isinstance(block, TextBlock)
        )
        for index, block in enumerate(served["blocks"]):
            held = extras.get(str(index), {})
            if "text" in block:
                text = dict(held.get("text", {}))
                text.setdefault("content", next(texts))
                assert {**held, "text": text} == block
            else:
                assert held == block


def test_citations_and_the_sharer_stay_out_of_the_document(
    minimal: dict[str, Any],
) -> None:
    result = _parse.parse(source(minimal))
    conversation = result.conversation
    assert conversation.provider_metadata["creator"]["name"] == "Example Sharer"
    assert len(conversation.messages[3].provider_metadata["references"]) == 1

    document = render_markdown(conversation, findings=result.findings)
    assert "Example Sharer" not in document
    assert "example.com/source" not in document
    assert "Search to confirm" not in document

    archive = render_json(conversation, findings=result.findings)
    assert "Example Sharer" in archive
    assert "Search to confirm" in archive


def test_a_status_other_than_completed_is_reported(minimal: dict[str, Any]) -> None:
    minimal["share"]["messages"][1]["status"] = "MESSAGE_STATUS_FAILED"
    result = _parse.parse(source(without_reasoning(minimal)))
    assert [(f.code, f.message) for f in result.findings] == [
        ("message_content_withheld", "status 'MESSAGE_STATUS_FAILED'")
    ]


def test_an_unknown_role_is_recorded_not_guessed(minimal: dict[str, Any]) -> None:
    minimal["share"]["messages"][0]["role"] = "system"
    result = _parse.parse(source(without_reasoning(minimal)))
    assert result.conversation.messages[0].role is MessageRole.UNKNOWN
    assert result.conversation.messages[0].provider_metadata["role"] == "system"
    assert codes(without_reasoning(minimal)) == ["unrecognised_role"]


def test_an_unknown_block_kind_is_kept_and_flagged(minimal: dict[str, Any]) -> None:
    minimal["share"]["messages"][0]["blocks"].append(
        {"messageId": "", "image": {"url": "x"}}
    )
    result = _parse.parse(source(without_reasoning(minimal)))
    assert [f.message for f in result.findings] == [
        "image block preserved in provider_metadata"
    ]
    assert result.conversation.messages[0].provider_metadata["block_extras"]["1"][
        "image"
    ] == {"url": "x"}


def test_a_message_with_no_text_is_recorded_not_dropped(
    minimal: dict[str, Any],
) -> None:
    minimal["share"]["messages"][0]["blocks"] = []
    result = _parse.parse(source(without_reasoning(minimal)))
    assert len(result.conversation.messages) == 4
    assert codes(without_reasoning(minimal)) == ["message_has_no_content"]


def test_a_share_with_no_messages_is_refused(minimal: dict[str, Any]) -> None:
    del minimal["share"]["messages"]
    with pytest.raises(ParseError, match="carried no conversation"):
        _parse.parse(source(minimal))


def test_a_saved_not_found_answer_is_refused_with_the_provider_s_code() -> None:
    with pytest.raises(ParseError, match="not_found"):
        _parse.parse(source({"code": "not_found", "details": []}))


@pytest.mark.parametrize("content", ["not json", "[]", json.dumps({"share": []})])
def test_a_payload_that_is_not_a_share_is_refused(content: str) -> None:
    with pytest.raises(ParseError):
        _parse.parse(RawSource(url=SHARE_URL, content=content))


def test_a_served_empty_text_is_kept(minimal: dict[str, Any]) -> None:
    """No text block holds "", so it is not mapped and must not vanish."""
    minimal["share"]["messages"][0]["blocks"] = [
        {"messageId": "", "text": {"content": ""}}
    ]
    result = _parse.parse(source(without_reasoning(minimal)))
    extras = result.conversation.messages[0].provider_metadata["block_extras"]
    assert extras["0"]["text"] == {"content": ""}
    assert [f.code for f in result.findings] == ["message_has_no_content"]
