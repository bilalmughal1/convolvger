"""The bookmarklet: a link that must survive being pasted into a browser."""

from convolvger.capture.bookmarklet import bookmarklet
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

    assert "claude.ai" in link
    assert r"\/share\/" in link
    assert "open a share page first" in link


def test_it_reads_the_snapshot_from_the_providers_own_endpoint() -> None:
    assert "api/chat_snapshots/" in bookmarklet()


def test_it_says_what_to_do_when_nothing_is_listening() -> None:
    """The likeliest failure is clicking before starting the command."""
    assert "nothing is listening" in bookmarklet()
