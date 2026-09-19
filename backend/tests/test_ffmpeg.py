import subprocess
import sys

import pytest

from asmr_auto_cut.media.ffmpeg import ensure_ffmpeg_available, run_command

# 让子进程往 stderr 吐两个非 UTF-8 字节再以非零码退出。0xad 是 GBK 解不了的字节，
# 在中文 Windows 上 ffmpeg 报错信息里带本地代码页路径时就长这样。
UNDECODABLE_STDERR = "import sys; sys.stderr.buffer.write(b'\\xad\\xad'); sys.exit(3)"


def test_missing_ffmpeg_has_clear_error(monkeypatch):
    def fake_run(*args, **kwargs):
        raise FileNotFoundError()

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="FFmpeg is required"):
        ensure_ffmpeg_available()


def test_undecodable_output_does_not_kill_the_reader_thread():
    """解不了的字节要被替换掉，而不是让读取线程抛异常。

    裸的 text=True 会按系统默认编码（中文 Windows 上是 GBK）解码，撞上解不了的字节
    就在 subprocess 的读取线程里抛 UnicodeDecodeError——命令本身的结果反而拿不到了。
    """
    result = run_command([sys.executable, "-c", UNDECODABLE_STDERR], check=False)

    assert result.returncode == 3
    # 两个字节各变成一个替换字符：说明拿到了内容，不是空字符串
    assert result.stderr == "��"


def test_failing_command_still_reports_its_error():
    """命令失败时，ffmpeg 的报错必须能传到上层，不能被解码异常吞掉。"""
    with pytest.raises(subprocess.CalledProcessError) as excinfo:
        run_command([sys.executable, "-c", UNDECODABLE_STDERR])

    assert excinfo.value.returncode == 3
    assert excinfo.value.stderr == "��"
