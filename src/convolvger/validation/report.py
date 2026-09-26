"""An integrity verdict derived from findings, never stored as one.

A report holds the findings it was given and computes its verdicts from
them on demand. Nothing here is written into an archive: the findings
are the record, and the verdict is what this version of Convolvger
makes of them today.

A finding whose code is not in ``ASPECTS`` is neither counted nor
refused. An archive may have been written by a later version that mints
codes this one has never seen, and a command whose purpose is to
reassure an operator must not crash on a file that is merely newer than
it is. Such findings are reported as unrecognised and change no verdict:
an unknown code is not evidence of damage, nor evidence of soundness.
"""

from pydantic import BaseModel, ConfigDict, Field

from convolvger.core.findings import Finding
from convolvger.validation.aspects import ASPECTS, Aspect


class Report(BaseModel):
    """What a set of findings says about an archive's integrity."""

    model_config = ConfigDict(extra="forbid")

    findings: list[Finding] = Field(default_factory=list)

    def findings_for(self, aspect: Aspect) -> list[Finding]:
        """Every finding bearing on one question, in the order recorded."""
        return [item for item in self.findings if ASPECTS.get(item.code) is aspect]

    @property
    def unrecognised(self) -> list[Finding]:
        """Findings carrying a code this version cannot classify."""
        return [item for item in self.findings if item.code not in ASPECTS]

    @property
    def complete(self) -> bool:
        """True when the provider served everything its snapshot referenced.

        Empty messages do not bear on this: a share snapshot omits system
        content by design, so a conversation can be complete with most of
        its messages carrying none.
        """
        return not self.findings_for(Aspect.COMPLETENESS)

    @property
    def faithful(self) -> bool:
        """True when everything the provider served could be modelled."""
        return not self.findings_for(Aspect.FIDELITY)
