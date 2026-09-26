"""HTTP retrieval of Grok public share conversations.

A Grok share page carries no conversation in its HTML: it is an
application shell that asks a JSON endpoint for one afterwards. This
asks the same endpoint directly, so no browser is involved and nothing
is scraped.

No cookie is sent and no token is needed. The request succeeds with this
tool's own User-Agent, so nothing here impersonates a browser.

Two failures were measured rather than assumed. An unknown or deleted
share answers 404 with ``{"code":5,"message":"Cannot find
conversation."}``, and an id whose UUID part is malformed answers 400
with ``Invalid uuid.``. Both mean the link names no conversation, so
both are reported as a missing share. A third answers 200 and still
carries nothing: a real public share was seen returning its title with
an empty ``responses`` list. Status alone cannot tell that from a
conversation, so the body is checked too, as Gemini's empty success is.

Errors are defined here rather than in the core because the mapping from
status code to meaning is provider-specific, matching the ChatGPT
adapter's reasoning.
"""

import json
from datetime import UTC, datetime
from importlib.metadata import version

import httpx

from convolvger.core.errors import ConvolvgerError
from convolvger.core.source import RawSource
from convolvger.providers.grok._parse import carries_nothing
from convolvger.providers.grok._urls import api_url

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
    """True when the endpoint answered 200 but carried no conversation.

    A body that is not JSON is not judged here: that is the parser's to
    refuse, with its own message.
    """
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return False
    return carries_nothing(payload)


def fetch(url: str, *, client: httpx.Client | None = None) -> RawSource:
    """Retrieve the raw share JSON for a Grok share URL.

    ``client`` is injectable so tests can supply a mock transport. The
    URL is recorded exactly as supplied, not the endpoint it was read
    from, so an archive names the link a reader would visit.
    """
    endpoint = api_url(url)
    if endpoint is None:
        raise ShareNotFoundError(f"Not a Grok share link: {url}")

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
