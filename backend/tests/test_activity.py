import numpy as np
import pytest

from asmr_auto_cut.analysis.activity import (
    InactiveTracker,
    detect_inactive_intervals,
    frame_rms,
)
from asmr_auto_cut.config import AnalysisConfig


def _adaptive_config(**overrides) -> AnalysisConfig:
    """自适应模式的基础配置。不传 inactive_rms_threshold 就是自适应。"""
    base = dict(inactive_frame_seconds=1.0, inactive_min_duration=20.0)
    base.update(overrides)
    return AnalysisConfig(**base)


def _threshold_of(audio: np.ndarray, sample_rate: int, config: AnalysisConfig):
    """跑一遍 collect 取判据。detect_inactive_intervals 只吐区间，判据得自己收。"""
    frame_size = int(sample_rate * config.inactive_frame_seconds)
    tracker = InactiveTracker(config)
    for start in range(0, len(audio), frame_size):
        chunk = audio[start : start + frame_size]
        if chunk.size:
            tracker.feed(frame_rms(chunk), start / sample_rate)
    tracker.finish(len(audio) / sample_rate)
    return tracker.threshold


def test_detect_inactive_low_rms_region():
    sample_rate = 10
    audio = np.concatenate([
        np.zeros(50, dtype="float32"),
        np.ones(50, dtype="float32") * 0.1,
    ])
    intervals = detect_inactive_intervals(
        audio,
        sample_rate,
        AnalysisConfig(
            inactive_frame_seconds=1.0,
            inactive_rms_threshold=0.01,
            inactive_min_duration=3.0,
        ),
    )
    assert len(intervals) == 1
    assert intervals[0].start == 0.0
    assert intervals[0].end == 5.0
    assert intervals[0].label == "inactive"


def test_adaptive_threshold_follows_the_recordings_own_noise_floor():
    """阈值取自这条录音自己的低分位，而不是一个跨录音的常量。"""
    sample_rate = 10
    audio = np.concatenate([
        np.full(300, 0.0008, dtype="float32"),
        np.full(300, 0.5, dtype="float32"),
    ])
    config = _adaptive_config()

    threshold = _threshold_of(audio, sample_rate, config)
    assert threshold.clamped is None
    assert threshold.noise_floor == pytest.approx(0.0008, rel=1e-4)
    assert threshold.value == pytest.approx(0.0008, rel=1e-4)
    assert threshold.note is None

    intervals = detect_inactive_intervals(audio, sample_rate, config)
    assert [(item.start, item.end) for item in intervals] == [(0.0, 30.0)]


def test_constant_level_recording_is_not_cut_off():
    """整条录音电平恒定、没有静音可切时，不能把它整个切掉。

    这是写死 0.004 的实际事故：电平恒定在 0.0005 的录音（安静的气声内容，
    全程没有静音）每一帧都落在 0.004 之下，会被整条判成 inactive 全删。
    自适应阈值带安全阀，这种情况下阈值被收紧到电平之下，一秒都不切。
    """
    sample_rate = 10
    audio = np.full(600, 0.0005, dtype="float32")
    config = _adaptive_config()

    threshold = _threshold_of(audio, sample_rate, config)
    assert threshold.clamped == "ceiling"
    assert threshold.note is not None
    assert threshold.value < 0.0005

    assert detect_inactive_intervals(audio, sample_rate, config) == []

    # 对照组：同一段音频交给写死的 0.004，会被整条切掉
    fixed = AnalysisConfig(
        inactive_frame_seconds=1.0,
        inactive_min_duration=20.0,
        inactive_rms_threshold=0.004,
    )
    assert [(item.start, item.end) for item in detect_inactive_intervals(audio, sample_rate, fixed)] == [
        (0.0, 60.0)
    ]


def test_recording_of_pure_silence_clamps_to_absolute_floor():
    """大半是数字静音时低分位会塌到 0，判据要由绝对下限兜住。"""
    sample_rate = 10
    audio = np.concatenate([
        np.zeros(300, dtype="float32"),
        np.full(300, 0.5, dtype="float32"),
    ])
    config = _adaptive_config()

    threshold = _threshold_of(audio, sample_rate, config)
    assert threshold.clamped == "floor"
    assert threshold.value == pytest.approx(0.0002)

    intervals = detect_inactive_intervals(audio, sample_rate, config)
    assert [(item.start, item.end) for item in intervals] == [(0.0, 30.0)]


def test_explicit_threshold_bypasses_adaptation():
    """显式给值就按固定值走，安全阀不参与——这是逃生口。"""
    sample_rate = 10
    audio = np.full(600, 0.0005, dtype="float32")
    config = AnalysisConfig(
        inactive_frame_seconds=1.0,
        inactive_min_duration=20.0,
        inactive_rms_threshold=0.001,
    )

    threshold = _threshold_of(audio, sample_rate, config)
    assert threshold.value == 0.001
    assert threshold.note is None

    assert [(item.start, item.end) for item in detect_inactive_intervals(audio, sample_rate, config)] == [
        (0.0, 60.0)
    ]
