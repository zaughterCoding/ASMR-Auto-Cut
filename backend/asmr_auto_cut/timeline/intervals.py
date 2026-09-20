from dataclasses import dataclass, replace

from asmr_auto_cut.models import SegmentLabel, TimelineSegment


@dataclass(frozen=True)
class RawInterval:
    start: float
    end: float
    label: SegmentLabel
    confidence: float
    source: str


def merge_cut_intervals(
    intervals: list[RawInterval],
    merge_gap: float = 0.2,
) -> list[RawInterval]:
    """合并切段，但**不跨标签合并**。

    只按时间合并的话，一段 talk 和一段 inactive 挨得够近就会并成一段，而合并后
    只能挂一个标签（先开始的那个说了算）。结果是**一整段 talk 被显示成灰色静默**
    ——用户看到的是「识别为静默、已自动去掉」，而那里其实有说话，且没人会去复核它。
    标签挂错方向的代价是不对称的，所以这里按标签分开。

    两条规则：
      * 标签相同且间隙 <= merge_gap 才合并；
      * 标签不同但**真重叠**时必须消解——时间轴是一层平铺，重叠的段会画在彼此上面。
        消解方式是裁掉重叠部分：后一段让位给前一段。**切的总量一秒不变**，两边的
        标签各自保住。完全落在前一段里面的直接丢弃，同样不改变总量。

    标签不同、只是挨得近的情况不再合并，中间会留一个很短的保留段；那个短段随后
    由 short_keep_filter 按上下文认领（见 refine._absorbed_label），最终仍然并进
    相邻的切段里，只是并进哪一个由两边谁更长决定。
    """
    ordered = sorted(intervals, key=lambda item: (item.start, item.end))
    if not ordered:
        return []

    merged: list[RawInterval] = [ordered[0]]
    for current in ordered[1:]:
        previous = merged[-1]
        if current.start < previous.end:
            if current.end <= previous.end:
                continue
            current = replace(current, start=previous.end)
        if current.label == previous.label and current.start <= previous.end + merge_gap:
            merged[-1] = RawInterval(
                start=previous.start,
                end=max(previous.end, current.end),
                label=previous.label,
                confidence=max(previous.confidence, current.confidence),
                source=f"{previous.source}+{current.source}",
            )
        else:
            merged.append(current)
    return merged


def subtract_intervals(
    intervals: list[RawInterval],
    holes: list[RawInterval],
) -> list[RawInterval]:
    """从 intervals 里挖掉 holes 盖住的部分，剩下几段就返回几段，标签原样带走。

    用途是算复核带：宽阈值（低）跑出来的「可能是人声」减去窄阈值（高）跑出来的
    「确定是人声」，剩下的就是模型自己拿不准的那一段。两个阈值只是同一串概率的
    两种切法，所以结果必然落在宽的那一份里——但这里不假设包含关系，真做减法，
    免得哪天某个阈值组合切出不是子集的形状（`neg_threshold` 跟着阈值走，
    两个阈值的迟滞宽度其实不一样）。

    要求两个入参**各自有序且不重叠**。这是两个生产者的实际输出：Silero 的区间天然
    有序不重叠；uncertain 本身也是这么减出来的。
    """
    if not holes:
        return list(intervals)

    result: list[RawInterval] = []
    index = 0
    for item in intervals:
        cursor = item.start
        # 已经结束在前面的洞用不上了，跳过（洞有序，所以跳过的不会再用到）。
        while index < len(holes) and holes[index].end <= cursor:
            index += 1
        probe = index
        while probe < len(holes) and holes[probe].start < item.end:
            hole = holes[probe]
            if hole.start > cursor:
                result.append(replace(item, start=cursor, end=hole.start))
            cursor = max(cursor, hole.end)
            probe += 1
        if cursor < item.end:
            result.append(replace(item, start=cursor, end=item.end))
    return result


def build_segments(duration: float, cut_intervals: list[RawInterval]) -> list[TimelineSegment]:
    segments: list[TimelineSegment] = []
    cursor = 0.0
    counter = 1
    for interval in cut_intervals:
        start = max(0.0, min(duration, interval.start))
        end = max(0.0, min(duration, interval.end))
        if start > cursor:
            segments.append(
                TimelineSegment(
                    id=f"seg_{counter:06d}",
                    start=cursor,
                    end=start,
                    label="asmr",
                    action="keep",
                    confidence=1.0,
                    source="rule_merge",
                )
            )
            counter += 1
        if end > start:
            segments.append(
                TimelineSegment(
                    id=f"seg_{counter:06d}",
                    start=start,
                    end=end,
                    label=interval.label,
                    action="cut",
                    confidence=interval.confidence,
                    source=interval.source,
                )
            )
            counter += 1
            cursor = end
    if cursor < duration:
        segments.append(
            TimelineSegment(
                id=f"seg_{counter:06d}",
                start=cursor,
                end=duration,
                label="asmr",
                action="keep",
                confidence=1.0,
                source="rule_merge",
            )
        )
    return segments
