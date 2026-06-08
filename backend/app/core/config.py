from dataclasses import dataclass
import os

from dotenv import load_dotenv

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
    embedding_model: str
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
        llm_provider=os.getenv("LLM_PROVIDER", "dashscope"),
        llm_base_url=os.getenv("LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
        llm_api_key=os.getenv("LLM_API_KEY", ""),
        llm_model=os.getenv("LLM_MODEL", "qwen-plus"),
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
        embedding_model=os.getenv("EMBEDDING_MODEL", "text-embedding-v4"),
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
        provider = self.settings.llm_provider.strip().lower()
        if provider == "openai":
            return LLMProviderConfig(
                provider="openai",
                api_key=self.settings.openai_api_key or self.settings.llm_api_key,
                base_url=self.settings.openai_base_url or self.settings.llm_base_url or "https://api.openai.com/v1",
                model=requested_model or self.settings.openai_model or self.settings.llm_model or "gpt-4.1-mini",
            )
        if provider == "deepseek":
            return LLMProviderConfig(
                provider="deepseek",
                api_key=self.settings.deepseek_api_key or self.settings.llm_api_key,
                base_url=self.settings.deepseek_base_url or self.settings.llm_base_url or "https://api.deepseek.com",
                model=requested_model or self.settings.deepseek_model or self.settings.llm_model or "deepseek-v4-flash",
            )
        if provider in {"qwen", "dashscope", "tongyi"}:
            return LLMProviderConfig(
                provider="qwen",
                api_key=self.settings.qwen_api_key or self.settings.dashscope_api_key or self.settings.llm_api_key,
                base_url=self.settings.qwen_base_url or self.settings.dashscope_base_url or self.settings.llm_base_url,
                model=requested_model or self.settings.qwen_model or self.settings.dashscope_model or self.settings.llm_model or "qwen-plus",
            )
        return LLMProviderConfig(
            provider=provider or "openai_compatible",
            api_key=self.settings.llm_api_key,
            base_url=self.settings.llm_base_url,
            model=requested_model or self.settings.llm_model or "qwen-plus",
        )
