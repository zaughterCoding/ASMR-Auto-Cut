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
