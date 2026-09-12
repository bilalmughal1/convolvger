import re
from pathlib import Path

import pytest

from convolvger.core.findings import LEVELS, Finding, Level, finding

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
        used.update(re.findall(r'finding\(\s*"([a-z_]+)"', path.read_text(encoding="utf-8")))

    assert used <= set(LEVELS), f"codes missing from LEVELS: {sorted(used - set(LEVELS))}"
