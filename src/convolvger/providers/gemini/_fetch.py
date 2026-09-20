"""HTTP retrieval of Gemini public share conversations.

A Gemini share page carries no conversation in its HTML: the document is
an application shell, and the conversation is loaded afterwards from a
batchexecute endpoint. Fetching the page would return 840KB of shell
holding Google's own marketing examples, so this asks the endpoint
directly for the same data the page itself requests.

Only ``rpcids`` is sent. The browser also sends ``source-path``, ``bl``
and ``rt``, and each was measured to be optional: the response carried
the same conversation without them. ``bl`` identifies a Google build and
would have to be updated whenever they ship one, so pinning it would
have been a standing liability for no gain. Dropping ``rt`` returns the
unchunked form of the response, which the decoder reads as readily as
the chunked one.

No cookie is sent and no token is needed. The request succeeds with this
tool's own User-Agent, so nothing here impersonates a browser.

Errors are defined here rather than in the core because the mapping from
status code to meaning is provider-specific, matching the ChatGPT
adapter's reasoning.
"""

import json
from datetime import UTC, datetime
from importlib.metadata import version
from urllib.parse import urlencode

import httpx

from convolvger.core.errors import ConvolvgerError
from convolvger.core.source import RawSource
from convolvger.providers.gemini._batchexecute import BatchExecuteError, decode
from convolvger.providers.gemini._parse import CONVERSATION_RPC
from convolvger.providers.gemini._urls import share_id

USER_AGENT = f"convolvger/{version('convolvger')} (+https://github.com/bilalmughal1/convolvger)"
TIMEOUT = httpx.Timeout(30.0)

ENDPOINT = "https://gemini.google.com/_/BardChatUi/data/batchexecute"

COMPACT = (",", ":")
"""The browser sends no whitespace in f.req; this matches it exactly."""


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
        headers={"User-Agent": USER_AGENT},
    )


def _request_body(conversation_id: str) -> str:
    """Build the f.req form field the endpoint expects.

    The trailing ``[4]`` is sent verbatim by the browser. Its meaning was
    not established, so it is reproduced rather than reinterpreted.
    """
    inner = json.dumps([None, conversation_id, [4]], separators=COMPACT)
    outer = json.dumps([[[CONVERSATION_RPC, inner, None, "generic"]]], separators=COMPACT)
    return urlencode({"f.req": outer, "at": ""})


def _is_empty(body: str) -> bool:
    """True when the endpoint answered 200 but carried no conversation.

    Measured: an unknown or malformed share id returns 200 with a
    ``wrb.fr`` envelope whose payload is null, so status alone cannot
    tell a missing share from a present one.
    """
    try:
        result = decode(body)
    except BatchExecuteError:
        return False
    return all(
        item.payload is None for item in result.envelopes if item.rpc_id == CONVERSATION_RPC
    )


def _resolve(url: str, client: httpx.Client) -> str:
    """Return the conversation id for ``url``, following one redirect if needed.

    Two of the three share forms carry the id in the path. The shortener
    does not, and its redirect is the only way to learn it, so that one
    form costs an extra request -- answered from the Location header
    rather than by downloading the page it points at.
    """
    known = share_id(url)
    if known is not None:
        return known

    try:
        response = client.get(url, follow_redirects=False)
    except httpx.TimeoutException as exc:
        raise TransientFetchError(f"Request timed out resolving: {url}") from exc
    except httpx.HTTPError as exc:
        raise FetchError(f"Could not resolve share link: {exc}") from exc

    location = response.headers.get("location")
    if not location:
        raise ShareNotFoundError(f"Share link did not redirect to a conversation: {url}")

    resolved = share_id(location)
    if resolved is None:
        raise ShareNotFoundError(f"Share link resolved to an unrecognised target: {location}")
    return resolved


def fetch(url: str, *, client: httpx.Client | None = None) -> RawSource:
    """Retrieve the raw batchexecute response for a Gemini share URL.

    ``client`` is injectable so tests can supply a mock transport. The
    URL is recorded exactly as supplied, not the endpoint it was read
    from, so an archive names the link a reader would visit.
    """
    owned = client is None
    active = client or _build_client()
    try:
        conversation_id = _resolve(url, active)
        try:
            response = active.post(
                ENDPOINT,
                params={"rpcids": CONVERSATION_RPC},
                content=_request_body(conversation_id),
                headers={"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"},
            )
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
