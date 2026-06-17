from pydantic import Field

from app.schemas.common import APIModel


class CreateProjectRequest(APIModel):
    title: str = Field(min_length=1, max_length=120)
    genre: str = Field(min_length=1, max_length=60)
    target_reader: str = Field(min_length=1)
    premise: str = Field(min_length=1)
    style_guide: str = ""
    language: str = "zh-CN"
    planned_chapter_count: int = Field(gt=0)
    planned_volume_count: int | None = Field(default=None, gt=0)
    chapters_per_volume: int | None = Field(default=None, gt=0)
    chapter_word_target: int = Field(ge=500, le=10000)
    chapter_word_min: int | None = Field(default=None, ge=500, le=20000)
    chapter_word_max: int | None = Field(default=None, ge=500, le=20000)
    target_words: int | None = Field(default=None, ge=0)
    current_volume: int = Field(default=1, ge=1)
    current_chapter: int = Field(default=1, ge=1)
    cover_image: str = ""
    initial_idea: str = ""
