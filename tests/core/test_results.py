import pytest

from convolvger.core.errors import ConvolvgerError
from convolvger.core.findings import Level, finding
from convolvger.core.models import Conversation, Message, MessageRole, TextBlock
from convolvger.core.results import ParseError, ParseResult


def conversation() -> Conversation:
    return Conversation(
        provider="chatgpt",
        source_url="https://chatgpt.com/share/x",
        messages=[Message(role=MessageRole.USER, content=[TextBlock(text="hi")])],
    )


def test_result_defaults_to_no_findings() -> None:
    assert ParseResult(conversation=conversation()).findings == []


def test_result_carries_findings() -> None:
    item = finding("unrecognised_role", "'bot' preserved as unknown")
    result = ParseResult(conversation=conversation(), findings=[item])

    assert result.findings == [item]


def test_findings_are_not_stored_on_the_conversation() -> None:
    """Findings are extraction metadata and must stay outside the model."""
    result = ParseResult(
        conversation=conversation(),
        findings=[finding("unrecognised_role", "something")],
    )

    assert "findings" not in result.conversation.model_dump()


def test_a_warning_finding_sets_warned() -> None:
    result = ParseResult(
        conversation=conversation(),
        findings=[finding("unrecognised_role", "something")],
    )

    assert result.warned is True


def test_notes_alone_do_not_set_warned() -> None:
    """A note is recorded in full but must not change the exit status."""
    result = ParseResult(
        conversation=conversation(),
        findings=[finding("message_has_no_content", "no content blocks", "m1")],
    )

    assert result.findings[0].level is Level.NOTE
    assert result.warned is False


def test_parse_error_preserves_findings_collected_before_failure() -> None:
    item = finding("unrecognised_stream_line", "line ignored")
    error = ParseError("no conversation node", findings=[item])

    assert error.findings == [item]
    assert isinstance(error, ConvolvgerError)


def test_parse_error_findings_default_to_empty() -> None:
    assert ParseError("boom").findings == []


def test_parse_error_findings_are_copied_not_aliased() -> None:
    collected = [finding("unrecognised_stream_line", "first")]
    error = ParseError("boom", findings=collected)
    collected.append(finding("unrecognised_stream_line", "second"))

    assert len(error.findings) == 1


def test_parse_error_is_raisable_and_catchable_as_base() -> None:
    with pytest.raises(ConvolvgerError, match="bad source"):
        raise ParseError("bad source")
