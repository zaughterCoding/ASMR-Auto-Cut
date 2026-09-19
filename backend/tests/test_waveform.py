import numpy as np

from asmr_auto_cut.analysis.waveform import build_waveform


def test_build_waveform_returns_expected_number_of_points():
    sample_rate = 10
    audio = np.ones(20, dtype="float32")
    points = build_waveform(audio, sample_rate, points_per_second=2)
    assert len(points) == 4
    assert points[0].peak == 1.0
    assert points[0].rms == 1.0


def test_build_waveform_handles_empty_audio():
    points = build_waveform(np.array([], dtype="float32"), sample_rate=16000)
    assert points == []
