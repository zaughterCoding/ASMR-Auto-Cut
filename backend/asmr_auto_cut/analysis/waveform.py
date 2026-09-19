import json
from pathlib import Path

import numpy as np
from pydantic import BaseModel


class WaveformPoint(BaseModel):
    time: float
    peak: float
    rms: float


def samples_per_point(sample_rate: int, points_per_second: int) -> int:
    """一个波形点覆盖多少采样点。

    单独抽出来是给分块分析用的：分块要按同样的单位切，才能和整段一次算的结果
    逐点对齐。这个除法写在两处早晚会改歪一处，所以只留这一份。
    """
    return max(1, sample_rate // points_per_second)


def waveform_point(chunk: np.ndarray, time: float) -> WaveformPoint:
    """把一段采样收成一个波形点。分块分析和整段分析共用，保证两边算式一致。"""
    return WaveformPoint(
        time=time,
        peak=float(np.max(np.abs(chunk))),
        rms=float(np.sqrt(np.mean(np.square(chunk)))),
    )


def build_waveform(
    audio: np.ndarray,
    sample_rate: int,
    points_per_second: int = 20,
) -> list[WaveformPoint]:
    if audio.size == 0:
        return []
    step = samples_per_point(sample_rate, points_per_second)
    points: list[WaveformPoint] = []
    for start in range(0, len(audio), step):
        chunk = audio[start : start + step]
        if chunk.size == 0:
            continue
        points.append(waveform_point(chunk, start / sample_rate))
    return points


def save_waveform_json(path: Path, points: list[WaveformPoint]) -> None:
    """写紧凑 JSON，不缩进。

    这份文件是给前端画图读的，没有任何人会去肉眼看它，而它随录音时长线性增长：
    20 点/秒下 1 小时是 72000 个点，缩进要占约 5.1 MiB，紧凑之后约 3.5 MiB。
    字段名保持 time/peak/rms 不变，前端 JSON.parse 出来的东西一模一样。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([point.model_dump() for point in points], separators=(",", ":")),
        encoding="utf-8",
    )
