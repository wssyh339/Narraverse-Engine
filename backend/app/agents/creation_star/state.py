from __future__ import annotations

from typing import Any

from pydantic import Field

from app.schemas.common import APIModel


class CreationStarState(APIModel):
    project_id: str
    current_step: str
    previous_steps: dict[str, Any] = Field(default_factory=dict)
    candidate_cards: list[dict[str, Any]] = Field(default_factory=list)
    selected_payload: dict[str, Any] = Field(default_factory=dict)
    confirmed: bool = False
