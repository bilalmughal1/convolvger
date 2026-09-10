from datetime import UTC, datetime

from convolvger.core.models import (
    ContentBlock,
    Conversation,
    Message,
    MessageRole,
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
                content=[
                    ContentBlock(
                        type="text",
                        content="Hello",
                    )
                ],
            ),
            Message(
                id="msg-2",
                role=MessageRole.ASSISTANT,
                content=[
                    ContentBlock(
                        type="text",
                        content="Hello! How can I help?",
                    )
                ],
            ),
        ],
    )

    assert conversation.provider == "chatgpt"
    assert len(conversation.messages) == 2
    assert conversation.messages[0].role == MessageRole.USER
    assert conversation.messages[1].content[0].content == "Hello! How can I help?"
