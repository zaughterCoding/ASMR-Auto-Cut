import io
import json

from asmr_auto_cut.progress import ProgressEvent, ResultEvent, emit_json_event


def test_progress_event_serializes_with_type_field():
    stream = io.StringIO()
    emit_json_event(
        ProgressEvent(
            operation="analyze",
            phase="detect_speech",
            message="正在检测人声",
            current=5,
            total=8,
        ),
        stream=stream,
    )
    payload = json.loads(stream.getvalue())
    assert payload["type"] == "progress"
    assert payload["operation"] == "analyze"
    assert payload["percent"] == 62.5


def test_result_event_serializes_project_path():
    stream = io.StringIO()
    emit_json_event(
        ResultEvent(operation="analyze", project_path="data/projects/demo/project.json"),
        stream=stream,
    )
    payload = json.loads(stream.getvalue())
    assert payload == {
        "type": "result",
        "operation": "analyze",
        "project_path": "data/projects/demo/project.json",
        "output_path": None,
    }
