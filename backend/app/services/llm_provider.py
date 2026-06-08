from __future__ import annotations

from app.core.config import LLMProviderResolver, get_settings


class MockLLM:
    """Deterministic fallback used when no provider key is configured."""

    def generate(self, prompt: str, *, agent_name: str = "MockLLM") -> dict[str, str | bool]:
        summary = prompt.strip().splitlines()[0] if prompt.strip() else "规则化本地推演"
        return {
            "agent_name": agent_name,
            "text": f"{agent_name} 使用本地规则化回退完成：{summary}",
            "used_remote_model": False,
        }


class LLMProvider:
    def __init__(self) -> None:
        self.config = LLMProviderResolver(get_settings()).resolve()
        self.mock = MockLLM()

    @property
    def has_remote_key(self) -> bool:
        return bool(self.config.api_key)

    def generate(self, prompt: str, *, agent_name: str) -> dict[str, str | bool]:
        if not self.has_remote_key:
            return self.mock.generate(prompt, agent_name=agent_name)
        return {
            "agent_name": agent_name,
            "text": f"{agent_name} 已准备通过 {self.config.provider}/{self.config.model} 调用远程模型；本流程保持结构化输出。",
            "used_remote_model": True,
        }
