import { useEffect, useRef, useState } from "react";
import { segmentColors, segmentOpacity } from "../timeline/segmentColors";
import { clipSegmentsToRange, findSegmentAt } from "../timeline/segmentView";
import type { TimeRange } from "../timeline/timeRange";
import { moveRange, normalizeRange } from "../timeline/timeRange";
import { formatClock, formatRangeLabel } from "../timeline/timeFormat";
import { useCtrlWheelZoom } from "../timeline/useCtrlWheelZoom";
import { drawWaveform } from "../timeline/waveformDrawing";
import type { ProjectState, WaveformPoint } from "../types";

interface Props {
  project: ProjectState | null;
  waveform: WaveformPoint[] | null;
  /** 概览显示的时间范围。默认整条录音，Ctrl+滚轮可以放大。 */
  viewport: TimeRange;
  selectedSegmentId: string | null;
  selectedRange: TimeRange | null;
  onSelectSegment: (segmentId: string) => void;
  onChangeRange: (range: TimeRange) => void;
  onChangeViewport: (viewport: TimeRange) => void;
  playheadSeconds: number | null;
}

/** 小于这个位移的拖动当成点击。手抖几个像素不该产生一个意外选区。 */
const DRAG_THRESHOLD_PX = 4;
/** 概览最多放大到 1 秒。波形是每秒 20 个点，放到比这更细没有更多信息可看。 */
const MIN_VIEWPORT_SECONDS = 1;
const WAVE_COLOR = "#8fd3c7";
const WAVE_BACKGROUND = "#10131a";

interface DragState {
  mode: "create" | "move" | "pan";
  pointerId: number;
  startX: number;
  startTime: number;
  originalRange: TimeRange | null;
  /** 平移以「按下时的视口」为基准，见 handlePointerMove 里的说明。 */
  originalViewport: TimeRange;
  /** 是否已经越过阈值。放在 ref 里是因为 pointerup 要同步读到它。 */
  moved: boolean;
}

export function OverviewTimeline({
  project,
  waveform,
  viewport,
  selectedSegmentId,
  selectedRange,
  onSelectSegment,
  onChangeRange,
  onChangeViewport,
  playheadSeconds,
}: Props) {
  const sectionRef = useRef<HTMLElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const dragRef = useRef<DragState | null>(null);
  const [hoveredSegmentId, setHoveredSegmentId] = useState<string | null>(null);

  const duration = project?.source.duration ?? 0;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const redraw = () =>
      drawWaveform(canvas, waveform ?? [], {
        viewport,
        waveColor: WAVE_COLOR,
        backgroundColor: WAVE_BACKGROUND,
      });
    redraw();
    // 窗口尺寸变化后 clientWidth 才会更新，需要重画一次
    const observer = new ResizeObserver(redraw);
    observer.observe(canvas);
    return () => observer.disconnect();
  }, [waveform, viewport]);

  useCtrlWheelZoom(sectionRef, canvasRef, {
    range: duration > 0 ? viewport : null,
    duration,
    minDuration: MIN_VIEWPORT_SECONDS,
    onChange: onChangeViewport,
  });

  if (!project) return <section className="timeline empty">尚未载入时间轴</section>;

  const segments = project.segments;
  const viewportSpan = viewport.end - viewport.start;
  const zoomed = viewportSpan < duration - 0.01;

  /** 画布上的横坐标换算成绝对时刻。放大之后必须按视口算，不能再按整条录音算。 */
  function xToTime(clientX: number): number {
    const canvas = canvasRef.current;
    if (!canvas || viewportSpan <= 0) return viewport.start;
    const rect = canvas.getBoundingClientRect();
    if (rect.width <= 0) return viewport.start;
    const ratio = (clientX - rect.left) / rect.width;
    const time = viewport.start + ratio * viewportSpan;
    return Math.max(viewport.start, Math.min(viewport.end, time));
  }

  function handlePointerDown(event: React.PointerEvent<HTMLCanvasElement>) {
    if (duration <= 0) return;
    const startTime = xToTime(event.clientX);
    // Shift 优先于其它两种：平移要能在任何位置按下，包括压在选区上的时候，
    // 否则放大之后想把视口挪走就非得先点到选区外面去。
    const mode = event.shiftKey
      ? "pan"
      : selectedRange !== null &&
          startTime >= selectedRange.start &&
          startTime <= selectedRange.end
        ? "move"
        : "create";
    dragRef.current = {
      mode,
      pointerId: event.pointerId,
      startX: event.clientX,
      startTime,
      originalRange: selectedRange,
      originalViewport: viewport,
      moved: false,
    };
    event.currentTarget.setPointerCapture(event.pointerId);
  }

  function handlePointerMove(event: React.PointerEvent<HTMLCanvasElement>) {
    const drag = dragRef.current;
    if (!drag) {
      // 没在拖动时才做悬停高亮。拖动过程中高亮会跟着鼠标乱闪，反而干扰。
      setHoveredSegmentId(findSegmentAt(segments, xToTime(event.clientX))?.id ?? null);
      return;
    }
    if (!drag.moved && Math.abs(event.clientX - drag.startX) < DRAG_THRESHOLD_PX) return;
    drag.moved = true;

    if (drag.mode === "pan") {
      // 平移量必须用「按下时的视口」换算成秒。若拿当前视口去算 xToTime，视口一动
      // 同一个 clientX 对应的时刻就变了，位移会自我放大，拖起来像在加速跑。
      const canvas = canvasRef.current;
      const rect = canvas?.getBoundingClientRect();
      const startSpan = drag.originalViewport.end - drag.originalViewport.start;
      if (!rect || rect.width <= 0 || startSpan <= 0) return;
      const deltaSeconds = ((event.clientX - drag.startX) / rect.width) * startSpan;
      onChangeViewport(moveRange(drag.originalViewport, -deltaSeconds, duration));
      return;
    }

    const currentTime = xToTime(event.clientX);
    if (drag.mode === "create") {
      onChangeRange(normalizeRange(drag.startTime, currentTime, duration));
    } else if (drag.originalRange) {
      onChangeRange(moveRange(drag.originalRange, currentTime - drag.startTime, duration));
    }
  }

  function handlePointerUp(event: React.PointerEvent<HTMLCanvasElement>) {
    const drag = dragRef.current;
    dragRef.current = null;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    if (!drag) return;
    // 位移没过阈值 = 一次点击，这时才选中鼠标底下的段落。拖动结束时也走这里，
    // 但 moved 为 true 所以不会改选中项——否则每拖一次都会顺手选中终点所在的段。
    if (!drag.moved) {
      const hit = findSegmentAt(segments, xToTime(event.clientX));
      if (hit) onSelectSegment(hit.id);
    }
  }

  /** 选区可能被缩放到视口外，只有落在视口里的那部分才画。 */
  const selectionClip =
    selectedRange && viewportSpan > 0
      ? {
          start: Math.max(selectedRange.start, viewport.start),
          end: Math.min(selectedRange.end, viewport.end),
        }
      : null;
  const selectionVisible = selectionClip !== null && selectionClip.end > selectionClip.start;

  return (
    <section
      className={zoomed ? "timeline overview-timeline zoomed" : "timeline overview-timeline"}
      ref={sectionRef}
    >
      <canvas
        ref={canvasRef}
        className="timeline-waveform"
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerCancel={handlePointerUp}
        onPointerLeave={() => setHoveredSegmentId(null)}
      />
      <div className="timeline-segments">
        {viewportSpan > 0 &&
          clipSegmentsToRange(segments, viewport).map(({ segment, visibleStart, visibleEnd }) => {
            const left = ((visibleStart - viewport.start) / viewportSpan) * 100;
            const width = ((visibleEnd - visibleStart) / viewportSpan) * 100;
            const classes = ["segment"];
            if (segment.id === selectedSegmentId) classes.push("selected");
            if (segment.id === hoveredSegmentId) classes.push("hovered");
            return (
              <div
                key={segment.id}
                className={classes.join(" ")}
                title={`${segment.label} ${segment.action} ${segment.start.toFixed(1)}-${segment.end.toFixed(1)}s`}
                style={{
                  left: `${left}%`,
                  width: `${width}%`,
                  background: segmentColors[segment.label],
                  opacity: segmentOpacity(segment.action),
                }}
              />
            );
          })}
      </div>
      {selectionVisible && viewportSpan > 0 && (
        <div
          className="overview-selection"
          style={{
            left: `${((selectionClip.start - viewport.start) / viewportSpan) * 100}%`,
            width: `${((selectionClip.end - selectionClip.start) / viewportSpan) * 100}%`,
          }}
        />
      )}
      {playheadSeconds !== null &&
        playheadSeconds >= viewport.start &&
        playheadSeconds <= viewport.end &&
        viewportSpan > 0 && (
          <div
            className="timeline-playhead"
            style={{ left: `${((playheadSeconds - viewport.start) / viewportSpan) * 100}%` }}
          />
        )}
      <div className="overview-hint">
        <span>Ctrl + 滚轮 缩放 · Shift + 拖动 平移 · 拖动 框选</span>
        <span className="overview-viewport">
          {formatRangeLabel(viewport.start, viewport.end)} / 共 {formatClock(duration)}
        </span>
        {zoomed && (
          <button
            type="button"
            className="overview-reset"
            onClick={() => onChangeViewport({ start: 0, end: duration })}
          >
            显示整条
          </button>
        )}
      </div>
    </section>
  );
}
