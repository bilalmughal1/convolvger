from datetime import UTC, datetime

import httpx
import pytest

from convolvger.core.errors import ConvolvgerError
from convolvger.providers.chatgpt._fetch import (
    FetchError,
    ShareAccessDeniedError,
    ShareNotFoundError,
    TransientFetchError,
    fetch,
)

URL = "https://chatgpt.com/share/6aa3f5a2-00a4-83eb-8d18-3b2266aac2e6"


def client_returning(*, status: int = 200, body: str = "<html></html>") -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status,
            content=body,
            headers={"content-type": "text/html; charset=utf-8"},
        )

    return httpx.Client(transport=httpx.MockTransport(handler))


def client_raising(exc: Exception) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        raise exc

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_successful_fetch_returns_raw_source() -> None:
    with client_returning(body="<html>snapshot</html>") as client:
        source = fetch(URL, client=client)

    assert source.url == URL
    assert source.content == "<html>snapshot</html>"
    assert source.content_type == "text/html; charset=utf-8"


def test_fetched_at_is_timezone_aware() -> None:
    with client_returning() as client:
        source = fetch(URL, client=client)

    assert source.fetched_at is not None
    assert source.fetched_at.tzinfo is not None
    assert source.fetched_at <= datetime.now(UTC)


def test_url_is_recorded_without_normalisation() -> None:
    messy = f"{URL}?utm_source=newsletter"
    with client_returning() as client:
        source = fetch(messy, client=client)

    assert source.url == messy


def test_404_raises_share_not_found() -> None:
    with client_returning(status=404) as client, pytest.raises(ShareNotFoundError):
        fetch(URL, client=client)


@pytest.mark.parametrize("status", [401, 403])
def test_denied_statuses_raise_access_denied(status: int) -> None:
    with client_returning(status=status) as client, pytest.raises(ShareAccessDeniedError):
        fetch(URL, client=client)


@pytest.mark.parametrize("status", [429, 500, 502, 503])
def test_transient_statuses_raise_transient_error(status: int) -> None:
    with client_returning(status=status) as client, pytest.raises(TransientFetchError):
        fetch(URL, client=client)


def test_unexpected_status_raises_fetch_error() -> None:
    with client_returning(status=302) as client, pytest.raises(FetchError, match="302"):
        fetch(URL, client=client)


def test_timeout_raises_transient_error() -> None:
    with (
        client_raising(httpx.ReadTimeout("slow")) as client,
        pytest.raises(TransientFetchError, match="timed out"),
    ):
        fetch(URL, client=client)


def test_connection_error_raises_fetch_error() -> None:
    with (
        client_raising(httpx.ConnectError("no route")) as client,
        pytest.raises(FetchError, match="Request failed"),
    ):
        fetch(URL, client=client)


def test_errors_share_a_catchable_base() -> None:
    with client_returning(status=404) as client, pytest.raises(ConvolvgerError):
        fetch(URL, client=client)


def test_injected_client_is_not_closed_by_fetch() -> None:
    client = client_returning()
    fetch(URL, client=client)

    assert client.is_closed is False
    client.close()
