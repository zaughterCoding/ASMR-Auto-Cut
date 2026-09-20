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


def cut_labels(refined):
    return [(item.start, item.end, item.label) for item in refined if item.action == "cut"]


def assert_tiles(refined, duration):
    """输出必须无缝铺满整条时间轴——时间轴是一层平铺，重叠或空洞都会画错。"""
    assert refined[0].start == 0.0
    assert refined[-1].end == duration
    for previous, current in pairwise(refined):
        assert previous.end == current.start


def test_refine_expands_talk_cut_padding():
    refined = refine_segments(
        [segment("seg_1", 10.0, 12.0, "talk", "cut")],
        duration=30.0,
        config=AnalysisConfig(speech_padding_before=0.5, speech_padding_after=0.25),
    )
    # refine_segments 返回的是覆盖整段时长的完整列表，首尾会自动补出 asmr/keep 段，
    # 所以这里取 cut 段来断言 padding 是否生效，而不是取 refined[0]。
    assert cut_labels(refined) == [(9.5, 12.25, "talk")]
    assert_tiles(refined, 30.0)


def test_refine_keeps_talk_and_inactive_apart_when_padding_makes_them_touch():
    """padding 让两段切段重叠时，消解只能改边界，不能让其中一个吞掉另一个。

    吞掉的后果是一整段 talk 被显示成灰色 inactive——用户看到「识别为静默、已自动
    去掉」，而那里其实有说话。夹缝被 padding 盖住，轮不到 short_keep_filter 出场。
    """
    refined = refine_segments(
        [
            segment("seg_1", 0.0, 10.0, "talk", "cut"),
            segment("seg_2", 10.0, 10.2, "asmr", "keep"),
            segment("seg_3", 10.2, 20.0, "inactive", "cut"),
        ],
        duration=20.0,
        config=AnalysisConfig(min_keep_duration=0.5),
    )
    assert cut_labels(refined) == [(0.0, 10.4, "talk"), (10.4, 20.0, "inactive")]
    assert_tiles(refined, 20.0)


def test_refine_labels_bridge_between_two_talks_as_talk():
    """夹在两段 talk 之间的短保留段并进 talk，不是标成 inactive。

    挂 inactive 的话，这段「说话中间的停顿」会显示成「识别为静默、已自动去掉」，
    语义不符，用户会误解。
    """
    refined = refine_segments(
        [
            segment("seg_1", 0.0, 10.0, "talk", "cut"),
            segment("seg_2", 10.0, 12.0, "asmr", "keep"),
            segment("seg_3", 12.0, 20.0, "talk", "cut"),
        ],
        duration=20.0,
        config=AnalysisConfig(min_keep_duration=1.5),
    )
    # padding 各撑 0.4s 后中间留出 1.2s 的保留段，短于 min_keep_duration 所以被吃掉。
    assert cut_labels(refined) == [(0.0, 20.0, "talk")]
    assert_tiles(refined, 20.0)


def test_refine_labels_bridge_by_the_longer_neighbour():
    """一边 talk 一边 inactive 时取更长的那一边——夹缝是从那段内容里咬下来的一口。"""
    talk_longer = refine_segments(
        [
            segment("seg_1", 0.0, 10.0, "talk", "cut"),
            segment("seg_2", 10.0, 12.0, "asmr", "keep"),
            segment("seg_3", 12.0, 20.0, "inactive", "cut"),
        ],
        duration=20.0,
        config=AnalysisConfig(min_keep_duration=2.0),
    )
    # 撑完 padding：talk 10.4s / inactive 8.1s，夹缝 1.5s 挂 talk
    assert cut_labels(talk_longer) == [(0.0, 11.9, "talk"), (11.9, 20.0, "inactive")]
    assert_tiles(talk_longer, 20.0)

    inactive_longer = refine_segments(
        [
            segment("seg_1", 0.0, 10.0, "inactive", "cut"),
            segment("seg_2", 10.0, 12.0, "asmr", "keep"),
            segment("seg_3", 12.0, 20.0, "talk", "cut"),
        ],
        duration=20.0,
        config=AnalysisConfig(min_keep_duration=2.0),
    )
    # 撑完 padding：inactive 10.1s / talk 8.4s，夹缝 1.5s 挂 inactive
    assert cut_labels(inactive_longer) == [(0.0, 11.6, "inactive"), (11.6, 20.0, "talk")]
    assert_tiles(inactive_longer, 20.0)
