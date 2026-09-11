"""URL recognition for ChatGPT public share links.

Only ``/share/<id>`` links are recognised. The share id itself is not
validated: observed ids are not RFC-4122 version 4 UUIDs, so any stricter
pattern risks rejecting links that work. An unrecognised id is left to
fail at fetch time, where the provider's response is authoritative.
"""

from urllib.parse import urlsplit

SHARE_HOSTS = frozenset({"chatgpt.com", "chat.openai.com"})


def is_share_url(url: str) -> bool:
    """Return True if ``url`` is a ChatGPT public conversation share link."""
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
