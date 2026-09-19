import type { RefObject } from "react";
import { useEffect } from "react";
import type { TimeRange } from "./timeRange";
import { zoomRangeAt } from "./timeRange";

/** 滚一格缩放的比例，放大和缩小约互为倒数，来回滚不会积累漂移。 */
const ZOOM_IN_FACTOR = 0.82;
const ZOOM_OUT_FACTOR = 1.22;

interface Options {
  /** 要缩放的区间；为 null 时不响应滚轮。 */
  range: TimeRange | null;
  duration: number;
  /** 允许缩到的最短长度，概览和缩放视图各不相同。 */
  minDuration: number;
  onChange: (range: TimeRange) => void;
}

/**
 * Ctrl + 滚轮以光标所在时刻为轴缩放时间轴。
 *
 * 必须在显式声明 `passive: false` 的监听器里 preventDefault，否则 WebView2 会把整个
 * 界面缩放掉，时间轴一点不动。而这件事在 React 的 onWheel 里做不到：React 从 17 起
 * 把 onWheel 当作 passive 监听器挂在根节点上（wheel / touchstart / touchmove 都是），
 * 在 onWheel 里调 preventDefault 拦不住默认行为，只会打印一条警告。
 *
 * 抽成 hook 是因为概览和缩放两块画布都要这么做，而 passive 这个选项是最容易抄漏的
 * 一处——漏了不会报错，只会表现为「页面跟着滚，波形不缩」。
 *
 * @param containerRef 挂监听器的容器，通常是要接收滚轮的那个 section。
 * @param canvasRef 用来量宽度的画布，通常与 containerRef 同宽。
 */
export function useCtrlWheelZoom(
  containerRef: RefObject<HTMLElement>,
  canvasRef: RefObject<HTMLCanvasElement>,
  { range, duration, minDuration, onChange }: Options,
): void {
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const handleWheel = (event: WheelEvent) => {
      if (!event.ctrlKey) return;
      const canvas = canvasRef.current;
      if (!canvas || !range || duration <= 0) return;
      const rect = canvas.getBoundingClientRect();
      if (rect.width <= 0) return;
      event.preventDefault();

      // 以光标所在时刻为轴缩放：那个位置的内容钉住不动，用户看着的东西不会跑掉。
      const ratio = (event.clientX - rect.left) / rect.width;
      const anchor = range.start + ratio * (range.end - range.start);
      const factor = event.deltaY < 0 ? ZOOM_IN_FACTOR : ZOOM_OUT_FACTOR;
      onChange(zoomRangeAt(range, anchor, factor, duration, minDuration));
    };

    container.addEventListener("wheel", handleWheel, { passive: false });
    return () => container.removeEventListener("wheel", handleWheel);
  }, [containerRef, canvasRef, range, duration, minDuration, onChange]);
}
