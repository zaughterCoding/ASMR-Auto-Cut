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
}

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
}: Props) {
  return (
    <header className="toolbar">
      <button type="button" onClick={onImport} disabled={busy}>
        导入
      </button>
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
