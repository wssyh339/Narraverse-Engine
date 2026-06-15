from __future__ import annotations

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.responses import success_response
from app.db.session import get_db
from app.schemas.deep_agent import LangSmithEvalRunRequest, LangSmithPromptPullPreviewRequest, LangSmithPromptPushRequest
from app.services.deep_agent_service import deep_agent_langsmith_service


def get_langsmith_status(db: Session = Depends(get_db)):
    return success_response(deep_agent_langsmith_service.langsmith_status(db))


def get_langsmith_runs(job_id: str, db: Session = Depends(get_db)):
    return success_response(deep_agent_langsmith_service.langsmith_runs(db, job_id))


def push_langsmith_prompt(request: LangSmithPromptPushRequest, db: Session = Depends(get_db)):
    return success_response(deep_agent_langsmith_service.push_prompt(db, request))


def pull_langsmith_prompt_preview(request: LangSmithPromptPullPreviewRequest, db: Session = Depends(get_db)):
    return success_response(deep_agent_langsmith_service.pull_prompt_preview(db, request))


def run_langsmith_eval(request: LangSmithEvalRunRequest, db: Session = Depends(get_db)):
    return success_response(deep_agent_langsmith_service.run_eval(db, request))
