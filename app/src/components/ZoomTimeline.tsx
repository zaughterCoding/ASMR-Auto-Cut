import { useEffect, useRef, useState } from "react";
import { segmentColors, segmentOpacity } from "../timeline/segmentColors";
import { clipSegmentsToRange } from "../timeline/segmentView";
import type { TimeRange } from "../timeline/timeRange";
import { useCtrlWheelZoom } from "../timeline/useCtrlWheelZoom";
import { drawWaveform } from "../timeline/waveformDrawing";
import type { ProjectState, WaveformPoint } from "../types";

interface Props {
  project: ProjectState | null;
  waveform: WaveformPoint[] | null;
  range: TimeRange | null;
  selectedSegmentId: string | null;
  onSelectSegment: (segmentId: string) => void;
  onChangeRange: (range: TimeRange) => void;
  /** 拖动倒三角时报告新的播放起点，单位秒。 */
  onSeek: (seconds: number) => void;
  playheadSeconds: number | null;
}

const WAVE_COLOR = "#a5f3fc";
const WAVE_BACKGROUND = "#0f121a";

/** 最多放大到 1 秒，再细就没有更多信息可看了（波形是每秒 20 个点）。 */
const MIN_RANGE_SECONDS = 1;

export function ZoomTimeline({
  project,
  waveform,
  range,
  selectedSegmentId,
  onSelectSegment,
  onChangeRange,
  onSeek,
  playheadSeconds,
}: Props) {
  const sectionRef = useRef<HTMLElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  /**
   * 拖动中的播放头位置，非 null 表示正在拖。
   *
   * 同时存 state 和 ref：state 给渲染用，ref 给 pointerup 同步读。松手那一瞬间
   * React 可能还没重渲染完，只读 state 会拿到上一个位置，落点差一帧。
   */
  const [scrubSeconds, setScrubSeconds] = useState<number | null>(null);
  const scrubRef = useRef<number | null>(null);
  /** 还没上报出去的那一帧的 seek 目标。 */
  const pendingSeek = useRef<number | null>(null);
  const seekFrame = useRef<number | null>(null);
  const duration = project?.source.duration ?? 0;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const redraw = () =>
      drawWaveform(canvas, waveform ?? [], {
        viewport: range ?? { start: 0, end: 0 },
        waveColor: WAVE_COLOR,
        backgroundColor: WAVE_BACKGROUND,
      });
    redraw();
    // 窗口尺寸变化后 clientWidth 才会更新，需要重画一次
    const observer = new ResizeObserver(redraw);
    observer.observe(canvas);
    return () => observer.disconnect();
  }, [waveform, range]);

  // 卸载时把还没跑的那一帧撤掉，否则会在组件没了之后调 onSeek。
  useEffect(
    () => () => {
      if (seekFrame.current !== null) cancelAnimationFrame(seekFrame.current);
    },
    [],
  );

  useCtrlWheelZoom(sectionRef, canvasRef, {
    range,
    duration,
    minDuration: MIN_RANGE_SECONDS,
    onChange: onChangeRange,
  });

  if (!project || !range) {
    return <section className="zoom-timeline empty">请在上方音轨选择一个范围</section>;
  }

  // 下面几个闭包要用，先收成局部变量：range 是 props 解构出来的，收一下类型才稳。
  const view = range;
  const rangeDuration = view.end - view.start;
  if (rangeDuration <= 0) {
    return <section className="zoom-timeline empty">请在上方音轨选择一个范围</section>;
  }

  const visibleSegments = clipSegmentsToRange(project.segments, view);

  /** 画布上的横坐标换算成绝对时刻，夹在视口内。 */
  function timeAt(clientX: number): number {
    const rect = sectionRef.current?.getBoundingClientRect();
    if (!rect || rect.width <= 0) return view.start;
    const ratio = (clientX - rect.left) / rect.width;
    return Math.max(view.start, Math.min(view.end, view.start + ratio * rangeDuration));
  }

  function updateScrub(seconds: number | null) {
    scrubRef.current = seconds;
    setScrubSeconds(seconds);
  }

  /**
   * 上报播放起点，但一帧最多一次。
   *
   * 高刷新率鼠标的 pointermove 能到每秒上千次，而每一次上报都会让播放器写一次
   * audio.currentTime，那是一次真正的 seek。不合并的话拖动会拖垮播放器，表现为
   * 声音断续、三角卡顿。合并到动画帧上，最多一帧一次，视觉上照样跟手。
   */
  function reportSeek(seconds: number) {
    pendingSeek.current = seconds;
    if (seekFrame.current !== null) return;
    seekFrame.current = requestAnimationFrame(() => {
      seekFrame.current = null;
      const target = pendingSeek.current;
      pendingSeek.current = null;
      if (target !== null) onSeek(target);
    });
  }

  function handleScrubDown(event: React.PointerEvent<HTMLButtonElement>) {
    event.preventDefault();
    updateScrub(timeAt(event.clientX));
    event.currentTarget.setPointerCapture(event.pointerId);
  }

  function handleScrubMove(event: React.PointerEvent<HTMLButtonElement>) {
    if (scrubRef.current === null) return;
    const seconds = timeAt(event.clientX);
    if (seconds === scrubRef.current) return;
    updateScrub(seconds);
    reportSeek(seconds);
  }

  function handleScrubUp(event: React.PointerEvent<HTMLButtonElement>) {
    const landed = scrubRef.current;
    if (landed === null) return;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    // 撤掉还没跑的那一帧，直接按落点报一次：拖动最后一小段可能没凑够一帧，
    // 那样松手的位置会和画面上三角的位置对不上。
    if (seekFrame.current !== null) {
      cancelAnimationFrame(seekFrame.current);
      seekFrame.current = null;
    }
    pendingSeek.current = null;
    onSeek(landed);
    updateScrub(null);
  }

  // 播放头位置。倒三角是控件而不是读数，所以播放头跑到视口外时它贴在边上并变淡，
  // 而不是干脆消失——否则缩放到别处之后就再也找不到它，没法把播放头拖回来。
  const playheadInRange =
    playheadSeconds !== null && playheadSeconds >= view.start && playheadSeconds <= view.end;
  const handleSeconds = scrubSeconds ?? playheadSeconds ?? view.start;
  const handleClamped = Math.max(view.start, Math.min(view.end, handleSeconds));
  const handlePercent = ((handleClamped - view.start) / rangeDuration) * 100;
  const handlePinned = scrubSeconds === null && playheadSeconds !== null && !playheadInRange;

  return (
    <section className="zoom-timeline" ref={sectionRef}>
      <canvas ref={canvasRef} className="zoom-waveform" />
      <div className="zoom-segments">
        {visibleSegments.map(({ segment, visibleStart, visibleEnd }) => {
          const left = ((visibleStart - view.start) / rangeDuration) * 100;
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
      {playheadInRange && (
        <div
          className="timeline-playhead zoom-playhead"
          style={{ left: `${((playheadSeconds - view.start) / rangeDuration) * 100}%` }}
        />
      )}
      <button
        type="button"
        className={handlePinned ? "zoom-scrub-handle pinned" : "zoom-scrub-handle"}
        style={{ left: `${handlePercent}%` }}
        onPointerDown={handleScrubDown}
        onPointerMove={handleScrubMove}
        onPointerUp={handleScrubUp}
        onPointerCancel={handleScrubUp}
        title={
          handlePinned
            ? `播放头在视野外（${(playheadSeconds ?? 0).toFixed(2)}s），拖动可拉到当前视野`
            : `拖动设置播放起点：${handleClamped.toFixed(2)}s`
        }
        aria-label="拖动设置播放起点"
      />
    </section>
  );
}
