from __future__ import annotations

from collections.abc import Callable
from math import ceil
from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.pregel import Pregel

from app.agents.outline_swarm.agent_runner import OutlineSwarmAgentRunner
from app.agents.outline_swarm.state import OutlineSwarmState
from app.agents.outline_swarm.tools import create_completion_ticket, create_uncertainty_ticket, record_outline_piece, upsert_canon_candidate
from app.agents.outline_swarm.validators import OutlineSwarmStopValidator
from app.agents.shared.trace import append_trace


OUTLINE_SWARM_AGENT_NAMES = (
    "StoryDirectorAgent",
    "WhyInterrogatorAgent",
    "WorldSettingAgent",
    "CharacterArcAgent",
    "ConflictAgent",
    "PlotArchitectAgent",
    "BeatControllerAgent",
    "ForeshadowingAgent",
    "EntityExtractorAgent",
    "ContinuityAgent",
)


AgentHandler = Callable[[OutlineSwarmState, OutlineSwarmAgentRunner], OutlineSwarmState]


def build_outline_swarm(runner: OutlineSwarmAgentRunner | None = None) -> StateGraph:
    try:
        from langgraph_swarm import create_swarm
    except Exception as exc:  # pragma: no cover - dependency failure path
        raise RuntimeError("langgraph_swarm 不可用，请安装 langgraph-swarm。") from exc

    agent_runner = runner or OutlineSwarmAgentRunner()
    agents = [_compile_agent_graph(name, handler, agent_runner) for name, handler in _HANDLERS.items()]
    return create_swarm(
        agents,
        default_active_agent="StoryDirectorAgent",
        state_schema=OutlineSwarmState,
    )


def run_outline_swarm_app(
    initial_state: OutlineSwarmState,
    runner: OutlineSwarmAgentRunner | None = None,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> OutlineSwarmState:
    app = build_outline_swarm(runner).compile()
    state = initial_state
    while state.status == "running":
        result = app.invoke(state.model_dump(mode="json"))
        state = OutlineSwarmState.model_validate(result)
        if progress_callback is not None:
            progress_callback(state.model_dump(mode="json"))
        if state.status != "running":
            break
        if state.iteration_count >= state.max_iterations:
            stop = OutlineSwarmStopValidator().evaluate(state)
            state.status = "failed" if stop.reasons else "needs_user_review"
            append_trace(
                state.agent_trace,
                agent_name="ContinuityAgent",
                event_type="max_iteration",
                message="大纲 Swarm 达到最大推演轮数",
                payload=stop.model_dump(),
            )
            break
    return state


def _compile_agent_graph(agent_name: str, handler: AgentHandler, runner: OutlineSwarmAgentRunner) -> Pregel:
    graph = StateGraph(OutlineSwarmState)
    graph.add_node(agent_name, _node(handler, runner))
    graph.add_edge(START, agent_name)
    graph.add_edge(agent_name, END)
    return graph.compile(name=agent_name)


def _node(handler: AgentHandler, runner: OutlineSwarmAgentRunner) -> Callable[[dict[str, Any] | OutlineSwarmState], dict[str, Any]]:
    def wrapped(raw_state: dict[str, Any] | OutlineSwarmState) -> dict[str, Any]:
        state = _as_state(raw_state)
        state = handler(state, runner)
        return state.model_dump(mode="json")

    return wrapped


def _as_state(raw_state: dict[str, Any] | OutlineSwarmState) -> OutlineSwarmState:
    if isinstance(raw_state, OutlineSwarmState):
        return raw_state
    return OutlineSwarmState.model_validate(raw_state)


def _seed_text(state: OutlineSwarmState, *keys: str, default: str = "") -> str:
    for key in keys:
        value = state.seed.get(key)
        if value:
            return str(value)
    return default


def _advance(state: OutlineSwarmState, agent_name: str, next_agent: str, message: str, payload: dict[str, Any] | None = None) -> OutlineSwarmState:
    state.iteration_count += 1
    state.active_agent = next_agent
    append_trace(
        state.agent_trace,
        agent_name=agent_name,
        event_type="agent_step",
        message=message,
        payload={"next_agent": next_agent, **(payload or {})},
    )
    return state


def _run_agent(
    state: OutlineSwarmState,
    runner: OutlineSwarmAgentRunner,
    *,
    agent_name: str,
    role: str,
    task: str,
    fallback: dict[str, Any],
) -> dict[str, Any]:
    payload, meta = runner.run(agent_name=agent_name, state=state, role=role, task=task, fallback=fallback, model=state.model)
    state.agent_llm_results[agent_name] = meta
    append_trace(
        state.agent_trace,
        agent_name=agent_name,
        event_type="llm_call",
        message="完成 Agent 模型调用" if meta.get("used_remote_model") else "完成 Agent 本地降级调用",
        payload=meta,
    )
    return payload


def _story_director(state: OutlineSwarmState, runner: OutlineSwarmAgentRunner) -> OutlineSwarmState:
    genre = _seed_text(state, "genre", default="未指定类型")
    premise = _seed_text(state, "premise", "one_sentence_story", default="尚未填写一句话故事")
    target_length = _seed_text(state, "target_length", default=f"{state.volume_target}卷，{state.chapter_target}章")
    fallback = {
        "director_brief": {
            "genre": genre,
            "premise": premise,
            "target_length": target_length,
            "why_chain": [
                "为什么这个题材适合长篇连载：它需要持续升级的目标、阻力和信息差。",
                "为什么现在进入大纲推演：立项信息已足以确定主线、世界约束和章节容量。",
                "为什么不能直接写正文：S/A 级正典实体需要先补全并通过连续性检查。",
            ],
        }
    }
    payload = _run_agent(
        state,
        runner,
        agent_name="StoryDirectorAgent",
        role="长篇小说总导演",
        task="基于立项种子判断全书方向、核心问题和下一步 Agent 交接。",
        fallback=fallback,
    )
    state.outline.setdefault("director_brief", payload.get("director_brief", fallback["director_brief"]))
    return _advance(state, "StoryDirectorAgent", "WhyInterrogatorAgent", "确定大纲推演方向")


def _why_interrogator(state: OutlineSwarmState, runner: OutlineSwarmAgentRunner) -> OutlineSwarmState:
    fallback = {
        "why_questions": [
            "主角为什么必须进入这条主线，而不是选择更简单的逃避方案？",
            "核心冲突为什么会在故事开端爆发，而不是更早或更晚？",
            "世界规则为什么会持续提高主角选择的代价？",
        ],
    }
    payload = _run_agent(
        state,
        runner,
        agent_name="WhyInterrogatorAgent",
        role="为什么审问官",
        task="只追问关键设定、动机和因果链中的解释缺口，生成不确定项。",
        fallback=fallback,
    )
    questions = payload.get("why_questions", fallback["why_questions"])
    if not state.uncertainty_tickets:
        for question in questions:
            create_uncertainty_ticket(state, str(question))
    state.outline["why_questions"] = [ticket["question"] for ticket in state.uncertainty_tickets]
    return _advance(state, "WhyInterrogatorAgent", "WorldSettingAgent", "记录大纲前置 Why 问题")


def _world_setting(state: OutlineSwarmState, runner: OutlineSwarmAgentRunner) -> OutlineSwarmState:
    worldview = _seed_text(state, "worldview", default="待扩展世界观")
    tone = _seed_text(state, "tone", "style", default="待定风格")
    fallback = {
        "world_fact": {
            "title": "核心世界约束",
            "category": "world_rule",
            "content": worldview,
            "importance_level": "core",
            "importance_score": 90,
            "confidence": 0.72,
            "completion_status": "complete",
            "updated_reason": "大纲 Swarm 根据立项种子建立首个世界正典锚点",
        },
        "story_entity": {
            "name": "主线压力源",
            "entity_type": "concept",
            "level": "A",
            "importance_level": "major",
            "importance_score": 82,
            "description": f"从世界观中提取的长期压迫源：{worldview}",
            "story_function": "持续制造代价、阻力和升级压力",
            "completion_status": "complete",
            "tone": tone,
        },
    }
    payload = _run_agent(
        state,
        runner,
        agent_name="WorldSettingAgent",
        role="世界构建 Agent",
        task="补全世界蓝图、社会规则和主线压力源，要求全部可写入正典。",
        fallback=fallback,
    )
    if not state.world_facts:
        world_fact = payload.get("world_fact", fallback["world_fact"])
        if isinstance(world_fact, dict):
            state.world_facts.append(world_fact)
    if not any(entity.get("name") == "主线压力源" for entity in state.story_entities):
        story_entity = payload.get("story_entity", fallback["story_entity"])
        if not isinstance(story_entity, dict):
            story_entity = fallback["story_entity"]
        upsert_canon_candidate(
            state,
            story_entity,
        )
    return _advance(state, "WorldSettingAgent", "CharacterArcAgent", "补全世界约束与压力源")


def _character_arc(state: OutlineSwarmState, runner: OutlineSwarmAgentRunner) -> OutlineSwarmState:
    protagonist = _seed_text(state, "protagonist", "main_character", default="待命名主角")
    fallback = {
        "character": {
            "name": protagonist,
            "role_type": "protagonist",
            "importance_level": "core",
            "importance_score": 100,
            "external_goal": "追逐立项种子中最明确的长期欲望",
            "inner_need": "在不断付出代价后修正错误信念",
            "wrong_belief": "以为只要避开核心冲突就能保全自己",
            "arc_start": "被世界规则推入主线",
            "arc_crisis": "必须在个人目标与更大代价之间做不可逆选择",
            "arc_end": "用新的选择方式改写自身位置",
            "completion_status": "complete",
        }
    }
    payload = _run_agent(
        state,
        runner,
        agent_name="CharacterArcAgent",
        role="人物弧光 Agent",
        task="补全主角长篇弧光，明确外在目标、内在需求、错误信念、危机选择和结局状态。",
        fallback=fallback,
    )
    if not state.characters:
        character = payload.get("character", fallback["character"])
        if isinstance(character, dict):
            state.characters.append(character)
    return _advance(state, "CharacterArcAgent", "ConflictAgent", "建立主角弧光骨架")


def _conflict(state: OutlineSwarmState, runner: OutlineSwarmAgentRunner) -> OutlineSwarmState:
    premise = _seed_text(state, "premise", "one_sentence_story", default="主线尚未填写")
    protagonist = state.characters[0]["name"] if state.characters else "主角"
    fallback = {
        "conflict_matrix": {
            "core_conflict": f"{protagonist}想完成长期目标，但世界压力源不断提高代价。",
            "seed_premise": premise,
            "escalation_path": [
                "私人阻碍：目标刚出现就带来误解或损失",
                "局部压迫：身边关系与资源开始被卷入",
                "组织性阻力：反对方形成稳定追捕或围堵",
                "制度性围剿：主角行动触碰世界运行规则",
                "价值观决战：主角必须证明新的选择方式",
            ],
        }
    }
    payload = _run_agent(
        state,
        runner,
        agent_name="ConflictAgent",
        role="冲突矩阵 Agent",
        task="把人物欲望、世界压力和反对力量转化为不可轻易调和的升级冲突。",
        fallback=fallback,
    )
    conflict_matrix = payload.get("conflict_matrix", fallback["conflict_matrix"])
    if isinstance(conflict_matrix, dict):
        state.outline["conflict_matrix"] = conflict_matrix
    return _advance(state, "ConflictAgent", "PlotArchitectAgent", "把人物欲望转化为升级冲突")


def _plot_architect(state: OutlineSwarmState, runner: OutlineSwarmAgentRunner) -> OutlineSwarmState:
    genre = _seed_text(state, "genre", default="长篇类型小说")
    premise = _seed_text(state, "premise", "one_sentence_story", default="待补充主线")
    missing_volumes = [
        {
            "volume_no": volume_no,
            "title": f"第{volume_no}卷：主线第{volume_no}次升级",
            "chapter_range": _chapter_range_for_volume(volume_no, state.volume_target, state.chapter_target),
            "core_goal": "让主角获得阶段性进展，同时制造更高代价",
            "main_track": "主线目标推进",
            "hidden_track": "世界规则与秘密逐步露出",
            "volume_hook": "卷末用未解决代价引向下一阶段",
        }
        for volume_no in range(len(state.volume_outlines) + 1, state.volume_target + 1)
    ]
    fallback = {
        "outline": {
            "title": "全书结构总纲",
            "genre": genre,
            "premise": premise,
            "volume_count": state.volume_target,
            "chapter_count": state.chapter_target,
            "logic": "目标建立 -> 阻力升级 -> 反转揭示 -> 危机选择 -> 高潮后果",
        },
        "volume_outlines": missing_volumes,
    }
    payload = _run_agent(
        state,
        runner,
        agent_name="PlotArchitectAgent",
        role="长篇结构 Agent",
        task="根据总字数、卷数、章节数和正典上下文生成总纲与缺失卷纲。",
        fallback=fallback,
    )
    if not state.outline.get("title"):
        outline = payload.get("outline", fallback["outline"])
        if not isinstance(outline, dict):
            outline = fallback["outline"]
        record_outline_piece(
            state,
            "outline",
            outline,
        )
    volume_payloads = payload.get("volume_outlines", fallback["volume_outlines"])
    if not isinstance(volume_payloads, list):
        volume_payloads = fallback["volume_outlines"]
    for volume_payload in volume_payloads:
        if len(state.volume_outlines) >= state.volume_target:
            break
        if not isinstance(volume_payload, dict):
            continue
        record_outline_piece(
            state,
            "volume",
            volume_payload,
        )
    if state.generation_kind == "book_outline":
        return _advance(state, "PlotArchitectAgent", "ForeshadowingAgent", "生成总纲与卷纲，跳过章纲拆分")
    return _advance(state, "PlotArchitectAgent", "BeatControllerAgent", "生成总纲与卷纲")


def _beat_controller(state: OutlineSwarmState, runner: OutlineSwarmAgentRunner) -> OutlineSwarmState:
    missing_chapters = []
    for chapter_no in range(len(state.chapter_beats) + 1, state.chapter_target + 1):
        missing_chapters.append(
            {
                "chapter_no": chapter_no,
                "volume_no": _volume_for_chapter(chapter_no, state.volume_target, state.chapter_target),
                "title": f"第{chapter_no}章：阶段目标与反作用力",
                "story_function": "明确目标、遭遇阻力、暴露新信息、留下钩子",
                "protagonist_goal": "完成当前最迫切的小目标",
                "opposition_force": "来自世界规则、人物关系或反对势力的阻碍",
                "cost": "每次推进都带来资源、关系或认知损失",
                "hook": "用未解决问题推动下一章",
            }
        )
    payload = _run_agent(
        state,
        runner,
        agent_name="BeatControllerAgent",
        role="章节节拍 Agent",
        task="把卷纲拆成缺失章纲，每章必须包含目标、阻力、代价、信息和钩子。",
        fallback={"chapter_beats": missing_chapters},
    )
    chapter_payloads = payload.get("chapter_beats", missing_chapters)
    if not isinstance(chapter_payloads, list):
        chapter_payloads = missing_chapters
    for chapter_payload in chapter_payloads:
        if len(state.chapter_beats) >= state.chapter_target:
            break
        if not isinstance(chapter_payload, dict):
            continue
        record_outline_piece(
            state,
            "chapter",
            chapter_payload,
        )
    return _advance(state, "BeatControllerAgent", "ForeshadowingAgent", "拆分章纲节拍")


def _foreshadowing(state: OutlineSwarmState, runner: OutlineSwarmAgentRunner) -> OutlineSwarmState:
    fallback_items = [
        {
            "content": purpose,
            "planted_chapter_no": index,
            "planned_payoff_chapter_no": max(1, min(state.chapter_target, index + 3)),
            "payoff_status": "planned",
            "importance_level": "major" if index == 1 else "medium",
            "importance_score": 80 - index * 5,
        }
        for index, purpose in enumerate(("主角错误信念", "世界规则隐藏代价", "高潮选择的前置证据"), start=1)
    ]
    payload = _run_agent(
        state,
        runner,
        agent_name="ForeshadowingAgent",
        role="伏笔设计 Agent",
        task="为大纲设计可追踪的预埋与回收计划，确保服务主线、危机和高潮。",
        fallback={"foreshadowing_items": fallback_items},
    )
    if not state.foreshadowing_items:
        items = payload.get("foreshadowing_items", fallback_items)
        if not isinstance(items, list):
            items = fallback_items
        for item in items:
            if not isinstance(item, dict):
                continue
            record_outline_piece(
                state,
                "foreshadowing",
                item,
            )
    return _advance(state, "ForeshadowingAgent", "EntityExtractorAgent", "建立伏笔预埋与回收意图")


def _entity_extractor(state: OutlineSwarmState, runner: OutlineSwarmAgentRunner) -> OutlineSwarmState:
    required_entities = [
        *[{"entity_name": item["name"], "entity_level": "S", "completion_status": item.get("completion_status")} for item in state.characters],
        *[
            {
                "entity_name": item.get("title", item.get("name", "世界事实")),
                "entity_level": "A",
                "completion_status": item.get("completion_status"),
            }
            for item in state.world_facts
        ],
        *[
            {
                "entity_name": item.get("name", "剧情实体"),
                "entity_level": item.get("level", "B"),
                "completion_status": item.get("completion_status"),
            }
            for item in state.story_entities
        ],
    ]
    fallback_incomplete = [
        entity
        for entity in required_entities
        if entity["entity_level"] in {"S", "A"} and entity.get("completion_status") != "complete"
    ]
    payload = _run_agent(
        state,
        runner,
        agent_name="EntityExtractorAgent",
        role="实体抽取 Agent",
        task="从当前输出中抽取新增实体，判定 S/A/B/C 等级和必须补全字段。",
        fallback={"incomplete_required_entities": fallback_incomplete, "new_entities": required_entities},
    )
    incomplete = payload.get("incomplete_required_entities", fallback_incomplete)
    if not isinstance(incomplete, list):
        incomplete = fallback_incomplete
    state.incomplete_required_entities = [item for item in incomplete if isinstance(item, dict)]
    for entity in state.incomplete_required_entities:
        create_completion_ticket(state, entity)
    for ticket in state.completion_tickets:
        if ticket.get("entity_name") not in {entity["entity_name"] for entity in state.incomplete_required_entities}:
            ticket["status"] = "closed"
    return _advance(state, "EntityExtractorAgent", "ContinuityAgent", "抽取实体并检查补全状态")


def _continuity(state: OutlineSwarmState, runner: OutlineSwarmAgentRunner) -> OutlineSwarmState:
    stop = OutlineSwarmStopValidator().evaluate(state)
    payload = _run_agent(
        state,
        runner,
        agent_name="ContinuityAgent",
        role="连续性审查 Agent",
        task="检查实体补全、因果链、时间线、伏笔和章纲/卷纲完整度，并给出是否通过。",
        fallback={"stop_check": stop.model_dump(), "continuity_issues": state.continuity_issues},
    )
    issues = payload.get("continuity_issues")
    if isinstance(issues, list):
        state.continuity_issues = [item for item in issues if isinstance(item, dict)]
        stop = OutlineSwarmStopValidator().evaluate(state)
    append_trace(
        state.agent_trace,
        agent_name="ContinuityAgent",
        event_type="stop_check",
        message="完成大纲 Swarm 停止条件检查",
        payload=stop.model_dump(),
    )
    if stop.should_stop:
        state.status = stop.status
        return state
    if any("卷纲" in reason for reason in stop.reasons):
        next_agent = "PlotArchitectAgent"
    elif any("章纲" in reason for reason in stop.reasons):
        next_agent = "BeatControllerAgent"
    elif state.incomplete_required_entities:
        next_agent = "EntityExtractorAgent"
    elif any("continuity" in reason for reason in stop.reasons):
        next_agent = "StoryDirectorAgent"
    else:
        next_agent = "PlotArchitectAgent"
    return _advance(state, "ContinuityAgent", next_agent, "未满足停止条件，交回对应 Agent 修复", {"reasons": stop.reasons})


def _chapter_range_for_volume(volume_no: int, volume_target: int, chapter_target: int) -> str:
    chapters_per_volume = max(1, ceil(chapter_target / max(1, volume_target)))
    start = (volume_no - 1) * chapters_per_volume + 1
    end = min(chapter_target, volume_no * chapters_per_volume)
    return f"{start}-{end}"


def _volume_for_chapter(chapter_no: int, volume_target: int, chapter_target: int) -> int:
    chapters_per_volume = max(1, ceil(chapter_target / max(1, volume_target)))
    return min(volume_target, max(1, ceil(chapter_no / chapters_per_volume)))


_HANDLERS: dict[str, AgentHandler] = {
    "StoryDirectorAgent": _story_director,
    "WhyInterrogatorAgent": _why_interrogator,
    "WorldSettingAgent": _world_setting,
    "CharacterArcAgent": _character_arc,
    "ConflictAgent": _conflict,
    "PlotArchitectAgent": _plot_architect,
    "BeatControllerAgent": _beat_controller,
    "ForeshadowingAgent": _foreshadowing,
    "EntityExtractorAgent": _entity_extractor,
    "ContinuityAgent": _continuity,
}
