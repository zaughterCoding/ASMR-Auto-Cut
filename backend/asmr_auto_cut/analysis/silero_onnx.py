"""Silero VAD 的 ONNX 运行时——不依赖 torch。

上游 silero-vad 6.2.2 把 torch 写死在依赖里（`torch>=1.12` 加 `torchaudio`），
连 onnx 那条路也不例外：`load_silero_vad(onnx=True)` 返回的 `OnnxWrapper` 只是
把「算」交给了 onnxruntime，状态和 context 仍旧拿 torch 张量存着，模块顶层照样
`import torch`。所以换 onnx 本身省不下任何东西——要真正甩掉那 4.4G 的 torch，
只能自己接手这段推理。

接手的只有两件事，都很小：

  * **逐窗推理**（`SileroVad`）——输入是一个 (1, 64+512) 的窗，模型吐回一个概率
    和一个 (2,1,128) 的新状态。全部用 numpy 存，没有别的东西。
  * **概率切区间**（`speech_timestamps_from_probs`）——纯 Python，上游那份的忠实
    移植，去掉的只有我们永远走不到的最大段长分支（见该函数的说明）。

模型文件 `assets/silero_vad.onnx` 取自 silero-vad 6.2.2 的包数据，与 `.jit` 同源。
实测逐窗概率与 JIT 的最大差为 9.3e-06（float32 累加噪声量级），同阈值下切出的
区间逐位相同——见 docs/verification/0.4.0-onnx-migration.md。
"""

from functools import lru_cache
from importlib import resources

import numpy as np

#: Silero 在 16k 下的窗长（采样点）和 context（上一窗尾巴）长度。两个数都是模型
#: 的硬要求，写死在这里而不是从配置推。
WINDOW_SAMPLES = 512
CONTEXT_SAMPLES = 64

#: 状态张量的形状。LSTM 的 h 和 c 各占一层，128 是隐层宽度。
STATE_SHAPE = (2, 1, 128)


@lru_cache(maxsize=1)
def model_path() -> str:
    """模型文件的位置。走 importlib.resources，装成 wheel 也找得到。"""
    return str(resources.files("asmr_auto_cut").joinpath("assets", "silero_vad.onnx"))


class SileroVad:
    """一个 ONNX 会话，外加它跨窗携带的那点状态。

    状态是模型自己的记忆：`state` 是 LSTM 的 h/c，`context` 是上一窗的尾巴
    （模型看 576 个点，其中前 64 个是上一窗的，这样窗与窗之间才连得上）。
    两样都随 `__call__` 递进，`reset_states` 把它们清零——不清就是把上一段音频
    的记忆带进这一段，所以每趟分析开头必须调一次。
    """

    def __init__(self, path: str | None = None) -> None:
        import onnxruntime

        options = onnxruntime.SessionOptions()
        # 上游同样把这两个线程数钉成 1。VAD 是逐窗的小算子，多线程的调度开销比
        # 算子本身还大；而且这里本来就是「一条流按顺序喂」的形态，没有并行度。
        options.inter_op_num_threads = 1
        options.intra_op_num_threads = 1

        self.session = onnxruntime.InferenceSession(
            path or model_path(),
            providers=["CPUExecutionProvider"],
            sess_options=options,
        )
        # 只支持 16k，所以不做成参数：context 的长度跟着采样率走（16k 是 64 点，
        # 8k 是 32 点），换采样率要改的不止这一个数。分析音频统一抽成 16k，
        # `speech.load_analysis_audio` 在入口处会拦下别的采样率。
        self.sample_rate = np.array(16000, dtype=np.int64)
        self.reset_states()

    def reset_states(self) -> None:
        self._state = np.zeros(STATE_SHAPE, dtype=np.float32)
        self._context = np.zeros((1, CONTEXT_SAMPLES), dtype=np.float32)

    def __call__(self, window: np.ndarray) -> float:
        """喂一窗 512 点的音频，返回它的语音概率。"""
        chunk = np.asarray(window, dtype=np.float32).reshape(1, -1)
        if chunk.shape[1] != WINDOW_SAMPLES:
            raise ValueError(
                f"窗长必须是 {WINDOW_SAMPLES} 点，收到 {chunk.shape[1]}"
            )
        inputs = np.concatenate([self._context, chunk], axis=1)
        probability, self._state = self.session.run(
            None, {"input": inputs, "state": self._state, "sr": self.sample_rate}
        )
        # 这一窗的尾巴就是下一窗的 context。必须在 run 之后取，取的是**含 context
        # 的整条输入**的最后 64 点——那才是模型这一窗真正看到的结尾。
        self._context = inputs[:, -CONTEXT_SAMPLES:]
        return float(np.asarray(probability).reshape(-1)[0])


def speech_timestamps_from_probs(
    speech_probs: list[float],
    sampling_rate: int,
    threshold: float,
    min_speech_duration_ms: int,
    min_silence_duration_ms: int,
    speech_pad_ms: int,
    audio_length_samples: int,
) -> list[tuple[float, float]]:
    """把逐窗语音概率切成 (起, 止) 秒对。

    移植自 silero-vad 6.2.2 的 `get_speech_timestamps_from_probs`，逐行照搬，
    只去掉了一个分支：上游的「单段最长时长」截断（`max_speech_duration_s`）。
    我们不传这个参数，它取默认的 `inf`，`cur_sample - start > max_speech_samples`
    永远为假，那段代码一次都执行不到。真要用它（比如防某个模型在长静音上失控），
    从上游那份拷回来即可，函数签名里没有它的位置。

    另有两处上游的参数固定成我们唯一会用到的取值，因此没有做成入参：
    `return_seconds=True`（调用方要的是秒）、`step=1`（我们没有降采样过）、
    `use_max_poss_sil_at_max_speech=True`（只被上面去掉的分支读）。
    """
    window_size_samples = WINDOW_SAMPLES
    min_speech_samples = sampling_rate * min_speech_duration_ms / 1000
    speech_pad_samples = sampling_rate * speech_pad_ms / 1000
    min_silence_samples = sampling_rate * min_silence_duration_ms / 1000

    # 迟滞下沿：概率掉到这个值以下才算「静音开始了」，比 threshold 低 0.15。
    # 和 threshold 用同一个值会让概率在阈值附近的抖动把一段话切成碎片。
    neg_threshold = max(threshold - 0.15, 0.01)

    triggered = False
    speeches: list[dict] = []
    current_speech: dict = {}
    temp_end = 0  # 疑似静音的起点，攒够 min_silence_samples 才作数

    for index, speech_prob in enumerate(speech_probs):
        cur_sample = window_size_samples * index

        # 说话重新出现 -> 上一段「疑似静音」作废，静音计时从头再来。少了这一句，
        # temp_end 会停在旧位置，后面那段静音就会被量成从旧位置开始的长度。
        if (speech_prob >= threshold) and temp_end:
            temp_end = 0

        if (speech_prob >= threshold) and not triggered:
            triggered = True
            current_speech["start"] = cur_sample
            continue

        if (speech_prob < neg_threshold) and triggered:
            if not temp_end:
                temp_end = cur_sample
            if cur_sample - temp_end < min_silence_samples:
                continue
            # 静音够长，落刀。上沿取 temp_end 而不是 cur_sample：这段静音已经被
            # 判定不要了，刀口应该贴在人声真正结束的地方。
            current_speech["end"] = temp_end
            if (current_speech["end"] - current_speech["start"]) > min_speech_samples:
                speeches.append(current_speech)
            current_speech = {}
            temp_end = 0
            triggered = False
            continue

    # 收尾：录音在说话中途断掉时，最后这段没有遇到任何静音，得在这里补上。
    if current_speech and (audio_length_samples - current_speech["start"]) > min_speech_samples:
        current_speech["end"] = audio_length_samples
        speeches.append(current_speech)

    # 前后各撑开 speech_pad_ms；相邻两段之间如果本来就很近，就各让一半，免得撑开后
    # 互相重叠（重叠会让下游的 subtract_intervals 算出负长度的区间）。
    for index, speech in enumerate(speeches):
        if index == 0:
            speech["start"] = int(max(0, speech["start"] - speech_pad_samples))
        if index != len(speeches) - 1:
            silence_duration = speeches[index + 1]["start"] - speech["end"]
            if silence_duration < 2 * speech_pad_samples:
                speech["end"] += int(silence_duration // 2)
                speeches[index + 1]["start"] = int(
                    max(0, speeches[index + 1]["start"] - silence_duration // 2)
                )
            else:
                speech["end"] = int(
                    min(audio_length_samples, speech["end"] + speech_pad_samples)
                )
                speeches[index + 1]["start"] = int(
                    max(0, speeches[index + 1]["start"] - speech_pad_samples)
                )
        else:
            speech["end"] = int(min(audio_length_samples, speech["end"] + speech_pad_samples))

    audio_length_seconds = audio_length_samples / sampling_rate
    return [
        (
            max(round(speech["start"] / sampling_rate, 1), 0),
            min(round(speech["end"] / sampling_rate, 1), audio_length_seconds),
        )
        for speech in speeches
    ]
