"""What a capture provider tells the bookmarklet about its share pages.

A provider whose conversation cannot be fetched -- the data behind the
page sits behind a bot wall -- is captured instead: the bookmarklet runs
on the share page in the reader's own browser and asks for the data the
page itself asks for. Each such provider declares where its share pages
are and where their data is, and the bookmarklet tries each declaration
in turn. Nothing in the bookmarklet is specific to a provider.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class CaptureRule:
    """Where one provider's share pages are, and where their data is read.

    ``hosts`` are matched exactly against the page's host name, as the
    browser reports it: only hosts a share page was seen on. ``path`` is
    a regular expression for the page's path whose first group is the
    share id; it is run by the browser, so it must mean the same in
    JavaScript as in Python. ``api`` is the address the page itself was
    measured reading its data from, with ``{share_id}`` in place of the
    id.
    """

    hosts: frozenset[str]
    path: str
    api: str
