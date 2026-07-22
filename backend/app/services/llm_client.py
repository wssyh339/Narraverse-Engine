from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any

from app.core.config import LLMProviderResolver, get_settings


@dataclass
class LLMResult:
    content: str
    provider: str
    model: str
    used_remote_model: bool


class LLMClient:
    remote_retry_attempts = 3
    remote_retry_base_delay_seconds = 0.5

    def _build_chat(self, config: Any, timeout: int) -> Any:
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
            model=config.model,
            timeout=timeout,
        )

    def _is_retryable_remote_error(self, exc: Exception) -> bool:
        error_text = f"{exc.__class__.__name__}: {exc}".lower()
        fatal_markers = (
            "authentication",
            "unauthorized",
            "invalid api key",
            "incorrect api key",
            "permission denied",
            "forbidden",
            "insufficient_quota",
            "requires a remote",
        )
        if any(marker in error_text for marker in fatal_markers):
            return False
        retryable_markers = (
            "connection error",
            "connection reset",
            "connecterror",
            "remoteprotocolerror",
            "readtimeout",
            "timeout",
            "timed out",
            "temporarily unavailable",
            "service unavailable",
            "server error",
            "rate limit",
            "too many requests",
            "429",
            "500",
            "502",
            "503",
            "504",
        )
        return any(marker in error_text for marker in retryable_markers)

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
        last_error: Exception | None = None
        try:
            from langchain_core.messages import HumanMessage, SystemMessage

            for attempt in range(1, self.remote_retry_attempts + 1):
                try:
                    chat = self._build_chat(config, settings.request_timeout_seconds)
                    response = chat.invoke([SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)])
                    break
                except Exception as exc:
                    last_error = exc
                    if attempt >= self.remote_retry_attempts or not self._is_retryable_remote_error(exc):
                        raise
                    time.sleep(self.remote_retry_base_delay_seconds * attempt)
            return LLMResult(content=str(response.content), provider=config.provider, model=config.model, used_remote_model=True)
        except Exception as exc:
            if last_error is not None:
                exc = last_error
            if settings.llm_require_remote:
                raise RuntimeError(f"LLM_REQUIRE_REMOTE remote {config.provider} call failed: {exc}") from exc
            return LLMResult(
                content=f"远程模型调用失败，已返回本地错误说明：{exc}",
                provider=config.provider,
                model=config.model,
                used_remote_model=False,
            )


llm_client = LLMClient()
