"""Which integrity question each finding code bears on.

A finding records something observed. An aspect says which question that
observation answers, and there are two worth asking of an archive:

``COMPLETENESS``
    Did the provider serve everything its own snapshot structure
    referenced? A slot left unmerged or a message emptied of content the
    snapshot was expected to carry means it did not.

``FIDELITY``
    Could we model everything the provider did serve? A content type we
    have no block for, or a value JSON cannot carry, means we could not.

``INFORMATIONAL``
    Neither. The observation is recorded because it is true, not because
    it indicates damage: empty system messages are how a share snapshot
    normally arrives, and neither check should count them.

The mapping lives here rather than on ``Finding`` because it is
editorial. Codes are append-only and permanent; which question a code
bears on can be revised as evidence arrives, and no aspect is ever
written into an archive, so revising one cannot invalidate a file
already on disk.

The mapping is total and has no default. A code with no aspect would
drop silently out of every report -- the same class of failure as a test
no longer being collected -- so a test keeps this table and ``LEVELS``
in step.

An aspect is not a severity. ``INFORMATIONAL`` cannot be derived from
``Level.NOTE``: ``literal_object_key`` and ``message_has_no_content``
are both notes and answer different questions.
"""

from enum import StrEnum


class Aspect(StrEnum):
    """The question a finding code bears on, or that it bears on none."""

    COMPLETENESS = "completeness"
    FIDELITY = "fidelity"
    INFORMATIONAL = "informational"


ASPECTS: dict[str, Aspect] = {
    "deferred_slot_not_merged": Aspect.COMPLETENESS,
    "deferred_value_unresolved": Aspect.COMPLETENESS,
    "literal_object_key": Aspect.FIDELITY,
    "message_content_withheld": Aspect.COMPLETENESS,
    "message_has_no_content": Aspect.INFORMATIONAL,
    "message_weight_absent": Aspect.INFORMATIONAL,
    "non_standard_json_constant": Aspect.FIDELITY,
    "unexpected_message_weight": Aspect.FIDELITY,
    "unmodelled_content_type": Aspect.FIDELITY,
    "unrecognised_role": Aspect.FIDELITY,
    "unrecognised_stream_line": Aspect.FIDELITY,
}
"""The single place a code's integrity question is decided.

``non_standard_json_constant`` and ``literal_object_key`` are fidelity
rather than completeness: the provider served the value, and what was
lost was lost converting it here.
"""
