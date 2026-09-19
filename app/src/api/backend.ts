import { invoke } from "@tauri-apps/api/core";
import type { ProjectState, WaveformPoint } from "../types";

/**
 * 后端命令统一返回 JSON 文本，在这里解析成 ProjectState。
 *
 * 时间轴的字段以后端 pydantic 模型为准，Rust 侧只做转发，不再定义一遍结构体，
 * 所以 invoke 的泛型是 string 而不是 ProjectState（泛型只是断言，不会真的解析）。
 */
function parseProjectState(raw: string): ProjectState {
  const state = JSON.parse(raw) as ProjectState;
  if (!Array.isArray(state.segments)) {
    throw new Error("后端返回的时间轴缺少 segments 字段");
  }
  return state;
}

/** 项目数据根目录，由后端按仓库位置推导（设计文档 §14 的 data/projects/）。 */
export async function projectsRootPath(): Promise<string> {
  return invoke<string>("projects_root_path");
}

export async function analyzeSource(
  sourcePath: string,
  projectDir: string,
): Promise<ProjectState> {
  const raw = await invoke<string>("analyze_source", { sourcePath, projectDir });
  return parseProjectState(raw);
}

export async function loadWaveform(projectDir: string): Promise<WaveformPoint[]> {
  const raw = await invoke<string>("load_waveform", { projectDir });
  const points = JSON.parse(raw) as WaveformPoint[];
  if (!Array.isArray(points)) {
    throw new Error("waveform.json 格式不正确，应为采样点数组");
  }
  return points;
}

export async function loadProject(projectPath: string): Promise<ProjectState> {
  const raw = await invoke<string>("load_project", { projectPath });
  return parseProjectState(raw);
}

export async function saveProject(
  projectPath: string,
  state: ProjectState,
): Promise<void> {
  await invoke<void>("save_project", {
    projectPath,
    stateJson: JSON.stringify(state),
  });
}

export async function exportProject(
  projectPath: string,
  outputPath: string,
): Promise<string> {
  return invoke<string>("export_project", { projectPath, outputPath });
}
