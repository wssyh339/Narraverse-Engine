from __future__ import annotations

from typing import Any

from app.agents.outline_swarm.state import OutlineSwarmState
from app.agents.outline_swarm.swarm import run_outline_swarm_app


def run_outline_swarm(payload: dict[str, Any]) -> dict[str, Any]:
    state = OutlineSwarmState(
        project_id=payload["project_id"],
        seed=payload.get("seed", {}),
        model=payload.get("model"),
        volume_target=int(payload.get("volume_target", 1)),
        chapter_target=int(payload.get("chapter_target", 10)),
        max_iterations=int(payload.get("max_iterations", 18)),
    )
    return run_outline_swarm_app(state).model_dump(mode="json")
