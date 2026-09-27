"""Lifting numbered citation markers, and leaving code alone."""

import re

import pytest

from convolvger.core.citations import code_spans, lift

MARKER = re.compile(r"\[\[(\d+)\]\]")


def known(number: str) -> bool:
    return number in {"1", "2"}


def test_a_resolved_marker_is_lifted_and_an_unresolved_one_left() -> None:
    outcome = lift("Copper heats evenly.[[1]] Lighter.[[2]][[9]]", MARKER, known)
    assert outcome.text == "Copper heats evenly. Lighter.[[9]]"
    assert outcome.lifted == ["[[1]]", "[[2]]"]
    assert outcome.unresolved == ["[[9]]"]


@pytest.mark.parametrize(
    "code",
    [
        "```python\nx = [[1]]\n```\n",
        "~~~\nx = [[1]]\n~~~\n",
        "````\n```\nx = [[1]]\n```\n````\n",
        "    ```js\n    x = [[1]]\n    ```\n",
    ],
    ids=["backticks", "tildes", "longer-fence", "indented"],
)
def test_a_marker_inside_a_fenced_block_is_content(code: str) -> None:
    outcome = lift(f"Before.[[1]]\n\n{code}\nAfter.[[2]]", MARKER, known)
    assert "x = [[1]]" in outcome.text
    assert outcome.lifted == ["[[1]]", "[[2]]"]
    assert outcome.unresolved == []


def test_a_marker_inside_inline_code_is_content() -> None:
    outcome = lift("the list `[[1]]` is nested[[1]]", MARKER, known)
    assert outcome.text == "the list `[[1]]` is nested"


def test_an_unclosed_fence_runs_to_the_end_as_markdown_renders_it() -> None:
    outcome = lift("```\n[[1]] stays", MARKER, known)
    assert outcome.text == "```\n[[1]] stays"
    assert outcome.lifted == []
    assert outcome.unresolved == []


def test_a_stray_backtick_does_not_hide_citations_in_later_paragraphs() -> None:
    """Inline code never crosses a blank line, so a lone backtick pairs with nothing."""
    text = "A stray ` backtick.[[1]]\n\nLater this is cited.[[2]] And `x` is code."
    outcome = lift(text, MARKER, known)
    assert outcome.lifted == ["[[1]]", "[[2]]"]
    assert (
        outcome.text == "A stray ` backtick.\n\nLater this is cited. And `x` is code."
    )


def test_inline_code_may_wrap_within_a_paragraph() -> None:
    assert code_spans("a `long\ncode` span") == [(2, 13)]


def test_text_without_markers_comes_back_unchanged() -> None:
    outcome = lift("Nothing cited here.", MARKER, known)
    assert outcome.text == "Nothing cited here."
    assert outcome.lifted == []
