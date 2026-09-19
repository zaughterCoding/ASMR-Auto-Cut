import numpy as np
import soundfile as sf

from asmr_auto_cut.media.audio import load_mono_audio


def test_load_mono_audio_returns_float32(tmp_path):
    path = tmp_path / "audio.wav"
    samples = np.array([[0.2, 0.4], [0.6, 0.8]], dtype="float32")
    # 必须显式写 FLOAT：sf.write 默认按容器挑子类型，WAV 默认是 PCM_16，样本会被
    # 量化成 16 bit。那样这个用例断言的就不只是 dtype 和降混，还捎带上了一次有损
    # 编码的误差，而 np.allclose 的默认容差（rtol=1e-5）刚好卡在量化误差边缘上。
    sf.write(path, samples, samplerate=16000, subtype="FLOAT")

    audio, sample_rate = load_mono_audio(path)

    assert sample_rate == 16000
    assert audio.dtype == np.float32
    assert np.allclose(audio, np.array([0.3, 0.7], dtype="float32"))
