"""钉住「config 里的 VAD 参数真的传到了 Silero」，以及复核带只跑一趟模型。

这组参数的毛病不是会报错，而是**静默不生效**：早先一个都没传，全吃 Silero 的
默认值，切出来的结果看着正常，只是和 ASMR 的说话形态对不上。没有这层测试的话，
以后谁把某个 kwarg 写错名字，症状只会是「切得不太对」，没人查得出来。

假模型是按**新**的调用面写的。我们不调 silero 的 `get_speech_timestamps`——它把
「算概率」和「切区间」焊在一个函数里，要切两刀就得跑两遍模型，而那是全流程最贵的
一步。现在自己逐窗算概率（模型的公开接口），再对同一串概率切两刀。所以假模型得
支持 `reset_states` 和 `__call__`，而 `get_speech_timestamps_from_probs` 收的是
一串现成的概率。
"""

import sys
import types
from pathlib import Path

import pytest
import torch

from asmr_auto_cut.analysis.speech import (
    SAMPLE_RATE,
    WINDOW_SAMPLES,
    detect_speech,
    detect_speech_intervals,
)
from asmr_auto_cut.config import AnalysisConfig

#: 假音频取 10 秒，好让下面的时间戳读起来是正常秒数而不是零点零几。
AUDIO_SAMPLES = SAMPLE_RATE * 10
WINDOWS = (AUDIO_SAMPLES + WINDOW_SAMPLES - 1) // WINDOW_SAMPLES

#: 假模型对每个窗都吐这个概率。取 0.5 是为了让算出来的 confidence 可断言。
FAKE_PROBABILITY = 0.5

#: 窄的那一刀（确定是人声）和宽的那一刀（可能是人声）各返回什么。
NARROW = [{"start": 1.5, "end": 3.25}]
WIDE = [{"start": 1.0, "end": 3.5}, {"start": 8.0, "end": 9.0}]


@pytest.fixture
def fake_silero(monkeypatch):
    """替掉 silero_vad 模块，把两次切区间的参数和模型的调用次数都记下来。"""
    captured: dict = {"calls": [], "model_calls": 0}

    class FakeProbability:
        def item(self):
            return FAKE_PROBABILITY

    class FakeModel:
        def reset_states(self):
            captured["resets"] = captured.get("resets", 0) + 1

        def __call__(self, chunk, sampling_rate):
            captured["model_calls"] += 1
            return FakeProbability()

    model = FakeModel()

    def fake_get_speech_timestamps_from_probs(probs, **kwargs):
        captured["calls"].append(kwargs)
        captured["probs"] = probs
        return NARROW if kwargs["threshold"] >= 0.5 else WIDE

    module = types.ModuleType("silero_vad")
    module.get_speech_timestamps_from_probs = fake_get_speech_timestamps_from_probs
    module.load_silero_vad = lambda: model
    module.read_audio = lambda path, sampling_rate: torch.zeros(AUDIO_SAMPLES)
    monkeypatch.setitem(sys.modules, "silero_vad", module)
    return captured, model


def test_vad_parameters_are_taken_from_config(fake_silero):
    captured, _ = fake_silero
    config = AnalysisConfig(
        vad_threshold=0.7,
        vad_uncertain_threshold=0.2,
        vad_min_speech_duration_ms=400,
        vad_min_silence_duration_ms=500,
        vad_speech_pad_ms=150,
    )

    detect_speech(Path("analysis.wav"), config)

    speech_pass, band_pass = captured["calls"]
    assert speech_pass["threshold"] == 0.7
    assert speech_pass["min_speech_duration_ms"] == 400
    assert speech_pass["min_silence_duration_ms"] == 500
    assert speech_pass["speech_pad_ms"] == 150
    # 采样率写死 16k 是 Silero 的硬要求，不跟着配置走
    assert speech_pass["sampling_rate"] == 16000
    assert speech_pass["return_seconds"] is True
    # 音频长度要显式传：silero 不知道我们切了几窗，默认值会按窗长向上取整，
    # 末尾那段的时间戳就会飘出去。
    assert speech_pass["audio_length_samples"] == AUDIO_SAMPLES
    # 复核带那一刀只换阈值，其余一模一样
    assert band_pass["threshold"] == 0.2
    assert band_pass["min_speech_duration_ms"] == 400


def test_intervals_come_back_as_talk(fake_silero):
    detection = detect_speech(Path("analysis.wav"), AnalysisConfig())

    assert len(detection.speech) == 1
    interval = detection.speech[0]
    assert (interval.start, interval.end) == (1.5, 3.25)
    assert interval.label == "talk"
    assert interval.source == "silero_vad"
    assert interval.confidence == FAKE_PROBABILITY


def test_a_passed_in_model_is_reused(fake_silero, monkeypatch):
    """扫描脚本要复用同一个实例，否则每组参数都要重新反序列化一遍权重。"""
    captured, model = fake_silero
    loaded = []
    monkeypatch.setattr(
        sys.modules["silero_vad"], "load_silero_vad", lambda: loaded.append(1) or model
    )

    detect_speech(Path("analysis.wav"), AnalysisConfig(), model=model)

    assert captured["model_calls"] == WINDOWS
    assert loaded == []


def test_the_model_runs_once_even_though_the_band_cuts_twice(fake_silero):
    """整个复核带就是靠这一条站住的：两刀，一趟模型。

    切两刀本身是纯 Python 过一遍概率数组，可以忽略；重新跑一遍模型才是分钟级开销。
    """
    captured, _ = fake_silero

    detect_speech(Path("analysis.wav"), AnalysisConfig())

    assert len(captured["calls"]) == 2
    assert captured["model_calls"] == WINDOWS
    assert captured["resets"] == 1


def test_the_band_is_the_wide_pass_minus_the_speech_pass(fake_silero):
    detection = detect_speech(Path("analysis.wav"), AnalysisConfig())

    assert [(item.start, item.end) for item in detection.speech] == [(1.5, 3.25)]
    assert [(item.start, item.end) for item in detection.uncertain] == [
        (1.0, 1.5),
        (3.25, 3.5),
        (8.0, 9.0),
    ]
    assert all(item.label == "uncertain" for item in detection.uncertain)


def test_no_band_when_the_lower_threshold_reaches_the_speech_one(fake_silero):
    """下沿不低于上沿 = 关掉复核带，此时不该白切第二刀。"""
    captured, _ = fake_silero

    detection = detect_speech(
        Path("analysis.wav"), AnalysisConfig(vad_threshold=0.5, vad_uncertain_threshold=0.5)
    )

    assert len(captured["calls"]) == 1
    assert detection.uncertain == []


def test_detect_speech_intervals_returns_only_the_speech_pass(fake_silero):
    """测量脚本走的就是这个入口——复核带不能渗进它们的读数里。"""
    intervals = detect_speech_intervals(Path("analysis.wav"), AnalysisConfig())
    assert [item.label for item in intervals] == ["talk"]
    assert [(item.start, item.end) for item in intervals] == [(1.5, 3.25)]
