import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from convolvger.core.models import Message, MessageRole, TextBlock
from convolvger.core.results import ParseError
from convolvger.core.source import RawSource
from convolvger.providers.deepseek import _parse
from convolvger.renderers import render_json, render_markdown

FIXTURE = Path(__file__).parent.parent / "fixtures" / "deepseek" / "share-minimal.json"
SHARE_URL = "https://chat.deepseek.com/share/0example0share0id"


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


def messages_of(payload: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = payload["data"]["biz_data"]["messages"]
    return result


def codes(payload: object) -> list[str]:
    return [item.code for item in _parse.parse(source(payload)).findings]


def test_maps_the_envelope_onto_a_conversation(minimal: dict[str, Any]) -> None:
    result = _parse.parse(source(minimal))
    conversation = result.conversation
    assert conversation.provider == "deepseek"
    assert conversation.title == "Shared Conversation"
    assert conversation.id is None
    assert result.findings == []


def test_the_generic_title_is_kept_as_served_not_invented(
    minimal: dict[str, Any],
) -> None:
    """Measured: a share's title is "Shared Conversation", not the chat's own."""
    assert _parse.parse(source(minimal)).conversation.title == "Shared Conversation"


def test_messages_follow_the_served_order_not_their_times(
    minimal: dict[str, Any],
) -> None:
    """Measured: an answer's time was earlier than its question's."""
    messages = _parse.parse(source(minimal)).conversation.messages
    assert [m.role for m in messages] == [
        MessageRole.USER,
        MessageRole.ASSISTANT,
        MessageRole.USER,
        MessageRole.ASSISTANT,
    ]
    assert messages[1].timestamp is not None
    assert messages[0].timestamp is not None
    assert messages[1].timestamp < messages[0].timestamp
    assert messages[0].timestamp == datetime.fromtimestamp(1767261600.081, tz=UTC)
    assert [m.id for m in messages] == ["1", "2", "3", "4"]
    assert messages[1].provider_metadata["message_id"] == 2


def test_resolved_citations_are_lifted_and_those_in_code_are_left(
    minimal: dict[str, Any],
) -> None:
    answer = text_of(_parse.parse(source(minimal)).conversation.messages[1])
    assert answer.startswith("Kettles heat water with an element.\n\n")
    assert "x = [citation:1]" in answer
    assert answer.count("[citation:") == 1


def test_the_served_text_is_kept_whenever_citations_are_lifted(
    minimal: dict[str, Any],
) -> None:
    message = _parse.parse(source(minimal)).conversation.messages[1]
    fragment = message.provider_metadata["fragment_extras"]["1"]
    assert fragment["content"] == messages_of(minimal)[1]["fragments"][1]["content"]
    assert "content" not in message.provider_metadata["fragment_extras"].get(
        "0", {}
    ) or (message.provider_metadata["fragment_extras"]["0"]["type"] == "SEARCH")


def test_a_fragment_without_citations_keeps_no_second_copy(
    minimal: dict[str, Any],
) -> None:
    message = _parse.parse(source(minimal)).conversation.messages[3]
    assert "content" not in message.provider_metadata["fragment_extras"]["0"]


def test_a_citation_that_names_no_result_is_left_and_reported(
    minimal: dict[str, Any],
) -> None:
    messages_of(minimal)[1]["fragments"][1]["content"] += " Also this.[citation:9]"
    result = _parse.parse(source(minimal))
    assert text_of(result.conversation.messages[1]).endswith("Also this.[citation:9]")
    assert [f.message for f in result.findings] == [
        "[citation:9] names no search result, preserved in text"
    ]


def test_search_results_stay_out_of_the_document(minimal: dict[str, Any]) -> None:
    result = _parse.parse(source(minimal))
    search = result.conversation.messages[1].provider_metadata["fragment_extras"]["0"]
    assert len(search["results"]) == 3
    document = render_markdown(result.conversation, findings=result.findings)
    assert "example.com/source" not in document
    assert "example.com/source" in render_json(
        result.conversation, findings=result.findings
    )


def test_an_unknown_fragment_type_is_kept_and_flagged(minimal: dict[str, Any]) -> None:
    """A thinking fragment was not observed; whatever it is, it is flagged."""
    messages_of(minimal)[1]["fragments"].insert(
        0, {"id": 0, "type": "THINK", "content": "hm"}
    )
    result = _parse.parse(source(minimal))
    assert [f.message for f in result.findings] == [
        "THINK fragment preserved in provider_metadata"
    ]
    assert (
        result.conversation.messages[1].provider_metadata["fragment_extras"]["0"][
            "content"
        ]
        == "hm"
    )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("status", "PENDING", "status 'PENDING'"),
        ("incomplete_message", {"reason": "x"}, "marked incomplete"),
        ("has_pending_fragment", True, "a fragment was still pending"),
    ],
)
def test_an_unfinished_answer_is_reported(
    minimal: dict[str, Any], field: str, value: object, message: str
) -> None:
    messages_of(minimal)[3][field] = value
    result = _parse.parse(source(minimal))
    assert [(f.code, f.message) for f in result.findings] == [
        ("message_content_withheld", message)
    ]


def test_an_unknown_role_is_recorded_not_guessed(minimal: dict[str, Any]) -> None:
    messages_of(minimal)[0]["role"] = "SYSTEM"
    result = _parse.parse(source(minimal))
    assert result.conversation.messages[0].role is MessageRole.UNKNOWN
    assert result.conversation.messages[0].provider_metadata["role"] == "SYSTEM"
    assert codes(minimal) == ["unrecognised_role"]


def test_the_envelopes_are_kept(minimal: dict[str, Any]) -> None:
    metadata = _parse.parse(source(minimal)).conversation.provider_metadata
    assert metadata["model_type"] == "default"
    assert metadata["envelope"] == {
        "outer": {"code": 0, "msg": ""},
        "data": {"biz_code": 0, "biz_msg": ""},
    }


def test_a_missing_share_is_refused_with_the_provider_s_words() -> None:
    payload = {
        "code": 0,
        "msg": "",
        "data": {"biz_code": 1, "biz_msg": "share does not exist", "biz_data": None},
    }
    with pytest.raises(ParseError, match="share does not exist"):
        _parse.parse(source(payload))


def test_a_share_with_no_messages_is_refused(minimal: dict[str, Any]) -> None:
    minimal["data"]["biz_data"]["messages"] = []
    with pytest.raises(ParseError, match="carried no conversation"):
        _parse.parse(source(minimal))


@pytest.mark.parametrize(
    "content",
    ["<!doctype html><title>DeepSeek</title>", "[]", json.dumps({"data": []})],
)
def test_a_payload_that_is_not_a_share_is_refused(content: str) -> None:
    with pytest.raises(ParseError):
        _parse.parse(RawSource(url=SHARE_URL, content=content))


def test_a_served_empty_text_is_kept(minimal: dict[str, Any]) -> None:
    """No text block holds "", so it is not mapped and must not vanish."""
    messages_of(minimal)[3]["fragments"][0]["content"] = ""
    result = _parse.parse(source(minimal))
    extras = result.conversation.messages[3].provider_metadata["fragment_extras"]
    assert extras["0"]["content"] == ""
    assert [f.code for f in result.findings] == ["message_has_no_content"]
