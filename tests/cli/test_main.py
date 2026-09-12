import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from convolvger.cli.main import app
from convolvger.core.errors import ProviderNotFoundError
from convolvger.core.models import Conversation, Message, MessageRole, TextBlock
from convolvger.core.results import ParseError, ParseResult
from convolvger.core.source import RawSource

runner = CliRunner()
URL = "https://chatgpt.com/share/6aa3f5a2-00a4-83eb-8d18-3b2266aac2e6"


def fake_result(warnings: list[str] | None = None) -> ParseResult:
    conversation = Conversation(
        provider="chatgpt",
        source_url=URL,
        title="A Test Chat",
        messages=[
            Message(role=MessageRole.USER, content=[TextBlock(text="hello")]),
            Message(role=MessageRole.ASSISTANT, content=[TextBlock(text="hi")]),
        ],
    )
    return ParseResult(conversation=conversation, warnings=warnings or [])


@pytest.fixture
def clean(monkeypatch: pytest.MonkeyPatch) -> None:
    def _retrieve(source: str) -> tuple[RawSource, ParseResult]:
        return RawSource(url=source, content="<html></html>"), fake_result()

    monkeypatch.setattr("convolvger.cli.main._retrieve", _retrieve)


@pytest.fixture
def warned(monkeypatch: pytest.MonkeyPatch) -> None:
    def _retrieve(source: str) -> tuple[RawSource, ParseResult]:
        return (
            RawSource(url=source, content="<html></html>"),
            fake_result(["something was skipped"]),
        )

    monkeypatch.setattr("convolvger.cli.main._retrieve", _retrieve)


def test_providers_lists_chatgpt() -> None:
    result = runner.invoke(app, ["providers"])

    assert result.exit_code == 0
    assert "chatgpt" in result.stdout


def test_inspect_reports_a_summary(clean: None) -> None:
    result = runner.invoke(app, ["inspect", URL])

    assert result.exit_code == 0
    assert "A Test Chat" in result.stdout
    assert "Messages:  2" in result.stdout


def test_inspect_exits_two_when_warnings_present(warned: None) -> None:
    result = runner.invoke(app, ["inspect", URL])

    assert result.exit_code == 2


def test_export_writes_a_slugged_file(
    clean: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["export", URL])

    assert result.exit_code == 0
    assert [p.name for p in tmp_path.glob("*.md")] == ["a-test-chat.md"]


def test_export_honours_the_output_option(clean: None, tmp_path: Path) -> None:
    destination = tmp_path / "archive.md"
    result = runner.invoke(app, ["export", URL, "-o", str(destination)])

    assert result.exit_code == 0
    assert "# A Test Chat" in destination.read_text(encoding="utf-8")


def test_export_writes_to_stdout_with_dash(clean: None) -> None:
    result = runner.invoke(app, ["export", URL, "-o", "-"])

    assert result.exit_code == 0
    assert "# A Test Chat" in result.stdout
    assert "Note on snapshots" in result.stdout


def test_export_exits_two_when_warnings_present(warned: None, tmp_path: Path) -> None:
    result = runner.invoke(app, ["export", URL, "-o", str(tmp_path / "out.md")])

    assert result.exit_code == 2


def test_unsupported_format_fails(clean: None) -> None:
    result = runner.invoke(app, ["export", URL, "-f", "pdf"])

    assert result.exit_code == 1


def test_unknown_url_fails_with_exit_one(monkeypatch: pytest.MonkeyPatch) -> None:
    def _retrieve(source: str) -> tuple[RawSource, ParseResult]:
        raise ProviderNotFoundError(f"No provider matches URL: {source}")

    monkeypatch.setattr("convolvger.cli.main._retrieve", _retrieve)
    result = runner.invoke(app, ["export", "https://example.com/x"])

    assert result.exit_code == 1


def test_parse_failure_reports_collected_warnings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _retrieve(source: str) -> tuple[RawSource, ParseResult]:
        raise ParseError("no messages", warnings=["saw something odd"])

    monkeypatch.setattr("convolvger.cli.main._retrieve", _retrieve)
    result = runner.invoke(app, ["inspect", URL])

    assert result.exit_code == 1


def test_export_json_writes_a_slugged_file(
    clean: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["export", URL, "-f", "json"])

    assert result.exit_code == 0
    assert [p.name for p in tmp_path.glob("*.json")] == ["a-test-chat.json"]


def test_export_json_to_stdout_is_valid_json(clean: None) -> None:
    result = runner.invoke(app, ["export", URL, "-f", "json", "-o", "-"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["tool"] == "convolvger"
    assert payload["conversation"]["title"] == "A Test Chat"


def test_include_flags_do_not_change_the_json(clean: None, tmp_path: Path) -> None:
    """The flags are meaningless here: JSON always keeps every message."""
    plain, flagged = tmp_path / "plain.json", tmp_path / "flagged.json"
    runner.invoke(app, ["export", URL, "-f", "json", "-o", str(plain)])
    runner.invoke(
        app,
        [
            "export",
            URL,
            "-f",
            "json",
            "--include-hidden",
            "--include-inactive",
            "-o",
            str(flagged),
        ],
    )

    assert flagged.read_text(encoding="utf-8") == plain.read_text(encoding="utf-8")
