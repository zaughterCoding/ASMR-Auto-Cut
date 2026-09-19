import { useEffect, useMemo, useState } from "react";
import type { TimeRange } from "../timeline/timeRange";
import { normalizeRange } from "../timeline/timeRange";
import type { ProjectState, TimelineSegment, WaveformPoint } from "../types";
import { OverviewTimeline } from "./OverviewTimeline";
import { ZoomEditBar } from "./ZoomEditBar";
import { ZoomTimeline } from "./ZoomTimeline";

interface Props {
  project: ProjectState | null;
  waveform: WaveformPoint[] | null;
  selectedSegmentId: string | null;
  selectedSegment: TimelineSegment | null;
  onSelectSegment: (segmentId: string) => void;
  onUpdateSegment: (segment: TimelineSegment) => void;
  /** 拖动缩放时间轴上的倒三角时报告新的播放起点。 */
  onSeek: (seconds: number) => void;
  playheadSeconds: number | null;
}

/** 没选中任何片段时，缩放视图先给出开头这么多秒。 */
const DEFAULT_RANGE_SECONDS = 60;

/** 选中片段时前后各留出片段长度的一半（至少 2 秒）作为上下文。 */
function focusRange(segment: TimelineSegment, duration: number): TimeRange {
  const padding = Math.max(2, (segment.end - segment.start) * 0.5);
  return normalizeRange(segment.start - padding, segment.end + padding, duration, 1);
}

/**
 * 上下两块时间轴加一条编辑栏：上面是整条录音的概览（框选范围），下面是框住
 * 那一段的放大视图（改标签、改保留/切除）。
 *
 * 缩放视口（range）是纯前端状态，不进 segments.json——它是「在看哪一段」而不是
 * 项目数据，重新打开项目本来也不该记住上次拖到哪。
 */
export function TimelineWorkspace({
  project,
  waveform,
  selectedSegmentId,
  selectedSegment,
  onSelectSegment,
  onUpdateSegment,
  onSeek,
  playheadSeconds,
}: Props) {
  const [range, setRange] = useState<TimeRange | null>(null);
  const [viewportState, setViewport] = useState<TimeRange | null>(null);

  // 概览的视口只在换项目时重置。
  //
  // 这件事不能并进下面那个 effect：那个 effect 的依赖里有 selectedSegment?.id，
  // 点任何一个段落都会重跑，用户刚用滚轮缩放好的视口会被一把冲回整条。
  useEffect(() => {
    setViewport(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project?.project_id, project?.source.duration]);

  // 依赖只写 id，不写 project / selectedSegment 对象本身，这是故意的：
  // updateSegment 每次都会换掉整个 project 对象，把对象放进依赖里的话，在编辑栏
  // 点一下预设按钮就会把缩放视口弹回「以选中片段为中心」——用户刚滚轮缩放到的
  // 位置就白缩了。这里要的是「换了项目 / 换了选中的段」才重新取景。
  useEffect(() => {
    if (!project) {
      setRange(null);
      return;
    }
    if (selectedSegment) {
      setRange(focusRange(selectedSegment, project.source.duration));
      return;
    }
    setRange(
      normalizeRange(
        0,
        Math.min(DEFAULT_RANGE_SECONDS, project.source.duration),
        project.source.duration,
        1,
      ),
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project?.project_id, selectedSegment?.id]);

  // 必须 memo：没缩放过时每次渲染都会新建一个字面量对象，而概览的重绘 effect 和
  // 滚轮监听的 effect 都拿它当依赖，对象身份一变就白重挂一遍监听器。
  const duration = project?.source.duration ?? 0;
  const viewport = useMemo(
    () => viewportState ?? { start: 0, end: duration },
    [viewportState, duration],
  );

  return (
    <section className="timeline-workspace">
      <OverviewTimeline
        project={project}
        waveform={waveform}
        viewport={viewport}
        selectedSegmentId={selectedSegmentId}
        selectedRange={range}
        onSelectSegment={onSelectSegment}
        onChangeRange={setRange}
        onChangeViewport={setViewport}
        playheadSeconds={playheadSeconds}
      />
      <ZoomTimeline
        project={project}
        waveform={waveform}
        range={range}
        selectedSegmentId={selectedSegmentId}
        onSelectSegment={onSelectSegment}
        onChangeRange={setRange}
        onSeek={onSeek}
        playheadSeconds={playheadSeconds}
      />
      <ZoomEditBar segment={selectedSegment} onChange={onUpdateSegment} />
    </section>
  );
}
