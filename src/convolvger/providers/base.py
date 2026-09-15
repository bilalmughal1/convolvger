from typing import Protocol

from convolvger.core.errors import ConvolvgerError
from convolvger.core.results import ParseResult
from convolvger.core.source import RawSource


class FetchUnsupportedError(ConvolvgerError):
    """Raised when a provider cannot retrieve a snapshot itself.

    Not every share page can be read over HTTP. A provider that cannot
    says so by raising this, carrying the message a user needs to get
    the snapshot another way. It subclasses ``ConvolvgerError`` so the
    CLI already reports it as a plain failure with its own text, which
    is why no capability predicate is needed to ask in advance.
    """


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

        Returns the conversation with any non-fatal findings. Raises
        ``ParseError`` when the source cannot be parsed at all.
        """
        ...
