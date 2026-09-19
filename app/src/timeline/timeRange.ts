/**
 * 时间轴上的一个时间区间，单位秒。纯前端状态：它描述的是「在看哪一段」，
 * 属于编辑视口而不是项目数据，所以不写进 segments.json。
 *
 * 始终满足 `0 <= start < end <= duration`，构造出来的值都由这里几个函数保证，
 * 组件里不要自己拼。
 */
export interface TimeRange {
  start: number;
  end: number;
}

/**
 * 把任意一对秒数收拾成一个合法的区间。
 *
 * 要处理三种情况，顺序不能换：
 * 1. 两个端点谁大谁小不确定（拖动时可能反过来），先排序再夹到 [0, duration]。
 * 2. 区间短于 minDuration 就以 start 为基准往右撑开。不用「以中点为轴两边各撑
 *    一半」：短区间基本都来自一次很轻的拖动，start 是用户按下去的位置，保留它
 *    更容易理解——拖出来的窗口至少覆盖从按下那一刻起的 minDuration 秒。
 * 3. 撑开可能顶出录音末尾，这时整体往回推，让长度正好是 minDuration。
 */
export function normalizeRange(
  rawStart: number,
  rawEnd: number,
  duration: number,
  minDuration = 1,
): TimeRange {
  let start = Math.max(0, Math.min(duration, Math.min(rawStart, rawEnd)));
  let end = Math.max(0, Math.min(duration, Math.max(rawStart, rawEnd)));
  if (end - start < minDuration) {
    end = start + minDuration;
    if (end > duration) {
      // 录音比 minDuration 还短时 start 会被夹到 0，此时长度不足 minDuration
      // 是没办法的事——整条录音就这么长。
      start = Math.max(0, duration - minDuration);
      end = duration;
    }
  }
  return { start, end };
}

/**
 * 平移区间，长度不变。碰到录音首尾就停住而不是压缩——拖动选区的语义是
 * 「搬走这一块」，不是「把这块拉长」。
 */
export function moveRange(range: TimeRange, delta: number, duration: number): TimeRange {
  const length = range.end - range.start;
  let start = range.start + delta;
  if (start < 0) start = 0;
  if (start + length > duration) start = Math.max(0, duration - length);
  return { start, end: Math.min(duration, start + length) };
}

/**
 * 以 anchor（秒）为轴缩放区间，anchor 就是鼠标位置。
 *
 * factor < 1 放大（区间变短），factor > 1 缩小。anchor 处的时刻在缩放前后保持
 * 在相同相对位置上，所以光标底下的内容是钉住的，不会往两边跑。
 * 结果一律过一遍 normalizeRange，长度越界和贴边的情况都交给它收。
 */
export function zoomRangeAt(
  range: TimeRange,
  anchor: number,
  factor: number,
  duration: number,
  minDuration = 1,
): TimeRange {
  const currentLength = range.end - range.start;
  const nextLength = Math.max(minDuration, Math.min(duration, currentLength * factor));
  const anchorRatio = currentLength > 0 ? (anchor - range.start) / currentLength : 0.5;
  const start = anchor - nextLength * anchorRatio;
  const end = start + nextLength;
  return normalizeRange(start, end, duration, minDuration);
}
