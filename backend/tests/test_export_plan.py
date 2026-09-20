import pytest

from asmr_auto_cut.export.ffmpeg_export import (
    DEFAULT_FADE_SECONDS,
    ExportClip,
    _clip_command,
    build_keep_clips,
    export_clean_media,
)
from asmr_auto_cut.models import MediaSource, ProjectState, TimelineSegment


def test_build_keep_clips_uses_edited_actions():
    state = ProjectState(
        project_id="demo",
        source=MediaSource(path="input.mp4", duration=6.0),
        segments=[
            TimelineSegment(id="seg_1", start=0.0, end=2.0, label="asmr", action="keep", confidence=1, source="test"),
            TimelineSegment(id="seg_2", start=2.0, end=4.0, label="talk", action="keep", confidence=1, source="manual", edited=True),
            TimelineSegment(id="seg_3", start=4.0, end=6.0, label="inactive", action="cut", confidence=1, source="test"),
        ],
    )
    clips = build_keep_clips(state)
    assert [(clip.start, clip.end) for clip in clips] == [(0.0, 2.0), (2.0, 4.0)]


def test_build_keep_clips_exports_uncertain_segments():
    """uncertain 是「保留，但请你听一遍」，所以它必须进成品。

    这里防的是一张标签白名单：如果哪天导出改成「只认某个标签列表」，uncertain
    会被整段丢掉，而丢掉的恰好是复核步骤专门挑出来给用户听的那部分音频——
    出错时没有任何异常，只是成品里安静地少了东西，用户很难发现。
    """
    state = ProjectState(
        project_id="demo",
        source=MediaSource(path="input.mp4", duration=8.0),
        segments=[
            TimelineSegment(id="seg_1", start=0.0, end=2.0, label="asmr", action="keep", confidence=1, source="test"),
            TimelineSegment(id="seg_2", start=2.0, end=4.0, label="uncertain", action="keep", confidence=0.3, source="silero_vad_band"),
            TimelineSegment(id="seg_3", start=4.0, end=6.0, label="talk", action="cut", confidence=1, source="test"),
            TimelineSegment(id="seg_4", start=6.0, end=8.0, label="uncertain", action="keep", confidence=0.3, source="silero_vad_band"),
        ],
    )

    clips = build_keep_clips(state)

    assert [(clip.start, clip.end) for clip in clips] == [(0.0, 2.0), (2.0, 4.0), (6.0, 8.0)]


def test_clip_command_applies_fades_around_the_requested_window():
    command = _clip_command(
        "input.mp4", ExportClip(10.0, 40.0), "clip.mp4", DEFAULT_FADE_SECONDS, "quality"
    )

    # -ss/-to 必须在 -i 之前，才能走 input seek 且不整条解码
    assert command.index("-ss") < command.index("-i")
    assert command[command.index("-ss") + 1] == "10.000"
    assert command[command.index("-to") + 1] == "40.000"
    # 音频重编码 + 首尾 afade，视频轨直接 copy
    assert command[command.index("-c:a") + 1] == "aac"
    assert command[command.index("-c:v") + 1] == "copy"
    fade = command[command.index("-af") + 1]
    assert fade == "afade=t=in:st=0:d=0.030,afade=t=out:st=29.970:d=0.030"


def test_clip_command_clamps_fade_for_very_short_clips():
    # 20ms 的片段放不下两个 30ms 渐变，应各自收窄到半长，避免首尾重叠
    command = _clip_command(
        "input.mp4", ExportClip(5.0, 5.02), "clip.mp4", DEFAULT_FADE_SECONDS, "quality"
    )
    assert command[command.index("-af") + 1] == "afade=t=in:st=0:d=0.010,afade=t=out:st=0.010:d=0.010"


def test_clip_command_without_fade_omits_the_filter():
    command = _clip_command("input.mp4", ExportClip(0.0, 1.0), "clip.mp4", 0.0, "quality")
    assert "-af" not in command


def test_export_rejects_timeline_without_keep_segments(tmp_path):
    state = ProjectState(
        project_id="demo",
        source=MediaSource(path="input.mp4", duration=4.0),
        segments=[
            TimelineSegment(id="seg_1", start=0.0, end=4.0, label="talk", action="cut", confidence=1, source="test"),
        ],
    )
    with pytest.raises(RuntimeError, match="no keep segments"):
        export_clean_media(state, tmp_path / "clean.mp4")
