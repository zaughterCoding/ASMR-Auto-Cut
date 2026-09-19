import { create } from "zustand";
import type { ProjectState, TimelineSegment, WaveformPoint } from "../types";

interface ProjectStore {
  project: ProjectState | null;
  projectPath: string | null;
  /** 最近一次导入选中的源文件，分析前先选它。 */
  sourcePath: string | null;
  waveform: WaveformPoint[] | null;
  setProject: (project: ProjectState, path?: string) => void;
  setSourcePath: (path: string | null) => void;
  setWaveform: (waveform: WaveformPoint[] | null) => void;
  updateSegment: (segment: TimelineSegment) => void;
}

export const useProjectStore = create<ProjectStore>((set) => ({
  project: null,
  projectPath: null,
  sourcePath: null,
  waveform: null,
  setProject: (project, path) => set({ project, projectPath: path ?? null }),
  setSourcePath: (path) => set({ sourcePath: path }),
  setWaveform: (waveform) => set({ waveform }),
  // 用户在界面上改过的段落标记为 edited，导出时以此为准，重跑分析也不会覆盖。
  updateSegment: (segment) =>
    set((state) => {
      if (!state.project) return state;
      return {
        project: {
          ...state.project,
          segments: state.project.segments.map((item) =>
            item.id === segment.id ? { ...segment, edited: true } : item,
          ),
        },
      };
    }),
}));
