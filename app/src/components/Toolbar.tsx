interface Props {
  onAnalyzeDemo: () => void;
}

export function Toolbar({ onAnalyzeDemo }: Props) {
  return (
    <header className="toolbar">
      <button type="button" onClick={onAnalyzeDemo}>
        载入示例项目
      </button>
      <button type="button" disabled>
        导入
      </button>
      <button type="button" disabled>
        分析
      </button>
      <button type="button" disabled>
        导出
      </button>
    </header>
  );
}
