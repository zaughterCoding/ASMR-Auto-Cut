import { describe, expect, it } from "vitest";
import { clipSegmentsToRange } from "./segmentView";
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
