from urllib.parse import parse_qs

import httpx
import pytest

from convolvger.providers.gemini import _fetch

CANONICAL = "https://gemini.google.com/share/09bcf760b07b"
ALIAS = "https://g.co/gemini/share/09bcf760b07b"
SHORT = "https://share.gemini.google/94ESiKYXbGiV"
BODY = ")]}'\n\n[[\"wrb.fr\",\"ujx1Bf\",\"[]\",null,null,null,\"generic\"]]"


def recording_client(
    *, status: int = 200, body: str = BODY, location: str | None = CANONICAL
) -> tuple[httpx.Client, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.method == "GET":
            headers = {"location": location} if location else {}
            return httpx.Response(301, headers=headers)
        return httpx.Response(
            status, text=body, headers={"content-type": "application/json"}
        )

    return httpx.Client(transport=httpx.MockTransport(handler)), seen


def client_raising(error: Exception) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        raise error

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_posts_the_measured_request_to_the_endpoint() -> None:
    client, seen = recording_client()
    _fetch.fetch(CANONICAL, client=client)

    assert len(seen) == 1
    request = seen[0]
    assert request.method == "POST"
    assert str(request.url).startswith(_fetch.ENDPOINT)
    assert parse_qs(request.url.query.decode())["rpcids"] == ["ujx1Bf"]

    sent = parse_qs(request.content.decode())["f.req"][0]
    assert sent == '[[["ujx1Bf","[null,\\"09bcf760b07b\\",[4]]",null,"generic"]]]'


def test_sends_no_build_identifier_or_cookie() -> None:
    """bl, source-path and rt were each measured to be optional."""
    client, seen = recording_client()
    _fetch.fetch(CANONICAL, client=client)

    query = parse_qs(seen[0].url.query.decode())
    assert "bl" not in query
    assert "rt" not in query
    assert "source-path" not in query
    assert "cookie" not in {name.lower() for name in seen[0].headers}


def test_records_the_share_url_not_the_endpoint() -> None:
    client, _ = recording_client()
    source = _fetch.fetch(CANONICAL, client=client)
    assert source.url == CANONICAL
    assert source.content == BODY
    assert source.fetched_at is not None


def test_a_canonical_url_costs_no_resolving_request() -> None:
    client, seen = recording_client()
    _fetch.fetch(CANONICAL, client=client)
    assert [request.method for request in seen] == ["POST"]


def test_the_alias_form_also_resolves_without_a_request() -> None:
    client, seen = recording_client()
    _fetch.fetch(ALIAS, client=client)
    assert [request.method for request in seen] == ["POST"]


def test_a_short_link_is_resolved_from_the_redirect() -> None:
    client, seen = recording_client()
    _fetch.fetch(SHORT, client=client)

    assert [request.method for request in seen] == ["GET", "POST"]
    sent = parse_qs(seen[1].content.decode())["f.req"][0]
    assert "09bcf760b07b" in sent


def test_a_short_link_that_does_not_redirect_is_refused() -> None:
    client, _ = recording_client(location=None)
    with pytest.raises(_fetch.ShareNotFoundError, match="did not redirect"):
        _fetch.fetch(SHORT, client=client)


def test_a_short_link_redirecting_elsewhere_is_refused() -> None:
    client, _ = recording_client(location="https://example.com/somewhere")
    with pytest.raises(_fetch.ShareNotFoundError, match="unrecognised target"):
        _fetch.fetch(SHORT, client=client)


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (404, _fetch.ShareNotFoundError),
        (401, _fetch.ShareAccessDeniedError),
        (403, _fetch.ShareAccessDeniedError),
        (429, _fetch.TransientFetchError),
        (500, _fetch.TransientFetchError),
        (503, _fetch.TransientFetchError),
        (418, _fetch.FetchError),
    ],
)
def test_status_codes_map_to_distinct_errors(status: int, expected: type) -> None:
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


MISSING_SHARE = (
    ")]}'\n\n"
    '[["wrb.fr","ujx1Bf",null,null,null,[5],"generic"],'
    '["di",172],["af.httprm",172,"-1490094734237710798",11]]'
)


def test_a_missing_share_is_reported_despite_a_200() -> None:
    """Measured: Gemini answers 200 for an unknown id, never 404."""
    client, _ = recording_client(body=MISSING_SHARE)
    with pytest.raises(_fetch.ShareNotFoundError, match="Share not found"):
        _fetch.fetch(CANONICAL, client=client)
