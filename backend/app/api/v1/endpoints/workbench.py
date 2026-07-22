from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.responses import success_response
from app.db.session import get_db
from app.schemas.workbench import (
    CreateEditorProposalRequest,
    CreateManualChapterRequest,
    CreateMethodPackRequest,
    CreateNoteRequest,
    CreateReferenceAssetRequest,
    CreateSnapshotRequest,
    CreateVolumeRequest,
    ImportNovelRequest,
    ReorderChaptersRequest,
    ReviewPlanRequest,
    TrashChaptersRequest,
    UpdateNoteRequest,
    UpdateVolumeRequest,
)
from app.services.workbench_service import workbench_service


def list_volumes(project_id: str, db: Session = Depends(get_db)):
    return success_response(workbench_service.list_volumes(db, project_id))


def create_volume(project_id: str, request: CreateVolumeRequest, db: Session = Depends(get_db)):
    return success_response(workbench_service.create_volume(db, project_id, request))


def update_volume(project_id: str, volume_id: str, request: UpdateVolumeRequest, db: Session = Depends(get_db)):
    return success_response(workbench_service.update_volume(db, project_id, volume_id, request))


def delete_volume(project_id: str, volume_id: str, db: Session = Depends(get_db)):
    return success_response(workbench_service.delete_volume(db, project_id, volume_id))


def create_chapter(project_id: str, request: CreateManualChapterRequest, db: Session = Depends(get_db)):
    return success_response(workbench_service.create_chapter(db, project_id, request))


def import_novel(project_id: str, request: ImportNovelRequest, db: Session = Depends(get_db)):
    return success_response(workbench_service.import_novel(db, project_id, request))


def create_method_pack(project_id: str, request: CreateMethodPackRequest, db: Session = Depends(get_db)):
    return success_response(workbench_service.create_method_pack(db, project_id, request))


def list_method_packs(project_id: str, db: Session = Depends(get_db)):
    return success_response(workbench_service.list_method_packs(db, project_id))


def create_reference_asset(project_id: str, request: CreateReferenceAssetRequest, db: Session = Depends(get_db)):
    return success_response(workbench_service.create_reference_asset(db, project_id, request))


def list_reference_assets(project_id: str, db: Session = Depends(get_db)):
    return success_response(workbench_service.list_reference_assets(db, project_id))


def review_plan(project_id: str, request: ReviewPlanRequest, db: Session = Depends(get_db)):
    return success_response(workbench_service.build_review_plan(db, project_id, request))


def reorder_chapters(project_id: str, request: ReorderChaptersRequest, db: Session = Depends(get_db)):
    return success_response(workbench_service.reorder_chapters(db, project_id, request))


def list_trash(project_id: str, db: Session = Depends(get_db)):
    return success_response(workbench_service.list_trash(db, project_id))


def trash_chapter(project_id: str, chapter_id: str, db: Session = Depends(get_db)):
    return success_response(workbench_service.trash_chapter(db, project_id, chapter_id))


def trash_chapters(project_id: str, request: TrashChaptersRequest, db: Session = Depends(get_db)):
    return success_response(workbench_service.trash_chapters(db, project_id, request))


def restore_chapter(project_id: str, chapter_id: str, db: Session = Depends(get_db)):
    return success_response(workbench_service.restore_chapter(db, project_id, chapter_id))


def list_notes(project_id: str, db: Session = Depends(get_db)):
    return success_response(workbench_service.list_notes(db, project_id))


def create_note(project_id: str, request: CreateNoteRequest, db: Session = Depends(get_db)):
    return success_response(workbench_service.create_note(db, project_id, request))


def update_note(project_id: str, note_id: str, request: UpdateNoteRequest, db: Session = Depends(get_db)):
    return success_response(workbench_service.update_note(db, project_id, note_id, request))


def delete_note(project_id: str, note_id: str, db: Session = Depends(get_db)):
    return success_response(workbench_service.delete_note(db, project_id, note_id))


def snapshot_chapter(project_id: str, chapter_id: str, request: CreateSnapshotRequest, db: Session = Depends(get_db)):
    return success_response(workbench_service.snapshot_chapter(db, project_id, chapter_id, request))


def list_proposals(project_id: str, chapter_id: str | None = None, db: Session = Depends(get_db)):
    return success_response(workbench_service.list_proposals(db, project_id, chapter_id))


def create_proposal(project_id: str, chapter_id: str, request: CreateEditorProposalRequest, db: Session = Depends(get_db)):
    return success_response(workbench_service.create_proposal(db, project_id, chapter_id, request))


def apply_proposal(project_id: str, proposal_id: str, db: Session = Depends(get_db)):
    return success_response(workbench_service.apply_proposal(db, project_id, proposal_id))


def reject_proposal(project_id: str, proposal_id: str, db: Session = Depends(get_db)):
    return success_response(workbench_service.reject_proposal(db, project_id, proposal_id))


def backup_project(project_id: str, db: Session = Depends(get_db)):
    return success_response(workbench_service.backup_project(db, project_id))
