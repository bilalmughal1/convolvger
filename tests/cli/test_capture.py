"""Capturing from the CLI: the third way a conversation gets in."""

import json
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from typer.testing import CliRunner

from convolvger.capture.server import DEFAULT_PORT
from convolvger.cli.main import app

runner = CliRunner()

PORT = DEFAULT_PORT + 2
SHARE = "https://claude.ai/share/00000000-0000-0000-0000-000000000000"
SNAPSHOT = Path(__file__).parent.parent / "fixtures" / "claude" / "share-minimal.json"


def _post_when_ready() -> threading.Thread:
    """Play the bookmarklet: post the snapshot once the CLI is listening."""

    def run() -> None:
        body = json.dumps(
            {"url": SHARE, "content": SNAPSHOT.read_text(encoding="utf-8")}
        ).encode()
        request = urllib.request.Request(
            f"http://127.0.0.1:{PORT}/",
            data=body,
            headers={"Content-Type": "application/json", "Origin": "https://claude.ai"},
            method="POST",
        )
        for _ in range(60):
            try:
                urllib.request.urlopen(request, timeout=5).close()
                return
            except urllib.error.URLError:
                time.sleep(0.05)

    thread = threading.Thread(target=run)
    thread.start()
    return thread


def test_a_captured_snapshot_is_exported_without_a_url_argument(tmp_path: Path) -> None:
    """The URL arrives with the snapshot, from the page that was clicked."""
    written = tmp_path / "out.md"
    poster = _post_when_ready()

    result = runner.invoke(
        app,
        ["export", "--capture", "--port", str(PORT), "-f", "md", "-o", str(written)],
    )
    poster.join(timeout=5)

    assert result.exit_code == 2
    body = written.read_text(encoding="utf-8")
    assert "Provider: claude" in body
    assert "A minimal shared conversation" in body


def test_a_captured_snapshot_can_be_inspected(tmp_path: Path) -> None:
    poster = _post_when_ready()

    result = runner.invoke(app, ["inspect", "--capture", "--port", str(PORT)])
    poster.join(timeout=5)

    assert result.exit_code == 2
    assert "Provider:  claude" in result.output


def test_capturing_and_a_url_together_are_refused() -> None:
    result = runner.invoke(app, ["export", SHARE, "--capture"])

    assert result.exit_code == 1
    assert "takes no URL" in result.output


def test_capturing_and_a_saved_file_together_are_refused() -> None:
    result = runner.invoke(
        app, ["export", "--capture", "--from-file", str(SNAPSHOT)]
    )

    assert result.exit_code == 1
    assert "two different sources" in result.output


def test_neither_a_url_nor_capture_is_refused_with_advice() -> None:
    result = runner.invoke(app, ["export"])

    assert result.exit_code == 1
    assert "--capture" in result.output


def test_waiting_says_what_to_do_when_there_is_no_bookmark_yet() -> None:
    """A first run would otherwise be three minutes of silence."""
    poster = _post_when_ready()

    result = runner.invoke(app, ["inspect", "--capture", "--port", str(PORT)])
    poster.join(timeout=5)

    assert "convolvger bookmarklet" in result.output
    assert "one-time setup" in result.output.lower()


def test_waiting_says_where_the_archive_will_land() -> None:
    """No URL was typed, so nothing else on screen hints at the filename."""
    poster = _post_when_ready()

    result = runner.invoke(app, ["inspect", "--capture", "--port", str(PORT)])
    poster.join(timeout=5)

    assert "title" in result.output.lower()
