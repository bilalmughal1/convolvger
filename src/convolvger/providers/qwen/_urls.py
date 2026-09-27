"""URL recognition for Qwen public share links.

A share link is ``chat.qwen.ai/s/<id>``, usually with a ``fev`` query the
share dialog appends; the query is ignored, since the conversation is
named by the path. ``chat.qwenlm.ai`` answered the same share with the
same data, so it is recognised too and asked on its own host.

The web application answers every path with its shell and a 200, so a
page loading proves nothing about whether a form is a share link. Only
the ``/s/`` form is recognised, because it is the one share links take.
The id is not validated; the provider's own answer is the authority.
"""

from urllib.parse import quote, urlsplit

SHARE_HOSTS = frozenset({"chat.qwen.ai", "chat.qwenlm.ai"})

SHARE_API = "https://{host}/api/v2/chats/share/{share_id}"
"""Where the share page gets its conversation.

It answered this tool's own User-Agent with no cookie or token. It is
undocumented and may change without notice.
"""


def _parts(url: str) -> tuple[str, list[str]] | None:
    try:
        split = urlsplit(url)
        host = split.hostname or ""
    except ValueError:
        return None
    if split.scheme.lower() != "https":
        return None
    host = host.rstrip(".").removeprefix("www.")
    return host, [segment for segment in split.path.split("/") if segment]


def is_share_url(url: str) -> bool:
    """Return True if ``url`` is a Qwen public conversation share link."""
    parsed = _parts(url)
    if parsed is None:
        return False
    host, segments = parsed
    return host in SHARE_HOSTS and len(segments) == 2 and segments[0] == "s"


def share_id(url: str) -> str | None:
    """Return the share id in ``url``, or None if it is not a share link."""
    parsed = _parts(url)
    if parsed is None or not is_share_url(url):
        return None
    return parsed[1][1]


def api_url(url: str) -> str | None:
    """Return the endpoint that serves the conversation behind ``url``."""
    parsed = _parts(url)
    identifier = share_id(url)
    if parsed is None or identifier is None:
        return None
    return SHARE_API.format(host=parsed[0], share_id=quote(identifier, safe=""))
