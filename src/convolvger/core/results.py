"""Outcome types carrying non-fatal diagnostics alongside parsed data.

Findings are extraction metadata, not conversation content, so they
travel beside the canonical model rather than inside it. This keeps the
same source snapshot producing the same ``Conversation`` even as finding
text evolves between releases.
"""

from pydantic import BaseModel, ConfigDict, Field

from convolvger.core.errors import ConvolvgerError
from convolvger.core.findings import Finding, Level
from convolvger.core.models import Conversation


class ParseResult(BaseModel):
    """A parsed conversation plus any non-fatal extraction findings."""

    model_config = ConfigDict(extra="forbid")

    conversation: Conversation
    findings: list[Finding] = Field(default_factory=list)

    @property
    def warned(self) -> bool:
        """True when a finding is severe enough to change the exit status."""
        return any(item.level is Level.WARNING for item in self.findings)


class ParseError(ConvolvgerError):
    """Raised when a source cannot be parsed into a conversation.

    Carries any findings accumulated before the failure so a caller can
    still report what was observed.
    """

    def __init__(self, message: str, findings: list[Finding] | None = None) -> None:
        super().__init__(message)
        self.findings = list(findings or [])
