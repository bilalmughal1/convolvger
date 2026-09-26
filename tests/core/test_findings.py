import re
from pathlib import Path

import pytest

from convolvger.core.findings import LEVELS, Finding, Level, collapse, finding

SRC = Path(__file__).parent.parent.parent / "src"


def test_level_comes_from_the_table_not_the_caller() -> None:
    assert finding("message_has_no_content", "empty").level is Level.NOTE
    assert finding("unrecognised_role", "odd role").level is Level.WARNING


def test_level_is_written_into_the_output() -> None:
    """A reader must not need our table to interpret an archive."""
    dumped = finding("message_has_no_content", "empty").model_dump()

    assert dumped["level"] == "note"


def test_unknown_code_is_refused() -> None:
    with pytest.raises(KeyError, match="Unknown finding code"):
        finding("not_a_real_code", "x")


def test_message_id_is_optional() -> None:
    assert finding("unrecognised_role", "x").message_id is None
    assert finding("unrecognised_role", "x", "m1").message_id == "m1"


def test_finding_round_trips_through_json() -> None:
    original = finding("message_content_withheld", "emptied", "m4")

    assert Finding.model_validate_json(original.model_dump_json()) == original


def test_every_code_used_in_the_source_is_in_the_table() -> None:
    """Keeps the KeyError above unreachable outside of tests."""
    used = set()
    for path in SRC.rglob("*.py"):
        used.update(
            re.findall(r'finding\(\s*"([a-z_]+)"', path.read_text(encoding="utf-8"))
        )

    assert used <= set(LEVELS), (
        f"codes missing from LEVELS: {sorted(used - set(LEVELS))}"
    )


def test_identical_observations_collapse_into_one_counted_finding() -> None:
    repeated = [finding("unmodelled_content_type", "knowledge preserved verbatim")] * 82

    collapsed = collapse(repeated)

    assert len(collapsed) == 1
    assert collapsed[0].occurrences == 82


def test_observations_differing_in_message_stay_separate() -> None:
    """The message says which key it was about; a count would lose that."""
    collapsed = collapse(
        [
            finding("literal_object_key", "kept as-is: title"),
            finding("literal_object_key", "kept as-is: linear_conversation"),
        ]
    )

    assert [item.message for item in collapsed] == [
        "kept as-is: title",
        "kept as-is: linear_conversation",
    ]
    assert [item.occurrences for item in collapsed] == [1, 1]


def test_observations_about_different_messages_stay_separate() -> None:
    collapsed = collapse(
        [
            finding("message_has_no_content", "no content", message_id="m1"),
            finding("message_has_no_content", "no content", message_id="m2"),
        ]
    )

    assert [item.message_id for item in collapsed] == ["m1", "m2"]


def test_collapse_keeps_the_order_each_observation_was_first_seen() -> None:
    collapsed = collapse(
        [
            finding("literal_object_key", "second"),
            finding("unmodelled_content_type", "first"),
            finding("literal_object_key", "second"),
        ]
    )

    assert [item.code for item in collapsed] == [
        "literal_object_key",
        "unmodelled_content_type",
    ]
    assert [item.occurrences for item in collapsed] == [2, 1]


def test_collapsing_twice_does_not_lose_a_count() -> None:
    once = collapse([finding("unmodelled_content_type", "knowledge")] * 3)

    assert collapse(once + once)[0].occurrences == 6
