import json

import httpx
import pytest

from convolvger.providers.kimi import _fetch

SHARE_ID = "00000000-0000-4000-8000-000000000002"
LINK = f"https://www.kimi.ai/share/{SHARE_ID}"
ENDPOINT = "https://www.kimi.ai/apiv2/kimi.gateway.chat.v1.ChatService/GetChatShare"
BODY = json.dumps(
    {"share": {"id": SHARE_ID, "messages": [{"id": "m", "role": "user"}]}}
)
NOT_FOUND = json.dumps(
    {
        "code": "not_found",
        "details": [{"debug": {"reason": "REASON_CHAT_NOT_FOUND"}}],
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


def test_posts_only_the_share_id_to_the_connect_method() -> None:
    client, seen = recording_client()
    _fetch.fetch(LINK, client=client)

    assert len(seen) == 1
    assert seen[0].method == "POST"
    assert str(seen[0].url) == ENDPOINT
    assert json.loads(seen[0].content) == {"shareId": SHARE_ID}


def test_sends_no_cookie_or_token() -> None:
    client, seen = recording_client()
    _fetch.fetch(LINK, client=client)

    headers = {name.lower() for name in seen[0].headers}
    assert "cookie" not in headers
    assert "authorization" not in headers


def test_the_old_moonshot_host_is_asked_where_it_redirects() -> None:
    client, seen = recording_client()
    _fetch.fetch(f"https://kimi.moonshot.cn/share/{SHARE_ID}", client=client)
    assert str(seen[0].url).startswith("https://www.kimi.com/apiv2/")


def test_records_the_share_url_not_the_endpoint() -> None:
    client, _ = recording_client()
    source = _fetch.fetch(LINK, client=client)
    assert source.url == LINK
    assert source.content == BODY
    assert source.fetched_at is not None


def test_a_url_that_is_not_a_share_link_is_refused_without_a_request() -> None:
    client, seen = recording_client()
    with pytest.raises(_fetch.ShareNotFoundError, match="Not a Kimi share link"):
        _fetch.fetch("https://www.kimi.ai/chat/abc", client=client)
    assert seen == []


def test_a_missing_share_is_reported() -> None:
    """Measured: an unknown and a malformed id both answer 404 not_found."""
    client, _ = recording_client(status=404, body=NOT_FOUND)
    with pytest.raises(_fetch.ShareNotFoundError, match="Share not found"):
        _fetch.fetch(LINK, client=client)


def test_a_share_with_no_messages_is_reported_despite_a_200() -> None:
    """Not observed; protobuf would omit the empty list, so none is sent."""
    client, _ = recording_client(body=json.dumps({"share": {"id": SHARE_ID}}))
    with pytest.raises(_fetch.ShareNotFoundError, match="Share not found"):
        _fetch.fetch(LINK, client=client)


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (400, _fetch.ShareNotFoundError),
        (401, _fetch.ShareAccessDeniedError),
        (403, _fetch.ShareAccessDeniedError),
        (429, _fetch.TransientFetchError),
        (500, _fetch.TransientFetchError),
        (503, _fetch.TransientFetchError),
        (418, _fetch.FetchError),
    ],
)
def test_status_codes_map_to_distinct_errors(status: int, expected: type) -> None:
    """Defensive, not observed: only 200 and 404 have been seen."""
    client, _ = recording_client(status=status)
    with pytest.raises(expected):
        _fetch.fetch(LINK, client=client)


def test_a_timeout_is_transient() -> None:
    client = client_raising(httpx.TimeoutException("slow"))
    with pytest.raises(_fetch.TransientFetchError, match="timed out"):
        _fetch.fetch(LINK, client=client)


def test_a_transport_failure_is_reported() -> None:
    client = client_raising(httpx.ConnectError("no route"))
    with pytest.raises(_fetch.FetchError, match="Request failed"):
        _fetch.fetch(LINK, client=client)
