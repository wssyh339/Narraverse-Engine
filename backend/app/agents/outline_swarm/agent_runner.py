from __future__ import annotations

from typing import Any

from app.agents.llm_io import call_agent_json
from app.agents.outline_swarm.state import OutlineSwarmState
from app.services.llm_client import llm_client as default_llm_client
from app.services.prompt_loader import load_prompt


OUTLINE_AGENT_PROMPTS: dict[str, str] = {
    "StoryDirectorAgent": "story_director",
    "WhyInterrogatorAgent": "why_interrogator",
    "WorldSettingAgent": "world_setting",
    "CharacterArcAgent": "character_arc",
    "ConflictAgent": "conflict",
    "PlotArchitectAgent": "plot_architect",
    "BeatControllerAgent": "beat_controller",
    "ForeshadowingAgent": "foreshadowing",
    "EntityExtractorAgent": "entity_extractor",
    "ContinuityAgent": "continuity",
}


class OutlineSwarmAgentRunner:
    def __init__(self, llm_client: Any = default_llm_client) -> None:
        self.llm_client = llm_client

    def run(
        self,
        *,
        agent_name: str,
        state: OutlineSwarmState,
        role: str,
        task: str,
        fallback: dict[str, Any],
        model: str | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        prompt_name = OUTLINE_AGENT_PROMPTS[agent_name]
        system_prompt = self._system_prompt(agent_name, prompt_name)
        return call_agent_json(
            llm_client=self.llm_client,
            agent_name=agent_name,
            role=role,
            system_prompt=system_prompt,
            task=task,
            context=self._context(state),
            fallback=fallback,
            model=model,
        )

    def _system_prompt(self, agent_name: str, prompt_name: str) -> str:
        global_prompt = load_prompt("global_prompt")
        agent_prompt = load_prompt(prompt_name)
        return (
            f"{global_prompt}\n\n"
            f"## 当前 Agent\n{agent_prompt}\n\n"
            f"## 运行约束\n"
            f"- 你当前的 agent_name 是 {agent_name}。\n"
            "- 必须优先使用 context 中的 seed、canon_context、story_bible、characters、world_facts、outline、volume_outlines、chapter_beats。\n"
            "- 不允许复用示例故事或硬编码故事名；所有具体内容必须来自 context 或明确标为 candidate。\n"
            "- 输出只能是 JSON object，字段应尽量贴合 expected_output_schema。\n"
        )

    def _context(self, state: OutlineSwarmState) -> dict[str, Any]:
        return {
            "project_id": state.project_id,
            "seed": state.seed,
            "model": state.model,
            "canon_context": state.canon_context.model_dump(mode="json") if state.canon_context else None,
            "story_bible": state.story_bible,
            "characters": state.characters,
            "story_entities": state.story_entities,
            "world_facts": state.world_facts,
            "outline": state.outline,
            "volume_outlines": state.volume_outlines,
            "chapter_beats": state.chapter_beats,
            "foreshadowing_items": state.foreshadowing_items,
            "continuity_issues": state.continuity_issues,
            "completion_tickets": state.completion_tickets,
            "uncertainty_tickets": state.uncertainty_tickets,
            "incomplete_required_entities": state.incomplete_required_entities,
            "active_agent": state.active_agent,
            "iteration_count": state.iteration_count,
            "volume_target": state.volume_target,
            "chapter_target": state.chapter_target,
            "status": state.status,
        }
