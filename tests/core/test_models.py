from datetime import UTC, datetime

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
