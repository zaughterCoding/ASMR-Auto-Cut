import type { SegmentAction, SegmentLabel, TimelineSegment } from "../types";

interface Props {
  segment: TimelineSegment | null;
  onChange: (segment: TimelineSegment) => void;
}

const labels: SegmentLabel[] = ["asmr", "talk", "inactive", "uncertain"];
const actions: SegmentAction[] = ["keep", "cut"];

export function SegmentInspector({ segment, onChange }: Props) {
  if (!segment) return <aside className="panel inspector empty">请选择一个片段</aside>;

  return (
    <aside className="panel inspector">
      <h2>片段</h2>
      <div className="inspector-range">
        {segment.start.toFixed(2)}s – {segment.end.toFixed(2)}s
        <span className="inspector-duration">
          （{(segment.end - segment.start).toFixed(2)}s）
        </span>
      </div>
      <label>
        标签
        <select
          value={segment.label}
          onChange={(event) =>
            onChange({ ...segment, label: event.target.value as SegmentLabel })
          }
        >
          {labels.map((label) => (
            <option key={label} value={label}>
              {label}
            </option>
          ))}
        </select>
      </label>
      <label>
        处理
        <select
          value={segment.action}
          onChange={(event) =>
            onChange({ ...segment, action: event.target.value as SegmentAction })
          }
        >
          {actions.map((action) => (
            <option key={action} value={action}>
              {action}
            </option>
          ))}
        </select>
      </label>
      <dl className="inspector-meta">
        <dt>置信度</dt>
        <dd>{segment.confidence.toFixed(2)}</dd>
        <dt>来源</dt>
        <dd>{segment.source}</dd>
        <dt>已手改</dt>
        <dd>{segment.edited ? "是" : "否"}</dd>
      </dl>
    </aside>
  );
}
