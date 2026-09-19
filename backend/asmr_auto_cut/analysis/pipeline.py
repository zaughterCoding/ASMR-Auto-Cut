from collections.abc import Callable
from pathlib import Path

from asmr_auto_cut.analysis.activity import detect_inactive_intervals
from asmr_auto_cut.analysis.speech import detect_speech_intervals
from asmr_auto_cut.analysis.waveform import build_waveform, save_waveform_json
from asmr_auto_cut.config import AnalysisConfig
from asmr_auto_cut.media.audio import load_mono_audio
from asmr_auto_cut.media.ffmpeg import extract_analysis_audio, probe_duration
from asmr_auto_cut.models import MediaSource, ProjectState
from asmr_auto_cut.progress import ProgressEvent
from asmr_auto_cut.timeline.intervals import RawInterval, build_segments, merge_cut_intervals
from asmr_auto_cut.timeline.io import save_project_state
from asmr_auto_cut.timeline.refine import refine_segments

#: 分析的阶段总数。进度条要算百分比就得先知道总数，所以固定写死在这里，
#: 每个阶段报数时都传它。改阶段顺序或增删阶段时这里要一起改。
ANALYZE_PHASES = 8


def _report(
    progress: Callable[[ProgressEvent], None] | None,
    phase: str,
    message: str,
    current: int,
    total: int,
) -> None:
    if progress is not None:
        progress(
            ProgressEvent(
                operation="analyze",
                phase=phase,
                message=message,
                current=current,
                total=total,
            )
        )


def assemble_project_state(
    project_id: str,
    source_path: str,
    duration: float,
    speech_intervals: list[RawInterval],
    inactive_intervals: list[RawInterval],
    config: AnalysisConfig,
) -> ProjectState:
    cuts = merge_cut_intervals(speech_intervals + inactive_intervals, merge_gap=config.merge_gap)
    raw_segments = build_segments(duration=duration, cut_intervals=cuts)
    refined_segments = refine_segments(raw_segments, duration=duration, config=config)
    return ProjectState(
        project_id=project_id,
        source=MediaSource(path=source_path, duration=duration),
        segments=refined_segments,
    )


def analyze_source(
    source: Path,
    project_dir: Path,
    config: AnalysisConfig,
    progress: Callable[[ProgressEvent], None] | None = None,
) -> ProjectState:
    project_dir.mkdir(parents=True, exist_ok=True)

    # 进度里报的 current 是「第几步」，不是完成度，所以每步在动手之前就报，
    # 报完这一条界面立刻有反馈，而不是等这一步跑完才跳。
    total = ANALYZE_PHASES
    _report(progress, "probe_source", "正在读取媒体信息", 1, total)
    duration = probe_duration(source)

    # analysis.wav 只是 VAD 和波形计算的中间产物，整条录音的体积可观
    # （8 小时约 0.9GB），而 waveform.json 已经够画图，所以分析成功后删掉。
    # 放在项目目录而不是 %TEMP%：默认临时目录在 C 盘，不能往那儿写大文件。
    # unlink 放在调用之后而不是 finally 里：中途失败时把 wav 留在原地便于排查。
    wav_path = project_dir / "analysis.wav"
    _report(progress, "extract_audio", "正在提取分析音频", 2, total)
    extract_analysis_audio(source, wav_path)
    _report(progress, "load_audio", "正在载入音频", 3, total)
    audio, sample_rate = load_mono_audio(wav_path)
    _report(progress, "build_waveform", "正在生成波形", 4, total)
    waveform = build_waveform(audio, sample_rate)
    save_waveform_json(project_dir / "waveform.json", waveform)
    _report(progress, "detect_speech", "正在检测人声", 5, total)
    speech_intervals = detect_speech_intervals(wav_path)
    _report(progress, "detect_inactive", "正在检测低活动片段", 6, total)
    inactive_intervals = detect_inactive_intervals(audio, sample_rate, config)
    wav_path.unlink()

    _report(progress, "build_timeline", "正在生成时间轴", 7, total)
    state = assemble_project_state(
        project_id=project_dir.name,
        source_path=str(source),
        duration=duration,
        speech_intervals=speech_intervals,
        inactive_intervals=inactive_intervals,
        config=config,
    )
    _report(progress, "save_project", "正在保存项目", 8, total)
    save_project_state(project_dir / "project.json", state)
    save_project_state(project_dir / "segments.json", state)
    return state
