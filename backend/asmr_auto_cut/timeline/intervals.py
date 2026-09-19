from dataclasses import dataclass

from asmr_auto_cut.models import SegmentLabel, TimelineSegment


@dataclass(frozen=True)
class RawInterval:
    start: float
    end: float
    label: SegmentLabel
    confidence: float
    source: str


def merge_cut_intervals(
    intervals: list[RawInterval],
    merge_gap: float = 0.2,
) -> list[RawInterval]:
    ordered = sorted(intervals, key=lambda item: (item.start, item.end))
    if not ordered:
        return []

    merged: list[RawInterval] = [ordered[0]]
    for current in ordered[1:]:
        previous = merged[-1]
        if current.start <= previous.end + merge_gap:
            merged[-1] = RawInterval(
                start=previous.start,
                end=max(previous.end, current.end),
                label=previous.label,
                confidence=max(previous.confidence, current.confidence),
                source=f"{previous.source}+{current.source}",
            )
        else:
            merged.append(current)
    return merged


def build_segments(duration: float, cut_intervals: list[RawInterval]) -> list[TimelineSegment]:
    segments: list[TimelineSegment] = []
    cursor = 0.0
    counter = 1
    for interval in cut_intervals:
        start = max(0.0, min(duration, interval.start))
        end = max(0.0, min(duration, interval.end))
        if start > cursor:
            segments.append(
                TimelineSegment(
                    id=f"seg_{counter:06d}",
                    start=cursor,
                    end=start,
                    label="asmr",
                    action="keep",
                    confidence=1.0,
                    source="rule_merge",
                )
            )
            counter += 1
        if end > start:
            segments.append(
                TimelineSegment(
                    id=f"seg_{counter:06d}",
                    start=start,
                    end=end,
                    label=interval.label,
                    action="cut",
                    confidence=interval.confidence,
                    source=interval.source,
                )
            )
            counter += 1
            cursor = end
    if cursor < duration:
        segments.append(
            TimelineSegment(
                id=f"seg_{counter:06d}",
                start=cursor,
                end=duration,
                label="asmr",
                action="keep",
                confidence=1.0,
                source="rule_merge",
            )
        )
    return segments
