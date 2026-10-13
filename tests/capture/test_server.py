"""The capture listener: what it accepts, and what it refuses to believe."""

import json
import socket
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

import pytest

from convolvger.capture.server import DEFAULT_PORT, CaptureError, wait_for_snapshot
from convolvger.core.source import RawSource

PORT = DEFAULT_PORT + 1
SHARE = "https://claude.ai/share/00000000-0000-0000-0000-000000000000"


class Listener:
    """Runs one wait_for_snapshot in a thread so a test can post to it."""

    def __init__(
        self, timeout: float = 5.0, accepts: Callable[[str], bool] | None = None
    ) -> None:
        self.source: RawSource | None = None
        self.error: CaptureError | None = None
        self._thread = threading.Thread(target=self._run, args=(timeout, accepts))
        self._ready = threading.Event()

    def _run(self, timeout: float, accepts: Callable[[str], bool] | None) -> None:
        self._ready.set()
        try:
            self.source = wait_for_snapshot(port=PORT, timeout=timeout, accepts=accepts)
        except CaptureError as error:
            self.error = error

    def __enter__(self) -> "Listener":
        self._thread.start()
        self._ready.wait(timeout=2)
        return self

    def __exit__(self, *exc: object) -> None:
        self._thread.join(timeout=5)


def _post(body: Any, origin: str, raw: bytes | None = None) -> int:
    """Post like a browser would, retrying only until the socket is up.

    Probing the port with a bare connection would be simpler and wrong:
    the listener accepts it as a request and spends a turn on it.
    """
    data = raw if raw is not None else json.dumps(body).encode()
    request = urllib.request.Request(
        f"http://127.0.0.1:{PORT}/",
        data=data,
        headers={"Content-Type": "application/json", "Origin": origin},
        method="POST",
    )
    for attempt in range(40):
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return int(response.status)
        except urllib.error.HTTPError as error:
            return int(error.code)
        except urllib.error.URLError:
            if attempt == 39:
                raise
            time.sleep(0.05)
    raise AssertionError("unreachable")


def test_a_posted_snapshot_becomes_a_source() -> None:
    with Listener() as listener:
        assert (
            _post({"url": SHARE, "content": '{"uuid":"x"}'}, "https://claude.ai") == 200
        )

    assert listener.source is not None
    assert listener.source.url == SHARE
    assert listener.source.content == '{"uuid":"x"}'


def test_a_captured_snapshot_records_when_it_was_retrieved() -> None:
    """Unlike a file on disk, a capture knows the moment it happened."""
    with Listener() as listener:
        _post({"url": SHARE, "content": "{}"}, "https://claude.ai")

    assert listener.source is not None
    assert listener.source.fetched_at is not None


def test_an_origin_that_does_not_match_the_claimed_url_is_refused() -> None:
    """A page cannot set its own Origin, so this is what stops a forgery."""
    with Listener(timeout=1.0) as listener:
        assert _post({"url": SHARE, "content": "{}"}, "https://evil.example") == 400

    assert listener.source is None
    assert isinstance(listener.error, CaptureError)


def test_a_refused_payload_does_not_end_the_wait() -> None:
    """Clicking the bookmarklet on the wrong page is the likeliest mistake."""
    with Listener() as listener:
        assert _post({"url": SHARE}, "https://claude.ai") == 400
        assert _post({"url": SHARE, "content": "{}"}, "https://claude.ai") == 200

    assert listener.source is not None


def test_a_content_type_that_is_not_a_string_is_refused_and_the_wait_goes_on() -> None:
    with Listener() as listener:
        body = {"url": SHARE, "content": "{}", "content_type": 123}
        assert _post(body, "https://claude.ai") == 400
        assert _post({"url": SHARE, "content": "{}"}, "https://claude.ai") == 200

    assert listener.source is not None
    assert listener.source.content_type is None


def test_a_url_the_caller_does_not_accept_is_refused_and_the_wait_goes_on() -> None:
    """Any page matches its own origin, so the origin check alone admits it."""
    elsewhere = "https://elsewhere.example/page"
    with Listener(accepts=lambda url: url == SHARE) as listener:
        assert (
            _post({"url": elsewhere, "content": "{}"}, "https://elsewhere.example")
            == 400
        )
        assert _post({"url": SHARE, "content": "{}"}, "https://claude.ai") == 200

    assert listener.source is not None
    assert listener.source.url == SHARE


def test_a_connection_that_sends_nothing_cannot_hold_the_wait_past_its_deadline() -> (
    None
):
    started = time.monotonic()
    with Listener(timeout=1.0) as listener:
        for _ in range(40):
            try:
                silent = socket.create_connection(("127.0.0.1", PORT), timeout=1)
                break
            except OSError:
                time.sleep(0.05)
        else:
            raise AssertionError("listener never came up")
        listener._thread.join(timeout=4)
        still_waiting = listener._thread.is_alive()
        silent.close()

    assert not still_waiting
    assert isinstance(listener.error, CaptureError)
    assert time.monotonic() - started < 4


def test_a_body_nested_too_deeply_is_refused_and_the_wait_goes_on() -> None:
    """Parsed before any origin check, so any page could send one."""
    deep = ("[" * 100_000 + "]" * 100_000).encode()
    with Listener() as listener:
        assert _post(None, "https://elsewhere.example", raw=deep) == 400
        assert _post({"url": SHARE, "content": "{}"}, "https://claude.ai") == 200

    assert listener.source is not None


def test_a_body_that_is_not_json_is_refused() -> None:
    with Listener(timeout=1.0) as listener:
        assert _post(None, "https://claude.ai", raw=b"<html>nope</html>") == 400

    assert listener.source is None


def test_an_empty_body_is_refused() -> None:
    with Listener(timeout=1.0) as listener:
        assert _post(None, "https://claude.ai", raw=b"") == 400

    assert listener.source is None


def test_waiting_ends_with_an_explanation_rather_than_silence() -> None:
    with Listener(timeout=0.4) as listener:
        pass

    assert isinstance(listener.error, CaptureError)
    assert "bookmarklet" in str(listener.error)


def test_a_port_already_in_use_says_how_to_choose_another() -> None:
    """Holding the port directly, rather than racing two listeners for it."""
    with socket.socket() as taken:
        taken.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        taken.bind(("127.0.0.1", PORT))
        taken.listen()

        with pytest.raises(CaptureError, match="--port"):
            wait_for_snapshot(port=PORT, timeout=1.0)
