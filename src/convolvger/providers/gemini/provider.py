"""The Gemini provider adapter."""

import httpx

from convolvger.core.results import ParseResult
from convolvger.core.source import RawSource
from convolvger.providers.gemini import _fetch, _parse, _urls


class GeminiProvider:
    """Archives public Gemini conversation share links."""

    name = "gemini"

    def matches(self, url: str) -> bool:
        return _urls.is_share_url(url)

    def fetch(self, url: str, *, client: httpx.Client | None = None) -> RawSource:
        return _fetch.fetch(url, client=client)

    def parse(self, source: RawSource) -> ParseResult:
        return _parse.parse(source)
