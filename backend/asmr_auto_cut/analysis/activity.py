import numpy as np

from asmr_auto_cut.config import AnalysisConfig
from asmr_auto_cut.timeline.intervals import RawInterval


def frame_size_for(sample_rate: int, frame_seconds: float) -> int:
    """一个 RMS 帧覆盖多少采样点。分块和整段共用同一个长度，见 waveform.samples_per_point 的说明。"""
    return max(1, int(sample_rate * frame_seconds))


def frame_rms(chunk: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(chunk))))


class InactiveTracker:
    """把逐帧的 RMS 判据攒成一段段低活动区间。

    抽成类是因为分块分析必须让状态跨块活着：一段静音正好跨在块边界上时，
    两个块各自看都凑不满 inactive_min_duration，只有把区间攒到一起才对。
    整段分析和分块分析共用这一个状态机，避免两边的判据各写一份慢慢改歪。
    """

    def __init__(self, config: AnalysisConfig) -> None:
        self._threshold = config.inactive_rms_threshold
        self._min_duration = config.inactive_min_duration
        self._start: float | None = None
        self._ranges: list[tuple[float, float]] = []

    def feed(self, rms: float, start_time: float) -> None:
        """喂一帧。start_time 是这一帧的起始时刻。"""
        if rms <= self._threshold:
            if self._start is None:
                self._start = start_time
            return
        if self._start is not None:
            # 区间在「第一个不安静的帧」处收口，而不是在那一帧的末尾：和整段分析
            # 的原有行为一致，切点落在声音刚起来的位置。
            self._ranges.append((self._start, start_time))
            self._start = None

    def finish(self, end_time: float) -> list[RawInterval]:
        """收尾。end_time 是整段音频的结束时刻，用来给一直安静到结尾的区间收口。"""
        if self._start is not None:
            self._ranges.append((self._start, end_time))
            self._start = None
        return [
            RawInterval(
                start=start,
                end=end,
                label="inactive",
                confidence=0.8,
                source="activity_detector",
            )
            for start, end in self._ranges
            if end - start >= self._min_duration
        ]


def detect_inactive_intervals(
    audio: np.ndarray,
    sample_rate: int,
    config: AnalysisConfig,
) -> list[RawInterval]:
    frame_size = frame_size_for(sample_rate, config.inactive_frame_seconds)
    tracker = InactiveTracker(config)
    for start_sample in range(0, len(audio), frame_size):
        chunk = audio[start_sample : start_sample + frame_size]
        if chunk.size == 0:
            continue
        tracker.feed(frame_rms(chunk), start_sample / sample_rate)
    return tracker.finish(len(audio) / sample_rate)
