from dataclasses import dataclass
import os

from dotenv import load_dotenv

from app.services.llm_catalog import provider_for_model, split_provider_model

load_dotenv()


@dataclass(frozen=True)
class Settings:
    app_env: str
    log_level: str
    frontend_origin: str
    database_url: str
    sql_echo: bool
    qdrant_url: str
    qdrant_collection: str
    llm_provider: str
    llm_base_url: str
    llm_api_key: str
    llm_model: str
    llm_require_remote: bool
    openai_api_key: str
    openai_base_url: str
    openai_model: str
    dashscope_api_key: str
    dashscope_base_url: str
    dashscope_model: str
    qwen_api_key: str
    qwen_base_url: str
    qwen_model: str
    deepseek_api_key: str
    deepseek_base_url: str
    deepseek_model: str
    openrouter_api_key: str
    openrouter_base_url: str
    openrouter_model: str
    siliconflow_api_key: str
    siliconflow_base_url: str
    siliconflow_model: str
    moonshot_api_key: str
    moonshot_base_url: str
    moonshot_model: str
    zhipu_api_key: str
    zhipu_base_url: str
    zhipu_model: str
    ollama_api_key: str
    ollama_base_url: str
    ollama_model: str
    embedding_model: str
    deep_agent_enabled: bool
    deep_agent_mode: str
    deep_agent_allow_write: bool
    langsmith_tracing: bool
    langsmith_api_key: str
    langsmith_project: str
    langsmith_endpoint: str
    langsmith_privacy_mode: str
    langsmith_prompt_sync: str
    job_artifact_dir: str
    request_timeout_seconds: int


def _bool_env(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "y"}


def _int_env(name: str, default: str) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return int(default)


def get_settings() -> Settings:
    return Settings(
        app_env=os.getenv("APP_ENV", "development"),
        log_level=os.getenv("LOG_LEVEL", "info"),
        frontend_origin=os.getenv("FRONTEND_ORIGIN", "http://localhost:5173"),
        database_url=os.getenv("DATABASE_URL", "sqlite:///./data/novel_agent.db"),
        sql_echo=_bool_env("SQL_ECHO"),
        qdrant_url=os.getenv("QDRANT_URL", "http://localhost:6333"),
        qdrant_collection=os.getenv("QDRANT_COLLECTION", "novel_memory_v1"),
        llm_provider=os.getenv("LLM_PROVIDER", "qwen"),
        llm_base_url=os.getenv("LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
        llm_api_key=os.getenv("LLM_API_KEY", ""),
        llm_model=os.getenv("LLM_MODEL", "qwen-plus"),
        llm_require_remote=_bool_env("LLM_REQUIRE_REMOTE"),
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        openai_base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        dashscope_api_key=os.getenv("DASHSCOPE_API_KEY", ""),
        dashscope_base_url=os.getenv("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
        dashscope_model=os.getenv("DASHSCOPE_MODEL", "qwen-plus"),
        qwen_api_key=os.getenv("QWEN_API_KEY", os.getenv("DASHSCOPE_API_KEY", "")),
        qwen_base_url=os.getenv("QWEN_BASE_URL", os.getenv("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")),
        qwen_model=os.getenv("QWEN_MODEL", os.getenv("DASHSCOPE_MODEL", "qwen-plus")),
        deepseek_api_key=os.getenv("DEEPSEEK_API_KEY", ""),
        deepseek_base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        deepseek_model=os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"),
        openrouter_api_key=os.getenv("OPENROUTER_API_KEY", ""),
        openrouter_base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
        openrouter_model=os.getenv("OPENROUTER_MODEL", "openrouter/auto"),
        siliconflow_api_key=os.getenv("SILICONFLOW_API_KEY", ""),
        siliconflow_base_url=os.getenv("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1"),
        siliconflow_model=os.getenv("SILICONFLOW_MODEL", "Qwen/Qwen3-32B"),
        moonshot_api_key=os.getenv("MOONSHOT_API_KEY", ""),
        moonshot_base_url=os.getenv("MOONSHOT_BASE_URL", "https://api.moonshot.cn/v1"),
        moonshot_model=os.getenv("MOONSHOT_MODEL", "kimi-k2-0711-preview"),
        zhipu_api_key=os.getenv("ZHIPU_API_KEY", ""),
        zhipu_base_url=os.getenv("ZHIPU_BASE_URL", "https://open.bigmodel.cn/api/paas/v4"),
        zhipu_model=os.getenv("ZHIPU_MODEL", "glm-4-plus"),
        ollama_api_key=os.getenv("OLLAMA_API_KEY", "ollama"),
        ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
        ollama_model=os.getenv("OLLAMA_MODEL", "qwen2.5:7b"),
        embedding_model=os.getenv("EMBEDDING_MODEL", "text-embedding-v4"),
        deep_agent_enabled=_bool_env("DEEP_AGENT_ENABLED"),
        deep_agent_mode=os.getenv("DEEP_AGENT_MODE", "advisor"),
        deep_agent_allow_write=_bool_env("DEEP_AGENT_ALLOW_WRITE"),
        langsmith_tracing=_bool_env("LANGSMITH_TRACING"),
        langsmith_api_key=os.getenv("LANGSMITH_API_KEY", ""),
        langsmith_project=os.getenv("LANGSMITH_PROJECT", "novel-agent-local"),
        langsmith_endpoint=os.getenv("LANGSMITH_ENDPOINT", ""),
        langsmith_privacy_mode=os.getenv("LANGSMITH_PRIVACY_MODE", "metadata_only"),
        langsmith_prompt_sync=os.getenv("LANGSMITH_PROMPT_SYNC", "manual"),
        job_artifact_dir=os.getenv("JOB_ARTIFACT_DIR", "artifacts/runs"),
        request_timeout_seconds=_int_env("REQUEST_TIMEOUT_SECONDS", "120"),
    )


@dataclass(frozen=True)
class LLMProviderConfig:
    provider: str
    api_key: str
    base_url: str
    model: str


class LLMProviderResolver:
    def __init__(self, settings: Settings):
        self.settings = settings

    def resolve(self, requested_model: str | None = None) -> LLMProviderConfig:
        requested_provider, normalized_model = split_provider_model(requested_model)
        provider = requested_provider or provider_for_model(requested_model) or self.settings.llm_provider.strip().lower()
        model_override = normalized_model if requested_provider else requested_model
        if provider == "openai":
            return LLMProviderConfig(
                provider="openai",
                api_key=self.settings.openai_api_key or self.settings.llm_api_key,
                base_url=self.settings.openai_base_url or self.settings.llm_base_url or "https://api.openai.com/v1",
                model=model_override or self.settings.openai_model or self.settings.llm_model or "gpt-4.1-mini",
            )
        if provider == "deepseek":
            return LLMProviderConfig(
                provider="deepseek",
                api_key=self.settings.deepseek_api_key or self.settings.llm_api_key,
                base_url=self.settings.deepseek_base_url or self.settings.llm_base_url or "https://api.deepseek.com",
                model=model_override or self.settings.deepseek_model or self.settings.llm_model or "deepseek-v4-flash",
            )
        if provider in {"qwen", "dashscope", "tongyi"}:
            return LLMProviderConfig(
                provider="qwen",
                api_key=self.settings.qwen_api_key or self.settings.dashscope_api_key or self.settings.llm_api_key,
                base_url=self.settings.qwen_base_url or self.settings.dashscope_base_url or self.settings.llm_base_url,
                model=model_override or self.settings.qwen_model or self.settings.dashscope_model or self.settings.llm_model or "qwen-plus",
            )
        if provider == "openrouter":
            return LLMProviderConfig(
                provider="openrouter",
                api_key=self.settings.openrouter_api_key or self.settings.llm_api_key,
                base_url=self.settings.openrouter_base_url or self.settings.llm_base_url or "https://openrouter.ai/api/v1",
                model=model_override or self.settings.openrouter_model or self.settings.llm_model or "openrouter/auto",
            )
        if provider == "siliconflow":
            return LLMProviderConfig(
                provider="siliconflow",
                api_key=self.settings.siliconflow_api_key or self.settings.llm_api_key,
                base_url=self.settings.siliconflow_base_url or self.settings.llm_base_url or "https://api.siliconflow.cn/v1",
                model=model_override or self.settings.siliconflow_model or self.settings.llm_model or "Qwen/Qwen3-32B",
            )
        if provider == "moonshot":
            return LLMProviderConfig(
                provider="moonshot",
                api_key=self.settings.moonshot_api_key or self.settings.llm_api_key,
                base_url=self.settings.moonshot_base_url or self.settings.llm_base_url or "https://api.moonshot.cn/v1",
                model=model_override or self.settings.moonshot_model or self.settings.llm_model or "kimi-k2-0711-preview",
            )
        if provider in {"zhipu", "glm"}:
            return LLMProviderConfig(
                provider="zhipu",
                api_key=self.settings.zhipu_api_key or self.settings.llm_api_key,
                base_url=self.settings.zhipu_base_url or self.settings.llm_base_url or "https://open.bigmodel.cn/api/paas/v4",
                model=model_override or self.settings.zhipu_model or self.settings.llm_model or "glm-4-plus",
            )
        if provider == "ollama":
            return LLMProviderConfig(
                provider="ollama",
                api_key=self.settings.ollama_api_key or "ollama",
                base_url=self.settings.ollama_base_url or self.settings.llm_base_url or "http://localhost:11434/v1",
                model=model_override or self.settings.ollama_model or self.settings.llm_model or "qwen2.5:7b",
            )
        return LLMProviderConfig(
            provider=provider or "openai_compatible",
            api_key=self.settings.llm_api_key,
            base_url=self.settings.llm_base_url,
            model=model_override or self.settings.llm_model or "qwen-plus",
        )
