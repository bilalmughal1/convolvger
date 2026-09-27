"""The Qwen provider adapter: what it claims, and what it delegates."""

from pathlib import Path

import httpx
import pytest

from convolvger.core.results import ParseError
from convolvger.core.source import RawSource
from convolvger.providers.qwen import QwenProvider
from convolvger.providers.qwen import _fetch as qwen_fetch

FIXTURE = Path(__file__).parent.parent / "fixtures" / "qwen" / "share-minimal.json"
LINK = "https://chat.qwen.ai/s/00000000-0000-4000-8000-000000000001?fev=0.3.11"


def test_the_provider_is_named_after_its_provider() -> None:
    assert QwenProvider().name == "qwen"


def test_it_claims_qwen_share_links_and_nothing_else() -> None:
    provider = QwenProvider()
    assert provider.matches(LINK)
    assert provider.matches(LINK.replace("chat.qwen.ai", "chat.qwenlm.ai"))
    assert not provider.matches("https://chat.qwen.ai/c/abc")
    assert not provider.matches("https://grok.com/share/abc")


def test_fetching_is_delegated_and_records_the_share_url() -> None:
    body = FIXTURE.read_text(encoding="utf-8")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=body)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    source = QwenProvider().fetch(LINK, client=client)
    assert source.url == LINK
    assert source.content == body


def test_parsing_is_delegated_to_the_payload_parser() -> None:
    body = FIXTURE.read_text(encoding="utf-8")
    result = QwenProvider().parse(RawSource(url=LINK, content=body))
    assert result.conversation.provider == "qwen"
    assert len(result.conversation.messages) == 4


def test_a_snapshot_that_is_not_a_qwen_payload_is_refused() -> None:
    with pytest.raises(ParseError):
        QwenProvider().parse(RawSource(url=LINK, content='{"mapping": {}}'))


def test_a_missing_share_is_refused_at_fetch() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text='{"success": false, "data": {"code": "Not_Found"}}',
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(qwen_fetch.ShareNotFoundError):
        QwenProvider().fetch(LINK, client=client)
