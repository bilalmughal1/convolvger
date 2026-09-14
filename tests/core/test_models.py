from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from convolvger.core.models import (
    Conversation,
    Message,
    MessageRole,
    TextBlock,
)


def test_conversation_can_be_created() -> None:
    conversation = Conversation(
        id="conv-1",
        provider="chatgpt",
        source_url="https://chatgpt.com/share/example",
        title="Test conversation",
        messages=[
            Message(
                id="msg-1",
                role=MessageRole.USER,
                timestamp=datetime(2026, 1, 1, tzinfo=UTC),
                content=[TextBlock(text="Hello")],
            ),
            Message(
                id="msg-2",
                role=MessageRole.ASSISTANT,
                content=[TextBlock(text="Hello! How can I help?")],
            ),
        ],
    )

    assert conversation.provider == "chatgpt"
    assert len(conversation.messages) == 2
    assert conversation.messages[0].role == MessageRole.USER
    block = conversation.messages[1].content[0]
    assert isinstance(block, TextBlock)
    assert block.text == "Hello! How can I help?"


def test_a_conversation_preserves_unmodelled_envelope_fields() -> None:
    extras: dict[str, Any] = {
        "conversation_uuid": "c-1",
        "up_to_date": True,
        "creator": {"full_name": "A Name", "uuid": "u-1"},
    }
    conversation = Conversation(
        provider="claude",
        source_url="https://claude.ai/share/x",
        provider_metadata=extras,
    )

    assert conversation.provider_metadata == extras


def test_conversation_provider_metadata_survives_json_round_trip() -> None:
    conversation = Conversation(
        provider="claude",
        source_url="https://claude.ai/share/x",
        provider_metadata={"up_to_date": False, "is_public": True},
        messages=[Message(role=MessageRole.USER, content=[TextBlock(text="hi")])],
    )

    restored = Conversation.model_validate_json(conversation.model_dump_json())

    assert restored == conversation


def test_an_unknown_conversation_field_is_still_rejected() -> None:
    """extra='forbid' stays in force; unmodelled data goes in provider_metadata."""
    with pytest.raises(ValidationError):
        Conversation.model_validate(
            {"provider": "claude", "source_url": "u", "up_to_date": True}
        )
