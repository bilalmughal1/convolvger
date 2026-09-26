import json

import httpx
import pytest

from convolvger.providers.grok import _fetch

SHARE_ID = "bGVnYWN5_00000000-0000-4000-8000-000000000001"
CANONICAL = f"https://grok.com/share/{SHARE_ID}"
ENDPOINT = f"https://grok.com/rest/app-chat/share_links/{SHARE_ID}"
BODY = json.dumps(
    {
        "conversation": {"conversationId": "c", "title": "t"},
        "responses": [{"responseId": "r", "sender": "human", "message": "hi"}],
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


def test_gets_the_share_endpoint_once() -> None:
    client, seen = recording_client()
    _fetch.fetch(CANONICAL, client=client)

    assert [(request.method, str(request.url)) for request in seen] == [
        ("GET", ENDPOINT)
    ]


def test_a_decorated_link_asks_for_the_same_endpoint() -> None:
    client, seen = recording_client()
    _fetch.fetch(f"https://www.grok.com/share/{SHARE_ID}/?ref=x#y", client=client)
    assert str(seen[0].url) == ENDPOINT


def test_sends_no_cookie_or_token() -> None:
    client, seen = recording_client()
    _fetch.fetch(CANONICAL, client=client)

    headers = {name.lower() for name in seen[0].headers}
    assert "cookie" not in headers
    assert "authorization" not in headers


def test_records_the_share_url_not_the_endpoint() -> None:
    client, _ = recording_client()
    source = _fetch.fetch(CANONICAL, client=client)
    assert source.url == CANONICAL
    assert source.content == BODY
    assert source.content_type == "application/json"
    assert source.fetched_at is not None


def test_a_url_that_is_not_a_share_link_is_refused_without_a_request() -> None:
    client, seen = recording_client()
    with pytest.raises(_fetch.ShareNotFoundError, match="Not a Grok share link"):
        _fetch.fetch("https://grok.com/chat/abc", client=client)
    assert seen == []


def test_a_missing_share_is_reported() -> None:
    """Measured: an unknown id answers 404 with gRPC code 5."""
    body = '{"code":5,"message":"Cannot find conversation.","details":[]}'
    client, _ = recording_client(status=404, body=body)
    with pytest.raises(_fetch.ShareNotFoundError, match="Share not found"):
        _fetch.fetch(CANONICAL, client=client)


def test_a_malformed_id_is_reported_as_a_missing_share() -> None:
    """Measured: an id whose UUID part is malformed answers 400."""
    body = '{"code":3,"message":"Invalid uuid.","details":[]}'
    client, _ = recording_client(status=400, body=body)
    with pytest.raises(_fetch.ShareNotFoundError, match="Share not found"):
        _fetch.fetch(CANONICAL, client=client)


def test_a_share_with_no_responses_is_reported_despite_a_200() -> None:
    """Measured: a public share answered 200 with a title and nothing else."""
    body = json.dumps({"conversation": {"title": "Kept"}, "responses": []})
    client, _ = recording_client(body=body)
    with pytest.raises(_fetch.ShareNotFoundError, match="Share not found"):
        _fetch.fetch(CANONICAL, client=client)


def test_a_body_that_is_not_json_is_left_for_the_parser() -> None:
    client, _ = recording_client(body="<html></html>")
    assert _fetch.fetch(CANONICAL, client=client).content == "<html></html>"


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (401, _fetch.ShareAccessDeniedError),
        (403, _fetch.ShareAccessDeniedError),
        (429, _fetch.TransientFetchError),
        (500, _fetch.TransientFetchError),
        (503, _fetch.TransientFetchError),
        (418, _fetch.FetchError),
    ],
)
def test_status_codes_map_to_distinct_errors(status: int, expected: type) -> None:
    """Defensive, not observed: only 200, 400 and 404 have been seen."""
    client, _ = recording_client(status=status)
    with pytest.raises(expected):
        _fetch.fetch(CANONICAL, client=client)


def test_a_timeout_is_transient() -> None:
    client = client_raising(httpx.TimeoutException("slow"))
    with pytest.raises(_fetch.TransientFetchError, match="timed out"):
        _fetch.fetch(CANONICAL, client=client)


def test_a_transport_failure_is_reported() -> None:
    client = client_raising(httpx.ConnectError("no route"))
    with pytest.raises(_fetch.FetchError, match="Request failed"):
        _fetch.fetch(CANONICAL, client=client)
