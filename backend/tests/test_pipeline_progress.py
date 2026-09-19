from pathlib import Path

import numpy as np

from asmr_auto_cut.analysis import pipeline
from asmr_auto_cut.config import AnalysisConfig


def test_analyze_source_reports_expected_phases(monkeypatch, tmp_path):
    events = []
    source = tmp_path / "input.mp4"
    source.write_bytes(b"fake")

    monkeypatch.setattr(pipeline, "probe_duration", lambda path: 10.0)
    monkeypatch.setattr(pipeline, "extract_analysis_audio", lambda source, wav_path: wav_path.write_bytes(b"wav"))
    monkeypatch.setattr(pipeline, "load_mono_audio", lambda wav_path: (np.zeros(16000, dtype="float32"), 16000))
    monkeypatch.setattr(pipeline, "build_waveform", lambda audio, sample_rate: [])
    monkeypatch.setattr(pipeline, "save_waveform_json", lambda path, waveform: path.write_text("[]", encoding="utf-8"))
    monkeypatch.setattr(pipeline, "detect_speech_intervals", lambda wav_path: [])
    monkeypatch.setattr(pipeline, "detect_inactive_intervals", lambda audio, sample_rate, config: [])

    pipeline.analyze_source(
        source=source,
        project_dir=tmp_path / "project",
        config=AnalysisConfig(),
        progress=events.append,
    )

    assert [event.phase for event in events] == [
        "probe_source",
        "extract_audio",
        "load_audio",
        "build_waveform",
        "detect_speech",
        "detect_inactive",
        "build_timeline",
        "save_project",
    ]
    assert events[-1].percent == 100.0
