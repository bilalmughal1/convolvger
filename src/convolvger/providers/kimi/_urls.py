"""URL recognition for Kimi public share links.

A share link is ``<host>/share/<id>``. Three hosts were observed serving
the same share: ``www.kimi.ai``, ``www.kimi.com``, and the older
``kimi.moonshot.cn``, which redirects to ``www.kimi.com`` keeping the
id. Each bare domain redirects to its ``www`` form, so ``www.`` is
normalised away as it is for every other provider.

Kimi's router also declares ``/share/<lang>/<id>``, but both forms tried
redirected to the home page rather than to a share, so a path with three
segments is not recognised. A host or form belongs here once a share was
seen on it.

The id is not validated. The one observed is UUID-shaped, but the
provider's own answer is the authority on whether an id exists.
"""

from urllib.parse import urlsplit

API_HOSTS = {
    "kimi.ai": "www.kimi.ai",
    "kimi.com": "www.kimi.com",
    "kimi.moonshot.cn": "www.kimi.com",
}
"""Where each share host's conversation is asked for.

Both ``www`` hosts answered the same share with the same bytes. The link's
own host is kept rather than one being picked for every link, so a link
is answered by the service it names; the old Moonshot host goes where it
redirects.
"""

SERVICE_PATH = "/apiv2/kimi.gateway.chat.v1.ChatService/GetChatShare"


def _host(url: str) -> tuple[str, list[str]] | None:
    try:
        parts = urlsplit(url)
        host = parts.hostname or ""
    except ValueError:
        return None
    if parts.scheme.lower() != "https":
        return None
    host = host.rstrip(".").removeprefix("www.")
    return host, [segment for segment in parts.path.split("/") if segment]


def is_share_url(url: str) -> bool:
    """Return True if ``url`` is a Kimi public conversation share link."""
    parsed = _host(url)
    if parsed is None:
        return False
    host, segments = parsed
    return host in API_HOSTS and len(segments) == 2 and segments[0] == "share"


def share_id(url: str) -> str | None:
    """Return the share id in ``url``, or None if it is not a share link."""
    parsed = _host(url)
    if parsed is None or not is_share_url(url):
        return None
    return parsed[1][1]


def api_url(url: str) -> str | None:
    """Return the endpoint that serves the conversation behind ``url``."""
    parsed = _host(url)
    if parsed is None or not is_share_url(url):
        return None
    return f"https://{API_HOSTS[parsed[0]]}{SERVICE_PATH}"
