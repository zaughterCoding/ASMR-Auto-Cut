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


def emit_json_event(event: BaseModel, stream: TextIO | None = None) -> None:
    # stream 默认值必须是 None 而不是 sys.stdout：写成默认参数的话，绑定发生在
    # import 那一刻，之后谁把 sys.stdout 换掉都影响不到这里。pytest 的 capsys、
    # typer 的 CliRunner、contextlib.redirect_stdout 都是这么干的，结果就是事件
    # 写进了真实控制台，调用方一条都收不到。这里改成调用时再取。
    if stream is None:
        stream = sys.stdout
    stream.write(json.dumps(event.model_dump(), ensure_ascii=False))
    stream.write("\n")
    stream.flush()
