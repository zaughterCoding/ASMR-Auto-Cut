from bisect import bisect_right
from typing import Literal

from pydantic import BaseModel

from asmr_auto_cut.models import SegmentAction, SegmentLabel, TimelineSegment

#: 时间轴没覆盖到的时间按最保守的方式处理：标签不确定，且不保留。
GAP_FRAME = ("uncertain", "cut")

LABELS: list[SegmentLabel] = ["asmr", "talk", "inactive", "uncertain"]
UNWANTED_LABELS: set[str] = {"talk", "inactive"}


class TimelineFrame(BaseModel):
    label: SegmentLabel
    action: SegmentAction


class ClassMetrics(BaseModel):
    precision: float
    recall: float
    f1: float


class EvaluationReport(BaseModel):
    asmr_preservation_rate: float
    unwanted_removal_rate: float
    per_class: dict[SegmentLabel, ClassMetrics]


def _frames(
    segments: list[TimelineSegment],
    duration: float,
    frame_seconds: float,
) -> list[TimelineFrame]:
    """把时间轴按固定步长抽样成逐帧序列。

    段落必须按 start 排序且互不重叠——ProjectState 的校验和编辑界面都保证了这一点。
    排序在这里再兜一次底，这样二分查找定位每帧所属段落是安全的，整体是
    O(帧数 · log 段落数)，不会随录音变长退化成逐帧扫全部段落。
    """
    if frame_seconds <= 0:
        raise ValueError("frame_seconds must be positive")

    ordered = sorted(segments, key=lambda segment: segment.start)
    starts = [segment.start for segment in ordered]
    label, action = GAP_FRAME

    frames: list[TimelineFrame] = []
    for index in range(int(duration / frame_seconds)):
        time = index * frame_seconds
        position = bisect_right(starts, time) - 1
        if position >= 0 and time < ordered[position].end:
            segment = ordered[position]
            frames.append(TimelineFrame(label=segment.label, action=segment.action))
        else:
            frames.append(TimelineFrame(label=label, action=action))
    return frames


def _class_metrics(
    label: SegmentLabel,
    truth: list[TimelineFrame],
    predicted: list[TimelineFrame],
) -> ClassMetrics:
    true_positive = false_positive = false_negative = 0
    for actual, guess in zip(truth, predicted, strict=True):
        if actual.label == label and guess.label == label:
            true_positive += 1
        elif guess.label == label:
            false_positive += 1
        elif actual.label == label:
            false_negative += 1

    precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else 1.0
    recall = true_positive / (true_positive + false_negative) if true_positive + false_negative else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return ClassMetrics(precision=precision, recall=recall, f1=f1)


def evaluate_segments(
    truth: list[TimelineSegment],
    predicted: list[TimelineSegment],
    duration: float,
    frame_seconds: float = 1.0,
) -> EvaluationReport:
    """把两份时间轴逐帧比对，给出保留率与逐类指标。

    asmr_preservation_rate 是「真实为 asmr 的时间里，被预测判为保留的比例」，
    unwanted_removal_rate 是「真实为 talk/inactive 的时间里，被预测切掉的比例」——
    这两个才是这个工具真正关心的：别把 ASMR 剪掉，也别把废话留下。
    """
    truth_frames = _frames(truth, duration, frame_seconds)
    predicted_frames = _frames(predicted, duration, frame_seconds)

    asmr_total = asmr_kept = 0
    unwanted_total = unwanted_removed = 0
    for actual, guess in zip(truth_frames, predicted_frames, strict=True):
        if actual.label == "asmr":
            asmr_total += 1
            if guess.action == "keep":
                asmr_kept += 1
        elif actual.label in UNWANTED_LABELS:
            unwanted_total += 1
            if guess.action == "cut":
                unwanted_removed += 1

    return EvaluationReport(
        asmr_preservation_rate=asmr_kept / asmr_total if asmr_total else 1.0,
        unwanted_removal_rate=unwanted_removed / unwanted_total if unwanted_total else 1.0,
        per_class={
            label: _class_metrics(label, truth_frames, predicted_frames)
            for label in LABELS
        },
    )
