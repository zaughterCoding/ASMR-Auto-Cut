import type { SegmentAction, SegmentLabel } from "../types";

/**
 * 各标签在时间轴上的配色。概览和缩放共用一份，改色只需改这里。
 *
 * 颜色本身就是信息：复核时是靠颜色一眼扫出哪段是 ASMR、哪段是闲聊，所以任何
 * 显示段落的地方都必须上色，不能只画成同一个灰块。
 */
export const segmentColors: Record<SegmentLabel, string> = {
  asmr: "#2f9e44",
  talk: "#e03131",
  inactive: "#868e96",
  uncertain: "#f08c00",
};

/** 切除的段落压暗一些：保留的段落是要留下的，视觉权重该更高。 */
export function segmentOpacity(action: SegmentAction): number {
  return action === "cut" ? 0.32 : 0.72;
}
