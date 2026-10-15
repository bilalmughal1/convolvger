"""The Perplexity provider adapter."""

from convolvger.core.results import ParseResult
from convolvger.core.source import RawSource
from convolvger.core.text import replace_unpaired_surrogates
from convolvger.providers.base import FetchUnsupportedError
from convolvger.providers.perplexity import _parse, _urls


class PerplexityProvider:
    """Archives Perplexity shared threads captured from a browser."""

    name = "perplexity"

    def matches(self, url: str) -> bool:
        return _urls.is_share_url(url)

    def fetch(self, url: str) -> RawSource:
        raise FetchUnsupportedError(
            "Perplexity shared threads cannot be retrieved over HTTP: the "
            "page and the data behind it answer this tool with a bot "
            "challenge. Capture the thread from your browser with "
            "'convolvger export --capture' and the bookmarklet, or save the "
            "thread's data and pass it with --from-file, keeping the share URL "
            "as the argument."
        )

    def parse(self, source: RawSource) -> ParseResult:
        return replace_unpaired_surrogates(_parse.parse(source))
