from __future__ import annotations

import argparse
import json
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT / "logs" / "real_xianxia_20w_4000_flow"
CONTEXT_PATH = LOG_DIR / "run_context.json"
JSONL_PATH = LOG_DIR / "flow.jsonl"
MARKDOWN_PATH = LOG_DIR / "flow.md"
NOVEL_PATH = LOG_DIR / "final_novel.md"
DEFAULT_FLOW_CONFIG: dict[str, int] = {
    "target_words": 200000,
    "volume_count": 5,
    "chapter_count": 50,
    "chapters_per_volume": 10,
    "chapter_word_target": 4000,
    "chapter_word_min": 4000,
    "chapter_word_max": 4000,
}

DEFAULT_BASIC_INFO: dict[str, Any] = {
    "channel": "男频",
    "genre": "仙侠",
    "subgenres": ["东方玄幻", "宗门修行", "天道悬疑", "劫数推演"],
    "tags": ["凡人流", "宗门权谋", "天劫谜案", "古法器", "因果债", "群像修行"],
    "manual_tags": ["九霄灵脉", "问劫台", "命契残卷", "宗门审判", "天道账簿"],
    "target_reader": "喜欢仙侠修行、宗门权谋、天道谜案、凡人逆命和长篇升级线的读者",
    "volume_count": DEFAULT_FLOW_CONFIG["volume_count"],
    "chapter_count": DEFAULT_FLOW_CONFIG["chapter_count"],
    "planned_chapter_count": DEFAULT_FLOW_CONFIG["chapter_count"],
    "chapters_per_volume": DEFAULT_FLOW_CONFIG["chapters_per_volume"],
    "chapter_word_target": DEFAULT_FLOW_CONFIG["chapter_word_target"],
    "chapter_word_min": DEFAULT_FLOW_CONFIG["chapter_word_min"],
    "chapter_word_max": DEFAULT_FLOW_CONFIG["chapter_word_max"],
    "target_words": DEFAULT_FLOW_CONFIG["target_words"],
    "style": "古意凝练、节奏紧张、强钩子、仙侠意象清晰，少堆设定，多让修行规则在行动、代价和因果中显形。",
    "initial_idea": (
        "九霄界诸宗以天劫定品阶，凡人少年沈砚在问劫台替人抄录劫数残卷时，发现天劫并非天道公判，"
        "而是上古宗门用因果债操控灵脉和飞升名额的审判系统。为救被错判为魔胎的师妹，他必须在宗门追杀、"
        "古器反噬和天道债簿的层层逼迫中，查清九霄灵脉崩坏的真相。"
    ),
}

FLOW_REQUIREMENT = ""


def set_log_dir(path: Path) -> None:
    global LOG_DIR, CONTEXT_PATH, JSONL_PATH, MARKDOWN_PATH, NOVEL_PATH
    LOG_DIR = path
    CONTEXT_PATH = LOG_DIR / "run_context.json"
    JSONL_PATH = LOG_DIR / "flow.jsonl"
    MARKDOWN_PATH = LOG_DIR / "flow.md"
    NOVEL_PATH = LOG_DIR / "final_novel.md"


def build_flow_requirement(config: dict[str, int]) -> str:
    target_wan = config["target_words"] / 10000
    target_label = f"{target_wan:g}万字" if config["target_words"] >= 10000 else f"{config['target_words']}字"
    return (
        f"目标规模：{target_label}，{config['volume_count']}卷，{config['chapter_count']}章，每章{config['chapter_word_target']}字。"
        f"每卷约{config['chapters_per_volume']}章。"
        "大纲讨论必须按总纲、逐卷卷纲、逐章章纲推进；每确认一卷/一章都更新正典。"
        "每章必须区分危机、高潮、结果；伏笔、角色、设定新增需要在确认后入正式正典。"
        "题材方向：仙侠、凡人逆命、宗门权谋、天劫悬疑、因果债、古法器、灵脉危机与修行升级。"
    )


def apply_flow_config(context: dict[str, Any], args: argparse.Namespace) -> dict[str, int]:
    config = {
        "target_words": int(args.target_words),
        "volume_count": int(args.volume_count),
        "chapter_count": int(args.chapter_count),
        "chapters_per_volume": int(args.chapters_per_volume),
        "chapter_word_target": int(args.chapter_word_target),
        "chapter_word_min": int(args.chapter_word_min),
        "chapter_word_max": int(args.chapter_word_max),
    }
    context["flow_config"] = config
    DEFAULT_BASIC_INFO.update(
        {
            "volume_count": config["volume_count"],
            "chapter_count": config["chapter_count"],
            "planned_chapter_count": config["chapter_count"],
            "chapters_per_volume": config["chapters_per_volume"],
            "chapter_word_target": config["chapter_word_target"],
            "chapter_word_min": config["chapter_word_min"],
            "chapter_word_max": config["chapter_word_max"],
            "target_words": config["target_words"],
        }
    )
    global FLOW_REQUIREMENT
    FLOW_REQUIREMENT = build_flow_requirement(config)
    return config


FLOW_REQUIREMENT = build_flow_requirement(DEFAULT_FLOW_CONFIG)


class FlowClient:
    def __init__(self, api_base: str) -> None:
        self.api_base = api_base.rstrip("/")

    def request(self, method: str, path: str, payload: dict[str, Any] | None = None, timeout: int = 900) -> dict[str, Any]:
        url = f"{self.api_base}{path}"
        body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        started = time.time()
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read().decode("utf-8")
                status = response.status
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            status = exc.code
        elapsed_ms = int((time.time() - started) * 1000)
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = {"raw": raw}
        log_event(
            "api",
            {
                "method": method,
                "path": path,
                "status": status,
                "elapsed_ms": elapsed_ms,
                "request": payload,
                "response": parsed,
            },
        )
        if status >= 400:
            raise RuntimeError(f"{method} {path} failed: {status} {raw[:1000]}")
        if isinstance(parsed, dict) and not parsed.get("success", False):
            raise RuntimeError(f"{method} {path} returned error: {parsed}")
        return parsed["data"] if isinstance(parsed, dict) and "data" in parsed else parsed


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def ensure_logs() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    if not MARKDOWN_PATH.exists():
        MARKDOWN_PATH.write_text("# 长篇真实流程日志\n\n", encoding="utf-8")


def log_event(kind: str, payload: dict[str, Any]) -> None:
    ensure_logs()
    record = {"ts": now_iso(), "kind": kind, **payload}
    with JSONL_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    if kind in {"stage", "problem", "artifact", "job", "chapter", "settings_audit"}:
        with MARKDOWN_PATH.open("a", encoding="utf-8") as handle:
            handle.write(f"## {record['ts']} {kind}\n\n")
            handle.write("```json\n")
            handle.write(json.dumps(payload, ensure_ascii=False, indent=2))
            handle.write("\n```\n\n")


def is_retryable_generation_error(error: Any) -> bool:
    if isinstance(error, (dict, list)):
        error_text = json.dumps(error, ensure_ascii=False)
    else:
        error_text = str(error)
    lowered = error_text.lower()
    fatal_markers = (
        "requires a remote",
        "api key",
        "authentication",
        "unauthorized",
        "invalid api key",
        "incorrect api key",
        "permission denied",
        "forbidden",
        "insufficient_quota",
    )
    if any(marker in lowered for marker in fatal_markers):
        return False
    retryable_markers = (
        "最低字数",
        "未达到最低",
        "below",
        "超过",
        "上限",
        "maximum",
        "connection error",
        "connection reset",
        "connecterror",
        "remoteprotocolerror",
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
    return any(marker in lowered for marker in retryable_markers)


def load_context() -> dict[str, Any]:
    ensure_logs()
    if CONTEXT_PATH.exists():
        return json.loads(CONTEXT_PATH.read_text(encoding="utf-8"))
    return {"basic_info": DEFAULT_BASIC_INFO, "created_at": now_iso()}


def save_context(context: dict[str, Any]) -> None:
    ensure_logs()
    context["updated_at"] = now_iso()
    CONTEXT_PATH.write_text(json.dumps(context, ensure_ascii=False, indent=2), encoding="utf-8")


def first(items: Any) -> dict[str, Any]:
    if isinstance(items, list) and items and isinstance(items[0], dict):
        return items[0]
    return {}


def require_project_id(client: FlowClient, context: dict[str, Any], project_id: str | None, *, force_new: bool = False) -> str:
    if project_id:
        context["project_id"] = project_id
        save_context(context)
        return project_id
    if context.get("project_id") and not force_new:
        return str(context["project_id"])
    projects = client.request("GET", "/projects").get("projects", [])
    if len(projects) == 1 and not force_new:
        context["project_id"] = projects[0]["id"]
        save_context(context)
        return str(context["project_id"])
    project_payload = {
        "title": "九霄问劫录",
        "genre": "仙侠",
        "target_reader": DEFAULT_BASIC_INFO["target_reader"],
        "premise": DEFAULT_BASIC_INFO["initial_idea"],
        "style_guide": DEFAULT_BASIC_INFO["style"],
        "language": "zh-CN",
        "planned_chapter_count": DEFAULT_BASIC_INFO["chapter_count"],
        "planned_volume_count": DEFAULT_BASIC_INFO["volume_count"],
        "chapters_per_volume": DEFAULT_BASIC_INFO["chapters_per_volume"],
        "chapter_word_target": DEFAULT_BASIC_INFO["chapter_word_target"],
        "chapter_word_min": DEFAULT_BASIC_INFO["chapter_word_min"],
        "chapter_word_max": DEFAULT_BASIC_INFO["chapter_word_max"],
        "target_words": DEFAULT_BASIC_INFO["target_words"],
        "initial_idea": DEFAULT_BASIC_INFO["initial_idea"],
    }
    data = client.request("POST", "/projects", project_payload)
    context["project_id"] = data["project"]["id"]
    save_context(context)
    return str(context["project_id"])


def run_creation(client: FlowClient, context: dict[str, Any], project_id: str) -> None:
    if context.get("creation_committed"):
        log_event("stage", {"stage": "creation", "status": "skipped", "reason": "already committed"})
        return
    log_event("stage", {"stage": "creation", "status": "started", "project_id": project_id})
    session_id = context.get("creation_session_id")
    if not session_id:
        created = client.request("POST", f"/projects/{project_id}/creation/sessions", {"basic_info": DEFAULT_BASIC_INFO})
        session_id = created["session"]["id"]
        context["creation_session_id"] = session_id
        context["basic_info"] = created["session"]["basic_info"]
        save_context(context)

    worldview = context.get("selected_worldview")
    if not worldview:
        data = client.request(
            "POST",
            f"/projects/{project_id}/creation/sessions/{session_id}/worldviews",
            {"count": 1, "replace_existing": True, "manual_input": FLOW_REQUIREMENT},
        )
        worldview = first(data.get("cards"))
        context["selected_worldview"] = worldview
        save_context(context)

    protagonist = context.get("selected_protagonist")
    if not protagonist:
        data = client.request(
            "POST",
            f"/projects/{project_id}/creation/sessions/{session_id}/protagonists",
            {"count": 1, "replace_existing": True, "selected_worldview": worldview, "manual_input": FLOW_REQUIREMENT},
        )
        protagonist = first(data.get("cards"))
        context["selected_protagonist"] = protagonist
        save_context(context)

    title = context.get("selected_title")
    market = context.get("market_position")
    if not title:
        data = client.request(
            "POST",
            f"/projects/{project_id}/creation/sessions/{session_id}/market-position",
            {
                "count": 1,
                "replace_existing": True,
                "selected_worldview": worldview,
                "selected_protagonist": protagonist,
                "manual_input": FLOW_REQUIREMENT,
            },
        )
        title = first(data.get("title_candidates") or data.get("cards"))
        market = first(data.get("market_position_candidates")) or {}
        context["selected_title"] = title
        context["market_position"] = market
        save_context(context)

    if not context.get("project_seed"):
        data = client.request(
            "POST",
            f"/projects/{project_id}/creation/sessions/{session_id}/seed",
            {
                "selected_worldview": worldview,
                "selected_protagonist": protagonist,
                "selected_title": title,
                "market_position": market or {},
                "user_note": FLOW_REQUIREMENT,
            },
        )
        context["project_seed"] = data["project_seed"]
        save_context(context)

    if not context.get("core_conflict_system"):
        data = client.request(
            "POST",
            f"/projects/{project_id}/creation/sessions/{session_id}/core-conflict",
            {"instruction": FLOW_REQUIREMENT},
        )
        context["core_conflict_system"] = data["core_conflict_system"]
        save_context(context)

    review_status = ""
    for attempt in range(1, 4):
        if not context.get("novel_constitution") or review_status in {"needs_revision", "blocked"}:
            instruction = FLOW_REQUIREMENT
            if context.get("constitution_review"):
                instruction += f"\n请按上一轮压力测试意见修订：{json.dumps(context['constitution_review'], ensure_ascii=False)}"
            data = client.request(
                "POST",
                f"/projects/{project_id}/creation/sessions/{session_id}/constitution",
                {"instruction": instruction},
            )
            context["novel_constitution"] = data["novel_constitution"]
            save_context(context)
        data = client.request(
            "POST",
            f"/projects/{project_id}/creation/sessions/{session_id}/constitution-review",
            {"instruction": FLOW_REQUIREMENT, "novel_constitution": context["novel_constitution"]},
        )
        context["constitution_review"] = data["constitution_review"]
        save_context(context)
        review_status = str(data["constitution_review"].get("status") or "")
        log_event("stage", {"stage": "constitution_review", "attempt": attempt, "status": review_status})
        if review_status in {"passed", "passed_with_notes"}:
            break
    if review_status not in {"passed", "passed_with_notes"}:
        raise RuntimeError(f"小说宪法压力测试未通过：{review_status}")

    if not context.get("canon_candidates"):
        data = client.request(
            "POST",
            f"/projects/{project_id}/creation/sessions/{session_id}/canon-preview",
            {"instruction": FLOW_REQUIREMENT, "novel_constitution": context["novel_constitution"]},
        )
        context["canon_candidates"] = data["canon_candidates"]
        save_context(context)

    data = client.request(
        "POST",
        f"/projects/{project_id}/creation/sessions/{session_id}/commit",
        {
            "user_note": "真实 LLM 20万字流程确认入库。",
            "approved_canon_sections": ["project", "story_bible", "characters", "entities", "world_facts", "graph"],
        },
    )
    context["creation_committed"] = True
    context["project"] = data["project"]
    context["story_bible"] = data["story_bible"]
    save_context(context)
    log_event("stage", {"stage": "creation", "status": "committed", "project": data["project"]})


def outline_payload(extra: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = {
        "requirement": FLOW_REQUIREMENT,
        "target_words": DEFAULT_BASIC_INFO["target_words"],
        "volume_count": DEFAULT_BASIC_INFO["volume_count"],
        "chapters_per_volume": DEFAULT_BASIC_INFO["chapters_per_volume"],
        "chapter_word_target": DEFAULT_BASIC_INFO["chapter_word_target"],
        "chapter_word_min": DEFAULT_BASIC_INFO["chapter_word_min"],
        "chapter_word_max": DEFAULT_BASIC_INFO["chapter_word_max"],
        "scale_plan": {
            "target_words": DEFAULT_BASIC_INFO["target_words"],
            "volume_count": DEFAULT_BASIC_INFO["volume_count"],
            "chapter_count": DEFAULT_BASIC_INFO["chapter_count"],
            "chapters_per_volume": DEFAULT_BASIC_INFO["chapters_per_volume"],
            "chapter_word_target": DEFAULT_BASIC_INFO["chapter_word_target"],
            "chapter_word_min": DEFAULT_BASIC_INFO["chapter_word_min"],
            "chapter_word_max": DEFAULT_BASIC_INFO["chapter_word_max"],
        },
    }
    if extra:
        payload.update(extra)
    return payload


def poll_job(client: FlowClient, job_id: str, timeout_seconds: int = 21600, interval: int = 10) -> dict[str, Any]:
    started = time.time()
    last_progress = None
    while True:
        data = client.request("GET", f"/jobs/{job_id}", timeout=120)
        job = data["job"]
        progress = job.get("progress") or {}
        progress_key = json.dumps(progress, ensure_ascii=False, sort_keys=True)
        if progress_key != last_progress:
            log_event("job", {"job_id": job_id, "status": job.get("status"), "progress": progress, "error": job.get("error")})
            last_progress = progress_key
        if job.get("status") in {"succeeded", "failed", "cancelled"}:
            return job
        if time.time() - started > timeout_seconds:
            raise TimeoutError(f"job timeout: {job_id}")
        time.sleep(interval)


def text_length(text: str) -> int:
    return len(re.sub(r"\s+", "", str(text or "")))


def settings_audit(client: FlowClient, context: dict[str, Any], project_id: str, chapter_no: int) -> dict[str, Any]:
    endpoints = {
        "settings_tree": f"/projects/{project_id}/settings/tree",
        "settings_health": f"/projects/{project_id}/settings/health",
        "version_timeline": f"/projects/{project_id}/settings/version-timeline",
        "creation_profile": f"/projects/{project_id}/creation/profile",
        "characters": f"/projects/{project_id}/characters",
        "entities": f"/projects/{project_id}/entities",
        "world_facts": f"/projects/{project_id}/world-facts",
        "graph": f"/projects/{project_id}/graph",
        "foreshadowing": f"/projects/{project_id}/foreshadowing",
        "pending_proposals": f"/projects/{project_id}/settings/proposals?status=pending",
    }
    raw: dict[str, Any] = {}
    errors: dict[str, str] = {}
    for name, path in endpoints.items():
        try:
            raw[name] = client.request("GET", path, timeout=180)
        except Exception as exc:
            errors[name] = str(exc)

    tree_nodes = raw.get("settings_tree", {}).get("nodes", [])
    health = raw.get("settings_tree", {}).get("health") or raw.get("settings_health", {}).get("health") or {}
    timeline = raw.get("version_timeline", {})
    timeline_chapters = timeline.get("chapters", []) if isinstance(timeline, dict) else []
    chapter_events = []
    for item in timeline_chapters:
        chapter = item.get("chapter") if isinstance(item, dict) else {}
        if isinstance(chapter, dict) and int(chapter.get("chapter_no") or 0) == chapter_no:
            chapter_events = item.get("events") or []
            break

    graph = raw.get("graph", {}).get("graph", {})
    proposals = raw.get("pending_proposals", {}).get("proposals", [])
    summary = {
        "chapter_no": chapter_no,
        "checked_at": now_iso(),
        "api_sections_checked": sorted(endpoints),
        "api_errors": errors,
        "node_count": len(tree_nodes) if isinstance(tree_nodes, list) else 0,
        "official_count": health.get("official_count"),
        "versioned_count": health.get("versioned_count"),
        "version_coverage": health.get("version_coverage"),
        "character_count": len(raw.get("characters", {}).get("characters", [])),
        "entity_count": len(raw.get("entities", {}).get("entities", [])),
        "world_fact_count": len(raw.get("world_facts", {}).get("world_facts", [])),
        "graph_node_count": len(graph.get("nodes", [])) if isinstance(graph, dict) else 0,
        "graph_edge_count": len(graph.get("edges", [])) if isinstance(graph, dict) else 0,
        "foreshadowing_count": len(raw.get("foreshadowing", {}).get("foreshadowing_items", [])),
        "pending_proposal_count": len(proposals) if isinstance(proposals, list) else 0,
        "current_chapter_timeline_event_count": len(chapter_events) if isinstance(chapter_events, list) else 0,
        "has_creation_profile": bool(raw.get("creation_profile")),
        "has_explicit_version_info": bool(health.get("versioned_count") or chapter_events),
    }
    problems: list[str] = []
    if errors:
        problems.append("设定页相关 API 存在读取错误")
    if not summary["node_count"]:
        problems.append("设定文件树没有节点")
    if not summary["has_explicit_version_info"]:
        problems.append("未发现明确版本信息或章节轴事件")
    if summary["character_count"] == 0:
        problems.append("角色板块为空")
    if summary["world_fact_count"] == 0:
        problems.append("世界观事实板块为空")
    summary["problems"] = problems
    context.setdefault("settings_audits", {})[str(chapter_no)] = summary
    save_context(context)
    log_event("settings_audit", summary)
    if problems:
        log_event("problem", {"stage": "settings_audit", "chapter_no": chapter_no, "problems": problems})
    return summary


def confirmed_chapter_numbers(client: FlowClient, project_id: str, session_id: str) -> set[int]:
    data = client.request("GET", f"/projects/{project_id}/outline/debate/sessions/{session_id}", timeout=120)
    session = data["session"]
    confirmed: set[int] = set()
    chapters_candidate = (session.get("confirmed_candidates") or {}).get("chapters") if isinstance(session.get("confirmed_candidates"), dict) else None
    for item in (chapters_candidate or {}).get("chapter_outlines", []) if isinstance(chapters_candidate, dict) else []:
        if isinstance(item, dict) and item.get("chapter_no"):
            confirmed.add(int(item["chapter_no"]))
    chapter_run = (session.get("phase_runs") or {}).get("chapters") if isinstance(session.get("phase_runs"), dict) else None
    for item in (chapter_run or {}).get("confirmation_items", []) if isinstance(chapter_run, dict) else []:
        if isinstance(item, dict) and item.get("candidate_status") == "confirmed" and item.get("chapter_no"):
            confirmed.add(int(item["chapter_no"]))
    return confirmed


def contiguous_segments(numbers: list[int]) -> list[tuple[int, int]]:
    if not numbers:
        return []
    ordered = sorted(numbers)
    segments: list[tuple[int, int]] = []
    start = previous = ordered[0]
    for number in ordered[1:]:
        if number == previous + 1:
            previous = number
            continue
        segments.append((start, previous))
        start = previous = number
    segments.append((start, previous))
    return segments


def run_outline(client: FlowClient, context: dict[str, Any], project_id: str, chapter_end: int = 50, smoke: bool = False) -> None:
    chapter_count = int(DEFAULT_BASIC_INFO["chapter_count"])
    chapters_per_volume = int(DEFAULT_BASIC_INFO["chapters_per_volume"])
    volume_count = int(DEFAULT_BASIC_INFO["volume_count"])
    chapter_end = min(chapter_count, max(1, int(chapter_end)))
    target_volume_count = min(volume_count, (chapter_end + chapters_per_volume - 1) // chapters_per_volume)
    key_prefix = "smoke_" if smoke else ""
    session_key = f"{key_prefix}outline_session_id"
    book_key = f"{key_prefix}book_confirmed"
    volumes_key = f"{key_prefix}confirmed_volumes"
    chapters_key = f"{key_prefix}chapters_confirmed"
    commit_key = f"{key_prefix}outline_committed"
    commit_summary_key = f"{key_prefix}outline_commit"
    if context.get(commit_key):
        log_event("stage", {"stage": "outline", "status": "skipped", "reason": "already committed"})
        return
    log_event("stage", {"stage": "outline", "status": "started", "project_id": project_id, "chapter_end": chapter_end, "smoke": smoke})
    session_id = context.get(session_key)
    if not session_id:
        brief = FLOW_REQUIREMENT if not smoke else f"{FLOW_REQUIREMENT} 轻量 smoke 只确认前{chapter_end}章，用于接口、正典和设定审计验收。"
        data = client.request(
            "POST",
            f"/projects/{project_id}/outline/debate/sessions",
            {"idempotency_key": f"real-flow-outline:{project_id}:{key_prefix}{chapter_end}", "brief": brief},
        )
        session_id = data["session"]["id"]
        context[session_key] = session_id
        save_context(context)

    if not context.get(book_key):
        log_event("stage", {"stage": "outline_book", "status": "running", "max_agent_turns": 6})
        client.request("POST", f"/projects/{project_id}/outline/debate/sessions/{session_id}/book/run", outline_payload({"max_agent_turns": 6}))
        client.request(
            "POST",
            f"/projects/{project_id}/outline/debate/sessions/{session_id}/book/confirm",
            {"notes": "确认总纲，并写入故事圣经与分卷壳。"},
        )
        context[book_key] = True
        save_context(context)

    confirmed_volumes = set(int(item) for item in context.get(volumes_key, []))
    for volume_no in range(1, target_volume_count + 1):
        if volume_no in confirmed_volumes:
            continue
        log_event("stage", {"stage": "outline_volume", "status": "running", "volume_no": volume_no, "max_agent_turns": 4})
        client.request(
            "POST",
            f"/projects/{project_id}/outline/debate/sessions/{session_id}/volumes/run",
            outline_payload({"target_volume_no": volume_no, "max_agent_turns": 4}),
        )
        client.request(
            "POST",
            f"/projects/{project_id}/outline/debate/sessions/{session_id}/volumes/confirm",
            {"item_key": f"volume:{volume_no}", "notes": f"确认第{volume_no}卷卷纲，并更新正典。"},
        )
        confirmed_volumes.add(volume_no)
        context[volumes_key] = sorted(confirmed_volumes)
        save_context(context)

    if not context.get(chapters_key):
        for volume_no in range(1, target_volume_count + 1):
            volume_start = (volume_no - 1) * chapters_per_volume + 1
            volume_end = min(volume_no * chapters_per_volume, chapter_end)
            while True:
                confirmed = confirmed_chapter_numbers(client, project_id, session_id)
                missing = [chapter_no for chapter_no in range(volume_start, volume_end + 1) if chapter_no not in confirmed]
                if not missing:
                    break
                for start_no, end_no in contiguous_segments(missing):
                    log_event(
                        "stage",
                        {
                            "stage": "outline_chapter_range",
                            "status": "running",
                            "volume_no": volume_no,
                            "start_chapter_no": start_no,
                            "end_chapter_no": end_no,
                            "max_agent_turns": 1,
                        },
                    )
                    client.request(
                        "POST",
                        f"/projects/{project_id}/outline/debate/sessions/{session_id}/chapters/run",
                        outline_payload(
                            {
                                "chapter_ranges": [{"volume_no": volume_no, "start_chapter_no": start_no, "end_chapter_no": end_no}],
                                "max_agent_turns": 1,
                            }
                        ),
                    )
                    for chapter_no in range(start_no, end_no + 1):
                        client.request(
                            "POST",
                            f"/projects/{project_id}/outline/debate/sessions/{session_id}/chapters/confirm",
                            {"item_key": f"chapter:{chapter_no}", "notes": f"确认第{chapter_no}章章纲，并更新正典。"},
                        )
                break
        confirmed = confirmed_chapter_numbers(client, project_id, session_id)
        if len([chapter_no for chapter_no in range(1, chapter_end + 1) if chapter_no in confirmed]) < chapter_end:
            raise RuntimeError(f"章纲确认不完整：已确认 {sorted(confirmed)}")
        context[chapters_key] = True
        save_context(context)

    data = client.request(
        "POST",
        f"/projects/{project_id}/outline/debate/sessions/{session_id}/commit",
        {
            "overwrite_existing_chapters": True,
            "notes": f"确认 {FLOW_REQUIREMENT} 完整大纲并写入正式章节。"
            if not smoke
            else f"轻量 smoke 确认前{chapter_end}章章纲并写入正式章节。",
        },
    )
    context[commit_key] = True
    context[commit_summary_key] = {
        "volume_count": len(data.get("book_commit", {}).get("volumes", [])),
        "chapter_count": len(data.get("chapter_commit", {}).get("chapters", [])),
        "chapter_end": chapter_end,
        "smoke": smoke,
    }
    save_context(context)
    log_event("stage", {"stage": "outline", "status": "committed", "summary": context[commit_summary_key]})


def run_draft(client: FlowClient, context: dict[str, Any], project_id: str, chapter_start: int = 1, chapter_end: int = 50, smoke: bool = False) -> None:
    draft_key = "smoke_draft_committed" if smoke else "draft_committed"
    completed_key = "smoke_completed_chapters" if smoke else "completed_chapters"
    chapter_jobs_key = "smoke_chapter_jobs" if smoke else "chapter_jobs"
    if context.get(draft_key):
        log_event("stage", {"stage": "draft", "status": "skipped", "reason": "already completed"})
        return
    chapter_start = max(1, int(chapter_start))
    chapter_count = int(DEFAULT_BASIC_INFO["chapter_count"])
    chapter_word_target = int(DEFAULT_BASIC_INFO["chapter_word_target"])
    chapter_word_min = int(DEFAULT_BASIC_INFO["chapter_word_min"])
    chapter_word_max = int(DEFAULT_BASIC_INFO["chapter_word_max"])
    chapter_end = min(chapter_count, int(chapter_end))
    log_event("stage", {"stage": "draft", "status": "started", "project_id": project_id, "mode": "sequential_chapter_jobs", "chapter_start": chapter_start, "chapter_end": chapter_end})
    chapters = client.request("GET", f"/projects/{project_id}/chapters", timeout=120).get("chapters", [])
    chapter_by_no = {int(item.get("chapter_no") or 0): item for item in chapters if item.get("chapter_no")}
    missing = [chapter_no for chapter_no in range(chapter_start, chapter_end + 1) if chapter_no not in chapter_by_no]
    if missing:
        raise RuntimeError(f"缺少章节，无法逐章生成：{missing}")

    completed = set(int(item) for item in context.get(completed_key, []))
    context.setdefault(chapter_jobs_key, {})
    for chapter_no in range(chapter_start, chapter_end + 1):
        chapter = chapter_by_no[chapter_no]
        chapter_id = chapter["id"]
        current_text = chapter.get("final_text") or chapter.get("draft_text") or ""
        current_length = text_length(current_text)
        if chapter_no in completed and max(1, chapter_word_min - 100) <= current_length <= chapter_word_max:
            settings_audit(client, context, project_id, chapter_no)
            continue
        job = None
        job_id = ""
        final_word_count = 0
        final_text_length = 0
        for attempt, target_words, max_words in (
            (1, chapter_word_target, chapter_word_max),
            (2, chapter_word_target, chapter_word_max),
            (3, chapter_word_target, chapter_word_max),
        ):
            instruction = (
                f"请生成仙侠长篇小说第{chapter_no}章正文，目标约{target_words}字，最低不少于{chapter_word_min}字，尽量控制在{max_words}字以内。"
                "必须承接已确认章纲、小说宪法、前文摘要和正典上下文；必须包含本章危机、高潮、结果；"
                "新增角色、法器、宗门、灵脉规则、伏笔和关系变化必须在章后正典候选中注明来源与置信度。"
                "只写本章核心行动链的3到4个必要场景，禁止展开支线、回忆长段和额外设定说明；"
                f"请在达到{chapter_word_min}字后立刻收束结尾，避免超过{chapter_word_max}字；若接近结尾仍不足{chapter_word_min}字，才补充必要的行动、感官细节和后果承担段落。"
            )
            idem = f"xianxia-real-draft:{project_id}:{chapter_no}:strict-range-v2:{attempt}:{chapter_word_target}:{chapter_word_max}"
            data = client.request(
                "POST",
                f"/projects/{project_id}/chapters/{chapter_id}/draft",
                {
                    "user_instruction": instruction,
                    "async_mode": True,
                    "max_words": max_words,
                    "idempotency_key": idem,
                },
                timeout=120,
            )
            job_id = data["job"]["id"]
            context[chapter_jobs_key][str(chapter_no)] = job_id
            save_context(context)
            log_event(
                "chapter",
                {
                    "chapter_no": chapter_no,
                    "status": "queued",
                    "job_id": job_id,
                    "attempt": attempt,
                    "target_words": target_words,
                    "max_words": max_words,
                },
            )
            job = poll_job(client, job_id, timeout_seconds=7200, interval=10)
            if job.get("status") == "succeeded":
                chapter_after_attempt = client.request("GET", f"/projects/{project_id}/chapters/{chapter_id}", timeout=120)["chapter"]
                attempt_text = chapter_after_attempt.get("final_text") or chapter_after_attempt.get("draft_text") or ""
                final_word_count = int(chapter_after_attempt.get("word_count") or text_length(attempt_text))
                final_text_length = text_length(attempt_text)
                if chapter_word_min <= final_text_length <= chapter_word_max:
                    break
                log_event(
                    "problem",
                    {
                        "stage": "draft",
                        "chapter_no": chapter_no,
                        "job_id": job_id,
                        "attempt": attempt,
                        "issue": "chapter_length_out_of_range",
                        "word_count": final_word_count,
                        "text_length": final_text_length,
                        "minimum": chapter_word_min,
                        "maximum": chapter_word_max,
                    },
                )
                if attempt == 3:
                    raise RuntimeError(
                        f"第{chapter_no}章字数不在范围内：当前 {final_text_length}，要求 {chapter_word_min}-{chapter_word_max}"
                    )
                continue
            error_text = str(job.get("error") or "")
            retryable = is_retryable_generation_error(job.get("error") or error_text)
            log_event(
                "problem",
                {
                    "stage": "draft",
                    "chapter_no": chapter_no,
                    "job_id": job_id,
                    "attempt": attempt,
                    "issue": "chapter_generation_failed",
                    "retryable": retryable,
                    "error": job.get("error"),
                },
            )
            if not retryable or attempt == 3:
                raise RuntimeError(f"第{chapter_no}章生成失败：{job}")
        chapter = client.request("GET", f"/projects/{project_id}/chapters/{chapter_id}", timeout=120)["chapter"]
        text = chapter.get("final_text") or chapter.get("draft_text") or ""
        word_count = int(chapter.get("word_count") or text_length(text))
        final_text_length = text_length(text)
        if not (chapter_word_min <= final_text_length <= chapter_word_max):
            raise RuntimeError(f"第{chapter_no}章字数不在范围内：当前 {final_text_length}，要求 {chapter_word_min}-{chapter_word_max}")
        completed.add(chapter_no)
        context[completed_key] = sorted(completed)
        save_context(context)
        log_event(
            "chapter",
            {
                "chapter_no": chapter_no,
                "status": "completed",
                "job_id": job_id,
                "title": chapter.get("title"),
                "word_count": word_count,
                "text_length": final_text_length,
            },
        )
        settings_audit(client, context, project_id, chapter_no)
    if all(chapter_no in completed for chapter_no in range(chapter_start, chapter_end + 1)):
        context[draft_key] = True
    save_context(context)
    log_event("stage", {"stage": "draft", "status": "completed", "completed_chapters": sorted(completed)})


def export_novel(client: FlowClient, context: dict[str, Any], project_id: str) -> None:
    data = client.request("GET", f"/projects/{project_id}/chapters", timeout=120)
    chapters = data.get("chapters", [])
    chapters.sort(key=lambda item: int(item.get("chapter_no") or 0))
    project = context.get("project") or client.request("GET", f"/projects/{project_id}")["project"]
    lines = [f"# {project.get('title') or '未命名小说'}", ""]
    total_words = 0
    missing: list[int] = []
    for chapter in chapters:
        chapter_no = int(chapter.get("chapter_no") or 0)
        title = chapter.get("title") or f"第{chapter_no}章"
        text = chapter.get("final_text") or chapter.get("draft_text") or ""
        word_count = text_length(text)
        total_words += word_count
        if not text.strip():
            missing.append(chapter_no)
        lines.extend([f"## 第{chapter_no}章 {title}", "", text.strip(), ""])
    NOVEL_PATH.write_text("\n".join(lines), encoding="utf-8")
    batch_job = context.get("batch_job") if isinstance(context.get("batch_job"), dict) else {}
    job_request = batch_job.get("request") if isinstance(batch_job.get("request"), dict) else {}
    provider = job_request.get("provider") or context.get("provider")
    model = batch_job.get("model") or context.get("model")
    if not provider:
        try:
            model_info = client.request("GET", "/llm/models", timeout=120)
            provider = model_info.get("default_provider") or provider
            model = model or model_info.get("default_model")
        except Exception as exc:  # pragma: no cover - export should still succeed if metadata lookup fails.
            log_event("problem", {"stage": "export", "issue": "llm_metadata_lookup_failed", "error": str(exc)})
    context["novel_path"] = str(NOVEL_PATH)
    context["export_path"] = str(NOVEL_PATH)
    context["provider"] = provider
    context["model"] = model
    context["export_summary"] = {
        "chapter_count": len(chapters),
        "total_words": total_words,
        "missing_chapters": missing,
        "bytes": NOVEL_PATH.stat().st_size,
    }
    save_context(context)
    log_event("artifact", {"type": "novel", "path": str(NOVEL_PATH), "summary": context["export_summary"]})


def run_smoke(client: FlowClient, context: dict[str, Any], project_id: str, smoke_chapter_count: int = 3) -> None:
    smoke_chapter_count = max(1, int(smoke_chapter_count))
    chapter_count = int(DEFAULT_BASIC_INFO["chapter_count"])
    log_event("stage", {"stage": "smoke", "status": "started", "chapter_count": min(chapter_count, smoke_chapter_count)})
    run_creation(client, context, project_id)
    run_outline(client, context, project_id, chapter_end=min(chapter_count, smoke_chapter_count), smoke=True)
    run_draft(client, context, project_id, 1, chapter_end=min(chapter_count, smoke_chapter_count), smoke=True)
    for chapter_no in range(1, min(chapter_count, smoke_chapter_count) + 1):
        settings_audit(client, context, project_id, chapter_no)
    context["smoke_committed"] = True
    save_context(context)
    log_event("stage", {"stage": "smoke", "status": "completed", "chapter_count": min(chapter_count, smoke_chapter_count)})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-base", default="http://127.0.0.1:8015/api")
    parser.add_argument("--project-id", default="")
    parser.add_argument("--stage", choices=["all", "creation", "outline", "draft", "export", "smoke"], default="all")
    parser.add_argument("--fresh", action="store_true", help="ignore and archive existing run context before starting")
    parser.add_argument("--chapter-start", type=int, default=1)
    parser.add_argument("--chapter-end", type=int, default=50)
    parser.add_argument("--smoke-chapter-count", type=int, default=3)
    parser.add_argument("--target-words", type=int, default=DEFAULT_FLOW_CONFIG["target_words"])
    parser.add_argument("--volume-count", type=int, default=DEFAULT_FLOW_CONFIG["volume_count"])
    parser.add_argument("--chapter-count", type=int, default=DEFAULT_FLOW_CONFIG["chapter_count"])
    parser.add_argument("--chapters-per-volume", type=int, default=DEFAULT_FLOW_CONFIG["chapters_per_volume"])
    parser.add_argument("--chapter-word-target", type=int, default=DEFAULT_FLOW_CONFIG["chapter_word_target"])
    parser.add_argument("--chapter-word-min", type=int, default=DEFAULT_FLOW_CONFIG["chapter_word_min"])
    parser.add_argument("--chapter-word-max", type=int, default=DEFAULT_FLOW_CONFIG["chapter_word_max"])
    parser.add_argument("--log-dir", default=str(LOG_DIR))
    args = parser.parse_args()
    set_log_dir(Path(args.log_dir))
    ensure_logs()
    if args.fresh and CONTEXT_PATH.exists():
        archive_path = CONTEXT_PATH.with_suffix(f".{int(time.time())}.json")
        CONTEXT_PATH.rename(archive_path)
        log_event("stage", {"stage": "fresh_context", "archived_context": str(archive_path)})
    client = FlowClient(args.api_base)
    context = load_context()
    config = apply_flow_config(context, args)
    save_context(context)
    project_id = require_project_id(client, context, args.project_id or None, force_new=bool(args.fresh and not args.project_id))
    log_event("stage", {"stage": "start", "target": FLOW_REQUIREMENT, "project_id": project_id, "flow_config": config})
    if args.stage == "smoke":
        run_smoke(client, context, project_id, args.smoke_chapter_count)
        log_event("stage", {"stage": "done", "context": context})
        return
    if args.stage in {"all", "creation"}:
        run_creation(client, context, project_id)
    if args.stage in {"all", "outline"}:
        run_outline(client, context, project_id, chapter_end=args.chapter_end)
    if args.stage in {"all", "draft"}:
        run_draft(client, context, project_id, args.chapter_start, args.chapter_end)
    if args.stage in {"all", "export"}:
        export_novel(client, context, project_id)
    log_event("stage", {"stage": "done", "context": context})


if __name__ == "__main__":
    main()
