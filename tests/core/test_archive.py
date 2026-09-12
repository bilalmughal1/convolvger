import json
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError

import pytest

from convolvger.core.archive import SCHEMA_VERSION, ArchiveEnvelope
from convolvger.core.models import (
    Conversation,
    Message,
    MessageRole,
    TextBlock,
    UnknownBlock,
)

RETRIEVED = datetime(2026, 9, 12, 9, 14, 22, tzinfo=UTC)


def conversation() -> Conversation:
    """A conversation carrying every shape the canonical model allows."""
    return Conversation(
        id="conv-1",
        provider="chatgpt",
        source_url="https://chatgpt.com/share/x",
        title="Tast - unicode and dashes",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        messages=[
            Message(id="m1", role=MessageRole.USER, content=[TextBlock(text="hi")]),
            Message(
                id="m2",
                role=MessageRole.SYSTEM,
                visible=False,
                content=[TextBlock(text="hidden")],
                provider_metadata={"channel": "final", "end_turn": True},
            ),
            Message(id="m3", role=MessageRole.ASSISTANT, active=False),
            Message(
                id="m4",
                role=MessageRole.TOOL,
                author="web.run",
                content=[UnknownBlock(type="thoughts", raw={"b": 2, "a": [1, None]})],
            ),
        ],
    )


def envelope() -> ArchiveEnvelope:
    return ArchiveEnvelope(
        retrieved_at=RETRIEVED,
        warnings=["something was skipped"],
        conversation=conversation(),
    )


def test_conversation_round_trips_unchanged() -> None:
    restored = ArchiveEnvelope.model_validate_json(envelope().model_dump_json())

    assert restored.conversation == conversation()


def test_envelope_round_trips_unchanged() -> None:
    original = envelope()

    assert ArchiveEnvelope.model_validate_json(original.model_dump_json()) == original


def test_unknown_block_does_not_reload_as_a_known_block() -> None:
    """The left_to_right union must still prefer UnknownBlock on reload."""
    original = ArchiveEnvelope(
        conversation=Conversation(
            provider="chatgpt",
            source_url="https://chatgpt.com/share/x",
            messages=[
                Message(
                    role=MessageRole.ASSISTANT,
                    content=[UnknownBlock(type="text", text="looks like a TextBlock")],
                )
            ],
        )
    )

    restored = ArchiveEnvelope.model_validate_json(original.model_dump_json())

    assert isinstance(restored.conversation.messages[0].content[0], UnknownBlock)
    assert restored == original


def test_serialisation_is_byte_stable() -> None:
    original = envelope()
    restored = ArchiveEnvelope.model_validate_json(original.model_dump_json())

    assert original.model_dump_json() == original.model_dump_json()
    assert restored.model_dump_json() == original.model_dump_json()


def test_warnings_sit_beside_the_conversation_not_inside_it() -> None:
    dumped = envelope().model_dump()

    assert dumped["warnings"] == ["something was skipped"]
    assert "warnings" not in dumped["conversation"]


def test_retrieval_time_stays_null_when_none_was_recorded() -> None:
    """Never invent provenance: an unknown retrieval time stays unknown."""
    original = ArchiveEnvelope(conversation=conversation())

    assert original.retrieved_at is None
    assert ArchiveEnvelope.model_validate_json(original.model_dump_json()) == original


def test_schema_version_is_recorded() -> None:
    assert ArchiveEnvelope(conversation=conversation()).schema_version == SCHEMA_VERSION


def test_tool_version_falls_back_when_not_installed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def missing(name: str) -> str:
        raise PackageNotFoundError(name)

    monkeypatch.setattr("convolvger.core.archive.version", missing)

    assert ArchiveEnvelope(conversation=conversation()).tool_version == "unknown"


def test_fields_from_a_newer_writer_survive_a_round_trip() -> None:
    """An archive is permanent, so a later version may add fields this
    one does not model. Reading such a file must not quietly drop them.
    """
    payload = json.loads(ArchiveEnvelope(conversation=conversation()).model_dump_json())
    payload["schema_version"] = SCHEMA_VERSION + 1
    payload["digest"] = {"algorithm": "sha256", "value": "abc"}

    restored = ArchiveEnvelope.model_validate(payload)

    assert restored.model_extra == {"digest": {"algorithm": "sha256", "value": "abc"}}
    assert "digest" in restored.model_dump_json()


def test_a_freshly_rendered_envelope_carries_no_extra_fields() -> None:
    """The cost of extra='allow': a mistyped kwarg would land here."""
    assert ArchiveEnvelope(conversation=conversation()).model_extra == {}
