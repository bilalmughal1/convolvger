import json
import platform
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

from convolvger.cli.main import app
from convolvger.core.archive import READABLE_VERSIONS, SCHEMA_VERSION, ArchiveEnvelope
from convolvger.core.errors import ProviderNotFoundError
from convolvger.core.findings import Finding, finding
from convolvger.core.models import Conversation, Message, MessageRole, TextBlock
from convolvger.core.results import ParseError, ParseResult
from convolvger.core.source import RawSource
from convolvger.renderers import render_json

runner = CliRunner()
URL = "https://chatgpt.com/share/6aa3f5a2-00a4-83eb-8d18-3b2266aac2e6"


def fake_result(findings: list[Finding] | None = None) -> ParseResult:
    conversation = Conversation(
        provider="chatgpt",
        source_url=URL,
        title="A Test Chat",
        messages=[
            Message(role=MessageRole.USER, content=[TextBlock(text="hello")]),
            Message(role=MessageRole.ASSISTANT, content=[TextBlock(text="hi")]),
        ],
    )
    return ParseResult(conversation=conversation, findings=findings or [])


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
            fake_result([finding("unrecognised_role", "something was skipped")]),
        )

    monkeypatch.setattr("convolvger.cli.main._retrieve", _retrieve)


def archive_file(tmp_path: Path, findings: list[Finding] | None = None) -> Path:
    """Write a real archive, exactly as ``export --format json`` would."""
    path = tmp_path / "archive.json"
    path.write_text(
        render_json(fake_result().conversation, findings=findings or []),
        encoding="utf-8",
    )
    return path


SNAPSHOT = Path(__file__).parent.parent / "fixtures" / "chatgpt" / "share-minimal.html"
SHARE_URL = "https://chatgpt.com/share/abc123"
CLAUDE_SNAPSHOT = (
    Path(__file__).parent.parent / "fixtures" / "claude" / "share-minimal.json"
)
CLAUDE_URL = "https://claude.ai/share/00000000-0000-0000-0000-000000000000"


def test_providers_lists_every_bundled_provider() -> None:
    result = runner.invoke(app, ["providers"])

    assert result.exit_code == 0
    for name in ("chatgpt", "claude", "gemini", "grok"):
        assert name in result.stdout


def test_inspect_reports_a_summary(clean: None) -> None:
    result = runner.invoke(app, ["inspect", URL])

    assert result.exit_code == 0
    assert "A Test Chat" in result.stdout
    assert "Messages:  2" in result.stdout


def test_a_collapsed_finding_reports_how_many_times_it_was_seen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One line standing for eighty-two observations must say so."""
    collapsed = finding("unmodelled_content_type", "knowledge preserved verbatim")

    def _retrieve(source: str) -> tuple[RawSource, ParseResult]:
        return (
            RawSource(url=source, content="<html></html>"),
            fake_result([collapsed.model_copy(update={"occurrences": 82})]),
        )

    monkeypatch.setattr("convolvger.cli.main._retrieve", _retrieve)
    result = runner.invoke(app, ["inspect", URL])

    assert "knowledge preserved verbatim (x82)" in result.output


def test_a_single_observation_carries_no_count(warned: None) -> None:
    """A count on every line would be noise where it says nothing."""
    result = runner.invoke(app, ["inspect", URL])

    assert "something was skipped" in result.output
    assert "(x1)" not in result.output


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


def test_parse_failure_reports_collected_findings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _retrieve(source: str) -> tuple[RawSource, ParseResult]:
        raise ParseError(
            "no messages",
            findings=[finding("unrecognised_stream_line", "saw something odd")],
        )

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


def test_verify_reports_a_clean_archive(tmp_path: Path) -> None:
    result = runner.invoke(app, ["verify", str(archive_file(tmp_path))])

    assert result.exit_code == 0
    assert "Complete:  yes" in result.stdout
    assert "Faithful:  yes" in result.stdout


def test_verify_calls_empty_messages_complete(tmp_path: Path) -> None:
    """The whole point: a snapshot of empty system messages is not damage."""
    empty = [
        finding("message_has_no_content", "no content blocks", f"m{n}")
        for n in range(12)
    ]
    result = runner.invoke(app, ["verify", str(archive_file(tmp_path, empty))])

    assert result.exit_code == 0
    assert "Complete:  yes" in result.stdout


def test_verify_reports_an_incomplete_archive(tmp_path: Path) -> None:
    withheld = [finding("message_content_withheld", "emptied", "m1")]
    result = runner.invoke(app, ["verify", str(archive_file(tmp_path, withheld))])

    assert result.exit_code == 2
    assert "Complete:  no" in result.stdout
    assert "Faithful:  yes" in result.stdout


def test_verify_reports_an_unfaithful_archive(tmp_path: Path) -> None:
    unmodelled = [finding("unmodelled_content_type", "no block for it")]
    result = runner.invoke(app, ["verify", str(archive_file(tmp_path, unmodelled))])

    assert result.exit_code == 2
    assert "Faithful:  no" in result.stdout


def test_verify_reports_a_code_it_cannot_classify(tmp_path: Path) -> None:
    path = archive_file(tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["findings"] = [
        {"code": "minted_by_a_later_version", "level": "warning", "message": "?"}
    ]
    path.write_text(json.dumps(payload), encoding="utf-8")

    result = runner.invoke(app, ["verify", str(path)])

    assert result.exit_code == 0
    assert "unclassifiable" in result.stdout


def test_verify_refuses_an_older_schema_version(tmp_path: Path) -> None:
    """Exit 1, not a clean verdict on a file recording real damage."""
    path = archive_file(tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["schema_version"] = 1
    payload["warnings"] = ["a deferred slot was never merged"]
    del payload["findings"]
    path.write_text(json.dumps(payload), encoding="utf-8")

    result = runner.invoke(app, ["verify", str(path)])

    assert result.exit_code == 1
    assert "Complete:" not in result.stdout


def test_verify_fails_on_a_file_that_is_not_an_archive(tmp_path: Path) -> None:
    path = tmp_path / "notes.md"
    path.write_text("# Untitled conversation\n", encoding="utf-8")

    assert runner.invoke(app, ["verify", str(path)]).exit_code == 1


def test_verify_fails_when_the_file_is_missing(tmp_path: Path) -> None:
    assert runner.invoke(app, ["verify", str(tmp_path / "gone.json")]).exit_code == 1


def test_export_from_file_does_not_fetch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A saved snapshot is parsed as it stands, network untouched."""

    def boom(self: object, url: str) -> RawSource:
        raise AssertionError("fetch must not be called for --from-file")

    monkeypatch.setattr("convolvger.providers.chatgpt.ChatGPTProvider.fetch", boom)
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(
        app, ["export", SHARE_URL, "--from-file", str(SNAPSHOT), "-f", "json"]
    )

    assert result.exit_code == 0
    written = tmp_path / "a-saved-snapshot.json"
    assert written.exists()
    assert "A Saved Snapshot" in written.read_text(encoding="utf-8")


def test_from_file_records_no_retrieval_time(tmp_path: Path) -> None:
    """When a file was captured is not knowable, so it is not claimed."""
    monkeypatched = tmp_path / "out.json"
    result = runner.invoke(
        app,
        [
            "export",
            SHARE_URL,
            "--from-file",
            str(SNAPSHOT),
            "-f",
            "json",
            "-o",
            str(monkeypatched),
        ],
    )

    assert result.exit_code == 0
    assert '"retrieved_at": null' in monkeypatched.read_text(encoding="utf-8")


def test_inspect_from_file_reports_the_snapshot() -> None:
    result = runner.invoke(app, ["inspect", SHARE_URL, "--from-file", str(SNAPSHOT)])

    assert result.exit_code == 0
    assert "A Saved Snapshot" in result.stdout
    assert "Messages:  2" in result.stdout


def test_from_file_still_needs_a_url_a_provider_claims(tmp_path: Path) -> None:
    """Routing is by URL even when the bytes come from disk."""
    result = runner.invoke(
        app, ["inspect", "https://example.com/nope", "--from-file", str(SNAPSHOT)]
    )

    assert result.exit_code == 1


def test_from_file_fails_when_the_file_is_missing(tmp_path: Path) -> None:
    result = runner.invoke(
        app, ["inspect", SHARE_URL, "--from-file", str(tmp_path / "gone.html")]
    )

    assert result.exit_code == 1


def test_a_saved_claude_snapshot_is_archived_end_to_end(tmp_path: Path) -> None:
    """The one path Claude has: a share URL for routing, a file for content."""
    monkeypatched = tmp_path / "out.md"
    result = runner.invoke(
        app,
        [
            "export",
            CLAUDE_URL,
            "--from-file",
            str(CLAUDE_SNAPSHOT),
            "-f",
            "md",
            "-o",
            str(monkeypatched),
        ],
    )

    assert result.exit_code == 2
    written = monkeypatched.read_text(encoding="utf-8")
    assert "Provider: claude" in written
    assert "the shared snapshot carried no result" in written


def test_a_claude_url_without_a_file_is_told_how_to_supply_one() -> None:
    """Fetching is impossible, so the failure has to be actionable."""
    result = runner.invoke(app, ["export", CLAUDE_URL, "-f", "json"])

    assert result.exit_code == 1
    assert "--from-file" in result.output


def test_the_bookmarklet_command_prints_a_link() -> None:
    result = runner.invoke(app, ["bookmarklet"])

    assert result.exit_code == 0
    assert "javascript:" in result.output


def test_the_bookmarklet_command_honours_a_chosen_port() -> None:
    result = runner.invoke(app, ["bookmarklet", "--port", "9999"])

    assert result.exit_code == 0
    assert "127.0.0.1:9999/" in result.output


def test_the_bookmarklet_command_explains_how_to_install_it() -> None:
    """Dragging from a terminal is the hardest route; Add page is the one."""
    result = runner.invoke(app, ["bookmarklet"])

    assert "Add page" in result.output
    assert "javascript:" in result.output
    assert "star button" in result.output


GEMINI_URL = "https://gemini.google.com/share/0000000000ab"
GEMINI_PAYLOAD = (
    Path(__file__).parent.parent / "fixtures" / "gemini" / "share-minimal.json"
)


def gemini_response(tmp_path: Path) -> Path:
    """Wrap the payload fixture in the envelope the endpoint serves.

    Built here rather than committed twice: the same bytes as an
    already-committed fixture, in the outer form a saved response takes.
    """
    inner = GEMINI_PAYLOAD.read_text(encoding="utf-8").strip()
    frame = json.dumps(
        [["wrb.fr", "ujx1Bf", inner, None, None, None, "generic"]], ensure_ascii=False
    )
    saved = tmp_path / "gemini-response.txt"
    saved.write_text(f")]}}'\n\n{frame}", encoding="utf-8")
    return saved


def test_a_saved_gemini_response_is_archived_end_to_end(tmp_path: Path) -> None:
    """Gemini fetches, but a saved response must still archive offline."""
    written = tmp_path / "out.md"
    result = runner.invoke(
        app,
        [
            "export",
            GEMINI_URL,
            "--from-file",
            str(gemini_response(tmp_path)),
            "-f",
            "md",
            "-o",
            str(written),
        ],
    )

    assert result.exit_code == 0
    document = written.read_text(encoding="utf-8")
    assert "Provider: gemini" in document
    assert "Example conversation" in document
    assert "| Component | Cost |" in document


def test_a_saved_gemini_response_keeps_metadata_out_of_the_document(
    tmp_path: Path,
) -> None:
    written = tmp_path / "out.md"
    runner.invoke(
        app,
        [
            "export",
            GEMINI_URL,
            "--from-file",
            str(gemini_response(tmp_path)),
            "-f",
            "md",
            "-o",
            str(written),
        ],
    )

    document = written.read_text(encoding="utf-8")
    for leaked in ("citations", "search_queries", "response_content_id", "sp_"):
        assert leaked not in document


def test_a_shortened_gemini_url_is_routed_from_a_saved_response(tmp_path: Path) -> None:
    """The shortener needs no redirect when the content is already on disk."""
    result = runner.invoke(
        app,
        [
            "inspect",
            "https://share.gemini.google/94ESiKYXbGiV",
            "--from-file",
            str(gemini_response(tmp_path)),
        ],
    )

    assert result.exit_code == 0
    assert "gemini" in result.stdout


GROK_URL = "https://grok.com/share/bGVnYWN5_00000000-0000-4000-8000-000000000001"
GROK_PAYLOAD = Path(__file__).parent.parent / "fixtures" / "grok" / "share-minimal.json"


def test_a_saved_grok_response_is_archived_end_to_end(tmp_path: Path) -> None:
    """Grok fetches, but a saved response must still archive offline.

    Exit 2 because the fixture carries a reasoning trace, which is kept
    and flagged rather than modelled.
    """
    written = tmp_path / "out.md"
    result = runner.invoke(
        app,
        ["export", GROK_URL, "--from-file", str(GROK_PAYLOAD), "-o", str(written)],
    )

    assert result.exit_code == 2
    assert "unmodelled_content_type" in result.output
    document = written.read_text(encoding="utf-8")
    assert "Provider: grok" in document
    assert "Example Grok conversation" in document
    assert "| Element | Heats |" in document
    for leaked in ("<grok:", "citation_card", "example.com/source", "grok-3"):
        assert leaked not in document


def test_a_saved_grok_response_round_trips_through_json(tmp_path: Path) -> None:
    written = tmp_path / "out.json"
    runner.invoke(
        app,
        [
            "export",
            GROK_URL,
            "--from-file",
            str(GROK_PAYLOAD),
            "-f",
            "json",
            "-o",
            str(written),
        ],
    )

    envelope = ArchiveEnvelope.model_validate_json(written.read_text(encoding="utf-8"))
    assert envelope.retrieved_at is None
    assert envelope.conversation.provider == "grok"
    assert len(envelope.conversation.messages) == 4
    assert [item.code for item in envelope.findings] == ["unmodelled_content_type"]

    verdict = runner.invoke(app, ["verify", str(written)])
    assert "Complete:  yes" in verdict.stdout
    assert "Faithful:  no" in verdict.stdout


def test_a_saved_grok_share_with_no_responses_is_refused(tmp_path: Path) -> None:
    saved = tmp_path / "empty.json"
    saved.write_text(
        json.dumps({"conversation": {}, "responses": []}), encoding="utf-8"
    )

    result = runner.invoke(app, ["inspect", GROK_URL, "--from-file", str(saved)])

    assert result.exit_code == 1
    assert "carried no conversation" in result.output


def test_version_exits_zero_and_names_the_package() -> None:
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert result.stdout.startswith("convolvger ")


def test_version_reports_what_an_archive_would_record() -> None:
    """A version quoted in a bug report must match the user's own files."""
    envelope = ArchiveEnvelope(conversation=fake_result().conversation)
    result = runner.invoke(app, ["--version"])

    assert f"convolvger {envelope.tool_version}" in result.stdout


def test_version_names_the_interpreter_it_is_running_on() -> None:
    result = runner.invoke(app, ["--version"])

    assert platform.python_version() in result.stdout


def test_version_reports_which_archives_it_can_read() -> None:
    result = runner.invoke(app, ["--version"])

    assert f"Archive schema {SCHEMA_VERSION}" in result.stdout
    for readable in READABLE_VERSIONS:
        assert str(readable) in result.stdout


def test_version_lists_the_providers_this_build_supports() -> None:
    result = runner.invoke(app, ["--version"])

    for name in ("chatgpt", "claude", "gemini", "grok"):
        assert name in result.stdout


def test_version_contacts_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    """A local-first tool must not phone home to report its own version."""

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("--version must not make a network request")

    monkeypatch.setattr(httpx.Client, "request", forbidden)
    monkeypatch.setattr(httpx.Client, "send", forbidden)

    assert runner.invoke(app, ["--version"]).exit_code == 0


def test_bare_invocation_still_shows_usage() -> None:
    """Adding a callback must not turn a bare call into an error."""
    result = runner.invoke(app, [])

    assert "Usage:" in result.output
    assert "convolvger" in result.output
