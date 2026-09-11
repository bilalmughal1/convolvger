"""Outcome types carrying non-fatal diagnostics alongside parsed data.

Warnings are extraction metadata, not conversation content, so they
travel beside the canonical model rather than inside it. This keeps the
same source snapshot producing the same ``Conversation`` even as warning
text evolves between releases.
"""

from pydantic import BaseModel, ConfigDict, Field

from convolvger.core.errors import ConvolvgerError
from convolvger.core.models import Conversation


class ParseResult(BaseModel):
    """A parsed conversation plus any non-fatal extraction warnings."""

    model_config = ConfigDict(extra="forbid")

    conversation: Conversation
    warnings: list[str] = Field(default_factory=list)


class ParseError(ConvolvgerError):
    """Raised when a source cannot be parsed into a conversation.

    Carries any warnings accumulated before the failure so a caller can
    still report what was observed.
    """

    def __init__(self, message: str, warnings: list[str] | None = None) -> None:
        super().__init__(message)
        self.warnings = list(warnings or [])
