import sys
from pathlib import Path
from typing import cast

import typer

from asmr_auto_cut import __version__
from asmr_auto_cut.analysis.pipeline import analyze_source
from asmr_auto_cut.config import AnalysisConfig
from asmr_auto_cut.export.ffmpeg_export import ExportMode, export_clean_media
from asmr_auto_cut.progress import ResultEvent, emit_json_event
from asmr_auto_cut.timeline.io import load_project_state

app = typer.Typer(no_args_is_help=True)

EXPORT_MODES = ("quality", "fast")


def _enable_utf8_output() -> None:
    """把 stdout/stderr 固定成 UTF-8。

    --progress-json 的输出是给别的进程读的（桌面端就是从管道里逐行读 JSON），
    而 Python 在 stdout 接到管道时会按系统编码来编码——中文 Windows 上是 GBK。
    那样发出去的就是 GBK 字节，对面按 UTF-8 解析要么直接失败，要么中文全变成
    乱码。进度里带中文提示，所以必须在这里定死。
    0.1.0 修过同一个问题的镜像版本（子进程输出按 GBK 解码导致报错被吞），
    这次是输出侧。

    reconfigure 在 3.7+ 的 TextIOWrapper 上都有；测试里换成 StringIO 之类的
    替身时没有这个方法，跳过即可——那种情况下也不存在系统编码的问题。
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")


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
    progress_json: bool = typer.Option(False, "--progress-json"),
) -> None:
    if progress_json:
        _enable_utf8_output()
    progress = emit_json_event if progress_json else None
    state = analyze_source(
        source=source,
        project_dir=project_dir,
        config=AnalysisConfig(),
        progress=progress,
    )
    if progress_json:
        emit_json_event(
            ResultEvent(
                operation="analyze",
                project_path=str(project_dir / "project.json"),
            )
        )
    else:
        typer.echo(f"Created project {state.project_id} with {len(state.segments)} segments")


@app.command()
def export(
    segments_path: Path,
    output: Path = typer.Option(..., "--output"),
    mode: str = typer.Option("quality", "--mode", help="Export mode: quality or fast."),
    progress_json: bool = typer.Option(False, "--progress-json"),
) -> None:
    # 用 str + 手工校验而不是 Literal：typer 各版本对 Literal 的 choices 渲染和
    # 报错行为不一致，这里只要一个稳定的、能自己写清楚错在哪的判断。
    if mode not in EXPORT_MODES:
        raise typer.BadParameter(f"mode must be one of {', '.join(sorted(EXPORT_MODES))}")
    if progress_json:
        _enable_utf8_output()
    state = load_project_state(segments_path, validate_source_exists=True)
    export_clean_media(
        state,
        output,
        mode=cast(ExportMode, mode),
        progress=emit_json_event if progress_json else None,
    )
    if progress_json:
        emit_json_event(ResultEvent(operation="export", output_path=str(output)))
    else:
        typer.echo(f"Exported {output}")
