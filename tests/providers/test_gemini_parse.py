import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from convolvger.core.models import Message, MessageRole, TextBlock
from convolvger.core.results import ParseError
from convolvger.core.source import RawSource
from convolvger.providers.gemini import _parse

FIXTURES = Path(__file__).parent.parent / "fixtures" / "gemini"
LOCAL = Path(__file__).parent.parent / "fixtures" / "local" / "gemini"
SHARE_URL = "https://gemini.google.com/share/0000000000ab"


def body(payload: object) -> str:
    inner = json.dumps(payload, ensure_ascii=False)
    frame = json.dumps(
        [["wrb.fr", "ujx1Bf", inner, None, None, None, "generic"]], ensure_ascii=False
    )
    return f")]}}'\n{len(frame.encode('utf-16-le')) // 2 + 2}\n{frame}"


def text_of(message: Message) -> str:
    """Narrow the first content block, as the Claude parse tests do."""
    block = message.content[0]
    assert isinstance(block, TextBlock)
    return block.text


def source(payload: object) -> RawSource:
    return RawSource(url=SHARE_URL, content=body(payload))


@pytest.fixture
def minimal() -> object:
    return json.loads((FIXTURES / "share-minimal.json").read_text(encoding="utf-8"))


def test_maps_the_envelope_onto_a_conversation(minimal: object) -> None:
    conversation = _parse.parse(source(minimal)).conversation
    assert conversation.provider == "gemini"
    assert conversation.source_url == SHARE_URL
    assert conversation.title == "Example conversation"
    assert conversation.id == "c_000000000001"


def test_each_turn_becomes_a_prompt_and_an_answer(minimal: object) -> None:
    messages = _parse.parse(source(minimal)).conversation.messages
    assert [message.role for message in messages] == [
        MessageRole.USER,
        MessageRole.ASSISTANT,
        MessageRole.USER,
        MessageRole.ASSISTANT,
    ]
    assert text_of(messages[0]) == "Question 0 from the user."
    assert text_of(messages[1]).startswith("First answer with **bold** text.")


def test_the_answer_keeps_its_markdown_table(minimal: object) -> None:
    """The flat string was measured to hold every rendered table cell."""
    answer = text_of(_parse.parse(source(minimal)).conversation.messages[1])
    assert "| Component | Cost |" in answer
    assert "## A heading" in answer


def test_the_answer_carries_the_response_id(minimal: object) -> None:
    messages = _parse.parse(source(minimal)).conversation.messages
    assert messages[1].id == "r_000000000002"
    assert messages[1].provider_metadata["response_content_id"] == "rc_000000000005"


def test_citations_are_preserved_rather_than_dropped(minimal: object) -> None:
    """They exist only in the payload, never in the flat Markdown."""
    messages = _parse.parse(source(minimal)).conversation.messages
    assert len(messages[1].provider_metadata["citations"]) == 2
    assert len(messages[3].provider_metadata["citations"]) == 1


def test_a_turn_that_triggered_no_search_has_no_citations(minimal: object) -> None:
    """Measured: a turn with no web search carries None, not an empty list."""
    payload = json.loads(json.dumps(minimal))
    payload[0][1][1][3][0][0][2] = None
    payload[0][1][1][3][1] = None

    messages = _parse.parse(source(payload)).conversation.messages
    assert len(messages) == 4
    assert "citations" not in messages[3].provider_metadata
    assert "search_queries" not in messages[3].provider_metadata


def test_search_queries_are_preserved(minimal: object) -> None:
    metadata = _parse.parse(source(minimal)).conversation.messages[1].provider_metadata
    assert metadata["search_queries"] == ["text-27", "text-28"]


def test_the_parent_link_is_preserved(minimal: object) -> None:
    messages = _parse.parse(source(minimal)).conversation.messages
    assert "parent" not in messages[1].provider_metadata
    assert messages[3].provider_metadata["parent"][1] == "r_000000000002"


def test_timestamps_come_from_the_turn(minimal: object) -> None:
    conversation = _parse.parse(source(minimal)).conversation
    assert conversation.messages[0].timestamp == datetime.fromtimestamp(
        1780760968.537561, tz=UTC
    )
    assert conversation.created_at == conversation.messages[0].timestamp
    assert conversation.updated_at == conversation.messages[3].timestamp


def test_the_model_name_is_kept_out_of_the_rendered_fields(minimal: object) -> None:
    conversation = _parse.parse(source(minimal)).conversation
    assert conversation.provider_metadata["model"] == "text-212"
    assert conversation.provider_metadata["share_id"] == "0000000000ab"


def test_a_clean_payload_reports_no_findings(minimal: object) -> None:
    assert _parse.parse(source(minimal)).findings == []


def test_a_turn_without_an_answer_is_recorded_not_dropped(minimal: object) -> None:
    payload = json.loads(json.dumps(minimal))
    payload[0][1][1][3][0][0][1][0] = ""
    result = _parse.parse(source(payload))
    assert [item.code for item in result.findings] == ["message_has_no_content"]
    assert len(result.conversation.messages) == 3


def test_a_turn_without_a_prompt_is_recorded_not_dropped(minimal: object) -> None:
    payload = json.loads(json.dumps(minimal))
    payload[0][1][0][2][0][0] = ""
    result = _parse.parse(source(payload))
    assert [item.code for item in result.findings] == ["message_has_no_content"]
    assert len(result.conversation.messages) == 3


def test_a_payload_without_turns_is_refused(minimal: object) -> None:
    payload = json.loads(json.dumps(minimal))
    payload[0][1] = []
    with pytest.raises(ParseError, match="no turns"):
        _parse.parse(source(payload))


def test_a_response_for_another_rpc_is_refused() -> None:
    inner = json.dumps([[]])
    frame = json.dumps([["wrb.fr", "Te6DCf", inner, None, None, None, "generic"]])
    raw = f")]}}'\n{len(frame.encode('utf-16-le')) // 2 + 2}\n{frame}"
    with pytest.raises(ParseError, match="ujx1Bf"):
        _parse.parse(RawSource(url=SHARE_URL, content=raw))


def test_an_undecodable_body_is_refused() -> None:
    with pytest.raises(ParseError, match="prefix"):
        _parse.parse(RawSource(url=SHARE_URL, content="not a batchexecute response"))


@pytest.mark.skipif(
    not (LOCAL / "ujx1Bf-full.txt").exists(),
    reason="local capture not present (see tests/fixtures/local/)",
)
def test_the_real_capture_parses_into_four_exchanges() -> None:
    raw = (LOCAL / "ujx1Bf-full.txt").read_text(encoding="utf-8")
    result = _parse.parse(RawSource(url=SHARE_URL, content=raw))
    messages = result.conversation.messages
    assert len(messages) == 8
    assert result.conversation.title == "Solar System Installation Guide Pakistan"
    assert [len(text_of(message)) for message in messages] == [
        311,
        4331,
        33,
        5396,
        28,
        1896,
        41,
        3500,
    ]
    assert result.findings == []


MISSING_SHARE = (
    ")]}'\n\n"
    '[["wrb.fr","ujx1Bf",null,null,null,[5],"generic"],'
    '["di",172],["af.httprm",172,"-1490094734237710798",11]]'
)


def test_a_share_that_carries_nothing_says_so() -> None:
    """A deleted or unknown share returns 200 with a null payload."""
    with pytest.raises(ParseError, match="carried no conversation"):
        _parse.parse(RawSource(url=SHARE_URL, content=MISSING_SHARE))
