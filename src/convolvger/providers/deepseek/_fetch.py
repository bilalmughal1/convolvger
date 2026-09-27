"""HTTP retrieval of DeepSeek public share conversations.

The share page refused every client tried with a 403 from its CDN,
whatever User-Agent was sent and with none at all, so it is never asked
for. The conversation the page would load comes from a JSON endpoint,
and that answered this tool's own User-Agent with no cookie and no
token. Nothing here impersonates a browser.

It is the same call the page itself makes. A HAR capture of a real
Chrome session opening a share showed the page's own script requesting
``/api/v0/share/content?share_id=...`` with no cookies, the share page
as referer, and ``sec-fetch-site: same-origin``. Nothing is asked for
that a visitor's browser does not already ask for.

``robots.txt``, as fetched in a browser, reads ``User-agent: *`` and
``Disallow: /share/``. That disallows the share page for crawlers; by
prefix matching it does not cover ``/api/v0/share/content``. It is
still evidence that DeepSeek does not want share links crawled or
indexed at scale. This tool does not do that: it fetches the one link a
person supplied, makes the call the page makes, identifies itself as
``convolvger/<version>``, and never enumerates share ids.

Whether a share exists is decided by the body, not the status. An unknown
share id answers 200 with ``biz_code`` 1, "share does not exist", as Gemini
answers 200 with a null payload. An unknown path on the same host
answers 200 with the web application's HTML; that is left to the parser
to refuse as not JSON.

Errors are defined here rather than in the core because the mapping from
status code to meaning is provider-specific, matching the other adapters.
"""

import json
from datetime import UTC, datetime
from importlib.metadata import version

import httpx

from convolvger.core.errors import ConvolvgerError
from convolvger.core.source import RawSource
from convolvger.providers.deepseek._parse import carries_nothing
from convolvger.providers.deepseek._urls import api_url

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
    """Retrieve the raw share JSON for a DeepSeek share URL.

    ``client`` is injectable so tests can supply a mock transport. The
    URL is recorded exactly as supplied, not the endpoint it was read
    from, so an archive names the link a reader would visit.
    """
    endpoint = api_url(url)
    if endpoint is None:
        raise ShareNotFoundError(f"Not a DeepSeek share link: {url}")

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
