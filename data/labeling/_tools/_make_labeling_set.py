"""从一次分析的结果里抽出一套人工标注用的片段。

用法：python _make_labeling_set.py [素材名]      不给参数就用 登记表里的 default

设计说明（为什么这么做，以后加中韩素材时要照着用）：

1. 片段长度 10 秒，**跟随模型自己的分段**取中间那一段，不跨段。跨了段的话，
   一个片段里就混着"模型判该留"和"模型判该切"两种决策，标注结果没法归因。
   段本身不足 10 秒就用整段。

2. 抽样**按时间加权**，不是按段落加权。最终关心的是"省下多少分钟"，不是
   "模型分了多少段"，所以一分钟的长段和一秒钟的短段应该按各自时长成比例被抽到。

3. 三组分别抽，是为了让每一组的"判对率"都能单独算出来：
     - 模型判 keep 的抽 40~60 个 → 听出有几个真该留 = 留得对不对
     - 模型判 talk 的抽 20~50 个 → 听出有几个真是聊天 = 切得对不对
     - 模型判 inactive 的抽 10~20 个
   随机抽的话 95% 都会落在"模型判该留"里（实测一条素材上就是 95%），模型切掉的
   那部分本来就少，不单独抽就几乎抽不到。

   各组的目标数按「该组素材总量」和「上一批的短板」给，写在登记表的 plan 里：
   某一组的素材总量小到抽不出足够多的独立位置时，配额就得压到别处去；上一批哪
   一组的判对率置信区间宽到没法用，这一批就把配额挪过去。抽的时候同组内片段起点
   至少隔开 MIN_START_GAP，免得抽出一堆几乎一样的位置。

4. 输出**打乱顺序**、文件名用不透明的编号，同时把分组写到另一个文件里。
   标注的人看不到分组，才不会被模型的判断带跑（盲标）。

5. 片段按原始音质抽（-c:a copy，不重编码、不降采样）。耳语和气声的细节在高频，
   降到 16kHz 就听不出来了，而标注恰恰要靠这些细节。
"""

import csv
import json
import random
import subprocess
import sys
from pathlib import Path

for stream in (sys.stdout, sys.stderr):
    stream.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _materials import default_name, load, project_dir  # noqa: E402

CLIP_SECONDS = 10.0
#: 同一组里两个片段的起点至少隔开这么多秒，否则会抽出一堆几乎一样的位置。
MIN_START_GAP = 3.0


def load_regions(
    segments_path: Path, min_region_seconds: float
) -> dict[str, list[tuple[float, float]]]:
    """把段落按「模型的决策」归成三组区间。"""
    data = json.loads(segments_path.read_text(encoding="utf-8"))
    regions: dict[str, list[tuple[float, float]]] = {"keep": [], "talk": [], "inactive": []}
    for seg in data["segments"]:
        if seg["action"] == "keep":
            key = "keep"
        elif seg["label"] == "talk":
            key = "talk"
        elif seg["label"] == "inactive":
            key = "inactive"
        else:
            continue
        if seg["end"] - seg["start"] >= min_region_seconds:
            regions[key].append((seg["start"], seg["end"]))
    return regions


def sample_clip(
    rng: random.Random, regions: list[tuple[float, float]]
) -> tuple[int, float, float]:
    """按时长加权抽一个点，再在它所在的区间里取一个不越界的窗口。

    返回 (区间下标, 窗口起点, 窗口长度)。下标用来去重：同一个区间里只要起点
    隔得够远就可以出多个片段，但近到重叠就没有意义了。
    """
    weights = [end - start for start, end in regions]
    index = rng.choices(range(len(regions)), weights=weights, k=1)[0]
    start, end = regions[index]
    length = min(CLIP_SECONDS, end - start)
    # 抽中的点当窗口中心，再夹回区间内；夹完保证窗口完整落在这一段里
    center = rng.uniform(start, end)
    clip_start = min(max(center - length / 2, start), end - length)
    return index, round(clip_start, 3), round(length, 3)


def extract(src: Path, start: float, length: float, dest: Path) -> None:
    subprocess.run(
        [
            "ffmpeg", "-v", "error", "-y",
            "-ss", f"{start:.3f}", "-t", f"{length:.3f}",
            "-i", str(src),
            "-vn", "-c:a", "copy",
            str(dest),
        ],
        check=True,
    )


def main() -> None:
    _, material = load(sys.argv[1] if len(sys.argv) > 1 else default_name())
    src: Path = material["src"]
    out_dir: Path = material["out"]
    plan: dict[str, int] = material["plan"]
    clips_dir = out_dir / "clips"

    segments_path = project_dir(material) / "segments.json"
    if not segments_path.exists():
        raise SystemExit(f"还没有分析结果：{segments_path}")

    print(f"素材：{material['title']}")
    print(f"分析结果：{segments_path}")
    print(f"输出目录：{out_dir}\n")

    regions = load_regions(segments_path, material["min_region_seconds"])
    for name, items in regions.items():
        total = sum(end - start for start, end in items)
        print(f"  {name:9s} {len(items):4d} 段 / {total/60:6.1f} 分钟")

    rng = random.Random(material["seed"])
    picked: list[tuple[str, float, float]] = []
    for name, count in plan.items():
        if not regions[name]:
            print(f"  跳过 {name}：没有可抽的区间", file=sys.stderr)
            continue
        seen: set[tuple[int, int]] = set()
        attempts = 0
        while len([p for p in picked if p[0] == name]) < count and attempts < count * 200:
            attempts += 1
            index, clip_start, length = sample_clip(rng, regions[name])
            # 同一段里每 MIN_START_GAP 秒才算一个不同的位置
            bucket = (index, int(clip_start // MIN_START_GAP))
            if bucket in seen:
                continue
            seen.add(bucket)
            picked.append((name, clip_start, length))
        got = len([p for p in picked if p[0] == name])
        print(f"\n  抽到 {name}: {got} 个（目标 {count}）")

    rng.shuffle(picked)
    clips_dir.mkdir(parents=True, exist_ok=True)

    rows, key_rows = [], []
    for index, (group, clip_start, length) in enumerate(picked, start=1):
        clip_id = f"clip_{index:03d}"
        dest = clips_dir / f"{clip_id}.m4a"
        if not dest.exists():
            extract(src, clip_start, length, dest)
        rows.append({
            "clip_id": clip_id,
            "时长秒": f"{length:.1f}",
            "你的判断": "",
            "备注（可选）": "",
        })
        key_rows.append({
            "clip_id": clip_id,
            "模型判断": group,
            "原片起点秒": f"{clip_start:.3f}",
            "时长秒": f"{length:.3f}",
        })
        if index % 20 == 0:
            print(f"  已生成 {index}/{len(picked)}")

    with (out_dir / "labels.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["clip_id", "时长秒", "你的判断", "备注（可选）"])
        writer.writeheader()
        writer.writerows(rows)

    with (out_dir / "_answer_key.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["clip_id", "模型判断", "原片起点秒", "时长秒"])
        writer.writeheader()
        writer.writerows(key_rows)

    print(f"\n完成：{len(picked)} 个片段 -> {clips_dir}")
    print(f"标注表：{out_dir / 'labels.csv'}")


if __name__ == "__main__":
    main()
