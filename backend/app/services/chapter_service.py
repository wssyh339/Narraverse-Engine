from pathlib import Path
import hashlib

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import LLMProviderResolver, get_settings
from app.core.ids import generate_id
from app.core.json import dumps
from app.db import models
from app.schemas.chapter import PlanChaptersRequest
from app.services.serializers import serialize_job


def _not_found(message: str) -> HTTPException:
    return HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": message})


def _conflict(message: str) -> HTTPException:
    return HTTPException(status_code=409, detail={"code": "CONFLICT", "message": message})


def _sha256_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


class ChapterService:
    def plan_chapters(self, db: Session, project_id: str, request: PlanChaptersRequest) -> dict:
        project = db.get(models.Project, project_id)
        if project is None:
            raise _not_found("项目不存在")

        existing_job = (
            db.query(models.GenerationJob)
            .filter(
                models.GenerationJob.project_id == project_id,
                models.GenerationJob.idempotency_key == request.idempotency_key,
            )
            .first()
        )
        if existing_job is not None:
            return {"job": serialize_job(existing_job)}

        end_chapter_no = request.start_chapter_no + request.chapter_count - 1
        existing_chapters = (
            db.query(models.Chapter)
            .filter(
                models.Chapter.project_id == project_id,
                models.Chapter.chapter_no >= request.start_chapter_no,
                models.Chapter.chapter_no <= end_chapter_no,
            )
            .all()
        )
        if existing_chapters and not request.overwrite_existing:
            raise _conflict("章节范围已存在，且 overwrite_existing=false")

        existing_by_no = {chapter.chapter_no: chapter for chapter in existing_chapters}
        for offset in range(request.chapter_count):
            chapter_no = request.start_chapter_no + offset
            title = f"第{chapter_no}章"
            outline = f"{request.volume_title}：{request.outline_requirement}"
            if chapter_no in existing_by_no:
                chapter = existing_by_no[chapter_no]
                chapter.title = title
                chapter.outline = outline
                chapter.status = "planned"
                continue
            db.add(
                models.Chapter(
                    id=generate_id("chp"),
                    project_id=project_id,
                    volume_no=1,
                    chapter_no=chapter_no,
                    title=title,
                    outline=outline,
                    draft_text="",
                    revision_notes="",
                    status="planned",
                    word_target=project.chapter_word_target,
                    word_count=0,
                )
            )

        settings = get_settings()
        provider_config = LLMProviderResolver(settings).resolve(request.model)
        job_id = generate_id("job")
        progress = {
            "current_step": "queued",
            "total_steps": 4,
            "completed_steps": 0,
            "message": "章节规划任务已入队",
        }
        request_payload = {
            "volume_title": request.volume_title,
            "start_chapter_no": request.start_chapter_no,
            "chapter_count": request.chapter_count,
            "outline_requirement": request.outline_requirement,
            "overwrite_existing": request.overwrite_existing,
            "idempotency_key": request.idempotency_key,
            "model": provider_config.model,
            "provider": provider_config.provider,
        }
        request_json = dumps(request_payload)
        job = models.GenerationJob(
            id=job_id,
            project_id=project_id,
            chapter_id=None,
            job_type="plan_chapters",
            status="queued",
            run_id=generate_id("run"),
            idempotency_key=request.idempotency_key,
            model=provider_config.model,
            request_json=request_json,
            progress_json=dumps(progress),
            result_json=None,
            error_message=None,
        )
        db.add(job)
        self._write_request_artifact(db, settings.job_artifact_dir, job_id, request_json)
        db.add(
            models.EventLog(
                id=generate_id("evt"),
                project_id=project_id,
                actor_type="system",
                event_type="chapter_plan_job_queued",
                entity_type="generation_job",
                entity_id=job_id,
                payload_json=dumps({"chapter_count": request.chapter_count, "start_chapter_no": request.start_chapter_no}),
            )
        )
        db.commit()
        db.refresh(job)
        return {"job": serialize_job(job)}

    def _write_request_artifact(self, db: Session, artifact_dir: str, job_id: str, request_json: str) -> None:
        run_dir = Path(artifact_dir) / job_id
        run_dir.mkdir(parents=True, exist_ok=True)
        path = run_dir / "request.json"
        path.write_text(request_json, encoding="utf-8")
        content_hash = _sha256_text(request_json)
        db.add(
            models.JobArtifact(
                id=generate_id("art"),
                job_id=job_id,
                artifact_type="prompt",
                path=str(path),
                content_hash=content_hash,
                byte_size=path.stat().st_size,
            )
        )


chapter_service = ChapterService()
