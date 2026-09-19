import { describe, expect, it } from "vitest";
import { clipSegmentsToRange, findSegmentAt } from "./segmentView";
import type { TimelineSegment } from "../types";

const segment: TimelineSegment = {
  id: "seg_1",
  start: 10,
  end: 20,
  label: "asmr",
  action: "keep",
  confidence: 1,
  source: "test",
  edited: false,
};

describe("clipSegmentsToRange", () => {
  it("clips segments to the visible range", () => {
    expect(clipSegmentsToRange([segment], { start: 15, end: 30 })).toEqual([
      { segment, visibleStart: 15, visibleEnd: 20 },
    ]);
  });

  it("drops hidden segments", () => {
    expect(clipSegmentsToRange([segment], { start: 21, end: 30 })).toEqual([]);
  });
});

describe("findSegmentAt", () => {
  // 首尾相接的三段，覆盖 0-30
  const segments: TimelineSegment[] = [
    { ...segment, id: "a", start: 0, end: 10 },
    { ...segment, id: "b", start: 10, end: 20 },
    { ...segment, id: "c", start: 20, end: 30 },
  ];

  it("finds the segment containing a time", () => {
    expect(findSegmentAt(segments, 5)?.id).toBe("a");
    expect(findSegmentAt(segments, 25)?.id).toBe("c");
  });

  it("returns null outside every segment", () => {
    expect(findSegmentAt(segments, -1)).toBeNull();
    expect(findSegmentAt(segments, 31)).toBeNull();
  });

  it("picks the left segment on a boundary", () => {
    // 落在交界处必须选中一个而不是两个都不选，且结果要确定
    expect(findSegmentAt(segments, 10)?.id).toBe("a");
  });
});
