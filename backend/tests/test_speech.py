"""钉住「config 里的 VAD 参数真的传到了切区间那一刀」，以及复核带只跑一趟模型。

这组参数的毛病不是会报错，而是**静默不生效**：早先一个都没传，全吃 Silero 的
默认值，切出来的结果看着正常，只是和 ASMR 的说话形态对不上。没有这层测试的话，
以后谁把某个 kwarg 写错名字，症状只会是「切得不太对」，没人查得出来。

假模型和假切区间都是按**我们自己的**调用面写的（`silero_onnx` 那两个）。上游那套
对象协议已经不在了——理由见该模块的说明：要甩掉 torch 就得自己接手这两件事。
所以这里替换的是 `speech` 模块里的名字，不是 `sys.modules["silero_vad"]`。
"""

from pathlib import Path

import numpy as np
import pytest

from asmr_auto_cut.analysis import speech
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
NARROW = [(1.5, 3.25)]
WIDE = [(1.0, 3.5), (8.0, 9.0)]


@pytest.fixture
def fake_vad(monkeypatch):
    """替掉模型和切区间，把两次切区间的参数和模型的调用次数都记下来。"""
    captured: dict = {"calls": [], "model_calls": 0, "built": 0}

    class FakeModel:
        def reset_states(self):
            captured["resets"] = captured.get("resets", 0) + 1

        def __call__(self, window):
            captured["model_calls"] += 1
            return FAKE_PROBABILITY

    model = FakeModel()

    def build():
        captured["built"] += 1
        return model

    def fake_timestamps(probs, **kwargs):
        captured["calls"].append(kwargs)
        captured["probs"] = probs
        return NARROW if kwargs["threshold"] >= 0.5 else WIDE

    monkeypatch.setattr(speech, "SileroVad", build)
    monkeypatch.setattr(speech, "speech_timestamps_from_probs", fake_timestamps)
    monkeypatch.setattr(
        speech, "load_analysis_audio", lambda path: np.zeros(AUDIO_SAMPLES, dtype="float32")
    )
    return captured, model


def test_vad_parameters_are_taken_from_config(fake_vad):
    captured, _ = fake_vad
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
    # 音频长度要显式传：切区间那一刀不知道我们切了几窗，默认值会按窗长向上取整，
    # 末尾那段的时间戳就会飘出去。
    assert speech_pass["audio_length_samples"] == AUDIO_SAMPLES
    # 复核带那一刀只换阈值，其余一模一样
    assert band_pass["threshold"] == 0.2
    assert band_pass["min_speech_duration_ms"] == 400


def test_intervals_come_back_as_talk(fake_vad):
    detection = detect_speech(Path("analysis.wav"), AnalysisConfig())

    assert len(detection.speech) == 1
    interval = detection.speech[0]
    assert (interval.start, interval.end) == (1.5, 3.25)
    assert interval.label == "talk"
    assert interval.source == "silero_vad"
    assert interval.confidence == FAKE_PROBABILITY


def test_a_passed_in_model_is_reused(fake_vad):
    """扫描脚本要复用同一个实例，否则每组参数都要重建一次 onnxruntime 会话。"""
    captured, model = fake_vad

    detect_speech(Path("analysis.wav"), AnalysisConfig(), model=model)

    assert captured["model_calls"] == WINDOWS
    assert captured["built"] == 0


def test_the_model_runs_once_even_though_the_band_cuts_twice(fake_vad):
    """整个复核带就是靠这一条站住的：两刀，一趟模型。

    切两刀本身是纯 Python 过一遍概率数组，可以忽略；重新跑一遍模型才是分钟级开销。
    """
    captured, _ = fake_vad

    detect_speech(Path("analysis.wav"), AnalysisConfig())

    assert len(captured["calls"]) == 2
    assert captured["model_calls"] == WINDOWS
    assert captured["resets"] == 1


def test_the_band_is_the_wide_pass_minus_the_speech_pass(fake_vad):
    detection = detect_speech(Path("analysis.wav"), AnalysisConfig())

    assert [(item.start, item.end) for item in detection.speech] == [(1.5, 3.25)]
    assert [(item.start, item.end) for item in detection.uncertain] == [
        (1.0, 1.5),
        (3.25, 3.5),
        (8.0, 9.0),
    ]
    assert all(item.label == "uncertain" for item in detection.uncertain)


def test_no_band_when_the_lower_threshold_reaches_the_speech_one(fake_vad):
    """下沿不低于上沿 = 关掉复核带，此时不该白切第二刀。"""
    captured, _ = fake_vad

    detection = detect_speech(
        Path("analysis.wav"), AnalysisConfig(vad_threshold=0.5, vad_uncertain_threshold=0.5)
    )

    assert len(captured["calls"]) == 1
    assert detection.uncertain == []


def test_detect_speech_intervals_returns_only_the_speech_pass(fake_vad):
    """测量脚本走的就是这个入口——复核带不能渗进它们的读数里。"""
    intervals = detect_speech_intervals(Path("analysis.wav"), AnalysisConfig())
    assert [item.label for item in intervals] == ["talk"]
    assert [(item.start, item.end) for item in intervals] == [(1.5, 3.25)]


def test_a_wrong_sample_rate_is_refused_rather_than_silently_misaligned(tmp_path, monkeypatch):
    """分析音频不是 16k 时必须报错，不能拿错窗长硬算。

    窗长跟着采样率走，采样率不对时间戳就整体偏移，而这条链路上没有任何一步会因此
    抛异常——切出来的东西看着正常，只是每一刀都错位。宁可在入口处拦下来。
    """
    monkeypatch.setattr(
        speech, "load_mono_audio", lambda path: (np.zeros(8000, dtype="float32"), 8000)
    )
    with pytest.raises(ValueError, match="16000Hz"):
        speech.load_analysis_audio(tmp_path / "analysis.wav")
