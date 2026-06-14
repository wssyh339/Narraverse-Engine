from __future__ import annotations

from typing import Any
import json
import re

from app.core.json import dumps


CRITICAL_AGENT_REQUIRED_OUTPUTS: dict[str, tuple[tuple[str, ...], ...]] = {
    "volume_outline": (("volume_outlines", "volumes"),),
    "logic_audit": (("passed", "status", "conclusion"), ("issues", "blocking_issues", "revision_suggestions")),
}


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


def _validate_agent_payload(agent_name: str, payload: dict[str, Any], parsed: dict[str, Any] | None) -> list[str]:
    warnings: list[str] = []
    if parsed is None:
        warnings.append("LLM 输出未解析为 JSON object，当前结果包含 fallback 内容。")
    for alternatives in CRITICAL_AGENT_REQUIRED_OUTPUTS.get(agent_name, ()):
        if not any(payload.get(key) not in (None, "", [], {}) for key in alternatives):
            warnings.append(f"{agent_name} 缺少必填字段：{' / '.join(alternatives)}")
    return warnings


def _find_context_value(value: Any, keys: set[str]) -> Any:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in keys:
                return item
        for item in value.values():
            found = _find_context_value(item, keys)
            if found not in (None, "", [], {}):
                return found
    if isinstance(value, list):
        for item in value:
            found = _find_context_value(item, keys)
            if found not in (None, "", [], {}):
                return found
    return None


def _compact_value(value: Any, fallback: str) -> str:
    if value in (None, "", [], {}):
        return fallback
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    return dumps(value)[:4000]


def _project_summary(context: dict[str, Any]) -> str:
    project = _find_context_value(context, {"project", "basic_info", "seed"}) or {}
    if not isinstance(project, dict):
        project = {}
    parts = [
        str(project.get("title") or project.get("genre") or ""),
        str(project.get("premise") or project.get("initial_idea") or project.get("one_sentence_story") or ""),
        str(project.get("target_reader") or ""),
    ]
    summary = "；".join([part for part in parts if part])
    return summary or "未提供明确输入，请根据 context 中已有项目资料和 request 生成候选。"


def _placeholder_context_value(label: str, context: dict[str, Any]) -> str:
    normalized = re.sub(r"\s+", "", label)

    def first(keys: set[str], fallback: str) -> str:
        return _compact_value(_find_context_value(context, keys), fallback)

    if "小说宪法" in normalized:
        return first({"novel_constitution", "story_bible", "constitution", "canon_context"}, _project_summary(context))
    if "核心矛盾系统" in normalized or "核心矛盾" in normalized:
        return first({"core_conflict_system", "main_conflict", "conflict_matrix"}, _project_summary(context))
    if "宏观大纲" in normalized or "全书宏观" in normalized:
        return first({"macro_outline", "outline", "book_outline", "structured_prompt"}, _project_summary(context))
    if "当前卷大纲" in normalized or "分卷大纲" in normalized or "当前要细化的卷" in normalized or "第一卷" in normalized:
        return first({"volume_outline", "volume_outlines", "volumes", "current_volume"}, _project_summary(context))
    if "接下来15章" in normalized or "滚动章节" in normalized or "第X章原始安排" in normalized or "章大纲" in normalized:
        return first({"rolling_chapter_outline", "chapter_beats", "chapter_outlines", "fallback_chapter_outlines", "current_chapter_outline"}, _project_summary(context))
    if "章节卡" in normalized:
        return first({"chapter_card", "current_chapter_outline"}, _project_summary(context))
    if "场景细纲" in normalized:
        return first({"scene_outline"}, _project_summary(context))
    if "叙事账本" in normalized:
        return first({"narrative_ledger", "ledger"}, _project_summary(context))
    if "伏笔账本" in normalized:
        return first({"foreshadowing_items", "foreshadowing_ledger"}, _project_summary(context))
    if "人物状态" in normalized or "主角状态" in normalized or "人物名单" in normalized or "关系变化表" in normalized:
        return first({"characters", "protagonist", "relationship_network", "graph"}, _project_summary(context))
    if "世界规则" in normalized:
        return first({"world_rules", "world_facts", "story_bible"}, _project_summary(context))
    if "时间线" in normalized:
        return first({"timeline", "world_facts", "completed_chapters"}, _project_summary(context))
    if "章节摘要" in normalized or "最近10章摘要" in normalized or "上一章摘要" in normalized or "剧情摘要" in normalized:
        return first({"chapter_summary", "previous_chapter_summary", "completed_chapters", "summaries"}, _project_summary(context))
    if "上一章结尾" in normalized:
        return first({"previous_chapter_ending", "cliffhanger", "completed_chapters"}, _project_summary(context))
    if "正文" in normalized or "本章正文" in normalized:
        return first({"chapter_text", "source_text", "integrated_draft", "final_chapter_text", "draft_text"}, _project_summary(context))
    if "审查意见" in normalized or "结构体检结果" in normalized:
        return first({"review_notes", "health_check_report", "structure_review", "logic_audit"}, _project_summary(context))
    if "样章" in normalized:
        return first({"style_sample", "sample_text", "final_chapter_text"}, _project_summary(context))
    if "结局" in normalized:
        return first({"ending", "ending_direction", "ending_closure_design"}, _project_summary(context))
    if "字数" in normalized or "正文长度" in normalized:
        return first({"chapter_word_target", "word_target", "target_words", "max_words"}, "按项目章节目标字数生成")
    if "题材" in normalized or "玄幻" in normalized:
        return first({"genre", "type_positioning"}, _project_summary(context))
    if "读者体验" in normalized:
        return first({"target_reader", "reader_hooks", "core_emotions"}, _project_summary(context))
    if "初始身份" in normalized:
        return first({"identity", "protagonist", "characters"}, _project_summary(context))
    if "初始处境" in normalized:
        return first({"premise", "initial_idea", "worldview"}, _project_summary(context))
    if "主题方向" in normalized:
        return first({"themes", "theme_direction", "story_bible"}, _project_summary(context))
    if "不希望" in normalized or "禁止事项" in normalized:
        return first({"forbidden_elements", "avoid_elements"}, "遵守项目禁用元素和用户补充约束。")
    if "第一人称" in normalized or "叙述视角" in normalized:
        return first({"narrative_pov"}, "第三人称有限视角")
    if "文风" in normalized or "节奏" in normalized:
        return first({"style_guide", "style"}, _project_summary(context))
    if "新增实体" in normalized:
        return "新增实体：名称、类型、等级、故事功能、是否需要补全、建议补全 Agent、必须补全字段。"
    if "输出可复制版本" in normalized:
        return "输出可复制版本"
    return f"{label}：{_project_summary(context)}"


def render_prompt_placeholders(system_prompt: str, context: dict[str, Any]) -> str:
    return re.sub(r"【([^】]+)】", lambda match: _placeholder_context_value(match.group(1), context), system_prompt)


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
    rendered_system_prompt = render_prompt_placeholders(system_prompt, context)
    prompt = (
        f"{rendered_system_prompt}\n\n"
        "你正在作为后端 Agent 节点运行。必须读取用户提供的 context，输出 expected_output_schema 对应的 JSON。"
    )
    result = llm_client.generate(prompt, dumps(user_payload), model)
    parsed = parse_json_object(result.content)
    payload = merge_agent_payload(fallback, parsed)
    validation_warnings = _validate_agent_payload(agent_name, payload, parsed)
    used_remote_model = bool(getattr(result, "used_remote_model", False))
    meta = {
        "provider": getattr(result, "provider", ""),
        "model": getattr(result, "model", model or ""),
        "used_remote_model": used_remote_model,
        "parsed": parsed is not None,
        "source": "remote_api" if used_remote_model else "local_fallback",
        "schema_valid": not validation_warnings,
        "validation_warnings": validation_warnings,
    }
    payload["_quality_gate"] = {
        "schema_valid": meta["schema_valid"],
        "severity": "ok" if meta["schema_valid"] else "warning",
        "warnings": validation_warnings,
    }
    return payload, meta
