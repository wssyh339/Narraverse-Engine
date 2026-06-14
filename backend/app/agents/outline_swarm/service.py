from __future__ import annotations

from typing import Any, Callable

from app.agents.outline_swarm.state import OutlineSwarmState
from app.agents.outline_swarm.swarm import run_outline_swarm_app


def run_outline_swarm(payload: dict[str, Any], progress_callback: Callable[[dict[str, Any]], None] | None = None) -> dict[str, Any]:
    state = OutlineSwarmState(
        project_id=payload["project_id"],
        generation_kind=payload.get("generation_kind", "legacy_plan_chapters"),
        seed=payload.get("seed", {}),
        model=payload.get("model"),
        volume_target=int(payload.get("volume_target", 1)),
        chapter_target=int(payload.get("chapter_target", 10)),
        max_iterations=int(payload.get("max_iterations", 18)),
    )
    return run_outline_swarm_app(state, progress_callback=progress_callback).model_dump(mode="json")
