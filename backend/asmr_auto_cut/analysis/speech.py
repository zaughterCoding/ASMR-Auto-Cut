from pathlib import Path

from asmr_auto_cut.timeline.intervals import RawInterval


def detect_speech_intervals(wav_path: Path) -> list[RawInterval]:
    from silero_vad import get_speech_timestamps, load_silero_vad, read_audio

    model = load_silero_vad()
    wav = read_audio(str(wav_path), sampling_rate=16000)
    timestamps = get_speech_timestamps(
        wav,
        model,
        sampling_rate=16000,
        return_seconds=True,
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
