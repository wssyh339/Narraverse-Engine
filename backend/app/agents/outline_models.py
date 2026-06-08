from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class OutlineBaseModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class ProjectConfig(OutlineBaseModel):
    project_name: str
    genre: str
    tone: str
    target_words: int = 1000000
    target_volumes: int = 10
    chapters_per_volume: int = 50
    words_per_chapter: int = 2000
    must_keep_elements: list[str] = Field(default_factory=list)
    forbidden_elements: list[str] = Field(default_factory=list)


class StoryKernel(OutlineBaseModel):
    one_sentence_story: str = ""
    core_story: str | None = None
    protagonist_desire: str | None = None
    core_conflict: str | None = None
    failure_cost: str | None = None
    long_term_engines: list[str] = Field(default_factory=list)
    ending_directions: list[str] = Field(default_factory=list)
    suitability_score: float | None = None


class WorldBible(OutlineBaseModel):
    world_summary: str | None = None
    base_rules: list[str] = Field(default_factory=list)
    power_system: dict[str, Any] = Field(default_factory=dict)
    social_structure: dict[str, Any] = Field(default_factory=dict)
    factions: list[dict[str, Any]] = Field(default_factory=list)
    resources: list[dict[str, Any]] = Field(default_factory=list)
    map_layers: list[str] = Field(default_factory=list)
    historical_secrets: list[str] = Field(default_factory=list)
    final_secret: str | None = None
    forbidden_changes: list[str] = Field(default_factory=list)


class CharacterProfile(OutlineBaseModel):
    name: str
    initial_identity: str
    faction: str | None = None
    first_volume: int | None = None
    surface_goal: str | None = None
    deep_desire: str | None = None
    secret: str | None = None
    relation_to_protagonist_start: str | None = None
    relation_to_protagonist_end: str | None = None
    representative_conflict: str | None = None
    arc: str | None = None
    final_fate: str | None = None
    can_die_or_exit: bool = True


class ProtagonistArc(OutlineBaseModel):
    volume: int
    external_goal: str
    internal_change: str
    ability_change: str
    relationship_change: str
    cost: str


class VolumeOutline(OutlineBaseModel):
    volume: int
    title: str
    chapter_range: str
    core_map: str
    main_plot: str
    hidden_plot: str
    character_plot: str | None = None
    foreshadowing_plot: str | None = None
    protagonist_upgrade: dict[str, Any] = Field(default_factory=dict)
    phases: list[dict[str, Any]] = Field(default_factory=list)
    final_hook: str
    change_summary: dict[str, Any] = Field(default_factory=dict)
    risks: list[str] = Field(default_factory=list)


class BeatSheet(OutlineBaseModel):
    volume: int
    emotional_curve: str
    phase_beats: list[dict[str, Any]] = Field(default_factory=list)
    ten_chapter_loops: list[dict[str, Any]] = Field(default_factory=list)
    chapter_functions: list[dict[str, Any]] = Field(default_factory=list)
    repetition_check: list[str] = Field(default_factory=list)
    revision_suggestions: list[str] = Field(default_factory=list)


class ForeshadowingItem(OutlineBaseModel):
    id: str
    name: str
    first_appearance: str
    surface_meaning: str
    true_meaning: str
    related_characters: list[str] = Field(default_factory=list)
    related_factions: list[str] = Field(default_factory=list)
    importance: str
    progress_nodes: list[str] = Field(default_factory=list)
    misdirection_nodes: list[str] = Field(default_factory=list)
    payoff_node: str
    payoff_method: str
    status: str
    risk: str | None = None


class AuditIssue(OutlineBaseModel):
    severity: str
    issue: str
    location: str
    reason: str
    suggestion: str


class AuditReport(OutlineBaseModel):
    stage: str
    conclusion: str
    issues: list[AuditIssue] = Field(default_factory=list)
    passed: bool
    next_agent: str | None = None
    revision_required: bool = False


class StoryState(OutlineBaseModel):
    config: ProjectConfig
    kernel: StoryKernel = Field(default_factory=StoryKernel)
    raw_worldview: str = ""
    market_position: dict[str, Any] = Field(default_factory=dict)
    world_bible: WorldBible = Field(default_factory=WorldBible)
    protagonist_arcs: list[ProtagonistArc] = Field(default_factory=list)
    characters: list[CharacterProfile] = Field(default_factory=list)
    faction_conflicts: dict[str, Any] = Field(default_factory=dict)
    power_progression: dict[str, Any] = Field(default_factory=dict)
    full_structure: dict[str, Any] = Field(default_factory=dict)
    volumes: list[VolumeOutline] = Field(default_factory=list)
    beat_sheets: list[BeatSheet] = Field(default_factory=list)
    foreshadowing_ledger: list[ForeshadowingItem] = Field(default_factory=list)
    audit_reports: list[AuditReport] = Field(default_factory=list)
    revision_history: list[dict[str, Any]] = Field(default_factory=list)
    current_stage: str = "S0"
    version: str = "outline-v1"
