from pathlib import Path

from asmr_auto_cut.analysis import pipeline
from asmr_auto_cut.analysis.block_analysis import BlockAnalysisResult
from asmr_auto_cut.config import AnalysisConfig


def test_analyze_source_reports_expected_phases(monkeypatch, tmp_path):
    events = []
    source = tmp_path / "input.mp4"
    source.write_bytes(b"fake")

    monkeypatch.setattr(pipeline, "probe_duration", lambda path: 10.0)
    monkeypatch.setattr(pipeline, "extract_analysis_audio", lambda source, wav_path: wav_path.write_bytes(b"wav"))
    monkeypatch.setattr(pipeline, "save_waveform_json", lambda path, waveform: path.write_text("[]", encoding="utf-8"))
    monkeypatch.setattr(pipeline, "detect_speech_intervals", lambda wav_path: [])

    def fake_analyze_audio_blocks(wav_path, config, progress=None):
        # 顺手代一次分块回调：它在实际实现里是穿在同一条 progress 通道上的，
        # 不代这一下就漏掉了 analyze_blocks 阶段的细分进度。
        if progress is not None:
            progress(1, 2)
            progress(2, 2)
        return BlockAnalysisResult(waveform=[], inactive_intervals=[], sample_rate=16000)

    monkeypatch.setattr(pipeline, "analyze_audio_blocks", fake_analyze_audio_blocks)

    pipeline.analyze_source(
        source=source,
        project_dir=tmp_path / "project",
        config=AnalysisConfig(),
        progress=events.append,
    )

    # 0.2.0 阶段数从 8 降到 6：波形和低活动合并成一趟分块扫描
    assert [event.phase for event in events] == [
        "probe_source",
        "extract_audio",
        "analyze_blocks",
        "analyze_blocks",
        "analyze_blocks",
        "detect_speech",
        "build_timeline",
        "save_project",
    ]
    assert [event.current for event in events] == [1, 2, 3, 3, 3, 4, 5, 6]
    assert events[2].message == "正在分析音频"
    assert events[3].message == "正在分析音频（第 1/2 块）"
    assert events[-1].percent == 100.0


def test_analyze_source_still_runs_without_progress(monkeypatch, tmp_path):
    """progress 是可选参数，不传时整条链路也要能跑完。"""
    source = tmp_path / "input.mp4"
    source.write_bytes(b"fake")

    monkeypatch.setattr(pipeline, "probe_duration", lambda path: 10.0)
    monkeypatch.setattr(pipeline, "extract_analysis_audio", lambda source, wav_path: wav_path.write_bytes(b"wav"))
    monkeypatch.setattr(pipeline, "save_waveform_json", lambda path, waveform: path.write_text("[]", encoding="utf-8"))
    monkeypatch.setattr(pipeline, "detect_speech_intervals", lambda wav_path: [])
    monkeypatch.setattr(
        pipeline,
        "analyze_audio_blocks",
        lambda wav_path, config, progress=None: BlockAnalysisResult(
            waveform=[], inactive_intervals=[], sample_rate=16000
        ),
    )

    state = pipeline.analyze_source(
        source=source,
        project_dir=tmp_path / "project",
        config=AnalysisConfig(),
    )

    assert state.source.duration == 10.0
    assert (tmp_path / "project" / "segments.json").exists()
