import json
import sys
from typing import Literal, TextIO

from pydantic import BaseModel, Field, computed_field


class ProgressEvent(BaseModel):
    type: Literal["progress"] = "progress"
    operation: Literal["analyze", "export"]
    phase: str
    message: str
    current: int = Field(ge=0)
    total: int = Field(gt=0)

    @computed_field
    @property
    def percent(self) -> float:
        return round((self.current / self.total) * 100, 1)


class ResultEvent(BaseModel):
    type: Literal["result"] = "result"
    operation: Literal["analyze", "export"]
    project_path: str | None = None
    output_path: str | None = None


def emit_json_event(event: BaseModel, stream: TextIO = sys.stdout) -> None:
    stream.write(json.dumps(event.model_dump(), ensure_ascii=False))
    stream.write("\n")
    stream.flush()
