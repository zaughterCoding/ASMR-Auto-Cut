from pydantic import BaseModel, Field


class AnalysisConfig(BaseModel):
    speech_padding_before: float = Field(default=0.4, ge=0)
    speech_padding_after: float = Field(default=0.4, ge=0)
    inactive_padding: float = Field(default=0.1, ge=0)
    min_keep_duration: float = Field(default=1.0, ge=0)
    merge_gap: float = Field(default=0.2, ge=0)
    inactive_frame_seconds: float = Field(default=1.0, gt=0)

    # --- 静默判据 ---------------------------------------------------------
    #
    # 早先这里只有一个写死的 inactive_rms_threshold = 0.004。那个值有两个毛病，
    # 而且都不报错：
    #
    #   1. 它是一条绝对线，可每条录音的底噪差得远。实测两份素材的 5% 分位差了
    #      13.6 dB，0.004 在 A 里落在第 13.5 百分位、在 B 里落在第 5.1 百分位。
    #      同一条线在两段录音里做的是完全不同的事；底噪再高一点的录音，0.004
    #      会一个区间都找不到，静默检测就悄无声息地什么也不做。
    #   2. 它可能落在内容上。一份电平恒定在 0.0005 的录音（安静的气声内容、
    #      全程没有静音）会被 0.004 整条切光——内容全丢，照样不报错。
    #
    # 现在改成按录音自己算：拿帧 RMS 的低分位当这条录音的底噪，阈值取它的
    # inactive_rms_ratio 倍，再用 floor / headroom 两个安全阀夹住。详见
    # analysis/activity.py 的 resolve_threshold。
    #
    # 想回到固定值就显式传 inactive_rms_threshold，其余四项会被忽略。
    inactive_rms_threshold: float | None = Field(default=None, ge=0)

    #: 拿帧 RMS 的第几百分位当这条录音的底噪。只有当静音占到录音的这么大比例
    #: 时，这个分位才真的等于底噪；静音更少时它会偏高一点，实测偏差可接受。
    inactive_rms_percentile: float = Field(default=0.05, gt=0, lt=1)

    #: 底噪的多少倍算「安静」。1.0 就是「安静 = 处于这条录音最安静的那 5%」。
    inactive_rms_ratio: float = Field(default=1.0, gt=0)

    #: 绝对下限。防止整条录音大半是数字静音时，底噪估计塌到 0、判据失去意义。
    inactive_rms_floor: float = Field(default=0.0002, gt=0)

    #: 安全阀：安静至少要比这条录音的**中位**电平低这么多分贝。写死的常量
    #: 不知道录音有多响，这一条知道——它保证阈值永远不会爬进内容的电平范围。
    #: 实测两份素材在这个值下都是零改动或只收紧一点，没有回归。
    inactive_rms_headroom_db: float = Field(default=25.0, gt=0)

    inactive_min_duration: float = Field(default=20.0, ge=0)

    # --- 人声检测（Silero VAD）------------------------------------------
    #
    # 这几项以前一个都没传，全用 Silero 的默认值。默认值是按「电话/会议录音」
    # 调的：说完一句会停顿几百毫秒，所以 min_silence_duration_ms=100 就够把
    # 两句话分开。ASMR 这边不是这个形态——
    #
    #   * 主播可能一边耳语一边喘气，句间停顿短，默认值会把一句话切成好几段，
    #     而每段都会被当成独立的 talk 区间切掉，中间夹着的 keep 碎片还短到
    #     触发 min_keep_duration 的合并规则，最后连成一大片（实测 111 秒里切出
    #     7 段 1.2~1.7 秒的碎片，而人工听是 4 段 8~10 秒的连续说话）。
    #   * 反过来，慢速耳语的能量低，threshold=0.5 可能整段漏掉（实测残留废话
    #     9.8 分钟，是误剪量的 10 倍）。
    #
    # 这一组就是给上面两个方向留的旋钮，具体取值靠
    # data/labeling/_sweep_vad.py 在已标注的片段上扫出来，不要凭感觉改。
    #: 语音概率高于它才算说话。调低 = 更激进地切（能捞回漏掉的耳语，
    #: 代价是可能误剪）。调高 = 更保守。Silero 默认 0.5。
    vad_threshold: float = Field(default=0.5, gt=0, lt=1)

    #: 短于这个时长的语音段直接丢掉。调大能压掉碎片，但会连同真正的短促
    #: 语气词一起扔掉。注意 Silero 里小于它的段是被**丢弃**而不是合并。
    vad_min_speech_duration_ms: int = Field(default=250, ge=0)

    #: 语音段之间静默超过这个时长才算断开。调大能把被停顿切碎的一句话重新
    #: 连成一段。Silero 默认 100。
    vad_min_silence_duration_ms: int = Field(default=100, ge=0)

    #: 每个语音段两端各补这么长。Silero 默认 30。这一项和上面的
    #: speech_padding_before / after 不是一回事：这里补在「合并成区间之前」，
    #: 影响两段会不会被算成相连；那两个补在「区间已经定了之后」，只改边界。
    vad_speech_pad_ms: int = Field(default=30, ge=0)

    # --- 复核带 -----------------------------------------------------------
    #
    # 概率落在 vad_threshold 附近的那一带，程序判不准：往上一点就切掉、往下一点
    # 就留下，而这两件事的代价差得远——切错了内容回不来，留错了只是成片多一段
    # 废话。所以这一带不交给程序决定，改成**保留 + 高亮**，用户扫一眼就能听。
    #
    # 实现上不额外跑模型：同一串概率切两刀，宽的那一刀减去窄的那一刀就是复核带
    # （见 analysis/speech.py）。窄的那一刀和以前完全一样，所以复核带是纯增量的
    # ——一个切段都不动，历次扫描出来的数字不作废。
    #: 复核带的下沿。概率落在 (它, vad_threshold] 的片段标成 uncertain。
    #: 调低 = 带更宽 = 高亮更多 = 复核更费时但更不容易漏。调到不小于
    #: vad_threshold 就等于关掉复核带。
    vad_uncertain_threshold: float = Field(default=0.2, ge=0, lt=1)


#: 「复核细致程度」-> 复核带下沿。分析前选一档，决定复核时要过多少高亮段——
#: 用户拿复核时间换漏检风险，这是笔说不清算不明的账，所以只给三档：一个拖不到头
#: 也说不清代价的滑块，不如三个说得出后果的选项。
#:
#: 上沿永远是 vad_threshold：「确定是人声」那一头没有商量的余地，复核带只往
#: 「可能是人声」的方向铺。
REVIEW_BANDS: dict[str, float] = {
    "quick": 0.35,
    "standard": 0.2,
    "thorough": 0.05,
}

DEFAULT_REVIEW_BAND = "standard"
