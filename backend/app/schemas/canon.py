from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import Field

from app.schemas.common import APIModel


class EntityLevel(str, Enum):
    S = "S"
    A = "A"
    B = "B"
    C = "C"


class EntityType(str, Enum):
    CHARACTER = "character"
    EVENT = "event"
    ITEM = "item"
    FACTION = "faction"
    LOCATION = "location"
    SECRET = "secret"
    RULE = "rule"
    RESOURCE = "resource"
    INSTITUTION = "institution"
    SYMBOL = "symbol"
    RELATIONSHIP = "relationship"


class CompletionStatus(str, Enum):
    CANDIDATE = "candidate"
    INCOMPLETE = "incomplete"
    COMPLETE = "complete"
    CONFLICT = "conflict"


class DramaNodeType(str, Enum):
    SETUP = "SETUP"
    INCITING_INCIDENT = "INCITING_INCIDENT"
    PROGRESSIVE_COMPLICATION = "PROGRESSIVE_COMPLICATION"
    REVERSAL = "REVERSAL"
    REVEAL = "REVEAL"
    CRISIS = "CRISIS"
    CLIMAX = "CLIMAX"
    RESOLUTION = "RESOLUTION"
    HOOK = "HOOK"


class NovelSeed(APIModel):
    worldview: str = ""
    one_sentence_story: str = ""
    genre: str = ""
    target_length: str = "长篇，多卷结构"
    tone: str = ""
    reference_works: list[str] = Field(default_factory=list)
    avoid_elements: list[str] = Field(default_factory=list)


class DramaNode(APIModel):
    node_id: str
    node_type: DramaNodeType
    title: str
    description: str
    story_function: str
    protagonist_goal: str
    opposition_force: str
    cost: str
    new_information: str
    state_change: str
    next_node: str | None = None
    why_chain: list[str] = Field(default_factory=list)
    related_entities: list[str] = Field(default_factory=list)


class UncertaintyTicket(APIModel):
    ticket_id: str
    source_agent: str
    question: str
    reason: str
    blocking_level: EntityLevel = EntityLevel.B
    suggested_agent: str
    status: str = "open"
    related_entities: list[str] = Field(default_factory=list)


class CanonCompletionTicket(APIModel):
    ticket_id: str
    entity_name: str
    entity_type: EntityType
    entity_level: EntityLevel
    missing_fields: list[str]
    suggested_agent: str
    reason: str
    status: str = "open"


class CanonEntity(APIModel):
    name: str
    entity_type: EntityType
    level: EntityLevel = EntityLevel.C
    story_function: str = ""
    first_appearance: str = ""
    responsible_agent: str = ""
    completion_status: CompletionStatus = CompletionStatus.INCOMPLETE
    continuity_checked: bool = False
    version: int = 1
    related_drama_nodes: list[str] = Field(default_factory=list)
    related_entities: list[str] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)

    @property
    def key(self) -> str:
        return f"{self.entity_type.value}:{self.name}"


class CharacterProfile(APIModel):
    name: str
    level: EntityLevel
    role_function: str
    first_appearance: str
    external_goal: str
    inner_need: str
    wrong_belief: str
    core_fear: str
    core_desire: str
    secret: str
    relationship_to_protagonist: str
    relationship_to_main_conflict: str
    faction: str
    power_or_skill: str
    weakness: str
    arc_start: str
    arc_midpoint: str
    arc_crisis: str
    arc_climax: str
    arc_end: str
    why_this_character_must_exist: str
    if_removed_what_breaks: str
    future_use: str


class EventProfile(APIModel):
    name: str
    level: EntityLevel
    event_type: str
    time_position: str
    location: str
    participants: list[str]
    trigger: str
    visible_event: str
    hidden_cause: str
    protagonist_goal: str
    opposition_force: str
    choice: str
    cost: str
    new_information: str
    state_change: str
    consequence: str
    next_event_caused: str
    why_now: str
    why_inevitable: str
    if_removed_what_breaks: str


class ItemProfile(APIModel):
    name: str
    level: EntityLevel
    item_type: str
    origin: str
    creator: str
    current_owner: str
    previous_owners: list[str]
    who_wants_it: list[str]
    function: str
    limitation: str
    cost: str
    risk: str
    symbolic_meaning: str
    first_appearance: str
    foreshadowing: str
    major_use: str
    climax_use: str
    why_it_exists: str
    why_now: str
    if_removed_what_breaks: str


class FactionProfile(APIModel):
    name: str
    level: EntityLevel
    faction_type: str
    public_goal: str
    hidden_goal: str
    core_resource: str
    power_base: str
    leader: str
    internal_split: str
    fear: str
    enemy_factions: list[str]
    ally_factions: list[str]
    relationship_to_protagonist: str
    relationship_to_antagonist: str
    ideology: str
    methods: str
    weakness: str
    first_appearance: str
    role_in_conflict: str
    role_in_climax: str
    why_it_exists: str
    if_removed_what_breaks: str


class LocationProfile(APIModel):
    name: str
    level: EntityLevel
    location_type: str
    geography: str
    history: str
    controller: str
    population: str
    resources: str
    danger: str
    secret: str
    social_order: str
    visual_identity: str
    story_function: str
    first_appearance: str
    major_events: list[str]
    why_here: str
    why_protagonist_must_go: str
    why_protagonist_cannot_easily_leave: str
    if_removed_what_breaks: str


class SecretProfile(APIModel):
    name: str
    level: EntityLevel
    truth: str
    who_knows: list[str]
    who_misunderstands: list[str]
    who_hides_it: list[str]
    why_hidden: str
    cost_if_revealed: str
    false_explanation: str
    foreshadowing_clues: list[str]
    reveal_timing: str
    impact_on_character: str
    impact_on_world: str
    impact_on_conflict: str
    impact_on_climax: str
    why_not_revealed_earlier: str
    if_removed_what_breaks: str


class ConflictMatrix(APIModel):
    core_conflict: str = ""
    sides: list[dict[str, Any]] = Field(default_factory=list)
    escalation_path: list[dict[str, Any]] = Field(default_factory=list)
    irreversible_points: list[str] = Field(default_factory=list)


class ForeshadowingRecord(APIModel):
    id: str
    clue: str
    planted_at: str
    payoff_plan: str
    status: str = "planned"
    related_entities: list[str] = Field(default_factory=list)


class ContinuityIssue(APIModel):
    issue_id: str
    severity: str
    issue_type: str
    location: str
    message: str
    impact_scope: str
    suggested_agent: str
    repair_requirement: str


class NovelCanon(APIModel):
    world_rules: list[str] = Field(default_factory=list)
    power_system: list[str] = Field(default_factory=list)
    factions: list[str] = Field(default_factory=list)
    history: list[str] = Field(default_factory=list)
    geography: list[str] = Field(default_factory=list)
    social_order: list[str] = Field(default_factory=list)
    items: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    secrets: list[str] = Field(default_factory=list)
    events: list[str] = Field(default_factory=list)
    resources: list[str] = Field(default_factory=list)
    institutions: list[str] = Field(default_factory=list)
    symbols: list[str] = Field(default_factory=list)


class NovelState(APIModel):
    project_id: str
    seed: NovelSeed
    theme: str = ""
    canon: NovelCanon = Field(default_factory=NovelCanon)
    characters: list[CanonEntity] = Field(default_factory=list)
    relationships: list[dict[str, Any]] = Field(default_factory=list)
    conflict_matrix: ConflictMatrix = Field(default_factory=ConflictMatrix)
    drama_nodes: list[DramaNode] = Field(default_factory=list)
    volume_outline: list[dict[str, Any]] = Field(default_factory=list)
    chapter_outline: list[dict[str, Any]] = Field(default_factory=list)
    foreshadowing_table: list[ForeshadowingRecord] = Field(default_factory=list)
    uncertainty_tickets: list[UncertaintyTicket] = Field(default_factory=list)
    canon_completion_tickets: list[CanonCompletionTicket] = Field(default_factory=list)
    resolved_tickets: list[str] = Field(default_factory=list)
    continuity_issues: list[ContinuityIssue] = Field(default_factory=list)
    why_logs: list[str] = Field(default_factory=list)
    agent_trace: list[str] = Field(default_factory=list)


class CanonRunRequest(APIModel):
    project_id: str | None = None
    worldview: str = Field(default="", max_length=30000)
    one_sentence_story: str = Field(default="", max_length=4000)
    genre: str = ""
    target_length: str = "长篇，多卷结构"
    tone: str = ""
    reference_works: list[str] = Field(default_factory=list)
    avoid_elements: list[str] = Field(default_factory=list)


class CanonRunResult(APIModel):
    project_id: str
    state: NovelState
    canon_store_path: str
    trace_store_path: str
    version_store_path: str
    final_outline_path: str
    final_outline: str
    continuity_report: dict[str, Any]
    agent_trace: list[str]
    drama_nodes: list[DramaNode]
    canon_entities: list[CanonEntity]
    completion_tickets: list[CanonCompletionTicket]
    uncertainty_tickets: list[UncertaintyTicket]
    agent_handoff_graph: dict[str, list[str]]
