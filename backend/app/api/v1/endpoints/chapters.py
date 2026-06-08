from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.responses import success_response
from app.db.session import get_db
from app.schemas.chapter import PlanChaptersRequest
from app.services.chapter_service import chapter_service


def plan_chapters(project_id: str, request: PlanChaptersRequest, db: Session = Depends(get_db)):
    return success_response(chapter_service.plan_chapters(db, project_id, request))
