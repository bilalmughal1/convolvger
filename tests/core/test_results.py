import pytest

from convolvger.core.errors import ConvolvgerError
from convolvger.core.models import Conversation, Message, MessageRole, TextBlock
from convolvger.core.results import ParseError, ParseResult


def conversation() -> Conversation:
    return Conversation(
        provider="chatgpt",
        source_url="https://chatgpt.com/share/x",
        messages=[Message(role=MessageRole.USER, content=[TextBlock(text="hi")])],
    )


def test_result_defaults_to_no_warnings() -> None:
    result = ParseResult(conversation=conversation())

    assert result.warnings == []


def test_result_carries_warnings() -> None:
    result = ParseResult(conversation=conversation(), warnings=["unknown role: bot"])

    assert result.warnings == ["unknown role: bot"]


def test_warnings_are_not_stored_on_the_conversation() -> None:
    """Warnings are extraction metadata and must stay outside the model."""
    result = ParseResult(conversation=conversation(), warnings=["something"])

    assert "warnings" not in result.conversation.model_dump()


def test_parse_error_preserves_warnings_collected_before_failure() -> None:
    error = ParseError("no conversation node", warnings=["skipped node 3"])

    assert error.warnings == ["skipped node 3"]
    assert isinstance(error, ConvolvgerError)


def test_parse_error_warnings_default_to_empty() -> None:
    assert ParseError("boom").warnings == []


def test_parse_error_warnings_are_copied_not_aliased() -> None:
    collected = ["first"]
    error = ParseError("boom", warnings=collected)
    collected.append("second")

    assert error.warnings == ["first"]


def test_parse_error_is_raisable_and_catchable_as_base() -> None:
    with pytest.raises(ConvolvgerError, match="bad source"):
        raise ParseError("bad source")
