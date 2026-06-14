from __future__ import annotations

from dataclasses import dataclass

from app.core.config import LLMProviderResolver, get_settings


@dataclass
class LLMResult:
    content: str
    provider: str
    model: str
    used_remote_model: bool


class LLMClient:
    def generate(self, system_prompt: str, user_prompt: str, model: str | None = None) -> LLMResult:
        settings = get_settings()
        config = LLMProviderResolver(settings).resolve(model)
        if not config.api_key:
            if settings.llm_require_remote:
                raise RuntimeError(f"LLM_REQUIRE_REMOTE requires a remote {config.provider} API key.")
            return LLMResult(
                content=f"本地降级输出：未配置 {config.provider} API Key，无法调用远程模型。用户提示：{user_prompt[:500]}",
                provider=config.provider,
                model=config.model,
                used_remote_model=False,
            )
        try:
            from langchain_openai import ChatOpenAI
            from langchain_core.messages import HumanMessage, SystemMessage

            chat = ChatOpenAI(
                api_key=config.api_key,
                base_url=config.base_url,
                model=config.model,
                timeout=settings.request_timeout_seconds,
            )
            response = chat.invoke([SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)])
            return LLMResult(content=str(response.content), provider=config.provider, model=config.model, used_remote_model=True)
        except Exception as exc:
            if settings.llm_require_remote:
                raise RuntimeError(f"LLM_REQUIRE_REMOTE remote {config.provider} call failed: {exc}") from exc
            return LLMResult(
                content=f"远程模型调用失败，已返回本地错误说明：{exc}",
                provider=config.provider,
                model=config.model,
                used_remote_model=False,
            )


llm_client = LLMClient()
