from __future__ import annotations

# legacy compatibility facade: new routes import domain endpoint modules instead.

import asyncio
from typing import Any

from fastapi import BackgroundTasks, Depends, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.responses import success_response
from app.db import models
from app.db.session import SessionLocal, get_db
from app.schemas.chapter import PlanChaptersRequest
from app.schemas.canon import CanonRunRequest
from app.schemas.outline import (
    BookOutlineCommitRequest,
    BookOutlineGenerateRequest,
    ChapterOutlineBatchGenerateRequest,
    ChapterOutlineCommitRequest,
)
from app.schemas.studio import (
    AgentPromptUpdateRequest,
    BatchGenerateRequest,
    BranchVersionRequest,
    CanonBulkArchiveRequest,
    CanonDuplicateScanRequest,
    CanonExportRequest,
    CanonFolderRequest,
    CanonLockFieldsRequest,
    CanonNodeMoveRequest,
    CanonProposalDecisionRequest,
    CanonRollbackRequest,
    ChapterChatRequest,
    CreationSessionCardRequest,
    CreationSessionCommitRequest,
    CreationSessionCreateRequest,
    CreationSessionRunRequest,
    CreationSessionSeedRequest,
    CreationStarCommitRequest,
    CreationStarDrawRequest,
    CreateCharacterRequest,
    CreateEntityRequest,
    CreateForeshadowingRequest,
    CreateWorldFactRequest,
    DraftChapterRequest,
    ExportRequest,
    ExportTemplateRequest,
    GenerateSettingRequest,
    GenerateStoryBibleRequest,
    ImportPromptTemplatesRequest,
    JobControlRequest,
    LearnStyleRequest,
    PartialRewriteRequest,
    PayoffForeshadowingRequest,
    PromptTemplateRequest,
    QueryKnowledgeRequest,
    RewriteChapterRequest,
    RollbackVersionRequest,
    SummaryRequest,
    TextToolRequest,
    UpdateChapterRequest,
    UpdateCharacterRequest,
    UpdateEntityRequest,
    UpdateForeshadowingRequest,
    UpdateProjectRequest,
    UpdateWorldFactRequest,
    VersionCompareRequest,
    WriteGenerateRequest,
)
from app.services.project_service import project_service
from app.services.serializers import serialize_job
from app.services.canon_service import get_canon_store as load_canon_store
from app.services.canon_service import get_final_outline, run_canon_workflow
from app.services.studio_service import studio_service


def list_projects(db: Session = Depends(get_db)):
    return success_response(project_service.list_projects(db))


def get_project(project_id: str, db: Session = Depends(get_db)):
    return success_response(project_service.get_project(db, project_id))


def update_project(project_id: str, request: UpdateProjectRequest, db: Session = Depends(get_db)):
    return success_response(project_service.update_project(db, project_id, request))


def delete_project(project_id: str, db: Session = Depends(get_db)):
    return success_response(project_service.delete_project(db, project_id))


def duplicate_project(project_id: str, db: Session = Depends(get_db)):
    return success_response(project_service.duplicate_project(db, project_id))


def get_project_state(project_id: str, db: Session = Depends(get_db)):
    return success_response(project_service.get_state(db, project_id))


def put_project_state(project_id: str, payload: dict[str, Any], db: Session = Depends(get_db)):
    return success_response(project_service.put_state(db, project_id, payload))


def get_story_bible(project_id: str, db: Session = Depends(get_db)):
    return success_response(project_service.get_story_bible(db, project_id))


def generate_story_bible(project_id: str, request: GenerateStoryBibleRequest, db: Session = Depends(get_db)):
    return success_response(studio_service.generate_story_bible(db, project_id, request))


def plan_chapters(project_id: str, request: PlanChaptersRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    return success_response(studio_service.plan_chapters(db, project_id, request, background_tasks=background_tasks))


def generate_book_outline(project_id: str, request: BookOutlineGenerateRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    return success_response(studio_service.generate_book_outline(db, project_id, request, background_tasks=background_tasks))


def commit_book_outline(project_id: str, request: BookOutlineCommitRequest, db: Session = Depends(get_db)):
    return success_response(studio_service.commit_book_outline(db, project_id, request))


def generate_chapter_outlines_batch(project_id: str, request: ChapterOutlineBatchGenerateRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    return success_response(studio_service.generate_chapter_outlines_batch(db, project_id, request, background_tasks=background_tasks))


def commit_chapter_outlines(project_id: str, request: ChapterOutlineCommitRequest, db: Session = Depends(get_db)):
    return success_response(studio_service.commit_chapter_outlines(db, project_id, request))


def list_chapters(project_id: str, db: Session = Depends(get_db)):
    return success_response(studio_service.list_chapters(db, project_id))


def get_chapter(project_id: str, chapter_id: str, db: Session = Depends(get_db)):
    return success_response(studio_service.get_chapter(db, project_id, chapter_id))


def update_chapter(project_id: str, chapter_id: str, request: UpdateChapterRequest, db: Session = Depends(get_db)):
    return success_response(studio_service.update_chapter(db, project_id, chapter_id, request))


def draft_chapter(project_id: str, chapter_id: str, request: DraftChapterRequest, db: Session = Depends(get_db)):
    return success_response(studio_service.draft_chapter(db, project_id, chapter_id, request))


def rewrite_chapter(project_id: str, chapter_id: str, request: RewriteChapterRequest, db: Session = Depends(get_db)):
    return success_response(studio_service.rewrite_chapter(db, project_id, chapter_id, request))


def partial_rewrite_chapter(project_id: str, chapter_id: str, request: PartialRewriteRequest, db: Session = Depends(get_db)):
    return success_response(studio_service.partial_rewrite_chapter(db, project_id, chapter_id, request))


def stream_chapter_chat(project_id: str, chapter_id: str, request: ChapterChatRequest, db: Session = Depends(get_db)):
    return StreamingResponse(
        studio_service.stream_chapter_chat(db, project_id, chapter_id, request),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def list_agents(db: Session = Depends(get_db)):
    return success_response(studio_service.list_agents(db))


def creation_star_options():
    return success_response(studio_service.creation_star_options())


def creation_star_draw(project_id: str, request: CreationStarDrawRequest, db: Session = Depends(get_db)):
    return success_response(studio_service.creation_star_draw(db, project_id, request))


def creation_star_commit(project_id: str, request: CreationStarCommitRequest, db: Session = Depends(get_db)):
    return success_response(studio_service.creation_star_commit(db, project_id, request))


def create_creation_session(project_id: str, request: CreationSessionCreateRequest, db: Session = Depends(get_db)):
    return success_response(studio_service.create_creation_session(db, project_id, request))


def get_creation_session(project_id: str, session_id: str, db: Session = Depends(get_db)):
    return success_response(studio_service.get_creation_session(db, project_id, session_id))


def creation_session_worldviews(project_id: str, session_id: str, request: CreationSessionCardRequest, db: Session = Depends(get_db)):
    return success_response(studio_service.creation_session_worldviews(db, project_id, session_id, request))


def creation_session_protagonists(project_id: str, session_id: str, request: CreationSessionCardRequest, db: Session = Depends(get_db)):
    return success_response(studio_service.creation_session_protagonists(db, project_id, session_id, request))


def creation_session_market_position(project_id: str, session_id: str, request: CreationSessionCardRequest, db: Session = Depends(get_db)):
    return success_response(studio_service.creation_session_market_position(db, project_id, session_id, request))


def creation_session_seed(project_id: str, session_id: str, request: CreationSessionSeedRequest, db: Session = Depends(get_db)):
    return success_response(studio_service.creation_session_seed(db, project_id, session_id, request))


def creation_session_core_conflict(project_id: str, session_id: str, request: CreationSessionRunRequest, db: Session = Depends(get_db)):
    return success_response(studio_service.creation_session_core_conflict(db, project_id, session_id, request))


def creation_session_constitution(project_id: str, session_id: str, request: CreationSessionRunRequest, db: Session = Depends(get_db)):
    return success_response(studio_service.creation_session_constitution(db, project_id, session_id, request))


def creation_session_constitution_review(project_id: str, session_id: str, request: CreationSessionRunRequest, db: Session = Depends(get_db)):
    return success_response(studio_service.creation_session_constitution_review(db, project_id, session_id, request))


def creation_session_canon_preview(project_id: str, session_id: str, request: CreationSessionRunRequest, db: Session = Depends(get_db)):
    return success_response(studio_service.creation_session_canon_preview(db, project_id, session_id, request))


def creation_session_commit(project_id: str, session_id: str, request: CreationSessionCommitRequest, db: Session = Depends(get_db)):
    return success_response(studio_service.creation_session_commit(db, project_id, session_id, request))


def run_canon_studio(project_id: str, request: CanonRunRequest, db: Session = Depends(get_db)):
    project_service.get_project(db, project_id)
    payload = request.model_copy(update={"project_id": project_id})
    return success_response(run_canon_workflow(payload).model_dump(mode="json"))


def get_canon_studio_store(project_id: str, db: Session = Depends(get_db)):
    project_service.get_project(db, project_id)
    return success_response({"store": load_canon_store(project_id)})


def get_canon_studio_final_outline(project_id: str, db: Session = Depends(get_db)):
    project_service.get_project(db, project_id)
    return success_response(get_final_outline(project_id))


def list_workflows(db: Session = Depends(get_db)):
    return success_response(studio_service.list_workflows(db))


def get_agent(agent_name: str, db: Session = Depends(get_db)):
    return success_response(studio_service.get_agent(db, agent_name))


def update_agent_prompt(agent_name: str, request: AgentPromptUpdateRequest, db: Session = Depends(get_db)):
    return success_response(studio_service.update_agent_prompt(db, agent_name, request))


def restore_agent_prompt(agent_name: str, db: Session = Depends(get_db)):
    return success_response(studio_service.restore_agent_prompt(db, agent_name))


def create_prompt_template(request: PromptTemplateRequest, db: Session = Depends(get_db)):
    return success_response(studio_service.create_prompt_template(db, request))


def list_prompt_templates(db: Session = Depends(get_db)):
    return success_response(studio_service.list_prompt_templates(db))


def import_prompt_templates(request: ImportPromptTemplatesRequest, db: Session = Depends(get_db)):
    return success_response(studio_service.import_prompt_templates(db, request))


def export_prompt_templates(db: Session = Depends(get_db)):
    return success_response(studio_service.export_prompt_templates(db))


def write_generate(request: WriteGenerateRequest, db: Session = Depends(get_db)):
    return success_response(studio_service.write_generate(db, request))


def batch_generate(request: BatchGenerateRequest, db: Session = Depends(get_db)):
    return success_response(studio_service.batch_generate(db, request))


def pause_job(request: JobControlRequest, db: Session = Depends(get_db)):
    return success_response(studio_service.control_job(db, request, "pause"))


def resume_job(request: JobControlRequest, db: Session = Depends(get_db)):
    return success_response(studio_service.control_job(db, request, "resume"))


def cancel_job(request: JobControlRequest, db: Session = Depends(get_db)):
    return success_response(studio_service.control_job(db, request, "cancel"))


def get_job(job_id: str, db: Session = Depends(get_db)):
    return success_response(studio_service.get_job(db, job_id))


def get_agent_runs(job_id: str, db: Session = Depends(get_db)):
    return success_response(studio_service.get_agent_runs(db, job_id))


def retry_job(job_id: str, db: Session = Depends(get_db)):
    return success_response(studio_service.retry_job(db, job_id))


def list_versions(db: Session = Depends(get_db)):
    return success_response(studio_service.list_versions(db))


def list_chapter_versions(chapter_id: str, db: Session = Depends(get_db)):
    return success_response(studio_service.list_versions(db, chapter_id))


def compare_versions(request: VersionCompareRequest, db: Session = Depends(get_db)):
    return success_response(studio_service.compare_versions(db, request))


def rollback_version(version_id: str, request: RollbackVersionRequest, db: Session = Depends(get_db)):
    return success_response(studio_service.rollback_version(db, version_id, request))


def branch_version(version_id: str, request: BranchVersionRequest, db: Session = Depends(get_db)):
    return success_response(studio_service.branch_version(db, version_id, request))


def list_foreshadowing(project_id: str, db: Session = Depends(get_db)):
    return success_response(studio_service.list_foreshadowing(db, project_id))


def create_foreshadowing(project_id: str, request: CreateForeshadowingRequest, db: Session = Depends(get_db)):
    return success_response(studio_service.create_foreshadowing(db, project_id, request))


def update_foreshadowing(project_id: str, item_id: str, request: UpdateForeshadowingRequest, db: Session = Depends(get_db)):
    return success_response(studio_service.update_foreshadowing(db, project_id, item_id, request))


def delete_foreshadowing(project_id: str, item_id: str, db: Session = Depends(get_db)):
    return success_response(studio_service.delete_foreshadowing(db, project_id, item_id))


def payoff_foreshadowing(project_id: str, item_id: str, request: PayoffForeshadowingRequest, db: Session = Depends(get_db)):
    return success_response(studio_service.payoff_foreshadowing(db, project_id, item_id, request))


def list_characters(project_id: str, db: Session = Depends(get_db)):
    return success_response(studio_service.list_characters(db, project_id))


def create_character(project_id: str, request: CreateCharacterRequest, db: Session = Depends(get_db)):
    return success_response(studio_service.create_character(db, project_id, request))


def get_character(project_id: str, character_id: str, db: Session = Depends(get_db)):
    return success_response(studio_service.get_character(db, project_id, character_id))


def update_character(project_id: str, character_id: str, request: UpdateCharacterRequest, db: Session = Depends(get_db)):
    return success_response(studio_service.update_character(db, project_id, character_id, request))


def delete_character(project_id: str, character_id: str, db: Session = Depends(get_db)):
    return success_response(studio_service.delete_character(db, project_id, character_id))


def list_entities(project_id: str, db: Session = Depends(get_db)):
    return success_response(studio_service.list_entities(db, project_id))


def create_entity(project_id: str, request: CreateEntityRequest, db: Session = Depends(get_db)):
    return success_response(studio_service.create_entity(db, project_id, request))


def update_entity(project_id: str, entity_id: str, request: UpdateEntityRequest, db: Session = Depends(get_db)):
    return success_response(studio_service.update_entity(db, project_id, entity_id, request))


def delete_entity(project_id: str, entity_id: str, db: Session = Depends(get_db)):
    return success_response(studio_service.delete_entity(db, project_id, entity_id))


def list_world_facts(project_id: str, db: Session = Depends(get_db)):
    return success_response(studio_service.list_world_facts(db, project_id))


def create_world_fact(project_id: str, request: CreateWorldFactRequest, db: Session = Depends(get_db)):
    return success_response(studio_service.create_world_fact(db, project_id, request))


def update_world_fact(project_id: str, fact_id: str, request: UpdateWorldFactRequest, db: Session = Depends(get_db)):
    return success_response(studio_service.update_world_fact(db, project_id, fact_id, request))


def delete_world_fact(project_id: str, fact_id: str, db: Session = Depends(get_db)):
    return success_response(studio_service.delete_world_fact(db, project_id, fact_id))


def generate_settings(project_id: str, request: GenerateSettingRequest, db: Session = Depends(get_db)):
    return success_response(studio_service.generate_settings(db, project_id, request))


def list_canon_tree(project_id: str, db: Session = Depends(get_db)):
    return success_response(studio_service.list_canon_tree(db, project_id))


def get_canon_health(project_id: str, db: Session = Depends(get_db)):
    return success_response(studio_service.get_canon_health(db, project_id))


def create_canon_folder(project_id: str, request: CanonFolderRequest, db: Session = Depends(get_db)):
    return success_response(studio_service.create_canon_folder(db, project_id, request))


def move_canon_node(project_id: str, node_id: str, request: CanonNodeMoveRequest, db: Session = Depends(get_db)):
    return success_response(studio_service.move_canon_node(db, project_id, node_id, request))


def set_canon_locks(project_id: str, ref_type: str, ref_id: str, request: CanonLockFieldsRequest, db: Session = Depends(get_db)):
    return success_response(studio_service.set_canon_locks(db, project_id, ref_type, ref_id, request))


def get_canon_impact(project_id: str, ref_type: str, ref_id: str, db: Session = Depends(get_db)):
    return success_response(studio_service.get_canon_impact(db, project_id, ref_type, ref_id))


def scan_canon_duplicates(project_id: str, request: CanonDuplicateScanRequest, db: Session = Depends(get_db)):
    return success_response(studio_service.scan_canon_duplicates(db, project_id, request))


def export_canon_package(project_id: str, format: str = "json", db: Session = Depends(get_db)):
    return success_response(studio_service.export_canon_package(db, project_id, CanonExportRequest(format=format)))


def list_canon_versions(project_id: str, ref_type: str, ref_id: str, db: Session = Depends(get_db)):
    return success_response(studio_service.list_canon_versions(db, project_id, ref_type, ref_id))


def rollback_canon_version(project_id: str, ref_type: str, ref_id: str, version_id: str, request: CanonRollbackRequest, db: Session = Depends(get_db)):
    return success_response(studio_service.rollback_canon_version(db, project_id, ref_type, ref_id, version_id, request))


def list_canon_proposals(project_id: str, status: str | None = None, db: Session = Depends(get_db)):
    return success_response(studio_service.list_canon_proposals(db, project_id, status=status))


def approve_canon_proposal(project_id: str, proposal_id: str, request: CanonProposalDecisionRequest | None = None, db: Session = Depends(get_db)):
    return success_response(studio_service.approve_canon_proposal(db, project_id, proposal_id, request))


def reject_canon_proposal(project_id: str, proposal_id: str, request: CanonProposalDecisionRequest | None = None, db: Session = Depends(get_db)):
    return success_response(studio_service.reject_canon_proposal(db, project_id, proposal_id, request))


def archive_canon_items(project_id: str, request: CanonBulkArchiveRequest, db: Session = Depends(get_db)):
    return success_response(studio_service.archive_canon_items(db, project_id, request))


def get_graph(project_id: str, db: Session = Depends(get_db)):
    return success_response(studio_service.get_graph(db, project_id))


def get_subgraph(project_id: str, chapter_id: str | None = None, db: Session = Depends(get_db)):
    return success_response(studio_service.get_graph(db, project_id, chapter_id))


def refresh_canon(project_id: str, db: Session = Depends(get_db)):
    return success_response(studio_service.refresh_canon(db, project_id))


def get_canon_context(project_id: str, chapter_id: str | None = None, db: Session = Depends(get_db)):
    return success_response(studio_service.build_canon_context(db, project_id, chapter_id))


def summary(request: SummaryRequest, db: Session = Depends(get_db)):
    return success_response(studio_service.generate_summary(db, request))


def foreshadowing(request: TextToolRequest, db: Session = Depends(get_db)):
    return success_response(studio_service.foreshadowing(db, request))


def cliffhanger(request: TextToolRequest, db: Session = Depends(get_db)):
    return success_response(studio_service.cliffhanger(db, request))


def fact_check(request: TextToolRequest, db: Session = Depends(get_db)):
    return success_response(studio_service.fact_check(db, request))


def consistency_check(request: TextToolRequest, db: Session = Depends(get_db)):
    return success_response(studio_service.consistency_check(db, request))


def learn_style(request: LearnStyleRequest, db: Session = Depends(get_db)):
    return success_response(studio_service.learn_style(db, request))


def query_knowledge(request: QueryKnowledgeRequest, db: Session = Depends(get_db)):
    return success_response(studio_service.query_knowledge(db, request))


def export_project(request: ExportRequest, db: Session = Depends(get_db)):
    return success_response(studio_service.export(db, request))


def export_templates():
    return success_response(studio_service.export_templates())


def create_export_template(request: ExportTemplateRequest):
    return success_response(studio_service.create_export_template(request))


async def progress_websocket(websocket: WebSocket):
    await websocket.accept()
    await websocket.send_json({"type": "connected", "message": "进度 WebSocket 已连接"})
    await websocket.close()


async def job_websocket(websocket: WebSocket, job_id: str):
    await websocket.accept()
    try:
        while True:
            db = SessionLocal()
            try:
                job = db.get(models.GenerationJob, job_id)
                if job is None:
                    await websocket.send_json({"type": "job", "job_id": job_id, "message": "任务 WebSocket 已连接", "job": None})
                    break
                payload = serialize_job(job)
            finally:
                db.close()
            await websocket.send_json({"type": "job", "job_id": job_id, "job": payload})
            if payload["status"] in {"succeeded", "failed", "cancelled", "canceled"}:
                break
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        return
    await websocket.close()
