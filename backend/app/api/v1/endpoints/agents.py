from __future__ import annotations

from fastapi import Depends
from sqlalchemy.orm import Session

from app.api.v1.endpoints.studio import (
    create_creation_session,
    creation_session_canon_preview,
    creation_session_commit,
    creation_session_constitution,
    creation_session_constitution_review,
    creation_session_core_conflict,
    creation_session_market_position,
    creation_session_protagonists,
    creation_session_seed,
    creation_session_worldviews,
    create_prompt_template,
    creation_star_commit,
    creation_star_draw,
    creation_star_options,
    export_prompt_templates,
    get_creation_profile,
    get_creation_session,
    get_agent,
    import_prompt_templates,
    list_agents,
    list_prompt_templates,
    list_workflows,
    restore_agent_prompt,
    update_agent_prompt,
)
from app.core.responses import success_response
from app.db.session import get_db
from app.schemas.studio import AgentModelConfigRequest, CreationBasicSuggestionsRequest
from app.services.studio_service import studio_service


def creation_basic_suggestions(project_id: str, request: CreationBasicSuggestionsRequest, db: Session = Depends(get_db)):
    return success_response(studio_service.creation_basic_suggestions(db, project_id, request))


def list_llm_models():
    return success_response(studio_service.list_llm_models())


def list_agent_model_configs(db: Session = Depends(get_db)):
    return success_response(studio_service.list_agent_model_configs(db))


def update_agent_model_config(request: AgentModelConfigRequest, db: Session = Depends(get_db)):
    return success_response(studio_service.update_agent_model_config(db, request))


def delete_agent_model_config(workflow_id: str, agent_name: str, db: Session = Depends(get_db)):
    return success_response(studio_service.delete_agent_model_config(db, workflow_id, agent_name))
