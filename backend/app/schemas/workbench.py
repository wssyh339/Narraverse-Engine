from typing import Literal

from pydantic import Field

from app.schemas.common import APIModel


class CreateVolumeRequest(APIModel):
    title: str = Field(min_length=1, max_length=160)
    outline: str = ""
    volume_no: int | None = Field(default=None, ge=1)


class UpdateVolumeRequest(APIModel):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    outline: str | None = None
    status: str | None = None
    sort_order: int | None = Field(default=None, ge=0)


class CreateManualChapterRequest(APIModel):
    volume_no: int = Field(default=1, ge=1)
    title: str = Field(min_length=1, max_length=200)
    outline: str = ""
    word_target: int | None = Field(default=None, ge=1, le=20000)


class ReorderChaptersRequest(APIModel):
    chapter_ids: list[str] = Field(min_length=1)


class TrashChaptersRequest(APIModel):
    chapter_ids: list[str] = Field(min_length=1)


class CreateNoteRequest(APIModel):
    parent_id: str | None = None
    note_type: Literal["note", "folder", "inspiration"] = "note"
    title: str = Field(min_length=1, max_length=200)
    content: str = ""
    sort_order: int = Field(default=0, ge=0)
    is_pinned: bool = False


class UpdateNoteRequest(APIModel):
    parent_id: str | None = None
    note_type: Literal["note", "folder", "inspiration"] | None = None
    title: str | None = Field(default=None, min_length=1, max_length=200)
    content: str | None = None
    sort_order: int | None = Field(default=None, ge=0)
    is_pinned: bool | None = None


class CreateSnapshotRequest(APIModel):
    user_note: str = Field(default="", max_length=500)


class CreateEditorProposalRequest(APIModel):
    tool_name: Literal["opening", "continue", "optimize", "polish", "review", "rewrite", "inspiration", "setting_update"]
    instruction: str = Field(default="", max_length=4000)
    selected_text: str = Field(default="", max_length=20000)
