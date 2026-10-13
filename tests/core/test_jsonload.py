"""Parsing JSON with a fixed limit on how deeply it nests."""

import json
import random
import time
from typing import Any

import pytest

from convolvger.core import jsonload


def nested(levels: int) -> str:
    return "[" * levels + "]" * levels


def test_a_document_at_the_limit_is_returned() -> None:
    value = jsonload.loads(nested(jsonload.MAX_DEPTH))
    assert isinstance(value, list)


def test_a_document_one_level_over_the_limit_is_refused_naming_the_limit() -> None:
    with pytest.raises(
        jsonload.JSONNestingError, match=f"more than {jsonload.MAX_DEPTH} levels"
    ):
        jsonload.loads(nested(jsonload.MAX_DEPTH + 1))


def test_objects_and_arrays_both_count_as_levels() -> None:
    document = '{"a": [{"b": []}]}'
    assert jsonload.loads(document, max_depth=4) == {"a": [{"b": []}]}
    with pytest.raises(jsonload.JSONNestingError):
        jsonload.loads(document, max_depth=3)


def test_a_document_too_deep_for_the_stack_is_refused_on_every_platform() -> None:
    """Either the parser runs out of stack or the check catches it; never neither."""
    with pytest.raises(jsonload.JSONNestingError):
        jsonload.loads(nested(100_000))


def test_running_out_of_stack_while_parsing_is_a_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def exhausted(*args: object, **kwargs: object) -> object:
        raise RecursionError("maximum recursion depth exceeded")

    monkeypatch.setattr(json, "loads", exhausted)
    with pytest.raises(jsonload.JSONNestingError):
        jsonload.loads("[]")


def test_malformed_json_is_still_a_decode_error() -> None:
    with pytest.raises(json.JSONDecodeError):
        jsonload.loads("[1,")


def test_options_reach_the_parser() -> None:
    seen: list[str] = []

    def note(token: str) -> None:
        seen.append(token)

    jsonload.loads("[NaN]", parse_constant=note)
    assert seen == ["NaN"]


def test_raw_decode_reads_one_document_and_says_where_it_ended() -> None:
    assert jsonload.raw_decode("xx[1] [2]", 2) == ([1], 5)


def test_raw_decode_refuses_what_loads_refuses() -> None:
    with pytest.raises(jsonload.JSONNestingError):
        jsonload.raw_decode(nested(jsonload.MAX_DEPTH + 1))


def _doubled(levels: int) -> Any:
    """Each level holds the level below twice: 2**levels paths, ``levels`` lists."""
    value: Any = "end"
    for _ in range(levels):
        value = [value, value]
    return value


def test_a_shared_container_is_not_walked_once_per_path() -> None:
    """Decoded payloads share containers; walking paths would take 2**60 steps."""
    started = time.perf_counter()
    jsonload.check_depth(_doubled(60))
    assert time.perf_counter() - started < 2


def test_a_shared_container_reached_again_deeper_is_measured_again() -> None:
    """Remembering only *that* a container was seen would miss this one."""
    shared = _doubled(3)
    wrapped: Any = shared
    for _ in range(jsonload.MAX_DEPTH - 2):
        wrapped = [wrapped]
    # Under ``[wrapped, shared]`` the wrappers end one level inside the
    # limit. ``shared`` is walked first at depth 2, then reached again
    # under them at the limit, where its own levels go past it.
    with pytest.raises(jsonload.JSONNestingError):
        jsonload.check_depth([wrapped, shared])


def test_an_archive_may_nest_deeper_than_a_source() -> None:
    """The archive's envelope adds levels to whatever it keeps."""
    jsonload.loads(
        nested(jsonload.MAX_DEPTH + 10), max_depth=jsonload.ARCHIVE_MAX_DEPTH
    )


def _random_tree(rng: random.Random, budget: int) -> Any:
    if budget <= 0 or rng.random() < 0.2:
        return rng.choice([0, "x", None, True])
    if rng.random() < 0.5:
        return [_random_tree(rng, budget - 1) for _ in range(rng.randint(0, 3))]
    return {str(i): _random_tree(rng, budget - 1) for i in range(rng.randint(0, 3))}


def test_parsed_json_is_judged_exactly_as_the_shared_aware_walk_judges_it() -> None:
    """Parsed JSON takes a faster walk; it must refuse the same documents."""
    rng = random.Random(20261013)
    for _ in range(2000):
        text = json.dumps(_random_tree(rng, rng.randint(0, 12)))
        for limit in range(1, 14):
            try:
                jsonload.check_depth(json.loads(text), limit)
                expected = True
            except jsonload.JSONNestingError:
                expected = False
            try:
                jsonload.loads(text, max_depth=limit)
                got = True
            except jsonload.JSONNestingError:
                got = False
            assert got == expected, (text, limit)
