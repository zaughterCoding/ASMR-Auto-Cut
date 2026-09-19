import json
from pathlib import Path

from asmr_auto_cut.models import ProjectState


def save_project_state(path: Path, state: ProjectState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(state.model_dump(), indent=2),
        encoding="utf-8",
    )


def load_project_state(path: Path, validate_source_exists: bool = False) -> ProjectState:
    state = ProjectState.model_validate_json(path.read_text(encoding="utf-8"))
    if validate_source_exists and not state.source.resolved_path.exists():
        raise FileNotFoundError(f"Source file does not exist: {state.source.path}")
    return state
