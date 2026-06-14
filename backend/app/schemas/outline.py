from __future__ import annotations

from pydantic import Field, model_validator

from app.schemas.common import APIModel


class BookOutlineGenerateRequest(APIModel):
    outline_requirement: str = Field(min_length=1, max_length=20000)
    target_words: int | None = Field(default=None, ge=30000, le=10000000)
    volume_count: int = Field(default=3, ge=1, le=30)
    chapters_per_volume: int = Field(default=50, ge=1, le=200)
    chapter_word_target: int | None = Field(default=None, ge=500, le=20000)
    use_topology_inference: bool = True
    idempotency_key: str = Field(min_length=1)
    model: str | None = None
    async_mode: bool = False


class BookOutlineCommitRequest(APIModel):
    job_id: str | None = None
    outline_plan: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def require_source(self) -> "BookOutlineCommitRequest":
        if not self.job_id and not self.outline_plan:
            raise ValueError("job_id 或 outline_plan 至少需要提供一个")
        return self


class ChapterOutlineRange(APIModel):
    volume_no: int = Field(ge=1)
    start_chapter_no: int = Field(ge=1)
    end_chapter_no: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_range(self) -> "ChapterOutlineRange":
        if self.end_chapter_no < self.start_chapter_no:
            raise ValueError("end_chapter_no 必须大于或等于 start_chapter_no")
        return self


class ChapterOutlineBatchGenerateRequest(APIModel):
    chapter_ranges: list[ChapterOutlineRange] = Field(min_length=1, max_length=30)
    generation_requirement: str = Field(default="", max_length=12000)
    overwrite_existing: bool = False
    use_topology_inference: bool = True
    idempotency_key: str = Field(min_length=1)
    model: str | None = None
    async_mode: bool = False


class ChapterOutlineCommitRequest(APIModel):
    job_id: str | None = None
    chapter_outlines: list[dict] = Field(default_factory=list)
    overwrite_existing: bool = True

    @model_validator(mode="after")
    def require_source(self) -> "ChapterOutlineCommitRequest":
        if not self.job_id and not self.chapter_outlines:
            raise ValueError("job_id 或 chapter_outlines 至少需要提供一个")
        return self
