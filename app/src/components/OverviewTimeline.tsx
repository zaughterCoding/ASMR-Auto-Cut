import { useEffect, useRef, useState } from "react";
import type { TimeRange } from "../timeline/timeRange";
import { moveRange, normalizeRange } from "../timeline/timeRange";
import { findSegmentAt } from "../timeline/segmentView";
import { drawWaveform } from "../timeline/waveformDrawing";
import type { ProjectState, WaveformPoint } from "../types";

interface Props {
  project: ProjectState | null;
  waveform: WaveformPoint[] | null;
  selectedSegmentId: string | null;
  selectedRange: TimeRange | null;
  onSelectSegment: (segmentId: string) => void;
  onChangeRange: (range: TimeRange) => void;
  playheadSeconds: number | null;
}

/** 小于这个位移的拖动当成点击。手抖几个像素不该产生一个意外选区。 */
const DRAG_THRESHOLD_PX = 4;
const WAVE_COLOR = "#8fd3c7";
const WAVE_BACKGROUND = "#10131a";

interface DragState {
  mode: "create" | "move";
  pointerId: number;
  startX: number;
  startTime: number;
  originalRange: TimeRange | null;
  /** 是否已经越过阈值。放在 ref 里是因为 pointerup 要同步读到它。 */
  moved: boolean;
}

export function OverviewTimeline({
  project,
  waveform,
  selectedSegmentId,
  selectedRange,
  onSelectSegment,
  onChangeRange,
  playheadSeconds,
}: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const dragRef = useRef<DragState | null>(null);
  const [hoveredSegmentId, setHoveredSegmentId] = useState<string | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const redraw = () =>
      drawWaveform(canvas, waveform ?? [], {
        waveColor: WAVE_COLOR,
        backgroundColor: WAVE_BACKGROUND,
      });
    redraw();
    // 窗口尺寸变化后 clientWidth 才会更新，需要重画一次
    const observer = new ResizeObserver(redraw);
    observer.observe(canvas);
    return () => observer.disconnect();
  }, [waveform]);

  if (!project) return <section className="timeline empty">尚未载入时间轴</section>;

  const duration = project.source.duration;
  const segments = project.segments;

  function xToTime(clientX: number): number {
    const canvas = canvasRef.current;
    if (!canvas || duration <= 0) return 0;
    const rect = canvas.getBoundingClientRect();
    if (rect.width <= 0) return 0;
    const ratio = (clientX - rect.left) / rect.width;
    return Math.max(0, Math.min(duration, ratio * duration));
  }

  function handlePointerDown(event: React.PointerEvent<HTMLCanvasElement>) {
    if (duration <= 0) return;
    const startTime = xToTime(event.clientX);
    // 起点落在已有选区内就是「搬走它」，否则是「新建一个」。判断必须先于新建，
    // 否则选区一旦存在就再也拖不动了。
    const insideSelection =
      selectedRange !== null && startTime >= selectedRange.start && startTime <= selectedRange.end;
    dragRef.current = {
      mode: insideSelection ? "move" : "create",
      pointerId: event.pointerId,
      startX: event.clientX,
      startTime,
      originalRange: selectedRange,
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

  return (
    <section className="timeline overview-timeline">
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
        {segments.map((segment) => {
          const left = duration > 0 ? (segment.start / duration) * 100 : 0;
          const width = duration > 0 ? ((segment.end - segment.start) / duration) * 100 : 0;
          const selected = segment.id === selectedSegmentId;
          const classes = ["segment"];
          if (selected) classes.push("selected");
          if (segment.id === hoveredSegmentId) classes.push("hovered");
          return (
            <div
              key={segment.id}
              className={classes.join(" ")}
              title={`${segment.label} ${segment.action} ${segment.start.toFixed(1)}-${segment.end.toFixed(1)}s`}
              style={{ left: `${left}%`, width: `${width}%` }}
            />
          );
        })}
      </div>
      {selectedRange && duration > 0 && (
        <div
          className="overview-selection"
          style={{
            left: `${(selectedRange.start / duration) * 100}%`,
            width: `${((selectedRange.end - selectedRange.start) / duration) * 100}%`,
          }}
        />
      )}
      {playheadSeconds !== null && duration > 0 && (
        <div className="timeline-playhead" style={{ left: `${(playheadSeconds / duration) * 100}%` }} />
      )}
    </section>
  );
}
