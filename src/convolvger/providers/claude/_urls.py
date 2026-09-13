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
