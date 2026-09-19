import { useEffect, useRef } from "react";
import { segmentColors, segmentOpacity } from "../timeline/segmentColors";
import { drawWaveform } from "../timeline/waveformDrawing";
import type { ProjectState, WaveformPoint } from "../types";

interface Props {
  project: ProjectState | null;
  waveform: WaveformPoint[] | null;
  selectedSegmentId: string | null;
  onSelectSegment: (segmentId: string) => void;
  /** 当前播放位置，null 表示没有在播放。 */
  playheadSeconds: number | null;
}

const WAVE_COLOR = "#8fd3c7";
const WAVE_BACKGROUND = "#10131a";

export function Timeline({
  project,
  waveform,
  selectedSegmentId,
  onSelectSegment,
  playheadSeconds,
}: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

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
                opacity: segmentOpacity(segment.action),
                borderColor: selected ? "#ffffff" : "transparent",
              }}
            />
          );
        })}
      </div>
      {playheadSeconds !== null && duration > 0 && (
        <div
          className="timeline-playhead"
          style={{ left: `${(playheadSeconds / duration) * 100}%` }}
        />
      )}
    </section>
  );
}
