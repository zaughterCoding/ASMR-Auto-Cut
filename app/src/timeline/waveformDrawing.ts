import type { WaveformPoint } from "../types";
import type { TimeRange } from "./timeRange";

export interface DrawWaveformOptions {
  /** 只画这个区间内的点；不给就画整条录音。缩放视图用它。 */
  range?: TimeRange;
  waveColor: string;
  backgroundColor: string;
}

/**
 * 把波形画到 canvas 上，按像素列聚合峰值。
 *
 * 波形是每秒 20 个点，一条 8 小时录音就有 57 万个点，而画布只有一千多像素宽；
 * 逐点画既慢又会因为一列内多次覆盖而虚高，所以每列只取该列覆盖到的最大峰值。
 *
 * 概览和缩放两个视图共用这里的绘制逻辑，区别只在传不传 range：概览不传（整条），
 * 缩放传当前选区。列数与 canvas 的 CSS 像素宽度绑定，和 range 的长度无关，所以
 * 拉近之后同一列覆盖的点变少，细节自然就出来了。
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
  const width = canvas.clientWidth;
  const height = canvas.clientHeight;
  canvas.width = Math.max(1, Math.round(width * ratio));
  canvas.height = Math.max(1, Math.round(height * ratio));
  context.setTransform(ratio, 0, 0, ratio, 0, 0);

  context.fillStyle = options.backgroundColor;
  context.fillRect(0, 0, width, height);

  // 尖头是闭区间：正好落在选区端点的点也要画进去，否则拖动时边缘会一闪一闪。
  const range = options.range;
  const visible = range
    ? waveform.filter((point) => point.time >= range.start && point.time <= range.end)
    : waveform;
  if (visible.length === 0 || width <= 0) return;

  const middle = height / 2;
  const columnCount = Math.min(width, visible.length);
  const pointsPerColumn = visible.length / columnCount;
  context.fillStyle = options.waveColor;

  for (let column = 0; column < columnCount; column += 1) {
    const start = Math.floor(column * pointsPerColumn);
    const end = Math.max(start + 1, Math.floor((column + 1) * pointsPerColumn));
    let peak = 0;
    for (let index = start; index < end && index < visible.length; index += 1) {
      if (visible[index].peak > peak) peak = visible[index].peak;
    }
    // 最矮也留 1px：安静段落若真的画成 0 高，那一带会看起来像没数据。
    const barHeight = Math.max(1, Math.min(1, peak) * middle);
    context.fillRect(column, middle - barHeight, 1, barHeight * 2);
  }
}
