from __future__ import annotations

from typing import Any, Callable
import re

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


def _positive_int(value: Any, default: int = 0) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return number if number > 0 else default


def _chapter_word_target(state: NovelStudioState) -> int:
    chapter = state.current_chapter_outline if isinstance(state.current_chapter_outline, dict) else {}
    explicit = _positive_int(chapter.get("word_target") or chapter.get("chapter_word_target"))
    if explicit:
        return explicit
    if state.target_words > 0 and state.target_chapters > 0:
        return max(1, state.target_words // state.target_chapters)
    return 0


def _chapter_word_min(state: NovelStudioState, target: int) -> int:
    chapter = state.current_chapter_outline if isinstance(state.current_chapter_outline, dict) else {}
    word_range = chapter.get("word_range")
    explicit_from_range = word_range[0] if isinstance(word_range, list) and word_range else None
    chapter_min = _positive_int(chapter.get("word_min") or chapter.get("chapter_word_min") or explicit_from_range)
    if chapter_min:
        return chapter_min
    project_min = _positive_int(state.chapter_word_min)
    if project_min:
        return min(project_min, target) if target > 0 else project_min
    return int(target * 0.85) if target > 0 else 0


def _chapter_word_max(state: NovelStudioState) -> int:
    chapter = state.current_chapter_outline if isinstance(state.current_chapter_outline, dict) else {}
    word_range = chapter.get("word_range")
    explicit_from_range = word_range[1] if isinstance(word_range, list) and len(word_range) > 1 else None
    return _positive_int(
        chapter.get("word_max")
        or chapter.get("chapter_word_max")
        or explicit_from_range
        or state.chapter_word_max
    )


def _text_length(value: str) -> int:
    return len(re.sub(r"\s+", "", value or ""))


def _length_requirements(state: NovelStudioState) -> dict[str, Any]:
    target = _chapter_word_target(state)
    minimum = _chapter_word_min(state, target)
    maximum = _chapter_word_max(state)
    chapter_no = _chapter_no(state)
    chapter_title = _chapter_title(state)
    ratio = round(minimum / target, 3) if target > 0 and minimum > 0 else 0
    return {
        "chapter_no": chapter_no,
        "chapter_title": chapter_title,
        "chapter_word_target": target,
        "minimum_acceptable_words": minimum,
        "maximum_words": maximum,
        "length_guard_ratio": ratio,
        "rule": f"当前只能生成第{chapter_no}章《{chapter_title}》正文，不得续写下一章；正文必须按单章目标字数生成，低于最低可接受字数时需要扩写场景、动作、心理和环境细节，不得只输出摘要。",
    }


def _length_instruction(state: NovelStudioState) -> str:
    requirements = _length_requirements(state)
    target = requirements["chapter_word_target"]
    minimum = requirements["minimum_acceptable_words"]
    chapter_no = requirements["chapter_no"]
    chapter_title = requirements["chapter_title"]
    if not target:
        return f"当前只能生成第{chapter_no}章《{chapter_title}》完整正文，不得续写下一章，不得只输出摘要。"
    maximum = requirements["maximum_words"]
    max_clause = f"，建议不超过 {maximum} 字" if maximum else ""
    return f"当前只能生成第{chapter_no}章《{chapter_title}》正文，不得续写下一章；本章目标约 {target} 字，最低可接受 {minimum} 字{max_clause}；必须写成完整正文，不得压缩成概要或片段。"


def _normalize_chapter_heading(state: NovelStudioState, text: str) -> str:
    expected = _chapter_title(state).strip()
    if not expected:
        return text
    stripped = text.lstrip()
    if not stripped:
        return expected
    leading_ws_length = len(text) - len(stripped)
    leading_ws = text[:leading_ws_length]
    lines = stripped.splitlines()
    if not lines:
        return f"{expected}\n\n{stripped}"
    heading_pattern = r"^\s*#{0,6}\s*第\s*(?:\d+|[零一二三四五六七八九十百千万两]+)\s*章(?:\s*[·:：、. -].*)?$"
    if re.match(heading_pattern, lines[0].strip()):
        lines[0] = expected
        return leading_ws + "\n".join(lines)
    if lines[0].strip() == expected:
        return text
    return text


def _reconcile_length_review_notes(
    review_notes: list[dict[str, Any]],
    *,
    target: int,
    minimum: int,
    final_length: int,
    guard_triggered: bool,
) -> list[dict[str, Any]]:
    if target <= 0:
        return review_notes
    adjusted: list[dict[str, Any]] = []
    length_terms = ("字数", "低于", "最低可接受", "扩写")
    for note in review_notes:
        if not isinstance(note, dict):
            continue
        message = f"{note.get('message', '')} {note.get('suggestion', '')}"
        if final_length >= minimum and any(term in message for term in length_terms):
            continue
        adjusted.append(note)
    if guard_triggered or final_length >= minimum:
        reached_minimum = minimum <= 0 or final_length >= minimum
        adjusted.append(
            {
                "severity": "info" if reached_minimum else "warning",
                "category": "length_guard",
                "message": (
                    f"最终正文 {final_length} 字，目标 {target} 字，最低可接受 {minimum} 字。"
                    if reached_minimum
                    else f"最终正文 {final_length} 字，仍低于最低可接受 {minimum} 字。"
                ),
                "suggestion": "字数守门已按最终正文重新校准。" if reached_minimum else "需继续扩写或人工复核后再定稿。",
            }
        )
    return adjusted


def _agent_context(state: NovelStudioState, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    length_requirements = _length_requirements(state)
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
            "chapter_word_target": length_requirements["chapter_word_target"],
            "chapter_word_min": length_requirements["minimum_acceptable_words"],
            "chapter_word_max": length_requirements["maximum_words"],
            "current_volume": state.current_volume,
            "current_chapter": state.current_chapter,
        },
        "generation_requirements": length_requirements,
        "core_conflict_system": state.core_conflict_system,
        "novel_constitution": state.novel_constitution,
        "constitution_review": state.constitution_review,
        "story_bible": state.story_bible,
        "characters": state.characters,
        "world_facts": state.world_facts,
        "story_entities": state.story_entities,
        "narrative_ledger": state.narrative_ledger,
        "canon_context": state.canon_context,
        "volume_outline": state.volume_outline,
        "rolling_chapter_outline": state.rolling_chapter_outline,
        "current_chapter_outline": state.current_chapter_outline,
        "chapter_card": state.chapter_card,
        "scene_outline": state.scene_outline,
        "completed_chapters": state.completed_chapters[-5:],
        "previous_agent_outputs": {
            "chapter_card": state.chapter_card,
            "scene_outline": state.scene_outline,
            "plot_draft": state.plot_draft,
            "dialogue_draft": state.dialogue_draft,
            "environment_draft": state.environment_draft,
            "integrated_draft": state.integrated_draft,
            "review_notes": state.review_notes,
            "fact_check_report": state.fact_check_report,
            "quality_gate": state.quality_gate,
            "chapter_summary": state.chapter_summary,
            "narrative_ledger": state.narrative_ledger,
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
        model=state.agent_model_configs.get(agent_name) or state.requested_model,
    )


def _llm_results(state: NovelStudioState, agent_name: str, meta: dict[str, Any]) -> dict[str, dict[str, Any]]:
    results = dict(state.agent_llm_results)
    results[agent_name] = meta
    return results


def _chapter_no(state: NovelStudioState) -> int:
    value = state.current_chapter_outline.get("chapter_no") or state.current_chapter
    try:
        return int(value)
    except (TypeError, ValueError):
        return state.current_chapter


def _chapter_title(state: NovelStudioState) -> str:
    return str(state.current_chapter_outline.get("title") or f"第{_chapter_no(state)}章")


def _card_from_outline(state: NovelStudioState, outline: dict[str, Any] | None = None) -> dict[str, Any]:
    chapter = outline or state.current_chapter_outline
    title = str(chapter.get("title") or _chapter_title(state))
    conflict = str(chapter.get("conflict") or "主角当前欲望与外部阻力发生正面碰撞。")
    core_event = str(chapter.get("core_event") or chapter.get("outline") or "推进当前章节核心事件。")
    return {
        "chapter_no": int(chapter.get("chapter_no") or _chapter_no(state)),
        "chapter_title": title,
        "word_target": _chapter_word_target(state),
        "chapter_function": str(chapter.get("plot_purpose") or "推进核心矛盾，并制造至少一种状态变化。"),
        "one_sentence": core_event,
        "opening_state": "主角带着上一章遗留压力进入新局面。",
        "protagonist_goal": str(chapter.get("protagonist_goal") or core_event),
        "main_obstacle": conflict,
        "conflict_escalation": [conflict, "信息差扩大，主角必须主动选择。", "选择造成不可逆后果。"],
        "key_choice": "主角必须在保全现状与追求真相之间选择。",
        "choice_cost": "关系、资源或认知上付出代价。",
        "irreversible_consequence": str(chapter.get("turn_point") or "章节结尾改变下一章行动方向。"),
        "relationship_change": "至少一组人物关系产生新的信任、裂痕或误解。",
        "foreshadowing": str(chapter.get("cliffhanger") or "一个旧设定被重新解释。"),
        "ending_hook": str(chapter.get("cliffhanger") or "新的问题逼迫主角继续行动。"),
    }


def _scene_outline_from_card(card: dict[str, Any]) -> dict[str, Any]:
    title = str(card.get("chapter_title") or "当前章节")
    escalation = card.get("conflict_escalation")
    if not isinstance(escalation, list) or not escalation:
        escalation = ["目标出现", "阻力升级", "选择落地"]
    return {
        "chapter_title": title,
        "scenes": [
            {
                "scene_no": 1,
                "goal": str(card.get("protagonist_goal") or "建立本章目标"),
                "conflict": str(escalation[0]),
                "information_change": "读者理解本章核心压力。",
                "emotional_change": "从不安进入警觉。",
                "ending_hook": "目标受阻。",
            },
            {
                "scene_no": 2,
                "goal": "逼近关键选择",
                "conflict": str(escalation[min(1, len(escalation) - 1)]),
                "information_change": "关键事实或误解浮出水面。",
                "emotional_change": "压力升高。",
                "ending_hook": "主角必须表态。",
            },
            {
                "scene_no": 3,
                "goal": "完成选择并落下后果",
                "conflict": str(escalation[-1]),
                "information_change": str(card.get("irreversible_consequence") or "局势被改写。"),
                "emotional_change": "选择后的余震出现。",
                "ending_hook": str(card.get("ending_hook") or "下一章问题被打开。"),
            },
        ],
        "emotion_curve": ["压迫", "升级", "余震"],
        "information_release_order": ["目标", "阻力", "代价"],
    }


def build_context_node(data: dict[str, Any]) -> dict[str, Any]:
    state = _state(data)
    context = dict(state.canon_context or {})
    context.setdefault("project", {"id": state.project_id, "title": state.title, "genre": state.genre})
    context.setdefault("novel_constitution", state.novel_constitution or state.story_bible)
    context.setdefault("story_bible", state.story_bible)
    context.setdefault("characters", state.characters)
    context.setdefault("world_facts", state.world_facts)
    context.setdefault("story_entities", state.story_entities)
    context.setdefault("narrative_ledger", state.narrative_ledger)
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
    core_conflict_system = {
        "protagonist_desire": f"{title}的主角必须追求一个无法轻易放弃的目标。",
        "world_resistance": "世界规则、制度压力、关系矛盾与主角缺陷共同构成阻力。",
        "core_conflict": story_bible["main_conflict"],
        "long_form_engine": "每一阶段都通过欲望、阻力、选择和代价制造新的状态变化。",
    }
    novel_constitution = {
        **story_bible,
        "core_narrative_engine": core_conflict_system,
        "cost_mechanism": ["获得力量必须付出代价", "赢得关系必须承担误解或牺牲", "靠近真相会改变主角处境"],
        "forbidden_directions": story_bible["forbidden_elements"],
    }
    constitution_review = {
        "status": "passed_with_notes",
        "largest_strength": "核心矛盾可持续制造选择与代价。",
        "largest_risk": "需要持续维护伏笔账本与关系变化，避免章节空转。",
        "recommended_next_stage": "outline_debate",
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
        "生成或更新核心矛盾系统、小说宪法、压力测试结果、核心角色与分卷结构。必须输出 story_bible、characters、outline，可输出 core_conflict_system、novel_constitution、constitution_review。",
        {
            "core_conflict_system": core_conflict_system,
            "novel_constitution": novel_constitution,
            "constitution_review": constitution_review,
            "story_bible": story_bible,
            "characters": characters,
            "outline": outline,
        },
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
    llm_core_conflict = payload.get("core_conflict_system", core_conflict_system)
    if not isinstance(llm_core_conflict, dict):
        llm_core_conflict = core_conflict_system
    llm_constitution = payload.get("novel_constitution") or llm_story_bible
    if not isinstance(llm_constitution, dict):
        llm_constitution = novel_constitution
    llm_constitution = {
        **llm_constitution,
        "world_setting": llm_story_bible.get("world_setting", llm_constitution.get("world_setting", world_setting)),
        "main_conflict": llm_story_bible.get("main_conflict", llm_constitution.get("main_conflict", story_bible["main_conflict"])),
        "themes": llm_story_bible.get("themes", llm_constitution.get("themes", [])),
        "style_guide": llm_story_bible.get("style_guide", llm_constitution.get("style_guide", state.style_guide)),
    }
    llm_review = payload.get("constitution_review", constitution_review)
    if not isinstance(llm_review, dict):
        llm_review = constitution_review
    return _update(
        data,
        current_agent="chief_architect",
        progress=0.2,
        world_setting=llm_story_bible.get("world_setting", world_setting),
        core_conflict_system=llm_core_conflict,
        novel_constitution=llm_constitution,
        constitution_review=llm_review,
        story_bible=llm_story_bible,
        characters=llm_characters,
        outline=llm_outline,
        agent_llm_results=_llm_results(state, "chief_architect", meta),
    )


def chapter_card_node(data: dict[str, Any]) -> dict[str, Any]:
    state = _state(data)
    fallback_card = _card_from_outline(state)
    payload, meta = _agent_payload(
        state,
        "chapter_planner",
        "根据小说宪法、当前卷大纲、滚动章节大纲、叙事账本和当前章纲生成单章章节卡。必须输出 chapter_card。",
        {"chapter_card": fallback_card},
        {"prompt_id": "chapter_card"},
    )
    card = payload.get("chapter_card")
    if not isinstance(card, dict):
        chapters = payload.get("chapters")
        if isinstance(chapters, list) and chapters and isinstance(chapters[0], dict):
            card = _card_from_outline(state, chapters[0])
        else:
            card = fallback_card
    return _update(
        data,
        current_agent="chapter_card",
        progress=0.42,
        chapter_card=card,
        agent_llm_results=_llm_results(state, "chapter_card", meta),
    )


def scene_outline_node(data: dict[str, Any]) -> dict[str, Any]:
    state = _state(data)
    fallback_outline = _scene_outline_from_card(state.chapter_card or _card_from_outline(state))
    payload, meta = _agent_payload(
        state,
        "plot_narrator",
        "根据章节卡生成场景细纲。必须输出 scene_outline，包含 scenes 数组、情绪曲线和信息释放顺序。",
        {"scene_outline": fallback_outline},
        {"prompt_id": "scene_outline"},
    )
    scene_outline = payload.get("scene_outline")
    if not isinstance(scene_outline, dict):
        scene_outline = fallback_outline
    return _update(
        data,
        current_agent="scene_outline",
        progress=0.46,
        scene_outline=scene_outline,
        agent_llm_results=_llm_results(state, "scene_outline", meta),
    )


def plot_narrator_node(data: dict[str, Any]) -> dict[str, Any]:
    state = _state(data)
    chapter = state.current_chapter_outline
    card = state.chapter_card or _card_from_outline(state)
    characters = _context_items(state, "characters", state.characters)
    facts = _context_items(state, "world_facts", state.world_facts)
    entities = _context_items(state, "story_entities", state.story_entities)
    lead = _name_list(characters)
    fact_names = _name_list(facts, "title")
    entity_names = _name_list(entities)
    text = (
        f"【情节主干】{card.get('chapter_title') or chapter.get('title', '本章')}围绕“{card.get('one_sentence') or chapter.get('core_event', '关键事件')}”展开。"
        f"本章优先读取设定上下文：核心角色={lead}；高重要度世界观={fact_names}；相关实体={entity_names}。"
        f"{lead.split('、')[0] if lead != '暂无' else '主角'}在压力下推进目标，却被“{card.get('main_obstacle') or chapter.get('conflict', '冲突')}”迫使改变策略。"
        "本段保留行动链、信息差和章节代价，供后续 Agent 加入对话与描写。"
    )
    payload, meta = _agent_payload(
        state,
        "plot_narrator",
        "基于 canon_context、章节卡和场景细纲生成章节情节主干，不写完整终稿，只输出 plot_draft。",
        {"plot_draft": text},
        {"prompt_id": "draft_generation"},
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
        "根据正文自检提示词审核当前章节草稿的逻辑、人物、节奏、伏笔和文笔问题。必须输出 review_notes 数组，可输出 health_check_report。",
        {
            "review_notes": notes,
            "health_check_report": {
                "status": "passed_with_notes",
                "chapter_title": state.chapter_card.get("chapter_title") or _chapter_title(state),
                "checks": ["章节功能", "状态变化", "人物主动性", "冲突来源", "伏笔推进"],
                "blocking_issue_count": 0,
            },
        },
        {"prompt_id": "draft_self_check"},
    )
    review_notes = payload.get("review_notes", notes)
    if not isinstance(review_notes, list):
        review_notes = notes
    health_check = payload.get("health_check_report")
    if not isinstance(health_check, dict):
        health_check = {
            "status": "passed_with_notes",
            "chapter_title": state.chapter_card.get("chapter_title") or _chapter_title(state),
            "checks": ["章节功能", "状态变化", "人物主动性", "冲突来源", "伏笔推进"],
            "blocking_issue_count": 0,
        }
    return _update(
        data,
        current_agent="reviewer",
        progress=0.72,
        review_notes=review_notes,
        health_check_report=health_check,
        agent_llm_results=_llm_results(state, "reviewer", meta),
    )


def integrator_node(data: dict[str, Any]) -> dict[str, Any]:
    state = _state(data)
    title = state.chapter_card.get("chapter_title") or state.current_chapter_outline.get("title", f"第{state.current_chapter}章")
    length_instruction = _length_instruction(state)
    integrated = (
        f"# {title}\n\n"
        f"{state.plot_draft}\n\n{state.dialogue_draft}\n\n{state.environment_draft}\n\n"
        "【整合草稿】本章以选择和代价收束，并在结尾留下后续悬念。"
    )
    summary = f"{title}推进了核心事件，主角在压力下获得新线索，同时付出关系或认知上的代价。"
    payload, meta = _agent_payload(
        state,
        "integrator",
        f"根据正文生成提示词，整合章节卡、场景细纲、情节、对话和环境层，生成 integrated_draft 与 chapter_summary。{length_instruction}",
        {"integrated_draft": integrated, "chapter_summary": summary},
        {"prompt_id": "draft_generation"},
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


def draft_rewrite_node(data: dict[str, Any]) -> dict[str, Any]:
    state = _state(data)
    suggestions = "；".join(item.get("suggestion", "") for item in state.review_notes if item.get("suggestion"))
    rewritten = (
        f"{state.integrated_draft}\n\n"
        f"【固定改写】已根据正文自检意见处理：{suggestions or '保持核心事件，强化选择、代价和结尾推动力。'}"
    )
    payload, meta = _agent_payload(
        state,
        "reviewer",
        "根据正文改写提示词修订 integrated_draft。保留核心事件、章节卡和不可逆后果。必须输出 integrated_draft。",
        {"integrated_draft": rewritten},
        {"prompt_id": "draft_rewrite"},
    )
    return _update(
        data,
        current_agent="draft_rewrite",
        progress=0.8,
        integrated_draft=str(payload.get("integrated_draft", rewritten)),
        agent_llm_results=_llm_results(state, "draft_rewrite", meta),
    )


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
    length_instruction = _length_instruction(state)
    payload, meta = _agent_payload(
        state,
        "style_unifier",
        f"按照 style_guide 统一章节风格。必须输出 style_polished_text 和 final_chapter_text。{length_instruction} 不得删减关键情节或压缩正文。",
        {"style_polished_text": text, "final_chapter_text": text},
    )
    final_text = str(payload.get("final_chapter_text") or payload.get("style_polished_text") or text)
    style_polished_text = str(payload.get("style_polished_text", final_text))
    target = _chapter_word_target(state)
    minimum = _chapter_word_min(state, target)
    current_length = _text_length(final_text)
    length_attempts: list[dict[str, Any]] = []
    length_meta: dict[str, Any] | None = None
    max_length_guard_attempts = 5
    for attempt_no in range(1, max_length_guard_attempts + 1):
        if target <= 0 or current_length >= minimum:
            break
        missing = max(0, minimum - current_length)
        buffer_words = min(max(120, int(target * 0.05)), max(120, target // 2))
        guarded_minimum = minimum + buffer_words
        expansion_payload, expansion_meta = _agent_payload(
            state,
            "style_unifier",
            (
                f"当前 final_chapter_text 只有 {current_length} 字，低于最低可接受字数 {minimum}。"
                f"至少还缺 {missing} 字；为避免估字误差，本次扩写后的最终正文必须不低于 {guarded_minimum} 字。"
                f"请在不改变章纲、人物选择、章节标题“{_chapter_title(state)}”和结尾钩子的前提下扩写为完整章节正文。"
                "扩写重点放在场景动作、心理反应、对话拉扯、环境压力和选择代价；必须输出 style_polished_text 和 final_chapter_text，不得只小幅润色。"
            ),
            {"style_polished_text": final_text, "final_chapter_text": final_text},
            {
                "prompt_id": "length_guard",
                "source_text": final_text,
                "length_guard": {
                    "attempt": attempt_no,
                    "target": target,
                    "minimum": minimum,
                    "guarded_minimum": guarded_minimum,
                    "current": current_length,
                    "missing": missing,
                },
            },
        )
        expanded_text = str(expansion_payload.get("final_chapter_text") or expansion_payload.get("style_polished_text") or "")
        expanded_length = _text_length(expanded_text)
        attempt_meta = {
            **expansion_meta,
            "attempt": attempt_no,
            "target_words": target,
            "minimum_acceptable_words": minimum,
            "before_words": current_length,
            "after_words": expanded_length,
            "expanded": expanded_length > current_length,
        }
        length_attempts.append(attempt_meta)
        if expanded_length > current_length:
            final_text = expanded_text
            style_polished_text = str(expansion_payload.get("style_polished_text") or expanded_text)
            current_length = expanded_length
    if length_attempts:
        length_meta = {
            **length_attempts[-1],
            "attempts": length_attempts,
            "reached_minimum": current_length >= minimum,
        }
    final_text = _normalize_chapter_heading(state, final_text)
    style_polished_text = _normalize_chapter_heading(state, style_polished_text)
    final_length = _text_length(final_text)
    review_notes = _reconcile_length_review_notes(
        state.review_notes,
        target=target,
        minimum=minimum,
        final_length=final_length,
        guard_triggered=length_meta is not None,
    )
    llm_results = _llm_results(state, "style_unifier", meta)
    if length_meta is not None:
        llm_results["style_unifier_length_guard"] = length_meta
    return _update(
        data,
        current_agent="style_unifier",
        progress=0.9,
        style_polished_text=style_polished_text,
        final_chapter_text=final_text,
        review_notes=review_notes,
        agent_llm_results=llm_results,
    )


def post_length_review_node(data: dict[str, Any]) -> dict[str, Any]:
    state = _state(data)
    target = _chapter_word_target(state)
    minimum = _chapter_word_min(state, target)
    final_text = state.final_chapter_text or state.style_polished_text
    final_length = _text_length(final_text)
    expected_title = _chapter_title(state).strip()
    first_line = next((line.strip().lstrip("#").strip() for line in final_text.splitlines() if line.strip()), "")
    heading_ok = not expected_title or first_line == expected_title
    length_ok = minimum <= 0 or final_length >= minimum
    status = "passed" if length_ok and heading_ok else "passed_with_notes" if length_ok else "needs_revision"
    checks = {
        "status": status,
        "chapter_no": _chapter_no(state),
        "chapter_title": expected_title,
        "final_words": final_length,
        "target_words": target,
        "minimum_acceptable_words": minimum,
        "length_ok": length_ok,
        "heading_ok": heading_ok,
        "length_guard_applied": "style_unifier_length_guard" in state.agent_llm_results,
    }
    review_notes = list(state.review_notes)
    severity = "info" if status == "passed" else "warning"
    message = (
        f"扩写后复审通过：最终正文 {final_length} 字，目标 {target or '未设置'} 字。"
        if status == "passed"
        else f"扩写后复审发现仍需关注：最终正文 {final_length} 字，最低要求 {minimum or '未设置'} 字，标题匹配={heading_ok}。"
    )
    review_notes.append(
        {
            "severity": severity,
            "category": "post_length_review",
            "message": message,
            "suggestion": "进入章后账本与正典更新。" if status == "passed" else "请人工复核标题、篇幅或后续章节边界。",
        }
    )
    health_check = dict(state.health_check_report)
    health_check["post_length_review"] = checks
    return _update(
        data,
        current_agent="post_length_review",
        progress=0.93,
        review_notes=review_notes,
        health_check_report=health_check,
    )


def canon_curator_node(data: dict[str, Any]) -> dict[str, Any]:
    state = _state(data)
    chapter_title = state.current_chapter_outline.get("title", "当前章节")
    protagonist = state.canon_context.get("characters", state.characters)
    protagonist_name = protagonist[0]["name"] if protagonist else "主角"
    updates = state.candidate_canon_updates or {
        "character_updates": [{"name": protagonist_name, "updated_reason": f"在{chapter_title}中出现新的选择压力。", "confidence": 0.82}],
        "entity_updates": [{"name": "关键线索", "entity_type": "clue", "importance_score": 70}],
        "world_fact_updates": [{"title": f"{chapter_title}新增规则", "category": "timeline", "content": state.chapter_summary, "confidence": 0.75}],
        "relation_updates": [{"source": protagonist_name, "target": "关键线索", "edge_type": "searches_for", "confidence": 0.8}],
    }
    payload, meta = _agent_payload(
        state,
        "canon_curator",
        "从章节卡、正文、叙事账本和审校结果中抽取候选设定更新。必须输出 candidate_canon_updates 和 canon_updates。",
        {"candidate_canon_updates": updates, "canon_updates": updates},
        {"prompt_id": "narrative_ledger_update"},
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


def narrative_ledger_node(data: dict[str, Any]) -> dict[str, Any]:
    state = _state(data)
    chapter_title = state.chapter_card.get("chapter_title") or _chapter_title(state)
    protagonist = state.canon_context.get("characters", state.characters)
    protagonist_name = protagonist[0]["name"] if protagonist else "主角"
    ledger = {
        "chapter_title": chapter_title,
        "chapter_summary": state.chapter_summary or f"{chapter_title}完成一次选择与代价的状态变化。",
        "state_changes": [
            {"type": "situation", "content": state.chapter_card.get("irreversible_consequence", "局势出现不可逆变化。")},
            {"type": "relationship", "content": state.chapter_card.get("relationship_change", "人物关系出现新压力。")},
        ],
        "character_states": [{"name": protagonist_name, "recent_change": "经历选择压力，下一步行动更明确。"}],
        "foreshadowing_updates": [{"content": state.chapter_card.get("foreshadowing", ""), "status": "candidate"}],
        "world_rule_updates": [{"content": state.chapter_summary, "source": chapter_title, "confidence": 0.75}],
        "next_chapter_input": state.chapter_card.get("ending_hook", ""),
    }
    candidate_updates = {
        "character_updates": [{"name": protagonist_name, "updated_reason": f"章后账本记录：{chapter_title}", "confidence": 0.82}],
        "world_fact_updates": [{"title": f"{chapter_title}章后摘要", "category": "timeline", "content": ledger["chapter_summary"], "confidence": 0.75}],
        "relation_updates": [{"source": protagonist_name, "target": chapter_title, "edge_type": "acts_in", "confidence": 0.78}],
    }
    payload, meta = _agent_payload(
        state,
        "canon_curator",
        "根据章后叙事账本更新提示词，更新叙事账本并输出候选设定变更。必须输出 narrative_ledger 和 candidate_canon_updates。",
        {"narrative_ledger": ledger, "candidate_canon_updates": candidate_updates},
        {"prompt_id": "narrative_ledger_update"},
    )
    narrative_ledger = payload.get("narrative_ledger", ledger)
    if not isinstance(narrative_ledger, dict):
        narrative_ledger = ledger
    updates = payload.get("candidate_canon_updates", candidate_updates)
    if not isinstance(updates, dict):
        updates = candidate_updates
    return _update(
        data,
        current_agent="narrative_ledger",
        progress=0.96,
        narrative_ledger=narrative_ledger,
        context_summary=(
            f"{narrative_ledger.get('chapter_title', chapter_title)}："
            f"{narrative_ledger.get('chapter_summary', ledger['chapter_summary'])} "
            f"下一章输入：{narrative_ledger.get('next_chapter_input', ledger['next_chapter_input'])}"
        ),
        candidate_canon_updates=updates,
        agent_llm_results=_llm_results(state, "narrative_ledger", meta),
    )


class AgentWorkflow:
    @staticmethod
    def _draft_progress_agent(node_name: str) -> str:
        if node_name == "build_context":
            return "canon_context"
        if node_name == "revise_draft":
            return "reviewer"
        return node_name

    def _running_state(self, data: dict[str, Any], node_name: str) -> NovelStudioState:
        current = dict(data)
        agent_name = self._draft_progress_agent(node_name)
        current["current_agent"] = agent_name
        current["progress_event"] = {"status": "running", "node": node_name, "agent_name": agent_name}
        return NovelStudioState.model_validate(current)

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
            ("chapter_card", chapter_card_node),
            ("scene_outline", scene_outline_node),
            ("plot_narrator", plot_narrator_node),
            ("dialogue_writer", dialogue_writer_node),
            ("environment_writer", environment_writer_node),
            ("integrator", integrator_node),
            ("reviewer", reviewer_node),
            ("fact_checker", fact_checker_node),
            ("draft_rewrite", draft_rewrite_node),
            ("quality_gate", quality_gate_node),
            ("revise_draft", revise_draft_node),
            ("style_unifier", style_unifier_node),
            ("post_length_review", post_length_review_node),
            ("narrative_ledger", narrative_ledger_node),
            ("canon_curator", canon_curator_node),
        ]
        for name, node in nodes:
            graph.add_node(name, node)
        graph.add_edge(START, "build_context")
        graph.add_edge("build_context", "chapter_card")
        graph.add_edge("chapter_card", "scene_outline")
        graph.add_edge("scene_outline", "plot_narrator")
        graph.add_edge("plot_narrator", "dialogue_writer")
        graph.add_edge("dialogue_writer", "environment_writer")
        graph.add_edge("environment_writer", "integrator")
        graph.add_edge("integrator", "reviewer")
        graph.add_edge("reviewer", "fact_checker")
        graph.add_edge("fact_checker", "draft_rewrite")
        graph.add_edge("draft_rewrite", "quality_gate")

        def route_after_quality_gate(data: dict[str, Any]) -> str:
            state = _state(data)
            if state.quality_gate.get("status") == "needs_revision" and state.revision_count < state.max_revisions:
                return "revise"
            return "pass"

        graph.add_conditional_edges("quality_gate", route_after_quality_gate, {"revise": "revise_draft", "pass": "style_unifier"})
        graph.add_edge("revise_draft", "style_unifier")
        graph.add_edge("style_unifier", "post_length_review")
        graph.add_edge("post_length_review", "narrative_ledger")
        graph.add_edge("narrative_ledger", "canon_curator")
        graph.add_edge("canon_curator", END)
        return graph.compile()

    def run_initialization(self, state: NovelStudioState) -> NovelStudioState:
        graph = self._compile([("chief_architect", chief_architect_node), ("canon_curator", canon_curator_node)])
        return NovelStudioState.model_validate(graph.invoke(state.model_dump()))

    def run_chapter_draft(self, state: NovelStudioState) -> NovelStudioState:
        result = state
        for result in self.stream_chapter_draft(state):
            pass
        return result

    def stream_chapter_draft(self, state: NovelStudioState):
        nodes: list[tuple[str, Callable[[dict[str, Any]], dict[str, Any]]]] = [
            ("build_context", build_context_node),
            ("chapter_card", chapter_card_node),
            ("scene_outline", scene_outline_node),
            ("plot_narrator", plot_narrator_node),
            ("dialogue_writer", dialogue_writer_node),
            ("environment_writer", environment_writer_node),
            ("integrator", integrator_node),
            ("reviewer", reviewer_node),
            ("fact_checker", fact_checker_node),
            ("draft_rewrite", draft_rewrite_node),
            ("quality_gate", quality_gate_node),
        ]
        data = state.model_dump()

        def run_node(node_name: str, node: Callable[[dict[str, Any]], dict[str, Any]]) -> NovelStudioState:
            nonlocal data
            data = dict(data)
            data["progress_event"] = {}
            result_data = node(data)
            data = dict(result_data)
            data["progress_event"] = {}
            return NovelStudioState.model_validate(data)

        result = state
        for node_name, node in nodes:
            yield self._running_state(data, node_name)
            result = run_node(node_name, node)
            yield result

        if result.quality_gate.get("status") == "needs_revision" and result.revision_count < result.max_revisions:
            yield self._running_state(data, "revise_draft")
            result = run_node("revise_draft", revise_draft_node)
            yield result

        for node_name, node in [
            ("style_unifier", style_unifier_node),
            ("post_length_review", post_length_review_node),
            ("narrative_ledger", narrative_ledger_node),
            ("canon_curator", canon_curator_node),
        ]:
            yield self._running_state(data, node_name)
            result = run_node(node_name, node)
            yield result


agent_workflow = AgentWorkflow()
