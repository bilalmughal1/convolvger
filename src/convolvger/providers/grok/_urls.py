"""URL recognition for Grok public share links.

Only ``grok.com/share/<id>`` is recognised. ``www.grok.com`` was
observed redirecting to the bare host with the path intact, so it is
normalised away like every other provider's ``www.``.

The id is treated as one opaque segment. Observed ids are a base64
prefix, an underscore and a UUID -- the prefix has been seen decoding to
``legacy``, ``legacy-copy`` and ``shard-2`` -- but what the prefix means
is Grok's business, and a new one should not make a working link look
foreign. The provider validates the id itself: a malformed one was
measured returning ``Invalid uuid.``, so the authority on whether an id
exists is the response, not a pattern here.

A host belongs here once a share link is seen on it, not because it
looks plausible, so ``x.com``'s Grok pages are absent.
"""

from urllib.parse import urlsplit

SHARE_HOSTS = frozenset({"grok.com"})

SHARE_API = "https://grok.com/rest/app-chat/share_links/{share_id}"
"""Where the share page gets its conversation.

The page is an application shell; the conversation arrives as JSON from
this endpoint, keyed only on the share id. It answered this tool's own
User-Agent with no cookie and no bot wall. It is undocumented and may
change without notice.
"""


def is_share_url(url: str) -> bool:
    """Return True if ``url`` is a Grok public conversation share link."""
    try:
        parts = urlsplit(url)
        host = parts.hostname or ""
    except ValueError:
        return False

    if parts.scheme.lower() != "https":
        return False

    host = host.rstrip(".").removeprefix("www.")
    if host not in SHARE_HOSTS:
        return False

    segments = [segment for segment in parts.path.split("/") if segment]
    return len(segments) == 2 and segments[0] == "share"


def share_id(url: str) -> str | None:
    """Return the share id in ``url``, or None if it is not a share link."""
    if not is_share_url(url):
        return None
    return [segment for segment in urlsplit(url).path.split("/") if segment][1]


def api_url(url: str) -> str | None:
    """Return the endpoint that serves the conversation behind ``url``."""
    identifier = share_id(url)
    if identifier is None:
        return None
    return SHARE_API.format(share_id=identifier)
