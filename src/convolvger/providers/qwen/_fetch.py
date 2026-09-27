"""HTTP retrieval of Qwen public share conversations.

A Qwen share page is an application shell; the conversation arrives
afterwards from a JSON endpoint, which this asks directly. No cookie is
sent and no token is needed: the request succeeds with this tool's own
User-Agent, so nothing here impersonates a browser.

Whether a share exists is decided by the body, not the status. An
unknown or malformed id answers 200 with ``success`` false and a
``Not_Found`` code, as Gemini answers 200 with a null payload.

Errors are defined here rather than in the core because the mapping from
status code to meaning is provider-specific, matching the other adapters.
"""

import json
from datetime import UTC, datetime
from importlib.metadata import version

import httpx

from convolvger.core.errors import ConvolvgerError
from convolvger.core.source import RawSource
from convolvger.providers.qwen._parse import carries_nothing
from convolvger.providers.qwen._urls import api_url

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
    """Retrieve the raw share JSON for a Qwen share URL.

    ``client`` is injectable so tests can supply a mock transport. The
    URL is recorded exactly as supplied, not the endpoint it was read
    from, so an archive names the link a reader would visit.
    """
    endpoint = api_url(url)
    if endpoint is None:
        raise ShareNotFoundError(f"Not a Qwen share link: {url}")

    owned = client is None
    active = client or _build_client()
    try:
        try:
            response = active.get(endpoint)
        except httpx.TimeoutException as exc:
            raise TransientFetchError(f"Request timed out: {url}") from exc
        except httpx.HTTPError as exc:
            raise FetchError(f"Request failed: {exc}") from exc

        status = response.status_code
        if status == 404:
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
