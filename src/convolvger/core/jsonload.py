"""Parsing JSON with a fixed limit on how deeply it nests.

``json`` recurses once per level of nesting, so a document deep enough
exhausts the stack. Where that happens depends on the interpreter, not
the document: measured with 100,000 nested arrays, Python 3.12, 3.13
and 3.14 on an 8 MiB stack raise ``RecursionError``, while 3.14 with an
unlimited stack parses the whole thing and hands it on. Catching
``RecursionError`` alone would leave the outcome to the machine.

So depth is checked after parsing as well, and anything deeper than
the limit is refused the same way everywhere.

``MAX_DEPTH`` applies to what a provider serves. The binding constraint
is not the stack but serialisation: pydantic-core 2.46.5 refuses to
serialise a value nested more than 254 levels inside an ``Any`` field,
which is where unmodelled content is kept, so a deeper source could be
parsed and then not written. The deepest real share measured nests 24
levels (a Gemini payload); the others nest 9 to 15. 128 leaves room
for five times that and stays well clear of 254.

``ARCHIVE_MAX_DEPTH`` applies to an archive being read back. An archive
wraps the conversation in its own envelope -- a value kept from a
source was measured 3 to 7 levels further from the top than within the
value itself -- so it must read deeper than a source may be, or
``verify`` would refuse archives this tool wrote. Archive loading was
measured to validate 2,000 levels.

A refusal is a ``JSONNestingError``, not a ``JSONDecodeError``: the
document may be perfectly valid JSON, and each caller names it in its
own error rather than calling it malformed.
"""

import json
from typing import Any

MAX_DEPTH = 128
ARCHIVE_MAX_DEPTH = 512


class JSONNestingError(ValueError):
    """The document nests deeper than this tool accepts."""

    def __init__(self, max_depth: int) -> None:
        super().__init__(f"JSON nested more than {max_depth} levels deep")
        self.max_depth = max_depth


def check_depth(value: Any, max_depth: int = MAX_DEPTH) -> None:
    """Raise ``JSONNestingError`` if ``value`` nests deeper than ``max_depth``.

    A walk with its own stack, since recursing here would fail on the
    very values it exists to refuse. A container reached again -- a
    decoded payload may share one object between many places -- is
    walked again only when reached at a greater depth, so the cost is
    bounded by containers times the limit rather than by paths, which
    can number two to the power of the depth.
    """
    deepest: dict[int, int] = {}
    pending: list[tuple[Any, int]] = [(value, 1)]
    while pending:
        node, depth = pending.pop()
        if isinstance(node, dict):
            children: Any = node.values()
        elif isinstance(node, list):
            children = node
        else:
            continue
        if depth > max_depth:
            raise JSONNestingError(max_depth)
        if deepest.get(id(node), 0) >= depth:
            continue
        deepest[id(node)] = depth
        pending.extend((child, depth + 1) for child in children)


def loads(text: str | bytes, *, max_depth: int = MAX_DEPTH, **options: Any) -> Any:
    """``json.loads``, refusing a document nested deeper than ``max_depth``.

    Malformed JSON still raises ``json.JSONDecodeError``.
    """
    try:
        value = json.loads(text, **options)
    except RecursionError as error:
        raise JSONNestingError(max_depth) from error
    check_depth(value, max_depth)
    return value


def raw_decode(text: str, position: int = 0) -> tuple[Any, int]:
    """``JSONDecoder().raw_decode``, refusing what ``loads`` refuses."""
    try:
        value, end = json.JSONDecoder().raw_decode(text, position)
    except RecursionError as error:
        raise JSONNestingError(MAX_DEPTH) from error
    check_depth(value)
    return value, end
