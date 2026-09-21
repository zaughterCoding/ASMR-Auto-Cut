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
  /** 还没定下数据目录：分析无处落盘，必须先让用户选一个。 */
  needsDataDir: boolean;
  onChooseDataDir: () => void;
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
  needsDataDir,
  onChooseDataDir,
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
      {/* 还没有数据目录时把入口摆在最显眼处，并挡住「分析」——否则用户点了分析
          才被告知无处落盘，而那时唯一的出路是强杀进程。取消过一次之后这个按钮
          就是重新打开选择器的入口。 */}
      {needsDataDir ? (
        <button type="button" onClick={onChooseDataDir} disabled={busy} className="toolbar-primary">
          选择数据目录
        </button>
      ) : null}
      <button type="button" onClick={onAnalyze} disabled={busy || !canAnalyze || needsDataDir}>
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
