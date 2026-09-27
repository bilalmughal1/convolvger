"""The DeepSeek provider adapter: what it claims, and what it delegates."""

from pathlib import Path

import httpx
import pytest

from convolvger.core.results import ParseError
from convolvger.core.source import RawSource
from convolvger.providers.deepseek import DeepSeekProvider
from convolvger.providers.deepseek import _fetch as deepseek_fetch

FIXTURE = Path(__file__).parent.parent / "fixtures" / "deepseek" / "share-minimal.json"
LINK = "https://chat.deepseek.com/share/0example0share0id"


def test_the_provider_is_named_after_its_provider() -> None:
    assert DeepSeekProvider().name == "deepseek"


def test_it_claims_deepseek_share_links_and_nothing_else() -> None:
    provider = DeepSeekProvider()
    assert provider.matches(LINK)
    assert provider.matches(LINK + "/")
    assert not provider.matches("https://deepseek.com/share/abc")
    assert not provider.matches("https://grok.com/share/abc")


def test_fetching_is_delegated_and_records_the_share_url() -> None:
    body = FIXTURE.read_text(encoding="utf-8")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=body)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    source = DeepSeekProvider().fetch(LINK, client=client)
    assert source.url == LINK
    assert source.content == body


def test_parsing_is_delegated_to_the_payload_parser() -> None:
    body = FIXTURE.read_text(encoding="utf-8")
    result = DeepSeekProvider().parse(RawSource(url=LINK, content=body))
    assert result.conversation.provider == "deepseek"
    assert len(result.conversation.messages) == 4


def test_a_snapshot_that_is_not_a_deepseek_payload_is_refused() -> None:
    with pytest.raises(ParseError):
        DeepSeekProvider().parse(RawSource(url=LINK, content='{"mapping": {}}'))


def test_a_missing_share_is_refused_at_fetch() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text='"not found"')

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(deepseek_fetch.ShareNotFoundError):
        DeepSeekProvider().fetch(LINK, client=client)
