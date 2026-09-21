import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from asmr_auto_cut.media.ffmpeg import ensure_ffmpeg_available, run_command, tool_path
from asmr_auto_cut.models import ProjectState
from asmr_auto_cut.progress import ProgressEvent

#: 每个 keep 段首尾的淡入淡出时长。接缝两侧波形不连续会产生爆音，
#: 加一小段渐变压掉；0 表示不做处理（导出更快，但接缝可能可闻）。
DEFAULT_FADE_SECONDS = 0.03

#: quality 是 0.1.0 的原有行为，保持默认。
#: fast 目前只做一件保守的事：去掉渐变。它不减少 ffmpeg 的调用次数，也不减少
#: 临时文件——真正能省掉这些的做法（filter_complex 一次渲染再拼接）会逼着视频
#: 轨重编码，而现在的 -c:v copy 原样透传正是导出容器能装下源视频编码的前提，
#: 换掉它得连带重新验证一遍容器兼容性，不适合放在这一版里。
ExportMode = Literal["quality", "fast"]


@dataclass(frozen=True)
class ExportClip:
    start: float
    end: float


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
                operation="export",
                phase=phase,
                message=message,
                current=current,
                total=total,
            )
        )


def build_keep_clips(state: ProjectState) -> list[ExportClip]:
    """把保留段合成 clip，**首尾相接的合成一个**。

    不能一个保留段一个 clip。每个 clip 在 quality 模式下首尾各拿一个 30ms 的
    afade，所以 clip 的边界是要花钱的（接缝处一个 60ms 的凹陷）。而保留段并不
    总是被切段隔开：复核带会把一个保留段切成 [asmr][uncertain][asmr] 这样首尾
    相接的几片（见 timeline/review.py），它们底下的音频是连续的，切开导出等于
    在连续的内容中间凭空插进若干次渐变——实测 minase 选「细致」档时保留段从 36
    涨到 309，也就是 273 处这样的接缝，全都落在耳语中间。

    合并之后 clip 数回到「不开复核带」时的数量：复核带只改高亮，不改音频的连续
    段落在哪里，所以它本来就不该影响导出切几刀。
    """
    clips: list[ExportClip] = []
    for segment in state.segments:
        if segment.action != "keep":
            continue
        if clips and segment.start <= clips[-1].end:
            # 相接（或由于浮点误差略微重叠）就并进上一段。段与段是平铺的，正常
            # 情况下 start 正好等于上一段的 end。
            clips[-1] = ExportClip(start=clips[-1].start, end=max(clips[-1].end, segment.end))
            continue
        clips.append(ExportClip(start=segment.start, end=segment.end))
    return clips


def _clip_command(
    source_path: str,
    clip: ExportClip,
    clip_path: Path,
    fade_seconds: float,
    mode: ExportMode,
) -> list[str]:
    duration = clip.end - clip.start
    # 段落太短时把 fade 收窄到半长，避免首尾渐变互相重叠。
    # fast 模式直接归零，于是下面那段 -af 整段不生成。
    fade = 0.0 if mode == "fast" else min(fade_seconds, duration / 2)

    # -ss/-to 放在 -i 之前配合默认的 -accurate_seek，音频能精确到采样点，
    # 且不必从头解码整条长录音。
    # 视频轨用 copy 不重编码；0:v? 里的 ? 让纯音频源也能走同一条命令。
    command = [
        tool_path("ffmpeg"),
        "-y",
        "-ss",
        f"{clip.start:.3f}",
        "-to",
        f"{clip.end:.3f}",
        "-i",
        source_path,
        "-map",
        "0:v?",
        "-map",
        "0:a",
        "-c:v",
        "copy",
    ]
    if fade > 0:
        command += [
            "-af",
            f"afade=t=in:st=0:d={fade:.3f},"
            f"afade=t=out:st={duration - fade:.3f}:d={fade:.3f}",
        ]
    command += ["-c:a", "aac", "-b:a", "192k", str(clip_path)]
    return command


def export_clean_media(
    state: ProjectState,
    output_path: Path,
    fade_seconds: float = DEFAULT_FADE_SECONDS,
    mode: ExportMode = "quality",
    progress: Callable[[ProgressEvent], None] | None = None,
) -> Path:
    ensure_ffmpeg_available()
    clips = build_keep_clips(state)
    if not clips:
        raise RuntimeError("Timeline has no keep segments, nothing to export.")

    # 分母是「准备 1 + 每段 1 + 合并 1 + 收尾 1」。逐段导出是耗时大头，
    # 所以每渲染完一段报一次，长时间导出时进度条才会真的在动，
    # 而不是卡在 20% 直到全部结束。
    total = len(clips) + 3
    _report(progress, "build_clip_list", "正在准备导出片段", 1, total)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    # 临时分段总大小与输出相当，不能落在默认的 %TEMP%（C 盘），
    # 放到输出文件同目录，跟数据一起留在项目盘上。
    with tempfile.TemporaryDirectory(dir=output_path.parent) as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        clip_files: list[Path] = []
        for index, clip in enumerate(clips):
            clip_path = temp_dir / f"clip_{index:06d}.mp4"
            run_command(_clip_command(state.source.path, clip, clip_path, fade_seconds, mode))
            clip_files.append(clip_path)
            _report(
                progress,
                "render_clip",
                f"正在导出片段 {index + 1}/{len(clips)}",
                index + 2,
                total,
            )

        list_path = temp_dir / "clips.txt"
        list_path.write_text(
            "".join(f"file '{path.as_posix()}'\n" for path in clip_files),
            encoding="utf-8",
        )
        _report(progress, "concat_clips", "正在合并片段", total - 1, total)
        run_command(
            [
                tool_path("ffmpeg"),
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(list_path),
                "-c",
                "copy",
                str(output_path),
            ]
        )
    _report(progress, "finish", "导出完成", total, total)
    return output_path
