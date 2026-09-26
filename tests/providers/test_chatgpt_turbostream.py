import json
from itertools import pairwise
from pathlib import Path
from typing import Any

import pytest

from convolvger.providers.chatgpt._turbostream import (
    TurboStreamError,
    decode,
    decode_html,
    extract_payloads,
    parse_stream,
)

FIXTURES = Path(__file__).parent.parent / "fixtures" / "chatgpt"
LOCAL = Path(__file__).parent.parent / "fixtures" / "local" / "chatgpt"


@pytest.fixture
def flat_minimal() -> list[Any]:
    flat: list[Any] = json.loads(
        (FIXTURES / "flat-minimal.json").read_text(encoding="utf-8")
    )
    return flat


def test_decodes_conversation_structure(flat_minimal: list[Any]) -> None:
    conversation = decode(flat_minimal).value["conversation"]

    assert conversation["title"] == "Synthetic Conversation"
    assert conversation["current_node"] == "node-assistant"
    assert len(conversation["linear_conversation"]) == 4


def test_root_node_has_no_message(flat_minimal: list[Any]) -> None:
    root = decode(flat_minimal).value["conversation"]["linear_conversation"][0]

    assert root["id"] == "node-root"
    assert "message" not in root


def test_hidden_system_node_is_decoded_with_user_role(flat_minimal: list[Any]) -> None:
    """The hidden node claims role 'user'; only metadata reveals otherwise."""
    node = decode(flat_minimal).value["conversation"]["linear_conversation"][1]
    message = node["message"]

    assert message["author"]["role"] == "user"
    assert message["metadata"]["is_visually_hidden_from_conversation"] is True
    assert message["metadata"]["is_user_system_message"] is True


def test_null_sentinel_becomes_none(flat_minimal: list[Any]) -> None:
    node = decode(flat_minimal).value["conversation"]["linear_conversation"][1]

    assert node["message"]["metadata"]["user_context_message_data"] is None


def test_deduplicated_values_are_shared(flat_minimal: list[Any]) -> None:
    nodes = decode(flat_minimal).value["conversation"]["linear_conversation"]

    assert all(node["message"]["create_time"] == 1789000000.5 for node in nodes[1:])


def test_message_content_and_roles(flat_minimal: list[Any]) -> None:
    nodes = decode(flat_minimal).value["conversation"]["linear_conversation"]
    user, assistant = nodes[2]["message"], nodes[3]["message"]

    assert user["author"]["role"] == "user"
    assert user["content"]["parts"] == [
        "Is breakfast the most important meal of the day?"
    ]
    assert assistant["author"]["role"] == "assistant"
    assert assistant["metadata"]["model_slug"] == "synthetic-model"


def test_graph_links_are_consistent(flat_minimal: list[Any]) -> None:
    nodes = decode(flat_minimal).value["conversation"]["linear_conversation"]

    for parent, child in pairwise(nodes):
        assert child["parent"] == parent["id"]
        assert parent["children"] == [child["id"]]
    assert nodes[-1]["children"] == []


def test_decode_is_deterministic(flat_minimal: list[Any]) -> None:
    first = decode(flat_minimal).value
    second = decode(flat_minimal).value

    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_string_list_is_not_treated_as_deferred_marker() -> None:
    """A list of references must not be confused with a ['P', n] marker."""
    flat = [{"_1": 2}, "tags", [3, 4], "P", "second"]

    assert decode(flat).value == {"tags": ["P", "second"]}


def test_deferred_marker_resolves_to_none_with_warning() -> None:
    flat = [{"_1": 2}, "pending", ["P", 3], 99]
    result = decode(flat)

    assert result.value == {"pending": None}
    assert any(item.code == "deferred_value_unresolved" for item in result.findings)


def test_unknown_sentinel_raises() -> None:
    with pytest.raises(TurboStreamError, match="sentinel"):
        decode([{"_1": -99}, "key"])


def test_out_of_range_reference_raises() -> None:
    with pytest.raises(TurboStreamError, match="out of range"):
        decode([{"_1": 500}, "key"])


def test_reference_cycle_raises() -> None:
    with pytest.raises(TurboStreamError, match="cycle"):
        decode([{"_1": 2}, "self", {"_1": 0}])


def test_empty_flat_array_raises() -> None:
    with pytest.raises(TurboStreamError, match="empty"):
        decode([])


def test_extracts_and_decodes_html_snapshot() -> None:
    html = (FIXTURES / "snapshot-tiny.html").read_text(encoding="utf-8")
    result = decode_html(html)

    assert result.value == {"pending": None, "ready": "yes"}
    assert len(result.findings) == 2


def test_extract_payloads_finds_all_chunks() -> None:
    html = (FIXTURES / "snapshot-tiny.html").read_text(encoding="utf-8")

    assert len(extract_payloads(html)) == 2


def test_missing_payload_raises() -> None:
    with pytest.raises(TurboStreamError, match="No turbo-stream payload"):
        extract_payloads("<html><body>nothing here</body></html>")


def test_deferred_lines_are_reported_as_findings() -> None:
    _, findings = parse_stream(['[{"_1":2},"a","b"]\n', "P7:[{}]\n"])

    assert [item.code for item in findings] == ["deferred_slot_not_merged"]
    assert any("slot 7" in item.message for item in findings)


def test_non_json_leading_line_raises() -> None:
    with pytest.raises(TurboStreamError, match="not JSON"):
        parse_stream(["not json at all\n"])


def test_non_list_payload_raises() -> None:
    with pytest.raises(TurboStreamError, match="flat array"):
        parse_stream(['{"a": 1}\n'])


@pytest.mark.skipif(
    not (LOCAL / "minimal-2026-09-11.html").exists(),
    reason="local capture not present (see tests/fixtures/local/)",
)
def test_real_capture_decodes() -> None:
    html = (LOCAL / "minimal-2026-09-11.html").read_text(encoding="utf-8")
    result = decode_html(html)

    assert "loaderData" in result.value


def test_non_standard_json_constants_are_warned_and_nulled() -> None:
    """NaN and Infinity are not valid JSON and must never pass silently."""
    flat, findings = parse_stream(['[{"_1":2},"value",NaN]\n'])

    assert flat == [{"_1": 2}, "value", None]
    assert [item.code for item in findings] == ["non_standard_json_constant"]
    assert any("NaN" in item.message for item in findings)


def test_repeated_constants_warn_once_per_token() -> None:
    _, findings = parse_stream(["[NaN, NaN, Infinity]\n"])

    assert len(findings) == 2
    assert len([item for item in findings if "NaN" in item.message]) == 1
    assert any("Infinity" in item.message for item in findings)
