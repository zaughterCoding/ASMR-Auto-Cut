from asmr_auto_cut.config import AnalysisConfig
from asmr_auto_cut.models import TimelineSegment
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


def _remove_short_keep_segments(
    segments: list[TimelineSegment],
    duration: float,
    config: AnalysisConfig,
) -> list[TimelineSegment]:
    extra_cuts = [
        RawInterval(
            start=segment.start,
            end=segment.end,
            label="inactive",
            confidence=1.0,
            source="short_keep_filter",
        )
        for segment in segments
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
