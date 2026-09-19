"""把人工标注和模型判断对起来，算出真实指标。

用法：python _report.py [素材名]      不给参数就用 登记表里的 default

三件事：
1. 混淆矩阵 —— 模型分的组 × 人工的判断。
2. 时间加权的总账 —— 抽样是按组等权抽的（60/20/20），不代表真实时间占比，
   所以要按每组在原片里的总时长折算回「多少秒」。
3. 错在哪里 —— 把错的片段按原片时间列出来，并对比它们的波形能量，
   看根因是不是音量。

和 _sweep_vad.py 的分工：那个在**固定的**标注窗口上比较不同参数组合，用来排参数；
这个拿**当前**的落盘结果算绝对指标，用来看交付物到底有多好。两者的「误剪/残留」
口径一致，可以直接对着看。
"""

import csv
import json
import sys
from pathlib import Path

for stream in (sys.stdout, sys.stderr):
    stream.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from _materials import default_name, load, project_dir  # noqa: E402

#: 人工标签 -> 期望的动作。mixed / uncertain 说不清该留该切，两边都不计。
WANT_KEEP = {"asmr"}
WANT_CUT = {"talk", "inactive", "other"}
#: 模型的分组 -> 人工标签，算「判对」时用。
CORRECT = {"keep": "asmr", "talk": "talk", "inactive": "inactive"}


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def load_waveform(project_dir: Path) -> list[dict]:
    return json.loads((project_dir / "waveform.json").read_text(encoding="utf-8"))


def window_rms(waveform: list[dict], start: float, duration: float) -> float | None:
    """取 [start, start+duration) 这段窗口的平均 rms。"""
    picked = [
        point["rms"] for point in waveform if start <= point["time"] < start + duration
    ]
    return sum(picked) / len(picked) if picked else None


def main() -> None:
    _, material = load(sys.argv[1] if len(sys.argv) > 1 else default_name())
    out_dir: Path = material["out"]
    project_dir_ = project_dir(material)

    print(f"素材：{material['title']}")
    print(f"分析结果：{project_dir_}\n")

    labels = {row["clip_id"]: row for row in load_csv(out_dir / "labels.csv")}
    key_rows = {row["clip_id"]: row for row in load_csv(out_dir / "_answer_key.csv")}
    waveform = load_waveform(project_dir_)

    rows = []
    for clip_id, key_row in sorted(key_rows.items()):
        label_row = labels.get(clip_id)
        if label_row is None:
            continue
        rows.append({
            "clip_id": clip_id,
            "group": key_row["模型判断"],
            "start": float(key_row["原片起点秒"]),
            "duration": float(key_row["时长秒"]),
            "truth": (label_row.get("你的判断") or "").strip().lower(),
            "note": (label_row.get("备注（可选）") or "").strip(),
        })

    blank = [r["clip_id"] for r in rows if not r["truth"]]
    if blank:
        print(f"⚠️ 还没填的片段：{len(blank)} 个 —— {', '.join(blank[:10])}")
    rows = [r for r in rows if r["truth"]]

    groups = ["keep", "talk", "inactive"]
    truths = ["asmr", "talk", "inactive", "other", "mixed", "uncertain"]

    print("=" * 66)
    print("混淆矩阵（行 = 模型判断，列 = 你的判断）")
    print("=" * 66)
    print(f"{'模型\\人工':<10}" + "".join(f"{t:>10}" for t in truths) + f"{'合计':>8}")
    for group in groups:
        subset = [r for r in rows if r["group"] == group]
        cells = [sum(1 for r in subset if r["truth"] == t) for t in truths]
        print(f"{group:<10}" + "".join(f"{c:>10}" for c in cells) + f"{len(subset):>8}")

    print()
    print("=" * 66)
    print("每一组的判对率")
    print("=" * 66)
    for group in groups:
        subset = [r for r in rows if r["group"] == group]
        if not subset:
            continue
        right = [r for r in subset if r["truth"] == CORRECT[group]]
        print(f"  {group:<9} {len(right):3d}/{len(subset):<3d} = {len(right)/len(subset)*100:5.1f}%")

    # 按时间折算：每组的片段等权，乘以该组在原片里的总时长
    document = json.loads((project_dir_ / "segments.json").read_text(encoding="utf-8"))
    segments = document["segments"]
    totals = {g: 0.0 for g in groups}
    for seg in segments:
        if seg["action"] == "keep":
            totals["keep"] += seg["end"] - seg["start"]
        elif seg["label"] in ("talk", "inactive"):
            totals[seg["label"]] += seg["end"] - seg["start"]
    source_duration = document["source"]["duration"]

    print()
    print("=" * 66)
    print(f"折算成时间（原片 {source_duration/60:.1f} 分钟）")
    print("=" * 66)
    print(f"{'组':<10}{'原片总长':>12}{'判错比例':>12}{'折合秒数':>12}")
    wasted_keep = 0.0
    wrongly_cut = 0.0
    for group in groups:
        subset = [r for r in rows if r["group"] == group]
        if not subset:
            continue
        wrong = [r for r in subset if r["truth"] != CORRECT[group]]
        ratio = len(wrong) / len(subset)
        seconds = ratio * totals[group]
        print(f"{group:<10}{totals[group]:>10.1f}s{ratio*100:>11.1f}%{seconds:>11.1f}s")
        if group == "keep":
            # 留下的东西里没用的部分
            wasted_keep = ratio * totals[group]
        else:
            # 被切掉的东西里其实该留的部分
            keep_ratio = sum(1 for r in wrong if r["truth"] == "asmr") / len(subset)
            wrongly_cut += keep_ratio * totals[group]

    print()
    print(f"  ➜ 留下的内容里，约 {wasted_keep/60:.1f} 分钟是废的（该切没切）")
    print(f"  ➜ 切掉的内容里，约 {wrongly_cut:.0f} 秒其实是 ASMR（误剪）")
    print(f"  ➜ 误剪占原片 {wrongly_cut/source_duration*100:.2f}%")

    # 抽样是分层的，样本里的秒数不等于原片的秒数；这一栏不做时间折算，
    # 直接数窗口，用来看「改动有没有让这几组变好」。
    print()
    print("=" * 66)
    print("样本内的原始秒数（不含时间折算，只看相对变化）")
    print("=" * 66)
    sample_cut, sample_kept, excluded = 0.0, 0.0, 0
    for r in rows:
        # mixed / uncertain 说不清该留该切，两边都不计；other（音乐、杂音）算该切。
        if r["truth"] in ("mixed", "uncertain"):
            excluded += 1
            continue
        if r["truth"] in WANT_KEEP:
            if r["group"] != "keep":
                sample_cut += r["duration"]
        elif r["truth"] in WANT_CUT and r["group"] == "keep":
            sample_kept += r["duration"]
    print(f"  误剪（该留却被切掉的样本秒数）  {sample_cut:6.1f}s")
    print(f"  残留（该切却留下的样本秒数）    {sample_kept:6.1f}s")
    print(f"\n  （mixed / uncertain 共 {excluded} 个，两边都不计）")

    print()
    print("=" * 66)
    print("判错的片段，连同它们的波形能量")
    print("=" * 66)
    ok_rms = []
    for group in groups:
        subset = [r for r in rows if r["group"] == group]
        for r in subset:
            r["rms"] = window_rms(waveform, r["start"], r["duration"])
        good = [r["rms"] for r in subset if r["truth"] == CORRECT[group] and r["rms"]]
        bad = [r for r in subset if r["truth"] != CORRECT[group]]
        ok_rms += good
        if good:
            print(f"\n  [{group}] 判对的平均 rms = {sum(good)/len(good):.5f}（{len(good)} 个）")
        for r in sorted(bad, key=lambda r: r["start"]):
            tag = (
                "误剪!" if r["truth"] in WANT_KEEP
                else ("残留" if r["truth"] in WANT_CUT else "存疑")
            )
            print(
                f"    {tag} {r['clip_id']}  {r['start']:9.1f}s  {r['duration']:4.1f}s  "
                f"模型={group:<8} 你={r['truth']:<8} rms={r['rms']:.5f}"
                + (f"  「{r['note']}」" if r["note"] else "")
            )
    if ok_rms:
        print(f"\n  全部判对的平均 rms = {sum(ok_rms)/len(ok_rms):.5f}")


if __name__ == "__main__":
    main()
