"""Parsing a saved Claude snapshot: the mapping, and what it records."""

import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from convolvger.core.models import MessageRole, TextBlock, ToolResultBlock, ToolUseBlock
from convolvger.core.results import ParseError, ParseResult
from convolvger.core.source import RawSource
from convolvger.providers.claude._parse import parse
from convolvger.validation.aspects import Aspect
from convolvger.validation.report import Report

FIXTURE = Path(__file__).parent.parent / "fixtures" / "claude" / "share-minimal.json"
SHARE_URL = "https://claude.ai/share/00000000-0000-0000-0000-000000000000"
LOCAL = Path(__file__).parent.parent / "fixtures" / "local" / "claude"
CAPTURE = LOCAL / "snapshot-2026-09-13.json"


def _parse(payload: Any) -> ParseResult:
    text = payload if isinstance(payload, str) else json.dumps(payload)
    return parse(RawSource(url=SHARE_URL, content=text, content_type="application/json"))


def _fixture() -> ParseResult:
    return parse(
        RawSource(
            url=SHARE_URL,
            content=FIXTURE.read_text(encoding="utf-8"),
            content_type="application/json",
        )
    )


def _envelope(**overrides: Any) -> dict[str, Any]:
    envelope: dict[str, Any] = json.loads(FIXTURE.read_text(encoding="utf-8"))
    envelope.update(overrides)
    return envelope


def test_the_envelope_supplies_the_conversations_identity() -> None:
    conversation = _fixture().conversation

    assert conversation.provider == "claude"
    assert conversation.id == "00000000-0000-0000-0000-000000000000"
    assert conversation.title == "A minimal shared conversation"
    assert conversation.source_url == SHARE_URL
    assert conversation.created_at == datetime(2026, 9, 13, 10, 0, tzinfo=UTC)
    assert conversation.updated_at == datetime(2026, 9, 13, 10, 5, tzinfo=UTC)


def test_senders_map_onto_canonical_roles() -> None:
    messages = _fixture().conversation.messages

    assert [message.role for message in messages] == [
        MessageRole.USER,
        MessageRole.ASSISTANT,
    ]
    assert messages[0].id == "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    assert messages[1].status == "end_turn"
    assert messages[0].timestamp == datetime(2026, 9, 13, 10, 0, tzinfo=UTC)


def test_an_unrecognised_sender_is_recorded_rather_than_guessed() -> None:
    envelope = _envelope()
    envelope["chat_messages"][0]["sender"] = "operator"

    result = _parse(envelope)

    assert result.conversation.messages[0].role is MessageRole.UNKNOWN
    assert "unrecognised_role" in {item.code for item in result.findings}


def test_content_comes_from_the_blocks_not_the_empty_text_field() -> None:
    """Every message carries text=""; reading it produces a blank archive."""
    envelope = _envelope()
    assert all(message["text"] == "" for message in envelope["chat_messages"])

    messages = _fixture().conversation.messages

    first = messages[0].content[0]
    assert isinstance(first, TextBlock)
    assert first.text == "Summarise the two files I attached."
    assert messages[0].provider_metadata["text"] == ""


def test_tool_blocks_survive_the_mapping() -> None:
    blocks = _fixture().conversation.messages[1].content

    call, result, prose = blocks
    assert isinstance(call, ToolUseBlock)
    assert call.name == "example_tool"
    assert call.input == {"query": "the two files"}
    assert call.raw["tool_origin"] == "first_party"
    assert isinstance(result, ToolResultBlock)
    assert result.tool_use_id == "toolu_0000"
    assert result.content == []
    assert isinstance(prose, TextBlock)


def test_unmodelled_envelope_fields_are_kept_on_the_conversation() -> None:
    metadata = _fixture().conversation.provider_metadata

    assert metadata["conversation_uuid"] == "11111111-1111-4111-8111-111111111111"
    assert metadata["up_to_date"] is True
    assert metadata["is_public"] is True
    assert metadata["created_by"] == "Example Sharer"
    assert metadata["creator"]["full_name"] == "Example Sharer"
    assert metadata["project_uuid"] is None


def test_unmodelled_message_fields_are_kept_on_the_message() -> None:
    metadata = _fixture().conversation.messages[0].provider_metadata

    assert metadata["index"] == 0
    assert metadata["input_mode"] == "text"
    assert metadata["parent_message_uuid"] == "00000000-0000-4000-8000-000000000000"
    assert metadata["truncated"] is False
    assert metadata["file_count"] == 2


def test_a_text_blocks_own_extras_are_kept_alongside_the_messages() -> None:
    metadata = _fixture().conversation.messages[0].provider_metadata

    assert metadata["text_block_extras"]["0"]["citations"] == []


def test_declared_files_that_were_not_served_are_recorded() -> None:
    recorded = [
        item for item in _fixture().findings if item.code == "attachment_withheld"
    ]

    assert len(recorded) == 1
    assert recorded[0].message_id == "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    assert "2 declared" in recorded[0].message


def test_files_that_were_served_are_not_recorded_as_withheld() -> None:
    envelope = _envelope()
    envelope["chat_messages"][0]["files"] = [{"file_name": "a.pdf"}]

    result = _parse(envelope)

    assert "attachment_withheld" not in {item.code for item in result.findings}


def test_an_emptied_tool_result_is_recorded() -> None:
    codes = {item.code for item in _fixture().findings}

    assert "tool_result_has_no_content" in codes


def test_repeated_observations_are_collapsed_once_for_the_whole_snapshot() -> None:
    """The same unmodelled shape can appear in many messages; it reads as one."""
    envelope = _envelope()
    for message in envelope["chat_messages"]:
        message["content"].append({"type": "knowledge", "title": "t"})

    recorded = [
        item
        for item in _parse(envelope).findings
        if item.code == "unmodelled_content_type"
    ]

    assert len(recorded) == 1
    assert recorded[0].occurrences == 2


def test_a_message_with_no_content_is_recorded() -> None:
    envelope = _envelope()
    envelope["chat_messages"][0]["content"] = []

    result = _parse(envelope)

    assert "message_has_no_content" in {item.code for item in result.findings}


def test_a_snapshot_that_is_not_json_is_refused() -> None:
    with pytest.raises(ParseError, match="not valid JSON"):
        _parse("<html>Just a moment...</html>")


def test_a_snapshot_without_messages_is_refused() -> None:
    with pytest.raises(ParseError, match="no chat_messages"):
        _parse({"uuid": "x", "snapshot_name": "y"})


def test_a_snapshot_whose_messages_are_all_unreadable_is_refused() -> None:
    with pytest.raises(ParseError, match="no messages"):
        _parse(_envelope(chat_messages=["not", "objects"]))


@pytest.mark.skipif(
    not CAPTURE.exists(),
    reason="local capture not present (see tests/fixtures/local/)",
)
def test_the_real_capture_parses_as_measured() -> None:
    """A 34-message conversation captured from claude.ai on 2026-09-13.

    The share URL here is the synthetic one: the parser reads the file,
    and the real link is not committed.
    """
    result = parse(
        RawSource(url=SHARE_URL, content=CAPTURE.read_text(encoding="utf-8"))
    )
    messages = result.conversation.messages

    assert len(messages) == 34
    assert Counter(m.role for m in messages) == {
        MessageRole.USER: 17,
        MessageRole.ASSISTANT: 17,
    }
    assert Counter(b.type for m in messages for b in m.content) == {
        "text": 34,
        "tool_use": 30,
        "tool_result": 30,
    }
    assert Counter(
        inner.type
        for m in messages
        for b in m.content
        if isinstance(b, ToolResultBlock)
        for inner in b.content
    ) == {"knowledge": 82, "text": 2}


@pytest.mark.skipif(
    not CAPTURE.exists(),
    reason="local capture not present (see tests/fixtures/local/)",
)
def test_the_real_capture_reports_what_claude_withheld() -> None:
    """Both verdicts are no, and for different reasons.

    A failure here need not mean the parser broke. It may mean the
    provider changed what a share link serves.
    """
    result = parse(
        RawSource(url=SHARE_URL, content=CAPTURE.read_text(encoding="utf-8"))
    )
    report = Report(findings=result.findings)

    counted = Counter(item.code for item in result.findings)
    occurrences: Counter[str] = Counter()
    for item in result.findings:
        occurrences[item.code] += item.occurrences

    assert counted == {
        "attachment_withheld": 3,
        "tool_result_has_no_content": 12,
        "unmodelled_content_type": 1,
    }
    assert occurrences["tool_result_has_no_content"] == 19
    assert occurrences["unmodelled_content_type"] == 82
    assert not report.complete
    assert not report.faithful
    assert report.unrecognised == []
    assert len(report.findings_for(Aspect.COMPLETENESS)) == 15


@pytest.mark.skipif(
    not CAPTURE.exists(),
    reason="local capture not present (see tests/fixtures/local/)",
)
def test_the_real_capture_keeps_what_the_envelope_carried() -> None:
    """Including the fields naming who shared it, which nothing renders."""
    result = parse(
        RawSource(url=SHARE_URL, content=CAPTURE.read_text(encoding="utf-8"))
    )
    conversation = result.conversation

    assert set(conversation.provider_metadata) == {
        "conversation_uuid",
        "created_by",
        "creator",
        "is_public",
        "project_uuid",
        "up_to_date",
        "working_documents",
    }
    assert conversation.provider_metadata["up_to_date"] is True
    assert sum(
        1
        for m in conversation.messages
        for extras in m.provider_metadata.get("text_block_extras", {}).values()
        if extras.get("citations")
    ) == 3
