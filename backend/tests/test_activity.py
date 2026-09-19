import numpy as np

from asmr_auto_cut.analysis.activity import detect_inactive_intervals
from asmr_auto_cut.config import AnalysisConfig


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
