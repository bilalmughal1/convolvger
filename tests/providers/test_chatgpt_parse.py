import json
from pathlib import Path
from typing import Any

import pytest

from convolvger.core.models import MessageRole
from convolvger.core.results import ParseError
from convolvger.core.source import RawSource
from convolvger.providers.chatgpt._parse import parse

LOCAL = Path(__file__).parent.parent / "fixtures" / "local" / "chatgpt"
URL = "https://chatgpt.com/share/6aa3f5a2-00a4-83eb-8d18-3b2266aac2e6"


def snapshot(payload: dict[str, Any]) -> RawSource:
    """Wrap a share payload in the minimal turbo-stream HTML envelope."""
    flat = [
        {"_1": 2},
        "loaderData",
        {"_3": 4},
        "routes/share.$shareId.($action)",
        {"_5": 6},
        "serverResponse",
        {"_7": 8},
        "data",
        payload,
    ]
    escaped = json.dumps(json.dumps(flat) + "\n")
    html = f"<html><script>streamController.enqueue({escaped})</script></html>"
    return RawSource(url=URL, content=html)


def node(**message: Any) -> dict[str, Any]:
    return {"id": message.get("id", "n"), "message": message}


def test_walks_nodes_into_messages() -> None:
    source = snapshot(
        {
            "title": "T",
            "linear_conversation": [
                {"id": "root", "children": ["a"]},
                node(id="a", author={"role": "user"}, content={
                    "content_type": "text", "parts": ["hi"]
                }),
            ],
        }
    )

    conversation = parse(source).conversation

    assert conversation.title == "T"
    assert conversation.provider == "chatgpt"
    assert conversation.source_url == URL
    assert len(conversation.messages) == 1


def test_root_node_without_message_is_skipped() -> None:
    source = snapshot(
        {
            "linear_conversation": [
                {"id": "root", "children": []},
                node(id="a", author={"role": "user"}, content={
                    "content_type": "text", "parts": ["hi"]
                }),
            ]
        }
    )

    assert [m.id for m in parse(source).conversation.messages] == ["a"]


def test_create_time_becomes_timezone_aware_timestamp() -> None:
    source = snapshot(
        {
            "linear_conversation": [
                node(
                    id="a",
                    author={"role": "user"},
                    create_time=1789025128.637383,
                    content={"content_type": "text", "parts": ["hi"]},
                )
            ]
        }
    )

    timestamp = parse(source).conversation.messages[0].timestamp

    assert timestamp is not None
    assert timestamp.tzinfo is not None
    assert timestamp.year == 2026


def test_hidden_metadata_sets_visible_false() -> None:
    source = snapshot(
        {
            "linear_conversation": [
                node(
                    id="a",
                    author={"role": "user"},
                    content={"content_type": "text", "parts": ["x"]},
                    metadata={"is_visually_hidden_from_conversation": True},
                )
            ]
        }
    )

    assert parse(source).conversation.messages[0].visible is False


@pytest.mark.parametrize(
    ("weight", "expected"),
    [(1, True), (1.0, True), (0, False), (0.0, False)],
)
def test_weight_maps_to_active(weight: float, expected: bool) -> None:
    source = snapshot(
        {
            "linear_conversation": [
                node(
                    id="a",
                    author={"role": "user"},
                    weight=weight,
                    content={"content_type": "text", "parts": ["x"]},
                )
            ]
        }
    )

    assert parse(source).conversation.messages[0].active is expected


def test_unexpected_weight_warns_and_stays_active() -> None:
    source = snapshot(
        {
            "linear_conversation": [
                node(
                    id="a",
                    author={"role": "user"},
                    weight=0.5,
                    content={"content_type": "text", "parts": ["x"]},
                )
            ]
        }
    )
    result = parse(source)

    assert result.conversation.messages[0].active is True
    assert any("weight" in warning for warning in result.warnings)


def test_unrecognised_role_becomes_unknown_with_warning() -> None:
    source = snapshot(
        {
            "linear_conversation": [
                node(id="a", author={"role": "oracle"}, content={
                    "content_type": "text", "parts": ["x"]
                })
            ]
        }
    )
    result = parse(source)

    assert result.conversation.messages[0].role is MessageRole.UNKNOWN
    assert any("oracle" in warning for warning in result.warnings)


def test_author_name_and_recipient_are_carried() -> None:
    source = snapshot(
        {
            "linear_conversation": [
                node(
                    id="a",
                    author={"role": "tool", "name": "web.run"},
                    recipient="all",
                    status="finished_successfully",
                    content={"content_type": "text", "parts": ["x"]},
                )
            ]
        }
    )
    message = parse(source).conversation.messages[0]

    assert message.author == "web.run"
    assert message.recipient == "all"
    assert message.status == "finished_successfully"


def test_channel_and_end_turn_go_to_provider_metadata() -> None:
    source = snapshot(
        {
            "linear_conversation": [
                node(
                    id="a",
                    author={"role": "assistant"},
                    channel="final",
                    end_turn=True,
                    content={"content_type": "text", "parts": ["x"]},
                )
            ]
        }
    )

    assert parse(source).conversation.messages[0].provider_metadata == {
        "channel": "final",
        "end_turn": True,
    }


def test_empty_content_is_warned_not_silently_dropped() -> None:
    source = snapshot(
        {
            "linear_conversation": [
                node(id="a", author={"role": "user"}, content={
                    "content_type": "text", "parts": [""]
                })
            ]
        }
    )
    result = parse(source)

    assert result.conversation.messages[0].content == []
    assert any("no content blocks" in warning for warning in result.warnings)


def test_missing_payload_raises_parse_error() -> None:
    flat = [{"_1": 2}, "loaderData", {}]
    escaped = json.dumps(json.dumps(flat) + "\n")
    html = f"<html><script>streamController.enqueue({escaped})</script></html>"

    with pytest.raises(ParseError, match="no shared conversation"):
        parse(RawSource(url=URL, content=html))


def test_missing_linear_conversation_raises() -> None:
    with pytest.raises(ParseError, match="linear_conversation"):
        parse(snapshot({"title": "T"}))


def test_no_messages_raises_parse_error() -> None:
    with pytest.raises(ParseError, match="no messages"):
        parse(snapshot({"linear_conversation": [{"id": "root", "children": []}]}))


@pytest.mark.skipif(
    not (LOCAL / "minimal.html").exists(),
    reason="local capture not present (see tests/fixtures/local/)",
)
def test_real_capture_parses_completely() -> None:
    html = (LOCAL / "minimal.html").read_text(encoding="utf-8")
    result = parse(RawSource(url=URL, content=html))
    conversation = result.conversation

    assert len(conversation.messages) == 31
    assert sum(m.visible for m in conversation.messages) == 20
    assert sum(m.active for m in conversation.messages) == 27
    assert {m.role for m in conversation.messages} == {
        MessageRole.USER,
        MessageRole.ASSISTANT,
        MessageRole.SYSTEM,
        MessageRole.TOOL,
    }
