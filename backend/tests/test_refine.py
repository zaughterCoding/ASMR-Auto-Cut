from itertools import pairwise

from asmr_auto_cut.config import AnalysisConfig
from asmr_auto_cut.models import TimelineSegment
from asmr_auto_cut.timeline.refine import refine_segments


def segment(id, start, end, label, action):
    return TimelineSegment(
        id=id,
        start=start,
        end=end,
        label=label,
        action=action,
        confidence=1.0,
        source="test",
    )


def test_refine_expands_talk_cut_padding():
    refined = refine_segments(
        [segment("seg_1", 10.0, 12.0, "talk", "cut")],
        duration=30.0,
        config=AnalysisConfig(speech_padding_before=0.5, speech_padding_after=0.25),
    )
    # refine_segments 返回的是覆盖整段时长的完整列表，首尾会自动补出 asmr/keep 段，
    # 所以这里取 cut 段来断言 padding 是否生效，而不是取 refined[0]。
    cuts = [item for item in refined if item.action == "cut"]
    assert [(item.start, item.end) for item in cuts] == [(9.5, 12.25)]

    # 整段时长必须被无缝覆盖
    assert refined[0].start == 0.0
    assert refined[-1].end == 30.0
    for previous, current in pairwise(refined):
        assert previous.end == current.start


def test_refine_removes_short_keep_island():
    refined = refine_segments(
        [
            segment("seg_1", 0.0, 10.0, "talk", "cut"),
            segment("seg_2", 10.0, 10.2, "asmr", "keep"),
            segment("seg_3", 10.2, 20.0, "inactive", "cut"),
        ],
        duration=20.0,
        config=AnalysisConfig(min_keep_duration=0.5),
    )
    assert len(refined) == 1
    assert refined[0].start == 0.0
    assert refined[0].end == 20.0
    assert refined[0].action == "cut"
