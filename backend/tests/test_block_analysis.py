import numpy as np
import soundfile as sf

from asmr_auto_cut.analysis.activity import detect_inactive_intervals
from asmr_auto_cut.analysis.block_analysis import analyze_audio_blocks
from asmr_auto_cut.analysis.waveform import build_waveform
from asmr_auto_cut.config import AnalysisConfig


def _write(path, audio, sample_rate):
    # FLOAT 子类型：WAV 默认是 PCM_16，样本会被量化，断言里就混进了有损编码的
    # 误差，分块和整段两边读回来虽然一样，但用例想验的是分块算法本身。
    sf.write(path, audio, sample_rate, subtype="FLOAT")
    return path


def test_block_analysis_matches_full_waveform_on_small_audio(tmp_path):
    path = tmp_path / "audio.wav"
    sample_rate = 10
    audio = np.concatenate([
        np.zeros(10, dtype="float32"),
        np.ones(10, dtype="float32") * 0.5,
    ])
    _write(path, audio, sample_rate)

    result = analyze_audio_blocks(
        path,
        AnalysisConfig(inactive_frame_seconds=1.0, inactive_rms_threshold=0.01, inactive_min_duration=1.0),
        points_per_second=2,
        block_seconds=1.0,
    )
    expected_waveform = build_waveform(audio, sample_rate, points_per_second=2)

    assert [point.model_dump() for point in result.waveform] == [
        point.model_dump() for point in expected_waveform
    ]


def test_block_analysis_matches_full_inactive_detection_on_small_audio(tmp_path):
    path = tmp_path / "audio.wav"
    sample_rate = 10
    audio = np.concatenate([
        np.zeros(30, dtype="float32"),
        np.ones(30, dtype="float32") * 0.5,
    ])
    config = AnalysisConfig(
        inactive_frame_seconds=1.0,
        inactive_rms_threshold=0.01,
        inactive_min_duration=2.0,
    )
    _write(path, audio, sample_rate)

    result = analyze_audio_blocks(path, config, points_per_second=1, block_seconds=1.0)
    expected = detect_inactive_intervals(audio, sample_rate, config)

    assert [(item.start, item.end, item.label) for item in result.inactive_intervals] == [
        (item.start, item.end, item.label) for item in expected
    ]


def test_block_analysis_matches_full_when_block_size_is_not_a_multiple(tmp_path):
    """块长除不尽点位长和帧长时也必须逐点一致。

    这是最容易出错的一种输入：sample_rate=10、points_per_second=3 时点位长是 3，
    而块长是 10，除不尽；inactive_frame_seconds=0.3 时帧长也是 3，同样除不尽。
    每块末尾都会剩 1 个采样点，两个消费者各剩各的，残差不接上的话结果就对不上。
    """
    path = tmp_path / "audio.wav"
    sample_rate = 10
    rng = np.random.default_rng(20260919)
    # 幅度在阈值两侧来回跳，好让帧判决真的经历几次开关，而不只是一段静音
    audio = (rng.random(97, dtype=np.float32) < 0.4).astype("float32") * 0.3
    _write(path, audio, sample_rate)

    config = AnalysisConfig(
        inactive_frame_seconds=0.3,
        inactive_rms_threshold=0.01,
        inactive_min_duration=0.6,
    )
    result = analyze_audio_blocks(path, config, points_per_second=3, block_seconds=1.0)

    expected_waveform = build_waveform(audio, sample_rate, points_per_second=3)
    expected_inactive = detect_inactive_intervals(audio, sample_rate, config)

    assert [point.model_dump() for point in result.waveform] == [
        point.model_dump() for point in expected_waveform
    ]
    assert [(item.start, item.end) for item in result.inactive_intervals] == [
        (item.start, item.end) for item in expected_inactive
    ]
    # 用例本身要有意义：得确认这次真的产生了低活动区间
    assert expected_inactive


def test_trailing_inactive_interval_ends_at_audio_end(tmp_path):
    """一直安静到结尾的区间要收到音频真正的结尾。

    音频 5.5 秒、点位长 1 秒时，最后一个波形点的时间是 5.0——它是那一个点的起始
    时刻，不是音频的结束时刻。拿它当区间收口位置会把尾巴截短 0.5 秒，短到刚好
    卡在 inactive_min_duration 上下时判决就翻了。
    """
    path = tmp_path / "audio.wav"
    sample_rate = 10
    audio = np.zeros(55, dtype="float32")
    _write(path, audio, sample_rate)

    config = AnalysisConfig(
        inactive_frame_seconds=1.0,
        inactive_rms_threshold=0.01,
        inactive_min_duration=5.4,
    )
    result = analyze_audio_blocks(path, config, points_per_second=1, block_seconds=1.0)

    assert [(item.start, item.end) for item in result.inactive_intervals] == [(0.0, 5.5)]
