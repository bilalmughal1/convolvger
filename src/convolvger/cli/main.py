"""Command line interface for Convolvger."""

import re
import sys
from pathlib import Path
from typing import Annotated

import typer

from convolvger.core.errors import ConvolvgerError
from convolvger.core.results import ParseError, ParseResult
from convolvger.core.source import RawSource
from convolvger.providers.default import build_registry
from convolvger.renderers import render_markdown

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_WARNINGS = 2

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


def _report_warnings(warnings: list[str]) -> None:
    if not warnings:
        return
    _warn(f"\n{len(warnings)} warning(s):")
    for warning in warnings:
        _warn(f"  - {warning}")


def _fail(error: Exception) -> None:
    _warn(f"Error: {error}")
    if isinstance(error, ParseError) and error.warnings:
        _report_warnings(error.warnings)
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

    _report_warnings(result.warnings)
    raise typer.Exit(EXIT_WARNINGS if result.warnings else EXIT_OK)


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
        typer.Option("--format", "-f", help="Output format."),
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
    if output_format != "md":
        _warn(f"Error: unsupported format: {output_format}")
        raise typer.Exit(EXIT_FAILED)

    try:
        raw, result = _retrieve(source)
    except ConvolvgerError as error:
        _fail(error)
        return

    rendered = render_markdown(
        result.conversation,
        include_hidden=include_hidden,
        include_inactive=include_inactive,
        warnings=result.warnings,
        fetched_at=raw.fetched_at,
    )

    if output is not None and str(output) == "-":
        sys.stdout.write(rendered)
    else:
        destination = output or Path(
            f"{_slug(result.conversation.title, result.conversation.provider)}.md"
        )
        destination.write_text(rendered, encoding="utf-8")
        _warn(f"Wrote {destination}")

    _report_warnings(result.warnings)
    raise typer.Exit(EXIT_WARNINGS if result.warnings else EXIT_OK)


if __name__ == "__main__":
    app()
