"""钉住 `--review` 真的改到了配置上，以及档位填错会当场报错。

这个选项的症状是**静默不生效**：档位名写错、或者字段名对不上，分析照样跑完，
只是复核带的宽度没变——用户以为选了「细致」，实际拿到的还是默认那一档，
而且看不出来。
"""

from typer.testing import CliRunner

from asmr_auto_cut import cli
from asmr_auto_cut.config import REVIEW_BANDS
from asmr_auto_cut.models import MediaSource, ProjectState


runner = CliRunner()


def capture_config(monkeypatch) -> dict:
    """替掉 analyze_source，把它收到的 config 记下来。"""
    seen: dict = {}

    def fake_analyze_source(source, project_dir, config, progress=None):
        seen["config"] = config
        return ProjectState(
            project_id="demo",
            source=MediaSource(path=str(source), duration=1),
            segments=[],
        )

    monkeypatch.setattr(cli, "analyze_source", fake_analyze_source)
    return seen


def run(review_args: list[str]):
    return runner.invoke(
        cli.app, ["analyze", "input.mp4", "--project-dir", "out", *review_args]
    )


def test_review_defaults_to_the_standard_band(monkeypatch):
    seen = capture_config(monkeypatch)
    assert run([]).exit_code == 0
    assert seen["config"].vad_uncertain_threshold == REVIEW_BANDS["standard"]


def test_each_review_level_sets_its_own_band(monkeypatch):
    seen = capture_config(monkeypatch)
    for level, lower in REVIEW_BANDS.items():
        assert run(["--review", level]).exit_code == 0
        assert seen["config"].vad_uncertain_threshold == lower, level


def test_an_unknown_review_level_is_rejected_before_analyzing(monkeypatch):
    seen = capture_config(monkeypatch)

    result = run(["--review", "careful"])

    assert result.exit_code != 0
    assert "--review" in result.output or "review must be one of" in result.output
    assert "config" not in seen, "档位不合法却已经把分析跑起来了"


def test_review_levels_read_from_coarse_to_fine():
    """档位顺序就是下拉框从上往下的顺序，用户是按这个顺序读的。

    顺序反了就等于把「细致」摆在「快速」上面，而两档的代价说明完全反了。
    """
    values = [REVIEW_BANDS[name] for name in cli.REVIEW_LEVELS]
    assert values == sorted(values, reverse=True)
