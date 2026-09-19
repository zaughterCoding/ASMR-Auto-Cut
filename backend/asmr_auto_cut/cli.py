import typer

from asmr_auto_cut import __version__

app = typer.Typer(no_args_is_help=True)


@app.callback(invoke_without_command=True)
def main(
    version: bool = typer.Option(False, "--version", help="Show version and exit."),
) -> None:
    if version:
        typer.echo(__version__)
        raise typer.Exit()
