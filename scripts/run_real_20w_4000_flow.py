from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT / "logs" / "real_20w_4000_flow"
CONTEXT_PATH = LOG_DIR / "run_context.json"
JSONL_PATH = LOG_DIR / "flow.jsonl"
MARKDOWN_PATH = LOG_DIR / "flow.md"
NOVEL_PATH = LOG_DIR / "final_novel.md"

DEFAULT_BASIC_INFO: dict[str, Any] = {
    "channel": "男频",
    "genre": "都市异能悬疑",
    "subgenres": ["近未来都市", "规则悬疑", "制度反抗"],
    "tags": ["记忆交易", "身份注销", "规则漏洞", "追债", "推理升级", "制度压迫"],
    "manual_tags": ["记忆抵押", "城市账本", "追债审判", "反垄断规则"],
    "target_reader": "喜欢都市异能、悬疑追查、规则漏洞爽点和长篇成长线的读者",
    "volume_count": 5,
    "chapter_count": 50,
    "planned_chapter_count": 50,
    "chapters_per_volume": 10,
    "chapter_word_target": 4000,
    "chapter_word_min": 4000,
    "chapter_word_max": 4000,
    "style": "冷峻、紧张、强钩子、规则感，少解释，多让规则在行动和代价中显形。",
    "initial_idea": (
        "现代近未来城市中，记忆可以被抵押、交易和追债。主角是被注销身份的底层账本修复师，"
        "意外发现整座城市的晋升制度靠篡改普通人的失败记忆运行。他必须在追债、逃亡和审判之间，"
        "重建被抹掉的真相。"
    ),
}

FLOW_REQUIREMENT = (
    "目标规模：20万字，5卷，50章，每章4000字。每卷10章。"
    "大纲讨论必须按总纲、逐卷卷纲、逐章章纲推进；每确认一卷/一章都更新正典。"
    "每章必须区分危机、高潮、结果；伏笔、角色、设定新增需要在确认后入正式正典。"
    "题材方向：近未来都市、记忆交易、制度压迫、身份注销、规则漏洞爽点、悬疑追查。"
)


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
        MARKDOWN_PATH.write_text("# 20万字真实流程日志\n\n", encoding="utf-8")


def log_event(kind: str, payload: dict[str, Any]) -> None:
    ensure_logs()
    record = {"ts": now_iso(), "kind": kind, **payload}
    with JSONL_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    if kind in {"stage", "problem", "artifact", "job"}:
        with MARKDOWN_PATH.open("a", encoding="utf-8") as handle:
            handle.write(f"## {record['ts']} {kind}\n\n")
            handle.write("```json\n")
            handle.write(json.dumps(payload, ensure_ascii=False, indent=2))
            handle.write("\n```\n\n")


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


def require_project_id(client: FlowClient, context: dict[str, Any], project_id: str | None) -> str:
    if project_id:
        context["project_id"] = project_id
        save_context(context)
        return project_id
    if context.get("project_id"):
        return str(context["project_id"])
    projects = client.request("GET", "/projects").get("projects", [])
    if len(projects) == 1:
        context["project_id"] = projects[0]["id"]
        save_context(context)
        return str(context["project_id"])
    project_payload = {
        "title": "20万字真实流程草稿",
        "genre": "都市异能悬疑",
        "target_reader": DEFAULT_BASIC_INFO["target_reader"],
        "premise": DEFAULT_BASIC_INFO["initial_idea"],
        "style_guide": DEFAULT_BASIC_INFO["style"],
        "language": "zh-CN",
        "planned_chapter_count": 50,
        "planned_volume_count": 5,
        "chapters_per_volume": 10,
        "chapter_word_target": 4000,
        "chapter_word_min": 4000,
        "chapter_word_max": 4000,
        "target_words": 200000,
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
        "target_words": 200000,
        "volume_count": 5,
        "chapters_per_volume": 10,
        "chapter_word_target": 4000,
        "chapter_word_min": 4000,
        "chapter_word_max": 4000,
        "scale_plan": {
            "target_words": 200000,
            "volume_count": 5,
            "chapter_count": 50,
            "chapters_per_volume": 10,
            "chapter_word_target": 4000,
            "chapter_word_min": 4000,
            "chapter_word_max": 4000,
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


def run_outline(client: FlowClient, context: dict[str, Any], project_id: str) -> None:
    if context.get("outline_committed"):
        log_event("stage", {"stage": "outline", "status": "skipped", "reason": "already committed"})
        return
    log_event("stage", {"stage": "outline", "status": "started", "project_id": project_id})
    session_id = context.get("outline_session_id")
    if not session_id:
        data = client.request(
            "POST",
            f"/projects/{project_id}/outline/debate/sessions",
            {"idempotency_key": f"real-20w-outline:{project_id}", "brief": FLOW_REQUIREMENT},
        )
        session_id = data["session"]["id"]
        context["outline_session_id"] = session_id
        save_context(context)

    if not context.get("book_confirmed"):
        log_event("stage", {"stage": "outline_book", "status": "running", "max_agent_turns": 6})
        client.request("POST", f"/projects/{project_id}/outline/debate/sessions/{session_id}/book/run", outline_payload({"max_agent_turns": 6}))
        client.request(
            "POST",
            f"/projects/{project_id}/outline/debate/sessions/{session_id}/book/confirm",
            {"notes": "确认总纲，并写入故事圣经与分卷壳。"},
        )
        context["book_confirmed"] = True
        save_context(context)

    confirmed_volumes = set(int(item) for item in context.get("confirmed_volumes", []))
    for volume_no in range(1, 6):
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
        context["confirmed_volumes"] = sorted(confirmed_volumes)
        save_context(context)

    if not context.get("chapters_confirmed"):
        for volume_no in range(1, 6):
            volume_start = (volume_no - 1) * 10 + 1
            volume_end = volume_no * 10
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
        if len([chapter_no for chapter_no in range(1, 51) if chapter_no in confirmed]) < 50:
            raise RuntimeError(f"章纲确认不完整：已确认 {sorted(confirmed)}")
        context["chapters_confirmed"] = True
        save_context(context)

    data = client.request(
        "POST",
        f"/projects/{project_id}/outline/debate/sessions/{session_id}/commit",
        {"overwrite_existing_chapters": True, "notes": "确认 20万字 50章完整大纲并写入正式章节。"},
    )
    context["outline_committed"] = True
    context["outline_commit"] = {
        "volume_count": len(data.get("book_commit", {}).get("volumes", [])),
        "chapter_count": len(data.get("chapter_commit", {}).get("chapters", [])),
    }
    save_context(context)
    log_event("stage", {"stage": "outline", "status": "committed", "summary": context["outline_commit"]})


def run_draft(client: FlowClient, context: dict[str, Any], project_id: str) -> None:
    if context.get("draft_committed"):
        log_event("stage", {"stage": "draft", "status": "skipped", "reason": "already completed"})
        return
    log_event("stage", {"stage": "draft", "status": "started", "project_id": project_id})
    existing_batch_job_id = context.get("batch_job_id")
    if existing_batch_job_id:
        existing_job = client.request("GET", f"/jobs/{existing_batch_job_id}", timeout=120)["job"]
        if existing_job.get("status") in {"cancelled", "failed"}:
            log_event("stage", {"stage": "draft", "status": "discard_old_batch_job", "job_id": existing_batch_job_id, "old_status": existing_job.get("status")})
            context.pop("batch_job_id", None)
            save_context(context)
    if not context.get("batch_job_id"):
        data = client.request(
            "POST",
            "/write/batch-generate",
            {
                "project_id": project_id,
                "chapter_start": 1,
                "chapter_end": 50,
                "generation_options": {"fast_draft": True, "purpose": "20w_real_browser_flow"},
            },
            timeout=120,
        )
        context["batch_job_id"] = data["job"]["id"]
        save_context(context)
    job = poll_job(client, context["batch_job_id"], timeout_seconds=43200, interval=20)
    if job.get("status") != "succeeded":
        progress = job.get("progress") if isinstance(job.get("progress"), dict) else {}
        result = job.get("result") if isinstance(job.get("result"), dict) else {}
        summary = {
            "id": job.get("id"),
            "status": job.get("status"),
            "current_step": progress.get("current_step"),
            "completed_chapters": progress.get("completed_chapters"),
            "total_chapters": progress.get("total_chapters"),
            "failed_chapters": result.get("failed_chapters") or [],
            "last_completed_chapter_no": result.get("last_completed_chapter_no"),
        }
        raise RuntimeError(f"批量正文生成失败：{summary}")
    context["draft_committed"] = True
    context["batch_job"] = job
    save_context(context)
    log_event("stage", {"stage": "draft", "status": "completed", "job_id": context["batch_job_id"]})


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
        word_count = int(chapter.get("word_count") or len(text))
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-base", default="http://127.0.0.1:8015/api")
    parser.add_argument("--project-id", default="")
    parser.add_argument("--stage", choices=["all", "creation", "outline", "draft", "export"], default="all")
    args = parser.parse_args()
    ensure_logs()
    client = FlowClient(args.api_base)
    context = load_context()
    project_id = require_project_id(client, context, args.project_id or None)
    log_event("stage", {"stage": "start", "target": "20万字 / 50章 / 每章4000字", "project_id": project_id})
    if args.stage in {"all", "creation"}:
        run_creation(client, context, project_id)
    if args.stage in {"all", "outline"}:
        run_outline(client, context, project_id)
    if args.stage in {"all", "draft"}:
        run_draft(client, context, project_id)
    if args.stage in {"all", "export"}:
        export_novel(client, context, project_id)
    log_event("stage", {"stage": "done", "context": context})


if __name__ == "__main__":
    main()
