import json

import numpy as np

from asmr_auto_cut.analysis.waveform import WaveformPoint, build_waveform, save_waveform_json


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


def test_save_waveform_json_is_compact_and_round_trips(tmp_path):
    """落盘必须是紧凑 JSON，且字段名不变。

    这份文件随录音时长线性增长（20 点/秒下 1 小时 72000 个点），缩进要多占约
    三成体积，而它只是给前端画图读的，没人会去看。字段名一旦改掉前端就画不出图，
    所以这里连着字段名一起钉死。
    """
    points = [
        WaveformPoint(time=0.0, peak=0.5, rms=0.25),
        WaveformPoint(time=0.05, peak=1.0, rms=0.5),
    ]
    path = tmp_path / "waveform.json"
    save_waveform_json(path, points)

    raw = path.read_text(encoding="utf-8")
    assert "\n" not in raw
    assert raw == '[{"time":0.0,"peak":0.5,"rms":0.25},{"time":0.05,"peak":1.0,"rms":0.5}]'
    assert json.loads(raw) == [point.model_dump() for point in points]
