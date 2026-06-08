from __future__ import annotations

from typing import Any

from app.agents.creation_star.state import CreationStarState


def build_creation_star_state(project_id: str, current_step: str, previous_steps: dict[str, Any] | None = None) -> CreationStarState:
    return CreationStarState(project_id=project_id, current_step=current_step, previous_steps=previous_steps or {})
