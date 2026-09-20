import type { ReviewLevel } from "../types";

interface Props {
  onImport: () => void;
  onAnalyze: () => void;
  onSave: () => void;
  onExport: () => void;
  /** 开发辅助：不弹文件对话框直接载入示例项目，用来检查界面渲染。 */
  onLoadDemo: () => void;
  busy: boolean;
  canAnalyze: boolean;
  canSave: boolean;
  canExport: boolean;
  review: ReviewLevel;
  onReviewChange: (level: ReviewLevel) => void;
}

/**
 * 复核细致程度的三档。value 要和后端 `config.REVIEW_BANDS` 的键一致——后端会校验，
 * 写错了会在分析时报参数错，而不是悄悄按默认值跑。
 *
 * 说明写在标签上而不是 title 里：这几句话正是用户做选择时需要的，藏进 tooltip
 * 等于没写。
 */
const REVIEW_OPTIONS: { value: ReviewLevel; text: string; hint: string }[] = [
  { value: "quick", text: "快速", hint: "高亮最少，复核最快" },
  { value: "standard", text: "标准", hint: "默认" },
  { value: "thorough", text: "细致", hint: "高亮最多，最不容易漏掉轻语" },
];

export function Toolbar({
  onImport,
  onAnalyze,
  onSave,
  onExport,
  onLoadDemo,
  busy,
  canAnalyze,
  canSave,
  canExport,
  review,
  onReviewChange,
}: Props) {
  const current = REVIEW_OPTIONS.find((option) => option.value === review);

  return (
    <header className="toolbar">
      <button type="button" onClick={onImport} disabled={busy}>
        导入
      </button>
      {/* 放在「分析」左边而不是右边：它只影响下一次分析，紧挨着才看得出这层关系。 */}
      <label className="toolbar-review">
        复核
        <select
          value={review}
          disabled={busy}
          onChange={(event) => onReviewChange(event.target.value as ReviewLevel)}
        >
          {REVIEW_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.text}
            </option>
          ))}
        </select>
        <span className="toolbar-hint">{current?.hint}</span>
      </label>
      <button type="button" onClick={onAnalyze} disabled={busy || !canAnalyze}>
        分析
      </button>
      <button type="button" onClick={onSave} disabled={busy || !canSave}>
        保存
      </button>
      <button type="button" onClick={onExport} disabled={busy || !canExport}>
        导出
      </button>
      <span className="toolbar-spacer" />
      <button type="button" onClick={onLoadDemo} disabled={busy} className="toolbar-ghost">
        载入示例
      </button>
    </header>
  );
}
