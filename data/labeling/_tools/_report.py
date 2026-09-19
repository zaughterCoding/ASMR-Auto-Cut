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

**分组按当前模型重算，不读对照表里那份快照。** 对照表的「模型判断」列是生成时
写下的，一改算法就过期；照着它算，混淆矩阵和时间折算都会是旧模型的成绩，而且
折算那一步会变成「旧模型的分组错误率 × 新模型的分组总时长」，两个口径混在一起。
所以这里用窗口中点去当前的 segments.json 里查它落在哪一段。

这仍不是完全无偏的：抽样配额是按**快照**分组分的，所以「当前分到 keep 的窗口」
偏向于那些模型判断一直没变的窗口。要彻底消掉得重新抽一批，但排名和相对变化不受
影响——_sweep_vad.py 就是用同一批固定窗口做这件事的。
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


def current_group(segments: list[dict], start: float, duration: float) -> str | None:
    """窗口的中点落在当前哪一段里，就按那一段的决策分组。

    用中点而不是「重叠面积最大的一段」：窗口有 10 秒，算法一改就可能横跨好几段，
    按面积归一的话结果会随切点漂移，同一批窗口在不同参数下的分组就不稳定了。
    中点只有一个点，口径稳，而且和抽样时「跟随模型分段取中间那一段」的做法一致。
    """
    middle = start + duration / 2
    for seg in segments:
        if seg["start"] <= middle < seg["end"]:
            if seg["action"] == "keep":
                return "keep"
            if seg["label"] in ("talk", "inactive"):
                return seg["label"]
            return None
    return None


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
    document = json.loads((project_dir_ / "segments.json").read_text(encoding="utf-8"))
    segments = document["segments"]

    rows = []
    unplaced: list[str] = []
    for clip_id, key_row in sorted(key_rows.items()):
        label_row = labels.get(clip_id)
        if label_row is None:
            continue
        start = float(key_row["原片起点秒"])
        duration = float(key_row["时长秒"])
        group = current_group(segments, start, duration)
        if group is None:
            unplaced.append(clip_id)
            continue
        rows.append({
            "clip_id": clip_id,
            #: 当前模型在这个窗口上的决策。
            "group": group,
            #: 对照表里生成时写下的那一份，只用来显示模型挪动了多少。
            "snapshot": key_row["模型判断"],
            "start": start,
            "duration": duration,
            "truth": (label_row.get("你的判断") or "").strip().lower(),
            "note": (label_row.get("备注（可选）") or "").strip(),
        })

    blank = [r["clip_id"] for r in rows if not r["truth"]]
    if blank:
        print(f"⚠️ 还没填的片段：{len(blank)} 个 —— {', '.join(blank[:10])}")
    rows = [r for r in rows if r["truth"]]
    if unplaced:
        print(f"⚠️ 中点落在无法分组的段落里，已跳过：{len(unplaced)} 个"
              f" —— {', '.join(unplaced[:10])}")
    moved = sum(1 for r in rows if r["group"] != r["snapshot"])
    if moved:
        print(f"ℹ️ 有 {moved}/{len(rows)} 个窗口，当前模型的分组和对照表快照不同"
              f"（快照是抽片段时写的，这里按当前模型重算）")

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
    #
    # 算法和 _sweep_vad.py 的 score() 逐字一致：按窗口**实际被 keep 覆盖的秒数**算，
    # 不是按「窗口中点落在哪一组」整段算。后者看着等价，其实差很多——模型完全可以
    # 切掉一个窗口的中间、留下两头，那时中点落在 cut 段里，整段计数会把它记成 0
    # 残留，而实际留下了几秒。两边口径必须一样，否则同一批窗口能报出两个数。
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
        hi = r["start"] + r["duration"]
        kept = sum(
            max(0.0, min(seg["end"], hi) - max(seg["start"], r["start"]))
            for seg in segments
            if seg["action"] == "keep"
        )
        if r["truth"] in WANT_KEEP:
            sample_cut += r["duration"] - kept
        elif r["truth"] in WANT_CUT:
            sample_kept += kept
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
