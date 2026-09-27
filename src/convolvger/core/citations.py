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


def code_spans(text: str) -> list[tuple[int, int]]:
    """Return the start and end of every fenced block and inline code span."""
    spans = [match.span() for match in FENCE.finditer(text)]
    for match in INLINE.finditer(text):
        start, end = match.span()
        if not any(low <= start < high for low, high in spans):
            spans.append((start, end))
    return spans


def lift(text: str, marker: re.Pattern[str], resolves: Callable[[str], bool]) -> Lifted:
    """Remove every marker that resolves and lies outside code."""
    spans = code_spans(text)
    kept: list[str] = []
    result = Lifted(text="")
    position = 0
    for match in marker.finditer(text):
        if any(low <= match.start() < high for low, high in spans):
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
