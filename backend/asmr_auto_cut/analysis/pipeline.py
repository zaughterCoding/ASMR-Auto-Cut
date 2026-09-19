from pathlib import Path

from asmr_auto_cut.analysis.activity import detect_inactive_intervals
from asmr_auto_cut.analysis.speech import detect_speech_intervals
from asmr_auto_cut.analysis.waveform import build_waveform, save_waveform_json
from asmr_auto_cut.config import AnalysisConfig
from asmr_auto_cut.media.audio import load_mono_audio
from asmr_auto_cut.media.ffmpeg import extract_analysis_audio, probe_duration
from asmr_auto_cut.models import MediaSource, ProjectState
from asmr_auto_cut.timeline.intervals import RawInterval, build_segments, merge_cut_intervals
from asmr_auto_cut.timeline.io import save_project_state
from asmr_auto_cut.timeline.refine import refine_segments


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


def analyze_source(source: Path, project_dir: Path, config: AnalysisConfig) -> ProjectState:
    project_dir.mkdir(parents=True, exist_ok=True)
    duration = probe_duration(source)

    # analysis.wav 只是 VAD 和波形计算的中间产物，整条录音的体积可观
    # （8 小时约 0.9GB），而 waveform.json 已经够画图，所以分析成功后删掉。
    # 放在项目目录而不是 %TEMP%：默认临时目录在 C 盘，不能往那儿写大文件。
    # unlink 放在调用之后而不是 finally 里：中途失败时把 wav 留在原地便于排查。
    wav_path = project_dir / "analysis.wav"
    extract_analysis_audio(source, wav_path)
    audio, sample_rate = load_mono_audio(wav_path)
    waveform = build_waveform(audio, sample_rate)
    save_waveform_json(project_dir / "waveform.json", waveform)
    speech_intervals = detect_speech_intervals(wav_path)
    inactive_intervals = detect_inactive_intervals(audio, sample_rate, config)
    wav_path.unlink()

    state = assemble_project_state(
        project_id=project_dir.name,
        source_path=str(source),
        duration=duration,
        speech_intervals=speech_intervals,
        inactive_intervals=inactive_intervals,
        config=config,
    )
    save_project_state(project_dir / "project.json", state)
    save_project_state(project_dir / "segments.json", state)
    return state
