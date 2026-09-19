import subprocess

import pytest

from asmr_auto_cut.media.ffmpeg import ensure_ffmpeg_available


def test_missing_ffmpeg_has_clear_error(monkeypatch):
    def fake_run(*args, **kwargs):
        raise FileNotFoundError()

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="FFmpeg is required"):
        ensure_ffmpeg_available()
