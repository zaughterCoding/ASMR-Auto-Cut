from pathlib import Path

import numpy as np
import soundfile as sf


def load_mono_audio(path: Path) -> tuple[np.ndarray, int]:
    """读成单声道 float32。

    这里直接问 soundfile 要 float32，而不是走 sf.read 的默认 float64 再转。
    长录音的采样点数是百万级的，float64 中间数组意味着多一份两倍大的临时分配，
    而音频分析要的精度只到 float32——分析链路上没有任何一步用得上 float64。
    """
    audio, sample_rate = sf.read(path, always_2d=True, dtype="float32")
    # mean 本来就返回新数组，astype(copy=False) 对已经是 float32 的结果是空操作，
    # 留着是为了把「返回的一定是 float32」写死在函数出口，不依赖上游的 dtype。
    mono = audio.mean(axis=1, dtype=np.float32)
    return mono.astype("float32", copy=False), sample_rate
