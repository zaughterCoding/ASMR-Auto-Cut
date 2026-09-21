import { open, save } from "@tauri-apps/plugin-dialog";
import { useEffect, useRef, useState } from "react";
import {
  analyzeSource,
  exportProject,
  listenToBackendProgress,
  loadProject,
  loadWaveform,
  projectsRootPath,
  projectsRootStatus,
  saveProject,
  setProjectsRoot,
} from "./api/backend";
import { AudioPlayer } from "./components/AudioPlayer";
import { ProgressBar } from "./components/ProgressBar";
import { SegmentInspector } from "./components/SegmentInspector";
import { SummaryPanel } from "./components/SummaryPanel";
import { TimelineWorkspace } from "./components/TimelineWorkspace";
import { Toolbar } from "./components/Toolbar";
import { useProjectStore } from "./state/projectStore";
import type { OperationProgress, ProjectState, ReviewLevel } from "./types";

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
  const [progress, setProgress] = useState<OperationProgress | null>(null);
  // 复核细致程度，只喂给下一次分析。它是「这次我愿意花多少时间复核」的声明，
  // 存在这里而不是项目里——同一个项目换个心情重跑一遍，本来就该能换一档。
  const [review, setReview] = useState<ReviewLevel>("standard");
  // 后端还没定下数据目录。分析要往那儿落盘，所以这期间「分析」是禁用的。
  const [needsDataDir, setNeedsDataDir] = useState(false);
  // 首次运行只引导一次。热重载会让 effect 再跑一遍，不挡的话会弹出第二个对话框。
  const promptedForDataDir = useRef(false);

  const project = useProjectStore((state) => state.project);
  const projectPath = useProjectStore((state) => state.projectPath);
  const sourcePath = useProjectStore((state) => state.sourcePath);
  const waveform = useProjectStore((state) => state.waveform);
  const setProject = useProjectStore((state) => state.setProject);
  const setSourcePath = useProjectStore((state) => state.setSourcePath);
  const setWaveform = useProjectStore((state) => state.setWaveform);
  const updateSegment = useProjectStore((state) => state.updateSegment);

  // 订阅后端进度。listen 返回的是 Promise，而组件可能在它 resolve 之前就卸载，
  // 那种情况下没有 unlisten 可调，只能等 resolve 出来再补调一次，否则监听器
  // 会一直挂在 window 上：热重载几轮之后同一条进度会被处理好几遍。
  useEffect(() => {
    let disposed = false;
    let unlisten: (() => void) | null = null;
    listenToBackendProgress((event) => {
      if (!disposed) setProgress(event);
    }).then((cleanup) => {
      if (disposed) cleanup();
      else unlisten = cleanup;
    });
    return () => {
      disposed = true;
      if (unlisten) unlisten();
    };
  }, []);

  // 首次运行引导：后端还没定下数据目录（安装版第一次启动就是这样）就问用户要一个。
  // 只在挂载时查一次；ref 挡的是热重载——effect 会再跑一遍，不挡就会弹出第二个对话框。
  useEffect(() => {
    if (promptedForDataDir.current) return;
    promptedForDataDir.current = true;
    // 用两参数的 then 而不是 .catch：后者会把 chooseDataDir 抛出的异常也一并算作
    // 「读取数据目录失败」，而那是完全另一回事，文案会把人指错方向。
    projectsRootStatus().then(
      (root) => {
        if (root !== null) return;
        setNeedsDataDir(true);
        void chooseDataDir();
      },
      (error) => setStatus(`读取数据目录失败：${errorText(error)}`),
    );
  }, []);

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
    // 清掉上一次操作的百分比：新操作开始时后端还没发第一批事件，不清的话进度条
    // 会先显示上一次的旧值再跳回去。
    setProgress(null);
    setStatus(`${label}…`);
    try {
      const result = await action();
      return result;
    } catch (error) {
      setStatus(`${label}失败：${errorText(error)}`);
      return null;
    } finally {
      setBusy(false);
      // 结束后把进度条交还给 status 文字：成功时留着 100% 会让人以为还在跑，
      // 失败时留着中途的百分比更是误导。
      setProgress(null);
    }
  }

  /**
   * 让用户挑一个数据目录并落盘。
   *
   * 取消（`open` 返回 null）时**什么都不做**：不重开对话框、也不清掉
   * needsDataDir。工具栏上那个「选择数据目录」按钮就是重新打开的入口，
   * 这样取消只是一个可恢复的状态，而不是把用户逼到只能强杀进程。
   */
  async function chooseDataDir() {
    // 对话框本身也会失败（权限、系统策略），而它不在 run() 的包裹里；
    // 不接住的话这里会变成一条没人处理的 rejection，界面上什么都不显示。
    let picked: string | null;
    try {
      picked = await open({ directory: true, multiple: false });
    } catch (error) {
      setStatus(`打开文件夹选择器失败：${errorText(error)}`);
      return;
    }
    if (typeof picked !== "string") return;
    const saved = await run("设置数据目录", () => setProjectsRoot(picked));
    if (saved !== null) {
      setNeedsDataDir(false);
      setStatus(`数据目录：${saved}`);
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
    // 工具栏已经把按钮禁掉了，这里再挡一次：数据目录没定下来时 projects_root_path()
    // 会退回到 cwd 下的相对路径，把几小时的项目数据悄悄写到安装目录旁边。
    if (needsDataDir) return;
    const result = await run("分析", async () => {
      const projectsRoot = await projectsRootPath();
      const projectDir = await resolveProjectDir(projectsRoot, sourcePath);
      const state = await analyzeSource(sourcePath, projectDir, review);
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

  /**
   * 拖动缩放时间轴上的倒三角：把播放起点挪到那个位置。
   *
   * 两个 setState 都要调。seekSeconds 是给播放器的（AudioPlayer 在它变化时写
   * audio.currentTime），playheadSeconds 是给时间轴画播放头的。只设前者的话，
   * 松手那一刻播放头会先退回旧位置，等播放器下一次回报时间才跳过去。
   */
  function seekTo(seconds: number) {
    setSeekSeconds(seconds);
    setPlayheadSeconds(seconds);
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
        needsDataDir={needsDataDir}
        onChooseDataDir={chooseDataDir}
        review={review}
        onReviewChange={setReview}
      />
      <div className="workspace">
        <div className="workspace-main">
          <TimelineWorkspace
            project={project}
            waveform={waveform}
            selectedSegmentId={selectedSegmentId}
            selectedSegment={selectedSegment}
            onSelectSegment={selectSegment}
            onUpdateSegment={updateSegment}
            onSeek={seekTo}
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
      <ProgressBar status={status} progress={progress} busy={busy} />
    </main>
  );
}
