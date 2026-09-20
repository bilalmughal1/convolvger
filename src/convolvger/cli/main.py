"""Command line interface for Convolvger."""

import platform
import re
import sys
from pathlib import Path
from typing import Annotated

import typer

from convolvger.capture.bookmarklet import bookmarklet as _bookmarklet
from convolvger.capture.server import DEFAULT_PORT, wait_for_snapshot
from convolvger.core.archive import (
    READABLE_VERSIONS,
    SCHEMA_VERSION,
    ArchiveError,
    load_archive,
    tool_version,
)
from convolvger.core.errors import ConvolvgerError
from convolvger.core.findings import Finding, Level
from convolvger.core.results import ParseError, ParseResult
from convolvger.core.source import RawSource
from convolvger.providers.default import build_registry
from convolvger.renderers import render_json, render_markdown
from convolvger.validation.report import Report

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_WARNINGS = 2

FORMATS = ("md", "json")
FORMAT_HELP = f"Output format ({', '.join(FORMATS)})."

app = typer.Typer(
    name="convolvger",
    help="Archive public AI conversations into portable, provider-independent formats.",
    no_args_is_help=True,
)


def _version_lines() -> list[str]:
    """Everything a useful bug report needs, and nothing that phones home."""
    readable = ", ".join(str(item) for item in sorted(READABLE_VERSIONS))
    return [
        f"convolvger {tool_version()}",
        f"Python {platform.python_version()} ({platform.python_implementation()})",
        f"Archive schema {SCHEMA_VERSION} (reads {readable})",
        f"Providers: {', '.join(build_registry().names())}",
    ]


@app.callback(invoke_without_command=True)
def main(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            help="Show version, schema and provider information, then exit.",
            is_eager=True,
        ),
    ] = False,
) -> None:
    """Archive public AI conversations into portable formats."""
    if version:
        for line in _version_lines():
            typer.echo(line)
        raise typer.Exit(EXIT_OK)


def _slug(title: str | None, fallback: str) -> str:
    base = (title or fallback).lower()
    base = re.sub(r"[^a-z0-9]+", "-", base).strip("-")
    return base[:60] or fallback


def _warn(message: str) -> None:
    typer.echo(message, err=True)


def _retrieve(source: str) -> tuple[RawSource, ParseResult]:
    """Detect, fetch, and parse a conversation source."""
    registry = build_registry()
    provider = registry.detect(source)
    raw = provider.fetch(source)
    return raw, provider.parse(raw)


def _capture(port: int) -> tuple[RawSource, ParseResult]:
    """Wait for a browser to hand over a snapshot, then parse it.

    The URL is not asked for: it arrives with the snapshot, from the
    page the bookmarklet was clicked on. Unlike a file on disk, a
    capture knows when it happened, so ``fetched_at`` is real here.
    """
    _warn(f"Waiting on port {port}. Open the share page you want to archive")
    _warn("and click your Convolvger bookmark. Ctrl-C to stop waiting.")
    _warn("")
    _warn("No bookmark yet? Stop, run 'convolvger bookmarklet', and follow")
    _warn("the instructions it prints. That is a one-time setup.")
    _warn("")
    _warn("The archive is named after the conversation's own title unless")
    _warn("you passed --output.")
    raw = wait_for_snapshot(port=port)
    provider = build_registry().detect(raw.url)
    return raw, provider.parse(raw)


def _chosen_input(
    source: str | None, from_file: Path | None, capture: bool
) -> None:
    """Refuse combinations that cannot mean one thing."""
    if capture and from_file is not None:
        _warn("Error: --capture and --from-file are two different sources.")
        raise typer.Exit(EXIT_FAILED)
    if capture and source is not None:
        _warn("Error: --capture takes no URL; it comes from the page you click.")
        raise typer.Exit(EXIT_FAILED)
    if not capture and source is None:
        _warn("Error: give a conversation URL, or use --capture to wait for one.")
        raise typer.Exit(EXIT_FAILED)


def _select(
    source: str | None, from_file: Path | None, capture: bool, port: int
) -> tuple[RawSource, ParseResult]:
    if capture:
        return _capture(port)
    assert source is not None, "validated by _chosen_input"
    if from_file is not None:
        return _reparse(source, from_file)
    return _retrieve(source)


def _reparse(source: str, path: Path) -> tuple[RawSource, ParseResult]:
    """Parse a snapshot already on disk instead of fetching it.

    The URL is still required and still routes the snapshot to a
    provider: a file on disk carries no indication of where it came
    from, and the URL is the provenance every archive records.

    ``fetched_at`` stays unset. When a saved file was captured is not
    knowable from the file, and guessing it would put a false retrieval
    time into an archive.
    """
    provider = build_registry().detect(source)
    raw = RawSource(url=source, content=path.read_text(encoding="utf-8"))
    return raw, provider.parse(raw)


def _report_findings(findings: list[Finding]) -> None:
    """Report every finding, loudest first.

    Notes are printed as well as warnings: a note does not change the
    exit status, but it is still something the snapshot did not carry
    and the operator should be able to see it.

    A finding carries how many times it was observed, and a collapsed
    finding can stand for dozens. The count is printed because without
    it one line reading "knowledge preserved verbatim" says the same
    thing whether it happened once or eighty-two times. The leading
    totals count findings, not observations, and the two differ
    whenever anything collapsed.
    """
    if not findings:
        return
    warnings = [item for item in findings if item.level is Level.WARNING]
    notes = [item for item in findings if item.level is Level.NOTE]
    counts = [
        f"{len(group)} {label}"
        for group, label in ((warnings, "warning(s)"), (notes, "note(s)"))
        if group
    ]
    _warn(f"\n{', '.join(counts)}:")
    for item in warnings + notes:
        where = f" ({item.message_id})" if item.message_id else ""
        seen = f" (x{item.occurrences})" if item.occurrences > 1 else ""
        _warn(f"  - [{item.level.value}] {item.code}{where}: {item.message}{seen}")


def _fail(error: Exception) -> None:
    _warn(f"Error: {error}")
    if isinstance(error, ParseError) and error.findings:
        _report_findings(error.findings)
    raise typer.Exit(EXIT_FAILED)


@app.command()
def providers() -> None:
    """List supported conversation providers."""
    for name in build_registry().names():
        typer.echo(name)


@app.command()
def bookmarklet(
    port: Annotated[
        int,
        typer.Option("--port", help="Port the listener will wait on."),
    ] = DEFAULT_PORT,
) -> None:
    """Print a bookmarklet that hands a share page's snapshot to this tool."""
    _warn("One-time setup. The line below is a bookmarklet: a bookmark whose")
    _warn("address is a small program, which reads the snapshot behind a")
    _warn("share page and passes it to 'convolvger export --capture'.")
    _warn("")
    _warn("To install it in Chrome, Edge or Firefox:")
    _warn("  1. Copy the whole line below.")
    _warn("  2. Right-click an empty part of the bookmarks bar.")
    _warn("  3. Choose 'Add page' (Firefox: 'Add Bookmark').")
    _warn("  4. Name it Convolvger and paste the line into the URL field.")
    _warn("  5. Save, then edit it once and check the address still starts")
    _warn("     with 'javascript:' -- some browsers drop that on paste, and")
    _warn("     without it the bookmark does nothing at all.")
    _warn("")
    _warn("Do not use the star button: that bookmarks the page you are on.")
    _warn("")
    typer.echo(_bookmarklet(port))


@app.command()
def inspect(
    source: Annotated[
        str | None,
        typer.Argument(help="Public conversation URL, or the URL a saved snapshot came from."),
    ] = None,
    from_file: Annotated[
        Path | None,
        typer.Option(
            "--from-file",
            help="Parse this saved snapshot instead of fetching the URL.",
        ),
    ] = None,
    capture: Annotated[
        bool,
        typer.Option("--capture", help="Wait for a browser to hand over a snapshot."),
    ] = False,
    port: Annotated[
        int,
        typer.Option("--port", help="Port to wait on when capturing."),
    ] = DEFAULT_PORT,
) -> None:
    """Inspect a conversation source without exporting it."""
    _chosen_input(source, from_file, capture)
    try:
        _, result = _select(source, from_file, capture, port)
    except (ConvolvgerError, OSError) as error:
        _fail(error)
        return

    conversation = result.conversation
    typer.echo(f"Title:     {conversation.title or '(untitled)'}")
    typer.echo(f"Provider:  {conversation.provider}")
    typer.echo(f"Messages:  {len(conversation.messages)}")
    typer.echo(f"Visible:   {sum(m.visible for m in conversation.messages)}")
    typer.echo(f"Active:    {sum(m.active for m in conversation.messages)}")
    typer.echo(f"Blocks:    {sum(len(m.content) for m in conversation.messages)}")

    _report_findings(result.findings)
    raise typer.Exit(EXIT_WARNINGS if result.warned else EXIT_OK)


@app.command()
def export(
    source: Annotated[
        str | None,
        typer.Argument(help="Public conversation URL, or the URL a saved snapshot came from."),
    ] = None,
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Output path, or - for stdout."),
    ] = None,
    output_format: Annotated[
        str,
        typer.Option("--format", "-f", help=FORMAT_HELP),
    ] = "md",
    include_hidden: Annotated[
        bool,
        typer.Option("--include-hidden", help="Include provider-hidden messages."),
    ] = False,
    include_inactive: Annotated[
        bool,
        typer.Option("--include-inactive", help="Include deactivated branches."),
    ] = False,
    from_file: Annotated[
        Path | None,
        typer.Option(
            "--from-file",
            help="Parse this saved snapshot instead of fetching the URL.",
        ),
    ] = None,
    capture: Annotated[
        bool,
        typer.Option("--capture", help="Wait for a browser to hand over a snapshot."),
    ] = False,
    port: Annotated[
        int,
        typer.Option("--port", help="Port to wait on when capturing."),
    ] = DEFAULT_PORT,
) -> None:
    """Export a conversation to a portable archive."""
    _chosen_input(source, from_file, capture)
    if output_format not in FORMATS:
        _warn(f"Error: unsupported format: {output_format}")
        _warn(f"Supported formats: {', '.join(FORMATS)}")
        raise typer.Exit(EXIT_FAILED)

    try:
        raw, result = _select(source, from_file, capture, port)
    except (ConvolvgerError, OSError) as error:
        _fail(error)
        return

    if output_format == "json":
        if include_hidden or include_inactive:
            _warn("Note: include flags are ignored; JSON keeps every message.")
        rendered = render_json(
            result.conversation,
            findings=result.findings,
            fetched_at=raw.fetched_at,
        )
    else:
        rendered = render_markdown(
            result.conversation,
            include_hidden=include_hidden,
            include_inactive=include_inactive,
            findings=result.findings,
            fetched_at=raw.fetched_at,
        )

    if output is not None and str(output) == "-":
        sys.stdout.write(rendered)
    else:
        destination = output or Path(
            f"{_slug(result.conversation.title, result.conversation.provider)}.{output_format}"
        )
        destination.write_text(rendered, encoding="utf-8")
        _warn(f"Wrote {destination}")

    _report_findings(result.findings)
    raise typer.Exit(EXIT_WARNINGS if result.warned else EXIT_OK)


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


@app.command()
def verify(
    archive: Annotated[
        Path,
        typer.Argument(help="Path to a JSON archive written by convolvger."),
    ],
) -> None:
    """Report what a JSON archive says about its own integrity.

    The verdict is derived from the findings the archive already
    carries. Nothing is re-fetched and nothing is re-parsed: this reads
    a file and reports what it records.
    """
    try:
        envelope = load_archive(archive.read_text(encoding="utf-8"))
    except (ArchiveError, OSError) as error:
        _fail(error)
        return

    report = Report(findings=envelope.findings)
    conversation = envelope.conversation

    typer.echo(f"Archive:   {archive}")
    typer.echo(f"Schema:    {envelope.schema_version}")
    typer.echo(f"Tool:      {envelope.tool} {envelope.tool_version}")
    if envelope.retrieved_at is not None:
        typer.echo(f"Retrieved: {envelope.retrieved_at.isoformat()}")
    typer.echo(f"Provider:  {conversation.provider}")
    typer.echo(f"Messages:  {len(conversation.messages)}")
    typer.echo(f"Complete:  {_yes_no(report.complete)}")
    typer.echo(f"Faithful:  {_yes_no(report.faithful)}")
    if report.unrecognised:
        typer.echo(f"Unknown:   {len(report.unrecognised)} unclassifiable code(s)")

    _report_findings(envelope.findings)
    raise typer.Exit(
        EXIT_OK if report.complete and report.faithful else EXIT_WARNINGS
    )


if __name__ == "__main__":
    app()
