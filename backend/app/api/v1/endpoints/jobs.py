from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.responses import success_response
from app.db.session import get_db
from app.services.generation_service import generation_service


def get_job(job_id: str, db: Session = Depends(get_db)):
    return success_response(generation_service.get_job(db, job_id))
