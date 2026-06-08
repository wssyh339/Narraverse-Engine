from __future__ import annotations

from typing import Any
import json
import re

from app.core.json import dumps


def _schema_hint(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _schema_hint(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_schema_hint(value[0])] if value else []
    return type(value).__name__


def _strip_code_fence(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.IGNORECASE)
        stripped = re.sub(r"\s*```$", "", stripped)
    return stripped.strip()


def parse_json_object(text: str) -> dict[str, Any] | None:
    stripped = _strip_code_fence(text)
    candidates = [stripped]
    first = stripped.find("{")
    last = stripped.rfind("}")
    if first >= 0 and last > first:
        candidates.append(stripped[first : last + 1])
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def merge_agent_payload(fallback: dict[str, Any], parsed: dict[str, Any] | None) -> dict[str, Any]:
    payload = dict(fallback)
    if parsed:
        payload.update(parsed)
    return payload


def call_agent_json(
    *,
    llm_client: Any,
    agent_name: str,
    role: str,
    system_prompt: str,
    task: str,
    context: dict[str, Any],
    fallback: dict[str, Any],
    model: str | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    user_payload = {
        "agent_name": agent_name,
        "role": role,
        "task": task,
        "context": context,
        "expected_output_schema": _schema_hint(fallback),
        "output_rules": [
            "只输出一个严格 JSON object",
            "不要输出 Markdown、代码围栏或解释性前后缀",
            "缺少把握的信息使用空数组、空字符串或 candidate 字段，不要编造来源",
        ],
    }
    prompt = (
        f"{system_prompt}\n\n"
        "你正在作为后端 Agent 节点运行。必须读取用户提供的 context，输出 expected_output_schema 对应的 JSON。"
    )
    result = llm_client.generate(prompt, dumps(user_payload), model)
    parsed = parse_json_object(result.content)
    used_remote_model = bool(getattr(result, "used_remote_model", False))
    meta = {
        "provider": getattr(result, "provider", ""),
        "model": getattr(result, "model", model or ""),
        "used_remote_model": used_remote_model,
        "parsed": parsed is not None,
        "source": "remote_api" if used_remote_model else "local_fallback",
    }
    return merge_agent_payload(fallback, parsed), meta
