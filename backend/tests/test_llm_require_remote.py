from __future__ import annotations

import pytest


def test_llm_client_requires_remote_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services.llm_client import LLMClient

    monkeypatch.setenv("LLM_PROVIDER", "local-test")
    monkeypatch.setenv("LLM_API_KEY", "")
    monkeypatch.setenv("LLM_REQUIRE_REMOTE", "true")

    with pytest.raises(RuntimeError, match="requires a remote"):
        LLMClient().generate("system", "user", None)


def test_llm_client_retries_transient_remote_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services.llm_client import LLMClient

    class Response:
        content = "远程成功"

    class FlakyLLMClient(LLMClient):
        def __init__(self) -> None:
            self.calls = 0
            self.remote_retry_base_delay_seconds = 0

        def _build_chat(self, config, timeout):
            return self

        def invoke(self, messages):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("Connection error.")
            return Response()

    monkeypatch.setenv("LLM_PROVIDER", "local-test")
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    monkeypatch.setenv("LLM_REQUIRE_REMOTE", "true")

    client = FlakyLLMClient()
    result = client.generate("system", "user", None)

    assert result.content == "远程成功"
    assert result.used_remote_model is True
    assert client.calls == 2
