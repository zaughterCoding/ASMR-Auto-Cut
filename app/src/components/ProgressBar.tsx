import type { OperationProgress } from "../types";

interface Props {
  status: string;
  progress: OperationProgress | null;
  busy: boolean;
}

/**
 * 底部状态栏：一行文字 + 一条进度条。
 *
 * 三种形态：
 * - 有进度事件：显示后端给的 message 和后端算的 percent，进度条按百分比填充。
 * - 忙碌但还没有进度事件：进度的多少无从得知，走不确定态（滑动条）。
 * - 空闲：文字显示 status，进度条归零。
 *
 * percent 为 null 只可能是「忙但不知道进度」，这时绝不能画成 0% —— 0% 看起来
 * 像卡住了，和「正在跑但不知道跑到哪」是两回事。
 */
export function ProgressBar({ status, progress, busy }: Props) {
  const percent = progress?.percent ?? (busy ? null : 0);
  return (
    <footer className="statusbar">
      <div className="statusbar-row">
        <span>{progress?.message ?? status}</span>
        {progress && <span>{progress.percent.toFixed(1)}%</span>}
      </div>
      <div className={percent === null ? "progress indeterminate" : "progress"}>
        <div
          className="progress-fill"
          style={percent === null ? undefined : { width: `${Math.max(0, Math.min(100, percent))}%` }}
        />
      </div>
    </footer>
  );
}
