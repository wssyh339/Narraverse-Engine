from __future__ import annotations

import json
import os
from typing import Any, Protocol


class OutlineLLMClient(Protocol):
    def generate(self, system_prompt: str, user_payload: dict[str, Any], response_schema: Any | None = None) -> dict[str, Any]:
        ...


class MockOutlineLLMClient:
    """Offline deterministic client for tests and local outline engineering."""

    def generate(self, system_prompt: str, user_payload: dict[str, Any], response_schema: Any | None = None) -> dict[str, Any]:
        agent_name = user_payload.get("agent_name", "unknown_agent")
        state = user_payload.get("story_state", {})
        config = state.get("config", {})
        project_name = config.get("project_name", "未命名项目")
        genre = config.get("genre", "类型小说")
        return {
            "agent_name": agent_name,
            "project_name": project_name,
            "genre": genre,
            "offline": True,
            "summary": f"{agent_name} 已基于当前 StoryState 生成结构化草案。",
            "notes": [
                "这是离线可验证输出；配置真实 API Key 后可替换为远程模型结果。",
                "所有 Agent 输出都应继续写回 StoryState，而不是单次散点生成。",
            ],
        }


class OpenAIOutlineLLMClient:
    """OpenAI-compatible client stub kept behind environment variables."""

    def __init__(self, model: str | None = None, base_url: str | None = None, api_key: str | None = None) -> None:
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-5.5")
        self.base_url = base_url or os.getenv("OPENAI_BASE_URL")
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")

    def generate(self, system_prompt: str, user_payload: dict[str, Any], response_schema: Any | None = None) -> dict[str, Any]:
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY 未配置，无法调用远程 Outline LLM。")
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("openai 包未安装，无法调用远程 Outline LLM。") from exc

        client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        response = client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or "{}"
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            parsed = {"raw_text": content}
        parsed.setdefault("_llm", {"provider": "openai-compatible", "model": self.model, "used_remote_model": True})
        return parsed


MockLLMClient = MockOutlineLLMClient
OpenAILLMClient = OpenAIOutlineLLMClient
