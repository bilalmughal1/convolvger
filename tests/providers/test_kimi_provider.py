"""The Kimi provider adapter: what it claims, and what it delegates."""

from pathlib import Path

import httpx
import pytest

from convolvger.core.results import ParseError
from convolvger.core.source import RawSource
from convolvger.providers.kimi import KimiProvider
from convolvger.providers.kimi import _fetch as kimi_fetch

FIXTURE = Path(__file__).parent.parent / "fixtures" / "kimi" / "share-minimal.json"
LINK = "https://www.kimi.ai/share/00000000-0000-4000-8000-000000000002"


def test_the_provider_is_named_after_its_provider() -> None:
    assert KimiProvider().name == "kimi"


def test_it_claims_kimi_share_links_and_nothing_else() -> None:
    provider = KimiProvider()
    assert provider.matches(LINK)
    assert provider.matches(LINK.replace("www.kimi.ai", "www.kimi.com"))
    assert not provider.matches("https://www.kimi.ai/chat/abc")
    assert not provider.matches("https://grok.com/share/abc")


def test_fetching_is_delegated_and_records_the_share_url() -> None:
    body = FIXTURE.read_text(encoding="utf-8")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=body)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    source = KimiProvider().fetch(LINK, client=client)
    assert source.url == LINK
    assert source.content == body


def test_parsing_is_delegated_to_the_payload_parser() -> None:
    body = FIXTURE.read_text(encoding="utf-8")
    result = KimiProvider().parse(RawSource(url=LINK, content=body))
    assert result.conversation.provider == "kimi"
    assert len(result.conversation.messages) == 4


def test_a_snapshot_that_is_not_a_kimi_payload_is_refused() -> None:
    with pytest.raises(ParseError):
        KimiProvider().parse(RawSource(url=LINK, content='{"mapping": {}}'))


def test_a_missing_share_is_refused_at_fetch() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text='{"code":"not_found"}')

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(kimi_fetch.ShareNotFoundError):
        KimiProvider().fetch(LINK, client=client)
