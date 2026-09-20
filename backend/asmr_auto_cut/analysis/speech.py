"""人声检测，以及「拿不准」的那一带。

Silero 对每个窗输出一个语音概率。单一阈值把它切成「说话 / 不说话」两半，但这两个
标签的代价不对称：判成说话就切掉，判错就永远丢了内容；判成不说话就留下，最多是
成片里多一段废话。所以阈值附近那一带不该由程序替用户决定——留着，但标出来给人听。

于是同一串概率切两刀：

    p >  vad_threshold            确定是人声，切
    p <= vad_uncertain_threshold  确定不是，静默保留
    中间那一带                     拿不准，保留 + 高亮（uncertain）

关键是**只跑一次模型**。两个阈值只是对同一串概率的两种切法，跑两遍等于把全流程最贵
的一步白做一遍。Silero 的 `get_speech_timestamps` 把「算概率」和「切区间」写在了一个
函数里，所以这里自己走一遍逐窗循环（用的是模型的公开调用），再对它暴露出来的
`get_speech_timestamps_from_probs` 调两次。
"""

from dataclasses import dataclass
from pathlib import Path

from asmr_auto_cut.config import AnalysisConfig
from asmr_auto_cut.timeline.intervals import RawInterval, subtract_intervals

#: 分析音频统一抽成 16k（见 media/ffmpeg），Silero 在这个采样率下的窗长是 512 点。
SAMPLE_RATE = 16000
WINDOW_SAMPLES = 512

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


def _speech_probs(wav, model) -> list[float]:
    """逐窗跑一遍模型，拿到每个窗的语音概率。

    这几行是 `silero_vad.utils_vad.get_speech_timestamps` 内部做的事，抄出来只为
    跑一次模型。用的是模型的公开接口（`reset_states` 和 `__call__`），不是库的私有
    实现——Silero 自己的流式类也是这么调的。

    `reset_states` 不能省：模型内部带 LSTM 状态，不清就是把上一段音频的记忆带进
    这一段。`no_grad` 也不能省——这里是纯推理，开着梯度只会白建一张几万个窗的图。
    """
    import torch

    model.reset_states()
    probs: list[float] = []
    with torch.no_grad():
        for start in range(0, len(wav), WINDOW_SAMPLES):
            chunk = wav[start : start + WINDOW_SAMPLES]
            if len(chunk) < WINDOW_SAMPLES:
                # 最后一块通常不满一窗，补零到整窗——模型只吃固定长度的输入。
                chunk = torch.nn.functional.pad(chunk, (0, WINDOW_SAMPLES - len(chunk)))
            probs.append(model(chunk, SAMPLE_RATE).item())
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
    from silero_vad import get_speech_timestamps_from_probs

    timestamps = get_speech_timestamps_from_probs(
        probs,
        sampling_rate=SAMPLE_RATE,
        threshold=threshold,
        min_speech_duration_ms=config.vad_min_speech_duration_ms,
        min_silence_duration_ms=config.vad_min_silence_duration_ms,
        speech_pad_ms=config.vad_speech_pad_ms,
        return_seconds=True,
        audio_length_samples=audio_length_samples,
    )
    return [
        RawInterval(
            start=float(item["start"]),
            end=float(item["end"]),
            label=label,
            confidence=_mean_probability(probs, float(item["start"]), float(item["end"])),
            source=source,
        )
        for item in timestamps
    ]


def detect_speech(
    wav_path: Path,
    config: AnalysisConfig,
    model=None,
) -> SpeechDetection:
    """跑一遍 VAD，同时给出「确定是人声」和「拿不准」两套区间。"""
    from silero_vad import load_silero_vad, read_audio

    if model is None:
        model = load_silero_vad()
    wav = read_audio(str(wav_path), sampling_rate=SAMPLE_RATE)
    probs = _speech_probs(wav, model)

    speech = _intervals_from_probs(
        probs, config, config.vad_threshold, "talk", "silero_vad", len(wav)
    )
    uncertain: list[RawInterval] = []
    if config.vad_uncertain_threshold < config.vad_threshold:
        wide = _intervals_from_probs(
            probs,
            config,
            config.vad_uncertain_threshold,
            "uncertain",
            "silero_vad_band",
            len(wav),
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
