from asmr_auto_cut.config import AnalysisConfig
from asmr_auto_cut.models import SegmentLabel, TimelineSegment
from asmr_auto_cut.timeline.intervals import RawInterval, build_segments, merge_cut_intervals


def refine_segments(
    segments: list[TimelineSegment],
    duration: float,
    config: AnalysisConfig,
) -> list[TimelineSegment]:
    cut_intervals: list[RawInterval] = []
    for segment in segments:
        if segment.action != "cut":
            continue
        if segment.label == "talk":
            start = max(0.0, segment.start - config.speech_padding_before)
            end = min(duration, segment.end + config.speech_padding_after)
        elif segment.label == "inactive":
            start = max(0.0, segment.start - config.inactive_padding)
            end = min(duration, segment.end + config.inactive_padding)
        else:
            start = segment.start
            end = segment.end
        cut_intervals.append(
            RawInterval(
                start=start,
                end=end,
                label=segment.label,
                confidence=segment.confidence,
                source=segment.source,
            )
        )

    merged = merge_cut_intervals(cut_intervals, merge_gap=config.merge_gap)
    rebuilt = build_segments(duration=duration, cut_intervals=merged)
    return _remove_short_keep_segments(rebuilt, duration, config)


def _absorbed_label(segments: list[TimelineSegment], index: int) -> SegmentLabel:
    """短保留段被吃掉之后挂哪个标签——由它两边的切段决定。

    夹在两段 talk 之间就挂 talk：这段夹缝本来就是说话中间的停顿，不是「静默」，
    挂 inactive 会让用户以为那里什么都没发生。

    一边 talk 一边 inactive 时取**更长的那一边**，因为夹缝是从那段内容里咬下来的
    一口，理应算进咬它的那一方。等长时取左边（max 在并列时返回先出现的那个，
    而这里左边先列出）。

    两边都没有切段时退回 inactive——理论上不会发生：没有切段就没有 short_keep_filter。
    """
    neighbors = [
        segments[other]
        for other in (index - 1, index + 1)
        if 0 <= other < len(segments) and segments[other].action == "cut"
    ]
    if not neighbors:
        return "inactive"
    return max(neighbors, key=lambda item: item.end - item.start).label


def _remove_short_keep_segments(
    segments: list[TimelineSegment],
    duration: float,
    config: AnalysisConfig,
) -> list[TimelineSegment]:
    # 标签不再写死成 inactive（见 _absorbed_label）。挂错的代价不对称：把 talk 说成
    # inactive，用户看到灰色会以为「识别为静默、已自动去掉」，而那里其实有说话。
    extra_cuts = [
        RawInterval(
            start=segment.start,
            end=segment.end,
            label=_absorbed_label(segments, index),
            confidence=1.0,
            source="short_keep_filter",
        )
        for index, segment in enumerate(segments)
        if segment.action == "keep" and segment.end - segment.start < config.min_keep_duration
    ]
    existing_cuts = [
        RawInterval(
            start=segment.start,
            end=segment.end,
            label=segment.label,
            confidence=segment.confidence,
            source=segment.source,
        )
        for segment in segments
        if segment.action == "cut"
    ]
    if not extra_cuts:
        return segments
    merged = merge_cut_intervals(existing_cuts + extra_cuts, merge_gap=config.merge_gap)
    return build_segments(duration=duration, cut_intervals=merged)
