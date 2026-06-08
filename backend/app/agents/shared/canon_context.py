from __future__ import annotations

from typing import Any

from pydantic import Field

from app.schemas.common import APIModel


class CanonContext(APIModel):
    project_id: str
    project: dict[str, Any] = Field(default_factory=dict)
    story_bible: dict[str, Any] = Field(default_factory=dict)
    characters: list[dict[str, Any]] = Field(default_factory=list)
    world_facts: list[dict[str, Any]] = Field(default_factory=list)
    story_entities: list[dict[str, Any]] = Field(default_factory=list)
    graph: dict[str, Any] = Field(default_factory=dict)
    previous_summaries: list[dict[str, Any]] = Field(default_factory=list)
    continuity_issues: list[dict[str, Any]] = Field(default_factory=list)
