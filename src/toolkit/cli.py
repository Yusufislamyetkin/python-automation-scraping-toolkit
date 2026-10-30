"""Typer CLI entry point (`toolkit ...`)."""

import typer

app = typer.Typer(help="Price monitoring & lead automation toolkit.", no_args_is_help=True)


@app.callback()
def main() -> None:
    """Price monitoring & lead automation toolkit."""


@app.command()
def version() -> None:
    """Print the toolkit version."""
    typer.echo("0.1.0")


if __name__ == "__main__":
    app()
