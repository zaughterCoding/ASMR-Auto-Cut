import type { TimelineSegment } from "../types";

interface Props {
  segment: TimelineSegment | null;
  onChange: (segment: TimelineSegment) => void;
}

/** 常用的四个「标签 + 处理方式」组合。判断依据是标签，处理方式是它的默认结果。 */
const PRESETS: { label: TimelineSegment["label"]; action: TimelineSegment["action"]; text: string }[] = [
  { label: "asmr", action: "keep", text: "ASMR / KEEP" },
  { label: "talk", action: "cut", text: "TALK / CUT" },
  { label: "inactive", action: "cut", text: "INACTIVE / CUT" },
  { label: "uncertain", action: "keep", text: "UNCERTAIN / KEEP" },
];

/**
 * 缩放波形下方的快捷编辑条，改的是当前选中的那一段。
 *
 * 只是省掉「去右侧面板点两下」的来回，右侧的 SegmentInspector 仍然是完整编辑器
 * （它能改的东西更多，也不依赖先选中）。所以这里只放最常用的四个组合，不做
 * 自定义标签+处理方式的任意组合。
 */
export function ZoomEditBar({ segment, onChange }: Props) {
  function apply(label: TimelineSegment["label"], action: TimelineSegment["action"]) {
    if (!segment) return;
    // edited 交给 store 里的 updateSegment 打标，这里只管改内容
    onChange({ ...segment, label, action });
  }

  return (
    <div className="zoom-editbar">
      <span>{segment ? `${segment.start.toFixed(2)}s - ${segment.end.toFixed(2)}s` : "未选择片段"}</span>
      {PRESETS.map((preset) => (
        <button
          key={preset.text}
          type="button"
          disabled={!segment}
          className={segment?.label === preset.label ? "active" : undefined}
          onClick={() => apply(preset.label, preset.action)}
        >
          {preset.text}
        </button>
      ))}
    </div>
  );
}
