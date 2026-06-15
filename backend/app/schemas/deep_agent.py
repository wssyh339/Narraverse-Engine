from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

DeepAgentMode = Literal["advisor", "orchestrator"]
LangSmithPrivacyMode = Literal["off", "metadata_only", "redacted", "full"]


class DeepAgentConfigUpdateRequest(BaseModel):
    deep_agent_enabled: bool | None = None
    deep_agent_mode: DeepAgentMode | None = None
    deep_agent_allow_write: bool | None = None
    langsmith_tracing: bool | None = None
    langsmith_privacy_mode: LangSmithPrivacyMode | None = None
    langsmith_prompt_sync: Literal["manual"] | None = None


class DeepAgentSessionCreateRequest(BaseModel):
    objective: str = Field(default="协助规划下一步创作任务。", max_length=2000)


class DeepAgentChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)


class LangSmithPromptPushRequest(BaseModel):
    agent_name: str
    prompt: str | None = None
    commit_message: str | None = None


class LangSmithPromptPullPreviewRequest(BaseModel):
    prompt_name: str
    commit_hash: str | None = None


class LangSmithEvalRunRequest(BaseModel):
    project_id: str | None = None
    job_id: str | None = None
    dataset_name: str | None = None
