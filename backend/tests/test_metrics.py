import pytest

from asmr_auto_cut.evaluation.metrics import evaluate_segments
from asmr_auto_cut.models import TimelineSegment


def seg(id, start, end, label, action):
    return TimelineSegment(
        id=id,
        start=start,
        end=end,
        label=label,
        action=action,
        confidence=1.0,
        source="test",
    )


def test_evaluate_segments_reports_asmr_preservation():
    truth = [
        seg("t1", 0, 5, "asmr", "keep"),
        seg("t2", 5, 10, "talk", "cut"),
    ]
    predicted = [
        seg("p1", 0, 4, "asmr", "keep"),
        seg("p2", 4, 10, "talk", "cut"),
    ]
    report = evaluate_segments(truth, predicted, duration=10, frame_seconds=1)
    assert report.asmr_preservation_rate == 0.8
    assert report.unwanted_removal_rate == 1.0


def test_perfect_prediction_scores_one():
    truth = [
        seg("t1", 0, 5, "asmr", "keep"),
        seg("t2", 5, 10, "talk", "cut"),
    ]
    report = evaluate_segments(truth, truth, duration=10, frame_seconds=1)
    assert report.asmr_preservation_rate == 1.0
    assert report.unwanted_removal_rate == 1.0
    assert report.per_class["asmr"].f1 == 1.0
    assert report.per_class["talk"].f1 == 1.0
    # 真值里没有出现的类别不应被算成错误
    assert report.per_class["inactive"].f1 == 1.0


def test_keeping_everything_preserves_asmr_but_removes_nothing():
    truth = [
        seg("t1", 0, 5, "asmr", "keep"),
        seg("t2", 5, 10, "talk", "cut"),
    ]
    predicted = [
        seg("p1", 0, 5, "asmr", "keep"),
        seg("p2", 5, 10, "talk", "keep"),
    ]
    report = evaluate_segments(truth, predicted, duration=10, frame_seconds=1)
    assert report.asmr_preservation_rate == 1.0
    assert report.unwanted_removal_rate == 0.0


def test_per_class_metrics_count_frames_not_seconds():
    # 预测把 talk 的 2s 判成 asmr：asmr 精确率 6/(6+2)=0.75，召回 6/6=1.0
    truth = [
        seg("t1", 0, 6, "asmr", "keep"),
        seg("t2", 6, 10, "talk", "cut"),
    ]
    predicted = [
        seg("p1", 0, 8, "asmr", "keep"),
        seg("p2", 8, 10, "talk", "cut"),
    ]
    report = evaluate_segments(truth, predicted, duration=10, frame_seconds=1)
    assert report.per_class["asmr"].precision == pytest.approx(0.75)
    assert report.per_class["asmr"].recall == pytest.approx(1.0)


def test_uncovered_time_is_treated_as_uncertain_and_cut():
    truth = [seg("t1", 0, 4, "asmr", "keep")]
    report = evaluate_segments(truth, truth, duration=10, frame_seconds=1)
    # 4-10s 没有段落覆盖，按不确定/不保留处理：既不计入 asmr 分母，也不计成切掉了废话
    assert report.asmr_preservation_rate == 1.0
    assert report.unwanted_removal_rate == 1.0
    assert report.per_class["uncertain"].f1 == 1.0
    assert report.per_class["asmr"].recall == 1.0


def test_empty_truth_does_not_divide_by_zero():
    report = evaluate_segments([], [], duration=10, frame_seconds=1)
    assert report.asmr_preservation_rate == 1.0
    assert report.unwanted_removal_rate == 1.0


def test_unsorted_segments_are_ordered_before_sampling():
    truth = [
        seg("t2", 5, 10, "talk", "cut"),
        seg("t1", 0, 5, "asmr", "keep"),
    ]
    report = evaluate_segments(truth, truth, duration=10, frame_seconds=1)
    assert report.asmr_preservation_rate == 1.0
    assert report.per_class["asmr"].f1 == 1.0
