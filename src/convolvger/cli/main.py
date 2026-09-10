from typing import Annotated

import typer

app = typer.Typer(
    name="convolvger",
    help="Archive public AI conversations into portable, provider-independent formats.",
    no_args_is_help=True,
)


@app.command()
def providers() -> None:
    """List supported conversation providers."""
    typer.echo("No providers registered yet.")


@app.command()
def inspect(
    source: Annotated[
        str,
        typer.Argument(help="Public conversation URL or local conversation source."),
    ],
) -> None:
    """Inspect a conversation source without exporting it."""
    typer.echo(f"Inspecting: {source}")


@app.command()
def export(
    source: Annotated[
        str,
        typer.Argument(help="Public conversation URL or local conversation source."),
    ],
) -> None:
    """Export a conversation."""
    typer.echo(f"Exporting: {source}")


if __name__ == "__main__":
    app()
