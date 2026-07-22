from __future__ import annotations

from scripts.run_real_20w_4000_flow import is_retryable_generation_error


def test_real_flow_retries_transient_generation_errors() -> None:
    assert is_retryable_generation_error({"message": "LLM_REQUIRE_REMOTE remote deepseek call failed: Connection error."})
    assert is_retryable_generation_error("provider returned 429 rate limit")
    assert is_retryable_generation_error("service unavailable 503")


def test_real_flow_does_not_retry_configuration_errors() -> None:
    assert not is_retryable_generation_error({"message": "LLM_REQUIRE_REMOTE requires a remote deepseek API key."})
    assert not is_retryable_generation_error("authentication failed: invalid api key")
