import { formatClock } from "../timeline/timeFormat";
import type { ProjectState, SegmentLabel } from "../types";

interface Props {
  project: ProjectState | null;
}

const LABELS: SegmentLabel[] = ["asmr", "talk", "inactive", "uncertain"];

export function SummaryPanel({ project }: Props) {
  if (!project) return <aside className="panel">尚未载入项目</aside>;

  const keepSeconds = project.segments
    .filter((segment) => segment.action === "keep")
    .reduce((sum, segment) => sum + segment.end - segment.start, 0);
  const cutSeconds = Math.max(0, project.source.duration - keepSeconds);
  const ratio = project.source.duration > 0 ? keepSeconds / project.source.duration : 0;

  return (
    <aside className="panel">
      <h2>概要</h2>
      <dl className="summary">
        <dt>总时长</dt>
        <dd>{formatClock(project.source.duration)}</dd>
        <dt>保留</dt>
        <dd>
          {formatClock(keepSeconds)}（{(ratio * 100).toFixed(1)}%）
        </dd>
        <dt>切除</dt>
        <dd>{formatClock(cutSeconds)}</dd>
        <dt>片段数</dt>
        <dd>{project.segments.length}</dd>
      </dl>
      <h3>按标签统计</h3>
      <ul className="label-counts">
        {LABELS.map((label) => (
          <li key={label}>
            <span>{label}</span>
            <span>{project.segments.filter((segment) => segment.label === label).length}</span>
          </li>
        ))}
      </ul>
    </aside>
  );
}
