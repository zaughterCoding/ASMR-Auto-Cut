from pathlib import Path

from asmr_auto_cut.config import AnalysisConfig
from asmr_auto_cut.timeline.intervals import RawInterval


def detect_speech_intervals(
    wav_path: Path,
    config: AnalysisConfig,
    model=None,
) -> list[RawInterval]:
    """跑一遍 Silero VAD，返回「说话」区间。

    参数全部走 config，不再吃 Silero 的默认值——那些默认值是按会议录音调的，
    和 ASMR 的说话形态对不上，理由写在 config.py 里。

    `model` 是为了扫描脚本能复用同一个模型实例：load_silero_vad() 每次都要
    反序列化一遍权重，扫参数时那是几十次重复开销。
    """
    from silero_vad import get_speech_timestamps, load_silero_vad, read_audio

    if model is None:
        model = load_silero_vad()
    wav = read_audio(str(wav_path), sampling_rate=16000)
    timestamps = get_speech_timestamps(
        wav,
        model,
        sampling_rate=16000,
        return_seconds=True,
        threshold=config.vad_threshold,
        min_speech_duration_ms=config.vad_min_speech_duration_ms,
        min_silence_duration_ms=config.vad_min_silence_duration_ms,
        speech_pad_ms=config.vad_speech_pad_ms,
    )
    return [
        RawInterval(
            start=float(item["start"]),
            end=float(item["end"]),
            label="talk",
            confidence=0.9,
            source="silero_vad",
        )
        for item in timestamps
    ]
