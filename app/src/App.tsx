import { useState } from "react";
import { AudioPlayer } from "./components/AudioPlayer";
import { SegmentInspector } from "./components/SegmentInspector";
import { SummaryPanel } from "./components/SummaryPanel";
import { Timeline } from "./components/Timeline";
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
  const [selectedSegmentId, setSelectedSegmentId] = useState<string | null>(null);
  const [seekSeconds, setSeekSeconds] = useState<number | null>(null);
  const [playheadSeconds, setPlayheadSeconds] = useState<number | null>(null);

  const project = useProjectStore((state) => state.project);
  const projectPath = useProjectStore((state) => state.projectPath);
  const waveform = useProjectStore((state) => state.waveform);
  const setProject = useProjectStore((state) => state.setProject);
  const setWaveform = useProjectStore((state) => state.setWaveform);
  const updateSegment = useProjectStore((state) => state.updateSegment);

  const selectedSegment =
    project?.segments.find((segment) => segment.id === selectedSegmentId) ?? null;

  // 示例项目没有真实文件，只有真正载入的项目才有可播放的源。
  const sourcePath = projectPath ? project?.source.path ?? null : null;

  const loadDemo = () => {
    setProject(demoProject);
    // 示例项目没有真实音频，清掉上一条波形，避免和示例时间轴对不上
    setWaveform(null);
    setSelectedSegmentId(null);
    setSeekSeconds(null);
    setPlayheadSeconds(null);
  };

  const selectSegment = (segmentId: string) => {
    const segment = project?.segments.find((item) => item.id === segmentId);
    setSelectedSegmentId(segmentId);
    setSeekSeconds(segment?.start ?? null);
    setPlayheadSeconds(segment?.start ?? null);
  };

  return (
    <main className="app">
      <Toolbar onAnalyzeDemo={loadDemo} />
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
            sourcePath={sourcePath}
            seekSeconds={seekSeconds}
            onTimeUpdate={setPlayheadSeconds}
          />
        </div>
        <div className="workspace-side">
          <SummaryPanel project={project} />
          <SegmentInspector segment={selectedSegment} onChange={updateSegment} />
        </div>
      </div>
    </main>
  );
}
