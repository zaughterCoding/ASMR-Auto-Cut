export type SegmentLabel = "asmr" | "talk" | "inactive" | "uncertain";
export type SegmentAction = "keep" | "cut";

export interface MediaSource {
  path: string;
  duration: number;
}

export interface TimelineSegment {
  id: string;
  start: number;
  end: number;
  label: SegmentLabel;
  action: SegmentAction;
  confidence: number;
  source: string;
  edited: boolean;
}

export interface ProjectState {
  version: number;
  project_id: string;
  source: MediaSource;
  segments: TimelineSegment[];
}

/** 后端 waveform.json 的一个采样点，默认每秒 20 个。 */
export interface WaveformPoint {
  time: number;
  peak: number;
  rms: number;
}

export type OperationName = "analyze" | "export";

export interface OperationProgress {
  type: "progress";
  operation: OperationName;
  phase: string;
  message: string;
  current: number;
  total: number;
  percent: number;
}

export interface BackendResultEvent {
  type: "result";
  operation: OperationName;
  project_path: string | null;
  output_path: string | null;
}
