import { useEffect, useRef } from "react";
import type { ProjectState, WaveformPoint } from "../types";

interface Props {
  project: ProjectState | null;
  waveform: WaveformPoint[] | null;
  selectedSegmentId: string | null;
  onSelectSegment: (segmentId: string) => void;
}

const segmentColors = {
  asmr: "#2f9e44",
  talk: "#e03131",
  inactive: "#868e96",
  uncertain: "#f08c00",
};

const WAVE_COLOR = "#8fd3c7";
const WAVE_BACKGROUND = "#10131a";

/**
 * 按像素列聚合波形峰值后再绘制。
 *
 * 波形是每秒 20 个点，一条 8 小时录音就有 57 万个点，而画布只有一千多像素宽；
 * 逐点画既慢又会因为一列内多次覆盖而虚高，所以每列只取该列覆盖到的最大峰值。
 */
function drawWaveform(
  canvas: HTMLCanvasElement,
  waveform: WaveformPoint[],
): void {
  const context = canvas.getContext("2d");
  if (!context) return;

  const ratio = window.devicePixelRatio || 1;
  const width = canvas.clientWidth;
  const height = canvas.clientHeight;
  canvas.width = Math.max(1, Math.round(width * ratio));
  canvas.height = Math.max(1, Math.round(height * ratio));
  context.setTransform(ratio, 0, 0, ratio, 0, 0);

  context.fillStyle = WAVE_BACKGROUND;
  context.fillRect(0, 0, width, height);

  if (waveform.length === 0 || width <= 0) return;

  const middle = height / 2;
  const columnCount = Math.min(width, waveform.length);
  const pointsPerColumn = waveform.length / columnCount;
  context.fillStyle = WAVE_COLOR;

  for (let column = 0; column < columnCount; column += 1) {
    const start = Math.floor(column * pointsPerColumn);
    const end = Math.max(start + 1, Math.floor((column + 1) * pointsPerColumn));
    let peak = 0;
    for (let index = start; index < end && index < waveform.length; index += 1) {
      if (waveform[index].peak > peak) peak = waveform[index].peak;
    }
    const barHeight = Math.max(1, Math.min(1, peak) * middle);
    context.fillRect(column, middle - barHeight, 1, barHeight * 2);
  }
}

export function Timeline({
  project,
  waveform,
  selectedSegmentId,
  onSelectSegment,
}: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const redraw = () => drawWaveform(canvas, waveform ?? []);
    redraw();
    // 窗口尺寸变化后 clientWidth 才会更新，需要重画一次
    const observer = new ResizeObserver(redraw);
    observer.observe(canvas);
    return () => observer.disconnect();
  }, [waveform]);

  if (!project) return <section className="timeline empty">尚未载入时间轴</section>;

  const duration = project.source.duration;

  return (
    <section className="timeline">
      <canvas ref={canvasRef} className="timeline-waveform" />
      <div className="timeline-segments">
        {project.segments.map((segment) => {
          const left = duration > 0 ? (segment.start / duration) * 100 : 0;
          const width = duration > 0 ? ((segment.end - segment.start) / duration) * 100 : 0;
          const selected = segment.id === selectedSegmentId;
          return (
            <button
              type="button"
              key={segment.id}
              className={selected ? "segment selected" : "segment"}
              title={`${segment.label} ${segment.action} ${segment.start.toFixed(1)}-${segment.end.toFixed(1)}s`}
              onClick={() => onSelectSegment(segment.id)}
              style={{
                left: `${left}%`,
                width: `${width}%`,
                // 切除段落压暗，保留段落用标签色标出
                background: segmentColors[segment.label],
                opacity: segment.action === "cut" ? 0.32 : 0.72,
                borderColor: selected ? "#ffffff" : "transparent",
              }}
            />
          );
        })}
      </div>
    </section>
  );
}
