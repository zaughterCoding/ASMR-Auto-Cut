from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

SegmentLabel = Literal["asmr", "talk", "inactive", "uncertain"]
SegmentAction = Literal["keep", "cut"]


class MediaSource(BaseModel):
    path: str
    duration: float = Field(ge=0)

    @property
    def resolved_path(self) -> Path:
        return Path(self.path).expanduser()


class TimelineSegment(BaseModel):
    id: str
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    label: SegmentLabel
    action: SegmentAction
    confidence: float = Field(ge=0, le=1)
    source: str
    edited: bool = False

    @model_validator(mode="after")
    def end_must_be_after_start(self) -> "TimelineSegment":
        if self.end <= self.start:
            raise ValueError("segment end must be greater than start")
        return self


class ProjectState(BaseModel):
    version: int = 1
    project_id: str
    source: MediaSource
    segments: list[TimelineSegment]

    @field_validator("segments")
    @classmethod
    def segments_must_be_sorted(cls, value: list[TimelineSegment]) -> list[TimelineSegment]:
        starts = [segment.start for segment in value]
        if starts != sorted(starts):
            raise ValueError("segments must be sorted by start time")
        return value
