from __future__ import annotations

from fastapi import Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.responses import success_response
from app.db.session import get_db
from app.schemas.outline import (
    OutlineDebateChapterAutopilotRequest,
    OutlineDebateCommitRequest,
    OutlineDebateConfirmRequest,
    OutlineDebateInterruptRequest,
    OutlineDebateRunRequest,
    OutlineDebateSessionCreateRequest,
    OutlineDebateUserMessageRequest,
)
from app.services.outline_debate_service import outline_debate_service


def create_outline_debate_session(project_id: str, request: OutlineDebateSessionCreateRequest, db: Session = Depends(get_db)):
    return success_response(outline_debate_service.create_session(db, project_id, request))


def get_outline_debate_session(project_id: str, session_id: str, db: Session = Depends(get_db)):
    return success_response(outline_debate_service.get_session(db, project_id, session_id))


def post_outline_debate_message(project_id: str, session_id: str, request: OutlineDebateUserMessageRequest, db: Session = Depends(get_db)):
    return success_response(outline_debate_service.add_user_message(db, project_id, session_id, request))


def interrupt_outline_debate_session(project_id: str, session_id: str, request: OutlineDebateInterruptRequest, db: Session = Depends(get_db)):
    return success_response(outline_debate_service.interrupt_session(db, project_id, session_id, request))


def run_outline_debate_book(project_id: str, session_id: str, request: OutlineDebateRunRequest, db: Session = Depends(get_db)):
    return success_response(outline_debate_service.run_phase(db, project_id, session_id, "book", request))


def confirm_outline_debate_book(project_id: str, session_id: str, request: OutlineDebateConfirmRequest, db: Session = Depends(get_db)):
    return success_response(outline_debate_service.confirm_phase(db, project_id, session_id, "book", request))


def run_outline_debate_volumes(project_id: str, session_id: str, request: OutlineDebateRunRequest, db: Session = Depends(get_db)):
    return success_response(outline_debate_service.run_phase(db, project_id, session_id, "volumes", request))


def confirm_outline_debate_volumes(project_id: str, session_id: str, request: OutlineDebateConfirmRequest, db: Session = Depends(get_db)):
    return success_response(outline_debate_service.confirm_phase(db, project_id, session_id, "volumes", request))


def run_outline_debate_chapters(project_id: str, session_id: str, request: OutlineDebateRunRequest, db: Session = Depends(get_db)):
    return success_response(outline_debate_service.run_phase(db, project_id, session_id, "chapters", request))


def confirm_outline_debate_chapters(project_id: str, session_id: str, request: OutlineDebateConfirmRequest, db: Session = Depends(get_db)):
    return success_response(outline_debate_service.confirm_phase(db, project_id, session_id, "chapters", request))


def start_outline_debate_chapter_autopilot(project_id: str, session_id: str, request: OutlineDebateChapterAutopilotRequest, db: Session = Depends(get_db)):
    return success_response(outline_debate_service.start_chapter_autopilot(db, project_id, session_id, request))


def commit_outline_debate_candidates(project_id: str, session_id: str, request: OutlineDebateCommitRequest, db: Session = Depends(get_db)):
    return success_response(outline_debate_service.commit_confirmed_candidates(db, project_id, session_id, request))


def stream_outline_debate_book(project_id: str, session_id: str, request: OutlineDebateRunRequest, db: Session = Depends(get_db)):
    outline_debate_service.validate_stream_phase_request(db, project_id, session_id, "book", request)
    return StreamingResponse(
        outline_debate_service.stream_phase(db, project_id, session_id, "book", request),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def stream_outline_debate_volumes(project_id: str, session_id: str, request: OutlineDebateRunRequest, db: Session = Depends(get_db)):
    outline_debate_service.validate_stream_phase_request(db, project_id, session_id, "volumes", request)
    return StreamingResponse(
        outline_debate_service.stream_phase(db, project_id, session_id, "volumes", request),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def stream_outline_debate_chapters(project_id: str, session_id: str, request: OutlineDebateRunRequest, db: Session = Depends(get_db)):
    outline_debate_service.validate_stream_phase_request(db, project_id, session_id, "chapters", request)
    return StreamingResponse(
        outline_debate_service.stream_phase(db, project_id, session_id, "chapters", request),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
