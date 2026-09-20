"""自己接手的 Silero：切区间的结果要钉死在 golden 上，推理要真的能跑。

这两件事分别防两种静默失败：

  * **切区间**是手抄上游的 100 行。抄错一个 `<` 或一处取整不会报错，只是切得
    稍微不一样——读数是慢慢飘的，等发现时已经不知道从哪一版开始飘了。所以拿
    一组固定的概率序列把结果钉死，同时覆盖三档复核带阈值和几组边界参数。
    golden 值由上游 silero-vad 6.2.2 的 `get_speech_timestamps_from_probs` 产出，
    两边在这组序列上逐位相同。
  * **推理**要真跑一遍模型，否则「权重文件没打进包」这种事只在用户第一次分析时
    才暴露。模型文件是随包走的资源，路径解析错了同样不会在导入期报错。
"""

import numpy as np
import pytest

from asmr_auto_cut.analysis.silero_onnx import (
    CONTEXT_SAMPLES,
    STATE_SHAPE,
    WINDOW_SAMPLES,
    SileroVad,
    model_path,
    speech_timestamps_from_probs,
)

#: 手写的概率序列：有平台、有毛刺、有贴着阈值抖动的段，够长到能落好几刀。
#: 203 个窗 = 103936 个采样点。
GOLDEN_PROBS = (
    [0.01] * 5 + [0.9] * 40 + [0.6] * 3 + [0.05] * 25 + [0.55] * 8 + [0.3] * 6
    + [0.8] * 60 + [0.02] * 10 + [0.45] * 4 + [0.7] * 30 + [0.01] * 12
)
GOLDEN_SAMPLES = len(GOLDEN_PROBS) * WINDOW_SAMPLES

#: (阈值, min_speech_ms, min_silence_ms, speech_pad_ms) -> 上游给出的区间。
#: 前三条是复核带的三档，第四条把三个时长参数全归零（边界），第五条整体偏离默认。
GOLDEN_CASES = [
    ((0.5, 250, 100, 30), [(0.1, 1.6), (2.3, 2.6), (2.8, 4.7), (5.1, 6.1)]),
    ((0.35, 250, 100, 30), [(0.1, 1.6), (2.3, 4.7), (5.0, 6.1)]),
    ((0.05, 250, 100, 30), [(0.1, 6.496)]),
    ((0.5, 0, 0, 0), [(0.2, 1.5), (2.3, 2.6), (2.8, 4.7), (5.2, 6.1)]),
    ((0.7, 400, 500, 150), [(0.0, 1.7), (2.6, 6.496)]),
]


@pytest.mark.parametrize("params, expected", GOLDEN_CASES)
def test_timestamps_match_upstream(params, expected):
    threshold, min_speech, min_silence, pad = params
    assert speech_timestamps_from_probs(
        GOLDEN_PROBS,
        sampling_rate=16000,
        threshold=threshold,
        min_speech_duration_ms=min_speech,
        min_silence_duration_ms=min_silence,
        speech_pad_ms=pad,
        audio_length_samples=GOLDEN_SAMPLES,
    ) == expected


def test_a_gap_shorter_than_min_silence_does_not_cut():
    """静音不够长就不断开——这是 min_silence_duration_ms 存在的全部理由。

    单独钉一条，因为它是「一段连续人声被切成碎片」的唯一防线，而 golden 那组
    序列里这个分支恰好只走到一半。
    """
    probs = [0.9] * 20 + [0.0] * 2 + [0.9] * 20  # 2 窗 = 64ms 的静音

    def cuts(min_silence_ms):
        return speech_timestamps_from_probs(
            probs,
            sampling_rate=16000,
            threshold=0.5,
            min_speech_duration_ms=250,
            min_silence_duration_ms=min_silence_ms,
            speech_pad_ms=0,
            audio_length_samples=len(probs) * WINDOW_SAMPLES,
        )

    # 64ms < 100ms 的静音下限，连成一片
    assert len(cuts(100)) == 1
    # 下限降到 0，同一处静音就该把它断成两段
    assert len(cuts(0)) == 2


def test_a_blip_shorter_than_min_speech_is_dropped():
    """短于人声下限的孤立尖峰不算一段话，否则每个咔哒声都会被切一刀。"""
    probs = [0.0] * 10 + [0.9] * 3 + [0.0] * 30  # 3 窗 = 96ms
    cut = speech_timestamps_from_probs(
        probs,
        sampling_rate=16000,
        threshold=0.5,
        min_speech_duration_ms=250,
        min_silence_duration_ms=100,
        speech_pad_ms=0,
        audio_length_samples=len(probs) * WINDOW_SAMPLES,
    )
    assert cut == []


def test_speech_still_open_at_the_end_is_closed_at_the_audio_length():
    """录音在说话中途断掉时，最后这段没有遇到任何静音，得靠收尾补上。"""
    probs = [0.0] * 10 + [0.9] * 40
    cut = speech_timestamps_from_probs(
        probs,
        sampling_rate=16000,
        threshold=0.5,
        min_speech_duration_ms=250,
        min_silence_duration_ms=100,
        speech_pad_ms=0,
        audio_length_samples=len(probs) * WINDOW_SAMPLES,
    )
    # 起点 10 窗 = 5120 采样点 = 0.32s，但时间戳一路取整到 0.1s（上游的
    # time_resolution=1），所以读出来是 0.3
    assert cut == [(0.3, len(probs) * WINDOW_SAMPLES / 16000)]


def test_the_model_file_ships_with_the_package():
    """权重是随包走的资源。路径解析错了只会在用户第一次分析时炸。

    所以这里真去开一次文件，而不是只 import 一下——importlib.resources 的路径
    在某些安装形态下指向一个不存在的临时位置，光看它返回字符串是看不出来的。
    """
    from pathlib import Path

    path = Path(model_path())
    assert path.is_file()
    assert path.stat().st_size > 1_000_000


def test_the_wrapper_returns_probabilities_in_range():
    """真跑一遍模型：静音上该给低概率，满幅噪声上该给低概率，别的一律在 [0,1]。"""
    model = SileroVad()
    model.reset_states()

    rng = np.random.default_rng(0)
    silent = model(np.zeros(WINDOW_SAMPLES, dtype="float32"))
    noise = model(rng.normal(0, 0.5, WINDOW_SAMPLES).astype("float32"))

    assert 0.0 <= silent <= 1.0
    assert 0.0 <= noise <= 1.0
    assert silent < 0.5, "纯静音不该被判成人声"


def test_reset_states_clears_the_memory():
    """不清状态就是把上一段音频的记忆带进下一段。同样的输入必须给出同样的输出。"""
    model = SileroVad()
    window = np.zeros(WINDOW_SAMPLES, dtype="float32")

    model.reset_states()
    first = model(window)
    model(window)  # 走一窗，状态被改掉
    model.reset_states()
    again = model(window)

    assert first == again


def test_a_window_of_the_wrong_length_is_refused():
    """窗长不对必须立刻报错。默默补零或截断都会让概率整体偏低，且不会报错。"""
    model = SileroVad()
    with pytest.raises(ValueError, match="512"):
        model(np.zeros(WINDOW_SAMPLES - 1, dtype="float32"))


def test_the_wrapper_keeps_no_torch_state():
    """状态必须是 numpy——用 torch 张量存就等于把 torch 又拖回来了。"""
    model = SileroVad()
    assert isinstance(model._state, np.ndarray)
    assert model._state.shape == STATE_SHAPE
    assert isinstance(model._context, np.ndarray)
    assert model._context.shape == (1, CONTEXT_SAMPLES)
