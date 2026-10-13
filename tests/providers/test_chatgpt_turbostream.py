import json
from itertools import pairwise
from pathlib import Path
from typing import Any

import pytest

from convolvger.providers import _http
from convolvger.providers.chatgpt._turbostream import (
    TurboStreamError,
    decode,
    decode_html,
    extract_payloads,
    parse_stream,
    unfolded_size,
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


@pytest.mark.parametrize("key", ["_x", "_", "_ 1", "_1_0", "_-5"])
def test_a_key_that_is_not_an_index_reference_raises(key: str) -> None:
    """``int()`` would accept some of these and choke on others; none is an index."""
    with pytest.raises(TurboStreamError, match="Malformed key reference"):
        decode([{key: 1}, "value"])


def test_a_reference_chain_deeper_than_the_stack_raises() -> None:
    chain: list[Any] = [[index + 1] for index in range(5000)]
    with pytest.raises(TurboStreamError, match="nested too deeply"):
        decode([*chain, "end"])


def test_a_leading_line_nested_100k_deep_raises_a_decoder_error() -> None:
    """Which error depends on the stack, never whether it is this one.

    Python 3.14 bounds recursion in C by the stack actually available:
    with ``ulimit -s unlimited`` it reads all 100,000 levels and reports
    the unclosed array, where 3.12, 3.13 and 3.14 on an 8 MiB stack run
    out of stack first.
    """
    with pytest.raises(TurboStreamError):
        parse_stream(["[" * 100_000 + "\n"])


def test_a_leading_line_that_exhausts_the_stack_raises_a_decoder_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def exhausted(*args: object, **kwargs: object) -> object:
        raise RecursionError("maximum recursion depth exceeded")

    monkeypatch.setattr(json, "loads", exhausted)
    with pytest.raises(TurboStreamError, match="nested too deeply"):
        parse_stream(["[1]\n"])


def _doubling(levels: int, leaf: str) -> list[Any]:
    """A flat array of ``levels`` lists, each referencing the next one twice."""
    return [[index + 1, index + 1] for index in range(levels)] + [leaf]


def test_unfolded_size_is_the_size_of_the_payload_written_compactly() -> None:
    shared = ["\u00e9t\u00e9", None, True, 1.5]
    value = {"a": [shared, shared], "b": {"c": -3, "\u65e5": "\U0001f600"}, "d": []}
    written = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    assert unfolded_size(value) == len(written.encode("utf-8"))


def test_a_lone_surrogate_is_counted_as_its_replacement_will_be() -> None:
    """It is replaced with U+FFFD after decoding, which also takes 3 bytes."""
    assert unfolded_size("\ud83d") == unfolded_size("\ufffd")


def test_a_payload_unfolding_to_the_limit_decodes_and_one_byte_more_does_not(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The limit is the one a fetched response is held to."""
    monkeypatch.setattr(_http, "MAX_BYTES", 100)
    assert decode(["x" * 98]).value == "x" * 98  # 100 bytes with its quotes
    with pytest.raises(TurboStreamError, match="unfolds to more than 100 bytes"):
        decode(["x" * 99])


def test_containers_shared_level_after_level_are_refused_by_what_they_unfold_to() -> (
    None
):
    """16 levels and a 1,000-character string: a tiny array, 65 MB written out."""
    flat = _doubling(16, "x" * 1000)
    assert len(json.dumps(flat)) < 2000
    with pytest.raises(TurboStreamError, match="unfolds to more than"):
        decode(flat)


def test_a_string_referenced_many_times_counts_every_time() -> None:
    flat: list[Any] = [[1] * 40, "x" * 1_000_000]
    with pytest.raises(TurboStreamError, match="unfolds to more than"):
        decode(flat)


def test_sharing_within_the_limit_still_decodes_to_shared_objects() -> None:
    result = decode(_doubling(10, "x"))
    assert result.value[0] is result.value[1]


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
