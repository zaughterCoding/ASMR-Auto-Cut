import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from asmr_auto_cut.media.ffmpeg import ensure_ffmpeg_available
from asmr_auto_cut.models import ProjectState

#: 每个 keep 段首尾的淡入淡出时长。接缝两侧波形不连续会产生爆音，
#: 加一小段渐变压掉；0 表示不做处理（导出更快，但接缝可能可闻）。
DEFAULT_FADE_SECONDS = 0.03


@dataclass(frozen=True)
class ExportClip:
    start: float
    end: float


def build_keep_clips(state: ProjectState) -> list[ExportClip]:
    return [
        ExportClip(start=segment.start, end=segment.end)
        for segment in state.segments
        if segment.action == "keep"
    ]


def _clip_command(
    source_path: str,
    clip: ExportClip,
    clip_path: Path,
    fade_seconds: float,
) -> list[str]:
    duration = clip.end - clip.start
    # 段落太短时把 fade 收窄到半长，避免首尾渐变互相重叠。
    fade = min(fade_seconds, duration / 2)

    # -ss/-to 放在 -i 之前配合默认的 -accurate_seek，音频能精确到采样点，
    # 且不必从头解码整条长录音。
    # 视频轨用 copy 不重编码；0:v? 里的 ? 让纯音频源也能走同一条命令。
    command = [
        "ffmpeg",
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
) -> Path:
    ensure_ffmpeg_available()
    clips = build_keep_clips(state)
    if not clips:
        raise RuntimeError("Timeline has no keep segments, nothing to export.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    # 临时分段总大小与输出相当，不能落在默认的 %TEMP%（C 盘），
    # 放到输出文件同目录，跟数据一起留在项目盘上。
    with tempfile.TemporaryDirectory(dir=output_path.parent) as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        clip_files: list[Path] = []
        for index, clip in enumerate(clips):
            clip_path = temp_dir / f"clip_{index:06d}.mp4"
            subprocess.run(
                _clip_command(state.source.path, clip, clip_path, fade_seconds),
                capture_output=True,
                text=True,
                check=True,
            )
            clip_files.append(clip_path)

        list_path = temp_dir / "clips.txt"
        list_path.write_text(
            "".join(f"file '{path.as_posix()}'\n" for path in clip_files),
            encoding="utf-8",
        )
        subprocess.run(
            [
                "ffmpeg",
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
            ],
            capture_output=True,
            text=True,
            check=True,
        )
    return output_path
