from itertools import pairwise

from asmr_auto_cut.config import REVIEW_BANDS, AnalysisConfig
from asmr_auto_cut.models import TimelineSegment
from asmr_auto_cut.timeline.intervals import RawInterval
from asmr_auto_cut.timeline.review import mark_uncertain


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


def band(start, end):
    return RawInterval(start=start, end=end, label="uncertain", confidence=0.3, source="band")


def assert_tiles(segments, start, end):
    """输出必须仍然无缝无叠地铺满输入覆盖的那一段。

    只查首尾和相接，不查能不能盖到 0：mark_uncertain 不该凭空造出输入里没有的段，
    所以它保留了输入的范围，输入从 2 秒开始输出就从 2 秒开始。
    """
    assert segments[0].start == start
    assert segments[-1].end == end
    for previous, current in pairwise(segments):
        assert previous.end == current.start


def test_mark_uncertain_only_relabels_keep_segments():
    """切段逐位原样返回——这是整个功能的立足点：它只加颜色，不动刀。

    复核带盖在切段上时什么都不做。切段注定要删，标了色只会让人以为那一刀还能商量。
    """
    segments = [
        segment("seg_1", 0.0, 5.0, "asmr", "keep"),
        segment("seg_2", 5.0, 8.0, "talk", "cut"),
        segment("seg_3", 8.0, 12.0, "asmr", "keep"),
    ]
    marked = mark_uncertain(segments, [band(1.0, 2.0), band(6.0, 7.0)])

    assert [item for item in marked if item.action == "cut"] == [segments[1]]
    assert [(item.start, item.end, item.label) for item in marked] == [
        (0.0, 1.0, "asmr"),
        (1.0, 2.0, "uncertain"),
        (2.0, 5.0, "asmr"),
        (5.0, 8.0, "talk"),
        (8.0, 12.0, "asmr"),
    ]
    assert_tiles(marked, 0.0, 12.0)


def test_mark_uncertain_keeps_ids_stable_for_untouched_segments():
    """没被切开的段 id 一个都不变，切出来的后续片挂后缀。"""
    segments = [
        segment("seg_1", 0.0, 5.0, "asmr", "keep"),
        segment("seg_2", 5.0, 9.0, "asmr", "keep"),
    ]
    marked = mark_uncertain(segments, [band(1.0, 2.0)])
    assert [item.id for item in marked] == ["seg_1", "seg_1_u1", "seg_1_u2", "seg_2"]


def test_mark_uncertain_absorbs_a_fully_covered_keep_segment():
    """整段落在复核带里就整段变 uncertain，不会切出零长度的空段。"""
    segments = [segment("seg_1", 0.0, 5.0, "asmr", "keep")]
    marked = mark_uncertain(segments, [band(1.0, 4.0)])
    assert [(item.start, item.end, item.label) for item in marked] == [
        (0.0, 1.0, "asmr"),
        (1.0, 4.0, "uncertain"),
        (4.0, 5.0, "asmr"),
    ]
    assert_tiles(marked, 0.0, 5.0)

    swallowed = mark_uncertain(segments, [band(0.0, 5.0)])
    assert [(item.start, item.end, item.label) for item in swallowed] == [(0.0, 5.0, "uncertain")]


def test_mark_uncertain_handles_a_band_straddling_the_segment_edges():
    """复核带伸出段外时按段裁掉——段与段是独立的，不能借邻居的地。"""
    segments = [
        segment("seg_1", 2.0, 6.0, "asmr", "keep"),
        segment("seg_2", 6.0, 10.0, "asmr", "keep"),
    ]
    marked = mark_uncertain(segments, [band(0.0, 3.0), band(9.0, 20.0)])
    assert [(item.start, item.end, item.label) for item in marked] == [
        (2.0, 3.0, "uncertain"),
        (3.0, 6.0, "asmr"),
        (6.0, 9.0, "asmr"),
        (9.0, 10.0, "uncertain"),
    ]
    assert_tiles(marked, 2.0, 10.0)


def test_mark_uncertain_without_a_band_changes_nothing():
    segments = [segment("seg_1", 0.0, 5.0, "asmr", "keep")]
    assert mark_uncertain(segments, []) == segments


def test_review_bands_all_open_a_band_below_the_speech_threshold():
    """每一档都得真的开出一条带——等于或高过 vad_threshold 就是关掉了复核带，
    那样用户选了「细致」却一个高亮都看不到。"""
    default = AnalysisConfig()
    assert default.vad_uncertain_threshold < default.vad_threshold
    for name, lower in REVIEW_BANDS.items():
        assert 0 <= lower < default.vad_threshold, name
