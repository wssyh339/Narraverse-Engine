from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.agents.canon_workflow import CanonWorkflow
from app.schemas.canon import CanonRunRequest, CanonRunResult
from app.storage.canon_store import CanonStore


DEFAULT_CANON_OUTPUT_DIR = Path("outputs")


def run_canon_workflow(request: CanonRunRequest, *, base_dir: Path | str = DEFAULT_CANON_OUTPUT_DIR) -> CanonRunResult:
    return CanonWorkflow(request, base_dir=base_dir).run()


def run_canon_from_file(input_path: Path, output_path: Path) -> CanonRunResult:
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    request = CanonRunRequest(**payload)
    result = run_canon_workflow(request, base_dir=output_path.parent)
    output_path.write_text(result.final_outline, encoding="utf-8")
    store_path = Path(result.canon_store_path)
    target_store = output_path.parent / "canon_store.json"
    if store_path.exists() and store_path != target_store:
        target_store.write_text(store_path.read_text(encoding="utf-8"), encoding="utf-8")
    return result.model_copy(update={"final_outline_path": str(output_path), "canon_store_path": str(target_store)})


def get_canon_store(project_id: str, *, base_dir: Path | str = DEFAULT_CANON_OUTPUT_DIR) -> dict[str, Any]:
    return CanonStore(project_id=project_id, base_dir=base_dir).load()


def get_final_outline(project_id: str, *, base_dir: Path | str = DEFAULT_CANON_OUTPUT_DIR) -> dict[str, str]:
    store = CanonStore(project_id=project_id, base_dir=base_dir)
    path = store.project_dir / "final_outline.md"
    return {"path": str(path), "markdown": path.read_text(encoding="utf-8") if path.exists() else ""}
