"""The bookmarklet: a link that must survive being pasted into a browser."""

import re

from convolvger.capture.bookmarklet import RULES, bookmarklet
from convolvger.capture.server import DEFAULT_PORT


def test_it_is_a_javascript_link() -> None:
    assert bookmarklet().startswith("javascript:")


def test_it_points_at_the_port_the_listener_waits_on() -> None:
    assert f"127.0.0.1:{DEFAULT_PORT}/" in bookmarklet()


def test_a_chosen_port_is_carried_instead() -> None:
    """A port collision means regenerating this, so it has to be settable."""
    link = bookmarklet(port=9999)

    assert "127.0.0.1:9999/" in link
    assert f"127.0.0.1:{DEFAULT_PORT}/" not in link


def test_it_is_one_line_and_free_of_percent_escapes() -> None:
    """A browser decodes a javascript: URL before running it."""
    link = bookmarklet()

    assert "\n" not in link
    assert "%" not in link


def test_it_declines_pages_that_are_not_share_pages() -> None:
    link = bookmarklet()

    assert '"h":["claude.ai"],"p":"^/share/([^/?#]+)"' in link
    assert '"h":["www.perplexity.ai"],"p":"^/search/([^/?#]+)"' in link
    assert "open a share page first" in link


def test_it_reads_each_snapshot_from_the_providers_own_endpoint() -> None:
    link = bookmarklet()
    assert "https://claude.ai/api/chat_snapshots/{share_id}" in link
    assert "https://www.perplexity.ai/rest/thread/{share_id}?" in link


def test_every_rule_carries_a_path_with_one_group_for_the_id() -> None:
    """The browser runs the pattern; Python checks it means one thing."""
    for rule in RULES:
        assert re.compile(rule.path).groups == 1
        assert rule.path.startswith("^/")
        assert "{share_id}" in rule.api
        assert rule.hosts


def test_it_says_what_to_do_when_nothing_is_listening() -> None:
    """The likeliest failure is clicking before starting the command."""
    assert "nothing is listening" in bookmarklet()
