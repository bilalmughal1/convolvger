from typing import Any

import pytest
from pydantic import ValidationError

from convolvger.core.models import Message, MessageRole, TextBlock


def test_defaults_describe_an_ordinary_visible_turn() -> None:
    message = Message(role=MessageRole.USER, content=[TextBlock(text="hi")])

    assert message.visible is True
    assert message.active is True
    assert message.status is None
    assert message.recipient is None
    assert message.provider_metadata == {}


def test_hidden_system_turn_is_representable() -> None:
    """A hidden node claims role 'user' in the source; visible carries the truth."""
    message = Message(
        role=MessageRole.SYSTEM,
        visible=False,
        content=[TextBlock(text="Original custom instructions no longer available")],
    )

    assert message.visible is False
    assert message.active is True


def test_deactivated_branch_is_representable() -> None:
    message = Message(role=MessageRole.ASSISTANT, active=False)

    assert message.active is False


def test_tool_turn_carries_author_and_recipient() -> None:
    message = Message(
        role=MessageRole.TOOL,
        author="web.run",
        recipient="all",
        status="finished_successfully",
    )

    assert message.author == "web.run"
    assert message.recipient == "all"


def test_provider_metadata_preserves_unmodelled_fields() -> None:
    extras: dict[str, Any] = {"channel": "final", "end_turn": True}
    message = Message(role=MessageRole.ASSISTANT, provider_metadata=extras)

    assert message.provider_metadata == extras


def test_provider_metadata_survives_json_round_trip() -> None:
    message = Message(
        role=MessageRole.ASSISTANT,
        visible=False,
        active=False,
        status="finished_successfully",
        recipient="web",
        provider_metadata={"channel": "final", "end_turn": False},
        content=[TextBlock(text="hello")],
    )

    restored = Message.model_validate_json(message.model_dump_json())

    assert restored == message


def test_unknown_top_level_field_is_still_rejected() -> None:
    """extra='forbid' stays in force; unmodelled data goes in provider_metadata."""
    with pytest.raises(ValidationError):
        Message.model_validate({"role": "user", "end_turn": True})
