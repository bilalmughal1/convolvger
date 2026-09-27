import json

import httpx
import pytest

from convolvger.providers.qwen import _fetch

LINK = "https://chat.qwen.ai/s/00000000-0000-4000-8000-000000000001?fev=0.3.11"
ENDPOINT = (
    "https://chat.qwen.ai/api/v2/chats/share/00000000-0000-4000-8000-000000000001"
)
BODY = json.dumps(
    {
        "success": True,
        "request_id": "r",
        "data": {"chat": {"history": {"messages": {"m": {}}}}},
    }
)
MISSING = json.dumps(
    {
        "success": False,
        "request_id": "r",
        "data": {"code": "Not_Found", "details": "This conversation has been deleted."},
    }
)


def recording_client(
    *, status: int = 200, body: str = BODY
) -> tuple[httpx.Client, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            status, text=body, headers={"content-type": "application/json"}
        )

    return httpx.Client(transport=httpx.MockTransport(handler)), seen


def client_raising(error: Exception) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        raise error

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_gets_the_share_endpoint_once_without_the_page_s_query() -> None:
    client, seen = recording_client()
    _fetch.fetch(LINK, client=client)
    assert [(request.method, str(request.url)) for request in seen] == [
        ("GET", ENDPOINT)
    ]


def test_sends_no_cookie_or_token() -> None:
    client, seen = recording_client()
    _fetch.fetch(LINK, client=client)
    headers = {name.lower() for name in seen[0].headers}
    assert "cookie" not in headers
    assert "authorization" not in headers


def test_records_the_share_url_not_the_endpoint() -> None:
    client, _ = recording_client()
    source = _fetch.fetch(LINK, client=client)
    assert source.url == LINK
    assert source.content == BODY


def test_a_missing_share_is_reported_despite_a_200() -> None:
    """Measured: an unknown or malformed id answers 200 with success false."""
    client, _ = recording_client(body=MISSING)
    with pytest.raises(_fetch.ShareNotFoundError, match="Share not found"):
        _fetch.fetch(LINK, client=client)


def test_a_url_that_is_not_a_share_link_is_refused_without_a_request() -> None:
    client, seen = recording_client()
    with pytest.raises(_fetch.ShareNotFoundError, match="Not a Qwen share link"):
        _fetch.fetch("https://chat.qwen.ai/c/x", client=client)
    assert seen == []


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (404, _fetch.ShareNotFoundError),
        (401, _fetch.ShareAccessDeniedError),
        (403, _fetch.ShareAccessDeniedError),
        (429, _fetch.TransientFetchError),
        (500, _fetch.TransientFetchError),
        (418, _fetch.FetchError),
    ],
)
def test_status_codes_map_to_distinct_errors(status: int, expected: type) -> None:
    """Defensive, not observed from the endpoint: only 200 has been seen."""
    client, _ = recording_client(status=status)
    with pytest.raises(expected):
        _fetch.fetch(LINK, client=client)


def test_a_timeout_is_transient() -> None:
    with pytest.raises(_fetch.TransientFetchError, match="timed out"):
        _fetch.fetch(LINK, client=client_raising(httpx.TimeoutException("slow")))


def test_a_transport_failure_is_reported() -> None:
    with pytest.raises(_fetch.FetchError, match="Request failed"):
        _fetch.fetch(LINK, client=client_raising(httpx.ConnectError("no route")))
