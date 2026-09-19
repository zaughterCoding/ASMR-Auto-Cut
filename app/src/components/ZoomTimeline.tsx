import { useEffect, useRef } from "react";
import { segmentColors, segmentOpacity } from "../timeline/segmentColors";
import { clipSegmentsToRange } from "../timeline/segmentView";
import type { TimeRange } from "../timeline/timeRange";
import { zoomRangeAt } from "../timeline/timeRange";
import { drawWaveform } from "../timeline/waveformDrawing";
import type { ProjectState, WaveformPoint } from "../types";

interface Props {
  project: ProjectState | null;
  waveform: WaveformPoint[] | null;
  range: TimeRange | null;
  selectedSegmentId: string | null;
  onSelectSegment: (segmentId: string) => void;
  onChangeRange: (range: TimeRange) => void;
  playheadSeconds: number | null;
}

const WAVE_COLOR = "#a5f3fc";
const WAVE_BACKGROUND = "#0f121a";

/** 滚一格缩放的比例，放大和缩小约互为倒数，来回滚不会积累漂移。 */
const ZOOM_IN_FACTOR = 0.82;
const ZOOM_OUT_FACTOR = 1.22;

export function ZoomTimeline({
  project,
  waveform,
  range,
  selectedSegmentId,
  onSelectSegment,
  onChangeRange,
  playheadSeconds,
}: Props) {
  const sectionRef = useRef<HTMLElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const duration = project?.source.duration ?? 0;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const redraw = () =>
      drawWaveform(canvas, waveform ?? [], {
        range: range ?? undefined,
        waveColor: WAVE_COLOR,
        backgroundColor: WAVE_BACKGROUND,
      });
    redraw();
    // 窗口尺寸变化后 clientWidth 才会更新，需要重画一次
    const observer = new ResizeObserver(redraw);
    observer.observe(canvas);
    return () => observer.disconnect();
  }, [waveform, range]);

  // Ctrl+滚轮必须 preventDefault，否则 WebView2 会把整个界面缩放掉，时间轴一点
  // 不动。而这件事只能在非 passive 的监听器里做：React 从 17 起把 onWheel 作为
  // passive 监听器挂在根节点上（wheel/touchstart/touchmove 都是），在 onWheel 里
  // 调 preventDefault 拦不住默认行为，只会打印一条警告。所以这里手工挂一个显式
  // 声明 passive: false 的监听器。
  useEffect(() => {
    const section = sectionRef.current;
    if (!section) return;

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
      onChangeRange(zoomRangeAt(range, anchor, factor, duration));
    };

    section.addEventListener("wheel", handleWheel, { passive: false });
    return () => section.removeEventListener("wheel", handleWheel);
  }, [range, duration, onChangeRange]);

  if (!project || !range) {
    return <section className="zoom-timeline empty">请在上方音轨选择一个范围</section>;
  }

  const rangeDuration = range.end - range.start;
  if (rangeDuration <= 0) {
    return <section className="zoom-timeline empty">请在上方音轨选择一个范围</section>;
  }

  const visibleSegments = clipSegmentsToRange(project.segments, range);

  return (
    <section className="zoom-timeline" ref={sectionRef}>
      <canvas ref={canvasRef} className="zoom-waveform" />
      <div className="zoom-segments">
        {visibleSegments.map(({ segment, visibleStart, visibleEnd }) => {
          const left = ((visibleStart - range.start) / rangeDuration) * 100;
          const width = ((visibleEnd - visibleStart) / rangeDuration) * 100;
          return (
            <button
              type="button"
              key={segment.id}
              className={segment.id === selectedSegmentId ? "zoom-segment selected" : "zoom-segment"}
              onClick={() => onSelectSegment(segment.id)}
              style={{
                left: `${left}%`,
                width: `${width}%`,
                background: segmentColors[segment.label],
                opacity: segmentOpacity(segment.action),
              }}
              title={`${segment.label} ${segment.action} ${segment.start.toFixed(2)}-${segment.end.toFixed(2)}s`}
            >
              {segment.label}
            </button>
          );
        })}
      </div>
      {playheadSeconds !== null &&
        playheadSeconds >= range.start &&
        playheadSeconds <= range.end && (
          <div
            className="timeline-playhead zoom-playhead"
            style={{ left: `${((playheadSeconds - range.start) / rangeDuration) * 100}%` }}
          />
        )}
    </section>
  );
}
