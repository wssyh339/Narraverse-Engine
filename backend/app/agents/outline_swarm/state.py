from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from app.agents.shared.canon_context import CanonContext
from app.agents.shared.trace import AgentTraceEvent
from app.schemas.common import APIModel


class OutlineSwarmState(APIModel):
    project_id: str
    generation_kind: Literal["book_outline", "chapter_outline_batch", "legacy_plan_chapters"] = "legacy_plan_chapters"
    seed: dict[str, Any] = Field(default_factory=dict)
    model: str | None = None
    canon_context: CanonContext | None = None
    story_bible: dict[str, Any] = Field(default_factory=dict)
    characters: list[dict[str, Any]] = Field(default_factory=list)
    story_entities: list[dict[str, Any]] = Field(default_factory=list)
    world_facts: list[dict[str, Any]] = Field(default_factory=list)
    graph_nodes: list[dict[str, Any]] = Field(default_factory=list)
    graph_edges: list[dict[str, Any]] = Field(default_factory=list)
    outline: dict[str, Any] = Field(default_factory=dict)
    volume_outlines: list[dict[str, Any]] = Field(default_factory=list)
    chapter_beats: list[dict[str, Any]] = Field(default_factory=list)
    foreshadowing_items: list[dict[str, Any]] = Field(default_factory=list)
    continuity_issues: list[dict[str, Any]] = Field(default_factory=list)
    completion_tickets: list[dict[str, Any]] = Field(default_factory=list)
    uncertainty_tickets: list[dict[str, Any]] = Field(default_factory=list)
    incomplete_required_entities: list[dict[str, Any]] = Field(default_factory=list)
    active_agent: str = "StoryDirectorAgent"
    agent_trace: list[AgentTraceEvent] = Field(default_factory=list)
    agent_llm_results: dict[str, dict[str, Any]] = Field(default_factory=dict)
    iteration_count: int = 0
    max_iterations: int = 18
    volume_target: int = 1
    chapter_target: int = 10
    status: Literal["running", "passed", "failed", "needs_user_review"] = "running"

    def get(self, key: str, default: Any = None) -> Any:
        """让 Pydantic 状态兼容 langgraph-swarm 的 active_agent router。"""
        return getattr(self, key, default)
