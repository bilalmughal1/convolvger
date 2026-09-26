"""HTTP retrieval of ChatGPT public share snapshots.

Errors are defined here rather than in the core: the mapping from status
code to meaning has only been verified against ChatGPT, and other
providers expose different failure behaviour. They subclass
``ConvolvgerError`` so callers can catch a single base type.
"""

from datetime import UTC, datetime
from importlib.metadata import version

import httpx

from convolvger.core.errors import ConvolvgerError
from convolvger.core.source import RawSource

USER_AGENT = (
    f"convolvger/{version('convolvger')} (+https://github.com/bilalmughal1/convolvger)"
)
TIMEOUT = httpx.Timeout(30.0)


class FetchError(ConvolvgerError):
    """Raised when a share snapshot cannot be retrieved."""


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
        headers={"User-Agent": USER_AGENT},
    )


def fetch(url: str, *, client: httpx.Client | None = None) -> RawSource:
    """Retrieve the raw HTML snapshot for a ChatGPT share URL.

    ``client`` is injectable so tests can supply a mock transport. The
    URL is recorded exactly as supplied, without normalisation.
    """
    owned = client is None
    active = client or _build_client()
    try:
        try:
            response = active.get(url)
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

        return RawSource(
            url=url,
            content=response.text,
            content_type=response.headers.get("content-type"),
            fetched_at=datetime.now(UTC),
        )
    finally:
        if owned:
            active.close()
