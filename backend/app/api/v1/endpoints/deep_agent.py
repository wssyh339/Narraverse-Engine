from __future__ import annotations

from collections.abc import Iterable

from fastapi import Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.json import dumps
from app.core.responses import success_response
from app.db.session import get_db
from app.schemas.deep_agent import DeepAgentChatRequest, DeepAgentConfigUpdateRequest, DeepAgentSessionCreateRequest
from app.services.deep_agent_service import deep_agent_langsmith_service


def get_deep_agent_config(db: Session = Depends(get_db)):
    return success_response(deep_agent_langsmith_service.get_config(db))


def update_deep_agent_config(request: DeepAgentConfigUpdateRequest, db: Session = Depends(get_db)):
    return success_response(deep_agent_langsmith_service.update_config(db, request))


def create_deep_agent_session(project_id: str, request: DeepAgentSessionCreateRequest, db: Session = Depends(get_db)):
    return success_response(deep_agent_langsmith_service.create_session(db, project_id, request))


def list_deep_agent_sessions(project_id: str, db: Session = Depends(get_db)):
    return success_response(deep_agent_langsmith_service.list_sessions(db, project_id))


def get_deep_agent_session(project_id: str, session_id: str, db: Session = Depends(get_db)):
    return success_response(deep_agent_langsmith_service.get_session(db, project_id, session_id))


def _sse(events: Iterable[dict]) -> Iterable[str]:
    for event in events:
        yield f"data: {dumps(event)}\n\n"


def stream_deep_agent_chat(project_id: str, session_id: str, request: DeepAgentChatRequest, db: Session = Depends(get_db)):
    events = deep_agent_langsmith_service.run_chat(db, project_id, session_id, request)
    return StreamingResponse(_sse(events), media_type="text/event-stream")


def approve_deep_agent_tool_call(project_id: str, tool_call_id: str, db: Session = Depends(get_db)):
    return success_response(deep_agent_langsmith_service.approve_tool_call(db, project_id, tool_call_id))


def reject_deep_agent_tool_call(project_id: str, tool_call_id: str, db: Session = Depends(get_db)):
    return success_response(deep_agent_langsmith_service.reject_tool_call(db, project_id, tool_call_id))
