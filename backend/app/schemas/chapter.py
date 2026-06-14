from pydantic import Field

from app.schemas.common import APIModel


class PlanChaptersRequest(APIModel):
    volume_title: str = Field(min_length=1)
    start_chapter_no: int = Field(ge=1)
    chapter_count: int = Field(ge=1, le=100)
    outline_requirement: str = Field(min_length=1)
    overwrite_existing: bool = False
    idempotency_key: str = Field(min_length=1)
    target_words: int | None = Field(default=None, ge=30000, le=10000000)
    volume_count: int | None = Field(default=None, ge=1, le=30)
    chapters_per_volume: int | None = Field(default=None, ge=1, le=200)
    chapter_word_target: int | None = Field(default=None, ge=500, le=20000)
    model: str | None = None
    async_mode: bool = False
