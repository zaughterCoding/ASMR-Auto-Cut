from collections.abc import Callable
from pathlib import Path

from asmr_auto_cut.analysis.block_analysis import analyze_audio_blocks
from asmr_auto_cut.analysis.speech import detect_speech
from asmr_auto_cut.analysis.waveform import save_waveform_json
from asmr_auto_cut.config import AnalysisConfig
from asmr_auto_cut.media.ffmpeg import extract_analysis_audio, probe_duration
from asmr_auto_cut.models import MediaSource, ProjectState
from asmr_auto_cut.progress import ProgressEvent
from asmr_auto_cut.timeline.intervals import RawInterval, build_segments, merge_cut_intervals
from asmr_auto_cut.timeline.io import save_project_state
from asmr_auto_cut.timeline.refine import refine_segments
from asmr_auto_cut.timeline.review import mark_uncertain

#: 分析的阶段总数。进度条要算百分比就得先知道总数，所以固定写死在这里，
#: 每个阶段报数时都传它。改阶段顺序或增删阶段时这里要一起改。
#:
#: 0.2.0 从 8 降到 6：波形和低活动检测现在是同一趟分块扫描出来的（见
#: block_analysis），「载入音频 / 生成波形 / 检测低活动」这三步实际只剩一步，
#: 再拆成三个阶段报就是在骗进度条。这一步内部会逐块报细分进度，所以对用户来说
#: 反馈反而更密了。
ANALYZE_PHASES = 6


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
    uncertain_intervals: list[RawInterval] | None = None,
) -> ProjectState:
    cuts = merge_cut_intervals(speech_intervals + inactive_intervals, merge_gap=config.merge_gap)
    raw_segments = build_segments(duration=duration, cut_intervals=cuts)
    refined_segments = refine_segments(raw_segments, duration=duration, config=config)
    # 复核带排在 refine 之后，因为它只给保留段换标签（见 timeline/review.py）。
    # 给 None 就是不开复核带——测量脚本走这条路，拿到的段落与带内时代逐位相同。
    if uncertain_intervals:
        refined_segments = mark_uncertain(refined_segments, uncertain_intervals)
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

    # 波形和低活动来自同一趟分块扫描：整段读进内存等于同时压着原始音频和派生
    # 结果两份大数组，而长录音光音频本身就是每小时的量级。这一趟内部逐块报数，
    # 所以它虽然是「一个阶段」，用户在进度条上看到的更新反而是最密的。
    _report(progress, "analyze_blocks", "正在分析音频", 3, total)
    block_result = analyze_audio_blocks(
        wav_path,
        config,
        progress=lambda done, blocks: _report(
            progress,
            "analyze_blocks",
            f"正在分析音频（第 {done}/{blocks} 块）",
            3,
            total,
        ),
    )
    save_waveform_json(project_dir / "waveform.json", block_result.waveform)

    # 静默阈值被安全阀夹住时把原因说出来。夹紧本身是正常行为（说明这条录音
    # 要么几乎没有静音、要么几乎全是数字静音），但用户看到的只是「切得比预期
    # 少」或「切得比预期多」，不说明原因就只能靠猜。没有夹紧时不发这条。
    if block_result.inactive_threshold is not None:
        note = block_result.inactive_threshold.note
        if note is not None:
            _report(progress, "analyze_blocks", note, 3, total)

    _report(progress, "detect_speech", "正在检测人声", 4, total)
    detection = detect_speech(wav_path, config)
    wav_path.unlink()

    _report(progress, "build_timeline", "正在生成时间轴", 5, total)
    state = assemble_project_state(
        project_id=project_dir.name,
        source_path=str(source),
        duration=duration,
        speech_intervals=detection.speech,
        inactive_intervals=block_result.inactive_intervals,
        config=config,
        uncertain_intervals=detection.uncertain,
    )
    _report(progress, "save_project", "正在保存项目", 6, total)
    save_project_state(project_dir / "project.json", state)
    save_project_state(project_dir / "segments.json", state)
    return state
