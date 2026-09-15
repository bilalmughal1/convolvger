"""URL recognition for Claude public share links.

Only ``/share/<id>`` links are recognised. The share id is not
validated: observed ids are RFC-4122 UUIDs, but the ChatGPT adapter
learned that a stricter pattern risks rejecting links that work, and
the provider's own response is the authority on whether an id exists.

``claude.ai`` is the only host in the set because it is the only one
observed serving a share page. Anthropic publishes under other domains
too, and a host belongs here once a share link is seen on it, not
because it looks plausible.
"""

from urllib.parse import urlsplit

SHARE_HOSTS = frozenset({"claude.ai"})

SNAPSHOT_API = (
    "https://claude.ai/api/chat_snapshots/{share_id}"
    "?rendering_mode=messages&render_all_tools=true"
)
"""Where a browser gets the conversation behind a share page.

The share page renders nothing by itself; the conversation arrives from
this endpoint, which is keyed only on the share id -- no organization,
no session. Opened in a signed-out browser it returns the snapshot as
JSON, which is how this tool reaches a conversation it cannot fetch.

It is never fetched from here. A programmatic client is refused by the
bot wall in front of it whatever headers it sends, and impersonating a
browser to get past that is not something this tool does. A browser the
user drives is refused by nothing, so the path exists to be handed to
one. It is undocumented and may change without notice: if it stops
returning a snapshot, the URL built here is wrong.
"""


def share_id(url: str) -> str | None:
    """Return the share id in ``url``, or None if it is not a share link."""
    if not is_share_url(url):
        return None
    return [segment for segment in urlsplit(url).path.split("/") if segment][1]


def snapshot_url(url: str) -> str | None:
    """Return where a browser can read the snapshot behind ``url``."""
    identifier = share_id(url)
    if identifier is None:
        return None
    return SNAPSHOT_API.format(share_id=identifier)


def is_share_url(url: str) -> bool:
    """Return True if ``url`` is a Claude public conversation share link."""
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
