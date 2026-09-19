import { create } from "zustand";
import type { ProjectState, TimelineSegment } from "../types";

interface ProjectStore {
  project: ProjectState | null;
  projectPath: string | null;
  setProject: (project: ProjectState, path?: string) => void;
  updateSegment: (segment: TimelineSegment) => void;
}

export const useProjectStore = create<ProjectStore>((set) => ({
  project: null,
  projectPath: null,
  setProject: (project, path) => set({ project, projectPath: path ?? null }),
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
