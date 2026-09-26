"""A single-shot listener that receives a snapshot from the user's browser.

Some providers put a bot wall in front of the data behind a share page.
The wall is not there to stop the person who owns the link; it is there
to stop programs. So this tool does not pretend to be a browser -- it
waits for one. A bookmarklet running on the share page reads the
snapshot with the user's own session and posts it here.

What stops another page from posting something false: a page cannot
choose its own ``Origin`` header, and this listener only accepts a
payload whose origin matches the origin of the URL it claims to come
from. A page on ``evil.example`` claiming to be a Claude share is
refused because its origin says otherwise. Cross-origin rules in the
browser are not what protects this, and must not be relied on: a POST
of ``text/plain`` is sent without a preflight, and only the response is
hidden. The check has to happen here.

What this does not defend against: another program on the same machine,
which can send whatever headers it likes. Such a program could hand
over a forged snapshot -- but it could equally write the archive file
directly, so the listener grants it nothing it did not already have.
"""

import json
import sys
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import urlsplit

from convolvger.core.errors import ConvolvgerError
from convolvger.core.source import RawSource

DEFAULT_PORT = 23477
"""Fixed because the bookmarklet has to know where to post.

Below the ephemeral range Linux allocates outbound ports from, so it
will not be taken transiently by an unrelated connection, and clear of
the ports development tools habitually use. No port is permanently
safe, so a collision is reported rather than worked around.
"""

DEFAULT_TIMEOUT = 180.0
MAX_BYTES = 32 * 1024 * 1024


class CaptureError(ConvolvgerError):
    """Raised when a capture cannot be completed."""


def _origin_of(url: str) -> str | None:
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    if not parts.scheme or not parts.hostname:
        return None
    return f"{parts.scheme}://{parts.netloc}".lower()


class _Server(HTTPServer):
    """An ``HTTPServer`` that refuses a busy port on every platform.

    ``HTTPServer`` sets ``SO_REUSEADDR``, and the option means different
    things in different places. On Linux and macOS it only lets a new
    socket bind over connections left in ``TIME_WAIT``, which is wanted:
    a capture run straight after another would otherwise fail for a
    minute or so. On Windows it lets a second socket bind a port another
    process is actively listening on, so a collision goes unreported and
    the snapshot may be delivered to whichever listener Windows picks.
    It is kept where it is harmless and turned off where it is not.
    """

    allow_reuse_address = sys.platform != "win32"


class _Handler(BaseHTTPRequestHandler):
    received: RawSource | None = None
    rejected: str | None = None

    protocol_version = "HTTP/1.1"

    def _respond(self, code: int, body: bytes = b"") -> None:
        origin = self.headers.get("Origin")
        self.close_connection = True
        self.send_response(code)
        self.send_header("Connection", "close")
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "content-type")
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        """Answer the preflight.

        Permissive on purpose: the preflight cannot say which share the
        payload will claim, so nothing useful can be decided here. The
        decision happens on the POST, which is the only place it can be
        made honestly.
        """
        self._respond(204)

    def do_POST(self) -> None:
        declared = self.headers.get("Content-Length")
        try:
            size = int(declared or 0)
        except ValueError:
            self._reject("a malformed content length")
            return
        if size <= 0 or size > MAX_BYTES:
            self._reject(f"a body of {size} bytes")
            return

        try:
            payload = json.loads(self.rfile.read(size))
        except (OSError, json.JSONDecodeError):
            self._reject("a body that is not JSON")
            return

        if not isinstance(payload, dict):
            self._reject("a payload that is not an object")
            return
        url = payload.get("url")
        content = payload.get("content")
        if not isinstance(url, str) or not isinstance(content, str) or not content:
            self._reject("a payload without a url and a snapshot")
            return

        origin = (self.headers.get("Origin") or "").lower()
        expected = _origin_of(url)
        if expected is None or origin != expected:
            self._reject(f"an origin of {origin or '(none)'} claiming {url}")
            return

        _Handler.received = RawSource(
            url=url,
            content=content,
            content_type=payload.get("content_type"),
            fetched_at=datetime.now(UTC),
        )
        self._respond(200, b'{"ok":true}')

    def _reject(self, reason: str) -> None:
        _Handler.rejected = reason
        self._respond(400, b'{"ok":false}')

    def log_message(self, fmt: str, *args: Any) -> None:
        """Stay quiet: the CLI reports what happened, not the socket."""


def wait_for_snapshot(
    port: int = DEFAULT_PORT,
    timeout: float = DEFAULT_TIMEOUT,
) -> RawSource:
    """Wait for a browser to post one snapshot, then stop listening.

    Rejected payloads do not end the wait. The likeliest cause is the
    bookmarklet being clicked on a page that is not a share page, and
    ending the command over that would punish the commonest mistake.
    """
    _Handler.received = None
    _Handler.rejected = None

    try:
        server = _Server(("127.0.0.1", port), _Handler)
    except OSError as error:
        raise CaptureError(
            f"Cannot listen on 127.0.0.1:{port}: {error}. "
            f"Choose another with --port, and regenerate the bookmarklet "
            f"with the same port so it knows where to post."
        ) from error

    deadline = datetime.now(UTC).timestamp() + timeout
    try:
        while _Handler.received is None:
            remaining = deadline - datetime.now(UTC).timestamp()
            if remaining <= 0:
                raise CaptureError(
                    f"Nothing arrived within {timeout:.0f} seconds. "
                    f"The bookmarklet has to be clicked on the share page "
                    f"itself while this command is waiting."
                )
            server.timeout = remaining
            server.handle_request()
    finally:
        server.server_close()

    return _Handler.received
