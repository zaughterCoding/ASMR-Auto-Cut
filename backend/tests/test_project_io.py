import pytest

from asmr_auto_cut.models import MediaSource, ProjectState, TimelineSegment
from asmr_auto_cut.timeline.io import load_project_state, save_project_state


def make_state() -> ProjectState:
    return ProjectState(
        project_id="demo",
        source=MediaSource(path="input.mp4", duration=5.0),
        segments=[
            TimelineSegment(
                id="seg_000001",
                start=0.0,
                end=5.0,
                label="asmr",
                action="keep",
                confidence=1.0,
                source="test",
                edited=True,
            )
        ],
    )


def test_save_and_load_project_state(tmp_path):
    path = tmp_path / "project.json"
    save_project_state(path, make_state())
    loaded = load_project_state(path)
    assert loaded.segments[0].edited is True
    assert loaded.source.path == "input.mp4"


def test_load_project_state_reports_missing_source(tmp_path):
    path = tmp_path / "project.json"
    state = make_state()
    state.source.path = str(tmp_path / "missing.mp4")
    save_project_state(path, state)

    with pytest.raises(FileNotFoundError, match="Source file does not exist"):
        load_project_state(path, validate_source_exists=True)
