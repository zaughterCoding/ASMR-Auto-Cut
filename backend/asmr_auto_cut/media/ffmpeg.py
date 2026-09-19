import json
import subprocess
from pathlib import Path

#: 所有外部命令的输出都按 UTF-8 解码，解不了的字节替换掉而不是抛异常。
#:
#: 不能省成裸的 text=True：那样 Python 会按系统默认编码解码，中文 Windows 上是 GBK。
#: ffmpeg 报错信息里会带上文件路径，字节既可能是 UTF-8 也可能混着本地代码页，一旦
#: 撞上 GBK 解不了的字节，subprocess 的读取线程会直接抛 UnicodeDecodeError，结果是
#: 把 ffmpeg 真正的报错吞掉、只留下一段看不懂的线程 traceback。
#: 宁可看到几个替换字符，也不能丢掉报错本身。
_TEXT_KWARGS = {
    "capture_output": True,
    "text": True,
    "encoding": "utf-8",
    "errors": "replace",
}


def run_command(
    args: list[str], *, check: bool = True
) -> subprocess.CompletedProcess[str]:
    """跑一条外部命令并按 UTF-8 安全解码输出。

    后端的 subprocess 调用一律走这里，不要直接调 subprocess.run。
    """
    return subprocess.run(args, check=check, **_TEXT_KWARGS)


def ensure_ffmpeg_available() -> None:
    try:
        run_command(["ffmpeg", "-version"])
        run_command(["ffprobe", "-version"])
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        raise RuntimeError("FFmpeg is required. Install ffmpeg and ffprobe before analysis.") from exc


def probe_duration(source: Path) -> float:
    ensure_ffmpeg_available()
    result = run_command(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(source),
        ]
    )
    data = json.loads(result.stdout)
    return float(data["format"]["duration"])


def extract_analysis_audio(source: Path, output_wav: Path, sample_rate: int = 16000) -> Path:
    ensure_ffmpeg_available()
    output_wav.parent.mkdir(parents=True, exist_ok=True)
    run_command(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(source),
            "-vn",
            "-ac",
            "1",
            "-ar",
            str(sample_rate),
            "-f",
            "wav",
            str(output_wav),
        ]
    )
    return output_wav
