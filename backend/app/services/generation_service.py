from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db import models
from app.services.serializers import serialize_job


class GenerationService:
    def get_job(self, db: Session, job_id: str) -> dict:
        job = db.get(models.GenerationJob, job_id)
        if job is None:
            raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "任务不存在"})
        return {"job": serialize_job(job)}


generation_service = GenerationService()
