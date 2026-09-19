"""URL recognition for Gemini public share links.

Three host forms were observed serving the same conversation, and they
do not agree on where the share id lives:

``gemini.google.com/share/<id>``
    The canonical form. Returns 200 directly and carries the id.
``g.co/gemini/share/<id>``
    The link Google's own share dialog copies. Redirects to the
    canonical form carrying **the same id**, so it is a path alias
    rather than a shortener and the id is read straight from it.
``share.gemini.google/<token>``
    A genuine shortener: its token is not the conversation id, and the
    canonical id is only learned by following the redirect.

``share_id`` therefore returns None for the shortener while still
recognising it, and resolving that one form is left to the fetcher,
where a network round trip belongs. Two of the three forms cost no
extra request.

The id itself is not validated. Observed ids are 12 hex characters, but
the ChatGPT adapter learned that a stricter pattern risks rejecting
links that work, and the provider's own response is the authority on
whether an id exists.

A host belongs here once a share link is seen on it, not because it
looks plausible.
"""

from urllib.parse import urlsplit

CANONICAL_HOST = "gemini.google.com"
ALIAS_HOST = "g.co"
SHORTENER_HOST = "share.gemini.google"


def _parts(url: str) -> tuple[str, list[str]] | None:
    """Return the normalised host and path segments, or None if unusable."""
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
    """Return True if ``url`` is a Gemini public conversation share link."""
    parsed = _parts(url)
    if parsed is None:
        return False

    host, segments = parsed
    if host == CANONICAL_HOST:
        return len(segments) == 2 and segments[0] == "share"
    if host == ALIAS_HOST:
        return len(segments) == 3 and segments[:2] == ["gemini", "share"]
    if host == SHORTENER_HOST:
        return len(segments) == 1
    return False


def share_id(url: str) -> str | None:
    """Return the conversation id in ``url``.

    None means the id is not derivable from the URL alone -- either
    because ``url`` is not a share link at all, or because it is a
    shortened one whose token must be resolved over the network.
    ``is_share_url`` distinguishes the two.
    """
    parsed = _parts(url)
    if parsed is None or not is_share_url(url):
        return None

    host, segments = parsed
    if host == CANONICAL_HOST:
        return segments[1]
    if host == ALIAS_HOST:
        return segments[2]
    return None
