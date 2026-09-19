from asmr_auto_cut.analysis.pipeline import assemble_project_state
from asmr_auto_cut.config import AnalysisConfig
from asmr_auto_cut.timeline.intervals import RawInterval


def test_assemble_project_state_combines_detectors():
    state = assemble_project_state(
        project_id="demo",
        source_path="input.mp4",
        duration=10.0,
        speech_intervals=[RawInterval(2.0, 3.0, "talk", 0.9, "vad")],
        inactive_intervals=[RawInterval(6.0, 8.0, "inactive", 0.8, "activity")],
        config=AnalysisConfig(),
    )
    assert [(segment.label, segment.action) for segment in state.segments] == [
        ("asmr", "keep"),
        ("talk", "cut"),
        ("asmr", "keep"),
        ("inactive", "cut"),
        ("asmr", "keep"),
    ]
