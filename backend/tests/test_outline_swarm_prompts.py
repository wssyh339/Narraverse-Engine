from __future__ import annotations

from app.agents.outline_swarm.agent_runner import OUTLINE_AGENT_PROMPTS
from app.services.prompt_loader import load_prompt


def test_outline_swarm_prompts_are_detailed_and_structured() -> None:
    for prompt_name in OUTLINE_AGENT_PROMPTS.values():
        prompt = load_prompt(prompt_name)
        assert len(prompt) > 600, prompt_name
        assert "JSON" in prompt
        assert "Why Chain" in prompt
        assert "新增实体" in prompt
        assert "不确定" in prompt
        assert "正典" in prompt


def test_global_prompt_contains_non_negotiable_outline_rules() -> None:
    prompt = load_prompt("global_prompt")
    for phrase in ("多问为什么", "不确定不硬编", "实体必须补全", "S 级和 A 级实体"):
        assert phrase in prompt
