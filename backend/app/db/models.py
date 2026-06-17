from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    genre: Mapped[str] = mapped_column(Text, nullable=False)
    target_reader: Mapped[str] = mapped_column(Text, nullable=False)
    premise: Mapped[str] = mapped_column(Text, nullable=False)
    style_guide: Mapped[str] = mapped_column(Text, nullable=False, default="")
    language: Mapped[str] = mapped_column(Text, nullable=False, default="zh-CN")
    planned_chapter_count: Mapped[int] = mapped_column(Integer, nullable=False)
    planned_volume_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    chapters_per_volume: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    chapter_word_target: Mapped[int] = mapped_column(Integer, nullable=False)
    chapter_word_min: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    chapter_word_max: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    target_words: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_volume: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    current_chapter: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    cover_image: Mapped[str] = mapped_column(Text, nullable=False, default="")
    initial_idea: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(Text, nullable=False, default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class StoryBible(Base):
    __tablename__ = "story_bibles"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    project_id: Mapped[str] = mapped_column(Text, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, unique=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    world_setting: Mapped[str] = mapped_column(Text, nullable=False, default="")
    main_conflict: Mapped[str] = mapped_column(Text, nullable=False, default="")
    themes_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    style_guide: Mapped[str] = mapped_column(Text, nullable=False, default="")
    narrative_pov: Mapped[str] = mapped_column(Text, nullable=False, default="third_person_limited")
    forbidden_elements_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    continuity_rules_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class CreationSession(Base):
    __tablename__ = "creation_sessions"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    project_id: Mapped[str] = mapped_column(Text, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="draft")
    current_step: Mapped[str] = mapped_column(Text, nullable=False, default="brief")
    basic_info_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    state_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class Character(Base):
    __tablename__ = "characters"
    __table_args__ = (UniqueConstraint("project_id", "name", name="uq_characters_project_name"),)

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    project_id: Mapped[str] = mapped_column(Text, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    aliases_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    role: Mapped[str] = mapped_column(Text, nullable=False)
    role_type: Mapped[str] = mapped_column(Text, nullable=False, default="supporting")
    importance_level: Mapped[str] = mapped_column(Text, nullable=False, default="medium")
    importance_score: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    appearance: Mapped[str] = mapped_column(Text, nullable=False, default="")
    personality: Mapped[str] = mapped_column(Text, nullable=False, default="")
    profile: Mapped[str] = mapped_column(Text, nullable=False, default="")
    goals_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    motivations_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    secrets_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    abilities_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    weaknesses_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    motivation: Mapped[str] = mapped_column(Text, nullable=False, default="")
    arc: Mapped[str] = mapped_column(Text, nullable=False, default="")
    character_arc: Mapped[str] = mapped_column(Text, nullable=False, default="")
    current_status: Mapped[str] = mapped_column(Text, nullable=False, default="active")
    first_appearance_chapter_id: Mapped[str | None] = mapped_column(Text, ForeignKey("chapters.id", ondelete="SET NULL"), nullable=True)
    last_seen_chapter_id: Mapped[str | None] = mapped_column(Text, ForeignKey("chapters.id", ondelete="SET NULL"), nullable=True)
    related_entity_ids_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    related_character_ids_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    updated_reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source: Mapped[str] = mapped_column(Text, nullable=False, default="manual")
    relations_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    status: Mapped[str] = mapped_column(Text, nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class Chapter(Base):
    __tablename__ = "chapters"
    __table_args__ = (UniqueConstraint("project_id", "chapter_no", name="uq_chapters_project_chapter_no"),)

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    project_id: Mapped[str] = mapped_column(Text, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    volume_no: Mapped[int] = mapped_column(Integer, nullable=False)
    chapter_no: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    outline: Mapped[str] = mapped_column(Text, nullable=False, default="")
    pov_character: Mapped[str] = mapped_column(Text, nullable=False, default="")
    core_event: Mapped[str] = mapped_column(Text, nullable=False, default="")
    conflict: Mapped[str] = mapped_column(Text, nullable=False, default="")
    turn_point: Mapped[str] = mapped_column(Text, nullable=False, default="")
    emotional_beats_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    plot_purpose: Mapped[str] = mapped_column(Text, nullable=False, default="")
    cliffhanger: Mapped[str] = mapped_column(Text, nullable=False, default="")
    crisis: Mapped[str] = mapped_column(Text, nullable=False, default="")
    climax: Mapped[str] = mapped_column(Text, nullable=False, default="")
    outcome: Mapped[str] = mapped_column(Text, nullable=False, default="")
    chapter_hook: Mapped[str] = mapped_column(Text, nullable=False, default="")
    foreshadowing_plants_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    foreshadowing_payoffs_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    canon_updates_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    continuity_risks_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    draft_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    final_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    revision_notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(Text, nullable=False, default="planned")
    word_target: Mapped[int] = mapped_column(Integer, nullable=False)
    word_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_locked: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class Volume(Base):
    __tablename__ = "volumes"
    __table_args__ = (UniqueConstraint("project_id", "volume_no", name="uq_volumes_project_volume_no"),)

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    project_id: Mapped[str] = mapped_column(Text, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    volume_no: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    outline: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(Text, nullable=False, default="active")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class Note(Base):
    __tablename__ = "notes"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    project_id: Mapped[str] = mapped_column(Text, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    parent_id: Mapped[str | None] = mapped_column(Text, ForeignKey("notes.id", ondelete="SET NULL"), nullable=True)
    note_type: Mapped[str] = mapped_column(Text, nullable=False, default="note")
    title: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_pinned: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class EditorProposal(Base):
    __tablename__ = "editor_proposals"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    project_id: Mapped[str] = mapped_column(Text, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    chapter_id: Mapped[str] = mapped_column(Text, ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False)
    tool_name: Mapped[str] = mapped_column(Text, nullable=False)
    instruction: Mapped[str] = mapped_column(Text, nullable=False, default="")
    original_content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    proposed_content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    diff_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MemoryChunk(Base):
    __tablename__ = "memory_chunks"
    __table_args__ = (
        UniqueConstraint("project_id", "source_type", "source_id", "content_hash", name="uq_memory_source_hash"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    project_id: Mapped[str] = mapped_column(Text, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    bank: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    source_id: Mapped[str] = mapped_column(Text, nullable=False)
    chapter_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    importance: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    is_pinned: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    qdrant_point_id: Mapped[str | None] = mapped_column(Text, nullable=True, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class GenerationJob(Base):
    __tablename__ = "generation_jobs"
    __table_args__ = (UniqueConstraint("project_id", "idempotency_key", name="uq_jobs_project_idempotency"),)

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    project_id: Mapped[str] = mapped_column(Text, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    chapter_id: Mapped[str | None] = mapped_column(Text, ForeignKey("chapters.id", ondelete="SET NULL"), nullable=True)
    job_type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="queued")
    run_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    request_json: Mapped[str] = mapped_column(Text, nullable=False)
    progress_json: Mapped[str] = mapped_column(Text, nullable=False)
    current_agent: Mapped[str] = mapped_column(Text, nullable=False, default="")
    result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    langsmith_run_id: Mapped[str] = mapped_column(Text, nullable=False, default="")
    langsmith_url: Mapped[str] = mapped_column(Text, nullable=False, default="")
    trace_mode: Mapped[str] = mapped_column(Text, nullable=False, default="local")
    cancel_requested: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cancel_reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ModelCall(Base):
    __tablename__ = "model_calls"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    job_id: Mapped[str] = mapped_column(Text, ForeignKey("generation_jobs.id", ondelete="CASCADE"), nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False, default="dashscope")
    model: Mapped[str] = mapped_column(Text, nullable=False)
    request_hash: Mapped[str] = mapped_column(Text, nullable=False)
    response_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    response_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    prompt_hash: Mapped[str] = mapped_column(Text, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class EventLog(Base):
    __tablename__ = "event_logs"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    project_id: Mapped[str] = mapped_column(Text, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    actor_type: Mapped[str] = mapped_column(Text, nullable=False)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[str] = mapped_column(Text, nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class ChapterIntent(Base):
    __tablename__ = "chapter_intents"
    __table_args__ = (UniqueConstraint("chapter_id", "version", name="uq_chapter_intent_version"),)

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    project_id: Mapped[str] = mapped_column(Text, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    chapter_id: Mapped[str] = mapped_column(Text, ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False)
    job_id: Mapped[str | None] = mapped_column(Text, ForeignKey("generation_jobs.id", ondelete="SET NULL"), nullable=True)
    goal: Mapped[str] = mapped_column(Text, nullable=False)
    outline_node: Mapped[str] = mapped_column(Text, nullable=False, default="")
    must_hit_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    must_preserve_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    must_avoid_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    required_characters_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    required_payoffs_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    style_emphasis_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class ContextPackage(Base):
    __tablename__ = "context_packages"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    project_id: Mapped[str] = mapped_column(Text, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    chapter_id: Mapped[str] = mapped_column(Text, ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False)
    job_id: Mapped[str | None] = mapped_column(Text, ForeignKey("generation_jobs.id", ondelete="SET NULL"), nullable=True)
    package_type: Mapped[str] = mapped_column(Text, nullable=False)
    required_blocks_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    optional_blocks_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    selected_sources_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    dropped_blocks_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    summarized_blocks_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    estimated_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    prompt_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class QualityReport(Base):
    __tablename__ = "quality_reports"
    __table_args__ = (UniqueConstraint("chapter_id", "content_hash", name="uq_quality_chapter_hash"),)

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    project_id: Mapped[str] = mapped_column(Text, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    chapter_id: Mapped[str] = mapped_column(Text, ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False)
    job_id: Mapped[str | None] = mapped_column(Text, ForeignKey("generation_jobs.id", ondelete="SET NULL"), nullable=True)
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    blocking_issue_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    warning_issue_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class QualityIssue(Base):
    __tablename__ = "quality_issues"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    report_id: Mapped[str] = mapped_column(Text, ForeignKey("quality_reports.id", ondelete="CASCADE"), nullable=False)
    severity: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[str] = mapped_column(Text, nullable=False, default="")
    suggestion: Mapped[str] = mapped_column(Text, nullable=False, default="")
    is_resolved: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class StoryStateSnapshot(Base):
    __tablename__ = "story_state_snapshots"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    project_id: Mapped[str] = mapped_column(Text, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    chapter_id: Mapped[str | None] = mapped_column(Text, ForeignKey("chapters.id", ondelete="SET NULL"), nullable=True)
    job_id: Mapped[str | None] = mapped_column(Text, ForeignKey("generation_jobs.id", ondelete="SET NULL"), nullable=True)
    snapshot_type: Mapped[str] = mapped_column(Text, nullable=False)
    chapter_no: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    current_state_json: Mapped[str] = mapped_column(Text, nullable=False)
    open_hooks_json: Mapped[str] = mapped_column(Text, nullable=False)
    chapter_summary_json: Mapped[str] = mapped_column(Text, nullable=False)
    continuity_facts_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class JobArtifact(Base):
    __tablename__ = "job_artifacts"
    __table_args__ = (UniqueConstraint("job_id", "artifact_type", "content_hash", name="uq_job_artifact_type_hash"),)

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    job_id: Mapped[str] = mapped_column(Text, ForeignKey("generation_jobs.id", ondelete="CASCADE"), nullable=False)
    artifact_type: Mapped[str] = mapped_column(Text, nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    job_id: Mapped[str] = mapped_column(Text, ForeignKey("generation_jobs.id", ondelete="CASCADE"), nullable=False)
    project_id: Mapped[str] = mapped_column(Text, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    chapter_id: Mapped[str | None] = mapped_column(Text, ForeignKey("chapters.id", ondelete="SET NULL"), nullable=True)
    agent_name: Mapped[str] = mapped_column(Text, nullable=False)
    agent_role: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    input_payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    output_payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    error_message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    langsmith_run_id: Mapped[str] = mapped_column(Text, nullable=False, default="")
    langsmith_url: Mapped[str] = mapped_column(Text, nullable=False, default="")
    trace_mode: Mapped[str] = mapped_column(Text, nullable=False, default="local")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class AgentMessage(Base):
    __tablename__ = "agent_messages"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    agent_run_id: Mapped[str] = mapped_column(Text, ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class GenerationOutput(Base):
    __tablename__ = "generation_outputs"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    project_id: Mapped[str] = mapped_column(Text, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    chapter_id: Mapped[str | None] = mapped_column(Text, ForeignKey("chapters.id", ondelete="SET NULL"), nullable=True)
    job_id: Mapped[str | None] = mapped_column(Text, ForeignKey("generation_jobs.id", ondelete="SET NULL"), nullable=True)
    output_type: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False, default="")
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class StoryEntity(Base):
    __tablename__ = "story_entities"
    __table_args__ = (UniqueConstraint("project_id", "entity_type", "name", name="uq_story_entities_project_type_name"),)

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    project_id: Mapped[str] = mapped_column(Text, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    importance_level: Mapped[str] = mapped_column(Text, nullable=False, default="medium")
    importance_score: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    current_status: Mapped[str] = mapped_column(Text, nullable=False, default="active")
    first_appearance_chapter_id: Mapped[str | None] = mapped_column(Text, ForeignKey("chapters.id", ondelete="SET NULL"), nullable=True)
    last_seen_chapter_id: Mapped[str | None] = mapped_column(Text, ForeignKey("chapters.id", ondelete="SET NULL"), nullable=True)
    source: Mapped[str] = mapped_column(Text, nullable=False, default="manual")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class WorldFact(Base):
    __tablename__ = "world_facts"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    project_id: Mapped[str] = mapped_column(Text, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    importance_level: Mapped[str] = mapped_column(Text, nullable=False, default="medium")
    importance_score: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.8)
    source_chapter_id: Mapped[str | None] = mapped_column(Text, ForeignKey("chapters.id", ondelete="SET NULL"), nullable=True)
    related_entity_ids_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class GraphNode(Base):
    __tablename__ = "graph_nodes"
    __table_args__ = (UniqueConstraint("project_id", "node_type", "ref_id", name="uq_graph_nodes_project_type_ref"),)

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    project_id: Mapped[str] = mapped_column(Text, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    node_type: Mapped[str] = mapped_column(Text, nullable=False)
    ref_id: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    importance_level: Mapped[str] = mapped_column(Text, nullable=False, default="medium")
    importance_score: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class GraphEdge(Base):
    __tablename__ = "graph_edges"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    project_id: Mapped[str] = mapped_column(Text, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    source_node_id: Mapped[str] = mapped_column(Text, ForeignKey("graph_nodes.id", ondelete="CASCADE"), nullable=False)
    target_node_id: Mapped[str] = mapped_column(Text, ForeignKey("graph_nodes.id", ondelete="CASCADE"), nullable=False)
    edge_type: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False, default="")
    importance_score: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.8)
    evidence: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_chapter_id: Mapped[str | None] = mapped_column(Text, ForeignKey("chapters.id", ondelete="SET NULL"), nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class CanonNode(Base):
    __tablename__ = "canon_nodes"
    __table_args__ = (UniqueConstraint("project_id", "ref_type", "ref_id", name="uq_canon_nodes_project_ref"),)

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    project_id: Mapped[str] = mapped_column(Text, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    parent_id: Mapped[str | None] = mapped_column(Text, ForeignKey("canon_nodes.id", ondelete="SET NULL"), nullable=True)
    node_type: Mapped[str] = mapped_column(Text, nullable=False, default="item")
    ref_type: Mapped[str] = mapped_column(Text, nullable=False, default="folder")
    ref_id: Mapped[str] = mapped_column(Text, nullable=False, default="")
    title: Mapped[str] = mapped_column(Text, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="active")
    importance_level: Mapped[str] = mapped_column(Text, nullable=False, default="medium")
    activity_status: Mapped[str] = mapped_column(Text, nullable=False, default="active")
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class CanonVersion(Base):
    __tablename__ = "canon_versions"
    __table_args__ = (UniqueConstraint("project_id", "ref_type", "ref_id", "version_no", name="uq_canon_versions_project_ref_version"),)

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    project_id: Mapped[str] = mapped_column(Text, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    ref_type: Mapped[str] = mapped_column(Text, nullable=False)
    ref_id: Mapped[str] = mapped_column(Text, nullable=False)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    content_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    source_chapter_id: Mapped[str | None] = mapped_column(Text, ForeignKey("chapters.id", ondelete="SET NULL"), nullable=True)
    source_job_id: Mapped[str | None] = mapped_column(Text, ForeignKey("generation_jobs.id", ondelete="SET NULL"), nullable=True)
    source_agent: Mapped[str] = mapped_column(Text, nullable=False, default="manual")
    change_reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class CanonChangeProposal(Base):
    __tablename__ = "canon_change_proposals"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    project_id: Mapped[str] = mapped_column(Text, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    target_type: Mapped[str] = mapped_column(Text, nullable=False)
    target_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    operation: Mapped[str] = mapped_column(Text, nullable=False, default="create")
    before_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    after_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    source_chapter_id: Mapped[str | None] = mapped_column(Text, ForeignKey("chapters.id", ondelete="SET NULL"), nullable=True)
    source_job_id: Mapped[str | None] = mapped_column(Text, ForeignKey("generation_jobs.id", ondelete="SET NULL"), nullable=True)
    source_agent: Mapped[str] = mapped_column(Text, nullable=False, default="agent")
    approval_status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.8)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CanonClassification(Base):
    __tablename__ = "canon_classifications"
    __table_args__ = (UniqueConstraint("project_id", "ref_type", "ref_id", "dimension", "value", name="uq_canon_classification"),)

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    project_id: Mapped[str] = mapped_column(Text, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    ref_type: Mapped[str] = mapped_column(Text, nullable=False)
    ref_id: Mapped[str] = mapped_column(Text, nullable=False)
    dimension: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class ContinuityIssue(Base):
    __tablename__ = "continuity_issues"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    project_id: Mapped[str] = mapped_column(Text, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    chapter_id: Mapped[str | None] = mapped_column(Text, ForeignKey("chapters.id", ondelete="SET NULL"), nullable=True)
    severity: Mapped[str] = mapped_column(Text, nullable=False, default="warning")
    category: Mapped[str] = mapped_column(Text, nullable=False, default="continuity")
    message: Mapped[str] = mapped_column(Text, nullable=False)
    suggestion: Mapped[str] = mapped_column(Text, nullable=False, default="")
    related_chapter_id: Mapped[str | None] = mapped_column(Text, ForeignKey("chapters.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="open")
    evidence: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class ForeshadowingItem(Base):
    __tablename__ = "foreshadowing_items"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    project_id: Mapped[str] = mapped_column(Text, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    chapter_id: Mapped[str | None] = mapped_column(Text, ForeignKey("chapters.id", ondelete="SET NULL"), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    planted_chapter_id: Mapped[str | None] = mapped_column(Text, ForeignKey("chapters.id", ondelete="SET NULL"), nullable=True)
    planned_payoff_chapter_id: Mapped[str | None] = mapped_column(Text, ForeignKey("chapters.id", ondelete="SET NULL"), nullable=True)
    actual_payoff_chapter_id: Mapped[str | None] = mapped_column(Text, ForeignKey("chapters.id", ondelete="SET NULL"), nullable=True)
    planned_payoff: Mapped[str] = mapped_column(Text, nullable=False, default="")
    payoff_status: Mapped[str] = mapped_column(Text, nullable=False, default="planned")
    importance_level: Mapped[str] = mapped_column(Text, nullable=False, default="medium")
    importance_score: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    related_character_ids_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    related_entity_ids_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    source: Mapped[str] = mapped_column(Text, nullable=False, default="manual")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class StyleProfile(Base):
    __tablename__ = "style_profiles"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    project_id: Mapped[str] = mapped_column(Text, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    sample_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    profile: Mapped[str] = mapped_column(Text, nullable=False, default="")
    active: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class PromptTemplate(Base):
    __tablename__ = "prompt_templates"
    __table_args__ = (UniqueConstraint("agent_name", "template_name", name="uq_prompt_agent_template"),)

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    agent_name: Mapped[str] = mapped_column(Text, nullable=False)
    template_name: Mapped[str] = mapped_column(Text, nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class AgentModelConfig(Base):
    __tablename__ = "agent_model_configs"
    __table_args__ = (UniqueConstraint("workflow_id", "agent_name", name="uq_agent_model_workflow_agent"),)

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    workflow_id: Mapped[str] = mapped_column(Text, nullable=False)
    agent_name: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class RuntimeSetting(Base):
    __tablename__ = "runtime_settings"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value_json: Mapped[str] = mapped_column(Text, nullable=False, default="null")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class DeepAgentSession(Base):
    __tablename__ = "deep_agent_sessions"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    project_id: Mapped[str] = mapped_column(Text, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    mode: Mapped[str] = mapped_column(Text, nullable=False, default="advisor")
    status: Mapped[str] = mapped_column(Text, nullable=False, default="active")
    objective: Mapped[str] = mapped_column(Text, nullable=False, default="")
    privacy_mode: Mapped[str] = mapped_column(Text, nullable=False, default="metadata_only")
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    state_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class DeepAgentToolCall(Base):
    __tablename__ = "deep_agent_tool_calls"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    session_id: Mapped[str] = mapped_column(Text, ForeignKey("deep_agent_sessions.id", ondelete="CASCADE"), nullable=False)
    project_id: Mapped[str] = mapped_column(Text, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    tool_name: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending_approval")
    risk_level: Mapped[str] = mapped_column(Text, nullable=False, default="medium")
    requires_approval: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    arguments_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    result_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LangSmithTraceLink(Base):
    __tablename__ = "langsmith_trace_links"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    project_id: Mapped[str | None] = mapped_column(Text, ForeignKey("projects.id", ondelete="CASCADE"), nullable=True)
    job_id: Mapped[str | None] = mapped_column(Text, ForeignKey("generation_jobs.id", ondelete="CASCADE"), nullable=True)
    agent_run_id: Mapped[str | None] = mapped_column(Text, ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=True)
    session_id: Mapped[str | None] = mapped_column(Text, ForeignKey("deep_agent_sessions.id", ondelete="SET NULL"), nullable=True)
    trace_mode: Mapped[str] = mapped_column(Text, nullable=False, default="metadata_only")
    langsmith_run_id: Mapped[str] = mapped_column(Text, nullable=False, default="")
    langsmith_url: Mapped[str] = mapped_column(Text, nullable=False, default="")
    payload_policy: Mapped[str] = mapped_column(Text, nullable=False, default="metadata_only")
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class VersionSnapshot(Base):
    __tablename__ = "version_snapshots"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    project_id: Mapped[str] = mapped_column(Text, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    chapter_id: Mapped[str | None] = mapped_column(Text, ForeignKey("chapters.id", ondelete="SET NULL"), nullable=True)
    job_id: Mapped[str | None] = mapped_column(Text, ForeignKey("generation_jobs.id", ondelete="SET NULL"), nullable=True)
    agent_name: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    user_note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    branch_name: Mapped[str] = mapped_column(Text, nullable=False, default="main")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class ExportJob(Base):
    __tablename__ = "export_jobs"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    project_id: Mapped[str] = mapped_column(Text, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    export_format: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="succeeded")
    options_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    output_path: Mapped[str] = mapped_column(Text, nullable=False, default="")
    error_message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class UserFeedback(Base):
    __tablename__ = "user_feedback"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    project_id: Mapped[str] = mapped_column(Text, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    chapter_id: Mapped[str | None] = mapped_column(Text, ForeignKey("chapters.id", ondelete="SET NULL"), nullable=True)
    feedback_type: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
