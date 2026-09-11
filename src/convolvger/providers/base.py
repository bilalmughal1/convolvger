from typing import Protocol

from convolvger.core.results import ParseResult
from convolvger.core.source import RawSource


class Provider(Protocol):
    """Adapter for one AI provider's public conversation format."""

    name: str

    def matches(self, url: str) -> bool:
        """Return True if this provider handles the given URL."""
        ...

    def fetch(self, url: str) -> RawSource:
        """Retrieve the raw public snapshot for the given URL."""
        ...

    def parse(self, source: RawSource) -> ParseResult:
        """Convert a raw snapshot into a canonical conversation.

        Returns the conversation with any non-fatal warnings. Raises
        ``ParseError`` when the source cannot be parsed at all.
        """
        ...
