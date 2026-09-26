"""The Gemini provider adapter: what it claims, and what it delegates."""

import json
from pathlib import Path

import httpx
import pytest

from convolvger.core.results import ParseError
from convolvger.core.source import RawSource
from convolvger.providers.gemini import GeminiProvider
from convolvger.providers.gemini import _fetch as gemini_fetch

FIXTURE = Path(__file__).parent.parent / "fixtures" / "gemini" / "share-minimal.json"
CANONICAL = "https://gemini.google.com/share/09bcf760b07b"
SHORT = "https://share.gemini.google/94ESiKYXbGiV"


def body(payload: object) -> str:
    inner = json.dumps(payload, ensure_ascii=False)
    frame = json.dumps(
        [["wrb.fr", "ujx1Bf", inner, None, None, None, "generic"]], ensure_ascii=False
    )
    return f")]}}'\n\n{frame}"


def test_the_provider_is_named_after_its_provider() -> None:
    assert GeminiProvider().name == "gemini"


def test_it_claims_every_gemini_share_form_and_nothing_else() -> None:
    provider = GeminiProvider()

    assert provider.matches(CANONICAL)
    assert provider.matches(SHORT)
    assert provider.matches("https://g.co/gemini/share/09bcf760b07b")
    assert not provider.matches("https://chatgpt.com/share/abc")
    assert not provider.matches("https://gemini.google.com/app/abc")


def test_fetching_is_delegated_and_records_the_share_url() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=body(payload))

    client = httpx.Client(transport=httpx.MockTransport(handler))
    source = GeminiProvider().fetch(CANONICAL, client=client)

    assert source.url == CANONICAL
    assert source.content.startswith(")]}'")


def test_parsing_is_delegated_to_the_payload_parser() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    result = GeminiProvider().parse(RawSource(url=CANONICAL, content=body(payload)))

    assert result.conversation.provider == "gemini"
    assert len(result.conversation.messages) == 4
    assert result.findings == []


def test_a_snapshot_that_is_not_a_gemini_response_is_refused() -> None:
    with pytest.raises(ParseError):
        GeminiProvider().parse(
            RawSource(url=CANONICAL, content=json.dumps({"mapping": {}}))
        )


def test_a_missing_share_is_refused_at_fetch() -> None:
    """Gemini answers 200 for an unknown id, so the provider must still refuse."""
    empty = ')]}\'\n\n[["wrb.fr","ujx1Bf",null,null,null,[5],"generic"]]'

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=empty)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(gemini_fetch.ShareNotFoundError):
        GeminiProvider().fetch(CANONICAL, client=client)
