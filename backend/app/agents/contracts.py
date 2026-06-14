from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class NovelStudioState(BaseModel):
    project_id: str = ""
    title: str = ""
    genre: str = ""
    target_words: int = 0
    target_chapters: int = 0
    current_volume: int = 1
    current_chapter: int = 1
    target_reader: str = ""
    premise: str = ""
    style_guide: str = ""
    initial_idea: str = ""
    world_setting: str = ""
    core_conflict_system: dict[str, Any] = Field(default_factory=dict)
    novel_constitution: dict[str, Any] = Field(default_factory=dict)
    constitution_review: dict[str, Any] = Field(default_factory=dict)
    macro_outline: dict[str, Any] = Field(default_factory=dict)
    ending_backcast: dict[str, Any] = Field(default_factory=dict)
    volume_outline: dict[str, Any] = Field(default_factory=dict)
    rolling_chapter_outline: list[dict[str, Any]] = Field(default_factory=list)
    story_bible: dict[str, Any] = Field(default_factory=dict)
    characters: list[dict[str, Any]] = Field(default_factory=list)
    outline: list[dict[str, Any]] = Field(default_factory=list)
    current_chapter_outline: dict[str, Any] = Field(default_factory=dict)
    chapter_card: dict[str, Any] = Field(default_factory=dict)
    scene_outline: dict[str, Any] = Field(default_factory=dict)
    plot_draft: str = ""
    dialogue_draft: str = ""
    environment_draft: str = ""
    integrated_draft: str = ""
    review_notes: list[dict[str, Any]] = Field(default_factory=list)
    fact_check_report: dict[str, Any] = Field(default_factory=dict)
    quality_gate: dict[str, Any] = Field(default_factory=dict)
    revision_count: int = 0
    max_revisions: int = 1
    style_polished_text: str = ""
    final_chapter_text: str = ""
    completed_chapters: list[dict[str, Any]] = Field(default_factory=list)
    user_feedback_history: list[dict[str, Any]] = Field(default_factory=list)
    agent_prompt_configs: dict[str, str] = Field(default_factory=dict)
    agent_model_configs: dict[str, str] = Field(default_factory=dict)
    foreshadowing_list: list[dict[str, Any]] = Field(default_factory=list)
    raw_worldview: str = ""
    market_position: dict[str, Any] = Field(default_factory=dict)
    world_bible: dict[str, Any] = Field(default_factory=dict)
    protagonist_arcs: list[dict[str, Any]] = Field(default_factory=list)
    faction_conflicts: dict[str, Any] = Field(default_factory=dict)
    power_progression: dict[str, Any] = Field(default_factory=dict)
    full_structure: dict[str, Any] = Field(default_factory=dict)
    volumes: list[dict[str, Any]] = Field(default_factory=list)
    beat_sheets: list[dict[str, Any]] = Field(default_factory=list)
    foreshadowing_ledger: list[dict[str, Any]] = Field(default_factory=list)
    audit_reports: list[dict[str, Any]] = Field(default_factory=list)
    revision_history: list[dict[str, Any]] = Field(default_factory=list)
    knowledge_graph: dict[str, Any] = Field(default_factory=dict)
    graph_nodes: list[dict[str, Any]] = Field(default_factory=list)
    graph_edges: list[dict[str, Any]] = Field(default_factory=list)
    world_facts: list[dict[str, Any]] = Field(default_factory=list)
    story_entities: list[dict[str, Any]] = Field(default_factory=list)
    continuity_issues: list[dict[str, Any]] = Field(default_factory=list)
    version_history: list[dict[str, Any]] = Field(default_factory=list)
    chapter_summary: str = ""
    narrative_ledger: dict[str, Any] = Field(default_factory=dict)
    timeline: list[dict[str, Any]] = Field(default_factory=list)
    health_check_report: dict[str, Any] = Field(default_factory=dict)
    context_summary: str = ""
    canon_context: dict[str, Any] = Field(default_factory=dict)
    candidate_canon_updates: dict[str, Any] = Field(default_factory=dict)
    canon_updates: dict[str, Any] = Field(default_factory=dict)
    job_id: str = ""
    requested_model: str | None = None
    agent_llm_results: dict[str, dict[str, Any]] = Field(default_factory=dict)
    current_agent: str = ""
    current_stage: str = "S0_PROJECT_INIT"
    version: str = "outline-v1"
    progress: float = 0
    errors: list[dict[str, Any]] = Field(default_factory=list)


class AgentSpec(BaseModel):
    name: str
    role: str
    prompt: str
    order: int
