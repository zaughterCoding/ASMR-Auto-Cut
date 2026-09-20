import { useMemo } from "react";
import { reviewStatus } from "../timeline/reviewQueue";
import type { TimelineSegment } from "../types";

interface Props {
  segments: TimelineSegment[];
  selectedSegment: TimelineSegment | null;
  onSelectSegment: (segmentId: string) => void;
}

const HINT = "分析时标为「拿不准」的片段，需要你听一遍决定去留";

/**
 * 复核队列的跳转导航：一段一段走完待听片段。
 *
 * 只负责**选中**目标段，不碰视口和播放头——选中之后 TimelineWorkspace 会把缩放
 * 视图取景到它、App 会把播放头挪到它的起点。跳转要真的把目标带进视野，这件事
 * 已经有主了，这里再实现一遍就会有两套取景逻辑互相打架。
 *
 * 走到底不绕回：按钮变灰就是「听完了」的信号，比转圈可靠。
 */
export function ReviewNav({ segments, selectedSegment, onSelectSegment }: Props) {
  const status = useMemo(
    () => reviewStatus(segments, selectedSegment),
    [segments, selectedSegment],
  );

  const readout =
    status.total === 0
      ? "没有待听片段"
      : status.position === null
        ? `待听 ${status.total} 段`
        : `待听 ${status.position} / ${status.total}`;

  return (
    <div className="review-nav">
      <span title={HINT}>{readout}</span>
      <button
        type="button"
        disabled={status.prevId === null}
        onClick={() => status.prevId && onSelectSegment(status.prevId)}
      >
        上一段
      </button>
      <button
        type="button"
        disabled={status.nextId === null}
        onClick={() => status.nextId && onSelectSegment(status.nextId)}
      >
        下一段
      </button>
    </div>
  );
}
