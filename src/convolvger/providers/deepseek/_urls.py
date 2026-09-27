"""URL recognition for DeepSeek public share links.

Only ``chat.deepseek.com/share/<id>`` is recognised: ``deepseek.com`` and
``www.deepseek.com`` answered 404 for the same path, so they are not share
hosts. The one observed id is 18 lowercase letters and digits; it is not
validated, since the provider's own answer is the authority on whether an
id exists.
"""

from urllib.parse import quote, urlsplit

SHARE_HOSTS = frozenset({"chat.deepseek.com"})

CONTENT_API = "https://chat.deepseek.com/api/v0/share/content?share_id={share_id}"
"""Where the share page gets its conversation.

The share page itself refused every client tried with a CDN 403, whatever
User-Agent was sent or none. This endpoint answered this tool's own
User-Agent with no cookie or token. It is undocumented and may change
without notice.
"""


def is_share_url(url: str) -> bool:
    """Return True if ``url`` is a DeepSeek public conversation share link."""
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
    return CONTENT_API.format(share_id=quote(identifier, safe=""))
