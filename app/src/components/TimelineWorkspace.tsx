import { useEffect, useState } from "react";
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
  playheadSeconds,
}: Props) {
  const [range, setRange] = useState<TimeRange | null>(null);

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

  return (
    <section className="timeline-workspace">
      <OverviewTimeline
        project={project}
        waveform={waveform}
        selectedSegmentId={selectedSegmentId}
        selectedRange={range}
        onSelectSegment={onSelectSegment}
        onChangeRange={setRange}
        playheadSeconds={playheadSeconds}
      />
      <ZoomTimeline
        project={project}
        waveform={waveform}
        range={range}
        selectedSegmentId={selectedSegmentId}
        onSelectSegment={onSelectSegment}
        onChangeRange={setRange}
        playheadSeconds={playheadSeconds}
      />
      <ZoomEditBar segment={selectedSegment} onChange={onUpdateSegment} />
    </section>
  );
}
