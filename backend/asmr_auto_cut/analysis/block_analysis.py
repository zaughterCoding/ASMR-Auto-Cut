import math
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf

from asmr_auto_cut.analysis.activity import InactiveTracker, frame_rms, frame_size_for
from asmr_auto_cut.analysis.waveform import WaveformPoint, samples_per_point, waveform_point
from asmr_auto_cut.config import AnalysisConfig
from asmr_auto_cut.timeline.intervals import RawInterval


@dataclass(frozen=True)
class AudioBlock:
    start_time: float
    audio: np.ndarray
    sample_rate: int


@dataclass(frozen=True)
class BlockAnalysisResult:
    waveform: list[WaveformPoint]
    inactive_intervals: list[RawInterval]
    sample_rate: int


#: 一次分析最多往进度里报这么多次。块数更多的长录音按比例跳着报。
MAX_PROGRESS_REPORTS = 200


def block_size_for(sample_rate: int, block_seconds: float) -> int:
    """一个块多少采样点。读块和预估块总数必须用同一个长度，所以只留这一份。"""
    return max(1, int(sample_rate * block_seconds))


def iter_audio_blocks(path: Path, block_seconds: float = 30.0) -> Iterator[AudioBlock]:
    """把音频降成单声道、一小块一小块地吐出来，避免整段读进内存。

    长录音动辄几小时，16 kHz 单声道 float32 下是每小时的量级；整段读进来再算波形
    等于同时压着原始音频和派生结果两份大数组。
    """
    with sf.SoundFile(path) as audio_file:
        sample_rate = audio_file.samplerate
        block_size = block_size_for(sample_rate, block_seconds)
        start_sample = 0
        while True:
            block = audio_file.read(block_size, always_2d=True, dtype="float32")
            if block.size == 0:
                break
            # 和 load_mono_audio 用同一套 float32 直读 + float32 累加
            mono = block.mean(axis=1, dtype=np.float32).astype("float32", copy=False)
            yield AudioBlock(
                start_time=start_sample / sample_rate,
                audio=mono,
                sample_rate=sample_rate,
            )
            start_sample += len(mono)


def analyze_audio_blocks(
    path: Path,
    config: AnalysisConfig,
    points_per_second: int = 20,
    block_seconds: float = 30.0,
    progress: Callable[[int, int], None] | None = None,
) -> BlockAnalysisResult:
    """流式算出波形和低活动区间，结果与整段一次性计算逐点一致。

    等价性不是顺手得的，是刻意维持的：分块只该改变内存占用，不该改变切点。切点
    差半个帧都可能让导出的成片多切或少切一小段，而这种偏差在界面上根本看不出来。
    """
    info = sf.info(path)
    sample_rate = info.samplerate
    step = samples_per_point(sample_rate, points_per_second)
    frame_size = frame_size_for(sample_rate, config.inactive_frame_seconds)
    tracker = InactiveTracker(config)

    waveform: list[WaveformPoint] = []
    # 波形点和 RMS 帧按各自的单位切同一股样本流，而块边界很少能同时整除这两个
    # 单位——16000 Hz 下 800 和 16000 都能整除 480000 只是巧合，22050 Hz 的点长是
    # 1102，就除不尽 661500。所以两个消费者各自留一段跨块残余，跨块拼回来，
    # 否则每块尾部都会多出半个点、半个帧。
    wave_carry = np.zeros(0, dtype="float32")
    frame_carry = np.zeros(0, dtype="float32")
    wave_start = 0  # wave_carry[0] 在整段音频里的采样下标
    frame_start = 0
    total_samples = 0

    # 块总数从头信息就能算出来，不用先跑一遍。报数按最长 200 次封顶，否则十小时
    # 的录音会往进度管道里灌几千条 JSON，每条都要过一次进程间通信。
    block_size = block_size_for(sample_rate, block_seconds)
    blocks_total = max(1, math.ceil(info.frames / block_size))
    report_every = max(1, blocks_total // MAX_PROGRESS_REPORTS)
    blocks_done = 0

    for block in iter_audio_blocks(path, block_seconds=block_seconds):
        total_samples += len(block.audio)
        blocks_done += 1
        if progress is not None and (blocks_done % report_every == 0 or blocks_done == blocks_total):
            progress(min(blocks_done, blocks_total), blocks_total)

        # 残余为空时直接拿块本身算，省掉一次整块拷贝。默认参数下每块都会走这条
        # 路；两条路都只是读，没有谁改过这块内存，共用是安全的。
        wave_carry = np.concatenate((wave_carry, block.audio)) if wave_carry.size else block.audio
        offset = 0
        while len(wave_carry) - offset >= step:
            chunk = wave_carry[offset : offset + step]
            waveform.append(waveform_point(chunk, (wave_start + offset) / sample_rate))
            offset += step
        wave_carry = wave_carry[offset:]
        wave_start += offset

        frame_carry = np.concatenate((frame_carry, block.audio)) if frame_carry.size else block.audio
        offset = 0
        while len(frame_carry) - offset >= frame_size:
            chunk = frame_carry[offset : offset + frame_size]
            tracker.feed(frame_rms(chunk), (frame_start + offset) / sample_rate)
            offset += frame_size
        frame_carry = frame_carry[offset:]
        frame_start += offset

    # 收尾，和整段分析一样：波形最后不足一个点长的部分照样出一个点，帧的最后
    # 不足一帧的部分照样算一帧。一直安静到结尾的区间要在这里才收口，而且收口
    # 用的是音频真正的结束时刻，不是最后一个波形点的时间——后者比真实结尾早，
    # 会把尾部静音段截短，短到刚好卡在 inactive_min_duration 上下时结果就翻了。
    if wave_carry.size:
        waveform.append(waveform_point(wave_carry, wave_start / sample_rate))
    if frame_carry.size:
        tracker.feed(frame_rms(frame_carry), frame_start / sample_rate)

    total_duration = total_samples / sample_rate if sample_rate > 0 else 0.0
    return BlockAnalysisResult(
        waveform=waveform,
        inactive_intervals=tracker.finish(total_duration),
        sample_rate=sample_rate,
    )
