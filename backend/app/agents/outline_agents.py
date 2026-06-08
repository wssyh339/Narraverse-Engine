from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from app.agents.outline_llm_client import MockOutlineLLMClient, OutlineLLMClient
from app.agents.outline_models import StoryState
from app.agents.prompts import AGENT_SPECS_BY_NAME


class BaseAgent:
    name: str = ""
    output_schema: type[BaseModel] | None = None

    def __init__(self, client: OutlineLLMClient | None = None) -> None:
        self.client = client or MockOutlineLLMClient()
        self.system_prompt = AGENT_SPECS_BY_NAME[self.name].prompt

    def run(self, story_state: StoryState, **kwargs: Any) -> dict[str, Any]:
        payload = {
            "agent_name": self.name,
            "story_state": story_state.model_dump(mode="json"),
            "task_options": kwargs,
        }
        return self.client.generate(
            system_prompt=self.system_prompt,
            user_payload=payload,
            response_schema=self.output_schema,
        )


class EditorOrchestratorAgent(BaseAgent):
    name = "editor_orchestrator"


class OneSentenceExpansionAgent(BaseAgent):
    name = "one_sentence_expansion"


class GenreMarketPositionAgent(BaseAgent):
    name = "genre_market_position"


class WorldBibleAgent(BaseAgent):
    name = "world_bible"


class ProtagonistArcAgent(BaseAgent):
    name = "protagonist_arc"


class CharacterTreeAgent(BaseAgent):
    name = "character_tree"


class FactionConflictAgent(BaseAgent):
    name = "faction_conflict"


class PowerSystemAgent(BaseAgent):
    name = "power_system"


class FullStructureAgent(BaseAgent):
    name = "full_structure"


class VolumeOutlineAgent(BaseAgent):
    name = "volume_outline"


class BeatControlAgent(BaseAgent):
    name = "beat_control"


class ForeshadowingAgent(BaseAgent):
    name = "foreshadowing_manager"


class LogicAuditAgent(BaseAgent):
    name = "logic_audit"


AGENT_CLASS_BY_NAME: dict[str, type[BaseAgent]] = {
    "editor_orchestrator": EditorOrchestratorAgent,
    "one_sentence_expansion": OneSentenceExpansionAgent,
    "genre_market_position": GenreMarketPositionAgent,
    "world_bible": WorldBibleAgent,
    "protagonist_arc": ProtagonistArcAgent,
    "character_tree": CharacterTreeAgent,
    "faction_conflict": FactionConflictAgent,
    "power_system": PowerSystemAgent,
    "full_structure": FullStructureAgent,
    "volume_outline": VolumeOutlineAgent,
    "beat_control": BeatControlAgent,
    "foreshadowing_manager": ForeshadowingAgent,
    "logic_audit": LogicAuditAgent,
}


CLASS_NAME_TO_AGENT_NAME = {
    "EditorOrchestratorAgent": "editor_orchestrator",
    "OneSentenceExpansionAgent": "one_sentence_expansion",
    "GenreMarketPositionAgent": "genre_market_position",
    "WorldBibleAgent": "world_bible",
    "ProtagonistArcAgent": "protagonist_arc",
    "CharacterTreeAgent": "character_tree",
    "FactionConflictAgent": "faction_conflict",
    "PowerSystemAgent": "power_system",
    "FullStructureAgent": "full_structure",
    "VolumeOutlineAgent": "volume_outline",
    "BeatControlAgent": "beat_control",
    "ForeshadowingAgent": "foreshadowing_manager",
    "LogicAuditAgent": "logic_audit",
}
