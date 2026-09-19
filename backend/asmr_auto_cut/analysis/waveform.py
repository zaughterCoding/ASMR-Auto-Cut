import json
from pathlib import Path

import numpy as np
from pydantic import BaseModel


class WaveformPoint(BaseModel):
    time: float
    peak: float
    rms: float


def build_waveform(
    audio: np.ndarray,
    sample_rate: int,
    points_per_second: int = 20,
) -> list[WaveformPoint]:
    if audio.size == 0:
        return []
    samples_per_point = max(1, sample_rate // points_per_second)
    points: list[WaveformPoint] = []
    for start in range(0, len(audio), samples_per_point):
        chunk = audio[start : start + samples_per_point]
        if chunk.size == 0:
            continue
        peak = float(np.max(np.abs(chunk)))
        rms = float(np.sqrt(np.mean(np.square(chunk))))
        points.append(WaveformPoint(time=start / sample_rate, peak=peak, rms=rms))
    return points


def save_waveform_json(path: Path, points: list[WaveformPoint]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([point.model_dump() for point in points], indent=2),
        encoding="utf-8",
    )
