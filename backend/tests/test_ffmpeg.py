import subprocess
import sys

import pytest

from asmr_auto_cut.media.ffmpeg import ensure_ffmpeg_available, run_command, tool_path

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


@pytest.fixture
def no_override(monkeypatch):
    """默认没有 ASMR_AUTO_CUT_FFMPEG_DIR，否则本机设了会污染下面每条用例。"""
    monkeypatch.delenv("ASMR_AUTO_CUT_FFMPEG_DIR", raising=False)


def test_tool_path_falls_back_to_bare_name(monkeypatch, no_override):
    """没打包、没覆盖时返回裸命令名，交给 PATH——开发环境的行为一字未改。"""
    monkeypatch.delattr(sys, "frozen", raising=False)

    assert tool_path("ffmpeg") == "ffmpeg"


def test_tool_path_prefers_the_override(monkeypatch, tmp_path):
    """显式覆盖永远最先看：本机那份 ffmpeg 不在安装目录布局里。"""
    (tmp_path / "ffmpeg.exe").write_bytes(b"")
    monkeypatch.setenv("ASMR_AUTO_CUT_FFMPEG_DIR", str(tmp_path))
    monkeypatch.delattr(sys, "frozen", raising=False)

    assert tool_path("ffmpeg") == str(tmp_path / "ffmpeg.exe")


def test_tool_path_ignores_an_override_without_the_binary(monkeypatch, tmp_path, no_override):
    """覆盖目录里没有这个二进制就当没设，继续往下退而不是报错。"""
    monkeypatch.setenv("ASMR_AUTO_CUT_FFMPEG_DIR", str(tmp_path / "nonexistent"))
    monkeypatch.delattr(sys, "frozen", raising=False)

    assert tool_path("ffmpeg") == "ffmpeg"


def test_tool_path_resolves_beside_an_installed_program(monkeypatch, no_override, tmp_path):
    """冻结后：入口 exe 在 <安装目录>/backend/，ffmpeg 在 <安装目录>/ffmpeg/。

    这一条钉的是「往上两级」——用 sys._MEIPASS 会落到 backend/_internal/，
    往上两级就成了 backend/，拼出来的路径必然不存在。
    """
    install = tmp_path / "install"
    backend = install / "backend"
    backend.mkdir(parents=True)
    (backend / "asmr-auto-cut.exe").write_bytes(b"")
    (install / "ffmpeg").mkdir()
    (install / "ffmpeg" / "ffmpeg.exe").write_bytes(b"")
    (install / "ffmpeg" / "ffprobe.exe").write_bytes(b"")

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(backend / "asmr-auto-cut.exe"))

    assert tool_path("ffmpeg") == str(install / "ffmpeg" / "ffmpeg.exe")
    assert tool_path("ffprobe") == str(install / "ffmpeg" / "ffprobe.exe")


def test_tool_path_falls_through_when_frozen_without_the_binary(monkeypatch, no_override, tmp_path):
    """装了个只带壳的旧版安装包时，退回 PATH 至少还能给出可读提示。"""
    backend = tmp_path / "install" / "backend"
    backend.mkdir(parents=True)
    (backend / "asmr-auto-cut.exe").write_bytes(b"")

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(backend / "asmr-auto-cut.exe"))

    assert tool_path("ffmpeg") == "ffmpeg"
