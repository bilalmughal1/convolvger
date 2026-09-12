from convolvger.core.findings import LEVELS, Level
from convolvger.validation.aspects import ASPECTS, Aspect


def test_every_code_has_exactly_one_aspect() -> None:
    """Keeps a code from dropping silently out of every report."""
    assert set(ASPECTS) == set(LEVELS), {
        "missing an aspect": sorted(set(LEVELS) - set(ASPECTS)),
        "not a real code": sorted(set(ASPECTS) - set(LEVELS)),
    }


def test_nothing_that_changes_the_exit_status_is_informational() -> None:
    """A warning must bear on a check, or exit 2 would contradict the verdict."""
    warnings = {code for code, level in LEVELS.items() if level is Level.WARNING}

    assert not [code for code in warnings if ASPECTS[code] is Aspect.INFORMATIONAL]
