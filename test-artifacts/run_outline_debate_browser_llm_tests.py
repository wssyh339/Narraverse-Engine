from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BASE = "http://127.0.0.1:8010/api"
RUN_ID = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
OUT_DIR = Path("test-artifacts") / f"outline_debate_browser_llm_{RUN_ID}"
OUT_DIR.mkdir(parents=True, exist_ok=True)
JSONL = OUT_DIR / "raw_discussion_log.jsonl"
SUMMARY_JSON = OUT_DIR / "summary.json"
DEFAULT_CASE_SCALE = {
    "volume_count": 2,
    "chapters_per_volume": 50,
    "chapter_word_target": 3000,
    "chapter_word_min": 2500,
    "chapter_word_max": 3600,
}
STRICT_THRESHOLDS = {
    "state_change_coverage": 0.95,
    "foreshadowing_use_coverage": 0.9,
    "source_window_coverage": 0.95,
    "window_required_field_coverage": 1.0,
    "window_mini_climax_coverage": 1.0,
    "foreshadowing_window_coverage": 0.8,
    "volume_end_function_coverage": 1.0,
    "crisis_climax_result_distinct_rate": 0.95,
    "duplicate_title_rate": 0.02,
    "decision_coverage": 1.0,
    "score_coverage": 1.0,
    "decision_source_coverage": 1.0,
    "score_source_coverage": 1.0,
}

SCENARIOS = [
    {
        "genre": "东方玄幻升级流",
        "title": "碎星炉",
        "reader": "喜欢升级、奇遇、师门压力和大世界秘密的男频读者",
        "premise": "废脉少年得到会吞噬星火的破炉，却发现每次突破都要牺牲一段记忆。",
        "requirement": "两卷，每卷50章。要求升级代价明确，主线冲突持续续燃，角色/设定候选只在影响主线、伏笔或关系压力时生成。",
    },
    {
        "genre": "都市悬疑探案",
        "title": "第七盏路灯",
        "reader": "喜欢公平线索、反转和人物秘密的悬疑读者",
        "premise": "失眠女刑警发现每起旧案现场都有一盏不该亮起的路灯。",
        "requirement": "两卷，每卷50章。要求线索公平、嫌疑人数量可读、伏笔有回收计划。",
    },
    {
        "genre": "赛博朋克群像",
        "title": "霓虹债主",
        "reader": "喜欢黑色幽默、公司阴谋、身体改造和群像反抗的读者",
        "premise": "底层义体维修师继承了一笔会追杀债务人的人格债券。",
        "requirement": "两卷，每卷50章。重点看组织规则、义体成本、群像角色是否过量。",
    },
    {
        "genre": "古代权谋女强",
        "title": "玉阶雪",
        "reader": "喜欢朝堂博弈、女性成长、情感拉扯和反杀爽点的读者",
        "premise": "被废太子妃回京查父兄旧案，却必须先救下害过她的旧敌。",
        "requirement": "两卷，每卷50章。要求危机不是大场面，而是不可逆政治选择。",
    },
    {
        "genre": "轻科幻殖民星球",
        "title": "潮汐宪章",
        "reader": "喜欢硬设定但需要强剧情推动的科幻读者",
        "premise": "移民星球每隔七天重置海岸线，所有土地契约都因此失效。",
        "requirement": "两卷，每卷50章。重点测试世界规则必须有成本、限制和冲突用途。",
    },
    {
        "genre": "现言娱乐圈成长",
        "title": "热搜之外",
        "reader": "喜欢事业线、情感拉扯、舆论反转和真实成长的女频读者",
        "premise": "过气童星成为危机公关顾问，专门替曾经伤害她的人收拾热搜。",
        "requirement": "两卷，每卷50章。测试类型卖点是否能给出持续追读理由而不是空泛营销。",
    },
    {
        "genre": "诡异规则怪谈",
        "title": "夜班守则",
        "reader": "喜欢规则谜题、恐怖氛围、推理和生存压力的读者",
        "premise": "便利店夜班员工发现每条员工守则都对应一名失踪前任。",
        "requirement": "两卷，每卷50章。规则必须有限制、代价、误导和回收计划。",
    },
    {
        "genre": "西幻冒险公路文",
        "title": "风暴邮差",
        "reader": "喜欢地图探索、伙伴羁绊、奇幻风物和阶段任务的读者",
        "premise": "不能撒谎的邮差被迫递送一封会改写王国边界的信。",
        "requirement": "两卷，每卷50章。测试地图探索节奏，避免地点设定泛滥。",
    },
    {
        "genre": "历史架空商战",
        "title": "盐铁余烬",
        "reader": "喜欢制度博弈、商业扩张、家族压力和时代转折的读者",
        "premise": "亡国盐商之女用一张旧盐引撬动新朝财政命门。",
        "requirement": "两卷，每卷50章。测试制度设定、组织关系和经济规则是否服务冲突。",
    },
    {
        "genre": "校园青春轻悬疑",
        "title": "借光社",
        "reader": "喜欢青春关系、轻推理、社团秘密和温柔成长的读者",
        "premise": "高二转学生加入帮人完成遗憾的社团，却发现委托来自未来。",
        "requirement": "两卷，每卷50章。测试情感推进、轻谜题和角色数量控制。",
    },
]


def write_log(event: dict[str, Any]) -> None:
    event = {"ts": datetime.now(timezone.utc).isoformat(), **event}
    with JSONL.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def request(method: str, path: str, payload: dict[str, Any] | None = None, timeout: int = 360) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        BASE + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    start = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            elapsed = time.time() - start
            return {"ok": True, "status": resp.status, "elapsed": elapsed, "data": json.loads(body) if body else {}}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        elapsed = time.time() - start
        return {"ok": False, "status": e.code, "elapsed": elapsed, "error": body}
    except Exception as e:
        elapsed = time.time() - start
        return {"ok": False, "status": 0, "elapsed": elapsed, "error": repr(e)}


def must(resp: dict[str, Any], label: str) -> dict[str, Any]:
    if not resp.get("ok"):
        raise RuntimeError(f"{label} failed: {resp.get('status')} {resp.get('error')}")
    data = resp["data"]
    if isinstance(data, dict) and data.get("success") is True and isinstance(data.get("data"), dict):
        return data["data"]
    return data


def case_scale(case: dict[str, Any]) -> dict[str, Any]:
    volume_count = int(case.get("volume_count", DEFAULT_CASE_SCALE["volume_count"]))
    chapters_per_volume = int(case.get("chapters_per_volume", DEFAULT_CASE_SCALE["chapters_per_volume"]))
    chapter_word_target = int(case.get("chapter_word_target", DEFAULT_CASE_SCALE["chapter_word_target"]))
    chapter_word_min = int(case.get("chapter_word_min", DEFAULT_CASE_SCALE["chapter_word_min"]))
    chapter_word_max = int(case.get("chapter_word_max", DEFAULT_CASE_SCALE["chapter_word_max"]))
    planned_chapter_count = volume_count * chapters_per_volume
    chapter_window_size = int(case.get("chapter_window_size", max(1, round(chapters_per_volume / 5))))
    chapter_ranges = build_chapter_ranges(volume_count, chapters_per_volume)
    return {
        "volume_count": volume_count,
        "chapters_per_volume": chapters_per_volume,
        "planned_chapter_count": planned_chapter_count,
        "chapter_word_target": chapter_word_target,
        "chapter_word_min": chapter_word_min,
        "chapter_word_max": chapter_word_max,
        "target_words": int(case.get("target_words", planned_chapter_count * chapter_word_target)),
        "chapter_window_size": chapter_window_size,
        "expected_chapter_window_count": expected_window_count(chapter_ranges, chapter_window_size),
        "chapter_ranges": chapter_ranges,
        "chapters_by_volume": {volume_no: chapters_per_volume for volume_no in range(1, volume_count + 1)},
    }


def build_chapter_ranges(volume_count: int, chapters_per_volume: int) -> list[dict[str, int]]:
    ranges = []
    start = 1
    for volume_no in range(1, volume_count + 1):
        end = start + chapters_per_volume - 1
        ranges.append({"volume_no": volume_no, "start_chapter_no": start, "end_chapter_no": end})
        start = end + 1
    return ranges


def expected_window_count(chapter_ranges: list[dict[str, int]], chapter_window_size: int) -> int:
    window_size = max(1, chapter_window_size)
    count = 0
    for chapter_range in chapter_ranges:
        length = int(chapter_range["end_chapter_no"]) - int(chapter_range["start_chapter_no"]) + 1
        count += (length + window_size - 1) // window_size
    return count


def summarize_phase(resp: dict[str, Any]) -> dict[str, Any]:
    phase_run = resp.get("phase_run", {}) if isinstance(resp, dict) else {}
    result = phase_run.get("result", {}) if isinstance(phase_run, dict) else {}
    turns = phase_run.get("turns", []) if isinstance(phase_run, dict) else []
    chapters = result.get("chapter_outlines") if isinstance(result, dict) else []
    volumes = result.get("volume_outlines") if isinstance(result, dict) else []
    windows = result.get("chapter_windows") if isinstance(result, dict) else []
    quality_metrics = result.get("quality_metrics") if isinstance(result, dict) and isinstance(result.get("quality_metrics"), dict) else {}
    llm = []
    for turn in turns:
        if not isinstance(turn, dict):
            continue
        meta = turn.get("_llm") if isinstance(turn.get("_llm"), dict) else {}
        llm.append({
            "agent": turn.get("agent_name"),
            "role": turn.get("role"),
            "decision": turn.get("decision"),
            "decision_source": turn.get("decision_source"),
            "score_keys": sorted((turn.get("scores") or {}).keys()) if isinstance(turn.get("scores"), dict) else [],
            "score_source": turn.get("score_source"),
            "blocking_count": len(turn.get("blocking_items") or []),
            "provider": meta.get("provider"),
            "model": meta.get("model"),
            "used_remote_model": meta.get("used_remote_model"),
            "error": meta.get("error"),
        })
    by_volume = {}
    if isinstance(chapters, list):
        for ch in chapters:
            if isinstance(ch, dict):
                v = int(ch.get("volume_no") or 0)
                by_volume[v] = by_volume.get(v, 0) + 1
    return {
        "status": phase_run.get("status"),
        "turn_count": len(turns),
        "agents": [t.get("agent_name") for t in turns if isinstance(t, dict)],
        "llm": llm,
        "chapter_count": len(chapters) if isinstance(chapters, list) else 0,
        "volume_count": len(volumes) if isinstance(volumes, list) else 0,
        "chapter_window_count": len(windows) if isinstance(windows, list) else 0,
        "chapters_by_volume": by_volume,
        "candidate_policy": phase_run.get("candidate_policy"),
        "validation_report": phase_run.get("validation_report"),
        "quality_metrics": quality_metrics,
        "blocking_items": result.get("blocking_items") if isinstance(result, dict) else [],
        "sample_windows": (windows[:2] + windows[-2:]) if isinstance(windows, list) and len(windows) >= 4 else windows,
        "sample_chapters": (chapters[:2] + chapters[-2:]) if isinstance(chapters, list) and len(chapters) >= 4 else chapters,
    }


def analyze(summary: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    scale = summary.get("scale", {})
    chapters = summary.get("chapters", {})
    volumes = summary.get("volumes", {})
    quality = chapters.get("quality_metrics") if isinstance(chapters.get("quality_metrics"), dict) else {}
    expected_volume_count = int(scale.get("volume_count") or 0)
    expected_chapter_count = int(scale.get("planned_chapter_count") or 0)
    expected_by_volume = {int(k): int(v) for k, v in (scale.get("chapters_by_volume") or {}).items()}
    if volumes.get("volume_count") != expected_volume_count:
        issues.append(f"卷纲数量异常：{volumes.get('volume_count')}，期望{expected_volume_count}")
    if chapters.get("chapter_count") != expected_chapter_count:
        issues.append(f"章纲数量异常：{chapters.get('chapter_count')}，期望{expected_chapter_count}")
    if {int(k): int(v) for k, v in chapters.get("chapters_by_volume", {}).items()} != expected_by_volume:
        issues.append(f"分卷章数异常：{chapters.get('chapters_by_volume')}，期望{expected_by_volume}")
    if chapters.get("chapter_window_count") != scale.get("expected_chapter_window_count"):
        issues.append(f"章节窗口数量异常：{chapters.get('chapter_window_count')}，期望{scale.get('expected_chapter_window_count')}")
    if quality.get("status") == "failed":
        issues.append(f"服务端质量门失败：{quality.get('blocking_items')}")
    if quality.get("template_blocking_count", 0) > 0:
        issues.append(f"存在模板占位：{quality.get('template_hits')}")
    for key in (
        "state_change_coverage",
        "foreshadowing_use_coverage",
        "source_window_coverage",
        "window_required_field_coverage",
        "window_mini_climax_coverage",
        "foreshadowing_window_coverage",
        "volume_end_function_coverage",
        "crisis_climax_result_distinct_rate",
    ):
        value = float(quality.get(key, 0))
        if value < STRICT_THRESHOLDS[key]:
            issues.append(f"{key} 不达标：{value}，阈值 {STRICT_THRESHOLDS[key]}")
    if quality.get("final_chapter_turn_present") is not True:
        issues.append("最终章节缺少卷末/阶段收束或下一阶段钩子功能")
    duplicate_rate = float(quality.get("duplicate_title_count", 0)) / max(1, expected_chapter_count)
    if duplicate_rate > STRICT_THRESHOLDS["duplicate_title_rate"]:
        issues.append(f"标题重复率不达标：{duplicate_rate:.4f}，阈值 {STRICT_THRESHOLDS['duplicate_title_rate']}")
    all_llm = []
    for phase in ["book", "volumes", "chapters"]:
        all_llm.extend(summary.get(phase, {}).get("llm", []))
    if not all_llm:
        issues.append("未记录到 LLM 元信息")
    else:
        not_remote = [m for m in all_llm if m.get("used_remote_model") is not True or m.get("error")]
        if not_remote:
            issues.append(f"存在非远程或错误 LLM 调用：{not_remote[:3]}")
    decision_coverage = sum(1 for m in all_llm if m.get("decision")) / max(1, len(all_llm))
    score_coverage = sum(1 for m in all_llm if m.get("score_keys")) / max(1, len(all_llm))
    decision_source_coverage = sum(1 for m in all_llm if m.get("decision_source") in {"model", "service_default", "local_preview"}) / max(1, len(all_llm))
    score_source_coverage = sum(1 for m in all_llm if m.get("score_source") in {"model", "service_default", "local_preview"}) / max(1, len(all_llm))
    if decision_coverage < STRICT_THRESHOLDS["decision_coverage"]:
        issues.append(f"Agent decision 覆盖率不达标：{decision_coverage:.4f}")
    if score_coverage < STRICT_THRESHOLDS["score_coverage"]:
        issues.append(f"Agent scores 覆盖率不达标：{score_coverage:.4f}")
    if decision_source_coverage < STRICT_THRESHOLDS["decision_source_coverage"]:
        issues.append(f"Agent decision_source 覆盖率不达标：{decision_source_coverage:.4f}")
    if score_source_coverage < STRICT_THRESHOLDS["score_source_coverage"]:
        issues.append(f"Agent score_source 覆盖率不达标：{score_source_coverage:.4f}")
    if not issues:
        issues.append(f"通过：远程 LLM、{expected_volume_count}卷/{expected_chapter_count}章、动态窗口和严格质量指标均满足本轮检查。")
    return issues


def main() -> None:
    run_summary = {"run_id": RUN_ID, "base": BASE, "out_dir": str(OUT_DIR), "cases": []}
    for idx, case in enumerate(SCENARIOS, 1):
        case_id = f"browser-llm-{RUN_ID}-{idx:02d}"
        title = f"浏览器LLM压测-{idx:02d}-{case['title']}-{RUN_ID}"
        scale = case_scale(case)
        write_log({"type": "case_start", "index": idx, "title": title, "genre": case["genre"]})
        summary = {"index": idx, "case_id": case_id, "title": title, "genre": case["genre"], "premise": case["premise"], "requirement": case["requirement"], "scale": scale, "ok": False, "accepted": False, "error": ""}
        try:
            project = must(request("POST", "/projects", {
                "title": title,
                "genre": case["genre"],
                "target_reader": case["reader"],
                "premise": case["premise"],
                "style_guide": "中文长篇网文节奏；重视因果、爽点、代价、伏笔和正典连续性。",
                "planned_chapter_count": scale["planned_chapter_count"],
                "planned_volume_count": scale["volume_count"],
                "chapters_per_volume": scale["chapters_per_volume"],
                "chapter_word_target": scale["chapter_word_target"],
                "chapter_word_min": scale["chapter_word_min"],
                "chapter_word_max": scale["chapter_word_max"],
                "target_words": scale["target_words"],
                "initial_idea": case["requirement"],
            }, timeout=60), "create_project")
            project_obj = project.get("project") if isinstance(project.get("project"), dict) else project
            project_id = project_obj["id"]
            summary["project_id"] = project_id
            must(request("PUT", f"/projects/{project_id}/story-bible", {
                "world_setting": case["premise"],
                "main_conflict": case["premise"],
                "themes": ["选择", "代价", "成长", "真相"],
                "style_guide": "要求每个关键节点说明为什么现在发生、为什么由此人经历、为什么不能逃避、为什么读者在意。",
                "narrative_pov": "third_person_limited",
                "forbidden_elements": ["无来源覆盖正典", "为反转而反转", "只有事件没有状态改变"],
                "continuity_rules": ["危机是不可逆选择", "高潮是执行选择", "结果是承担后果", "重要角色和设定必须可追溯"],
            }, timeout=60), "story_bible")
            session = must(request("POST", f"/projects/{project_id}/outline/debate/sessions", {"brief": case["requirement"], "model": "deepseek-v4-flash"}, timeout=60), "create_session")
            session_id = session["session"]["id"]
            summary["session_id"] = session_id
            common = {
                "requirement": case["requirement"] + f" 必须输出{scale['volume_count']}卷，每卷{scale['chapters_per_volume']}章；local_preview=false；必须使用远程模型；章节窗口大小由 scale_plan 动态推导。",
                "use_topology_inference": True,
                "target_words": scale["target_words"],
                "volume_count": scale["volume_count"],
                "chapters_per_volume": scale["chapters_per_volume"],
                "chapter_word_target": scale["chapter_word_target"],
                "chapter_word_min": scale["chapter_word_min"],
                "chapter_word_max": scale["chapter_word_max"],
                "scale_plan": {
                    "volume_count": scale["volume_count"],
                    "chapters_per_volume": scale["chapters_per_volume"],
                    "chapter_count": scale["planned_chapter_count"],
                    "chapter_window_size": scale["chapter_window_size"],
                },
                "local_preview": False,
                "max_agent_turns": 6,
                "model": "deepseek-v4-flash",
            }
            book = must(request("POST", f"/projects/{project_id}/outline/debate/sessions/{session_id}/book/run", common, timeout=420), "book_run")
            (OUT_DIR / f"case_{idx:02d}_book.json").write_text(json.dumps(book, ensure_ascii=False, indent=2), encoding="utf-8")
            write_log({"type": "phase", "case": idx, "phase": "book", "summary": summarize_phase(book)})
            must(request("POST", f"/projects/{project_id}/outline/debate/sessions/{session_id}/book/confirm", {"notes": "真实浏览器+LLM压测自动确认总纲。"}, timeout=240), "book_confirm")
            volumes = must(request("POST", f"/projects/{project_id}/outline/debate/sessions/{session_id}/volumes/run", common, timeout=420), "volumes_run")
            (OUT_DIR / f"case_{idx:02d}_volumes.json").write_text(json.dumps(volumes, ensure_ascii=False, indent=2), encoding="utf-8")
            write_log({"type": "phase", "case": idx, "phase": "volumes", "summary": summarize_phase(volumes)})
            must(request("POST", f"/projects/{project_id}/outline/debate/sessions/{session_id}/volumes/confirm", {"notes": "真实浏览器+LLM压测自动确认卷纲。"}, timeout=240), "volumes_confirm")
            chapter_payload = dict(common)
            chapter_payload["chapter_ranges"] = scale["chapter_ranges"]
            chapters = must(request("POST", f"/projects/{project_id}/outline/debate/sessions/{session_id}/chapters/run", chapter_payload, timeout=600), "chapters_run")
            (OUT_DIR / f"case_{idx:02d}_chapters.json").write_text(json.dumps(chapters, ensure_ascii=False, indent=2), encoding="utf-8")
            write_log({"type": "phase", "case": idx, "phase": "chapters", "summary": summarize_phase(chapters)})
            summary["book"] = summarize_phase(book)
            summary["volumes"] = summarize_phase(volumes)
            summary["chapters"] = summarize_phase(chapters)
            summary["issues"] = analyze(summary)
            summary["ok"] = True
            summary["accepted"] = len(summary["issues"]) == 1 and str(summary["issues"][0]).startswith("通过：")
            write_log({"type": "case_done", "case": idx, "issues": summary["issues"]})
        except Exception as e:
            summary["error"] = repr(e)
            summary["issues"] = [f"测试中断：{repr(e)}"]
            write_log({"type": "case_error", "case": idx, "error": repr(e)})
        run_summary["cases"].append(summary)
        SUMMARY_JSON.write_text(json.dumps(run_summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"case": idx, "ok": summary["ok"], "accepted": summary.get("accepted"), "issues": summary.get("issues"), "out_dir": str(OUT_DIR)}, ensure_ascii=False), flush=True)
    print(str(OUT_DIR), flush=True)

if __name__ == "__main__":
    main()
