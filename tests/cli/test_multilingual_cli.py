"""Conversations in any language, through the command line, end to end.

The renderer never rewrites message text, so the content of an export
was already exact in every script tried. What failed was around it: the
file name, the terminal, the file a snapshot was saved in, and half an
emoji. These drive the real commands so each of those stays fixed.

The samples live in a JSON fixture rather than here, because ruff flags
look-alike characters in source code, and Cyrillic a (U+0430) is exactly
that.
"""

import codecs
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from convolvger.cli.main import app

runner = CliRunner()
FIXTURE = Path(__file__).parent.parent / "fixtures" / "multilingual" / "samples.json"
SAMPLES: list[dict[str, str]] = json.loads(FIXTURE.read_text(encoding="utf-8"))[
    "samples"
]
GROK_URL = "https://grok.com/share/bGVnYWN5_00000000-0000-4000-8000-000000000001"
ARABIC = next(s["text"] for s in SAMPLES if s["language"] == "Arabic")
CHINESE = next(s["text"] for s in SAMPLES if s["language"] == "Mandarin (Simplified)")


def payload(title: str, reply: str = "OK") -> dict[str, Any]:
    return {
        "conversation": {"conversationId": "c", "title": title},
        "responses": [
            {
                "responseId": "r1",
                "sender": "human",
                "message": title,
                "createTime": "2026-01-01T00:00:00Z",
            },
            {
                "responseId": "r2",
                "sender": "assistant",
                "message": reply,
                "createTime": "2026-01-01T00:00:01Z",
            },
        ],
    }


def saved(path: Path, title: str, reply: str = "OK") -> Path:
    path.write_text(
        json.dumps(payload(title, reply), ensure_ascii=False), encoding="utf-8"
    )
    return path


def label(sample: dict[str, str]) -> str:
    return f"{sample['continent']}-{sample['language']}"


@pytest.mark.parametrize("sample", SAMPLES, ids=label)
def test_a_title_in_any_language_names_its_file(
    sample: dict[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A title in any script names the file, rather than the provider."""
    snapshot = saved(tmp_path / "snapshot.json", sample["text"])
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["export", GROK_URL, "--from-file", str(snapshot)])

    assert result.exit_code == 0, result.output
    written = list(tmp_path.glob("*.md"))
    assert len(written) == 1
    assert written[0].stem != "grok"
    assert f"# {sample['text']}" in written[0].read_text(encoding="utf-8")
    assert f"Wrote {written[0].name}" in result.output


def test_two_titles_in_other_scripts_do_not_overwrite_each_other(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both used to be named after the provider, so the second replaced the first."""
    first = saved(tmp_path / "a.json", ARABIC)
    second = saved(tmp_path / "b.json", CHINESE)
    monkeypatch.chdir(tmp_path)

    runner.invoke(app, ["export", GROK_URL, "--from-file", str(first)])
    runner.invoke(app, ["export", GROK_URL, "--from-file", str(second)])

    documents = [p.read_text(encoding="utf-8") for p in tmp_path.glob("*.md")]
    assert len(documents) == 2
    assert any(f"# {ARABIC}" in text for text in documents)
    assert any(f"# {CHINESE}" in text for text in documents)


def test_exporting_the_same_conversation_again_numbers_the_new_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    snapshot = saved(tmp_path / "snapshot.json", "Same Title")
    monkeypatch.chdir(tmp_path)

    runner.invoke(app, ["export", GROK_URL, "--from-file", str(snapshot)])
    again = runner.invoke(app, ["export", GROK_URL, "--from-file", str(snapshot)])

    assert sorted(p.name for p in tmp_path.glob("*.md")) == [
        "same-title-2.md",
        "same-title.md",
    ]
    assert "Wrote same-title-2.md" in again.output


def test_an_output_path_that_was_asked_for_is_still_replaced(tmp_path: Path) -> None:
    """Numbering protects a name the tool chose, not one the user chose."""
    snapshot = saved(tmp_path / "snapshot.json", ARABIC)
    destination = tmp_path / "chosen.md"
    destination.write_text("old", encoding="utf-8")

    result = runner.invoke(
        app, ["export", GROK_URL, "--from-file", str(snapshot), "-o", str(destination)]
    )

    assert result.exit_code == 0
    assert f"# {ARABIC}" in destination.read_text(encoding="utf-8")
    assert [p.name for p in tmp_path.glob("*.md")] == ["chosen.md"]


def run_with_legacy_terminal(
    args: list[str], cwd: Path
) -> subprocess.CompletedProcess[bytes]:
    """Run the real CLI with stdout and stderr encoded as Windows-1252.

    That is what a redirected or piped stream gets on Windows unless UTF-8
    mode is on, and it cannot encode most of the world's scripts. Here it
    is simulated on any platform; on a Windows runner it is also the real
    default.
    """
    env = {**os.environ, "PYTHONIOENCODING": "cp1252"}
    env.pop("PYTHONUTF8", None)
    return subprocess.run(
        [sys.executable, "-m", "convolvger.cli.main", *args],
        capture_output=True,
        cwd=cwd,
        env=env,
        check=False,
    )


def test_markdown_to_stdout_is_utf8_whatever_the_terminal_encoding(
    tmp_path: Path,
) -> None:
    snapshot = saved(tmp_path / "snapshot.json", ARABIC, CHINESE)

    completed = run_with_legacy_terminal(
        ["export", GROK_URL, "--from-file", str(snapshot), "-o", "-"], tmp_path
    )

    assert completed.returncode == 0, completed.stderr.decode("utf-8", "replace")
    document = completed.stdout.decode("utf-8")
    assert f"# {ARABIC}" in document
    assert CHINESE in document


def test_inspect_prints_any_title_whatever_the_terminal_encoding(
    tmp_path: Path,
) -> None:
    snapshot = saved(tmp_path / "snapshot.json", CHINESE)

    completed = run_with_legacy_terminal(
        ["inspect", GROK_URL, "--from-file", str(snapshot)], tmp_path
    )

    assert completed.returncode == 0, completed.stderr.decode("utf-8", "replace")
    assert CHINESE in completed.stdout.decode("utf-8")


ENCODINGS = {
    "utf-8 with a BOM": (codecs.BOM_UTF8, "utf-8"),
    "utf-16-le with a BOM": (codecs.BOM_UTF16_LE, "utf-16-le"),
    "utf-16-be with a BOM": (codecs.BOM_UTF16_BE, "utf-16-be"),
    "utf-32-le with a BOM": (codecs.BOM_UTF32_LE, "utf-32-le"),
    "utf-32-be with a BOM": (codecs.BOM_UTF32_BE, "utf-32-be"),
}


@pytest.mark.parametrize("encoding", list(ENCODINGS))
def test_a_snapshot_saved_with_a_byte_order_mark_is_read(
    encoding: str, tmp_path: Path
) -> None:
    """Notepad adds a UTF-8 BOM; Windows PowerShell 5.1's '>' writes UTF-16."""
    text = json.dumps(payload(ARABIC), ensure_ascii=False)
    mark, codec = ENCODINGS[encoding]
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_bytes(mark + text.encode(codec))

    result = runner.invoke(app, ["inspect", GROK_URL, "--from-file", str(snapshot)])

    assert result.exit_code == 0, result.output
    assert ARABIC in result.stdout


def test_a_snapshot_in_a_legacy_encoding_is_refused_with_a_reason(
    tmp_path: Path,
) -> None:
    """Guessing a code page would silently produce the wrong text."""
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_bytes(
        json.dumps(payload("Café"), ensure_ascii=False).encode("cp1252")
    )

    result = runner.invoke(app, ["inspect", GROK_URL, "--from-file", str(snapshot)])

    assert result.exit_code == 1
    assert result.exception is None or isinstance(result.exception, SystemExit)
    assert "UTF-8" in result.output


def test_verify_reads_an_archive_saved_with_a_byte_order_mark(tmp_path: Path) -> None:
    snapshot = saved(tmp_path / "snapshot.json", ARABIC)
    archive = tmp_path / "archive.json"
    runner.invoke(
        app,
        [
            "export",
            GROK_URL,
            "--from-file",
            str(snapshot),
            "-f",
            "json",
            "-o",
            str(archive),
        ],
    )
    archive.write_bytes(b"\xef\xbb\xbf" + archive.read_bytes())

    result = runner.invoke(app, ["verify", str(archive)])

    assert result.exit_code == 0, result.output


HALF_EMOJI = "cut off mid-emoji \\ud83d"
"""A JSON escape for the first half of a surrogate pair, with no second half."""


def test_half_an_emoji_is_replaced_and_reported_not_a_crash(tmp_path: Path) -> None:
    raw = json.dumps(payload("Title", "PLACEHOLDER")).replace("PLACEHOLDER", HALF_EMOJI)
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text(raw, encoding="utf-8")
    written = tmp_path / "out.md"

    result = runner.invoke(
        app, ["export", GROK_URL, "--from-file", str(snapshot), "-o", str(written)]
    )

    assert result.exit_code == 2, result.output
    assert "unpaired_surrogate_replaced" in result.output
    assert "cut off mid-emoji �" in written.read_text(encoding="utf-8")


def test_whole_emoji_sent_as_escaped_pairs_raise_nothing(tmp_path: Path) -> None:
    """Every emoji arrives as two escaped halves when a provider escapes."""
    snapshot = tmp_path / "snapshot.json"
    reply = "wave \U0001f44b\U0001f3fd family \U0001f468‍\U0001f469‍\U0001f467"
    snapshot.write_text(json.dumps(payload("Title", reply)), encoding="utf-8")
    assert "\\ud83d" in snapshot.read_text(encoding="utf-8")

    result = runner.invoke(app, ["inspect", GROK_URL, "--from-file", str(snapshot)])

    assert result.exit_code == 0, result.output
    assert "unpaired_surrogate_replaced" not in result.output


def test_a_failed_export_leaves_no_empty_file_behind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A document that cannot be written must not leave a file claiming it was."""
    snapshot = saved(tmp_path / "snapshot.json", "Title")
    monkeypatch.setattr(
        "convolvger.cli.main.render_markdown", lambda *args, **kwargs: "# \ud800\n"
    )
    monkeypatch.chdir(tmp_path)
    chosen = tmp_path / "chosen.md"

    default = runner.invoke(app, ["export", GROK_URL, "--from-file", str(snapshot)])
    explicit = runner.invoke(
        app, ["export", GROK_URL, "--from-file", str(snapshot), "-o", str(chosen)]
    )

    assert default.exit_code == 1
    assert explicit.exit_code == 1
    assert list(tmp_path.glob("*.md")) == []
