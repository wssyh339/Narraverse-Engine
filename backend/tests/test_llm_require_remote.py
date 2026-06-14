from __future__ import annotations

import pytest


def test_llm_client_requires_remote_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services.llm_client import LLMClient

    monkeypatch.setenv("LLM_PROVIDER", "local-test")
    monkeypatch.setenv("LLM_API_KEY", "")
    monkeypatch.setenv("LLM_REQUIRE_REMOTE", "true")

    with pytest.raises(RuntimeError, match="requires a remote"):
        LLMClient().generate("system", "user", None)
