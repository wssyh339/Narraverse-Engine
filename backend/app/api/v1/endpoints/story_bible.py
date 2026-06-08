from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.responses import success_response
from app.db.session import get_db
from app.schemas.story_bible import UpdateStoryBibleRequest
from app.services.project_service import project_service


def update_story_bible(project_id: str, request: UpdateStoryBibleRequest, db: Session = Depends(get_db)):
    return success_response(project_service.update_story_bible(db, project_id, request))
