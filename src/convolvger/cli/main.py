"""Command line interface for Convolvger."""

import re
import sys
from pathlib import Path
from typing import Annotated

import typer

from convolvger.core.errors import ConvolvgerError
from convolvger.core.findings import Finding, Level
from convolvger.core.results import ParseError, ParseResult
from convolvger.core.source import RawSource
from convolvger.providers.default import build_registry
from convolvger.renderers import render_json, render_markdown

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


def _report_findings(findings: list[Finding]) -> None:
    """Report every finding, loudest first.

    Notes are printed as well as warnings: a note does not change the
    exit status, but it is still something the snapshot did not carry
    and the operator should be able to see it.
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
        _warn(f"  - [{item.level.value}] {item.code}{where}: {item.message}")


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
def inspect(
    source: Annotated[
        str,
        typer.Argument(help="Public conversation URL or local conversation source."),
    ],
) -> None:
    """Inspect a conversation source without exporting it."""
    try:
        _, result = _retrieve(source)
    except ConvolvgerError as error:
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
        str,
        typer.Argument(help="Public conversation URL or local conversation source."),
    ],
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
) -> None:
    """Export a conversation to a portable archive."""
    if output_format not in FORMATS:
        _warn(f"Error: unsupported format: {output_format}")
        _warn(f"Supported formats: {', '.join(FORMATS)}")
        raise typer.Exit(EXIT_FAILED)

    try:
        raw, result = _retrieve(source)
    except ConvolvgerError as error:
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


if __name__ == "__main__":
    app()
