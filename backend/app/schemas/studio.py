from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from app.schemas.common import APIModel


ImportanceLevel = Literal["core", "major", "medium", "minor"]
RoleType = Literal["protagonist", "antagonist", "supporting", "minor"]
EntityType = Literal["location", "organization", "item", "event", "concept", "rule", "clue", "timeline_event"]
WorldFactCategory = Literal[
    "geography",
    "history",
    "magic_rule",
    "technology",
    "politics",
    "culture",
    "economy",
    "religion",
    "organization",
    "timeline",
    "taboo",
]


class UpdateProjectRequest(APIModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    genre: str | None = Field(default=None, min_length=1, max_length=60)
    target_reader: str | None = Field(default=None, min_length=1)
    premise: str | None = Field(default=None, min_length=1)
    style_guide: str | None = None
    language: str | None = None
    planned_chapter_count: int | None = Field(default=None, gt=0)
    planned_volume_count: int | None = Field(default=None, gt=0)
    chapters_per_volume: int | None = Field(default=None, gt=0)
    chapter_word_target: int | None = Field(default=None, ge=500, le=10000)
    chapter_word_min: int | None = Field(default=None, ge=500, le=20000)
    chapter_word_max: int | None = Field(default=None, ge=500, le=20000)
    status: Literal["draft", "active", "archived"] | None = None
    target_words: int | None = Field(default=None, ge=0)
    current_volume: int | None = Field(default=None, ge=1)
    current_chapter: int | None = Field(default=None, ge=1)
    cover_image: str | None = None
    initial_idea: str | None = None


class GenerateStoryBibleRequest(APIModel):
    initial_idea: str = Field(default="", max_length=12000)
    model: str | None = None
    template_name: str | None = None


class DraftChapterRequest(APIModel):
    mode: str = "first_draft"
    user_instruction: str = ""
    use_memory: bool = True
    temperature: float = Field(default=0.75, ge=0, le=2)
    max_words: int = Field(default=3200, ge=500, le=12000)
    idempotency_key: str | None = None
    async_mode: bool = False
    model: str | None = None


class RewriteChapterRequest(APIModel):
    instruction: str = Field(min_length=1)
    model: str | None = None


class PartialRewriteRequest(APIModel):
    selection: str = Field(min_length=1)
    instruction: str = Field(min_length=1)
    model: str | None = None


class ChapterChatRequest(APIModel):
    mode: Literal["revise", "polish", "expand", "tighten", "continue"] = "revise"
    instruction: str = Field(min_length=1, max_length=4000)
    selected_text: str = Field(default="", max_length=20000)
    chapter_text: str = Field(default="", max_length=200000)
    selection_start: int | None = Field(default=None, ge=0)
    selection_end: int | None = Field(default=None, ge=0)
    model: str | None = None


class CreateCharacterRequest(APIModel):
    name: str = Field(min_length=1, max_length=120)
    aliases: list[str] = Field(default_factory=list)
    role_type: RoleType = "supporting"
    importance_level: ImportanceLevel = "medium"
    importance_score: int = Field(default=50, ge=0, le=100)
    summary: str = ""
    appearance: str = ""
    personality: str = ""
    goals: list[str] = Field(default_factory=list)
    motivations: list[str] = Field(default_factory=list)
    secrets: list[str] = Field(default_factory=list)
    abilities: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    character_arc: str = ""
    current_status: str = "active"
    related_entity_ids: list[str] = Field(default_factory=list)
    related_character_ids: list[str] = Field(default_factory=list)
    updated_reason: str = "manual"
    source_chapter_id: str | None = None
    source_agent: str = "manual"


class UpdateCharacterRequest(APIModel):
    name: str | None = None
    aliases: list[str] | None = None
    role_type: RoleType | None = None
    importance_level: ImportanceLevel | None = None
    importance_score: int | None = Field(default=None, ge=0, le=100)
    summary: str | None = None
    appearance: str | None = None
    personality: str | None = None
    goals: list[str] | None = None
    motivations: list[str] | None = None
    secrets: list[str] | None = None
    abilities: list[str] | None = None
    weaknesses: list[str] | None = None
    character_arc: str | None = None
    current_status: str | None = None
    related_entity_ids: list[str] | None = None
    related_character_ids: list[str] | None = None
    updated_reason: str | None = None
    source_chapter_id: str | None = None
    source_agent: str | None = None


class CreateEntityRequest(APIModel):
    entity_type: EntityType = "item"
    name: str = Field(min_length=1, max_length=120)
    importance_level: ImportanceLevel = "medium"
    importance_score: int = Field(default=50, ge=0, le=100)
    description: str = ""
    current_status: str = "active"
    source: str = "manual"
    source_chapter_id: str | None = None
    source_agent: str = "manual"


class UpdateEntityRequest(APIModel):
    entity_type: EntityType | None = None
    name: str | None = Field(default=None, min_length=1, max_length=120)
    importance_level: ImportanceLevel | None = None
    importance_score: int | None = Field(default=None, ge=0, le=100)
    description: str | None = None
    current_status: str | None = None
    source: str | None = None
    source_chapter_id: str | None = None
    source_agent: str | None = None


class CreateWorldFactRequest(APIModel):
    category: WorldFactCategory = "timeline"
    title: str = Field(min_length=1, max_length=160)
    content: str = ""
    importance_level: ImportanceLevel = "medium"
    importance_score: int = Field(default=50, ge=0, le=100)
    confidence: float = Field(default=0.8, ge=0, le=1)
    related_entity_ids: list[str] = Field(default_factory=list)
    source_chapter_id: str | None = None
    source_agent: str = "manual"


class UpdateWorldFactRequest(APIModel):
    category: WorldFactCategory | None = None
    title: str | None = Field(default=None, min_length=1, max_length=160)
    content: str | None = None
    importance_level: ImportanceLevel | None = None
    importance_score: int | None = Field(default=None, ge=0, le=100)
    confidence: float | None = Field(default=None, ge=0, le=1)
    related_entity_ids: list[str] | None = None
    source_chapter_id: str | None = None
    source_agent: str | None = None


class GenerateSettingRequest(APIModel):
    target: Literal["characters", "entities", "world_facts", "all"] = "all"
    instruction: str = Field(default="", max_length=4000)
    count: int = Field(default=3, ge=1, le=12)
    preview_only: bool = False
    model: str | None = None


class CanonRollbackRequest(APIModel):
    user_note: str = Field(default="", max_length=1000)


class CanonProposalDecisionRequest(APIModel):
    user_note: str = Field(default="", max_length=1000)


class CanonBulkArchiveRequest(APIModel):
    ref_type: str = Field(min_length=1, max_length=80)
    ref_ids: list[str] = Field(min_length=1)
    reason: str = Field(default="", max_length=1000)


class CanonFolderRequest(APIModel):
    title: str = Field(min_length=1, max_length=120)
    parent_id: str | None = Field(default=None, max_length=160)
    sort_order: int = Field(default=0, ge=0)


class CanonNodeMoveRequest(APIModel):
    parent_id: str | None = Field(default=None, max_length=160)
    sort_order: int = Field(default=0, ge=0)


class CanonLockFieldsRequest(APIModel):
    locked_fields: list[str] = Field(default_factory=list)
    reason: str = Field(default="", max_length=1000)


class CanonDuplicateScanRequest(APIModel):
    ref_types: list[str] = Field(default_factory=lambda: ["character", "entity", "world_fact", "foreshadowing"])
    threshold: float = Field(default=0.72, ge=0, le=1)
    create_proposals: bool = True


class CanonExportRequest(APIModel):
    format: Literal["json", "markdown"] = "json"


CreationStarStep = Literal["worldview", "protagonist", "project_bible", "world_rules", "title"]


class CreationStarDrawRequest(APIModel):
    step: CreationStarStep
    basic_info: dict[str, Any] = Field(default_factory=dict)
    selected_worldview: dict[str, Any] = Field(default_factory=dict)
    selected_protagonist: dict[str, Any] = Field(default_factory=dict)
    project_bible: dict[str, Any] = Field(default_factory=dict)
    world_rules: dict[str, Any] = Field(default_factory=dict)
    manual_input: str = Field(default="", max_length=6000)
    count: int = Field(default=9, ge=1, le=12)
    model: str | None = None


class CreationStarCommitRequest(APIModel):
    basic_info: dict[str, Any] = Field(default_factory=dict)
    selected_worldview: dict[str, Any] = Field(default_factory=dict)
    selected_protagonist: dict[str, Any] = Field(default_factory=dict)
    selected_title: dict[str, Any] = Field(default_factory=dict)
    project_bible: dict[str, Any] = Field(default_factory=dict)
    world_rules: dict[str, Any] = Field(default_factory=dict)
    user_note: str = Field(default="", max_length=2000)
    model: str | None = None


class CreationBasicSuggestionsRequest(APIModel):
    basic_info: dict[str, Any] = Field(default_factory=dict)
    manual_input: str = Field(default="", max_length=6000)
    previous_suggestions: list[dict[str, Any]] = Field(default_factory=list)
    count: int = Field(default=6, ge=2, le=12)
    model: str | None = None


class CreationSessionCreateRequest(APIModel):
    basic_info: dict[str, Any] = Field(default_factory=dict)
    model: str | None = None


class CreationSessionCardRequest(APIModel):
    selected_worldview: dict[str, Any] = Field(default_factory=dict)
    selected_protagonist: dict[str, Any] = Field(default_factory=dict)
    selected_title: dict[str, Any] = Field(default_factory=dict)
    manual_input: str = Field(default="", max_length=6000)
    count: int = Field(default=1, ge=1, le=3)
    replace_existing: bool = False
    model: str | None = None


class CreationSessionSeedRequest(APIModel):
    selected_worldview: dict[str, Any] = Field(default_factory=dict)
    selected_protagonist: dict[str, Any] = Field(default_factory=dict)
    selected_title: dict[str, Any] = Field(default_factory=dict)
    market_position: dict[str, Any] = Field(default_factory=dict)
    user_note: str = Field(default="", max_length=2000)


class CreationSessionRunRequest(APIModel):
    instruction: str = Field(default="", max_length=4000)
    model: str | None = None
    core_conflict_system: dict[str, Any] = Field(default_factory=dict)
    novel_constitution: dict[str, Any] = Field(default_factory=dict)


class CreationSessionCommitRequest(APIModel):
    user_note: str = Field(default="", max_length=2000)
    approved_canon_sections: list[str] | None = None
    model: str | None = None


ForeshadowingStatus = Literal["planned", "planted", "paid_off", "abandoned", "candidate"]


class CreateForeshadowingRequest(APIModel):
    chapter_id: str | None = None
    content: str = Field(min_length=1, max_length=4000)
    planted_chapter_id: str | None = None
    planned_payoff_chapter_id: str | None = None
    actual_payoff_chapter_id: str | None = None
    planned_payoff: str = ""
    payoff_status: ForeshadowingStatus = "planned"
    importance_level: ImportanceLevel = "medium"
    importance_score: int = Field(default=50, ge=0, le=100)
    related_character_ids: list[str] = Field(default_factory=list)
    related_entity_ids: list[str] = Field(default_factory=list)
    source: Literal["manual", "agent"] = "manual"


class UpdateForeshadowingRequest(APIModel):
    chapter_id: str | None = None
    content: str | None = Field(default=None, min_length=1, max_length=4000)
    planted_chapter_id: str | None = None
    planned_payoff_chapter_id: str | None = None
    actual_payoff_chapter_id: str | None = None
    planned_payoff: str | None = None
    payoff_status: ForeshadowingStatus | None = None
    importance_level: ImportanceLevel | None = None
    importance_score: int | None = Field(default=None, ge=0, le=100)
    related_character_ids: list[str] | None = None
    related_entity_ids: list[str] | None = None
    source: Literal["manual", "agent"] | None = None


class PayoffForeshadowingRequest(APIModel):
    actual_payoff_chapter_id: str = Field(min_length=1)
    payoff_note: str = ""


class UpdateChapterRequest(APIModel):
    title: str | None = None
    outline: str | None = None
    pov_character: str | None = None
    core_event: str | None = None
    conflict: str | None = None
    crisis: str | None = None
    climax: str | None = None
    outcome: str | None = None
    turn_point: str | None = None
    emotional_beats: list[str] | None = None
    plot_purpose: str | None = None
    cliffhanger: str | None = None
    chapter_hook: str | None = None
    draft_text: str | None = None
    final_text: str | None = None
    summary: str | None = None
    revision_notes: str | None = None
    status: str | None = None
    word_target: int | None = Field(default=None, ge=1)


class AgentPromptUpdateRequest(APIModel):
    prompt: str = Field(min_length=1)
    template_name: str = "custom"
    temporary: bool = False


class AgentModelConfigRequest(APIModel):
    workflow_id: str = Field(min_length=1, max_length=120)
    agent_name: str = Field(min_length=1, max_length=120)
    model: str = Field(min_length=1, max_length=200)


class PromptTemplateRequest(APIModel):
    agent_name: str = Field(min_length=1)
    template_name: str = Field(min_length=1)
    prompt: str = Field(min_length=1)
    activate: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class ImportPromptTemplatesRequest(APIModel):
    templates: list[PromptTemplateRequest]


class WriteGenerateRequest(APIModel):
    project_id: str
    chapter_id: str | None = None
    workflow_type: str = "draft_chapter"
    instruction: str = ""
    model: str | None = None


class BatchGenerateRequest(APIModel):
    project_id: str
    chapter_start: int = Field(ge=1)
    chapter_end: int = Field(ge=1)
    generation_options: dict[str, Any] = Field(default_factory=dict)
    model: str | None = None


class JobControlRequest(APIModel):
    job_id: str
    reason: str = ""


class VersionCompareRequest(APIModel):
    left_version_id: str
    right_version_id: str


class RollbackVersionRequest(APIModel):
    user_note: str = ""


class BranchVersionRequest(APIModel):
    branch_name: str = Field(min_length=1)
    user_note: str = ""


class SummaryRequest(APIModel):
    project_id: str
    chapter_start: int | None = Field(default=None, ge=1)
    chapter_end: int | None = Field(default=None, ge=1)
    character_id: str | None = None


class TextToolRequest(APIModel):
    project_id: str
    chapter_id: str | None = None
    text: str = ""
    instruction: str = ""


class LearnStyleRequest(APIModel):
    project_id: str
    name: str = Field(default="默认风格", min_length=1)
    sample_text: str = Field(min_length=1)


class QueryKnowledgeRequest(APIModel):
    project_id: str
    question: str = Field(min_length=1)


class ExportRequest(APIModel):
    project_id: str
    format: Literal["markdown", "txt", "html", "pdf", "epub", "word"] = "markdown"
    volume_no: int | None = Field(default=None, ge=1)
    chapter_start: int | None = Field(default=None, ge=1)
    chapter_end: int | None = Field(default=None, ge=1)
    platform_template: str = "default"
    include_summary: bool = True
    branch_name: str = "main"


class ExportTemplateRequest(APIModel):
    name: str = Field(min_length=1)
    format: str = "markdown"
    template: str = Field(min_length=1)
