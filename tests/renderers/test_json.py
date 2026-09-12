from datetime import UTC, datetime

from convolvger.core.archive import ArchiveEnvelope
from convolvger.core.findings import finding
from convolvger.core.models import (
    Conversation,
    Message,
    MessageRole,
    TextBlock,
    UnknownBlock,
)
from convolvger.renderers import render_json

RETRIEVED = datetime(2026, 9, 12, 9, 14, 22, tzinfo=UTC)


def conversation() -> Conversation:
    """A conversation holding everything Markdown is allowed to drop."""
    return Conversation(
        provider="chatgpt",
        source_url="https://chatgpt.com/share/x",
        title="A Test Chat",
        messages=[
            Message(id="m1", role=MessageRole.USER, content=[TextBlock(text="hello")]),
            Message(
                id="m2",
                role=MessageRole.SYSTEM,
                visible=False,
                content=[TextBlock(text="hidden")],
                provider_metadata={"channel": "final"},
            ),
            Message(id="m3", role=MessageRole.ASSISTANT, active=False),
            Message(
                id="m4",
                role=MessageRole.TOOL,
                content=[UnknownBlock(type="text", text="not a TextBlock")],
            ),
        ],
    )


def test_every_message_survives_the_export() -> None:
    """Hidden, deactivated and empty messages all belong in the archive."""
    restored = ArchiveEnvelope.model_validate_json(render_json(conversation()))

    assert [m.id for m in restored.conversation.messages] == ["m1", "m2", "m3", "m4"]
    assert restored.conversation == conversation()


def test_unknown_blocks_keep_their_type_through_a_round_trip() -> None:
    restored = ArchiveEnvelope.model_validate_json(render_json(conversation()))

    assert isinstance(restored.conversation.messages[3].content[0], UnknownBlock)


def test_empty_raw_is_written_so_unknown_blocks_cannot_collapse() -> None:
    """Omitting an empty raw would let this block reload as a TextBlock."""
    assert '"raw": {}' in render_json(conversation())


def test_findings_and_retrieval_time_are_recorded() -> None:
    restored = ArchiveEnvelope.model_validate_json(
        render_json(
            conversation(),
            findings=[finding("unrecognised_role", "skipped")],
            fetched_at=RETRIEVED,
        )
    )

    assert [item.code for item in restored.findings] == ["unrecognised_role"]
    assert restored.retrieved_at == RETRIEVED


def test_retrieval_time_stays_null_when_unknown() -> None:
    restored = ArchiveEnvelope.model_validate_json(render_json(conversation()))

    assert restored.retrieved_at is None


def test_render_is_deterministic() -> None:
    assert render_json(conversation()) == render_json(conversation())


def test_output_ends_with_a_single_newline() -> None:
    output = render_json(conversation())

    assert output.endswith("\n")
    assert not output.endswith("\n\n")
