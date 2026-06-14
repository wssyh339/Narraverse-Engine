from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LLMProviderEntry:
    id: str
    label: str
    base_url_env: str
    api_key_env: str
    default_model: str
    notes: str


@dataclass(frozen=True)
class LLMModelEntry:
    id: str
    provider: str
    label: str
    family: str
    recommended_for: tuple[str, ...]


LLM_PROVIDER_ENTRIES: tuple[LLMProviderEntry, ...] = (
    LLMProviderEntry("openai", "OpenAI", "OPENAI_BASE_URL", "OPENAI_API_KEY", "gpt-4.1-mini", "官方 OpenAI API。"),
    LLMProviderEntry("qwen", "通义千问 / DashScope", "QWEN_BASE_URL", "QWEN_API_KEY", "qwen-plus", "OpenAI 兼容模式。"),
    LLMProviderEntry("deepseek", "DeepSeek", "DEEPSEEK_BASE_URL", "DEEPSEEK_API_KEY", "deepseek-v4-flash", "OpenAI 兼容 API。"),
    LLMProviderEntry("openrouter", "OpenRouter", "OPENROUTER_BASE_URL", "OPENROUTER_API_KEY", "openrouter/auto", "多模型聚合，OpenAI 兼容 API。"),
    LLMProviderEntry("siliconflow", "SiliconFlow", "SILICONFLOW_BASE_URL", "SILICONFLOW_API_KEY", "Qwen/Qwen3-32B", "多开源模型聚合，OpenAI 兼容 API。"),
    LLMProviderEntry("moonshot", "Moonshot / Kimi", "MOONSHOT_BASE_URL", "MOONSHOT_API_KEY", "kimi-k2-0711-preview", "Moonshot OpenAI 兼容 API。"),
    LLMProviderEntry("zhipu", "智谱 GLM", "ZHIPU_BASE_URL", "ZHIPU_API_KEY", "glm-4-plus", "智谱 OpenAI 兼容 API。"),
    LLMProviderEntry("ollama", "Ollama 本地模型", "OLLAMA_BASE_URL", "OLLAMA_API_KEY", "qwen2.5:7b", "本地 OpenAI 兼容接口。"),
    LLMProviderEntry("openai_compatible", "自定义 OpenAI-compatible", "LLM_BASE_URL", "LLM_API_KEY", "qwen-plus", "任意兼容 /v1/chat/completions 的服务。"),
)


LLM_MODEL_ENTRIES: tuple[LLMModelEntry, ...] = (
    LLMModelEntry("gpt-4.1-mini", "openai", "GPT-4.1 Mini", "gpt-4.1", ("日常写作", "轻量审稿", "结构化输出")),
    LLMModelEntry("gpt-4.1", "openai", "GPT-4.1", "gpt-4.1", ("复杂推理", "总纲", "一致性审查")),
    LLMModelEntry("gpt-4o-mini", "openai", "GPT-4o Mini", "gpt-4o", ("低成本草案", "快速对话")),
    LLMModelEntry("gpt-4o", "openai", "GPT-4o", "gpt-4o", ("多模态扩展", "综合写作")),
    LLMModelEntry("qwen-plus", "qwen", "Qwen Plus", "qwen", ("默认创作", "长篇草案", "中文写作")),
    LLMModelEntry("qwen-max", "qwen", "Qwen Max", "qwen", ("高质量中文", "复杂设定", "审稿")),
    LLMModelEntry("qwen-turbo", "qwen", "Qwen Turbo", "qwen", ("快速抽卡", "低成本生成")),
    LLMModelEntry("qwen-long", "qwen", "Qwen Long", "qwen", ("长上下文", "前文摘要整合")),
    LLMModelEntry("deepseek-v4-flash", "deepseek", "DeepSeek V4 Flash", "deepseek", ("快速推理", "章节草案")),
    LLMModelEntry("deepseek-v4-pro", "deepseek", "DeepSeek V4 Pro", "deepseek", ("复杂推理", "逻辑审计", "小说宪法")),
    LLMModelEntry("openrouter/auto", "openrouter", "OpenRouter Auto", "openrouter", ("跨模型兜底", "试验")),
    LLMModelEntry("anthropic/claude-sonnet-4", "openrouter", "Claude Sonnet 4 via OpenRouter", "claude", ("审稿", "长文改写")),
    LLMModelEntry("google/gemini-2.5-pro", "openrouter", "Gemini 2.5 Pro via OpenRouter", "gemini", ("长上下文", "结构推理")),
    LLMModelEntry("Qwen/Qwen3-32B", "siliconflow", "Qwen3 32B via SiliconFlow", "qwen", ("本地优先替代", "中文生成")),
    LLMModelEntry("deepseek-ai/DeepSeek-V3", "siliconflow", "DeepSeek V3 via SiliconFlow", "deepseek", ("开源模型", "草案生成")),
    LLMModelEntry("kimi-k2-0711-preview", "moonshot", "Kimi K2", "kimi", ("长上下文", "中文创作")),
    LLMModelEntry("glm-4-plus", "zhipu", "GLM-4 Plus", "glm", ("中文推理", "设定整理")),
    LLMModelEntry("qwen2.5:7b", "ollama", "Qwen2.5 7B Local", "qwen", ("本地离线草案", "隐私优先")),
)

PROVIDER_BY_ID = {provider.id: provider for provider in LLM_PROVIDER_ENTRIES}
MODEL_BY_ID = {model.id: model for model in LLM_MODEL_ENTRIES}


def split_provider_model(model: str | None) -> tuple[str | None, str | None]:
    if not model:
        return None, None
    if ":" not in model:
        return None, model
    provider, raw_model = model.split(":", 1)
    provider = provider.strip().lower()
    raw_model = raw_model.strip()
    if provider in PROVIDER_BY_ID and raw_model:
        return provider, raw_model
    return None, model


def provider_for_model(model: str | None) -> str | None:
    provider, raw_model = split_provider_model(model)
    if provider:
        return provider
    if raw_model and raw_model in MODEL_BY_ID:
        return MODEL_BY_ID[raw_model].provider
    return None


def catalog_payload(default_model: str, default_provider: str) -> dict[str, Any]:
    return {
        "default_provider": default_provider,
        "default_model": default_model,
        "providers": [provider.__dict__ for provider in LLM_PROVIDER_ENTRIES],
        "models": [
            {
                "id": model.id,
                "provider": model.provider,
                "label": model.label,
                "family": model.family,
                "recommended_for": list(model.recommended_for),
            }
            for model in LLM_MODEL_ENTRIES
        ],
    }
