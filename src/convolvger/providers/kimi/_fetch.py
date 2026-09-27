"""HTTP retrieval of Kimi public share conversations.

A Kimi share page is an application shell. It loads its conversation
through a Connect RPC, ``kimi.gateway.chat.v1.ChatService/GetChatShare``,
which is a POST of a small JSON body naming the share. This makes the
same call directly, so no browser is involved and nothing is scraped.

Only ``shareId`` is sent. The page also sends a message order, and the
answer was measured identical without it. The ``Connect-Protocol-Version``
header the page sends was likewise measured unnecessary. No cookie is
sent and no token is needed: the request succeeds with this tool's own
User-Agent, so nothing here impersonates a browser.

An unknown share id answers 404 with Connect's ``not_found`` code, and
so does a malformed one. A deleted share was not tried. A share that
exists but holds no messages has not been seen; it is refused anyway,
because an archive of a title alone would pass an empty conversation off
as a real one.

Errors are defined here rather than in the core because the mapping from
status code to meaning is provider-specific, matching the other adapters.
"""

import json
from datetime import UTC, datetime
from importlib.metadata import version

import httpx

from convolvger.core.errors import ConvolvgerError
from convolvger.core.source import RawSource
from convolvger.providers.kimi._parse import carries_nothing
from convolvger.providers.kimi._urls import api_url, share_id

USER_AGENT = (
    f"convolvger/{version('convolvger')} (+https://github.com/bilalmughal1/convolvger)"
)
TIMEOUT = httpx.Timeout(30.0)


class FetchError(ConvolvgerError):
    """Raised when a share conversation cannot be retrieved."""


class ShareNotFoundError(FetchError):
    """The share link does not resolve to a conversation."""


class ShareAccessDeniedError(FetchError):
    """The share link exists but access was refused."""


class TransientFetchError(FetchError):
    """The provider signalled a temporary failure."""


def _build_client() -> httpx.Client:
    return httpx.Client(
        follow_redirects=True,
        timeout=TIMEOUT,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )


def _is_empty(body: str) -> bool:
    """True when the endpoint answered 200 but carried no conversation."""
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return False
    return carries_nothing(payload)


def fetch(url: str, *, client: httpx.Client | None = None) -> RawSource:
    """Retrieve the raw share JSON for a Kimi share URL.

    ``client`` is injectable so tests can supply a mock transport. The
    URL is recorded exactly as supplied, not the endpoint it was read
    from, so an archive names the link a reader would visit.
    """
    endpoint = api_url(url)
    identifier = share_id(url)
    if endpoint is None or identifier is None:
        raise ShareNotFoundError(f"Not a Kimi share link: {url}")

    owned = client is None
    active = client or _build_client()
    try:
        try:
            response = active.post(endpoint, json={"shareId": identifier})
        except httpx.TimeoutException as exc:
            raise TransientFetchError(f"Request timed out: {url}") from exc
        except httpx.HTTPError as exc:
            raise FetchError(f"Request failed: {exc}") from exc

        status = response.status_code
        if status in (400, 404):
            raise ShareNotFoundError(
                f"Share not found (deleted, never existed, or made private): {url}"
            )
        if status in (401, 403):
            raise ShareAccessDeniedError(
                f"Access refused (private, unshared, or blocked): {url}"
            )
        if status == 429 or status >= 500:
            raise TransientFetchError(f"Provider returned {status}, retry later: {url}")
        if status != 200:
            raise FetchError(f"Unexpected status {status}: {url}")

        if _is_empty(response.text):
            raise ShareNotFoundError(
                f"Share not found (deleted, never existed, or made private): {url}"
            )

        return RawSource(
            url=url,
            content=response.text,
            content_type=response.headers.get("content-type"),
            fetched_at=datetime.now(UTC),
        )
    finally:
        if owned:
            active.close()
