from asmr_auto_cut.export import ffmpeg_export
from asmr_auto_cut.export.ffmpeg_export import export_clean_media
from asmr_auto_cut.models import MediaSource, ProjectState, TimelineSegment


def segment(id, start, end, action):
    return TimelineSegment(
        id=id,
        start=start,
        end=end,
        label="asmr",
        action=action,
        confidence=1.0,
        source="test",
    )


def test_export_reports_per_clip_progress(monkeypatch, tmp_path):
    events = []
    source = tmp_path / "input.mp4"
    source.write_bytes(b"fake")
    state = ProjectState(
        project_id="demo",
        source=MediaSource(path=str(source), duration=4.0),
        segments=[
            segment("seg_1", 0.0, 1.0, "keep"),
            segment("seg_2", 1.0, 2.0, "cut"),
            segment("seg_3", 2.0, 4.0, "keep"),
        ],
    )

    monkeypatch.setattr(ffmpeg_export, "ensure_ffmpeg_available", lambda: None)
    monkeypatch.setattr(ffmpeg_export, "run_command", lambda command: None)

    export_clean_media(state, tmp_path / "clean.mp4", progress=events.append)

    assert [event.phase for event in events] == [
        "build_clip_list",
        "render_clip",
        "render_clip",
        "concat_clips",
        "finish",
    ]
    assert events[-1].percent == 100.0
