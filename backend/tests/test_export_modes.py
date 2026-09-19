from asmr_auto_cut.export import ffmpeg_export
from asmr_auto_cut.export.ffmpeg_export import export_clean_media
from asmr_auto_cut.models import MediaSource, ProjectState, TimelineSegment


def seg(id, start, end, action):
    return TimelineSegment(
        id=id,
        start=start,
        end=end,
        label="asmr",
        action=action,
        confidence=1.0,
        source="test",
    )


def make_state(tmp_path):
    source = tmp_path / "input.mp4"
    source.write_bytes(b"fake")
    return ProjectState(
        project_id="demo",
        source=MediaSource(path=str(source), duration=4.0),
        segments=[
            seg("seg_1", 0.0, 1.0, "keep"),
            seg("seg_2", 1.0, 2.0, "cut"),
            seg("seg_3", 2.0, 4.0, "keep"),
        ],
    )


def _capture(monkeypatch):
    commands = []
    monkeypatch.setattr(ffmpeg_export, "ensure_ffmpeg_available", lambda: None)
    monkeypatch.setattr(ffmpeg_export, "run_command", lambda command: commands.append(command))
    return commands


def test_fast_mode_uses_no_fade_filter(monkeypatch, tmp_path):
    commands = _capture(monkeypatch)

    export_clean_media(make_state(tmp_path), tmp_path / "clean.mp4", mode="fast")

    flat = " ".join(" ".join(command) for command in commands)
    assert "afade" not in flat


def test_quality_mode_keeps_fade_filter(monkeypatch, tmp_path):
    commands = _capture(monkeypatch)

    export_clean_media(make_state(tmp_path), tmp_path / "clean.mp4", mode="quality")

    flat = " ".join(" ".join(command) for command in commands)
    assert "afade" in flat


def test_quality_mode_is_the_default(monkeypatch, tmp_path):
    """不传 mode 时必须还是 0.1.0 的行为：既有的调用方一个都不该被改到。"""
    commands = _capture(monkeypatch)

    export_clean_media(make_state(tmp_path), tmp_path / "clean.mp4")

    flat = " ".join(" ".join(command) for command in commands)
    assert "afade" in flat


def test_fast_mode_still_renders_every_keep_clip(monkeypatch, tmp_path):
    """快模式只该省掉渐变，不该省掉片段或改变合并方式。"""
    commands = _capture(monkeypatch)

    export_clean_media(make_state(tmp_path), tmp_path / "clean.mp4", mode="fast")

    # 2 个 keep 段各一条渲染命令 + 1 条 concat
    assert len(commands) == 3
    assert any(isinstance(command, list) and "concat" in command for command in commands)
    # 视频仍然原样透传，没有因为快模式被重编码
    assert all("copy" in command for command in commands)
