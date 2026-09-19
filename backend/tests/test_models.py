import pytest
from pydantic import ValidationError

from asmr_auto_cut.models import MediaSource, ProjectState, TimelineSegment


def test_segment_rejects_negative_time():
    with pytest.raises(ValidationError):
        TimelineSegment(
            id="seg_1",
            start=-0.1,
            end=1.0,
            label="asmr",
            action="keep",
            confidence=1.0,
            source="test",
        )


def test_segment_rejects_end_before_start():
    with pytest.raises(ValidationError):
        TimelineSegment(
            id="seg_1",
            start=2.0,
            end=1.0,
            label="asmr",
            action="keep",
            confidence=1.0,
            source="test",
        )


def test_project_state_round_trip_data():
    state = ProjectState(
        version=1,
        project_id="demo",
        source=MediaSource(path="input.mp4", duration=10.0),
        segments=[
            TimelineSegment(
                id="seg_000001",
                start=0.0,
                end=2.0,
                label="talk",
                action="cut",
                confidence=0.8,
                source="silero_vad",
            )
        ],
    )
    dumped = state.model_dump()
    assert dumped["segments"][0]["label"] == "talk"
