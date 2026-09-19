import { describe, expect, it } from "vitest";
import { moveRange, normalizeRange, zoomRangeAt } from "./timeRange";

describe("timeRange", () => {
  it("normalizes reversed ranges and enforces minimum duration", () => {
    expect(normalizeRange(10, 9.8, 60, 1)).toEqual({ start: 9.8, end: 10.8 });
  });

  it("moves ranges while clamping to duration", () => {
    expect(moveRange({ start: 10, end: 20 }, -15, 60)).toEqual({ start: 0, end: 10 });
    expect(moveRange({ start: 50, end: 60 }, 15, 60)).toEqual({ start: 50, end: 60 });
  });

  it("zooms around an anchor", () => {
    const range = zoomRangeAt({ start: 0, end: 100 }, 25, 0.5, 200, 1);
    expect(range.start).toBeCloseTo(12.5);
    expect(range.end).toBeCloseTo(62.5);
  });
});
