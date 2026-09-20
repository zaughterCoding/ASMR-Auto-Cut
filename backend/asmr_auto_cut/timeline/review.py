"""把复核带标到已经定稿的时间轴上——只加颜色，不动刀。

这是整条流水线的最后一步（见 analysis/pipeline.assemble_project_state），必须排在
`refine_segments` 之后。两个原因，都是硬性的：

  * `refine_segments` 会把保留段整个重建一遍（`build_segments` 里保留段的标签写死
    成 asmr），先标好的 uncertain 会被抹掉；
  * 它的 `short_keep_filter` 会把短于 `min_keep_duration` 的保留段转成切段。复核带
    本来就是碎片状的，先标就会被当成碎渣吃掉——而用户要看的恰恰是这些。
"""

from dataclasses import replace

from asmr_auto_cut.models import TimelineSegment
from asmr_auto_cut.timeline.intervals import RawInterval, subtract_intervals


def _clip_to(intervals: list[RawInterval], start: float, end: float) -> list[RawInterval]:
    """把区间裁到 [start, end) 里，落在外面或裁完为空的丢掉。

    `RawInterval` 是不可变的，所以裁出来的是新对象——这正好，调用方不该看到
    参数被就地改动。
    """
    return [
        replace(item, start=max(item.start, start), end=min(item.end, end))
        for item in intervals
        if item.end > start and item.start < end
    ]


def mark_uncertain(
    segments: list[TimelineSegment],
    uncertain_intervals: list[RawInterval],
) -> list[TimelineSegment]:
    """把与复核带重叠的**保留段**标成 `uncertain`。

    两条不变量：

      * **只碰 action == "keep" 的段。** 切段原样返回，所以「切哪儿」这个决定与
        不开复核带时逐位相同。这是这个功能敢发的前提：它只多了一层颜色，一刀都没
        动过，历次扫描出来的误剪/残留数字因此继续成立。
      * **输出仍是一层平铺。** 保留段被复核带切开之后，两边都是保留段，只是标签
        不同，所以段与段照样首尾相接、无缝无叠（`ProjectState` 要求有序，
        `build_segments` 的调用方也都假设它铺满整条时间轴）。

    复核带横跨一个切段时不做任何事——切段已经注定要被删掉，标不标都没意义，而且
    在切段上标颜色只会让人以为那一刀还可以商量。
    """
    if not uncertain_intervals:
        return segments

    result: list[TimelineSegment] = []
    for segment in segments:
        if segment.action != "keep":
            result.append(segment)
            continue

        holes = _clip_to(uncertain_intervals, segment.start, segment.end)
        if not holes:
            result.append(segment)
            continue

        original = RawInterval(
            start=segment.start,
            end=segment.end,
            label=segment.label,
            confidence=segment.confidence,
            source=segment.source,
        )
        # 复核带与「剩下那些」拼起来就是这个保留段的完整划分——两边的区间各自
        # 有序不重叠，按起点归并即可。切出来的第一片留用原 id，其余加后缀，
        # 这样没被切开的段 id 一个都没变。
        pieces = sorted([*holes, *subtract_intervals([original], holes)], key=lambda item: item.start)
        for index, piece in enumerate(pieces):
            result.append(
                TimelineSegment(
                    id=segment.id if index == 0 else f"{segment.id}_u{index}",
                    start=piece.start,
                    end=piece.end,
                    label=piece.label,
                    action="keep",
                    confidence=piece.confidence,
                    source=piece.source,
                    edited=segment.edited,
                )
            )
    return result
