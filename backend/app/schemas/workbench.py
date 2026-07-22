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


NoteType = Literal["note", "folder", "inspiration", "import_report", "method_pack", "reference_asset", "review_report"]


class CreateNoteRequest(APIModel):
    parent_id: str | None = None
    note_type: NoteType = "note"
    title: str = Field(min_length=1, max_length=200)
    content: str = ""
    sort_order: int = Field(default=0, ge=0)
    is_pinned: bool = False


class UpdateNoteRequest(APIModel):
    parent_id: str | None = None
    note_type: NoteType | None = None
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


class ImportNovelRequest(APIModel):
    source_name: str = Field(default="导入小说", min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=2_000_000)
    target_platform: str = Field(default="", max_length=80)
    create_canon_proposals: bool = True


class CreateMethodPackRequest(APIModel):
    name: str = Field(min_length=1, max_length=160)
    source: str = Field(default="", max_length=240)
    genre: str = Field(default="", max_length=80)
    principles: list[str] = Field(default_factory=list)
    chapter_recipe: list[str] = Field(default_factory=list)
    style_rules: list[str] = Field(default_factory=list)
    anti_patterns: list[str] = Field(default_factory=list)
    reference_note_ids: list[str] = Field(default_factory=list)
    is_pinned: bool = True


class CreateReferenceAssetRequest(APIModel):
    title: str = Field(min_length=1, max_length=160)
    asset_type: Literal["novel_excerpt", "chapter_excerpt", "outline", "review", "style_sample"] = "novel_excerpt"
    source_name: str = Field(default="", max_length=160)
    text: str = Field(min_length=1, max_length=500_000)
    tags: list[str] = Field(default_factory=list)
    analysis: dict = Field(default_factory=dict)
    method_pack_id: str | None = None
    is_pinned: bool = False


class ReviewPlanRequest(APIModel):
    mode: Literal["solo", "lean", "full"] = "lean"
    scope: Literal["chapter", "outline", "project"] = "chapter"
    chapter_id: str | None = None
    method_pack_id: str | None = None
    instruction: str = Field(default="", max_length=4000)
