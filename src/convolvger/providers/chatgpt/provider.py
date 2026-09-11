"""The ChatGPT provider adapter."""

import httpx

from convolvger.core.results import ParseResult
from convolvger.core.source import RawSource
from convolvger.providers.chatgpt import _fetch, _parse, _urls


class ChatGPTProvider:
    """Archives public ChatGPT conversation share links."""

    name = "chatgpt"

    def matches(self, url: str) -> bool:
        return _urls.is_share_url(url)

    def fetch(self, url: str, *, client: httpx.Client | None = None) -> RawSource:
        return _fetch.fetch(url, client=client)

    def parse(self, source: RawSource) -> ParseResult:
        return _parse.parse(source)
