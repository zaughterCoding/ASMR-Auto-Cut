import json
import os
import subprocess
import sys
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


def tool_path(name: str) -> str:
    """ffmpeg / ffprobe 的调用路径，找不到就退回裸命令名交给 PATH 解析。

    三级顺序，与 Rust 侧找后端的三级是同一套思路：

    1. `ASMR_AUTO_CUT_FFMPEG_DIR` 显式覆盖，永远最先看（开发时指向本机那份）。
    2. 冻结（PyInstaller onedir）后，入口 exe 在 <安装目录>/backend/，
       ffmpeg 在 <安装目录>/ffmpeg/，也就是 exe 往上两级再进 ffmpeg/。
    3. 裸命令名交给 PATH——没打包时的行为一字未改。

    第 2 步用 `sys.executable` 而不是 `sys._MEIPASS`：后者指向 backend/_internal/，
    往上两级会落到 backend/ 而不是安装目录，拼出来的路径必然不存在。
    """
    override = os.environ.get("ASMR_AUTO_CUT_FFMPEG_DIR")
    if override:
        candidate = Path(override) / f"{name}.exe"
        if candidate.is_file():
            return str(candidate)

    if getattr(sys, "frozen", False):
        candidate = Path(sys.executable).resolve().parent.parent / "ffmpeg" / f"{name}.exe"
        if candidate.is_file():
            return str(candidate)

    return name


def ensure_ffmpeg_available() -> None:
    try:
        run_command([tool_path("ffmpeg"), "-version"])
        run_command([tool_path("ffprobe"), "-version"])
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        raise RuntimeError(
            "FFmpeg is required. Install ffmpeg and ffprobe before analysis, "
            "or set ASMR_AUTO_CUT_FFMPEG_DIR. An installed build expects them in "
            "the ffmpeg/ directory beside the program."
        ) from exc


def probe_duration(source: Path) -> float:
    ensure_ffmpeg_available()
    result = run_command(
        [
            tool_path("ffprobe"),
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
            tool_path("ffmpeg"),
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
