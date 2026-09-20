"""把两个检测器拆开单独计价：误剪和残留各是谁挣来的。

落盘的 `segments.json` 里切段带 label（`talk` / `inactive`），看上去能按 label 反推
出「只用 inactive 会怎样」。那是反推，不是真跑，两个理由：

  1. `refine_segments` 的 `short_keep_filter` 也会吐 `inactive` 标签的切段，和自己
     检出来的混在同一个 label 里，分不开；
  2. `segments.json` 存的是 refine **跑过之后**的结果，拿它再 refine 一遍 padding
     会叠第二次（见 `_whisper_segments.py` 里那个 control 组）。

所以这里真跑：同一段音频、同一份标注、同一套后处理，只换喂给
`assemble_project_state` 的区间表。四个变体：

  不切         空表。误剪必然 0、残留必然是天窗。它是标尺，不是方案。
  只 speech    只有 Silero VAD。
  只 inactive  只有低活动检测。
  基准         speech + inactive，也就是现在的默认行为。

两种配置各跑一遍：当前默认（自适应静默阈值）和 v0.2.0（`inactive_rms_threshold`
= 0.004 定值）。「拆开计价」和「新旧对照」一次拿到，不用跑两趟。

**speech 只算一次**：`detect_speech_intervals` 只读 `vad_*` 那组字段，而这两个配置
在那组上逐字相同（补丁只动 `inactive_rms_threshold`）。这一点由下面的断言守住，
不是靠人记着。

得分怎么读：这套标注窗口是按**模型的判断**分层抽的（keep 60 / talk 20 / inactive
20），不是按时间抽的，所以秒数的**绝对量不代表原片占比**，只能横向比。纵向比之前
先看「不切」那一行——它就是这套样本里「该切」的总量，其余各行的残留都要对着它读。

打分口径逐字复用 `_sweep_vad.py`——同一套窗口、同一个 `score()`、同一个
`CUT_TOLERANCE`。不另抄一份，免得两处口径各自漂移。

用法：python _ablate_detectors.py [素材名 ...]     不给就跑登记表里全部
      python _ablate_detectors.py --keep-audio    留着 analysis.wav
"""

import sys
from pathlib import Path

for stream in (sys.stdout, sys.stderr):
    stream.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
# 本文件在 data/labeling/_tools/ 下，往上三层是仓库根
sys.path.insert(0, str(HERE.parents[2] / "backend"))

from _materials import load, materials, project_dir  # noqa: E402
from _sweep_vad import (  # noqa: E402
    WAVEFORM_FIELDS,
    Score,
    format_residual,
    format_score,
    load_windows,
    score,
)
from asmr_auto_cut.analysis.block_analysis import analyze_audio_blocks  # noqa: E402
from asmr_auto_cut.analysis.pipeline import assemble_project_state  # noqa: E402
from asmr_auto_cut.analysis.speech import detect_speech_intervals  # noqa: E402
from asmr_auto_cut.config import AnalysisConfig  # noqa: E402
from asmr_auto_cut.media.ffmpeg import extract_analysis_audio, probe_duration  # noqa: E402

#: 变体名 -> 这个变体喂哪几个区间表。`不切` 喂两个空表，是标尺不是方案。
VARIANTS = [
    ("不切", (False, False)),
    ("只 speech", (True, False)),
    ("只 inactive", (False, True)),
    ("基准", (True, True)),
]

#: 要对照的配置。v0.2.0 的静默阈值是定值，HEAD 是自适应百分位——两者只差这一处。
CONFIGS = [
    ("当前默认", {}),
    ("v0.2.0", {"inactive_rms_threshold": 0.004}),
]


def check_configs_share_vad() -> None:
    """守住「speech 只算一次」这个前提：两个配置只能在波形那组字段上有差。

    以后谁改了 v0.2.0 的补丁、或者不小心动了 vad_* 的默认值，这里会当场炸，
    而不是安静地拿一份错的 speech 区间去算第二个配置。
    """
    plain = AnalysisConfig()
    patched = AnalysisConfig(**CONFIGS[1][1])
    diff = {name for name in AnalysisConfig.model_fields if getattr(plain, name) != getattr(patched, name)}
    if not diff <= set(WAVEFORM_FIELDS):
        raise SystemExit(
            f"v0.2.0 补丁改到了波形以外的字段：{sorted(diff - set(WAVEFORM_FIELDS))}。"
            "speech 区间不能再共用一次，得按配置各算一遍。"
        )


def ablate(material: dict, wav: Path, duration: float, model) -> None:
    windows = load_windows(material["out"])
    if not windows:
        print(f"{material['title']}：没有可用的标注，跳过")
        return
    kept = sum(1 for w in windows if w.truth == "asmr")
    print()
    print("=" * 78)
    print(f"{material['title']}   标注窗口 {len(windows)} 个"
          f"（该留 {kept}，该切 {len(windows) - kept}）   "
          f"样本合计 {sum(w.duration for w in windows):.0f} 秒")
    print("=" * 78)

    # speech 只读 vad_* 那组字段，两个配置在那组上逐字相同（check_configs_share_vad
    # 守着这条），所以算一遍就够。
    print("检测人声……")
    speech = detect_speech_intervals(wav, AnalysisConfig(), model=model)

    for config_name, overrides in CONFIGS:
        config = AnalysisConfig(**overrides)
        print()
        print(f"  配置：{config_name}"
              + (f"（{', '.join(f'{k}={v}' for k, v in overrides.items())}）" if overrides else ""))
        # 波形与静默扫描是分钟级开销，一个配置只扫一次，四个变体共用。放在变体循环
        # 里会让「只 inactive」和「基准」各扫一遍，白花一倍时间。
        print("    扫描波形与静默……")
        inactive = analyze_audio_blocks(wav, config).inactive_intervals
        rows: dict[str, Score] = {}
        for name, (use_speech, use_inactive) in VARIANTS:
            state = assemble_project_state(
                project_id="ablate",
                source_path="ablate",
                duration=duration,
                speech_intervals=speech if use_speech else [],
                inactive_intervals=inactive if use_inactive else [],
                config=config,
            )
            result = score(state.segments, windows)
            rows[name] = result
            print(f"    {name:<12}{format_score(result)}")
            print(f"    {'':<12}残留构成：{format_residual(result)}")

        # 不切是标尺，它的两个数是被构造出来的、不是测出来的：区间表为空 -> 没有
        # 切段 -> 误剪必然 0、切掉必然 0。不为 0 说明打分函数或区间传递坏了。
        # 这个自检值钱的地方在于：前面所有变体的秒数都建立在同一套打分上，
        # 它一错，整张表都跟着错，而且错得看不出来（数字都还是「合理」的量级）。
        # 用容差不用等号：真出错时偏差是「秒」量级，1e-6 挡得住；而浮点尘埃
        # （见 score() 里那段关于负零的注释）不该把整张表判死。
        blank = rows["不切"]
        if abs(blank.误剪) > 1e-6 or abs(blank.切掉) > 1e-6:
            raise SystemExit(
                f"自检没过：「不切」应当误剪 0 / 切掉 0，实测 "
                f"误剪 {blank.误剪:.1f}s / 切掉 {blank.切掉:.1f}s。打分或区间传递有问题，"
                "上面整张表都不可信。"
            )

        ceiling = blank.残留
        print()
        print(f"    相对「不切」（残留天窗 {ceiling:.1f}s）各变体消掉多少：")
        for name in ("只 speech", "只 inactive", "基准"):
            print(f"      {name:<12}{ceiling - rows[name].残留:7.1f}s")
        # 两个单独消掉的量之和，未必等于合起来消掉的量：同一段音频被两个检测器同时
        # 判切时只算一次，多出来的那部分就是它们重叠的秒数。差为负说明「单独跑能切掉、
        # 合起来反而切不掉」——那只可能来自后处理（merge_gap 把短切段并进了 keep 段
        # 之类），是个真问题，不该被这行字糊过去，所以只报数不定性。
        overlap = (ceiling - rows["只 speech"].残留) + (ceiling - rows["只 inactive"].残留) - (
            ceiling - rows["基准"].残留
        )
        print(f"      两个单独之和 {overlap:+.1f}s 相对基准 —— 正数 = 重叠（同时判切，"
              f"只算了一次），负数 = 合起来反而切得更少")


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    keep_audio = "--keep-audio" in sys.argv

    check_configs_share_vad()

    names = args or sorted(materials())
    from asmr_auto_cut.analysis.silero_onnx import SileroVad

    for name in names:
        _, material = load(name)
        target = project_dir(material)
        target.mkdir(parents=True, exist_ok=True)
        # 分析音频留在项目目录里，不落 C 盘；抽一次两个配置共用。
        wav = target / "analysis.wav"
        if not wav.exists():
            print(f"\n提取分析音频：{material['title']}……")
            extract_analysis_audio(material["src"], wav)
        duration = probe_duration(material["src"])

        print("\n载入 Silero……")
        model = SileroVad()
        ablate(material, wav, duration, model)

        if not keep_audio:
            wav.unlink(missing_ok=True)

    if not keep_audio:
        print("\n（分析音频已删；--keep-audio 可留着省一次重抽）")


if __name__ == "__main__":
    main()
