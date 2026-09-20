import json
from pathlib import Path

from asmr_auto_cut.analysis import pipeline
from asmr_auto_cut.analysis.block_analysis import BlockAnalysisResult
from asmr_auto_cut.analysis.speech import SpeechDetection
from asmr_auto_cut.config import AnalysisConfig
from asmr_auto_cut.timeline.intervals import RawInterval

#: 替掉整趟 VAD：这些用例关心的是阶段的顺序和字段，不是切得准不准。
NO_SPEECH = lambda wav_path, config: SpeechDetection(speech=[], uncertain=[])  # noqa: E731


def test_analyze_source_reports_expected_phases(monkeypatch, tmp_path):
    events = []
    source = tmp_path / "input.mp4"
    source.write_bytes(b"fake")

    monkeypatch.setattr(pipeline, "probe_duration", lambda path: 10.0)
    monkeypatch.setattr(pipeline, "extract_analysis_audio", lambda source, wav_path: wav_path.write_bytes(b"wav"))
    monkeypatch.setattr(pipeline, "save_waveform_json", lambda path, waveform: path.write_text("[]", encoding="utf-8"))
    monkeypatch.setattr(pipeline, "detect_speech", NO_SPEECH)

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
    monkeypatch.setattr(pipeline, "detect_speech", NO_SPEECH)
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


def test_analyze_source_passes_the_review_band_all_the_way_to_disk(monkeypatch, tmp_path):
    """复核带必须一路走到 segments.json——中间任何一环漏掉它，界面都是一片素色。

    这条链路有四跳（detect_speech → assemble_project_state → mark_uncertain →
    save_project_state），而每一跳都能在不报错的前提下把带子丢掉：漏了就只是
    没有橙色段，没有任何异常。所以钉在最后一跳的产物上，而不是钉中间的调用。
    """
    source = tmp_path / "input.mp4"
    source.write_bytes(b"fake")
    band = RawInterval(start=2.0, end=4.0, label="uncertain", confidence=0.3, source="silero_vad_band")

    monkeypatch.setattr(pipeline, "probe_duration", lambda path: 10.0)
    monkeypatch.setattr(pipeline, "extract_analysis_audio", lambda source, wav_path: wav_path.write_bytes(b"wav"))
    monkeypatch.setattr(pipeline, "save_waveform_json", lambda path, waveform: path.write_text("[]", encoding="utf-8"))
    monkeypatch.setattr(
        pipeline, "detect_speech", lambda wav_path, config: SpeechDetection(speech=[], uncertain=[band])
    )
    monkeypatch.setattr(
        pipeline,
        "analyze_audio_blocks",
        lambda wav_path, config, progress=None: BlockAnalysisResult(
            waveform=[], inactive_intervals=[], sample_rate=16000
        ),
    )

    state = pipeline.analyze_source(
        source=source, project_dir=tmp_path / "project", config=AnalysisConfig()
    )

    marked = [item for item in state.segments if item.label == "uncertain"]
    assert [(item.start, item.end, item.action) for item in marked] == [(2.0, 4.0, "keep")]

    saved = json.loads((tmp_path / "project" / "segments.json").read_text(encoding="utf-8"))
    assert "uncertain" in json.dumps(saved)
    # 带子只加颜色：切段一条都不该多出来
    assert [item for item in state.segments if item.action == "cut"] == []
