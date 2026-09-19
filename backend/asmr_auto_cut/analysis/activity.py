import numpy as np

from asmr_auto_cut.config import AnalysisConfig
from asmr_auto_cut.timeline.intervals import RawInterval


def detect_inactive_intervals(
    audio: np.ndarray,
    sample_rate: int,
    config: AnalysisConfig,
) -> list[RawInterval]:
    frame_size = max(1, int(sample_rate * config.inactive_frame_seconds))
    inactive_ranges: list[tuple[float, float]] = []
    current_start: float | None = None

    for start_sample in range(0, len(audio), frame_size):
        chunk = audio[start_sample : start_sample + frame_size]
        if chunk.size == 0:
            continue
        rms = float(np.sqrt(np.mean(np.square(chunk))))
        start_time = start_sample / sample_rate
        end_time = min(len(audio) / sample_rate, (start_sample + chunk.size) / sample_rate)
        is_inactive = rms <= config.inactive_rms_threshold
        if is_inactive and current_start is None:
            current_start = start_time
        if not is_inactive and current_start is not None:
            inactive_ranges.append((current_start, start_time))
            current_start = None
    if current_start is not None:
        inactive_ranges.append((current_start, len(audio) / sample_rate))

    return [
        RawInterval(start=start, end=end, label="inactive", confidence=0.8, source="activity_detector")
        for start, end in inactive_ranges
        if end - start >= config.inactive_min_duration
    ]
