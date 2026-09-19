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
