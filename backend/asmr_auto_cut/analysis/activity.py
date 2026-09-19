from dataclasses import dataclass
from typing import Literal

import numpy as np

from asmr_auto_cut.config import AnalysisConfig
from asmr_auto_cut.timeline.intervals import RawInterval


def frame_size_for(sample_rate: int, frame_seconds: float) -> int:
    """一个 RMS 帧覆盖多少采样点。分块和整段共用同一个长度，见 waveform.samples_per_point 的说明。"""
    return max(1, int(sample_rate * frame_seconds))


def frame_rms(chunk: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(chunk))))


@dataclass(frozen=True)
class InactiveThreshold:
    """静默判据最后取的值，连同它是怎么来的。

    三个数一起留着是为了能回答「这条录音为什么切了这么多（少）」。只留一个
    value 的话，出了问题只能重新猜一遍。
    """

    value: float
    noise_floor: float
    ceiling: float
    clamped: Literal["floor", "ceiling"] | None = None

    @property
    def note(self) -> str | None:
        """夹紧到安全阀上时给人看的一句话。正常取值下返回 None。"""
        if self.clamped == "ceiling":
            return (
                f"这条录音几乎没有真正的静音（底噪 {self.noise_floor:.5f} 高于上限 "
                f"{self.ceiling:.5f}），静默阈值已按 {self.value:.5f} 收紧"
            )
        if self.clamped == "floor":
            return (
                f"这条录音的底噪极低（{self.noise_floor:.5f}），静默阈值已按绝对下限 "
                f"抬到 {self.value:.5f}"
            )
        return None


def resolve_threshold(values: np.ndarray, config: AnalysisConfig) -> InactiveThreshold:
    """定出这条录音的静默阈值。

    固定模式（显式传了 inactive_rms_threshold）下不算分位数，noise_floor 和
    ceiling 直接填同一个值——它们只服务于 note，而固定模式没有 note 可说。
    """
    if config.inactive_rms_threshold is not None:
        fixed = config.inactive_rms_threshold
        return InactiveThreshold(value=fixed, noise_floor=fixed, ceiling=fixed)

    noise_floor = float(np.percentile(values, config.inactive_rms_percentile * 100))
    # 中位电平代表「这条录音正常响的时候有多响」，倒数第二安静的一半都在它之上
    ceiling = float(np.percentile(values, 50)) * 10 ** (-config.inactive_rms_headroom_db / 20)
    wanted = noise_floor * config.inactive_rms_ratio

    if wanted > ceiling:
        return InactiveThreshold(
            value=ceiling, noise_floor=noise_floor, ceiling=ceiling, clamped="ceiling"
        )
    if wanted < config.inactive_rms_floor:
        return InactiveThreshold(
            value=config.inactive_rms_floor,
            noise_floor=noise_floor,
            ceiling=ceiling,
            clamped="floor",
        )
    return InactiveThreshold(value=wanted, noise_floor=noise_floor, ceiling=ceiling)


class InactiveTracker:
    """把逐帧的 RMS 判据攒成一段段低活动区间。

    抽成类是因为分块分析必须让状态跨块活着：一段静音正好跨在块边界上时，
    两个块各自看都凑不满 inactive_min_duration，只有把区间攒到一起才对。
    整段分析和分块分析共用这一个状态机，避免两边的判据各写一份慢慢改歪。

    判决推迟到 finish() 才做：静默阈值要按整条录音自己的底噪算，而底噪得等
    所有帧都见过才知道。所以 feed() 只把帧收着，finish() 里一次算完。

    攒的是每帧一个 float 加一个时刻，1 秒帧下 8 小时录音约 28800 帧。和音频
    本身（16 kHz float32 下约 1.8 GB）差着四个数量级，不违背分块扫描省内存的
    初衷——那趟扫描躲的是音频，不是这个。
    """

    def __init__(self, config: AnalysisConfig) -> None:
        self._config = config
        self._min_duration = config.inactive_min_duration
        self._frames: list[float] = []
        self._starts: list[float] = []
        self._threshold: InactiveThreshold | None = None

    @property
    def threshold(self) -> InactiveThreshold | None:
        """判据取值。调用过 finish() 之后才有值。"""
        return self._threshold

    def feed(self, rms: float, start_time: float) -> None:
        """喂一帧。start_time 是这一帧的起始时刻。"""
        self._frames.append(rms)
        self._starts.append(start_time)

    def finish(self, end_time: float) -> list[RawInterval]:
        """收尾。end_time 是整段音频的结束时刻，用来给一直安静到结尾的区间收口。"""
        if not self._frames:
            return []

        decision = resolve_threshold(np.asarray(self._frames, dtype="float64"), self._config)
        self._threshold = decision

        ranges: list[tuple[float, float]] = []
        start: float | None = None
        for rms, start_time in zip(self._frames, self._starts):
            if rms <= decision.value:
                if start is None:
                    start = start_time
                continue
            if start is not None:
                # 区间在「第一个不安静的帧」处收口，而不是在那一帧的末尾：和整段分析
                # 的原有行为一致，切点落在声音刚起来的位置。
                ranges.append((start, start_time))
                start = None
        if start is not None:
            ranges.append((start, end_time))

        return [
            RawInterval(
                start=range_start,
                end=range_end,
                label="inactive",
                confidence=0.8,
                source="activity_detector",
            )
            for range_start, range_end in ranges
            if range_end - range_start >= self._min_duration
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
