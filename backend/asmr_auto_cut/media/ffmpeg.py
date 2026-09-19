import json
import subprocess
from pathlib import Path


def ensure_ffmpeg_available() -> None:
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, check=True)
        subprocess.run(["ffprobe", "-version"], capture_output=True, text=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        raise RuntimeError("FFmpeg is required. Install ffmpeg and ffprobe before analysis.") from exc


def probe_duration(source: Path) -> float:
    ensure_ffmpeg_available()
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(source),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    data = json.loads(result.stdout)
    return float(data["format"]["duration"])


def extract_analysis_audio(source: Path, output_wav: Path, sample_rate: int = 16000) -> Path:
    ensure_ffmpeg_available()
    output_wav.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
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
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return output_wav
