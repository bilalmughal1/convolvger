from typing import Protocol

from convolvger.core.models import Conversation
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

    def parse(self, source: RawSource) -> Conversation:
        """Convert a raw snapshot into the canonical conversation model."""
        ...
