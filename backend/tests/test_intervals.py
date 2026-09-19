from asmr_auto_cut.timeline.intervals import RawInterval, build_segments, merge_cut_intervals


def test_merge_cut_intervals_sorts_and_merges_overlaps():
    intervals = [
        RawInterval(start=5.0, end=7.0, label="talk", confidence=0.8, source="test"),
        RawInterval(start=1.0, end=3.0, label="inactive", confidence=0.9, source="test"),
        RawInterval(start=2.9, end=4.0, label="talk", confidence=0.7, source="test"),
    ]
    merged = merge_cut_intervals(intervals, merge_gap=0.2)
    assert [(item.start, item.end, item.label) for item in merged] == [
        (1.0, 4.0, "inactive"),
        (5.0, 7.0, "talk"),
    ]


def test_build_segments_inverts_cut_intervals():
    cuts = [RawInterval(start=2.0, end=4.0, label="talk", confidence=0.9, source="vad")]
    segments = build_segments(duration=6.0, cut_intervals=cuts)
    assert [(segment.start, segment.end, segment.label, segment.action) for segment in segments] == [
        (0.0, 2.0, "asmr", "keep"),
        (2.0, 4.0, "talk", "cut"),
        (4.0, 6.0, "asmr", "keep"),
    ]
