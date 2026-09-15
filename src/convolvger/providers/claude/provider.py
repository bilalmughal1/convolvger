"""The Claude provider adapter."""

from convolvger.core.results import ParseResult
from convolvger.core.source import RawSource
from convolvger.providers.base import FetchUnsupportedError
from convolvger.providers.claude import _parse, _urls


class ClaudeProvider:
    """Archives Claude conversation share snapshots saved from a browser."""

    name = "claude"

    def matches(self, url: str) -> bool:
        return _urls.is_share_url(url)

    def fetch(self, url: str) -> RawSource:
        raise FetchUnsupportedError(
            "Claude share links cannot be retrieved over HTTP: the page loads "
            "its conversation separately, so the URL alone returns no "
            "conversation. Save the snapshot from your browser and pass it "
            "with --from-file, keeping the share URL as the argument so it "
            "still routes to this provider and is recorded in the archive."
        )

    def parse(self, source: RawSource) -> ParseResult:
        return _parse.parse(source)
