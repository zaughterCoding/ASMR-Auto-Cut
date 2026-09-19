"""在已标注的片段上扫 Silero VAD 的参数，拿人工标注当答案。

用法：python _sweep_vad.py [素材名] [--rounds 1,2] [--set k=v,k=v] [--keep-audio]
      不给素材名就用 登记表里的 default，不给 --rounds 就全部轮。

  --rounds=1,2    只跑这几轮；--rounds= 空表示一轮都不跑，只报基准。
  --set           给基准配置打个补丁。做「新旧同口径对照」就靠它，比如
                  --set=inactive_rms_threshold=0.004 --rounds= 能跑出旧静默阈值
                  在同一套打分下的成绩。补丁落在 inactive_* 上会触发波形重扫
                  （见 WAVEFORM_FIELDS），否则那次对照是拿同一个配置跟自己比。
  --keep-audio    扫完不删 analysis.wav。连着跑几组实验时开着省一次重抽。

为什么这么写：
  「抽分析音频」只做一次；「扫波形」按 WAVEFORM_FIELDS 做键缓存——只扫 VAD 参数
  时它是常量，扫一次就够（对 70 分钟的录音是分钟级的开销），扫到 inactive_* 才
  重扫。Silero 的模型实例也复用，否则每轮都要反序列化一遍权重。

打分方式：
  标注片段是按「模型的判断」分层抽的（keep 60 / talk 20 / inactive 20），不是按
  时间抽的，所以把这 100 个片段的秒数加起来**不代表原片的真实占比**。但这套样本
  对**所有**参数组合都是同一套，所以拿它来排参数是成立的——只看排名和相对变化，
  别把这些秒数当成原片的绝对量。要看绝对量得用 _report.py（它按组时长折算）。

两个指标：
  误剪 = 人工标成 asmr 的窗口里，被模型判 cut 的秒数。丢的是内容，用户拿不回来。
  残留 = 人工标成 talk/inactive/other 的窗口里，被判 keep 的秒数。切得不干净。
  误剪是硬约束、残留是优化目标：整片里混着几分钟废话还能用，剪掉的内容回不来。
"""

import json
import sys
from dataclasses import dataclass
from pathlib import Path

for stream in (sys.stdout, sys.stderr):
    stream.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
# 本文件在 data/labeling/_tools/ 下，往上三层是仓库根
sys.path.insert(0, str(HERE.parents[2] / "backend"))

from _materials import default_name, load, project_dir  # noqa: E402
from asmr_auto_cut.analysis.block_analysis import analyze_audio_blocks  # noqa: E402
from asmr_auto_cut.analysis.pipeline import assemble_project_state  # noqa: E402
from asmr_auto_cut.analysis.speech import detect_speech_intervals  # noqa: E402
from asmr_auto_cut.config import AnalysisConfig  # noqa: E402
from asmr_auto_cut.media.ffmpeg import extract_analysis_audio, probe_duration  # noqa: E402

#: 每轮只动一个参数，取当前最优再进下一轮（坐标下降）。参数之间有耦合——
#: pad 会影响两段会不会被算成相连，进而影响碎片——所以这些轮次是起点不是终点，
#: 最后一轮跑完还可以手动做一次二维确认。
ROUNDS: list[tuple[str, list]] = [
    ("vad_threshold", [0.5, 0.45, 0.4, 0.35, 0.3, 0.25]),
    ("vad_min_silence_duration_ms", [100, 200, 300, 500, 800]),
    ("vad_speech_pad_ms", [30, 80, 150, 250]),
    ("vad_min_speech_duration_ms", [250, 100, 400, 700]),
]

#: 最后打印参数表时列出来的字段。--set 打进来的补丁字段也要看得见，
#: 所以这里列全，不是只列 ROUNDS 里出现过的。
VAD_FIELDS = [
    "vad_threshold",
    "vad_min_speech_duration_ms",
    "vad_min_silence_duration_ms",
    "vad_speech_pad_ms",
    "inactive_rms_threshold",
    "inactive_rms_ratio",
    "inactive_rms_headroom_db",
]

#: 影响「波形 + 静默」那一趟扫描的字段。只有这组变了才需要重扫：VAD 参数在
#: run_once 里现算，而静默区间是 main 里扫一次缓存下来的。--set 打进来的补丁
#: 如果落在这组里而缓存不跟着失效，那次对照就是拿同一个配置跟自己比。
WAVEFORM_FIELDS = [
    "inactive_frame_seconds",
    "inactive_min_duration",
    "inactive_rms_threshold",
    "inactive_rms_percentile",
    "inactive_rms_ratio",
    "inactive_rms_floor",
    "inactive_rms_headroom_db",
]

#: 选参数时的误剪容忍带（秒，整个样本上的合计）。误剪是硬约束、残留是优化目标，
#: 所以这条线锚在**基准**上：容许比现状多丢这么多内容，在此之内挑残留最低的。
#: 给 3 秒是因为样本合计约 800 秒音频，3 秒 = 0.4%，小于标注本身的手抖幅度。
CUT_TOLERANCE = 3.0

#: 人工标签 -> 期望的动作。mixed / uncertain 没法拆成两半，两边都不计入。
WANT_KEEP = {"asmr"}
WANT_CUT = {"talk", "inactive", "other"}


@dataclass
class Window:
    clip_id: str
    start: float
    duration: float
    truth: str
    group: str


@dataclass
class Score:
    误剪: float
    残留: float
    #: 派生量，不是独立测量：切掉 ≡ 误剪 + （该切窗口总时长）- 残留。列出来只为看
    #: 出这轮动的是「切的总量」还是「切的位置」——如果残留的每一次下降都被切掉的
    #: 等量上升抵消，那这一轮就没在找边界，只是在同一根杆子上滑。
    切掉: float
    段数: int
    #: 人工标签 -> 残留秒数。分开统计是因为 talk 的残留该找 VAD，inactive 的残留
    #: 该找静默检测器——两套完全不同的东西，混成一个数就不知道该动哪个。
    残留明细: dict[str, float]


def load_csv(path: Path) -> list[dict[str, str]]:
    import csv

    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def load_windows(out_dir: Path) -> list[Window]:
    labels = {r["clip_id"]: r for r in load_csv(out_dir / "labels.csv")}
    key = {r["clip_id"]: r for r in load_csv(out_dir / "_answer_key.csv")}
    windows = []
    for clip_id, key_row in sorted(key.items()):
        label_row = labels.get(clip_id)
        if label_row is None:
            continue
        truth = (label_row.get("你的判断") or "").strip().lower()
        if truth not in WANT_KEEP | WANT_CUT:
            continue
        windows.append(
            Window(
                clip_id=clip_id,
                start=float(key_row["原片起点秒"]),
                duration=float(key_row["时长秒"]),
                truth=truth,
                group=key_row["模型判断"],
            )
        )
    return windows


def score(segments, windows: list[Window]) -> Score:
    """把每个标注窗口切成 keep / cut 两半，按人工标签归到误剪或残留上。"""
    cut_wrong = kept_wrong = cut_total = 0.0
    residual: dict[str, float] = {}
    for window in windows:
        lo, hi = window.start, window.start + window.duration
        kept = 0.0
        for seg in segments:
            if seg.action != "keep":
                continue
            kept += max(0.0, min(seg.end, hi) - max(seg.start, lo))
        cut = window.duration - kept
        cut_total += cut
        if window.truth in WANT_KEEP:
            cut_wrong += cut
        else:
            kept_wrong += kept
            residual[window.truth] = residual.get(window.truth, 0.0) + kept
    return Score(误剪=cut_wrong, 残留=kept_wrong, 切掉=cut_total,
                 段数=len(segments), 残留明细=residual)


def format_residual(score: Score) -> str:
    """按残留量从大到小排一行，用来一眼看出该动哪个检测器。"""
    if not score.残留明细:
        return "（无）"
    items = sorted(score.残留明细.items(), key=lambda item: -item[1])
    return "  ".join(f"{label} {seconds:.1f}s" for label, seconds in items)


def run_once(config, wav, waveform_result, windows, duration, model) -> Score:
    speech = detect_speech_intervals(wav, config, model=model)
    state = assemble_project_state(
        project_id="sweep",
        source_path="sweep",
        duration=duration,
        speech_intervals=speech,
        inactive_intervals=waveform_result.inactive_intervals,
        config=config,
    )
    return score(state.segments, windows)


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    _, material = load(args[0] if args else default_name())
    out_dir: Path = material["out"]
    src: Path = material["src"]
    target = project_dir(material)

    # None = 全跑，空集合 = 一轮都不跑（只看基准）。两者不能混，所以不用真假值判断。
    wanted_rounds: set[int] | None = None
    overrides: dict[str, str] = {}
    keep_audio = "--keep-audio" in sys.argv
    for arg in sys.argv[1:]:
        if arg.startswith("--rounds="):
            raw = arg.split("=", 1)[1]
            wanted_rounds = {int(x) for x in raw.split(",") if x.strip()}
        elif arg.startswith("--set="):
            for pair in arg.split("=", 1)[1].split(","):
                if not pair.strip():
                    continue
                name, value = pair.split("=", 1)
                overrides[name.strip()] = value.strip()

    windows = load_windows(out_dir)
    if not windows:
        raise SystemExit(f"没有可用的标注：{out_dir / 'labels.csv'}（先标注，或检查标签拼写）")
    kept = sum(1 for w in windows if w.truth in WANT_KEEP)
    print(f"素材：{material['title']}")
    print(f"标注窗口：{len(windows)} 个（该留 {kept}，该切 {len(windows) - kept}）")
    print(f"样本合计：{sum(w.duration for w in windows):.0f} 秒\n")

    # 分析音频留在项目目录里，不落 C 盘；扫完删掉（--keep-audio 时留着，
    # 连着跑几组实验能省一次 70 分钟音频的重抽 + 重扫）。
    wav = target / "analysis.wav"
    if not wav.exists():
        print("提取分析音频……")
        extract_analysis_audio(src, wav)
    # 波形和静默扫描只跟 inactive_* 那组字段有关（对 70 分钟的录音是分钟级开销），
    # 所以按那组字段做键缓存：只扫 VAD 参数时扫一次就够，扫到静默参数就重扫。
    scans: dict[tuple, object] = {}

    def waveform_for(config: AnalysisConfig):
        key = tuple(getattr(config, name) for name in WAVEFORM_FIELDS)
        if key not in scans:
            print("扫描波形与静默……")
            scans[key] = analyze_audio_blocks(wav, config)
        return scans[key]

    duration = probe_duration(src)

    from silero_vad import load_silero_vad

    print("载入 Silero……\n")
    model = load_silero_vad()

    # pydantic 会把字符串按字段类型转好（"0.3" -> 0.3），不用在这儿手工 coerce
    base_config = AnalysisConfig(**overrides)
    best = base_config
    label = "当前默认" if not overrides else "基准 " + ",".join(f"{k}={v}" for k, v in overrides.items())
    base = run_once(best, wav, waveform_for(best), windows, duration, model)
    print(f"{label:<32}误剪 {base.误剪:6.1f}s  残留 {base.残留:7.1f}s  "
          f"切掉 {base.切掉:7.1f}s  {base.段数:4d} 段")
    print(f"  残留构成：{format_residual(base)}\n")

    for number, (field, values) in enumerate(ROUNDS, start=1):
        if wanted_rounds is not None and number not in wanted_rounds:
            continue
        print("=" * 78)
        print(f"第 {number} 轮：{field}")
        print("=" * 78)
        rows = []
        for value in values:
            trial = best.model_copy(update={field: value})
            result = run_once(trial, wav, waveform_for(trial), windows, duration, model)
            mark = "  <- 当前" if getattr(best, field) == value else ""
            print(f"  {field}={value!s:<10}误剪 {result.误剪:6.1f}s  残留 {result.残留:7.1f}s  "
                  f"切掉 {result.切掉:7.1f}s  {result.段数:4d} 段{mark}")
            rows.append((value, result))

        # 约束线锚在基准上，不锚在本轮最小值上。「误剪最小 + 带宽」看着等价，其实
        # 是给「少切」发奖金：切得越少误剪必然越低，那个选项就把下限拉到最低，其余
        # 选项全被判成超标，最后选中一个残留更差、只是切得更少的组合。第 4 轮
        # min_speech_duration_ms 就这么选出了本轮残留最高的一项。
        budget = base.误剪 + CUT_TOLERANCE
        eligible = [(v, r) for v, r in rows if r.误剪 <= budget]
        # 预算内一个都没有，说明 incumbent 自己已越线——那就别动了。
        eligible = eligible or [(v, r) for v, r in rows if getattr(best, field) == v]
        winner_value, winner = min(eligible, key=lambda item: item[1].残留)
        best = best.model_copy(update={field: winner_value})
        print(f"  ➜ 取 {field}={winner_value}（误剪预算 {budget:.1f}s，"
              f"预算内残留最低 {winner.残留:.1f}s）\n")

    print("=" * 78)
    print("最终参数")
    print("=" * 78)
    for field in VAD_FIELDS:
        print(f"  {field} = {getattr(best, field)}")

    # 一轮都没跑成（--rounds= 空）时 best 就是基准，再跑一遍纯属浪费三分钟。
    if best == base_config:
        print("\n  基准即最终参数，没有需要复算的。")
    else:
        final = run_once(best, wav, waveform_for(best), windows, duration, model)
        print(f"\n  基准   误剪 {base.误剪:6.1f}s  残留 {base.残留:7.1f}s  切掉 {base.切掉:7.1f}s")
        print(f"  扫出来 误剪 {final.误剪:6.1f}s  残留 {final.残留:7.1f}s  切掉 {final.切掉:7.1f}s")

    if keep_audio:
        print(f"\n（分析音频保留：{wav}）")
    else:
        wav.unlink(missing_ok=True)
        print("\n（分析音频已删）")


if __name__ == "__main__":
    main()
