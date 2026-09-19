from pathlib import Path

import numpy as np
import soundfile as sf


def load_mono_audio(path: Path) -> tuple[np.ndarray, int]:
    audio, sample_rate = sf.read(path, always_2d=True)
    mono = audio.mean(axis=1).astype("float32")
    return mono, sample_rate
