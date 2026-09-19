import { open, save } from "@tauri-apps/plugin-dialog";
import { useState } from "react";
import {
  analyzeSource,
  exportProject,
  loadProject,
  loadWaveform,
  projectsRootPath,
  saveProject,
} from "./api/backend";
import { AudioPlayer } from "./components/AudioPlayer";
import { SegmentInspector } from "./components/SegmentInspector";
import { SummaryPanel } from "./components/SummaryPanel";
import { Timeline } from "./components/Timeline";
import { Toolbar } from "./components/Toolbar";
import { useProjectStore } from "./state/projectStore";
import type { ProjectState } from "./types";

const MEDIA_EXTENSIONS = ["mp3", "m4a", "aac", "wav", "flac", "ogg", "opus", "mp4", "mkv", "flv", "ts", "mov"];

// 显式标注类型而不是 as const：as const 会把数组变成 readonly，
// 无法赋给要求可变 TimelineSegment[] 的 ProjectState。
const demoProject: ProjectState = {
  version: 1,
  project_id: "demo",
  source: { path: "demo.mp4", duration: 60 },
  segments: [
    { id: "seg_1", start: 0, end: 10, label: "inactive", action: "cut", confidence: 0.9, source: "demo", edited: false },
    { id: "seg_2", start: 10, end: 45, label: "asmr", action: "keep", confidence: 1, source: "demo", edited: false },
    { id: "seg_3", start: 45, end: 60, label: "talk", action: "cut", confidence: 0.9, source: "demo", edited: false },
  ],
};

/** 源文件名去掉扩展名后作为项目目录名，project_id 取的就是目录名。 */
function projectNameFromSource(sourcePath: string): string {
  const base = sourcePath.split(/[\\/]/).pop() ?? "";
  const stem = base.replace(/\.[^.]+$/, "");
  // 去掉文件名不允许的字符，避免拼出非法目录名
  const safe = stem.replace(/[<>:"/\\|?*\u0000-\u001f]/g, "_").trim();
  return safe || `project_${Date.now()}`;
}

/**
 * 选定项目目录。同名源文件放在不同目录时项目名会撞车，直接复用会覆盖掉
 * 上一次的编辑结果，所以发现已存在的项目来自另一个源文件就往后加序号。
 */
async function resolveProjectDir(projectsRoot: string, sourcePath: string): Promise<string> {
  const name = projectNameFromSource(sourcePath);
  for (let attempt = 1; attempt <= 50; attempt += 1) {
    const suffix = attempt === 1 ? "" : `_${attempt}`;
    const dir = `${projectsRoot}\\${name}${suffix}`;
    try {
      const existing = await loadProject(`${dir}\\project.json`);
      if (existing.source.path === sourcePath) return dir;
    } catch {
      // 还没有 project.json，说明这个目录名可用
      return dir;
    }
  }
  return `${projectsRoot}\\${name}_${Date.now()}`;
}

function errorText(error: unknown): string {
  if (typeof error === "string") return error;
  if (error instanceof Error) return error.message;
  return String(error);
}

export function App() {
  const [selectedSegmentId, setSelectedSegmentId] = useState<string | null>(null);
  const [seekSeconds, setSeekSeconds] = useState<number | null>(null);
  const [playheadSeconds, setPlayheadSeconds] = useState<number | null>(null);
  const [status, setStatus] = useState("就绪");
  const [busy, setBusy] = useState(false);

  const project = useProjectStore((state) => state.project);
  const projectPath = useProjectStore((state) => state.projectPath);
  const sourcePath = useProjectStore((state) => state.sourcePath);
  const waveform = useProjectStore((state) => state.waveform);
  const setProject = useProjectStore((state) => state.setProject);
  const setSourcePath = useProjectStore((state) => state.setSourcePath);
  const setWaveform = useProjectStore((state) => state.setWaveform);
  const updateSegment = useProjectStore((state) => state.updateSegment);

  const selectedSegment =
    project?.segments.find((segment) => segment.id === selectedSegmentId) ?? null;

  // 示例项目没有真实文件，只有真正载入的项目才有可播放的源。
  const playablePath = projectPath ? project?.source.path ?? null : null;

  function resetSelection() {
    setSelectedSegmentId(null);
    setSeekSeconds(null);
    setPlayheadSeconds(null);
  }

  function loadDemo() {
    setProject(demoProject);
    // 示例项目没有真实音频，清掉上一条波形，避免和示例时间轴对不上
    setWaveform(null);
    setSourcePath(null);
    resetSelection();
    setStatus("已载入示例项目（无真实音频）");
  }

  async function run<T>(label: string, action: () => Promise<T>): Promise<T | null> {
    setBusy(true);
    setStatus(`${label}…`);
    try {
      const result = await action();
      return result;
    } catch (error) {
      setStatus(`${label}失败：${errorText(error)}`);
      return null;
    } finally {
      setBusy(false);
    }
  }

  async function handleImport() {
    // 对话框是交互式的，取消时返回 null，不能当成错误
    const picked = await open({
      multiple: false,
      directory: false,
      filters: [{ name: "音视频", extensions: MEDIA_EXTENSIONS }],
    });
    if (typeof picked !== "string") return;
    setSourcePath(picked);
    setStatus(`已选择源文件：${picked}`);
  }

  async function handleAnalyze() {
    if (!sourcePath) return;
    const result = await run("分析", async () => {
      const projectsRoot = await projectsRootPath();
      const projectDir = await resolveProjectDir(projectsRoot, sourcePath);
      const state = await analyzeSource(sourcePath, projectDir);
      // 编辑器改的是 segments.json，导出 CLI 读的也是它；project.json 留作分析记录
      setProject(state, `${projectDir}\\segments.json`);
      setWaveform(await loadWaveform(projectDir));
      return projectDir;
    });
    if (result) {
      resetSelection();
      setStatus(`分析完成，共 ${useProjectStore.getState().project?.segments.length ?? 0} 段`);
    }
  }

  async function handleSave() {
    if (!projectPath || !project) return;
    const ok = await run("保存", async () => {
      await saveProject(projectPath, project);
      return true;
    });
    if (ok) setStatus(`已保存到 ${projectPath}`);
  }

  async function handleExport() {
    if (!projectPath || !project) return;
    const outputPath = await save({
      defaultPath: "clean.mp4",
      filters: [{ name: "媒体文件", extensions: ["mp4", "m4a"] }],
    });
    if (typeof outputPath !== "string") return;
    const done = await run("导出", async () => {
      // 先把界面上的改动落盘，否则导出的是分析时的旧时间轴
      await saveProject(projectPath, project);
      return exportProject(projectPath, outputPath);
    });
    if (done) setStatus(`已导出到 ${done}`);
  }

  function selectSegment(segmentId: string) {
    const segment = project?.segments.find((item) => item.id === segmentId);
    setSelectedSegmentId(segmentId);
    setSeekSeconds(segment?.start ?? null);
    setPlayheadSeconds(segment?.start ?? null);
  }

  return (
    <main className="app">
      <Toolbar
        onImport={handleImport}
        onAnalyze={handleAnalyze}
        onSave={handleSave}
        onExport={handleExport}
        onLoadDemo={loadDemo}
        busy={busy}
        canAnalyze={sourcePath !== null}
        canSave={project !== null && projectPath !== null}
        canExport={project !== null && projectPath !== null}
      />
      <div className="workspace">
        <div className="workspace-main">
          <Timeline
            project={project}
            waveform={waveform}
            selectedSegmentId={selectedSegmentId}
            onSelectSegment={selectSegment}
            playheadSeconds={playheadSeconds}
          />
          <AudioPlayer
            sourcePath={playablePath}
            seekSeconds={seekSeconds}
            onTimeUpdate={setPlayheadSeconds}
          />
        </div>
        <div className="workspace-side">
          <SummaryPanel project={project} />
          <SegmentInspector segment={selectedSegment} onChange={updateSegment} />
        </div>
      </div>
      <footer className="statusbar">{status}</footer>
    </main>
  );
}
