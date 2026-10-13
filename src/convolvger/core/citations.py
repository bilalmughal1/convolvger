"""Lifting numbered citation markers out of an answer's Markdown.

Several providers number their citations inline -- DeepSeek writes
``[citation:3]``, Qwen writes ``[[3]]`` -- and each number points at a
search result the payload carries beside the answer. Left in, the
markers clutter the document a reader sees with numbers that lead
nowhere, since the results they name are kept in the JSON and not
rendered.

Two things make a marker safe to lift, and both are checked. It must
resolve: a number the payload has no result for is left where it is and
reported, because text this tool cannot account for is shown rather
than hidden. And it must not be inside code: ``x = [[3]]`` in a Python
answer is a nested list, not a citation, and a fenced or inline code
span is content whatever it looks like.

Nothing here knows a provider. The caller supplies the marker pattern,
whose first group is the number, and says which numbers resolve.
"""

import re
from bisect import bisect_right
from collections.abc import Callable
from dataclasses import dataclass, field

FENCE = re.compile(
    r"^[ \t]*(`{3,}|~{3,})[^\n]*\n.*?(?:^[ \t]*\1[ \t]*$|\Z)", re.M | re.S
)
INLINE = re.compile(r"(`+)(?!`)(?:(?!\n[ \t]*\n).)+?(?<!`)\1(?!`)", re.S)
"""An inline code span, which as in CommonMark may wrap a line but never
crosses a blank one. Without that limit, one stray backtick in prose pairs
with a backtick paragraphs later and hides every citation between them."""


@dataclass
class Lifted:
    """The visible text, and what happened to each marker outside code."""

    text: str
    lifted: list[str] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)


def _merged(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """The same positions as ``spans``, as sorted intervals that do not overlap."""
    merged: list[tuple[int, int]] = []
    for low, high in sorted(spans):
        if merged and low <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], high))
        else:
            merged.append((low, high))
    return merged


def _within(position: int, intervals: list[tuple[int, int]], lows: list[int]) -> bool:
    """True when ``position`` lies in one of the sorted, disjoint ``intervals``.

    A binary search, not a scan: a text with thousands of stray
    backticks has thousands of spans, and checking each one against
    every other made the time grow with the square of their number.
    """
    index = bisect_right(lows, position) - 1
    return index >= 0 and position < intervals[index][1]


def code_spans(text: str) -> list[tuple[int, int]]:
    """Return the start and end of every fenced block and inline code span."""
    spans = [match.span() for match in FENCE.finditer(text)]
    fences = list(spans)
    lows = [low for low, _ in fences]
    for match in INLINE.finditer(text):
        start, end = match.span()
        if not _within(start, fences, lows):
            spans.append((start, end))
    return spans


def lift(text: str, marker: re.Pattern[str], resolves: Callable[[str], bool]) -> Lifted:
    """Remove every marker that resolves and lies outside code."""
    spans = _merged(code_spans(text))
    lows = [low for low, _ in spans]
    kept: list[str] = []
    result = Lifted(text="")
    position = 0
    for match in marker.finditer(text):
        if _within(match.start(), spans, lows):
            continue
        if not resolves(match.group(1)):
            result.unresolved.append(match.group(0))
            continue
        kept.append(text[position : match.start()])
        result.lifted.append(match.group(0))
        position = match.end()
    kept.append(text[position:])
    result.text = "".join(kept)
    return result
