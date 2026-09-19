import { SummaryPanel } from "./components/SummaryPanel";
import { Toolbar } from "./components/Toolbar";
import { useProjectStore } from "./state/projectStore";
import type { ProjectState } from "./types";

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

export function App() {
  const project = useProjectStore((state) => state.project);
  const setProject = useProjectStore((state) => state.setProject);

  return (
    <main className="app">
      <Toolbar onAnalyzeDemo={() => setProject(demoProject)} />
      <SummaryPanel project={project} />
    </main>
  );
}
