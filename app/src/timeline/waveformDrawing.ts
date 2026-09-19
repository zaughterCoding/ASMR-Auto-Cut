import type { WaveformPoint } from "../types";
import type { TimeRange } from "./timeRange";

export interface DrawWaveformOptions {
  /** 要显示的区间，两端正好映射到画布的左右边缘。概览传自己的视口，缩放视图传选区。 */
  viewport: TimeRange;
  waveColor: string;
  backgroundColor: string;
}

/**
 * 把波形按时间映射到 columnCount 个像素列，每列取落在该列时间范围内最大的峰值。
 *
 * 抽成纯函数是为了能测：画布上画错了肉眼看不出对错，而这里的映射错一点就是整片空白。
 *
 * 有两件事容易写错：
 *
 * 1. **列号必须由「点的时刻」算出来，不能按点在数组里的下标平均分。** 点比像素多
 *    （长录音的概览、缩小后的缩放视图）时两种算法结果几乎一样，所以按下标写在测试里
 *    看不出来；但点比像素少（放大到几十秒以内）时，按下标分只会占满左边几个像素，
 *    右边整片是空的——这就是「缩放到一定程度后右边不显示音轨」那个 bug。
 *
 * 2. **点比像素少时一列里可能一个点都没有。** 这时沿用「下一个还没用掉的点」的值，
 *    画出来是阶梯状。阶梯不是缺陷：波形本来就只有每秒 20 个点，放到比这更细就该看到
 *    台阶，而不是一条平滑的假曲线。
 *
 * 列的归属是左闭右开（除了最后一列）：正好落在列边界上的点归右边那一列，这样
 * 列号和时间才对得上——用左闭右闭的话每个点都会往左偏一列。最后一列收口成闭区间，
 * 把时刻正好等于 viewport.end 的点也收进来，否则拖动选区时最右边那一列会在有和
 * 无之间闪。
 */
export function columnPeaks(
  points: WaveformPoint[],
  viewport: TimeRange,
  columnCount: number,
): number[] {
  if (columnCount <= 0) return [];
  const span = viewport.end - viewport.start;
  if (span <= 0 || points.length === 0) return new Array<number>(columnCount).fill(0);

  const peaks: number[] = [];
  const lastColumn = columnCount - 1;
  let cursor = 0;
  for (let column = 0; column < columnCount; column += 1) {
    const columnEnd = viewport.start + ((column + 1) / columnCount) * span;
    const includeEnd = column === lastColumn;
    let peak = 0;
    let filled = false;
    while (cursor < points.length) {
      const time = points[cursor].time;
      if (time > columnEnd || (time === columnEnd && !includeEnd)) break;
      if (points[cursor].peak > peak) peak = points[cursor].peak;
      filled = true;
      cursor += 1;
    }
    if (!filled) {
      // 这一列没吃到任何新点：用下一个还没用掉的点，后面没有了就用最后一个。
      peak = points[Math.min(cursor, points.length - 1)].peak;
    }
    peaks.push(peak);
  }
  return peaks;
}

/**
 * 把波形画到 canvas 上，按像素列聚合峰值。
 *
 * 波形是每秒 20 个点，一条 8 小时录音就有 57 万个点，而画布只有一千多像素宽；
 * 逐点画既慢又会因为一列内多次覆盖而虚高，所以每列只取该列覆盖到的最大峰值。
 *
 * 概览和缩放两个视图共用这里的绘制逻辑，区别只在 viewport 传什么。
 */
export function drawWaveform(
  canvas: HTMLCanvasElement,
  waveform: WaveformPoint[],
  options: DrawWaveformOptions,
): void {
  const context = canvas.getContext("2d");
  if (!context) return;

  // canvas 的位图尺寸要按设备像素比放大，否则在缩放不是 100% 的屏幕上会糊；
  // 放大之后把坐标系整体缩放回去，下面的绘制代码就都能用 CSS 像素来写。
  const ratio = window.devicePixelRatio || 1;
  const width = Math.max(1, Math.round(canvas.clientWidth));
  const height = Math.max(1, Math.round(canvas.clientHeight));
  canvas.width = Math.round(width * ratio);
  canvas.height = Math.round(height * ratio);
  context.setTransform(ratio, 0, 0, ratio, 0, 0);

  context.fillStyle = options.backgroundColor;
  context.fillRect(0, 0, width, height);

  const { viewport } = options;
  const visible = waveform.filter(
    (point) => point.time >= viewport.start && point.time <= viewport.end,
  );
  if (visible.length === 0) return;

  const middle = height / 2;
  const peaks = columnPeaks(visible, viewport, width);
  context.fillStyle = options.waveColor;

  for (let column = 0; column < peaks.length; column += 1) {
    // 最矮也留 1px：安静段落若真的画成 0 高，那一带会看起来像没数据。
    const barHeight = Math.max(1, Math.min(1, peaks[column]) * middle);
    context.fillRect(column, middle - barHeight, 1, barHeight * 2);
  }
}
