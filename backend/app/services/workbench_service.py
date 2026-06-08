from __future__ import annotations

import difflib
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.ids import generate_id
from app.core.json import dumps
from app.db import models
from app.db.models import utcnow
from app.schemas.workbench import (
    CreateEditorProposalRequest,
    CreateManualChapterRequest,
    CreateNoteRequest,
    CreateSnapshotRequest,
    CreateVolumeRequest,
    ReorderChaptersRequest,
    TrashChaptersRequest,
    UpdateNoteRequest,
    UpdateVolumeRequest,
)
from app.services.serializers import (
    serialize_chapter,
    serialize_character,
    serialize_editor_proposal,
    serialize_foreshadowing_item,
    serialize_graph_edge,
    serialize_graph_node,
    serialize_note,
    serialize_project,
    serialize_story_bible,
    serialize_story_entity,
    serialize_version_snapshot,
    serialize_volume,
    serialize_world_fact,
)


def _not_found(message: str) -> HTTPException:
    return HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": message})


def _bad_request(message: str) -> HTTPException:
    return HTTPException(status_code=400, detail={"code": "VALIDATION_ERROR", "message": message})


class WorkbenchService:
    def list_volumes(self, db: Session, project_id: str) -> dict:
        self._project(db, project_id)
        rows = (
            db.query(models.Volume)
            .filter(models.Volume.project_id == project_id)
            .order_by(models.Volume.sort_order.asc(), models.Volume.volume_no.asc())
            .all()
        )
        return {"volumes": [serialize_volume(row) for row in rows]}

    def create_volume(self, db: Session, project_id: str, request: CreateVolumeRequest) -> dict:
        self._project(db, project_id)
        next_no = request.volume_no or ((db.query(func.max(models.Volume.volume_no)).filter(models.Volume.project_id == project_id).scalar() or 0) + 1)
        if db.query(models.Volume).filter(models.Volume.project_id == project_id, models.Volume.volume_no == next_no).first():
            raise _bad_request("该分卷序号已存在")
        row = models.Volume(
            id=generate_id("vol"),
            project_id=project_id,
            volume_no=next_no,
            title=request.title,
            outline=request.outline,
            sort_order=next_no,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return {"volume": serialize_volume(row)}

    def update_volume(self, db: Session, project_id: str, volume_id: str, request: UpdateVolumeRequest) -> dict:
        row = self._volume(db, project_id, volume_id)
        for field, value in request.model_dump(exclude_unset=True).items():
            if value is not None:
                setattr(row, field, value)
        db.commit()
        db.refresh(row)
        return {"volume": serialize_volume(row)}

    def delete_volume(self, db: Session, project_id: str, volume_id: str) -> dict:
        row = self._volume(db, project_id, volume_id)
        if db.query(models.Chapter).filter(models.Chapter.project_id == project_id, models.Chapter.volume_no == row.volume_no, models.Chapter.deleted_at.is_(None)).count():
            raise _bad_request("分卷仍包含章节，请先移动或删除章节")
        db.delete(row)
        db.commit()
        return {"deleted": True, "volume_id": volume_id}

    def create_chapter(self, db: Session, project_id: str, request: CreateManualChapterRequest) -> dict:
        project = self._project(db, project_id)
        self._ensure_volume(db, project_id, request.volume_no)
        next_no = (db.query(func.max(models.Chapter.chapter_no)).filter(models.Chapter.project_id == project_id).scalar() or 0) + 1
        next_order = (db.query(func.max(models.Chapter.sort_order)).filter(models.Chapter.project_id == project_id).scalar() or 0) + 1
        row = models.Chapter(
            id=generate_id("chp"),
            project_id=project_id,
            volume_no=request.volume_no,
            chapter_no=next_no,
            title=request.title,
            outline=request.outline,
            word_target=request.word_target or project.chapter_word_target,
            sort_order=next_order,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return {"chapter": serialize_chapter(row)}

    def reorder_chapters(self, db: Session, project_id: str, request: ReorderChaptersRequest) -> dict:
        rows = (
            db.query(models.Chapter)
            .filter(models.Chapter.project_id == project_id, models.Chapter.id.in_(request.chapter_ids), models.Chapter.deleted_at.is_(None))
            .all()
        )
        by_id = {row.id: row for row in rows}
        if len(by_id) != len(request.chapter_ids):
            raise _bad_request("排序列表包含不存在或已删除的章节")
        for index, chapter_id in enumerate(request.chapter_ids, start=1):
            by_id[chapter_id].sort_order = index
        db.commit()
        return {"chapters": [serialize_chapter(by_id[chapter_id]) for chapter_id in request.chapter_ids]}

    def list_trash(self, db: Session, project_id: str) -> dict:
        self._project(db, project_id)
        rows = (
            db.query(models.Chapter)
            .filter(models.Chapter.project_id == project_id, models.Chapter.deleted_at.is_not(None))
            .order_by(models.Chapter.deleted_at.desc())
            .all()
        )
        return {"chapters": [serialize_chapter(row) for row in rows]}

    def trash_chapter(self, db: Session, project_id: str, chapter_id: str) -> dict:
        row = self._chapter(db, project_id, chapter_id)
        row.deleted_at = utcnow()
        db.commit()
        db.refresh(row)
        return {"chapter": serialize_chapter(row)}

    def trash_chapters(self, db: Session, project_id: str, request: TrashChaptersRequest) -> dict:
        self._project(db, project_id)
        unique_ids = list(dict.fromkeys(request.chapter_ids))
        rows = (
            db.query(models.Chapter)
            .filter(models.Chapter.project_id == project_id, models.Chapter.id.in_(unique_ids), models.Chapter.deleted_at.is_(None))
            .all()
        )
        by_id = {row.id: row for row in rows}
        if len(by_id) != len(unique_ids):
            raise _bad_request("批量删除列表包含不存在或已删除的章节")
        deleted_at = utcnow()
        for chapter_id in unique_ids:
            by_id[chapter_id].deleted_at = deleted_at
        db.commit()
        for row in rows:
            db.refresh(row)
        return {"deleted": True, "chapter_ids": unique_ids, "chapters": [serialize_chapter(by_id[chapter_id]) for chapter_id in unique_ids]}

    def restore_chapter(self, db: Session, project_id: str, chapter_id: str) -> dict:
        row = self._chapter(db, project_id, chapter_id)
        row.deleted_at = None
        db.commit()
        db.refresh(row)
        return {"chapter": serialize_chapter(row)}

    def list_notes(self, db: Session, project_id: str) -> dict:
        self._project(db, project_id)
        rows = (
            db.query(models.Note)
            .filter(models.Note.project_id == project_id)
            .order_by(models.Note.is_pinned.desc(), models.Note.sort_order.asc(), models.Note.updated_at.desc())
            .all()
        )
        return {"notes": [serialize_note(row) for row in rows]}

    def create_note(self, db: Session, project_id: str, request: CreateNoteRequest) -> dict:
        self._project(db, project_id)
        if request.parent_id:
            self._note(db, project_id, request.parent_id)
        row = models.Note(
            id=generate_id("nte"),
            project_id=project_id,
            parent_id=request.parent_id,
            note_type=request.note_type,
            title=request.title,
            content=request.content,
            sort_order=request.sort_order,
            is_pinned=1 if request.is_pinned else 0,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return {"note": serialize_note(row)}

    def update_note(self, db: Session, project_id: str, note_id: str, request: UpdateNoteRequest) -> dict:
        row = self._note(db, project_id, note_id)
        updates = request.model_dump(exclude_unset=True)
        if updates.get("parent_id"):
            self._note(db, project_id, updates["parent_id"])
        for field, value in updates.items():
            if field == "is_pinned":
                row.is_pinned = 1 if value else 0
            else:
                setattr(row, field, value)
        db.commit()
        db.refresh(row)
        return {"note": serialize_note(row)}

    def delete_note(self, db: Session, project_id: str, note_id: str) -> dict:
        row = self._note(db, project_id, note_id)
        db.query(models.Note).filter(models.Note.project_id == project_id, models.Note.parent_id == note_id).update({"parent_id": None})
        db.delete(row)
        db.commit()
        return {"deleted": True, "note_id": note_id}

    def snapshot_chapter(self, db: Session, project_id: str, chapter_id: str, request: CreateSnapshotRequest) -> dict:
        chapter = self._chapter(db, project_id, chapter_id)
        version = self._snapshot(db, chapter, "user", request.user_note or "手动快照")
        db.commit()
        db.refresh(version)
        return {"version": serialize_version_snapshot(version)}

    def list_proposals(self, db: Session, project_id: str, chapter_id: str | None = None) -> dict:
        self._project(db, project_id)
        query = db.query(models.EditorProposal).filter(models.EditorProposal.project_id == project_id)
        if chapter_id:
            query = query.filter(models.EditorProposal.chapter_id == chapter_id)
        rows = query.order_by(models.EditorProposal.created_at.desc()).all()
        return {"proposals": [serialize_editor_proposal(row) for row in rows]}

    def create_proposal(self, db: Session, project_id: str, chapter_id: str, request: CreateEditorProposalRequest) -> dict:
        chapter = self._chapter(db, project_id, chapter_id)
        original = request.selected_text or chapter.final_text or chapter.draft_text or chapter.outline
        proposed = self._local_proposal(request.tool_name, original, request.instruction, chapter.title)
        diff = list(difflib.unified_diff(original.splitlines(), proposed.splitlines(), fromfile="当前正文", tofile="AI 提案", lineterm=""))
        row = models.EditorProposal(
            id=generate_id("prp"),
            project_id=project_id,
            chapter_id=chapter_id,
            tool_name=request.tool_name,
            instruction=request.instruction,
            original_content=original,
            proposed_content=proposed,
            diff_json=dumps(diff),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return {"proposal": serialize_editor_proposal(row)}

    def apply_proposal(self, db: Session, project_id: str, proposal_id: str) -> dict:
        proposal = self._proposal(db, project_id, proposal_id)
        if proposal.status != "pending":
            raise _bad_request("只有待审批提案可以应用")
        chapter = self._chapter(db, project_id, proposal.chapter_id)
        self._snapshot(db, chapter, "proposal_apply", f"应用 {proposal.tool_name} 提案前快照")
        chapter.final_text = proposal.proposed_content
        chapter.word_count = len(proposal.proposed_content.replace("\n", ""))
        chapter.status = "drafted"
        proposal.status = "applied"
        proposal.applied_at = utcnow()
        db.commit()
        db.refresh(proposal)
        return {"proposal": serialize_editor_proposal(proposal), "chapter": serialize_chapter(chapter)}

    def reject_proposal(self, db: Session, project_id: str, proposal_id: str) -> dict:
        proposal = self._proposal(db, project_id, proposal_id)
        if proposal.status != "pending":
            raise _bad_request("只有待审批提案可以拒绝")
        proposal.status = "rejected"
        db.commit()
        db.refresh(proposal)
        return {"proposal": serialize_editor_proposal(proposal)}

    def backup_project(self, db: Session, project_id: str) -> dict:
        project = self._project(db, project_id)
        story_bible = db.query(models.StoryBible).filter(models.StoryBible.project_id == project_id).first()
        return {
            "backup": {
                "schema_version": 1,
                "project": serialize_project(project),
                "story_bible": serialize_story_bible(story_bible) if story_bible else None,
                "volumes": [serialize_volume(row) for row in db.query(models.Volume).filter(models.Volume.project_id == project_id).all()],
                "chapters": [serialize_chapter(row) for row in db.query(models.Chapter).filter(models.Chapter.project_id == project_id).all()],
                "notes": [serialize_note(row) for row in db.query(models.Note).filter(models.Note.project_id == project_id).all()],
                "characters": [serialize_character(row) for row in db.query(models.Character).filter(models.Character.project_id == project_id).all()],
                "entities": [serialize_story_entity(row) for row in db.query(models.StoryEntity).filter(models.StoryEntity.project_id == project_id).all()],
                "world_facts": [serialize_world_fact(row) for row in db.query(models.WorldFact).filter(models.WorldFact.project_id == project_id).all()],
                "foreshadowing_items": [serialize_foreshadowing_item(row) for row in db.query(models.ForeshadowingItem).filter(models.ForeshadowingItem.project_id == project_id).all()],
                "graph": {
                    "nodes": [serialize_graph_node(row) for row in db.query(models.GraphNode).filter(models.GraphNode.project_id == project_id).all()],
                    "edges": [serialize_graph_edge(row) for row in db.query(models.GraphEdge).filter(models.GraphEdge.project_id == project_id).all()],
                },
                "editor_proposals": [serialize_editor_proposal(row) for row in db.query(models.EditorProposal).filter(models.EditorProposal.project_id == project_id).all()],
            }
        }

    def _local_proposal(self, tool_name: str, original: str, instruction: str, title: str) -> str:
        text = original.strip()
        requirement = instruction.strip() or "保持人物与设定连续"
        if tool_name == "opening":
            return f"门外传来第三次敲击时，{title}里最不该出现的东西已经摆在桌上。\n\n{text}".strip()
        if tool_name == "continue":
            return f"{text}\n\n然而事情没有按预期结束。新的线索迫使人物重新选择，而代价也随之显现。".strip()
        if tool_name == "review":
            return f"{text}\n\n---\n审稿建议：检查因果链、人物动机和结尾钩子；本次重点要求：{requirement}"
        if tool_name == "inspiration":
            return f"{text}\n\n---\n灵感卡：让一个次要细节连接核心冲突；让盟友提出更昂贵的选择；让结尾证据推翻当前认知。"
        if tool_name == "setting_update":
            return f"{text}\n\n---\n候选设定更新：从本章抽取新增角色状态、实体变化、世界规则与未回收伏笔，确认后写入设定集。"
        if tool_name == "rewrite":
            return f"{requirement}\n\n{text}".strip()
        if tool_name == "polish":
            return f"{text}\n\n空气像被一根看不见的线绷紧，连沉默都带着即将断裂的重量。".strip()
        return f"{text}\n\n优化目标：{requirement}".strip()

    def _snapshot(self, db: Session, chapter: models.Chapter, agent_name: str, user_note: str) -> models.VersionSnapshot:
        version = models.VersionSnapshot(
            id=generate_id("ver"),
            project_id=chapter.project_id,
            chapter_id=chapter.id,
            job_id=None,
            agent_name=agent_name,
            content_type="chapter",
            content=chapter.final_text or chapter.draft_text or chapter.outline,
            metadata_json=dumps({"created_by": agent_name}),
            user_note=user_note,
            branch_name="main",
        )
        db.add(version)
        return version

    def _ensure_volume(self, db: Session, project_id: str, volume_no: int) -> models.Volume:
        row = db.query(models.Volume).filter(models.Volume.project_id == project_id, models.Volume.volume_no == volume_no).first()
        if row is None:
            row = models.Volume(id=generate_id("vol"), project_id=project_id, volume_no=volume_no, title=f"第{volume_no}卷", sort_order=volume_no)
            db.add(row)
            db.flush()
        return row

    def _project(self, db: Session, project_id: str) -> models.Project:
        row = db.get(models.Project, project_id)
        if row is None:
            raise _not_found("项目不存在")
        return row

    def _volume(self, db: Session, project_id: str, volume_id: str) -> models.Volume:
        row = db.get(models.Volume, volume_id)
        if row is None or row.project_id != project_id:
            raise _not_found("分卷不存在")
        return row

    def _chapter(self, db: Session, project_id: str, chapter_id: str) -> models.Chapter:
        row = db.get(models.Chapter, chapter_id)
        if row is None or row.project_id != project_id:
            raise _not_found("章节不存在")
        return row

    def _note(self, db: Session, project_id: str, note_id: str) -> models.Note:
        row = db.get(models.Note, note_id)
        if row is None or row.project_id != project_id:
            raise _not_found("笔记不存在")
        return row

    def _proposal(self, db: Session, project_id: str, proposal_id: str) -> models.EditorProposal:
        row = db.get(models.EditorProposal, proposal_id)
        if row is None or row.project_id != project_id:
            raise _not_found("编辑提案不存在")
        return row


workbench_service = WorkbenchService()
