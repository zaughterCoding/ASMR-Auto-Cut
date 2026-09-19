import json
import sys

from typer.testing import CliRunner

from asmr_auto_cut import cli
from asmr_auto_cut.media.ffmpeg import run_command
from asmr_auto_cut.models import MediaSource, ProjectState


runner = CliRunner()

#: 在子进程里走一遍「开启 UTF-8 输出 + 发一条中文进度」。单独开子进程是必须的：
#: 只有 stdout 真的接到管道上，Python 才会按系统编码（中文 Windows 上是 GBK）
#: 来编码，这个 bug 在进程内用 StringIO 是复现不出来的。
#: 中文写成转义是为了让传给子进程的 argv 保持纯 ASCII，否则一旦 argv 的编码
#: 本身有问题，测试就分不清是 argv 坏了还是 stdout 编码坏了。
_EMIT_CHINESE_PROGRESS = (
    "from asmr_auto_cut.cli import _enable_utf8_output;"
    "from asmr_auto_cut.progress import ProgressEvent, emit_json_event;"
    "_enable_utf8_output();"
    "emit_json_event(ProgressEvent(operation='analyze', phase='p',"
    " message='\\u6b63\\u5728\\u68c0\\u6d4b\\u4eba\\u58f0', current=1, total=2))"
)


def test_analyze_progress_json_outputs_result(monkeypatch, tmp_path):
    def fake_analyze_source(source, project_dir, config, progress=None):
        if progress:
            from asmr_auto_cut.progress import ProgressEvent
            progress(ProgressEvent(operation="analyze", phase="probe_source", message="x", current=1, total=1))
        return ProjectState(project_id="demo", source=MediaSource(path=str(source), duration=1), segments=[])

    monkeypatch.setattr(cli, "analyze_source", fake_analyze_source)
    result = runner.invoke(
        cli.app,
        ["analyze", "input.mp4", "--project-dir", str(tmp_path), "--progress-json"],
    )
    assert result.exit_code == 0
    records = [json.loads(line) for line in result.stdout.strip().splitlines()]
    assert records[0]["type"] == "progress"
    assert records[-1]["type"] == "result"
    assert records[-1]["project_path"].endswith("project.json")


def test_progress_json_is_utf8_even_when_stdout_is_a_pipe():
    # run_command 按 UTF-8 解码，解不出来的字节会变成替换字符。所以这条断言
    # 同时验证了两件事：字节是合法 UTF-8，且内容没丢。
    result = run_command([sys.executable, "-c", _EMIT_CHINESE_PROGRESS])
    assert "正在检测人声" in result.stdout
