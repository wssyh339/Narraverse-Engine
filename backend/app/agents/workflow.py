from __future__ import annotations

from typing import Any, Callable

from langgraph.graph import END, START, StateGraph

from app.agents.contracts import NovelStudioState
from app.agents.llm_io import call_agent_json
from app.agents.prompts import AGENT_SPECS_BY_NAME
from app.services.llm_client import llm_client


def _state(data: dict[str, Any]) -> NovelStudioState:
    return NovelStudioState.model_validate(data)


def _update(data: dict[str, Any], **values: Any) -> dict[str, Any]:
    current = _state(data).model_dump()
    current.update(values)
    return current


def _title_slug(value: str) -> str:
    return value.strip() or "未命名"


def _context_items(state: NovelStudioState, key: str, fallback: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items = state.canon_context.get(key) if isinstance(state.canon_context, dict) else None
    return items if isinstance(items, list) and items else fallback


def _name_list(items: list[dict[str, Any]], primary_key: str = "name", limit: int = 4) -> str:
    names = [str(item.get(primary_key) or item.get("title") or "").strip() for item in items[:limit]]
    names = [name for name in names if name]
    return "、".join(names) if names else "暂无"


def _agent_context(state: NovelStudioState, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    context = {
        "project": {
            "id": state.project_id,
            "title": state.title,
            "genre": state.genre,
            "target_reader": state.target_reader,
            "premise": state.premise,
            "style_guide": state.style_guide,
            "target_words": state.target_words,
            "target_chapters": state.target_chapters,
            "current_volume": state.current_volume,
            "current_chapter": state.current_chapter,
        },
        "story_bible": state.story_bible,
        "characters": state.characters,
        "world_facts": state.world_facts,
        "story_entities": state.story_entities,
        "canon_context": state.canon_context,
        "current_chapter_outline": state.current_chapter_outline,
        "completed_chapters": state.completed_chapters[-5:],
        "previous_agent_outputs": {
            "plot_draft": state.plot_draft,
            "dialogue_draft": state.dialogue_draft,
            "environment_draft": state.environment_draft,
            "integrated_draft": state.integrated_draft,
            "review_notes": state.review_notes,
            "fact_check_report": state.fact_check_report,
            "quality_gate": state.quality_gate,
            "chapter_summary": state.chapter_summary,
        },
    }
    if extra:
        context.update(extra)
    return context


def _prompt_for(state: NovelStudioState, agent_name: str) -> tuple[str, str]:
    spec = AGENT_SPECS_BY_NAME[agent_name]
    return spec.role, state.agent_prompt_configs.get(agent_name) or spec.prompt


def _agent_payload(
    state: NovelStudioState,
    agent_name: str,
    task: str,
    fallback: dict[str, Any],
    extra: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    role, prompt = _prompt_for(state, agent_name)
    return call_agent_json(
        llm_client=llm_client,
        agent_name=agent_name,
        role=role,
        system_prompt=prompt,
        task=task,
        context=_agent_context(state, extra),
        fallback=fallback,
        model=state.requested_model,
    )


def _llm_results(state: NovelStudioState, agent_name: str, meta: dict[str, Any]) -> dict[str, dict[str, Any]]:
    results = dict(state.agent_llm_results)
    results[agent_name] = meta
    return results


def build_context_node(data: dict[str, Any]) -> dict[str, Any]:
    state = _state(data)
    context = dict(state.canon_context or {})
    context.setdefault("project", {"id": state.project_id, "title": state.title, "genre": state.genre})
    context.setdefault("story_bible", state.story_bible)
    context.setdefault("characters", state.characters)
    context.setdefault("world_facts", state.world_facts)
    context.setdefault("story_entities", state.story_entities)
    context.setdefault("previous_summaries", state.completed_chapters[-5:])
    context.setdefault("unresolved_continuity_issues", state.continuity_issues)
    return _update(data, current_agent="canon_context", progress=0.38, canon_context=context)


def chief_architect_node(data: dict[str, Any]) -> dict[str, Any]:
    state = _state(data)
    title = _title_slug(state.title)
    world_setting = state.world_setting or f"围绕「{state.premise}」建立的{state.genre}长篇世界，核心读者是{state.target_reader}。"
    story_bible = {
        "world_setting": world_setting,
        "main_conflict": f"{title}的主线冲突来自个人目标、外部秩序和隐藏真相的三重碰撞。",
        "themes": ["身份选择", "代价", "长期承诺"],
        "narrative_pov": "third_person_limited",
        "style_guide": state.style_guide,
        "forbidden_elements": ["无铺垫反转", "机械降神", "角色动机突变"],
        "continuity_rules": ["角色认知不得超过其经历与被告知的信息。", "新增设定必须能追溯来源。"],
    }
    characters = state.characters or [
        {
            "name": "待定主角",
            "role_type": "protagonist",
            "importance_level": "core",
            "importance_score": 95,
            "summary": f"被「{state.premise}」推入核心冲突的人物。",
            "goals": ["查清真相", "完成自我选择"],
            "character_arc": "从被动承受转为主动承担。",
        },
        {
            "name": "核心对手",
            "role_type": "antagonist",
            "importance_level": "major",
            "importance_score": 82,
            "summary": "以相反价值观推动主线压力的人物。",
            "goals": ["维护自身秩序", "阻止主角触及真相"],
            "character_arc": "逐渐暴露其合理性与代价。",
        },
    ]
    outline = state.outline or [
        {"volume_no": 1, "title": "第一卷：引火", "core_event": "主角进入冲突现场，发现第一条关键线索。"},
        {"volume_no": 2, "title": "第二卷：裂变", "core_event": "同盟关系破裂，真相呈现多重解释。"},
        {"volume_no": 3, "title": "第三卷：回收", "core_event": "伏笔集中回收，主角做出不可逆选择。"},
    ]
    payload, meta = _agent_payload(
        state,
        "chief_architect",
        "生成或更新项目故事圣经、核心角色与分卷结构。必须输出 story_bible、characters、outline。",
        {"story_bible": story_bible, "characters": characters, "outline": outline},
    )
    llm_story_bible = payload.get("story_bible", story_bible)
    if not isinstance(llm_story_bible, dict):
        llm_story_bible = story_bible
    llm_characters = payload.get("characters", characters)
    if not isinstance(llm_characters, list):
        llm_characters = characters
    llm_outline = payload.get("outline", outline)
    if not isinstance(llm_outline, list):
        llm_outline = outline
    return _update(
        data,
        current_agent="chief_architect",
        progress=0.2,
        world_setting=llm_story_bible.get("world_setting", world_setting),
        story_bible=llm_story_bible,
        characters=llm_characters,
        outline=llm_outline,
        agent_llm_results=_llm_results(state, "chief_architect", meta),
    )


def chapter_planner_node(data: dict[str, Any]) -> dict[str, Any]:
    state = _state(data)
    start = max(1, state.current_chapter)
    count = max(1, min(20, state.target_chapters or 3))
    chapters = []
    for index in range(count):
        chapter_no = start + index
        chapters.append(
            {
                "chapter_no": chapter_no,
                "volume_no": state.current_volume,
                "title": f"第{chapter_no}章：{state.genre}转折 {chapter_no}",
                "outline": f"承接《{state.title}》主线，推进第{chapter_no}个关键事件。",
                "pov_character": state.characters[0]["name"] if state.characters else "待定主角",
                "core_event": "发现新线索并付出代价。",
                "conflict": "个人目标与外部压力正面碰撞。",
                "turn_point": "章节末尾出现改变行动方向的信息。",
                "emotional_beats": ["压迫", "试探", "失衡", "决断"],
                "plot_purpose": "推进主线并暴露一个角色选择。",
                "cliffhanger": "一个旧设定被重新解释。",
                "word_target": 3000,
            }
        )
    payload, meta = _agent_payload(
        state,
        "chapter_planner",
        "生成章节规划。必须输出 chapters 数组，每章包含标题、POV、核心事件、冲突、转折、情绪节奏、剧情功能、结尾钩子和目标字数。",
        {"chapters": chapters},
        {"chapter_count": count, "start_chapter_no": start},
    )
    planned_chapters = payload.get("chapters", chapters)
    if not isinstance(planned_chapters, list) or not planned_chapters:
        planned_chapters = chapters
    return _update(
        data,
        current_agent="chapter_planner",
        progress=0.35,
        outline=state.outline,
        current_chapter_outline=planned_chapters[0],
        completed_chapters=planned_chapters,
        agent_llm_results=_llm_results(state, "chapter_planner", meta),
    )


def plot_narrator_node(data: dict[str, Any]) -> dict[str, Any]:
    state = _state(data)
    chapter = state.current_chapter_outline
    characters = _context_items(state, "characters", state.characters)
    facts = _context_items(state, "world_facts", state.world_facts)
    entities = _context_items(state, "story_entities", state.story_entities)
    lead = _name_list(characters)
    fact_names = _name_list(facts, "title")
    entity_names = _name_list(entities)
    text = (
        f"【情节主干】{chapter.get('title', '本章')}围绕“{chapter.get('core_event', '关键事件')}”展开。"
        f"本章优先读取设定上下文：核心角色={lead}；高重要度世界观={fact_names}；相关实体={entity_names}。"
        f"{lead.split('、')[0] if lead != '暂无' else '主角'}在压力下推进目标，却被“{chapter.get('conflict', '冲突')}”迫使改变策略。"
        "本段保留行动链、信息差和章节代价，供后续 Agent 加入对话与描写。"
    )
    payload, meta = _agent_payload(
        state,
        "plot_narrator",
        "基于 canon_context 与章纲生成章节情节主干，不写完整终稿，只输出 plot_draft。",
        {"plot_draft": text},
    )
    return _update(data, current_agent="plot_narrator", progress=0.45, plot_draft=str(payload.get("plot_draft", text)), agent_llm_results=_llm_results(state, "plot_narrator", meta))


def dialogue_writer_node(data: dict[str, Any]) -> dict[str, Any]:
    state = _state(data)
    characters = _context_items(state, "characters", state.characters)
    protagonist = characters[0]["name"] if characters else "主角"
    partner = characters[1]["name"] if len(characters) > 1 else "对方"
    text = (
        f"【对话层】“你早就知道答案？”{protagonist}问。\n"
        f"“我只知道，答案会让你失去现在还能相信的东西。”{partner}避开视线。\n"
        f"{protagonist}沉默片刻，意识到这不是警告，而是一场交换的开端。"
    )
    payload, meta = _agent_payload(
        state,
        "dialogue_writer",
        "基于情节主干、角色卡和关系网生成对话层，只输出 dialogue_draft。",
        {"dialogue_draft": text},
    )
    return _update(data, current_agent="dialogue_writer", progress=0.55, dialogue_draft=str(payload.get("dialogue_draft", text)), agent_llm_results=_llm_results(state, "dialogue_writer", meta))


def environment_writer_node(data: dict[str, Any]) -> dict[str, Any]:
    state = _state(data)
    entities = _context_items(state, "story_entities", state.story_entities)
    anchor = _name_list(entities, "name", 2)
    text = (
        f"【环境层】场景围绕相关实体“{anchor}”展开，光线被压低，远处声响像潮水一样反复逼近。"
        "空气里残留冷金属与雨水的气味，使每一次停顿都显得更长。"
        f"这种氛围服务于《{state.title}》当前章节的怀疑、逼近和选择。"
    )
    payload, meta = _agent_payload(
        state,
        "environment_writer",
        "基于情节与对话生成环境、氛围和感官描写层，只输出 environment_draft。",
        {"environment_draft": text},
    )
    return _update(data, current_agent="environment_writer", progress=0.63, environment_draft=str(payload.get("environment_draft", text)), agent_llm_results=_llm_results(state, "environment_writer", meta))


def reviewer_node(data: dict[str, Any]) -> dict[str, Any]:
    state = _state(data)
    notes = [
        {"severity": "warning", "category": "motivation", "message": "关键选择需要补足个人动机。", "suggestion": "加入一句角色为何不能后退的理由。"},
        {"severity": "info", "category": "continuity", "message": "新增线索应写入设定集。", "suggestion": "交给设定整理 Agent 标记来源章节。"},
    ]
    if not state.canon_context.get("characters"):
        notes.insert(0, {"severity": "blocking", "category": "canon_context", "message": "缺少角色卡上下文。", "suggestion": "先创建或生成至少一张角色卡。"})
    payload, meta = _agent_payload(
        state,
        "reviewer",
        "审核当前章节草稿的逻辑、人物、节奏、伏笔和文笔问题。必须输出 review_notes 数组。",
        {"review_notes": notes},
    )
    review_notes = payload.get("review_notes", notes)
    if not isinstance(review_notes, list):
        review_notes = notes
    return _update(data, current_agent="reviewer", progress=0.72, review_notes=review_notes, agent_llm_results=_llm_results(state, "reviewer", meta))


def integrator_node(data: dict[str, Any]) -> dict[str, Any]:
    state = _state(data)
    title = state.current_chapter_outline.get("title", f"第{state.current_chapter}章")
    integrated = (
        f"# {title}\n\n"
        f"{state.plot_draft}\n\n{state.dialogue_draft}\n\n{state.environment_draft}\n\n"
        "【整合草稿】本章以选择和代价收束，并在结尾留下后续悬念。"
    )
    summary = f"{title}推进了核心事件，主角在压力下获得新线索，同时付出关系或认知上的代价。"
    payload, meta = _agent_payload(
        state,
        "integrator",
        "整合情节、对话和环境层，生成 integrated_draft 与 chapter_summary。",
        {"integrated_draft": integrated, "chapter_summary": summary},
    )
    return _update(
        data,
        current_agent="integrator",
        progress=0.68,
        integrated_draft=str(payload.get("integrated_draft", integrated)),
        chapter_summary=str(payload.get("chapter_summary", summary)),
        agent_llm_results=_llm_results(state, "integrator", meta),
    )


def fact_checker_node(data: dict[str, Any]) -> dict[str, Any]:
    state = _state(data)
    report = {
        "status": "passed_with_notes",
        "categories": ["history", "science", "technology", "geography", "culture"],
        "issues": [
            {
                "severity": "info",
                "category": "internal_rule",
                "message": "当前为架空/创作设定，事实核查重点转为内部规则自洽。",
                "suggestion": "把新规则写入 world_facts，后续章节持续引用。",
            }
        ],
        "checked_context": {
            "world_fact_count": len(state.canon_context.get("world_facts", [])),
            "entity_count": len(state.canon_context.get("story_entities", [])),
        },
    }
    payload, meta = _agent_payload(
        state,
        "fact_checker",
        "检查历史、科学、技术、地理、文化事实和内部设定规则。必须输出 fact_check_report。",
        {"fact_check_report": report},
    )
    fact_report = payload.get("fact_check_report", report)
    if not isinstance(fact_report, dict):
        fact_report = report
    return _update(data, current_agent="fact_checker", progress=0.78, fact_check_report=fact_report, agent_llm_results=_llm_results(state, "fact_checker", meta))


def quality_gate_node(data: dict[str, Any]) -> dict[str, Any]:
    state = _state(data)
    review_blockers = [item for item in state.review_notes if item.get("severity") in {"blocking", "error"}]
    fact_blockers = [item for item in state.fact_check_report.get("issues", []) if item.get("severity") in {"blocking", "error"}]
    status = "needs_revision" if review_blockers or fact_blockers else "passed"
    gate = {
        "status": status,
        "revision_count": state.revision_count,
        "blocking_issue_count": len(review_blockers) + len(fact_blockers),
        "message": "需要修订后再定稿。" if status == "needs_revision" else "通过质量门，可以进入风格统一与设定整理。",
    }
    return _update(data, current_agent="quality_gate", progress=0.82, quality_gate=gate)


def revise_draft_node(data: dict[str, Any]) -> dict[str, Any]:
    state = _state(data)
    suggestions = "；".join(item.get("suggestion", "") for item in state.review_notes if item.get("suggestion"))
    revised = f"{state.integrated_draft}\n\n【修订回路】已根据质量门意见补强：{suggestions or '补足角色动机与设定来源。'}"
    payload, meta = _agent_payload(
        state,
        "reviewer",
        "根据质量门和审稿意见修订 integrated_draft。必须输出 integrated_draft，可同时输出 quality_gate。",
        {"integrated_draft": revised, "quality_gate": {"status": "passed", "revision_count": state.revision_count + 1, "message": "修订后通过质量门。"}},
    )
    quality_gate = payload.get("quality_gate", {"status": "passed", "revision_count": state.revision_count + 1, "message": "修订后通过质量门。"})
    if not isinstance(quality_gate, dict):
        quality_gate = {"status": "passed", "revision_count": state.revision_count + 1, "message": "修订后通过质量门。"}
    return _update(
        data,
        current_agent="reviewer",
        progress=0.84,
        integrated_draft=str(payload.get("integrated_draft", revised)),
        revision_count=state.revision_count + 1,
        quality_gate=quality_gate,
        agent_llm_results=_llm_results(state, "reviewer", meta),
    )


def style_unifier_node(data: dict[str, Any]) -> dict[str, Any]:
    state = _state(data)
    text = state.integrated_draft or "\n\n".join([state.plot_draft, state.dialogue_draft, state.environment_draft])
    if state.style_guide:
        text += f"\n\n【风格统一】已按风格约束润色：{state.style_guide}"
    payload, meta = _agent_payload(
        state,
        "style_unifier",
        "按照 style_guide 统一章节风格。必须输出 style_polished_text 和 final_chapter_text。",
        {"style_polished_text": text, "final_chapter_text": text},
    )
    final_text = str(payload.get("final_chapter_text") or payload.get("style_polished_text") or text)
    return _update(
        data,
        current_agent="style_unifier",
        progress=0.9,
        style_polished_text=str(payload.get("style_polished_text", final_text)),
        final_chapter_text=final_text,
        agent_llm_results=_llm_results(state, "style_unifier", meta),
    )


def canon_curator_node(data: dict[str, Any]) -> dict[str, Any]:
    state = _state(data)
    chapter_title = state.current_chapter_outline.get("title", "当前章节")
    protagonist = state.canon_context.get("characters", state.characters)
    protagonist_name = protagonist[0]["name"] if protagonist else "主角"
    updates = {
        "character_updates": [{"name": protagonist_name, "updated_reason": f"在{chapter_title}中出现新的选择压力。", "confidence": 0.82}],
        "entity_updates": [{"name": "关键线索", "entity_type": "clue", "importance_score": 70}],
        "world_fact_updates": [{"title": f"{chapter_title}新增规则", "category": "timeline", "content": state.chapter_summary, "confidence": 0.75}],
        "relation_updates": [{"source": protagonist_name, "target": "关键线索", "edge_type": "searches_for", "confidence": 0.8}],
    }
    payload, meta = _agent_payload(
        state,
        "canon_curator",
        "从当前规划、正文、审校结果中抽取候选设定更新。必须输出 candidate_canon_updates 和 canon_updates。",
        {"candidate_canon_updates": updates, "canon_updates": updates},
    )
    candidate_updates = payload.get("candidate_canon_updates", updates)
    canon_updates = payload.get("canon_updates", candidate_updates)
    if not isinstance(candidate_updates, dict):
        candidate_updates = updates
    if not isinstance(canon_updates, dict):
        canon_updates = candidate_updates
    return _update(
        data,
        current_agent="canon_curator",
        progress=1.0,
        candidate_canon_updates=candidate_updates,
        canon_updates=canon_updates,
        agent_llm_results=_llm_results(state, "canon_curator", meta),
    )


class AgentWorkflow:
    def _compile(self, nodes: list[tuple[str, Callable[[dict[str, Any]], dict[str, Any]]]]):
        graph = StateGraph(dict)
        for name, node in nodes:
            graph.add_node(name, node)
        graph.add_edge(START, nodes[0][0])
        for (left, _), (right, _) in zip(nodes, nodes[1:]):
            graph.add_edge(left, right)
        graph.add_edge(nodes[-1][0], END)
        return graph.compile()

    def _compile_draft(self):
        graph = StateGraph(dict)
        nodes: list[tuple[str, Callable[[dict[str, Any]], dict[str, Any]]]] = [
            ("build_context", build_context_node),
            ("plot_narrator", plot_narrator_node),
            ("dialogue_writer", dialogue_writer_node),
            ("environment_writer", environment_writer_node),
            ("integrator", integrator_node),
            ("reviewer", reviewer_node),
            ("fact_checker", fact_checker_node),
            ("quality_gate", quality_gate_node),
            ("revise_draft", revise_draft_node),
            ("style_unifier", style_unifier_node),
            ("canon_curator", canon_curator_node),
        ]
        for name, node in nodes:
            graph.add_node(name, node)
        graph.add_edge(START, "build_context")
        graph.add_edge("build_context", "plot_narrator")
        graph.add_edge("plot_narrator", "dialogue_writer")
        graph.add_edge("dialogue_writer", "environment_writer")
        graph.add_edge("environment_writer", "integrator")
        graph.add_edge("integrator", "reviewer")
        graph.add_edge("reviewer", "fact_checker")
        graph.add_edge("fact_checker", "quality_gate")

        def route_after_quality_gate(data: dict[str, Any]) -> str:
            state = _state(data)
            if state.quality_gate.get("status") == "needs_revision" and state.revision_count < state.max_revisions:
                return "revise"
            return "pass"

        graph.add_conditional_edges("quality_gate", route_after_quality_gate, {"revise": "revise_draft", "pass": "style_unifier"})
        graph.add_edge("revise_draft", "style_unifier")
        graph.add_edge("style_unifier", "canon_curator")
        graph.add_edge("canon_curator", END)
        return graph.compile()

    def run_initialization(self, state: NovelStudioState) -> NovelStudioState:
        graph = self._compile([("chief_architect", chief_architect_node), ("canon_curator", canon_curator_node)])
        return NovelStudioState.model_validate(graph.invoke(state.model_dump()))

    def run_chapter_plan(self, state: NovelStudioState) -> NovelStudioState:
        graph = self._compile([("chapter_planner", chapter_planner_node), ("reviewer", reviewer_node), ("canon_curator", canon_curator_node)])
        return NovelStudioState.model_validate(graph.invoke(state.model_dump()))

    def run_chapter_draft(self, state: NovelStudioState) -> NovelStudioState:
        graph = self._compile_draft()
        return NovelStudioState.model_validate(graph.invoke(state.model_dump()))


agent_workflow = AgentWorkflow()
