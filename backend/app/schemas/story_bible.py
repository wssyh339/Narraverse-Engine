from typing import Literal

from pydantic import Field

from app.schemas.common import APIModel


class UpdateStoryBibleRequest(APIModel):
    world_setting: str = ""
    main_conflict: str = ""
    themes: list[str] = Field(default_factory=list)
    style_guide: str = ""
    narrative_pov: Literal["first_person", "third_person_limited", "third_person_omniscient"] = "third_person_limited"
    forbidden_elements: list[str] = Field(default_factory=list)
    continuity_rules: list[str] = Field(default_factory=list)
