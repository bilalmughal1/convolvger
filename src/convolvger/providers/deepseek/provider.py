"""The DeepSeek provider adapter."""

import httpx

from convolvger.core.results import ParseResult
from convolvger.core.source import RawSource
from convolvger.core.text import replace_unpaired_surrogates
from convolvger.providers.deepseek import _fetch, _parse, _urls


class DeepSeekProvider:
    """Archives public DeepSeek conversation share links."""

    name = "deepseek"

    def matches(self, url: str) -> bool:
        return _urls.is_share_url(url)

    def fetch(self, url: str, *, client: httpx.Client | None = None) -> RawSource:
        return _fetch.fetch(url, client=client)

    def parse(self, source: RawSource) -> ParseResult:
        return replace_unpaired_surrogates(_parse.parse(source))
