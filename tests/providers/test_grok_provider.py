"""The Grok provider adapter: what it claims, and what it delegates."""

import json
from pathlib import Path

import httpx
import pytest

from convolvger.core.results import ParseError
from convolvger.core.source import RawSource
from convolvger.providers.grok import GrokProvider
from convolvger.providers.grok import _fetch as grok_fetch

FIXTURE = Path(__file__).parent.parent / "fixtures" / "grok" / "share-minimal.json"
CANONICAL = "https://grok.com/share/bGVnYWN5_00000000-0000-4000-8000-000000000001"


def test_the_provider_is_named_after_its_provider() -> None:
    assert GrokProvider().name == "grok"


def test_it_claims_grok_share_links_and_nothing_else() -> None:
    provider = GrokProvider()

    assert provider.matches(CANONICAL)
    assert provider.matches(CANONICAL.replace("://", "://www."))
    assert not provider.matches("https://grok.com/chat/abc")
    assert not provider.matches("https://gemini.google.com/share/abc")


def test_fetching_is_delegated_and_records_the_share_url() -> None:
    body = FIXTURE.read_text(encoding="utf-8")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=body)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    source = GrokProvider().fetch(CANONICAL, client=client)

    assert source.url == CANONICAL
    assert source.content == body


def test_parsing_is_delegated_to_the_payload_parser() -> None:
    body = FIXTURE.read_text(encoding="utf-8")
    result = GrokProvider().parse(RawSource(url=CANONICAL, content=body))

    assert result.conversation.provider == "grok"
    assert len(result.conversation.messages) == 4


def test_a_snapshot_that_is_not_a_grok_payload_is_refused() -> None:
    with pytest.raises(ParseError):
        GrokProvider().parse(
            RawSource(url=CANONICAL, content=json.dumps({"mapping": {}}))
        )


def test_a_missing_share_is_refused_at_fetch() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            404, text='{"code":5,"message":"Cannot find conversation.","details":[]}'
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(grok_fetch.ShareNotFoundError):
        GrokProvider().fetch(CANONICAL, client=client)
