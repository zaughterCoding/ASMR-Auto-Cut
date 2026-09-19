from pydantic import BaseModel, Field


class AnalysisConfig(BaseModel):
    speech_padding_before: float = Field(default=0.4, ge=0)
    speech_padding_after: float = Field(default=0.4, ge=0)
    inactive_padding: float = Field(default=0.1, ge=0)
    min_keep_duration: float = Field(default=1.0, ge=0)
    merge_gap: float = Field(default=0.2, ge=0)
    inactive_frame_seconds: float = Field(default=1.0, gt=0)
    inactive_rms_threshold: float = Field(default=0.004, ge=0)
    inactive_min_duration: float = Field(default=20.0, ge=0)
