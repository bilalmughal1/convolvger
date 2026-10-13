"""Reading a response without trusting its size."""

import gzip
from collections.abc import Iterator

import httpx
import pytest

from convolvger.providers import _http
from convolvger.providers.chatgpt import _fetch as chatgpt_fetch
from convolvger.providers.deepseek import _fetch as deepseek_fetch
from convolvger.providers.gemini import _fetch as gemini_fetch
from convolvger.providers.grok import _fetch as grok_fetch
from convolvger.providers.kimi import _fetch as kimi_fetch
from convolvger.providers.qwen import _fetch as qwen_fetch

URL = "https://example.test/x"
SHARE = "https://example.test/share/x"


class TooLarge(Exception):
    pass


def _client(response: httpx.Response) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(lambda request: response))


def _chunks(*parts: bytes) -> Iterator[bytes]:
    yield from parts


@pytest.fixture
def small_limit(monkeypatch: pytest.MonkeyPatch) -> int:
    monkeypatch.setattr(_http, "MAX_BYTES", 100)
    return 100


def test_a_body_at_the_limit_is_read(small_limit: int) -> None:
    client = _client(httpx.Response(200, content=b"a" * small_limit))
    response, body = _http.read(client, "GET", URL, too_large=TooLarge, share_url=SHARE)
    assert response.status_code == 200
    assert body == "a" * small_limit


def test_a_body_over_the_limit_is_refused_while_it_streams(small_limit: int) -> None:
    """No Content-Length: the count kept while reading is what stops it."""
    content = _chunks(b"a" * 60, b"a" * 60)
    client = _client(httpx.Response(200, content=content))
    with pytest.raises(TooLarge, match="over the limit"):
        _http.read(client, "GET", URL, too_large=TooLarge, share_url=SHARE)


def test_a_declared_length_over_the_limit_is_refused_before_reading(
    small_limit: int,
) -> None:
    def never_read() -> Iterator[bytes]:
        raise AssertionError("the body was read")
        yield b""

    response = httpx.Response(
        200, content=never_read(), headers={"content-length": "101"}
    )
    with pytest.raises(TooLarge, match="declares 101 bytes"):
        _http.read(_client(response), "GET", URL, too_large=TooLarge, share_url=SHARE)


def test_a_small_compressed_body_that_expands_past_the_limit_is_refused(
    small_limit: int,
) -> None:
    packed = gzip.compress(b"0" * 1000)
    assert len(packed) < small_limit
    response = httpx.Response(200, content=packed, headers={"content-encoding": "gzip"})
    with pytest.raises(TooLarge):
        _http.read(_client(response), "GET", URL, too_large=TooLarge, share_url=SHARE)


def test_a_compressed_body_is_decoded_once() -> None:
    response = httpx.Response(
        200,
        content=gzip.compress("café".encode()),
        headers={"content-encoding": "gzip", "content-type": "text/plain"},
    )
    _, body = _http.read(
        _client(response), "GET", URL, too_large=TooLarge, share_url=SHARE
    )
    assert body == "café"


def test_a_refusal_names_the_link_that_was_supplied(small_limit: int) -> None:
    """The endpoint asked is an implementation detail; the link is what was given."""
    client = _client(httpx.Response(200, content=_chunks(b"a" * 101)))
    with pytest.raises(TooLarge) as raised:
        _http.read(client, "GET", URL, too_large=TooLarge, share_url=SHARE)
    assert str(raised.value).endswith(SHARE)
    assert URL not in str(raised.value)


def test_a_declared_charset_is_honoured_as_response_text_would() -> None:
    raw = "café".encode("latin-1")
    response = httpx.Response(
        200, content=raw, headers={"content-type": "text/plain; charset=latin-1"}
    )
    _, body = _http.read(
        _client(response), "GET", URL, too_large=TooLarge, share_url=SHARE
    )
    assert body == httpx.Response(200, content=raw, headers=response.headers).text


FETCHERS = {
    "chatgpt": (chatgpt_fetch, "https://chatgpt.com/share/x"),
    "gemini": (gemini_fetch, "https://gemini.google.com/share/0000000000ab"),
    "grok": (
        grok_fetch,
        "https://grok.com/share/bGVnYWN5_00000000-0000-4000-8000-000000000001",
    ),
    "deepseek": (deepseek_fetch, "https://chat.deepseek.com/share/0example0share0id"),
    "kimi": (
        kimi_fetch,
        "https://www.kimi.ai/share/00000000-0000-4000-8000-000000000002",
    ),
    "qwen": (qwen_fetch, "https://chat.qwen.ai/s/00000000-0000-4000-8000-000000000001"),
}


@pytest.mark.parametrize("provider", list(FETCHERS))
def test_every_fetcher_refuses_an_oversized_response_with_its_own_error(
    provider: str, small_limit: int
) -> None:
    module, url = FETCHERS[provider]
    client = _client(httpx.Response(200, content=_chunks(b"{" * 80, b"}" * 80)))
    with pytest.raises(module.FetchError, match="over the limit") as raised:
        module.fetch(url, client=client)
    assert str(raised.value).endswith(url)
