"""Structured observations recorded during extraction.

A finding is one thing this tool noticed, not a verdict. Each carries a
stable ``code`` callers can key on without matching prose, and a
``level`` that decides whether it raises the exit status.

Level governs notification only. Every finding is recorded in the
archive whatever its level: nothing is ever withheld from the record
because it was judged unremarkable.

Codes are append-only. Never rename a code and never change what it
means -- an archive written a year ago keys on the same string, and a
descriptive name tempts renaming when an interpretation shifts. If the
meaning changes, add a new code and stop emitting the old one.
"""

from collections.abc import Iterable
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class Level(StrEnum):
    """How loudly a finding is reported.

    There is deliberately no ``error``: an unrecoverable problem raises
    ``ParseError``, and there is then no archive for a finding to sit in.
    """

    NOTE = "note"
    WARNING = "warning"


LEVELS: dict[str, Level] = {
    "attachment_withheld": Level.WARNING,
    "deferred_slot_not_merged": Level.WARNING,
    "deferred_value_unresolved": Level.WARNING,
    "literal_object_key": Level.NOTE,
    "message_content_withheld": Level.WARNING,
    "message_has_no_content": Level.NOTE,
    "message_weight_absent": Level.NOTE,
    "non_standard_json_constant": Level.WARNING,
    "tool_result_has_no_content": Level.WARNING,
    "unexpected_message_weight": Level.WARNING,
    "unmodelled_content_type": Level.WARNING,
    "unrecognised_role": Level.WARNING,
    "unrecognised_stream_line": Level.WARNING,
}
"""The single place a code's severity is decided.

``message_has_no_content`` is a note because a public share snapshot
omits content by design: OpenAI states that custom instructions are not
shared with share-link viewers, so empty system messages appear in every
such conversation. ``message_content_withheld`` is a warning because it
marks content the snapshot was expected to carry and did not.

``message_weight_absent`` is a note because absence is not damage on
its own: a snapshot that never carried the field says nothing about
whether a branch was deactivated. It is recorded rather than assumed
away so that a provider dropping a field it always sent is visible.

``attachment_withheld`` and ``tool_result_has_no_content`` are warnings
for the reason ``message_content_withheld`` is: the snapshot's own
structure referenced something it then did not serve. A snapshot
declaring a file count while carrying no files says so itself, and a
tool result addressed by a tool call but holding no payload is the same
shape. That a provider withholds them deliberately makes them expected,
not present.
"""


class Finding(BaseModel):
    """One recorded observation about an extraction."""

    model_config = ConfigDict(extra="forbid")

    code: str
    level: Level
    message: str
    message_id: str | None = None
    occurrences: int = Field(default=1, ge=1)
    """How many times this observation was made.

    Repeated observations of one code collapse into a single finding
    carrying a count, rather than one finding each. A decoder can meet
    the same unmodelled shape eighty times in one snapshot, and eighty
    identical findings bury the other things the report has to say
    while adding nothing. The count is kept because the number is
    itself evidence: an archival record should not lose how much of
    something it saw.
    """


def finding(code: str, message: str, message_id: str | None = None) -> Finding:
    """Build a finding, taking its level from ``LEVELS``.

    The level is not a parameter: one code must never be emitted at two
    different severities. It is still written into the output, so a
    reader does not need this table to interpret an archive.
    """
    if code not in LEVELS:
        raise KeyError(f"Unknown finding code: {code}")
    return Finding(
        code=code, level=LEVELS[code], message=message, message_id=message_id
    )


def collapse(findings: Iterable[Finding]) -> list[Finding]:
    """Fold identical observations into one finding carrying a count.

    Two findings are the same observation when code, message and
    message id all match. Anything that differs stays separate:
    collapsing on the code alone would discard which key, or which
    block, each observation was about, and that is the part worth
    keeping. SARIF counts a logically unique result rather than a rule,
    for the same reason.

    The first occurrence of each observation keeps its position, so a
    reader sees them in the order they were noticed. Counts already
    carried are added rather than overwritten, so collapsing a list
    twice cannot lose a number.
    """
    counted: dict[tuple[str, str, str | None], Finding] = {}
    for item in findings:
        key = (item.code, item.message, item.message_id)
        seen = counted.get(key)
        if seen is None:
            counted[key] = item
            continue
        counted[key] = seen.model_copy(
            update={"occurrences": seen.occurrences + item.occurrences}
        )
    return list(counted.values())
