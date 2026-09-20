import type { TimelineSegment } from "../types";

/**
 * 复核队列：所有 label 为 uncertain 的片段，按时间排序。
 *
 * 队列是**动态的**，不能缓存：用户在编辑栏把一段改成 asmr 或 talk，它当场就
 * 离开队列；重跑一次分析（换一档复核深度）整个队列又换一批。所以每次都要从
 * 当前 segments 现算。
 */
export function reviewQueue(segments: TimelineSegment[]): TimelineSegment[] {
  return segments
    .filter((segment) => segment.label === "uncertain")
    .sort((left, right) => left.start - right.start);
}

/**
 * 沿 direction 找下一段待听：1 往后，-1 往前。找不到返回 null。
 *
 * **按时间位置找，不按队列下标找。** 用户可能正停在某个 asmr 段上听（他从概览
 * 随便点了一段），这时「下一段待听」应该是它之后的第一段，而不是从队首数起。
 * 一条规则同时管住「选中项在队列里」和「不在队列里」两种情况，不用分支。
 *
 * 到头返回 null 而**不绕回**：绕回会让「队列走完了」这件事从界面上消失，用户
 * 会以为还有东西没看，在里面一圈一圈转。
 */
export function reviewNeighbor(
  queue: TimelineSegment[],
  selected: TimelineSegment | null,
  direction: 1 | -1,
): TimelineSegment | null {
  if (queue.length === 0) return null;

  // 没选中时「往后」从队首开始；「往前」没有起点可言，交给调用方禁用按钮
  if (!selected) return direction === 1 ? queue[0] : null;

  if (direction === 1) {
    return queue.find((item) => item.start > selected.start) ?? null;
  }

  let found: TimelineSegment | null = null;
  for (const item of queue) {
    if (item.start >= selected.start) break;
    found = item;
  }
  return found;
}

export interface ReviewStatus {
  /** 待听片段总数。 */
  total: number;
  /** 当前选中项在队列中的序号，从 1 起；选中项不在队列里时为 null。 */
  position: number | null;
  /** 上一段 / 下一段待听的 id，没有就是 null，按钮据此禁用。 */
  prevId: string | null;
  nextId: string | null;
}

/**
 * 界面要的全部信息一次算出来。组件拿它直接渲染，不用自己拼队列——
 * 拼三遍就会有一遍忘了排序。
 */
export function reviewStatus(
  segments: TimelineSegment[],
  selected: TimelineSegment | null,
): ReviewStatus {
  const queue = reviewQueue(segments);
  const index = selected ? queue.findIndex((item) => item.id === selected.id) : -1;
  return {
    total: queue.length,
    position: index >= 0 ? index + 1 : null,
    prevId: reviewNeighbor(queue, selected, -1)?.id ?? null,
    nextId: reviewNeighbor(queue, selected, 1)?.id ?? null,
  };
}
