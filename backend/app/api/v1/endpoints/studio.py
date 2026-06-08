from __future__ import annotations

# legacy compatibility facade: new routes import domain endpoint modules instead.

from typing import Any

from fastapi import Depends, WebSocket
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.responses import success_response
from app.db.session import get_db
from app.schemas.chapter import PlanChaptersRequest
from app.schemas.canon import CanonRunRequest
from app.schemas.studio import (
    AgentPromptUpdateRequest,
    BatchGenerateRequest,
    BranchVersionRequest,
    ChapterChatRequest,
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


def plan_chapters(project_id: str, request: PlanChaptersRequest, db: Session = Depends(get_db)):
    return success_response(studio_service.plan_chapters(db, project_id, request))


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


def list_workflows():
    return success_response(studio_service.list_workflows())


def get_agent(agent_name: str, db: Session = Depends(get_db)):
    return success_response(studio_service.get_agent(db, agent_name))


def update_agent_prompt(agent_name: str, request: AgentPromptUpdateRequest, db: Session = Depends(get_db)):
    return success_response(studio_service.update_agent_prompt(db, agent_name, request))


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
    await websocket.send_json({"type": "job", "job_id": job_id, "message": "任务 WebSocket 已连接"})
    await websocket.close()
