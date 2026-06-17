from __future__ import annotations

import json
from types import SimpleNamespace

from app.agents.outline_swarm.agent_runner import OUTLINE_AGENT_PROMPTS, OutlineSwarmAgentRunner
from app.agents.outline_swarm.service import run_outline_swarm
from app.agents.outline_swarm.state import OutlineSwarmState


class RecordingLLMClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str | None]] = []

    def generate(self, system_prompt: str, user_prompt: str, model: str | None = None) -> SimpleNamespace:
        self.calls.append((system_prompt, user_prompt, model))
        return SimpleNamespace(
            content=json.dumps({"director_brief": {"from_llm": True}}, ensure_ascii=False),
            provider="fake",
            model=model or "fake-model",
            used_remote_model=True,
        )


def test_outline_agent_runner_loads_prompt_and_calls_llm_client() -> None:
    client = RecordingLLMClient()
    runner = OutlineSwarmAgentRunner(llm_client=client)
    payload, meta = runner.run(
        agent_name="StoryDirectorAgent",
        state=OutlineSwarmState(project_id="prj_test", seed={"genre": "奇幻"}),
        role="故事总导演",
        task="生成阶段判断",
        fallback={"director_brief": {"from_fallback": True}},
        model="fake-model",
    )

    assert payload["director_brief"]["from_llm"] is True
    assert meta["used_remote_model"] is True
    assert meta["parsed"] is True
    assert len(client.calls) == 1
    system_prompt, user_prompt, model = client.calls[0]
    assert "StoryDirectorAgent" in system_prompt
    assert "多问为什么" in system_prompt
    assert "expected_output_schema" in user_prompt
    assert model == "fake-model"


def test_outline_swarm_records_llm_metadata_for_agent_steps() -> None:
    result = run_outline_swarm(
        {
            "project_id": "prj_test",
            "seed": {"genre": "都市脑洞", "premise": "普通人发现城市规则正在改写现实。"},
            "volume_target": 1,
            "chapter_target": 2,
        }
    )

    assert result["agent_llm_results"]
    assert "StoryDirectorAgent" in result["agent_llm_results"]
    assert result["agent_llm_results"]["StoryDirectorAgent"]["source"] in {"remote_api", "local_fallback"}


def test_outline_swarm_prompt_files_are_registered_for_all_agents() -> None:
    assert set(OUTLINE_AGENT_PROMPTS) == {
        "StoryDirectorAgent",
        "WhyInterrogatorAgent",
        "WorldSettingAgent",
        "CharacterArcAgent",
        "ConflictAgent",
        "CharacterGeneratorAgent",
        "SettingGeneratorAgent",
        "PlotArchitectAgent",
        "BeatControllerAgent",
        "ForeshadowingAgent",
        "EntityExtractorAgent",
        "ContinuityAgent",
    }
