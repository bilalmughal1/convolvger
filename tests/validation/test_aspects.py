from convolvger.core.findings import LEVELS, Level
from convolvger.validation.aspects import ASPECTS, Aspect


def test_every_code_has_exactly_one_aspect() -> None:
    """Keeps a code from dropping silently out of every report."""
    assert set(ASPECTS) == set(LEVELS), {
        "missing an aspect": sorted(set(LEVELS) - set(ASPECTS)),
        "not a real code": sorted(set(ASPECTS) - set(LEVELS)),
    }


def test_informational_is_not_derivable_from_level() -> None:
    """Two notes, two different questions: the tables must stay separate."""
    assert LEVELS["literal_object_key"] is Level.NOTE
    assert LEVELS["message_has_no_content"] is Level.NOTE

    assert ASPECTS["literal_object_key"] is Aspect.FIDELITY
    assert ASPECTS["message_has_no_content"] is Aspect.INFORMATIONAL


def test_nothing_that_changes_the_exit_status_is_informational() -> None:
    """A warning must bear on a check, or exit 2 would contradict the verdict."""
    warnings = {code for code, level in LEVELS.items() if level is Level.WARNING}

    assert not [code for code in warnings if ASPECTS[code] is Aspect.INFORMATIONAL]
