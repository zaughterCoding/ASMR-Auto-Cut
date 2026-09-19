"""钉住「config 里的 VAD 参数真的传到了 Silero」。

这组参数的毛病不是会报错，而是**静默不生效**：早先一个都没传，全吃 Silero 的
默认值，切出来的结果看着正常，只是和 ASMR 的说话形态对不上。没有这层测试的话，
以后谁把某个 kwarg 写错名字，症状只会是「切得不太对」，没人查得出来。
"""

import sys
import types
from pathlib import Path

import pytest

from asmr_auto_cut.analysis.speech import detect_speech_intervals
from asmr_auto_cut.config import AnalysisConfig


@pytest.fixture
def fake_silero(monkeypatch):
    """替掉 silero_vad 模块，把调用参数记下来。"""
    captured: dict = {}

    class FakeModel:
        pass

    model = FakeModel()

    def fake_get_speech_timestamps(wav, model, **kwargs):
        captured["wav"] = wav
        captured["model"] = model
        captured["kwargs"] = kwargs
        return [{"start": 1.5, "end": 3.25}]

    module = types.ModuleType("silero_vad")
    module.get_speech_timestamps = fake_get_speech_timestamps
    module.load_silero_vad = lambda: model
    module.read_audio = lambda path, sampling_rate: f"audio@{sampling_rate}"
    monkeypatch.setitem(sys.modules, "silero_vad", module)
    return captured, model


def test_vad_parameters_are_taken_from_config(fake_silero):
    captured, _ = fake_silero
    config = AnalysisConfig(
        vad_threshold=0.3,
        vad_min_speech_duration_ms=400,
        vad_min_silence_duration_ms=500,
        vad_speech_pad_ms=150,
    )

    detect_speech_intervals(Path("analysis.wav"), config)

    kwargs = captured["kwargs"]
    assert kwargs["threshold"] == 0.3
    assert kwargs["min_speech_duration_ms"] == 400
    assert kwargs["min_silence_duration_ms"] == 500
    assert kwargs["speech_pad_ms"] == 150
    # 采样率写死 16k 是 Silero 的硬要求，不跟着配置走
    assert kwargs["sampling_rate"] == 16000
    assert kwargs["return_seconds"] is True
    assert captured["wav"] == "audio@16000"


def test_intervals_come_back_as_talk(fake_silero):
    intervals = detect_speech_intervals(Path("analysis.wav"), AnalysisConfig())

    assert len(intervals) == 1
    assert (intervals[0].start, intervals[0].end) == (1.5, 3.25)
    assert intervals[0].label == "talk"
    assert intervals[0].source == "silero_vad"


def test_a_passed_in_model_is_reused(fake_silero, monkeypatch):
    """扫描脚本要复用同一个实例，否则每组参数都要重新反序列化一遍权重。"""
    captured, model = fake_silero
    loaded = []
    monkeypatch.setattr(
        sys.modules["silero_vad"], "load_silero_vad", lambda: loaded.append(1) or model
    )

    detect_speech_intervals(Path("analysis.wav"), AnalysisConfig(), model=model)

    assert captured["model"] is model
    assert loaded == []
