"""人声检测，以及「拿不准」的那一带。

Silero 对每个窗输出一个语音概率。单一阈值把它切成「说话 / 不说话」两半，但这两个
标签的代价不对称：判成说话就切掉，判错就永远丢了内容；判成不说话就留下，最多是
成片里多一段废话。所以阈值附近那一带不该由程序替用户决定——留着，但标出来给人听。

于是同一串概率切两刀：

    p >  vad_threshold            确定是人声，切
    p <= vad_uncertain_threshold  确定不是，静默保留
    中间那一带                     拿不准，保留 + 高亮（uncertain）

关键是**只跑一次模型**。两个阈值只是对同一串概率的两种切法，跑两遍等于把全流程最贵
的一步白做一遍。上游的 `get_speech_timestamps` 把「算概率」和「切区间」写在了一个
函数里，所以这里自己走一遍逐窗循环，再对拿到的概率调两次切区间。

推理和切区间都在 `silero_onnx` 里——那是我们自己接手的 Silero，见该模块的说明。
"""

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from asmr_auto_cut.analysis.silero_onnx import (
    WINDOW_SAMPLES,
    SileroVad,
    speech_timestamps_from_probs,
)
from asmr_auto_cut.config import AnalysisConfig
from asmr_auto_cut.media.audio import load_mono_audio
from asmr_auto_cut.timeline.intervals import RawInterval, subtract_intervals

#: 分析音频统一抽成 16k（见 media/ffmpeg），Silero 在这个采样率下的窗长是 512 点。
SAMPLE_RATE = 16000

#: 一个窗覆盖多少秒。概率是逐窗算的，要把秒换算回窗序号就得有它。
WINDOW_SECONDS = WINDOW_SAMPLES / SAMPLE_RATE


@dataclass
class SpeechDetection:
    """一趟 VAD 的两种读法。"""

    #: 概率高过 `vad_threshold` 的区间——判定为说话，会被切掉。
    speech: list[RawInterval]
    #: 概率落在两个阈值之间的区间——拿不准，保留下来但标成 uncertain 高亮。
    #: `vad_uncertain_threshold >= vad_threshold` 时为空（复核带被关掉）。
    uncertain: list[RawInterval]


def _speech_probs(audio, model) -> list[float]:
    """逐窗跑一遍模型，拿到每个窗的语音概率。

    `reset_states` 不能省：模型内部带 LSTM 状态，不清就是把上一段音频的记忆带进
    这一段。
    """
    model.reset_states()
    probs: list[float] = []
    for start in range(0, len(audio), WINDOW_SAMPLES):
        chunk = audio[start : start + WINDOW_SAMPLES]
        if len(chunk) < WINDOW_SAMPLES:
            # 最后一块通常不满一窗，补零到整窗——模型只吃固定长度的输入。
            chunk = np.pad(chunk, (0, WINDOW_SAMPLES - len(chunk)))
        probs.append(model(chunk))
    return probs


def _mean_probability(probs: list[float], start: float, end: float) -> float:
    """区间内各窗概率的均值。

    `confidence` 字段要的是「这段有多像人声」，拍一个常数进去等于把信息丢掉——
    复核时按这个数排序，就是先看最像人声的那几段还是一点都不像的那几段。
    """
    first = max(0, int(start / WINDOW_SECONDS))
    last = min(len(probs), max(first + 1, round(end / WINDOW_SECONDS)))
    chunk = probs[first:last]
    return sum(chunk) / len(chunk) if chunk else 0.0


def _intervals_from_probs(
    probs: list[float],
    config: AnalysisConfig,
    threshold: float,
    label: str,
    source: str,
    audio_length_samples: int,
) -> list[RawInterval]:
    """用给定阈值把概率切成区间。两刀走的是同一个函数，只有阈值和标签不同。"""
    timestamps = speech_timestamps_from_probs(
        probs,
        sampling_rate=SAMPLE_RATE,
        threshold=threshold,
        min_speech_duration_ms=config.vad_min_speech_duration_ms,
        min_silence_duration_ms=config.vad_min_silence_duration_ms,
        speech_pad_ms=config.vad_speech_pad_ms,
        audio_length_samples=audio_length_samples,
    )
    return [
        RawInterval(
            start=start,
            end=end,
            label=label,
            confidence=_mean_probability(probs, start, end),
            source=source,
        )
        for start, end in timestamps
    ]


def load_analysis_audio(wav_path: Path):
    """读分析音频，顺带确认它真的是 16k 单声道。

    采样率不对的话模型会拿错窗长去切，切出来的时间戳整体偏移，而这件事不会报错——
    静默错位比抛异常难查得多。上游的 `read_audio` 用 torchaudio 读并顺手重采样，
    我们这里依赖上游已经抽好了 16k（`extract_analysis_audio` 做的那一步）。
    """
    audio, sample_rate = load_mono_audio(wav_path)
    if sample_rate != SAMPLE_RATE:
        raise ValueError(
            f"分析音频必须是 {SAMPLE_RATE}Hz，{wav_path} 是 {sample_rate}Hz"
        )
    return audio


def detect_speech(
    wav_path: Path,
    config: AnalysisConfig,
    model=None,
) -> SpeechDetection:
    """跑一遍 VAD，同时给出「确定是人声」和「拿不准」两套区间。"""
    if model is None:
        model = SileroVad()
    audio = load_analysis_audio(wav_path)
    probs = _speech_probs(audio, model)

    speech = _intervals_from_probs(
        probs, config, config.vad_threshold, "talk", "silero_vad", len(audio)
    )
    uncertain: list[RawInterval] = []
    if config.vad_uncertain_threshold < config.vad_threshold:
        wide = _intervals_from_probs(
            probs,
            config,
            config.vad_uncertain_threshold,
            "uncertain",
            "silero_vad_band",
            len(audio),
        )
        uncertain = subtract_intervals(wide, speech)
    return SpeechDetection(speech=speech, uncertain=uncertain)


def detect_speech_intervals(
    wav_path: Path,
    config: AnalysisConfig,
    model=None,
) -> list[RawInterval]:
    """只要「确定是人声」那一套——测量脚本和旧调用点用的就是它。

    复核带是纯增量的：它只给保留段换标签，一个切段都不动（见 timeline/review.py），
    所以拿这个函数测出来的数字在新旧两种配置下都成立，历次扫描的记录不作废。
    """
    return detect_speech(wav_path, config, model=model).speech
