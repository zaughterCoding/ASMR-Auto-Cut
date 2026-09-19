import { describe, expect, it } from "vitest";
import type { WaveformPoint } from "../types";
import { columnPeaks } from "./waveformDrawing";

/** 造一个每秒 step 个点的波形，时间从 0 开始。 */
function pointsAt(peaks: number[], step = 1): WaveformPoint[] {
  return peaks.map((peak, index) => ({ time: index * step, peak, rms: peak }));
}

describe("columnPeaks", () => {
  it("点比像素多时每列取覆盖到的最大峰值", () => {
    const peaks = columnPeaks(pointsAt([0.1, 0.5, 0.9, 0.2]), { start: 0, end: 4 }, 4);
    expect(peaks).toEqual([0.1, 0.5, 0.9, 0.2]);
  });

  it("点多于列数时一列收多个点，取其中最大的", () => {
    const points = pointsAt([0.1, 0.5, 0.9, 0.2], 0.5);
    // 视口 0–2 秒、2 列。第 1 列收到 0 和 0.5，最大 0.5；第 2 列收到 1.0 和 1.5，
    // 最大 0.9。落在边界上的 1.0 归右列，所以第 1 列拿不到它。
    expect(columnPeaks(points, { start: 0, end: 2 }, 2)).toEqual([0.5, 0.9]);
  });

  it("点比像素少时铺满整个宽度，右边不能是空的", () => {
    // 这是「缩放到一定程度后右边不显示音轨」那个 bug 的回归测试：4 个点画成
    // 100 列，按下标分配只会用掉左边 4 列，右边 96 列全空。
    const peaks = columnPeaks(pointsAt([0.1, 0.9, 0.4, 0.7]), { start: 0, end: 3 }, 100);
    expect(peaks).toHaveLength(100);
    expect(peaks.every((peak) => peak > 0)).toBe(true);
  });

  it("放大到点比像素少时呈阶梯状，每列取最近的那个点", () => {
    // 视口 0–1 秒、4 列，点每秒一个：第 1 列落在第一个点上，
    // 其余三列没有新点，沿用「下一个还没用掉的点」
    const peaks = columnPeaks(pointsAt([0.2, 0.8]), { start: 0, end: 1 }, 4);
    expect(peaks).toEqual([0.2, 0.8, 0.8, 0.8]);
  });

  it("视口右端点上的点属于最后一列", () => {
    const peaks = columnPeaks(pointsAt([0.1, 0.4, 0.9]), { start: 0, end: 2 }, 2);
    expect(peaks[1]).toBeCloseTo(0.9, 6);
  });

  it("视口里没有点时全是 0", () => {
    expect(columnPeaks([], { start: 0, end: 4 }, 3)).toEqual([0, 0, 0]);
  });

  it("视口长度非法或列数为 0 时不炸", () => {
    expect(columnPeaks(pointsAt([1]), { start: 5, end: 5 }, 3)).toEqual([0, 0, 0]);
    expect(columnPeaks(pointsAt([1]), { start: 0, end: 1 }, 0)).toEqual([]);
  });
});
