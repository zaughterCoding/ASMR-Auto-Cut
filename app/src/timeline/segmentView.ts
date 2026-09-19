import type { TimelineSegment } from "../types";
import type { TimeRange } from "./timeRange";

/**
 * 一个段落落在可见区间内的那部分。段落的 start/end 是它在整条录音里的绝对
 * 时间，visibleStart/visibleEnd 是裁到当前视口后的范围，画图时用后者。
 */
export interface VisibleSegment {
  segment: TimelineSegment;
  visibleStart: number;
  visibleEnd: number;
}

/**
 * 把段落裁到可见区间，完全落在外面的丢掉。
 *
 * 丢掉而不是返回零宽度的段：零宽度的段在 canvas 上什么都画不出来，却还会参与
 * 命中测试，用户点空白处会莫名其妙选中一个看不见的段。
 */
export function clipSegmentsToRange(
  segments: TimelineSegment[],
  range: TimeRange,
): VisibleSegment[] {
  return segments
    .map((segment) => ({
      segment,
      visibleStart: Math.max(segment.start, range.start),
      visibleEnd: Math.min(segment.end, range.end),
    }))
    .filter((item) => item.visibleEnd > item.visibleStart);
}
