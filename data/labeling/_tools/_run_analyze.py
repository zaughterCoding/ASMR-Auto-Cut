"""给某个素材跑一次分析，产出 segments.json。

写成脚本文件而不是直接敲命令行，是为了绕开 Windows 下 shell 传中日韩路径的
编码问题：路径写在 UTF-8 的 .py 里，Python 直接按字面量读，不经过 shell。

用法：python _run_analyze.py [素材名]      不给参数就用 登记表里的 default
"""

import sys
from pathlib import Path

for stream in (sys.stdout, sys.stderr):
    stream.reconfigure(encoding="utf-8")

# 本文件在 data/labeling/_tools/ 下，往上三层是仓库根
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "backend"))

from _materials import default_name, load, project_dir  # noqa: E402
from asmr_auto_cut.analysis.pipeline import analyze_source  # noqa: E402
from asmr_auto_cut.config import AnalysisConfig  # noqa: E402

notes: list[str] = []


def on_progress(event) -> None:
    # 安全阀的提示只走 progress 通道，不写进 segments.json，单独收一下
    if "静默" in event.message:
        notes.append(event.message)
    print(f"  [{event.current}/{event.total}] {event.message}", flush=True)


def main() -> None:
    _, material = load(sys.argv[1] if len(sys.argv) > 1 else default_name())
    src = material["src"]
    if not src.exists():
        raise SystemExit(f"源文件不存在：{src}")

    target = project_dir(material)
    print(f"素材：{material['title']}")
    print(f"源文件：{src.name}")
    print(f"项目目录：{target}")

    state = analyze_source(src, target, AnalysisConfig(), progress=on_progress)
    print(f"\n完成，共 {len(state.segments)} 段，时长 {state.source.duration:.1f}s")
    if notes:
        print("安全阀提示：")
        for note in notes:
            print(f"  {note}")
    else:
        print("安全阀没有触发（阈值落在底噪和上限之间）")


if __name__ == "__main__":
    main()
