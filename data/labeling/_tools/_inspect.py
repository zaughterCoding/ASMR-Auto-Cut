"""看一个素材的分段构成。定下一套标注的配额之前先跑这个。

用法：python _inspect.py [素材名] [--region lo,hi]
      不给素材名就用登记表里的 default。
      --region 给一对秒数，额外列出这段时间里的每一段，用来看某个区域是怎么切的。

素材名和区域都从命令行来，不写死在这份文件里——它要进版本管理，而素材是什么、
在哪一段时间出问题，都属于本地数据。
"""

import json
import sys
from collections import Counter
from pathlib import Path

for stream in (sys.stdout, sys.stderr):
    stream.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from _materials import default_name, load, project_dir  # noqa: E402


def read_segments(material: dict) -> dict:
    path = project_dir(material) / "segments.json"
    if not path.exists():
        raise SystemExit(f"没有分析结果：{path}\n先跑 _run_analyze.py。")
    return json.loads(path.read_text(encoding="utf-8"))


def dump_region(data: dict, lo: float, hi: float) -> None:
    print(f"\n  原片 {lo:.0f}s – {hi:.0f}s 之间的段落：")
    for seg in data["segments"]:
        if seg["end"] < lo or seg["start"] > hi:
            continue
        flag = "  <-- 整段落在区间内" if seg["start"] >= lo and seg["end"] <= hi else ""
        print(
            f"    {seg['start']:8.1f} – {seg['end']:8.1f} "
            f"({seg['end'] - seg['start']:6.1f}s)  {seg['label']:<9} {seg['action']:<5} "
            f"conf={seg.get('confidence')}  {seg.get('source')}{flag}"
        )


def totals(data: dict) -> None:
    duration = data["source"]["duration"]
    keep = [s for s in data["segments"] if s["action"] == "keep"]
    talk = [s for s in data["segments"] if s["label"] == "talk"]
    inact = [s for s in data["segments"] if s["label"] == "inactive"]
    print(f"\n  总时长 {duration / 60:.1f} 分钟，共 {len(data['segments'])} 段")
    for name, group in (("keep", keep), ("talk", talk), ("inactive", inact)):
        secs = sum(s["end"] - s["start"] for s in group)
        short = sum(
            1
            for s in group
            if s["end"] - s["start"] < 2.0
        )
        print(
            f"    {name:<9} {len(group):4d} 段 / {secs:8.1f}s = {secs / duration * 100:5.1f}%"
            f"   其中 <2s 的 {short} 段"
        )
    # 碎片比例是配额的关键输入：某组全是短段时，抽出来的片段听不出内容，
    # 而短段又恰恰是切碎的产物，混在一起就没法判。
    print("    source 分布：", dict(Counter(s.get("source") for s in data["segments"])))


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    region = None
    for arg in sys.argv[1:]:
        if arg.startswith("--region="):
            lo, hi = arg.split("=", 1)[1].split(",")
            region = (float(lo), float(hi))

    _, material = load(args[0] if args else default_name())
    data = read_segments(material)

    print("=" * 66)
    print(f"【{material['title']}】")
    print("=" * 66)
    totals(data)

    if region is not None:
        dump_region(data, *region)

    print("\n  全部 inactive 段（静默检测切掉的）：")
    for seg in data["segments"]:
        if seg["label"] == "inactive":
            print(
                f"    {seg['start']:8.1f} – {seg['end']:8.1f} "
                f"({seg['end'] - seg['start']:6.1f}s)  conf={seg.get('confidence')}  "
                f"{seg.get('source')}"
            )


if __name__ == "__main__":
    main()
