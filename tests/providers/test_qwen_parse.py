import copy
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from convolvger.core.models import Message, MessageRole, TextBlock
from convolvger.core.results import ParseError
from convolvger.core.source import RawSource
from convolvger.providers.qwen import _parse
from convolvger.renderers import render_json, render_markdown

FIXTURE = Path(__file__).parent.parent / "fixtures" / "qwen" / "share-minimal.json"
SHARE_URL = "https://chat.qwen.ai/s/00000000-0000-4000-8000-000000000001"


def source(payload: object) -> RawSource:
    return RawSource(url=SHARE_URL, content=json.dumps(payload))


def text_of(message: Message) -> str:
    block = message.content[0]
    assert isinstance(block, TextBlock)
    return block.text


@pytest.fixture
def minimal() -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return loaded


def tree(payload: dict[str, Any]) -> dict[str, Any]:
    nodes: dict[str, Any] = payload["data"]["chat"]["history"]["messages"]
    return nodes


def node(payload: dict[str, Any], position: int) -> dict[str, Any]:
    """The node at ``position`` on the current path, in tree and flat list alike."""
    identifier = payload["data"]["chat"]["messages"][position]["id"]
    found: dict[str, Any] = tree(payload)[identifier]
    return found


def edit(payload: dict[str, Any], position: int, **changes: Any) -> None:
    """Change a node in the tree and its flat copy together, as the provider serves them."""
    node(payload, position).update(changes)
    payload["data"]["chat"]["messages"][position].update(changes)


def without_thinking(payload: dict[str, Any]) -> dict[str, Any]:
    """The fixture minus its thinking summaries, which are flagged by design."""
    for position, flat in enumerate(payload["data"]["chat"]["messages"]):
        if "content_list" in flat:
            parts = [
                p for p in flat["content_list"] if p["phase"] != "thinking_summary"
            ]
            edit(payload, position, content_list=parts)
    return payload


def messages_of(payload: dict[str, Any]) -> list[Message]:
    return _parse.parse(source(payload)).conversation.messages


def test_maps_the_envelope_onto_a_conversation(minimal: dict[str, Any]) -> None:
    conversation = _parse.parse(source(minimal)).conversation
    assert conversation.provider == "qwen"
    assert conversation.title == "Example Qwen conversation"
    assert conversation.id == "00000000-0000-4000-8000-000000000001"
    assert conversation.created_at == datetime.fromtimestamp(1767261600, tz=UTC)


def test_messages_follow_the_tree_with_text_from_the_answer_part(
    minimal: dict[str, Any],
) -> None:
    messages = messages_of(minimal)
    assert [m.role for m in messages] == [
        MessageRole.USER,
        MessageRole.ASSISTANT,
        MessageRole.USER,
        MessageRole.ASSISTANT,
    ]
    assert text_of(messages[0]) == "How does a kettle work?"
    assert text_of(messages[3]) == "A thermostat switches it off."
    assert all(message.active for message in messages)


def test_citations_are_numbered_across_every_search_in_the_message(
    minimal: dict[str, Any],
) -> None:
    """[[3]] is the first result of the second search, which had one."""
    answer = text_of(messages_of(minimal)[1])
    assert answer.startswith("Kettles heat water with an element.\n\n")
    assert "[[3]]" not in answer.split("```")[0]


def test_a_nested_list_inside_code_is_never_taken_for_a_citation(
    minimal: dict[str, Any],
) -> None:
    assert "x = [[1]]" in text_of(messages_of(minimal)[1])


def test_the_served_answer_is_kept_whenever_citations_are_lifted(
    minimal: dict[str, Any],
) -> None:
    message = messages_of(minimal)[1]
    answer = message.provider_metadata["part_extras"]["3"]
    assert answer["content"] == node(minimal, 1)["content_list"][3]["content"]
    untouched = messages_of(minimal)[3].provider_metadata["part_extras"]["1"]
    assert "content" not in untouched


def test_a_citation_beyond_the_results_is_left_and_reported(
    minimal: dict[str, Any],
) -> None:
    parts = copy.deepcopy(node(minimal, 1)["content_list"])
    parts[3]["content"] += " More.[[4]]"
    edit(minimal, 1, content_list=parts)
    result = _parse.parse(source(without_thinking(minimal)))
    assert text_of(result.conversation.messages[1]).endswith("More.[[4]]")
    assert [f.message for f in result.findings] == [
        "[[4]] names no search result, preserved in text"
    ]


def test_thinking_summaries_are_kept_and_flagged(minimal: dict[str, Any]) -> None:
    result = _parse.parse(source(minimal))
    assert [(f.code, f.message, f.message_id) for f in result.findings] == [
        (
            "unmodelled_content_type",
            "thinking_summary part preserved in provider_metadata",
            message.id,
        )
        for message in result.conversation.messages
        if message.role is MessageRole.ASSISTANT
    ]
    kept = result.conversation.messages[1].provider_metadata["part_extras"]["0"]
    assert kept["extra"]["summary_title"]["content"] == ["Planning the answer"]


def test_search_results_and_the_sharer_stay_out_of_the_document(
    minimal: dict[str, Any],
) -> None:
    result = _parse.parse(source(minimal))
    conversation = result.conversation
    assert conversation.provider_metadata["user_id"].startswith("shared-")
    document = render_markdown(conversation, findings=result.findings)
    for leaked in ("shared-", "example.com/source", "Invented summary"):
        assert leaked not in document
    archive = render_json(conversation, findings=result.findings)
    assert "example.com/source" in archive
    assert "Invented summary" in archive


def test_a_regenerated_answer_off_the_current_path_is_kept_inactive(
    minimal: dict[str, Any],
) -> None:
    """Synthetic: the one capture had no branches."""
    payload = without_thinking(minimal)
    first_user = node(payload, 0)
    original = copy.deepcopy(node(payload, 1))
    alternative = {**original, "id": "alt", "childrenIds": []}
    alternative["content_list"] = [
        {**original["content_list"][-1], "content": "An earlier answer."}
    ]
    first_user["childrenIds"] = ["alt", original["id"]]
    payload["data"]["chat"]["messages"][0]["childrenIds"] = ["alt", original["id"]]
    tree(payload)["alt"] = alternative

    messages = messages_of(payload)
    assert [(m.id, m.active) for m in messages][:3] == [
        (first_user["id"], True),
        ("alt", False),
        (original["id"], True),
    ]
    assert len(messages) == 5


def test_a_flat_list_that_disagrees_with_the_tree_is_kept_and_reported(
    minimal: dict[str, Any],
) -> None:
    payload = without_thinking(minimal)
    payload["data"]["chat"]["messages"][0]["content"] = "a different question"
    result = _parse.parse(source(payload))
    assert [f.message for f in result.findings] == [
        "flat message list disagrees with the tree, preserved in provider_metadata"
    ]
    assert result.conversation.provider_metadata["chat"]["messages"][0]["content"] == (
        "a different question"
    )


def test_a_flat_list_in_step_with_the_tree_is_passed_over(
    minimal: dict[str, Any],
) -> None:
    metadata = _parse.parse(
        source(without_thinking(minimal))
    ).conversation.provider_metadata
    assert "messages" not in metadata["chat"]


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"error": {"code": "x"}}, "the provider recorded an error"),
        ({"done": False}, "marked not done"),
        ({"is_stop": True}, "stopped before finishing"),
    ],
)
def test_an_unfinished_answer_is_reported(
    minimal: dict[str, Any], changes: dict[str, Any], message: str
) -> None:
    payload = without_thinking(minimal)
    edit(payload, 3, **changes)
    assert [(f.code, f.message) for f in _parse.parse(source(payload)).findings] == [
        ("message_content_withheld", message)
    ]


def test_files_declared_but_not_carried_are_reported(minimal: dict[str, Any]) -> None:
    payload = without_thinking(minimal)
    edit(payload, 0, files=[{"id": "f1"}])
    assert [(f.code, f.message) for f in _parse.parse(source(payload)).findings] == [
        ("attachment_withheld", "1 files declared, none carried")
    ]


def test_an_unknown_role_is_recorded_not_guessed(minimal: dict[str, Any]) -> None:
    payload = without_thinking(minimal)
    edit(payload, 0, role="system")
    result = _parse.parse(source(payload))
    assert result.conversation.messages[0].role is MessageRole.UNKNOWN
    assert result.conversation.messages[0].provider_metadata["role"] == "system"


def test_a_missing_share_is_refused_with_the_provider_s_words() -> None:
    payload = {
        "success": False,
        "request_id": "r",
        "data": {"code": "Not_Found", "details": "This conversation has been deleted."},
    }
    with pytest.raises(ParseError, match="has been deleted"):
        _parse.parse(source(payload))


@pytest.mark.parametrize(
    "content", ["not json", "[]", json.dumps({"detail": "Not Found"})]
)
def test_a_payload_that_is_not_a_share_is_refused(content: str) -> None:
    with pytest.raises(ParseError):
        _parse.parse(RawSource(url=SHARE_URL, content=content))


def test_a_served_empty_answer_is_kept(minimal: dict[str, Any]) -> None:
    """No text block holds "", so it is not mapped and must not vanish."""
    payload = without_thinking(minimal)
    parts = copy.deepcopy(node(payload, 3)["content_list"])
    parts[0]["content"] = ""
    edit(payload, 3, content_list=parts)
    result = _parse.parse(source(payload))
    extras = result.conversation.messages[3].provider_metadata["part_extras"]
    assert extras["0"]["content"] == ""
    assert [f.code for f in result.findings] == ["message_has_no_content"]
