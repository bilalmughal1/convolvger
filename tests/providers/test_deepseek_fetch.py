import json

import httpx
import pytest

from convolvger.providers.deepseek import _fetch

LINK = "https://chat.deepseek.com/share/0example0share0id"
ENDPOINT = "https://chat.deepseek.com/api/v0/share/content?share_id=0example0share0id"
BODY = json.dumps(
    {
        "code": 0,
        "msg": "",
        "data": {
            "biz_code": 0,
            "biz_msg": "",
            "biz_data": {"messages": [{"message_id": 1}]},
        },
    }
)
MISSING = json.dumps(
    {
        "code": 0,
        "msg": "",
        "data": {"biz_code": 1, "biz_msg": "share does not exist", "biz_data": None},
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


def test_gets_the_data_endpoint_once_and_never_the_page() -> None:
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
    """Measured: an unknown id answers 200 with biz_code 1."""
    client, _ = recording_client(body=MISSING)
    with pytest.raises(_fetch.ShareNotFoundError, match="Share not found"):
        _fetch.fetch(LINK, client=client)


def test_an_html_answer_is_left_for_the_parser_to_refuse() -> None:
    """Unknown paths on the host answer the web application with a 200."""
    client, _ = recording_client(body="<!doctype html><title>DeepSeek</title>")
    assert _fetch.fetch(LINK, client=client).content.startswith("<!doctype")


def test_a_url_that_is_not_a_share_link_is_refused_without_a_request() -> None:
    client, seen = recording_client()
    with pytest.raises(_fetch.ShareNotFoundError, match="Not a DeepSeek share link"):
        _fetch.fetch("https://deepseek.com/share/x", client=client)
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
