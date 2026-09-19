from pathlib import Path

import typer

from asmr_auto_cut import __version__
from asmr_auto_cut.analysis.pipeline import analyze_source
from asmr_auto_cut.config import AnalysisConfig
from asmr_auto_cut.export.ffmpeg_export import export_clean_media
from asmr_auto_cut.timeline.io import load_project_state

app = typer.Typer(no_args_is_help=True)


@app.callback(invoke_without_command=True)
def main(
    version: bool = typer.Option(False, "--version", help="Show version and exit."),
) -> None:
    if version:
        typer.echo(__version__)
        raise typer.Exit()


@app.command()
def analyze(
    source: Path,
    project_dir: Path = typer.Option(..., "--project-dir"),
) -> None:
    state = analyze_source(source=source, project_dir=project_dir, config=AnalysisConfig())
    typer.echo(f"Created project {state.project_id} with {len(state.segments)} segments")


@app.command()
def export(
    segments_path: Path,
    output: Path = typer.Option(..., "--output"),
) -> None:
    state = load_project_state(segments_path, validate_source_exists=True)
    export_clean_media(state, output)
    typer.echo(f"Exported {output}")
