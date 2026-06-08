from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.responses import success_response
from app.db.session import get_db
from app.schemas.project import CreateProjectRequest
from app.services.project_service import project_service


def create_project(request: CreateProjectRequest, db: Session = Depends(get_db)):
    return success_response(project_service.create_project(db, request))
