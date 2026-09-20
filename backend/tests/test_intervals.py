from asmr_auto_cut.timeline.intervals import (
    RawInterval,
    build_segments,
    merge_cut_intervals,
    subtract_intervals,
)


def covered(intervals: list[RawInterval]) -> float:
    """这些区间并起来一共盖住多少秒。跨标签合并与否不该改变这个数。"""
    total = 0.0
    end = float("-inf")
    for item in sorted(intervals, key=lambda i: i.start):
        total += max(0.0, item.end - max(item.start, end))
        end = max(end, item.end)
    return total


def test_merge_cut_intervals_merges_same_label_within_gap():
    intervals = [
        RawInterval(start=5.0, end=7.0, label="talk", confidence=0.8, source="test"),
        RawInterval(start=7.1, end=8.0, label="talk", confidence=0.7, source="test"),
        RawInterval(start=1.0, end=3.0, label="talk", confidence=0.9, source="test"),
    ]
    merged = merge_cut_intervals(intervals, merge_gap=0.2)
    assert [(item.start, item.end, item.label) for item in merged] == [
        (1.0, 3.0, "talk"),
        (5.0, 8.0, "talk"),
    ]


def test_merge_cut_intervals_keeps_different_labels_apart():
    """标签不同就不合并：合并只能留一个标签，一段 talk 会被整段显示成灰色静默。"""
    intervals = [
        RawInterval(start=1.0, end=3.0, label="inactive", confidence=0.8, source="test"),
        RawInterval(start=3.05, end=4.0, label="talk", confidence=0.9, source="test"),
    ]
    merged = merge_cut_intervals(intervals, merge_gap=0.2)
    assert [(item.start, item.end, item.label) for item in merged] == [
        (1.0, 3.0, "inactive"),
        (3.05, 4.0, "talk"),
    ]


def test_merge_cut_intervals_clips_overlap_keeping_every_second():
    """真重叠必须消解（时间轴是一层平铺，重叠的段会画在彼此上面），
    但消解只能改边界，不能改变切掉的总量——否则误剪/残留的测量全部失效。"""
    intervals = [
        RawInterval(start=1.0, end=3.0, label="inactive", confidence=0.8, source="test"),
        RawInterval(start=2.9, end=4.0, label="talk", confidence=0.9, source="test"),
    ]
    merged = merge_cut_intervals(intervals, merge_gap=0.2)
    assert [(item.start, item.end, item.label) for item in merged] == [
        (1.0, 3.0, "inactive"),
        (3.0, 4.0, "talk"),
    ]
    assert covered(merged) == covered(intervals) == 3.0


def test_merge_cut_intervals_drops_fully_contained_interval():
    """完全被包住的段丢弃——它一秒都不增加覆盖，留着只会造成重叠。"""
    intervals = [
        RawInterval(start=1.0, end=10.0, label="inactive", confidence=0.8, source="test"),
        RawInterval(start=4.0, end=5.0, label="talk", confidence=0.9, source="test"),
    ]
    merged = merge_cut_intervals(intervals, merge_gap=0.2)
    assert [(item.start, item.end, item.label) for item in merged] == [(1.0, 10.0, "inactive")]
    assert covered(merged) == covered(intervals) == 9.0


def test_subtract_intervals_holes_out_the_middle():
    intervals = [RawInterval(0.0, 10.0, "talk", 0.9, "vad")]
    holes = [RawInterval(4.0, 6.0, "uncertain", 0.3, "band")]
    assert [(item.start, item.end) for item in subtract_intervals(intervals, holes)] == [
        (0.0, 4.0),
        (6.0, 10.0),
    ]


def test_subtract_intervals_without_holes_returns_the_input():
    intervals = [RawInterval(0.0, 10.0, "talk", 0.9, "vad")]
    assert subtract_intervals(intervals, []) == intervals


def test_subtract_intervals_drops_a_fully_covered_interval():
    intervals = [RawInterval(0.0, 10.0, "talk", 0.9, "vad")]
    holes = [RawInterval(0.0, 10.0, "uncertain", 0.3, "band")]
    assert subtract_intervals(intervals, holes) == []


def test_subtract_intervals_handles_a_hole_straddling_the_start():
    """洞从区间左边伸进来：起点被吃掉，第一片从洞的结尾开始。"""
    intervals = [RawInterval(5.0, 10.0, "talk", 0.9, "vad")]
    holes = [RawInterval(0.0, 6.0, "uncertain", 0.3, "band")]
    assert [(item.start, item.end) for item in subtract_intervals(intervals, holes)] == [(6.0, 10.0)]


def test_subtract_intervals_carries_the_original_metadata():
    """挖出来的碎片还是原来那段东西，标签和出处不该被洞的标签覆盖。"""
    intervals = [RawInterval(0.0, 10.0, "talk", 0.9, "vad")]
    holes = [RawInterval(4.0, 6.0, "uncertain", 0.3, "band")]
    for piece in subtract_intervals(intervals, holes):
        assert (piece.label, piece.confidence, piece.source) == ("talk", 0.9, "vad")


def test_subtract_intervals_across_several_intervals_and_holes():
    """洞跨到下一个区间时要接着用，不能被第一个区间丢掉。"""
    intervals = [
        RawInterval(0.0, 2.0, "talk", 0.9, "vad"),
        RawInterval(4.0, 8.0, "talk", 0.9, "vad"),
        RawInterval(10.0, 12.0, "talk", 0.9, "vad"),
    ]
    holes = [
        RawInterval(1.0, 5.0, "uncertain", 0.3, "band"),
        RawInterval(7.0, 11.0, "uncertain", 0.3, "band"),
    ]
    pieces = subtract_intervals(intervals, holes)
    assert [(item.start, item.end) for item in pieces] == [(0.0, 1.0), (5.0, 7.0), (11.0, 12.0)]
    # 挖掉多少就该少多少：8 秒的输入被洞盖住 4 秒，剩下 4 秒。
    assert covered(pieces) == covered(intervals) - 4.0 == 4.0


def test_build_segments_inverts_cut_intervals():
    cuts = [RawInterval(start=2.0, end=4.0, label="talk", confidence=0.9, source="vad")]
    segments = build_segments(duration=6.0, cut_intervals=cuts)
    assert [(segment.start, segment.end, segment.label, segment.action) for segment in segments] == [
        (0.0, 2.0, "asmr", "keep"),
        (2.0, 4.0, "talk", "cut"),
        (4.0, 6.0, "asmr", "keep"),
    ]
