from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any, Iterable

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.agents.llm_io import call_agent_json
from app.core.config import LLMProviderResolver, get_settings
from app.core.ids import generate_id
from app.core.json import dumps, loads
from app.db import models
from app.db.models import utcnow
from app.schemas.outline import BookOutlineCommitRequest, ChapterOutlineCommitRequest, OutlineDebateCommitRequest, OutlineDebateConfirmRequest, OutlineDebateInterruptRequest, OutlineDebateRunRequest, OutlineDebateSessionCreateRequest, OutlineDebateUserMessageRequest
from app.services.llm_client import llm_client
from app.services.serializers import (
    serialize_chapter,
    serialize_character,
    serialize_continuity_issue,
    serialize_creation_session,
    serialize_foreshadowing_item,
    serialize_graph_edge,
    serialize_graph_node,
    serialize_job,
    serialize_project,
    serialize_story_bible,
    serialize_story_entity,
    serialize_volume,
    serialize_world_fact,
)


PHASE_CONFIG: dict[str, dict[str, str]] = {
    "book": {
        "label": "讨论总纲",
        "generation_kind": "outline_debate_book",
        "result_key": "book_outline_candidate",
        "result_title": "总纲候选",
    },
    "volumes": {
        "label": "讨论卷纲",
        "generation_kind": "outline_debate_volumes",
        "result_key": "volume_outline_candidates",
        "result_title": "卷纲候选",
    },
    "chapters": {
        "label": "讨论章纲",
        "generation_kind": "outline_debate_chapters",
        "result_key": "chapter_outline_candidates",
        "result_title": "章纲候选",
    },
}

PHASE_ORDER = ("book", "volumes", "chapters")
PHASE_UPSTREAM_LABELS = {"volumes": ("book", "总纲"), "chapters": ("volumes", "卷纲")}

DEBATE_AGENTS: tuple[tuple[str, str], ...] = (
    ("outline_debate/StoryDirectorAgent", "主持总策划 Agent"),
    ("outline_debate/MarketPositionAgent", "类型卖点与读者体验 Agent"),
    ("outline_debate/StructureDoctorAgent", "结构医生 Agent"),
    ("outline_debate/CharacterGeneratorAgent", "大纲角色生成 Agent"),
    ("outline_debate/SettingGeneratorAgent", "大纲设定生成 Agent"),
    ("outline_debate/ContinuityAuditorAgent", "连续性审计 Agent"),
)

DEBATE_AGENT_SYSTEM_PROMPTS: dict[str, str] = {
    "outline_debate/StoryDirectorAgent": (
        "你是大纲讨论组的主持总策划 Agent。你的能力是收束作品承诺、核心矛盾、阶段边界和候选产物。"
        "你必须读取 context 中的 Star 立项种子、项目资料、已确认正典和上游阶段结果。"
        "本轮只输出候选讨论意见，不得宣称已经写入 Story Bible、Volumes、Chapters 或正典表。"
    ),
    "outline_debate/MarketPositionAgent": (
        "你是类型卖点与读者体验 Agent。你的能力是判断频道、类型、爽点、压迫感、情感拉扯、平台期待和商业可读性。"
        "你必须把读者体验转成可持续冲突、章节钩子和风险提示，不得生成空泛营销话术。"
    ),
    "outline_debate/StructureDoctorAgent": (
        "你是结构医生 Agent。你的能力是检查长篇因果链、节奏模型、危机/高潮/结果边界、卷章功能和返工点。"
        "必须严格区分：危机是不可逆选择，高潮是执行选择，结果是承担后果。"
    ),
    "outline_debate/CharacterGeneratorAgent": (
        "你是大纲角色生成 Agent。你的能力是在大纲讨论发现角色缺口时生成角色档案卡候选。"
        "角色必须有剧情功能、首次需要位置、冲突关系、重复项检查建议和确认物化边界。"
        "讨论发言阶段不得要求直接写入 characters 表；用户确认对应候选后由服务层入库。"
    ),
    "outline_debate/SettingGeneratorAgent": (
        "你是大纲设定生成 Agent。你的能力是在大纲讨论发现规则、地点、组织、物件或制度缺口时生成设定候选。"
        "设定必须说明冲突用途、伏笔用途、连续性风险和确认物化边界。讨论发言阶段不得要求直接写入 world_facts 或 graph 表；用户确认对应候选后由服务层入库。"
    ),
    "outline_debate/ContinuityAuditorAgent": (
        "你是连续性审计 Agent。你的能力是标记不确定项、冲突风险、缺失来源、阻塞问题和需要用户确认的变更。"
        "不确定不得硬编，任何正式正典变更都必须进入候选审批。"
    ),
}

DEBATE_AGENT_SKILL_SPECS: dict[str, dict[str, Any]] = {
    "outline_debate/StoryDirectorAgent": {
        "core_capability": "主持讨论并收束作品承诺、主线冲突、阶段目标和候选结论。",
        "skill_file": "app/prompts/outline_debate_story_director_skill.md",
        "skills": ["长篇主线设计 skill", "冲突发动机 skill", "终局反推 skill", "讨论主持 skill", "决议归纳 skill"],
        "required_context_keys": ["project", "story_bible", "canon_context", "scale_plan", "upstream_phase_runs", "requirement"],
        "allowed_read_tools": ["get_project_state", "get_story_bible", "get_canon_context", "list_volumes", "list_chapters"],
        "allowed_candidate_tools": ["record_outline_piece", "build_outline_topology", "create_uncertainty_ticket"],
        "validators": ["schema_validator", "impact_analyzer"],
        "forbidden_tools": ["commit_book_outline", "commit_chapter_outlines", "createCharacter", "createWorldFact", "createEntity"],
        "candidate_policy": "只形成可确认大纲候选，不直接写入正式大纲或正典。",
    },
    "outline_debate/MarketPositionAgent": {
        "core_capability": "判断目标读者体验、类型卖点、压迫感和期待管理。",
        "skill_file": "app/prompts/outline_debate_market_position_skill.md",
        "skills": ["类型文卖点识别 skill", "目标读者体验建模 skill", "平台风格判断 skill", "预期管理 skill"],
        "required_context_keys": ["project", "story_bible", "canon_context", "scale_plan", "requirement"],
        "allowed_read_tools": ["get_project_state", "get_story_bible", "get_canon_context"],
        "allowed_candidate_tools": ["record_outline_piece"],
        "validators": ["schema_validator", "impact_analyzer"],
        "forbidden_tools": ["commit_book_outline", "commit_chapter_outlines", "createCharacter", "createWorldFact", "createEntity"],
        "candidate_policy": "只把市场判断转译为冲突、钩子和风险，不创建正式设定。",
    },
    "outline_debate/StructureDoctorAgent": {
        "core_capability": "检查长篇结构、卷节奏、章节因果，以及危机/高潮/结果边界。",
        "skill_file": "app/prompts/outline_debate_structure_doctor_skill.md",
        "skills": ["节奏模型选择 skill", "危机高潮结果区分 skill", "长篇因果链检查 skill", "卷纲拆分 skill", "章纲密度控制 skill"],
        "required_context_keys": ["project", "story_bible", "canon_context", "scale_plan", "upstream_phase_runs", "requirement"],
        "allowed_read_tools": ["get_project_state", "get_story_bible", "get_canon_context", "list_volumes", "list_chapters"],
        "allowed_candidate_tools": ["record_outline_piece", "create_completion_ticket"],
        "validators": ["schema_validator", "rhythm_model_selector", "crisis_climax_result_checker", "impact_analyzer"],
        "forbidden_tools": ["commit_book_outline", "commit_chapter_outlines", "createCharacter", "createWorldFact", "createEntity"],
        "candidate_policy": "只校正结构候选；发现结构阻塞时登记返工建议。",
    },
    "outline_debate/CharacterGeneratorAgent": {
        "core_capability": "在大纲讨论发现角色缺口时生成候选角色卡。",
        "skill_file": "app/prompts/outline_debate_character_generator_skill.md",
        "skills": ["角色功能识别 skill", "人物卡生成 skill", "角色关系钩子 skill", "重复角色识别 skill", "活跃状态重要度分类 skill"],
        "required_context_keys": ["project", "canon_context.characters", "canon_context.graph", "requirement"],
        "allowed_read_tools": ["get_canon_context", "list_characters", "get_graph"],
        "allowed_candidate_tools": ["create_character_candidate", "create_uncertainty_ticket"],
        "validators": ["schema_validator", "duplicate_scanner", "impact_analyzer"],
        "forbidden_tools": ["createCharacter", "commit_book_outline", "commit_chapter_outlines"],
        "candidate_policy": "只有明确角色缺口时才生成 character_candidate；候选随对应总纲/卷纲/章纲确认由服务层物化。",
    },
    "outline_debate/SettingGeneratorAgent": {
        "core_capability": "在大纲讨论发现规则、地点、组织、物件或制度缺口时生成候选设定。",
        "skill_file": "app/prompts/outline_debate_setting_generator_skill.md",
        "skills": ["世界规则生成 skill", "组织地点物件制度生成 skill", "设定冲突用途分析 skill", "伏笔用途分析 skill", "正典候选归类 skill"],
        "required_context_keys": ["project", "canon_context.entities", "canon_context.world_facts", "canon_context.graph", "requirement"],
        "allowed_read_tools": ["get_canon_context", "list_entities", "list_world_facts", "get_graph", "list_foreshadowing"],
        "allowed_candidate_tools": ["create_setting_candidate", "create_uncertainty_ticket"],
        "validators": ["schema_validator", "duplicate_scanner", "continuity_checker", "impact_analyzer"],
        "forbidden_tools": ["createWorldFact", "createEntity", "commit_book_outline", "commit_chapter_outlines"],
        "candidate_policy": "只有明确设定缺口时才生成 setting_candidate；候选随对应总纲/卷纲/章纲确认由服务层物化。",
    },
    "outline_debate/ContinuityAuditorAgent": {
        "core_capability": "审计连续性、正典冲突、伏笔账本、时间线和不确定项。",
        "skill_file": "app/prompts/outline_debate_continuity_auditor_skill.md",
        "skills": ["连续性审计 skill", "正典冲突检测 skill", "伏笔账本检查 skill", "时间线检查 skill", "不确定项登记 skill"],
        "required_context_keys": ["project", "story_bible", "canon_context", "scale_plan", "upstream_phase_runs", "requirement"],
        "allowed_read_tools": ["get_project_state", "get_story_bible", "get_canon_context", "get_graph", "list_foreshadowing", "list_chapters"],
        "allowed_candidate_tools": ["create_uncertainty_ticket", "create_completion_ticket", "record_outline_piece"],
        "validators": ["schema_validator", "continuity_checker", "crisis_climax_result_checker", "impact_analyzer"],
        "forbidden_tools": ["createCharacter", "createWorldFact", "createEntity", "commit_book_outline", "commit_chapter_outlines"],
        "candidate_policy": "只输出风险、证据和待确认项；不得把不确定内容写成正式正典。",
    },
}

DEBATE_AGENT_ALIASES: dict[str, str] = {
    "主持": "outline_debate/StoryDirectorAgent",
    "主持总策划": "outline_debate/StoryDirectorAgent",
    "总策划": "outline_debate/StoryDirectorAgent",
    "市场": "outline_debate/MarketPositionAgent",
    "类型卖点": "outline_debate/MarketPositionAgent",
    "读者体验": "outline_debate/MarketPositionAgent",
    "结构医生": "outline_debate/StructureDoctorAgent",
    "结构": "outline_debate/StructureDoctorAgent",
    "角色生成": "outline_debate/CharacterGeneratorAgent",
    "角色": "outline_debate/CharacterGeneratorAgent",
    "设定生成": "outline_debate/SettingGeneratorAgent",
    "设定": "outline_debate/SettingGeneratorAgent",
    "连续性审计": "outline_debate/ContinuityAuditorAgent",
    "连续性": "outline_debate/ContinuityAuditorAgent",
    "审计": "outline_debate/ContinuityAuditorAgent",
}

DEBATE_AGENT_NAMES = {agent_name for agent_name, _role in DEBATE_AGENTS}
DEBATE_AGENT_MENTION_LABELS = {
    "outline_debate/StoryDirectorAgent": "主持总策划",
    "outline_debate/MarketPositionAgent": "类型卖点",
    "outline_debate/StructureDoctorAgent": "结构医生",
    "outline_debate/CharacterGeneratorAgent": "角色生成",
    "outline_debate/SettingGeneratorAgent": "设定生成",
    "outline_debate/ContinuityAuditorAgent": "连续性审计",
}

DISPLAY_KEY_LABELS: dict[str, str] = {
    "agent_name": "发言角色",
    "artifact_patch": "候选大纲补丁",
    "audience": "目标读者",
    "boundary": "阶段边界",
    "book_outline": "总纲",
    "book_outline_candidate": "总纲候选",
    "canon_update": "正典更新",
    "candidate_status": "候选状态",
    "chapter_count": "章节数",
    "chapter_distribution": "章节分配",
    "chapter_no": "章序",
    "chapter_outline": "章纲",
    "chapter_outline_candidates": "章纲候选",
    "chapter_outlines": "章纲列表",
    "chapter_ranges": "章节范围",
    "chapter_word_max": "单章最高字数",
    "chapter_word_min": "单章最低字数",
    "chapter_word_target": "单章目标字数",
    "chapters": "章节",
    "chapters_per_volume": "每卷章节数",
    "character_candidate": "角色候选",
    "claims": "关键主张",
    "cliffhanger": "章末钩子",
    "climax": "高潮",
    "confidence": "置信度",
    "conflict": "冲突",
    "continuity_risk": "连续性风险",
    "core_promise": "作品承诺",
    "cost": "代价",
    "crisis": "危机",
    "decisions": "决议",
    "discussion_summary": "讨论摘要",
    "ending_direction": "终局方向",
    "events": "事件",
    "foreshadowing": "伏笔",
    "foreshadowing_direction": "伏笔方向",
    "generation_kind": "生成类型",
    "hook": "钩子",
    "item_key": "条目标识",
    "main_conflict": "主线冲突",
    "market_position": "类型定位",
    "message": "意见",
    "name": "名称",
    "objections": "反对与质疑",
    "outline_topology": "推演拓扑",
    "phase": "阶段",
    "phase_count": "阶段数",
    "phase_goal": "阶段目标",
    "phase_label": "阶段名称",
    "pov": "视角",
    "proposed_decisions": "建议决议",
    "protagonist_change": "主角变化",
    "protagonist_long_change": "主角长期变化",
    "reader_experience": "读者体验",
    "requires_user_confirmation": "需要用户确认",
    "result": "结果",
    "result_patch": "结果补丁",
    "rhythm_model": "节奏模型",
    "risks": "风险",
    "setting_candidate": "设定候选",
    "stage_goal": "阶段目标",
    "status": "状态",
    "title": "标题",
    "turn_count": "发言数",
    "uncertainties": "不确定项",
    "volume_count": "卷数",
    "volume_no": "卷序",
    "volume_outline": "卷纲",
    "volume_outline_candidates": "卷纲候选",
    "volume_outlines": "卷纲列表",
    "why_this_model": "模型选择理由",
    "world_pressure": "世界压力",
}

DISPLAY_KEY_TOKEN_LABELS: dict[str, str] = {
    "actual": "实际",
    "agent": "角色",
    "arc": "弧光",
    "artifact": "产物",
    "audit": "审计",
    "beat": "节拍",
    "beats": "节拍",
    "book": "总纲",
    "boundary": "边界",
    "candidate": "候选",
    "candidates": "候选",
    "canon": "正典",
    "chapter": "章节",
    "chapters": "章节",
    "character": "角色",
    "characters": "角色",
    "climax": "高潮",
    "conflict": "冲突",
    "confirmation": "确认",
    "continuity": "连续性",
    "cost": "代价",
    "count": "数量",
    "crisis": "危机",
    "decision": "决议",
    "decisions": "决议",
    "direction": "方向",
    "distribution": "分配",
    "ending": "终局",
    "event": "事件",
    "events": "事件",
    "experience": "体验",
    "fact": "事实",
    "foreshadowing": "伏笔",
    "goal": "目标",
    "hook": "钩子",
    "item": "条目",
    "key": "标识",
    "kind": "类型",
    "label": "名称",
    "long": "长期",
    "main": "主线",
    "market": "市场",
    "materialization": "入库",
    "model": "模型",
    "name": "名称",
    "outline": "大纲",
    "patch": "补丁",
    "phase": "阶段",
    "position": "定位",
    "pressure": "压力",
    "promise": "承诺",
    "protagonist": "主角",
    "reader": "读者",
    "reason": "理由",
    "result": "结果",
    "risk": "风险",
    "risks": "风险",
    "setting": "设定",
    "stage": "阶段",
    "status": "状态",
    "summary": "摘要",
    "target": "目标",
    "title": "标题",
    "topology": "拓扑",
    "turn": "发言",
    "uncertainty": "不确定项",
    "uncertainties": "不确定项",
    "update": "更新",
    "user": "用户",
    "volume": "卷",
    "volumes": "卷",
    "why": "理由",
    "word": "字数",
    "world": "世界",
}

_CHINESE_NUMERALS = "零一二三四五六七八九十"


def _not_found(message: str) -> HTTPException:
    return HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": message})


def _bad_request(message: str) -> HTTPException:
    return HTTPException(status_code=400, detail={"code": "VALIDATION_ERROR", "message": message})


def _sse_block(event_name: str, payload: dict[str, Any]) -> str:
    return f"event: {event_name}\ndata: {dumps(payload)}\n\n"


class OutlineDebateOrchestrator:
    """Coordinates debate protocol state while the service owns persistence."""

    steps = [
        "build_agenda",
        "run_agent_turn",
        "apply_turn_to_debate_state",
        "cross_review",
        "synthesize_candidate_artifact",
        "validate_result",
        "request_revision_or_finish",
    ]

    def __init__(self, service: "OutlineDebateService"):
        self.service = service

    def build_agenda(self, phase: str, request: OutlineDebateRunRequest, context: dict[str, Any]) -> dict[str, Any]:
        questions_by_phase = {
            "book": [
                "作品核心承诺是否能支撑长篇规模？",
                "主线冲突、世界压力和终局方向是否互相因果递进？",
                "读者体验是否能转化为持续钩子和阶段代价？",
                "哪些角色或设定缺口只应生成候选，不应直接入库？",
            ],
            "volumes": [
                "目标卷承担什么长篇功能？",
                "节奏模型为什么适合这一卷，而不是套用固定模板？",
                "卷内主线、暗线、人物线和世界揭示如何因果递进？",
                "卷末钩子如何改变下一卷压力？",
            ],
            "chapters": [
                "目标章的核心事件、POV 和章内冲突是什么？",
                "危机、高潮、结果是否严格分离？",
                "章末钩子和伏笔状态如何服务下一章？",
                "连续性风险和不确定项是否需要登记？",
            ],
        }
        return {
            "id": generate_id("agenda"),
            "phase": phase,
            "phase_label": PHASE_CONFIG[phase]["label"],
            "objective": request.requirement or context.get("session_brief") or "按项目上下文生成可确认大纲候选。",
            "open_questions": questions_by_phase[phase],
            "required_outputs": [PHASE_CONFIG[phase]["result_key"], "decisions", "outline_topology", "validation_report"],
            "user_requirement": request.requirement,
            "created_at": utcnow().isoformat(),
        }

    def initial_state(self, agenda: dict[str, Any], request: OutlineDebateRunRequest) -> dict[str, Any]:
        return {
            "id": generate_id("ods"),
            "source": "local_preview" if request.local_preview else "real_llm",
            "agenda_id": agenda["id"],
            "phase": agenda["phase"],
            "open_questions": list(agenda.get("open_questions") or []),
            "agreements": [],
            "conflicts": [],
            "decisions": [],
            "artifact_patches": [],
            "blocked_items": [],
            "turn_ids": [],
            "source_turn_ids": [],
            "turn_count": 0,
        }

    def turn_contract(self) -> dict[str, Any]:
        return {
            "stance": "",
            "message": "",
            "claims": [],
            "objections": [],
            "proposed_decisions": [],
            "artifact_patch": {},
            "result_patch": {},
            "risks": [],
            "uncertainties": [],
            "confidence": 0.0,
            "character_candidate": {},
            "setting_candidate": {},
            "decisions": [],
        }

    def turn_context(self, context: dict[str, Any], agenda: dict[str, Any] | None, state: dict[str, Any] | None) -> dict[str, Any]:
        enriched = dict(context)
        if agenda:
            enriched["agenda"] = agenda
        if state:
            enriched["deliberation_state"] = state
        return enriched

    def apply_turn_to_state(self, state: dict[str, Any], turn: dict[str, Any]) -> None:
        state.setdefault("turn_ids", []).append(turn["id"])
        state.setdefault("source_turn_ids", []).append(turn["id"])
        state["turn_count"] = len(state["turn_ids"])
        for claim in turn.get("claims", []):
            state.setdefault("agreements", []).append({"turn_id": turn["id"], "agent_name": turn["agent_name"], "claim": claim})
        for objection in turn.get("objections", []):
            state.setdefault("conflicts", []).append({"turn_id": turn["id"], "agent_name": turn["agent_name"], "objection": objection})
        for decision in [*turn.get("proposed_decisions", []), *turn.get("decisions", [])]:
            if isinstance(decision, dict):
                value = decision
            else:
                value = {"decision": str(decision)}
            state.setdefault("decisions", []).append({"turn_id": turn["id"], "agent_name": turn["agent_name"], **value})
        patch = turn.get("artifact_patch") if isinstance(turn.get("artifact_patch"), dict) and turn.get("artifact_patch") else turn.get("result_patch")
        if isinstance(patch, dict) and patch:
            state.setdefault("artifact_patches", []).append({"turn_id": turn["id"], "agent_name": turn["agent_name"], "patch": patch})
        for item in turn.get("uncertainties", []):
            state.setdefault("blocked_items", []).append({"turn_id": turn["id"], "agent_name": turn["agent_name"], "item": item})

    def cross_review(self, state: dict[str, Any], turns: list[dict[str, Any]]) -> dict[str, Any]:
        review = {
            "status": "needs_revision" if state.get("blocked_items") else "passed",
            "turn_count": len(turns),
            "objection_count": len(state.get("conflicts", [])),
            "blocked_count": len(state.get("blocked_items", [])),
            "reviewed_at": utcnow().isoformat(),
        }
        state["cross_review"] = review
        return review

    def synthesize_candidate_artifact(
        self,
        project: models.Project,
        phase: str,
        request: OutlineDebateRunRequest,
        turns: list[dict[str, Any]],
        session: dict[str, Any],
        state: dict[str, Any],
    ) -> dict[str, Any]:
        return self.service._build_result_from_debate_state(project, phase, request, turns, session, state)

    def validate_result(self, phase: str, result: dict[str, Any], artifacts: list[dict[str, Any]], context: dict[str, Any]) -> dict[str, Any]:
        return self.service._validation_report(phase, result, artifacts, context)

    def request_revision_or_finish(
        self,
        phase: str,
        request: OutlineDebateRunRequest,
        result: dict[str, Any],
        candidate_policy: dict[str, Any],
        state: dict[str, Any],
    ) -> list[dict[str, Any]]:
        decisions = self.service._build_decisions(phase, request, result, candidate_policy)
        for item in state.get("decisions", [])[:6]:
            decisions.append(
                {
                    "id": generate_id("dec"),
                    "phase": phase,
                    "title": "Agent 提议",
                    "decision": str(item.get("decision") or item.get("title") or item),
                    "rationale": f"来自 {item.get('agent_name', 'outline_debate')}",
                    "source_turn_id": item.get("turn_id", ""),
                }
            )
        return decisions

    def protocol(
        self,
        agenda: dict[str, Any],
        state: dict[str, Any],
        cross_review: dict[str, Any],
        validation_report: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "orchestrator": "OutlineDebateOrchestrator",
            "version": "1.0",
            "steps": list(self.steps),
            "agenda": agenda,
            "cross_review": cross_review,
            "validation_status": validation_report.get("status", ""),
            "state_id": state.get("id", ""),
        }


class OutlineDebateService:
    def create_session(self, db: Session, project_id: str, request: OutlineDebateSessionCreateRequest) -> dict[str, Any]:
        project = self._project(db, project_id)
        idempotency_key = request.idempotency_key or f"outline_debate:{project_id}:{generate_id('idem')}"
        existing = (
            db.query(models.GenerationJob)
            .filter(models.GenerationJob.project_id == project_id, models.GenerationJob.idempotency_key == idempotency_key)
            .first()
        )
        if existing:
            return {"session": self._session_from_job(existing), "job": serialize_job(existing)}
        provider = LLMProviderResolver(get_settings()).resolve(request.model)
        now = utcnow()
        session = {
            "id": "",
            "project_id": project_id,
            "status": "draft",
            "current_phase": "",
            "brief": request.brief,
            "phase_order": list(PHASE_ORDER),
            "phase_runs": {},
            "confirmed_candidates": {},
            "source": "outline_debate",
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }
        job = models.GenerationJob(
            id=generate_id("odb"),
            project_id=project_id,
            chapter_id=None,
            job_type="outline_debate_session",
            status="running",
            run_id=generate_id("run"),
            idempotency_key=idempotency_key,
            model=provider.model,
            request_json=dumps(
                {
                    "brief": request.brief,
                    "model": request.model,
                    "provider": provider.provider,
                    "has_api_key": bool(provider.api_key),
                    "project": serialize_project(project),
                }
            ),
            progress_json=dumps({"current_step": "created", "total_steps": 3, "completed_steps": 0, "message": "大纲议事会话已创建"}),
            current_agent="",
            started_at=now,
            heartbeat_at=now,
            result_json="",
        )
        session["id"] = job.id
        job.result_json = dumps({"session": session})
        db.add(job)
        db.commit()
        db.refresh(job)
        return {"session": self._session_from_job(job), "job": serialize_job(job)}

    def get_session(self, db: Session, project_id: str, session_id: str) -> dict[str, Any]:
        job = self._session_job(db, project_id, session_id)
        return {"session": self._session_from_job(job), "job": serialize_job(job)}

    def add_user_message(self, db: Session, project_id: str, session_id: str, request: OutlineDebateUserMessageRequest) -> dict[str, Any]:
        self._validate_phase(request.phase)
        job = self._session_job(db, project_id, session_id)
        session = self._session_from_job(job)
        target_agent_name = self._valid_agent_name(request.target_agent_name)
        mentions = self._extract_mentions(request.message, target_agent_name)
        user_message = {
            "id": generate_id("odm"),
            "phase": request.phase,
            "role": "user",
            "message": request.message,
            "target_agent_name": target_agent_name,
            "mentions": mentions,
            "created_at": utcnow().isoformat(),
            "handled_by_turn_id": "",
        }
        session.setdefault("messages", []).append(user_message)
        phase_runs = session.setdefault("phase_runs", {})
        phase_run = phase_runs.get(request.phase)
        if isinstance(phase_run, dict):
            phase_run.setdefault("user_messages", []).append(user_message)
            phase_run["status"] = "paused"
            phase_run["next_agent_name"] = target_agent_name or phase_run.get("next_agent_name", "")
        session["current_phase"] = request.phase
        session["status"] = "paused"
        session["updated_at"] = utcnow().isoformat()
        job.result_json = dumps({"session": session})
        job.progress_json = dumps(
            {
                "current_step": request.phase,
                "total_steps": 3,
                "completed_steps": len([run for run in phase_runs.values() if isinstance(run, dict) and run.get("status") == "succeeded"]),
                "message": "已保存用户议事意见，等待下一轮回应",
            }
        )
        job.heartbeat_at = utcnow()
        db.commit()
        db.refresh(job)
        return {"session": self._session_from_job(job), "message": user_message, "job": serialize_job(job)}

    def interrupt_session(self, db: Session, project_id: str, session_id: str, request: OutlineDebateInterruptRequest) -> dict[str, Any]:
        job = self._session_job(db, project_id, session_id)
        session = self._session_from_job(job)
        phase = request.phase or session.get("current_phase") or "book"
        self._validate_phase(phase)
        phase_run = session.setdefault("phase_runs", {}).get(phase)
        if isinstance(phase_run, dict):
            phase_run["status"] = "interrupted"
            phase_run["interrupted_at"] = utcnow().isoformat()
            phase_run["interrupt_reason"] = request.reason
            phase_run.setdefault("artifacts", [])
        session["status"] = "interrupted"
        session["current_phase"] = phase
        session["updated_at"] = utcnow().isoformat()
        session.setdefault("messages", []).append(
            {
                "id": generate_id("odm"),
                "phase": phase,
                "role": "system",
                "message": request.reason or "用户打断了当前议事。",
                "target_agent_name": "",
                "mentions": [],
                "created_at": utcnow().isoformat(),
                "event": "interrupt",
            }
        )
        job.current_agent = ""
        job.progress_json = dumps({"current_step": phase, "total_steps": 3, "completed_steps": 0, "message": "大纲议事已打断"})
        job.heartbeat_at = utcnow()
        job.result_json = dumps({"session": session})
        db.commit()
        db.refresh(job)
        return {"session": self._session_from_job(job), "job": serialize_job(job)}

    def run_phase(self, db: Session, project_id: str, session_id: str, phase: str, request: OutlineDebateRunRequest) -> dict[str, Any]:
        self._validate_phase(phase)
        job = self._session_job(db, project_id, session_id)
        project = self._project(db, project_id)
        session = self._session_from_job(job)
        self._ensure_upstream_confirmed(session, phase, request)
        if self._is_itemized_phase(phase):
            self._invalidate_item_confirmation(session, phase, self._item_key_for_request(phase, request))
        else:
            self._invalidate_confirmation_chain(session, phase)
        previous_phase_run = session["phase_runs"].get(phase)
        phase_run = self._build_phase_run(db, project, session, phase, request)
        if self._is_itemized_phase(phase):
            phase_run = self._merge_itemized_phase_run(previous_phase_run, phase_run, request)
        session["phase_runs"][phase] = phase_run
        session["current_phase"] = phase
        session["status"] = "succeeded" if set(session["phase_runs"]) == set(session["phase_order"]) else "in_progress"
        session["updated_at"] = utcnow().isoformat()
        job.result_json = dumps({"session": session})
        job.current_agent = phase_run["turns"][-1]["agent_name"] if phase_run["turns"] else ""
        job.heartbeat_at = utcnow()
        completed = len(session["phase_runs"])
        job.progress_json = dumps(
            {
                "current_step": phase,
                "total_steps": 3,
                "completed_steps": completed,
                "message": f"{PHASE_CONFIG[phase]['label']}已完成",
            }
        )
        if completed >= 3:
            job.status = "succeeded"
            job.finished_at = utcnow()
        self._record_turn_runs(db, job, phase_run)
        db.commit()
        db.refresh(job)
        return {"session": self._session_from_job(job), "phase_run": phase_run, "job": serialize_job(job)}

    def confirm_phase(self, db: Session, project_id: str, session_id: str, phase: str, request: OutlineDebateConfirmRequest) -> dict[str, Any]:
        self._validate_phase(phase)
        job = self._session_job(db, project_id, session_id)
        session = self._session_from_job(job)
        phase_run = session.get("phase_runs", {}).get(phase)
        if not isinstance(phase_run, dict) or phase_run.get("status") != "succeeded":
            raise _bad_request(f"请先形成{PHASE_CONFIG[phase]['result_title']}后再确认")
        if phase_run.get("candidate_status") == "stale":
            raise _bad_request(f"{PHASE_CONFIG[phase]['result_title']}已过期，请重新议事生成后再确认")
        result = phase_run.get("result") if isinstance(phase_run.get("result"), dict) else {}
        if not result:
            raise _bad_request(f"{PHASE_CONFIG[phase]['result_title']}缺少可确认结果")
        if self._is_itemized_phase(phase):
            return self._confirm_itemized_phase(db, project_id, job, session, phase, phase_run, result, request)
        self._ensure_upstream_confirmed(session, phase)
        was_already_confirmed = phase_run.get("candidate_status") == "confirmed"
        now = utcnow().isoformat()
        phase_run["candidate_status"] = "confirmed"
        phase_run["confirmed_at"] = now
        phase_run["confirmation"] = {"notes": request.notes, "confirmed_by": "user", "confirmed_at": now}
        result["candidate_status"] = "confirmed"
        result["confirmed_at"] = now
        result["requires_user_confirmation"] = False
        self._mark_primary_artifact_status(phase_run, "confirmed")
        materializations = self._materialize_phase_candidate_artifacts(db, project_id, job, phase_run, phase, request.notes)
        if materializations:
            phase_run["canon_materializations"] = materializations
            result["canon_materializations"] = materializations
            self._remember_candidate_materializations(session, phase, materializations)
        confirmed_candidates = session.setdefault("confirmed_candidates", {})
        confirmed_candidates[phase] = result
        book_commit = None
        if phase == "book" and not was_already_confirmed:
            book_commit = self._commit_confirmed_book_outline(db, project_id, result)
            commit_summary = {
                "status": "committed",
                "committed_at": now,
                "target": "story_bible",
                "story_bible_version": book_commit.get("story_bible", {}).get("version"),
            }
            phase_run["book_commit"] = commit_summary
            result["book_commit"] = commit_summary
        session["status"] = "confirmed" if set(confirmed_candidates) >= set(PHASE_ORDER) else "in_progress"
        session["current_phase"] = phase
        session["updated_at"] = now
        job.result_json = dumps({"session": session})
        job.progress_json = dumps(
            {
                "current_step": phase,
                "total_steps": len(PHASE_ORDER),
                "completed_steps": len(confirmed_candidates),
                "message": f"{PHASE_CONFIG[phase]['result_title']}已确认",
            }
        )
        job.heartbeat_at = utcnow()
        db.commit()
        db.refresh(job)
        session = self._session_from_job(job)
        payload = {"session": session, "phase_run": session["phase_runs"][phase], "job": serialize_job(job)}
        if book_commit is not None:
            payload["book_commit"] = book_commit
        return payload

    def commit_confirmed_candidates(self, db: Session, project_id: str, session_id: str, request: OutlineDebateCommitRequest) -> dict[str, Any]:
        self._project(db, project_id)
        job = self._session_job(db, project_id, session_id)
        session = self._session_from_job(job)
        confirmed_candidates = self._ensure_all_candidates_confirmed(session)
        book_outline_plan = self._book_outline_plan_from_confirmed_candidates(confirmed_candidates)
        chapter_outlines = self._chapter_outlines_from_confirmed_candidates(confirmed_candidates)

        from app.services.studio_service import studio_service

        book_commit = studio_service.commit_book_outline(db, project_id, BookOutlineCommitRequest(outline_plan=book_outline_plan))
        chapter_commit = studio_service.commit_chapter_outlines(
            db,
            project_id,
            ChapterOutlineCommitRequest(chapter_outlines=chapter_outlines, overwrite_existing=request.overwrite_existing_chapters),
        )

        now = utcnow().isoformat()
        incremental_updates = session.get("incremental_canon_updates") if isinstance(session.get("incremental_canon_updates"), dict) else {}
        session["status"] = "committed"
        session["formal_commit"] = {
            "status": "committed",
            "committed_at": now,
            "notes": request.notes,
            "source": "outline_debate",
            "book_volume_count": len(book_outline_plan.get("volume_outlines", [])),
            "chapter_count": len(chapter_outlines),
            "incremental_canon_updates": {
                "volumes": len(incremental_updates.get("volumes", [])) if isinstance(incremental_updates.get("volumes"), list) else 0,
                "chapters": len(incremental_updates.get("chapters", [])) if isinstance(incremental_updates.get("chapters"), list) else 0,
            },
            "writes": ["story_bible", "volumes", "chapters"],
            "pre_materialized_writes": session.get("candidate_canon_materializations", {}),
            "excluded_writes": ["graph_edges"],
        }
        session["updated_at"] = now
        job.result_json = dumps({"session": session})
        job.progress_json = dumps(
            {
                "current_step": "formal_commit",
                "total_steps": len(PHASE_ORDER),
                "completed_steps": len(PHASE_ORDER),
                "message": "已把确认候选写入正式大纲",
            }
        )
        job.status = "succeeded"
        job.current_agent = "outline_debate/formal_commit"
        job.heartbeat_at = utcnow()
        job.finished_at = utcnow()
        db.commit()
        db.refresh(job)
        return {
            "session": self._session_from_job(job),
            "book_commit": book_commit,
            "chapter_commit": chapter_commit,
            "job": serialize_job(job),
        }

    async def stream_phase(self, db: Session, project_id: str, session_id: str, phase: str, request: OutlineDebateRunRequest) -> Iterable[str]:
        if request.join_discussion or request.finish_phase:
            events = self.advance_phase_round(db, project_id, session_id, phase, request)
            for event_name, payload in events:
                if event_name == "turn":
                    async for block in self._stream_turn_event(phase, payload["turn"]):
                        yield block
                else:
                    yield _sse_block(event_name, payload)
                await asyncio.sleep(0)
            return
        self._validate_phase(phase)
        job = self._session_job(db, project_id, session_id)
        project = self._project(db, project_id)
        session = self._session_from_job(job)
        self._ensure_upstream_confirmed(session, phase, request)
        if self._is_itemized_phase(phase):
            self._invalidate_item_confirmation(session, phase, self._item_key_for_request(phase, request))
        else:
            self._invalidate_confirmation_chain(session, phase)
        previous_phase_run = session["phase_runs"].get(phase)
        yield _sse_block(
            "meta",
            {
                "type": "meta",
                "session_id": session_id,
                "phase": phase,
                "phase_label": PHASE_CONFIG[phase]["label"],
                "message": f"{PHASE_CONFIG[phase]['label']}开始流式回放",
            },
        )
        await asyncio.sleep(0)

        orchestrator = OutlineDebateOrchestrator(self)
        context = self._phase_context(db, project, session, phase, request)
        agenda = orchestrator.build_agenda(phase, request, context)
        deliberation_state = orchestrator.initial_state(agenda, request)
        turns: list[dict[str, Any]] = []
        for index, (agent_name, role) in enumerate(DEBATE_AGENTS, start=1):
            turn = self._build_turn(project, phase, request, context, agent_name, role, index, index, agenda, deliberation_state)
            turns.append(turn)
            orchestrator.apply_turn_to_state(deliberation_state, turn)
            next_agent_name = DEBATE_AGENTS[index][0] if index < len(DEBATE_AGENTS) else ""
            self._attach_turn_display(turn, next_agent_name)
            async for block in self._stream_turn_event(phase, turn):
                yield block
            await asyncio.sleep(0)

        cross_review = orchestrator.cross_review(deliberation_state, turns)
        result = orchestrator.synthesize_candidate_artifact(project, phase, request, turns, session, deliberation_state)
        artifacts, candidate_policy = self._build_artifacts(project, phase, request, result, turns)
        validation_report = orchestrator.validate_result(phase, result, artifacts, context)
        decisions = orchestrator.request_revision_or_finish(phase, request, result, candidate_policy, deliberation_state)
        topology = self._build_topology(phase, request, turns, decisions, artifacts)
        phase_run = self._mark_phase_run_pending(
            {
                "id": generate_id("odr"),
                "phase": phase,
                "phase_label": PHASE_CONFIG[phase]["label"],
                "status": "succeeded",
                "started_at": utcnow().isoformat(),
                "finished_at": utcnow().isoformat(),
                "input": request.model_dump(mode="json"),
                "agent_specs": self._agent_specs(),
                "candidate_policy": candidate_policy,
                "validation_report": validation_report,
                "turns": turns,
                "decisions": decisions,
                "artifacts": artifacts,
                "outline_topology": topology,
                "debate_protocol": orchestrator.protocol(agenda, deliberation_state, cross_review, validation_report),
                "deliberation_state": deliberation_state,
                "result": result,
            }
        )
        if self._is_itemized_phase(phase):
            phase_run = self._merge_itemized_phase_run(previous_phase_run, phase_run, request)
        session["phase_runs"][phase] = phase_run
        session["current_phase"] = phase
        session["status"] = "succeeded" if set(session["phase_runs"]) == set(session["phase_order"]) else "in_progress"
        session["updated_at"] = utcnow().isoformat()
        job.result_json = dumps({"session": session})
        job.current_agent = turns[-1]["agent_name"] if turns else ""
        job.heartbeat_at = utcnow()
        completed = len(session["phase_runs"])
        job.progress_json = dumps(
            {
                "current_step": phase,
                "total_steps": len(PHASE_ORDER),
                "completed_steps": completed,
                "message": f"{PHASE_CONFIG[phase]['label']}已完成",
            }
        )
        if completed >= len(PHASE_ORDER):
            job.status = "succeeded"
            job.finished_at = utcnow()
        self._record_turn_runs(db, job, phase_run)
        db.commit()
        db.refresh(job)
        session = self._session_from_job(job)
        phase_run = session["phase_runs"][phase]
        for decision in phase_run["decisions"]:
            yield _sse_block("decision", {"type": "decision", "phase": phase, "decision": decision})
            await asyncio.sleep(0)
        for artifact in phase_run["artifacts"]:
            yield _sse_block("artifact", {"type": "artifact", "phase": phase, "artifact": artifact})
            await asyncio.sleep(0)
        yield _sse_block("done", {"type": "done", "phase": phase, "phase_run": phase_run, "session": session})

    def advance_phase_round(
        self,
        db: Session,
        project_id: str,
        session_id: str,
        phase: str,
        request: OutlineDebateRunRequest,
    ) -> list[tuple[str, dict[str, Any]]]:
        self._validate_phase(phase)
        job = self._session_job(db, project_id, session_id)
        project = self._project(db, project_id)
        session = self._session_from_job(job)
        self._ensure_upstream_confirmed(session, phase, request)
        phase_run = self._load_or_create_round_phase_run(session, phase, request)
        if request.refresh_phase or not phase_run.get("turns"):
            if self._is_itemized_phase(phase):
                self._invalidate_item_confirmation(session, phase, self._item_key_for_request(phase, request))
            else:
                self._invalidate_confirmation_chain(session, phase)
        session["current_phase"] = phase
        session["status"] = "running"
        session["updated_at"] = utcnow().isoformat()
        events: list[tuple[str, dict[str, Any]]] = [
            (
                "meta",
                {
                    "type": "meta",
                    "session_id": session_id,
                    "phase": phase,
                    "phase_label": PHASE_CONFIG[phase]["label"],
                    "message": f"{PHASE_CONFIG[phase]['label']}回合制议事推进",
                },
            )
        ]
        if request.user_message.strip():
            user_request = OutlineDebateUserMessageRequest(phase=phase, message=request.user_message, target_agent_name=request.target_agent_name)
            message = self._append_user_message_to_session(session, user_request)
            events.append(("user_message", {"type": "user_message", "phase": phase, "message": message, "session": session}))
        if request.finish_phase:
            self._finalize_round_phase(db, job, project, session, phase, request, phase_run)
            events.extend(("decision", {"type": "decision", "phase": phase, "decision": decision}) for decision in phase_run["decisions"])
            events.extend(("artifact", {"type": "artifact", "phase": phase, "artifact": artifact}) for artifact in phase_run["artifacts"])
            events.append(("done", {"type": "done", "phase": phase, "phase_run": phase_run, "session": session}))
            db.commit()
            db.refresh(job)
            return events

        next_agent_name = self._next_round_agent_name(phase_run)
        if not next_agent_name:
            self._finalize_round_phase(db, job, project, session, phase, request, phase_run)
            events.extend(("decision", {"type": "decision", "phase": phase, "decision": decision}) for decision in phase_run["decisions"])
            events.extend(("artifact", {"type": "artifact", "phase": phase, "artifact": artifact}) for artifact in phase_run["artifacts"])
            events.append(("done", {"type": "done", "phase": phase, "phase_run": phase_run, "session": session}))
            db.commit()
            db.refresh(job)
            return events

        orchestrator = OutlineDebateOrchestrator(self)
        context = self._phase_context(db, project, session, phase, request)
        agenda = phase_run.get("agenda") if isinstance(phase_run.get("agenda"), dict) else orchestrator.build_agenda(phase, request, context)
        deliberation_state = phase_run.get("deliberation_state") if isinstance(phase_run.get("deliberation_state"), dict) else orchestrator.initial_state(agenda, request)
        agent_index = next((index for index, (agent_name, _role) in enumerate(DEBATE_AGENTS, start=1) if agent_name == next_agent_name), len(phase_run["turns"]) + 1)
        role = dict(DEBATE_AGENTS)[next_agent_name]
        turn = self._build_turn(project, phase, request, context, next_agent_name, role, len(phase_run["turns"]) + 1, agent_index, agenda, deliberation_state)
        phase_run.setdefault("turns", []).append(turn)
        orchestrator.apply_turn_to_state(deliberation_state, turn)
        self._mark_target_message_handled(phase_run, turn)
        phase_run["status"] = "paused"
        phase_run["next_agent_name"] = self._next_round_agent_name(phase_run)
        self._attach_turn_display(turn, phase_run["next_agent_name"])
        phase_run["agenda"] = agenda
        phase_run["deliberation_state"] = deliberation_state
        phase_run["outline_topology"] = self._build_topology(phase, request, phase_run["turns"], phase_run.get("decisions", []), phase_run.get("artifacts", []))
        session["status"] = "paused"
        session["updated_at"] = utcnow().isoformat()
        job.current_agent = next_agent_name
        job.heartbeat_at = utcnow()
        job.progress_json = dumps(
            {
                "current_step": phase,
                "total_steps": 3,
                "completed_steps": len([run for run in session.get("phase_runs", {}).values() if isinstance(run, dict) and run.get("status") == "succeeded"]),
                "message": f"{role}已发言，等待用户继续",
            }
        )
        job.result_json = dumps({"session": session})
        self._record_single_turn_run(db, job, phase_run, turn)
        db.commit()
        db.refresh(job)
        session = self._session_from_job(job)
        phase_run = session["phase_runs"][phase]
        events.append(("turn", {"type": "turn", "phase": phase, "turn": turn}))
        events.append(
            (
                "pause",
                {
                    "type": "pause",
                    "phase": phase,
                    "message": "当前 Agent 发言完成，等待用户继续或发表意见。",
                    "next_agent_name": phase_run.get("next_agent_name", ""),
                    "phase_run": phase_run,
                    "session": session,
                },
            )
        )
        return events

    def _validate_phase(self, phase: str) -> None:
        if phase not in PHASE_CONFIG:
            raise _bad_request("大纲议事阶段必须是 book、volumes 或 chapters")

    def _is_itemized_phase(self, phase: str) -> bool:
        return phase in {"volumes", "chapters"}

    def _target_volume_no(self, request: OutlineDebateRunRequest | None) -> int:
        if request is None:
            return 1
        if request.target_volume_no:
            return int(request.target_volume_no)
        if request.chapter_ranges:
            return int(request.chapter_ranges[0].volume_no)
        return 1

    def _target_chapter_no(self, request: OutlineDebateRunRequest | None) -> int:
        if request is None:
            return 1
        if request.target_chapter_no:
            return int(request.target_chapter_no)
        if request.chapter_ranges:
            return int(request.chapter_ranges[0].start_chapter_no)
        return 1

    def _item_key_for_request(self, phase: str, request: OutlineDebateRunRequest) -> str:
        if phase == "volumes":
            return f"volume:{self._target_volume_no(request)}"
        if phase == "chapters":
            return f"chapter:{self._target_chapter_no(request)}"
        return phase

    def _item_list_key(self, phase: str) -> str:
        return "volume_outlines" if phase == "volumes" else "chapter_outlines"

    def _item_no_field(self, phase: str) -> str:
        return "volume_no" if phase == "volumes" else "chapter_no"

    def _item_key_for_candidate(self, phase: str, item: dict[str, Any]) -> str:
        prefix = "volume" if phase == "volumes" else "chapter"
        number = int(item.get(self._item_no_field(phase)) or 1)
        return f"{prefix}:{number}"

    def _expected_item_count(self, phase: str, request: OutlineDebateRunRequest) -> int:
        if phase == "volumes":
            return max(1, int(request.volume_count or 1))
        return max(1, len(self._chapter_candidates_for_request(request)) or 1)

    def _chapter_candidates_for_request(self, request: OutlineDebateRunRequest) -> list[tuple[int, int]]:
        if request.target_chapter_no:
            return [(self._target_volume_no(request), self._target_chapter_no(request))]
        if request.chapter_ranges:
            first = request.chapter_ranges[0]
            return [(int(first.volume_no), int(first.start_chapter_no))]
        return [(1, 1)]

    def _refresh_confirmation_items(self, phase_run: dict[str, Any], request: OutlineDebateRunRequest | None = None) -> dict[str, Any]:
        phase = phase_run["phase"]
        if not self._is_itemized_phase(phase):
            return phase_run
        result = phase_run.get("result") if isinstance(phase_run.get("result"), dict) else {}
        list_key = self._item_list_key(phase)
        candidates = result.get(list_key) if isinstance(result.get(list_key), list) else []
        existing_by_key = {
            str(item.get("item_key")): item
            for item in phase_run.get("confirmation_items", [])
            if isinstance(item, dict) and item.get("item_key")
        }
        refreshed: list[dict[str, Any]] = []
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            item_key = self._item_key_for_candidate(phase, candidate)
            previous = existing_by_key.get(item_key, {})
            status = str(candidate.get("candidate_status") or previous.get("candidate_status") or "pending_confirmation")
            number = int(candidate.get(self._item_no_field(phase)) or 1)
            refreshed.append(
                {
                    "item_key": item_key,
                    "phase": phase,
                    "candidate_status": status,
                    self._item_no_field(phase): number,
                    "title": str(candidate.get("title") or previous.get("title") or item_key),
                    "confirmed_at": candidate.get("confirmed_at") or previous.get("confirmed_at") or "",
                    "canon_update": candidate.get("canon_update") or previous.get("canon_update") or {},
                }
            )
        phase_run["confirmation_items"] = refreshed
        phase_run["expected_item_count"] = max(
            int(phase_run.get("expected_item_count") or 0),
            self._expected_item_count(phase, request) if request is not None else len(refreshed),
            len(refreshed),
        )
        phase_run["candidate_status"] = self._derive_itemized_candidate_status(phase_run)
        result["candidate_status"] = phase_run["candidate_status"]
        result["requires_user_confirmation"] = phase_run["candidate_status"] != "confirmed"
        return phase_run

    def _derive_itemized_candidate_status(self, phase_run: dict[str, Any]) -> str:
        items = [item for item in phase_run.get("confirmation_items", []) if isinstance(item, dict)]
        if not items:
            return "pending_confirmation"
        if any(item.get("candidate_status") == "stale" for item in items):
            return "stale"
        if any(item.get("candidate_status") == "pending_confirmation" for item in items):
            return "pending_confirmation"
        confirmed_count = len([item for item in items if item.get("candidate_status") == "confirmed"])
        expected = max(1, int(phase_run.get("expected_item_count") or len(items)))
        return "confirmed" if confirmed_count >= expected and len(items) >= expected else "partially_confirmed"

    def _ensure_upstream_confirmed(self, session: dict[str, Any], phase: str, request: OutlineDebateRunRequest | None = None) -> None:
        upstream = PHASE_UPSTREAM_LABELS.get(phase)
        if not upstream:
            return
        upstream_phase, upstream_label = upstream
        if phase == "chapters":
            volume_no = self._target_volume_no(request) if request is not None else 1
            volumes_candidate = session.get("confirmed_candidates", {}).get("volumes")
            volume_outlines = volumes_candidate.get("volume_outlines") if isinstance(volumes_candidate, dict) and isinstance(volumes_candidate.get("volume_outlines"), list) else []
            if any(int(item.get("volume_no") or 0) == volume_no for item in volume_outlines if isinstance(item, dict)):
                return
            raise _bad_request(f"请先确认第{volume_no}卷卷纲候选，再进入{PHASE_CONFIG[phase]['label']}")
        upstream_run = session.get("phase_runs", {}).get(upstream_phase)
        if not isinstance(upstream_run, dict) or upstream_run.get("candidate_status") != "confirmed":
            raise _bad_request(f"请先确认{upstream_label}候选，再进入{PHASE_CONFIG[phase]['label']}")

    def _ensure_all_candidates_confirmed(self, session: dict[str, Any]) -> dict[str, dict[str, Any]]:
        confirmed_candidates = session.setdefault("confirmed_candidates", {})
        if not isinstance(confirmed_candidates, dict):
            confirmed_candidates = {}
        phase_runs = session.get("phase_runs") if isinstance(session.get("phase_runs"), dict) else {}
        for phase in PHASE_ORDER:
            phase_run = phase_runs.get(phase)
            confirmed = confirmed_candidates.get(phase)
            if not isinstance(phase_run, dict) or phase_run.get("candidate_status") != "confirmed" or not isinstance(confirmed, dict):
                raise _bad_request(f"请先确认{PHASE_CONFIG[phase]['result_title']}，再写入正式大纲")
        return {phase: confirmed_candidates[phase] for phase in PHASE_ORDER}

    def _confirm_itemized_phase(
        self,
        db: Session,
        project_id: str,
        job: models.GenerationJob,
        session: dict[str, Any],
        phase: str,
        phase_run: dict[str, Any],
        result: dict[str, Any],
        request: OutlineDebateConfirmRequest,
    ) -> dict[str, Any]:
        self._ensure_upstream_confirmed(session, phase, self._request_from_phase_run(phase_run))
        item_key = request.item_key or self._first_pending_item_key(phase_run)
        if not item_key:
            raise _bad_request(f"{PHASE_CONFIG[phase]['result_title']}缺少待确认条目")
        item = self._candidate_item_by_key(phase_run, item_key)
        if item is None:
            raise _bad_request(f"未找到可确认条目：{item_key}")
        if item.get("candidate_status") == "stale":
            raise _bad_request(f"{item_key} 已过期，请重新议事生成后再确认")

        canon_update = self._commit_outline_item_to_canon(db, project_id, job, phase, item, request.notes)
        materializations = self._materialize_phase_candidate_artifacts(
            db,
            project_id,
            job,
            phase_run,
            phase,
            request.notes,
            source_chapter_id=canon_update.get("ref_id") if canon_update.get("ref_type") == "chapter" else None,
        )
        now = utcnow().isoformat()
        item["candidate_status"] = "confirmed"
        item["confirmed_at"] = now
        item["requires_user_confirmation"] = False
        item["canon_update"] = canon_update
        if materializations:
            item["canon_materializations"] = materializations
            canon_update["candidate_materializations"] = materializations
            phase_run["canon_materializations"] = materializations
            self._remember_candidate_materializations(session, phase, materializations)
        for confirmation_item in phase_run.get("confirmation_items", []):
            if isinstance(confirmation_item, dict) and confirmation_item.get("item_key") == item_key:
                confirmation_item["candidate_status"] = "confirmed"
                confirmation_item["confirmed_at"] = now
                confirmation_item["canon_update"] = canon_update
        self._upsert_confirmed_item(session, phase, item)
        self._refresh_confirmation_items(phase_run)
        if phase_run["candidate_status"] == "confirmed":
            phase_run["confirmed_at"] = now
        phase_run["last_confirmed_item_key"] = item_key
        phase_run["last_canon_update"] = canon_update
        result["candidate_status"] = phase_run["candidate_status"]
        result["requires_user_confirmation"] = phase_run["candidate_status"] != "confirmed"
        self._mark_primary_artifact_status(phase_run, phase_run["candidate_status"])
        confirmed_candidates = session.setdefault("confirmed_candidates", {})
        if self._all_phase_candidates_confirmed(session):
            session["status"] = "confirmed"
        else:
            session["status"] = "in_progress"
        session.setdefault("incremental_canon_updates", {}).setdefault(phase, [])
        session["incremental_canon_updates"][phase].append(canon_update)
        session["current_phase"] = phase
        session["updated_at"] = now
        job.result_json = dumps({"session": session})
        job.progress_json = dumps(
            {
                "current_step": phase,
                "total_steps": len(PHASE_ORDER),
                "completed_steps": len([key for key in PHASE_ORDER if key in confirmed_candidates]),
                "message": f"{PHASE_CONFIG[phase]['result_title']}条目已确认并更新正典",
            }
        )
        job.heartbeat_at = utcnow()
        db.commit()
        db.refresh(job)
        session = self._session_from_job(job)
        return {"session": session, "phase_run": session["phase_runs"][phase], "canon_update": canon_update, "job": serialize_job(job)}

    def _request_from_phase_run(self, phase_run: dict[str, Any]) -> OutlineDebateRunRequest:
        payload = phase_run.get("input") if isinstance(phase_run.get("input"), dict) else {}
        return OutlineDebateRunRequest(**payload)

    def _first_pending_item_key(self, phase_run: dict[str, Any]) -> str:
        for item in phase_run.get("confirmation_items", []):
            if isinstance(item, dict) and item.get("candidate_status") == "pending_confirmation":
                return str(item.get("item_key") or "")
        for item in phase_run.get("confirmation_items", []):
            if isinstance(item, dict):
                return str(item.get("item_key") or "")
        return ""

    def _candidate_item_by_key(self, phase_run: dict[str, Any], item_key: str) -> dict[str, Any] | None:
        phase = phase_run["phase"]
        result = phase_run.get("result") if isinstance(phase_run.get("result"), dict) else {}
        values = result.get(self._item_list_key(phase)) if isinstance(result.get(self._item_list_key(phase)), list) else []
        for item in values:
            if isinstance(item, dict) and self._item_key_for_candidate(phase, item) == item_key:
                return item
        return None

    def _commit_outline_item_to_canon(
        self,
        db: Session,
        project_id: str,
        job: models.GenerationJob,
        phase: str,
        item: dict[str, Any],
        notes: str,
    ) -> dict[str, Any]:
        from app.services.studio_service import studio_service

        project = self._project(db, project_id)
        if phase == "volumes":
            volume_no = int(item.get("volume_no") or 1)
            volume = db.query(models.Volume).filter(models.Volume.project_id == project_id, models.Volume.volume_no == volume_no).first()
            if volume is None:
                volume = models.Volume(id=generate_id("vol"), project_id=project_id, volume_no=volume_no, title=str(item.get("title") or f"第{volume_no}卷"), sort_order=volume_no)
                db.add(volume)
            volume.title = str(item.get("title") or volume.title)
            volume.outline = studio_service._format_dynamic_volume_outline_text(item)
            volume.status = "active"
            volume.sort_order = volume_no
            db.flush()
            version = studio_service._sync_canon_ref(
                db,
                project_id,
                "volume",
                volume,
                source_job_id=job.id,
                source_agent="outline_debate/StructureDoctorAgent",
                change_reason=notes or f"确认第{volume_no}卷卷纲",
            )
            return {
                "ref_type": "volume",
                "ref_id": volume.id,
                "version_id": version.id,
                "version_no": version.version_no,
                "title": volume.title,
                "volume_no": volume_no,
            }

        chapters = studio_service._persist_chapter_outline_candidates(db, project, [item], job.id, True)
        chapter = chapters[0]
        db.flush()
        version = studio_service._sync_canon_ref(
            db,
            project_id,
            "chapter",
            chapter,
            source_chapter_id=chapter.id,
            source_job_id=job.id,
            source_agent="outline_debate/ContinuityAuditorAgent",
            change_reason=notes or f"确认第{chapter.chapter_no}章章纲",
        )
        return {
            "ref_type": "chapter",
            "ref_id": chapter.id,
            "version_id": version.id,
            "version_no": version.version_no,
            "title": chapter.title,
            "volume_no": chapter.volume_no,
            "chapter_no": chapter.chapter_no,
        }

    def _materialize_phase_candidate_artifacts(
        self,
        db: Session,
        project_id: str,
        job: models.GenerationJob,
        phase_run: dict[str, Any],
        phase: str,
        notes: str,
        *,
        source_chapter_id: str | None = None,
    ) -> list[dict[str, Any]]:
        from app.services.studio_service import studio_service

        materializations: list[dict[str, Any]] = []
        for artifact in phase_run.get("artifacts", []):
            if not isinstance(artifact, dict) or artifact.get("type") not in {"character_candidate", "setting_candidate"}:
                continue
            existing_materialization = artifact.get("materialization") if isinstance(artifact.get("materialization"), dict) else None
            if existing_materialization and existing_materialization.get("ref_id"):
                materializations.append(existing_materialization)
                continue
            payload = artifact.get("payload") if isinstance(artifact.get("payload"), dict) else {}
            if not payload:
                continue
            if artifact.get("type") == "character_candidate":
                materialization = self._materialize_character_candidate(db, project_id, job, phase, payload, notes, source_chapter_id, studio_service)
            else:
                materialization = self._materialize_setting_candidate(db, project_id, job, phase, payload, notes, source_chapter_id, studio_service)
            if not materialization:
                continue
            materialization = {**materialization, "artifact_id": artifact.get("id"), "artifact_type": artifact.get("type")}
            artifact["materialization"] = materialization
            artifact["requires_user_confirmation"] = False
            payload["activity_status"] = "active"
            payload["status"] = "committed"
            payload["materialized_ref"] = {"ref_type": materialization["ref_type"], "ref_id": materialization["ref_id"]}
            suggestion = payload.get("canon_write_suggestion") if isinstance(payload.get("canon_write_suggestion"), dict) else {}
            suggestion.update(
                {
                    "requires_user_approval": False,
                    "approved_by": "outline_candidate_confirmation",
                    "materialized": True,
                    "ref_type": materialization["ref_type"],
                    "ref_id": materialization["ref_id"],
                }
            )
            payload["canon_write_suggestion"] = suggestion
            materializations.append(materialization)
        if materializations:
            phase_run["canon_materializations"] = materializations
        return materializations

    def _remember_candidate_materializations(self, session: dict[str, Any], phase: str, materializations: list[dict[str, Any]]) -> None:
        buckets = session.setdefault("candidate_canon_materializations", {})
        if not isinstance(buckets, dict):
            buckets = {}
            session["candidate_canon_materializations"] = buckets
        bucket = buckets.setdefault(phase, [])
        if not isinstance(bucket, list):
            bucket = []
            buckets[phase] = bucket
        seen = {(item.get("artifact_id"), item.get("ref_type"), item.get("ref_id")) for item in bucket if isinstance(item, dict)}
        for materialization in materializations:
            key = (materialization.get("artifact_id"), materialization.get("ref_type"), materialization.get("ref_id"))
            if key not in seen:
                bucket.append(materialization)
                seen.add(key)

    def _materialize_character_candidate(
        self,
        db: Session,
        project_id: str,
        job: models.GenerationJob,
        phase: str,
        payload: dict[str, Any],
        notes: str,
        source_chapter_id: str | None,
        studio_service: Any,
    ) -> dict[str, Any]:
        name = self._string_or(payload.get("name"), "未命名角色")
        existing = db.query(models.Character).filter(models.Character.project_id == project_id, models.Character.name == name).first()
        if existing:
            return {
                "status": "reused",
                "action": "reused",
                "ref_type": "character",
                "ref_id": existing.id,
                "title": existing.name,
                "reason": "同名角色已存在，确认时复用正式角色。",
            }
        role_type = self._string_or(payload.get("role_type") or payload.get("role"), "supporting")
        importance_score = self._bounded_int(payload.get("importance_score"), 50, 0, 100)
        row = models.Character(
            id=generate_id("chr"),
            project_id=project_id,
            name=name,
            aliases_json=dumps(self._list_of_clean_strings(payload.get("aliases"))),
            role=role_type,
            role_type=role_type,
            importance_level=self._string_or(payload.get("importance_level"), "medium"),
            importance_score=importance_score,
            summary=self._string_or(payload.get("summary") or payload.get("profile") or payload.get("story_function"), ""),
            appearance=self._string_or(payload.get("appearance"), ""),
            personality=self._string_or(payload.get("personality"), ""),
            goals_json=dumps(self._list_of_clean_strings(payload.get("goals"))),
            motivations_json=dumps(self._list_of_clean_strings(payload.get("motivations"))),
            secrets_json=dumps(self._list_of_clean_strings(payload.get("secrets"))),
            abilities_json=dumps(self._list_of_clean_strings(payload.get("abilities"))),
            weaknesses_json=dumps(self._list_of_clean_strings(payload.get("weaknesses"))),
            character_arc=self._string_or(payload.get("character_arc") or payload.get("arc"), ""),
            current_status=self._string_or(payload.get("current_status"), "active"),
            first_appearance_chapter_id=source_chapter_id,
            last_seen_chapter_id=source_chapter_id,
            related_entity_ids_json=dumps(self._list_of_clean_strings(payload.get("related_entity_ids"))),
            related_character_ids_json=dumps(self._list_of_clean_strings(payload.get("related_character_ids"))),
            relations_json=dumps(payload.get("relationship_hooks") if isinstance(payload.get("relationship_hooks"), list) else []),
            updated_reason=notes or f"确认{PHASE_CONFIG[phase]['result_title']}时自动入库",
            source="outline_debate",
            status="active",
        )
        db.add(row)
        db.flush()
        studio_service._ensure_graph_node(db, project_id, "character", row.id, row.name, row.importance_level, row.importance_score)
        version = studio_service._sync_canon_ref(
            db,
            project_id,
            "character",
            row,
            source_chapter_id=source_chapter_id,
            source_job_id=job.id,
            source_agent="outline_debate/CharacterGeneratorAgent",
            change_reason=notes or f"确认{PHASE_CONFIG[phase]['result_title']}角色候选",
            confidence=self._bounded_float(payload.get("confidence"), 0.8, 0.0, 1.0),
        )
        return {
            "status": "materialized",
            "action": "created",
            "ref_type": "character",
            "ref_id": row.id,
            "version_id": version.id,
            "version_no": version.version_no,
            "title": row.name,
        }

    def _materialize_setting_candidate(
        self,
        db: Session,
        project_id: str,
        job: models.GenerationJob,
        phase: str,
        payload: dict[str, Any],
        notes: str,
        source_chapter_id: str | None,
        studio_service: Any,
    ) -> dict[str, Any]:
        target = self._setting_candidate_target(payload)
        if target == "entity":
            return self._materialize_entity_candidate(db, project_id, job, phase, payload, notes, source_chapter_id, studio_service)
        return self._materialize_world_fact_candidate(db, project_id, job, phase, payload, notes, source_chapter_id, studio_service)

    def _materialize_entity_candidate(
        self,
        db: Session,
        project_id: str,
        job: models.GenerationJob,
        phase: str,
        payload: dict[str, Any],
        notes: str,
        source_chapter_id: str | None,
        studio_service: Any,
    ) -> dict[str, Any]:
        entity_type = self._string_or(payload.get("entity_type") or payload.get("category"), "item")
        name = self._string_or(payload.get("name") or payload.get("title"), "未命名实体")
        existing = (
            db.query(models.StoryEntity)
            .filter(models.StoryEntity.project_id == project_id, models.StoryEntity.entity_type == entity_type, models.StoryEntity.name == name)
            .first()
        )
        if existing:
            return {
                "status": "reused",
                "action": "reused",
                "ref_type": "entity",
                "ref_id": existing.id,
                "title": existing.name,
                "reason": "同名同类型实体已存在，确认时复用正式实体。",
            }
        importance_score = self._bounded_int(payload.get("importance_score"), 50, 0, 100)
        row = models.StoryEntity(
            id=generate_id("ent"),
            project_id=project_id,
            entity_type=entity_type,
            name=name,
            importance_level=self._string_or(payload.get("importance_level"), "medium"),
            importance_score=importance_score,
            description=self._string_or(payload.get("description") or payload.get("content") or payload.get("conflict_utility"), ""),
            current_status=self._string_or(payload.get("current_status"), "active"),
            source="outline_debate",
            first_appearance_chapter_id=source_chapter_id,
            last_seen_chapter_id=source_chapter_id,
        )
        db.add(row)
        db.flush()
        studio_service._ensure_graph_node(db, project_id, "entity", row.id, row.name, row.importance_level, row.importance_score)
        version = studio_service._sync_canon_ref(
            db,
            project_id,
            "entity",
            row,
            source_chapter_id=source_chapter_id,
            source_job_id=job.id,
            source_agent="outline_debate/SettingGeneratorAgent",
            change_reason=notes or f"确认{PHASE_CONFIG[phase]['result_title']}设定候选",
            confidence=self._bounded_float(payload.get("confidence"), 0.8, 0.0, 1.0),
        )
        return {
            "status": "materialized",
            "action": "created",
            "ref_type": "entity",
            "ref_id": row.id,
            "version_id": version.id,
            "version_no": version.version_no,
            "title": row.name,
        }

    def _materialize_world_fact_candidate(
        self,
        db: Session,
        project_id: str,
        job: models.GenerationJob,
        phase: str,
        payload: dict[str, Any],
        notes: str,
        source_chapter_id: str | None,
        studio_service: Any,
    ) -> dict[str, Any]:
        title = self._string_or(payload.get("title") or payload.get("name"), "未命名世界观事实")
        existing = db.query(models.WorldFact).filter(models.WorldFact.project_id == project_id, models.WorldFact.title == title).first()
        if existing:
            return {
                "status": "reused",
                "action": "reused",
                "ref_type": "world_fact",
                "ref_id": existing.id,
                "title": existing.title,
                "reason": "同名世界观事实已存在，确认时复用正式世界观事实。",
            }
        importance_score = self._bounded_int(payload.get("importance_score"), 50, 0, 100)
        row = models.WorldFact(
            id=generate_id("wld"),
            project_id=project_id,
            category=self._string_or(payload.get("category"), "rule"),
            title=title,
            content=self._string_or(payload.get("content") or payload.get("conflict_utility"), ""),
            importance_level=self._string_or(payload.get("importance_level"), "medium"),
            importance_score=importance_score,
            confidence=self._bounded_float(payload.get("confidence"), 0.8, 0.0, 1.0),
            source_chapter_id=source_chapter_id,
            related_entity_ids_json=dumps(self._list_of_clean_strings(payload.get("related_entity_ids"))),
        )
        db.add(row)
        db.flush()
        studio_service._ensure_graph_node(db, project_id, "world_fact", row.id, row.title, row.importance_level, row.importance_score)
        version = studio_service._sync_canon_ref(
            db,
            project_id,
            "world_fact",
            row,
            source_chapter_id=source_chapter_id,
            source_job_id=job.id,
            source_agent="outline_debate/SettingGeneratorAgent",
            change_reason=notes or f"确认{PHASE_CONFIG[phase]['result_title']}设定候选",
            confidence=row.confidence,
        )
        return {
            "status": "materialized",
            "action": "created",
            "ref_type": "world_fact",
            "ref_id": row.id,
            "version_id": version.id,
            "version_no": version.version_no,
            "title": row.title,
        }

    def _setting_candidate_target(self, payload: dict[str, Any]) -> str:
        suggestion = payload.get("canon_write_suggestion") if isinstance(payload.get("canon_write_suggestion"), dict) else {}
        raw = str(payload.get("ref_type") or suggestion.get("target") or "").strip().lower()
        if raw in {"entity", "entities", "story_entity", "story_entities"} or payload.get("entity_type"):
            return "entity"
        return "world_fact"

    def _list_of_clean_strings(self, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()]

    def _bounded_int(self, value: Any, fallback: int, minimum: int, maximum: int) -> int:
        try:
            number = int(value)
        except (TypeError, ValueError):
            number = fallback
        return max(minimum, min(maximum, number))

    def _bounded_float(self, value: Any, fallback: float, minimum: float, maximum: float) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            number = fallback
        return max(minimum, min(maximum, number))

    def _upsert_confirmed_item(self, session: dict[str, Any], phase: str, item: dict[str, Any]) -> None:
        confirmed_candidates = session.setdefault("confirmed_candidates", {})
        phase_candidate = confirmed_candidates.setdefault(
            phase,
            {
                "generation_kind": PHASE_CONFIG[phase]["generation_kind"],
                self._item_list_key(phase): [],
                "requires_user_confirmation": False,
                "candidate_status": "partially_confirmed",
            },
        )
        list_key = self._item_list_key(phase)
        id_field = self._item_no_field(phase)
        values = phase_candidate.get(list_key)
        if not isinstance(values, list):
            values = []
        number = int(item.get(id_field) or 1)
        replaced = False
        next_values: list[dict[str, Any]] = []
        for value in values:
            if isinstance(value, dict) and int(value.get(id_field) or 0) == number:
                next_values.append(dict(item))
                replaced = True
            elif isinstance(value, dict):
                next_values.append(value)
        if not replaced:
            next_values.append(dict(item))
        phase_candidate[list_key] = sorted(next_values, key=lambda value: int(value.get(id_field) or 0))
        phase_candidate["candidate_status"] = "confirmed"
        phase_candidate["requires_user_confirmation"] = False

    def _all_phase_candidates_confirmed(self, session: dict[str, Any]) -> bool:
        phase_runs = session.get("phase_runs") if isinstance(session.get("phase_runs"), dict) else {}
        confirmed_candidates = session.get("confirmed_candidates") if isinstance(session.get("confirmed_candidates"), dict) else {}
        for phase in PHASE_ORDER:
            phase_run = phase_runs.get(phase)
            if not isinstance(phase_run, dict) or phase_run.get("candidate_status") != "confirmed" or phase not in confirmed_candidates:
                return False
        return True

    def _merge_itemized_phase_run(
        self,
        previous_phase_run: Any,
        next_phase_run: dict[str, Any],
        request: OutlineDebateRunRequest,
    ) -> dict[str, Any]:
        phase = next_phase_run["phase"]
        self._refresh_confirmation_items(next_phase_run, request)
        if not isinstance(previous_phase_run, dict) or previous_phase_run.get("phase") != phase:
            next_phase_run["item_runs"] = [
                {
                    "id": next_phase_run["id"],
                    "item_key": self._item_key_for_request(phase, request),
                    "candidate_status": "pending_confirmation",
                    "started_at": next_phase_run.get("started_at", ""),
                    "finished_at": next_phase_run.get("finished_at", ""),
                }
            ]
            return next_phase_run

        list_key = self._item_list_key(phase)
        id_field = self._item_no_field(phase)
        previous_result = previous_phase_run.get("result") if isinstance(previous_phase_run.get("result"), dict) else {}
        next_result = next_phase_run.get("result") if isinstance(next_phase_run.get("result"), dict) else {}
        merged_by_number: dict[int, dict[str, Any]] = {}
        for source in (previous_result.get(list_key), next_result.get(list_key)):
            if not isinstance(source, list):
                continue
            for item in source:
                if not isinstance(item, dict):
                    continue
                merged_by_number[int(item.get(id_field) or 1)] = dict(item)
        next_result[list_key] = [merged_by_number[number] for number in sorted(merged_by_number)]
        next_phase_run["result"] = next_result

        previous_items = {
            str(item.get("item_key")): item
            for item in previous_phase_run.get("confirmation_items", [])
            if isinstance(item, dict) and item.get("item_key")
        }
        self._refresh_confirmation_items(next_phase_run, request)
        for item in next_phase_run.get("confirmation_items", []):
            if not isinstance(item, dict):
                continue
            previous = previous_items.get(str(item.get("item_key")))
            if previous and item.get("candidate_status") != "pending_confirmation":
                item.update(previous)
        next_phase_run["expected_item_count"] = max(
            int(previous_phase_run.get("expected_item_count") or 0),
            int(next_phase_run.get("expected_item_count") or 0),
            self._expected_item_count(phase, request),
        )
        next_phase_run["item_runs"] = [
            *[item for item in previous_phase_run.get("item_runs", []) if isinstance(item, dict)],
            {
                "id": next_phase_run["id"],
                "item_key": self._item_key_for_request(phase, request),
                "candidate_status": "pending_confirmation",
                "started_at": next_phase_run.get("started_at", ""),
                "finished_at": next_phase_run.get("finished_at", ""),
            },
        ]
        return self._refresh_confirmation_items(next_phase_run, request)

    def _commit_confirmed_book_outline(self, db: Session, project_id: str, book_candidate: dict[str, Any]) -> dict[str, Any]:
        from app.services.studio_service import studio_service

        return studio_service.commit_book_outline(db, project_id, BookOutlineCommitRequest(outline_plan=self._book_outline_plan_from_book_candidate(book_candidate)))

    def _book_outline_plan_from_book_candidate(self, book_candidate: dict[str, Any]) -> dict[str, Any]:
        book_outline = book_candidate.get("book_outline") if isinstance(book_candidate.get("book_outline"), dict) else {}
        if not book_outline:
            raise _bad_request("总纲候选缺少 book_outline，无法写入正式大纲")
        normalized_book_outline = self._normalize_book_outline_for_commit(book_outline)
        return {
            **{
                key: value
                for key, value in book_candidate.items()
                if key not in {"generation_kind", "book_outline", "volume_outlines", "requires_user_confirmation", "candidate_status"}
            },
            "generation_kind": "book_outline",
            "source": "outline_debate",
            "requires_user_confirmation": False,
            "candidate_status": "committed",
            "book_outline": normalized_book_outline,
            "volume_outlines": [],
            "parameters": {},
        }

    def _normalize_book_outline_for_commit(self, book_outline: dict[str, Any]) -> dict[str, Any]:
        normalized_book_outline = dict(book_outline)
        main_conflict = str(normalized_book_outline.get("main_conflict") or normalized_book_outline.get("core_conflict") or "")
        if main_conflict and not normalized_book_outline.get("core_conflict"):
            normalized_book_outline["core_conflict"] = main_conflict
        if main_conflict and not normalized_book_outline.get("mainline"):
            normalized_book_outline["mainline"] = main_conflict
        return normalized_book_outline

    def _book_outline_plan_from_confirmed_candidates(self, confirmed_candidates: dict[str, dict[str, Any]]) -> dict[str, Any]:
        book_candidate = confirmed_candidates["book"]
        volumes_candidate = confirmed_candidates["volumes"]
        book_outline = book_candidate.get("book_outline") if isinstance(book_candidate.get("book_outline"), dict) else {}
        volume_outlines = volumes_candidate.get("volume_outlines") if isinstance(volumes_candidate.get("volume_outlines"), list) else []
        if not book_outline:
            raise _bad_request("总纲候选缺少 book_outline，无法写入正式大纲")
        if not volume_outlines:
            raise _bad_request("卷纲候选缺少 volume_outlines，无法写入正式大纲")
        normalized_book_outline = self._normalize_book_outline_for_commit(book_outline)
        normalized_volumes = [dict(item) for item in volume_outlines if isinstance(item, dict)]
        return {
            **{key: value for key, value in book_candidate.items() if key not in {"generation_kind", "book_outline", "volume_outlines", "requires_user_confirmation", "candidate_status"}},
            "generation_kind": "book_outline",
            "source": "outline_debate",
            "requires_user_confirmation": False,
            "candidate_status": "committed",
            "book_outline": normalized_book_outline,
            "volume_outlines": normalized_volumes,
            "10卷单元总表": normalized_volumes,
            "parameters": {
                "volume_count": len(normalized_volumes),
            },
        }

    def _chapter_outlines_from_confirmed_candidates(self, confirmed_candidates: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        chapters_candidate = confirmed_candidates["chapters"]
        chapter_outlines = chapters_candidate.get("chapter_outlines") if isinstance(chapters_candidate.get("chapter_outlines"), list) else []
        normalized = [dict(item) for item in chapter_outlines if isinstance(item, dict)]
        if not normalized:
            raise _bad_request("章纲候选缺少 chapter_outlines，无法写入正式章纲")
        return normalized

    def _phase_chain(self, phase: str) -> list[str]:
        index = PHASE_ORDER.index(phase)
        return list(PHASE_ORDER[index:])

    def _downstream_phases(self, phase: str) -> list[str]:
        index = PHASE_ORDER.index(phase)
        return list(PHASE_ORDER[index + 1 :])

    def _invalidate_confirmation_chain(self, session: dict[str, Any], phase: str) -> None:
        confirmed_candidates = session.setdefault("confirmed_candidates", {})
        for target_phase in self._phase_chain(phase):
            confirmed_candidates.pop(target_phase, None)
        for downstream_phase in self._downstream_phases(phase):
            phase_run = session.get("phase_runs", {}).get(downstream_phase)
            if isinstance(phase_run, dict):
                self._mark_phase_run_stale(phase_run, f"{PHASE_CONFIG[phase]['result_title']}已重新生成")

    def _invalidate_item_confirmation(self, session: dict[str, Any], phase: str, item_key: str) -> None:
        confirmed_candidates = session.setdefault("confirmed_candidates", {})
        phase_candidate = confirmed_candidates.get(phase)
        if isinstance(phase_candidate, dict):
            list_key = self._item_list_key(phase)
            values = phase_candidate.get(list_key)
            if isinstance(values, list):
                phase_candidate[list_key] = [
                    item
                    for item in values
                    if not (isinstance(item, dict) and self._item_key_for_candidate(phase, item) == item_key)
                ]
            if not phase_candidate.get(list_key):
                confirmed_candidates.pop(phase, None)
        phase_run = session.get("phase_runs", {}).get(phase)
        if isinstance(phase_run, dict):
            for item in phase_run.get("confirmation_items", []):
                if isinstance(item, dict) and item.get("item_key") == item_key and item.get("candidate_status") == "confirmed":
                    item["candidate_status"] = "stale"
                    item["stale_reason"] = "该项已重新生成"
            result = phase_run.get("result")
            list_key = self._item_list_key(phase)
            if isinstance(result, dict) and isinstance(result.get(list_key), list):
                for candidate in result[list_key]:
                    if isinstance(candidate, dict) and self._item_key_for_candidate(phase, candidate) == item_key:
                        candidate["candidate_status"] = "stale"
                        candidate["stale_reason"] = "该项已重新生成"
            self._refresh_confirmation_items(phase_run)
        if phase == "volumes":
            chapters_run = session.get("phase_runs", {}).get("chapters")
            if isinstance(chapters_run, dict):
                self._mark_phase_run_stale(chapters_run, "卷纲条目已重新生成，请重新确认相关章纲")
            confirmed_candidates.pop("chapters", None)

    def _mark_phase_run_stale(self, phase_run: dict[str, Any], reason: str) -> None:
        now = utcnow().isoformat()
        phase_run["candidate_status"] = "stale"
        phase_run["stale_reason"] = reason
        phase_run["stale_at"] = now
        result = phase_run.get("result")
        if isinstance(result, dict):
            result["candidate_status"] = "stale"
            result["stale_reason"] = reason
            result["requires_user_confirmation"] = True
        for item in phase_run.get("confirmation_items", []):
            if isinstance(item, dict):
                item["candidate_status"] = "stale"
                item["stale_reason"] = reason
        self._mark_primary_artifact_status(phase_run, "stale")

    def _mark_primary_artifact_status(self, phase_run: dict[str, Any], status: str) -> None:
        result_key = PHASE_CONFIG[phase_run["phase"]]["result_key"]
        for artifact in phase_run.get("artifacts", []):
            if not isinstance(artifact, dict) or artifact.get("type") != result_key:
                continue
            artifact["candidate_status"] = status
            payload = artifact.get("payload")
            if isinstance(payload, dict):
                payload["candidate_status"] = status
                payload["requires_user_confirmation"] = status != "confirmed"

    def _mark_phase_run_pending(self, phase_run: dict[str, Any]) -> dict[str, Any]:
        phase_run["candidate_status"] = "pending_confirmation"
        phase_run["requires_user_confirmation"] = True
        result = phase_run.get("result")
        if isinstance(result, dict):
            result["candidate_status"] = "pending_confirmation"
            result["requires_user_confirmation"] = True
        self._mark_primary_artifact_status(phase_run, "pending_confirmation")
        if self._is_itemized_phase(phase_run["phase"]):
            self._refresh_confirmation_items(phase_run)
        return phase_run

    def _project(self, db: Session, project_id: str) -> models.Project:
        project = db.get(models.Project, project_id)
        if project is None:
            raise _not_found("项目不存在")
        return project

    def _session_job(self, db: Session, project_id: str, session_id: str) -> models.GenerationJob:
        job = db.get(models.GenerationJob, session_id)
        if job is None or job.project_id != project_id or job.job_type != "outline_debate_session":
            raise _not_found("大纲议事会话不存在")
        return job

    def _session_from_job(self, job: models.GenerationJob) -> dict[str, Any]:
        payload = loads(job.result_json, {}) if job.result_json else {}
        session = payload.get("session") if isinstance(payload, dict) else None
        if not isinstance(session, dict):
            session = {}
        session.setdefault("id", job.id)
        session.setdefault("project_id", job.project_id)
        session.setdefault("status", "draft")
        session.setdefault("current_phase", "")
        session.setdefault("brief", "")
        session.setdefault("phase_order", list(PHASE_ORDER))
        session.setdefault("phase_runs", {})
        session.setdefault("confirmed_candidates", {})
        session.setdefault("source", "outline_debate")
        session.setdefault("messages", [])
        self._refresh_turn_display_text(session)
        return session

    def _refresh_turn_display_text(self, session: dict[str, Any]) -> None:
        phase_runs = session.get("phase_runs") if isinstance(session.get("phase_runs"), dict) else {}
        for phase_run in phase_runs.values():
            if not isinstance(phase_run, dict):
                continue
            turns = phase_run.get("turns") if isinstance(phase_run.get("turns"), list) else []
            for index, turn in enumerate(turns):
                if not isinstance(turn, dict):
                    continue
                next_agent_name = str(turn.get("next_agent_name") or "")
                if not next_agent_name and index + 1 < len(turns) and isinstance(turns[index + 1], dict):
                    next_agent_name = str(turns[index + 1].get("agent_name") or "")
                if not next_agent_name and index == len(turns) - 1:
                    next_agent_name = str(phase_run.get("next_agent_name") or "")
                self._attach_turn_display(turn, next_agent_name)

    def _agent_spec(self, agent_name: str) -> dict[str, Any]:
        role = dict(DEBATE_AGENTS).get(agent_name, agent_name)
        base = DEBATE_AGENT_SKILL_SPECS.get(agent_name, {})
        skill_file = str(base.get("skill_file") or "")
        return {
            "name": agent_name,
            "role": role,
            "core_capability": str(base.get("core_capability") or role),
            "skill_file": skill_file,
            "skill_source": "file" if skill_file else "inline",
            "skill_file_exists": self._skill_file_path(skill_file).exists() if skill_file else False,
            "skills": list(base.get("skills") or []),
            "required_context_keys": list(base.get("required_context_keys") or []),
            "allowed_read_tools": list(base.get("allowed_read_tools") or []),
            "allowed_candidate_tools": list(base.get("allowed_candidate_tools") or []),
            "validators": list(base.get("validators") or []),
            "forbidden_tools": list(base.get("forbidden_tools") or []),
            "candidate_policy": str(base.get("candidate_policy") or "只输出候选讨论意见。"),
        }

    def _skill_file_path(self, skill_file: str) -> Path:
        return Path(__file__).resolve().parents[2] / skill_file

    def _agent_skill_context(self, agent_spec: dict[str, Any]) -> dict[str, Any]:
        skill_file = str(agent_spec.get("skill_file") or "")
        path = self._skill_file_path(skill_file) if skill_file else None
        content = ""
        if path and path.exists():
            content = path.read_text(encoding="utf-8")[:12000]
        return {
            "source": agent_spec.get("skill_source", "inline"),
            "file": skill_file,
            "content": content,
        }

    def _agent_specs(self) -> list[dict[str, Any]]:
        return [self._agent_spec(agent_name) for agent_name, _role in DEBATE_AGENTS]

    def _canon_context(self, db: Session, project_id: str) -> dict[str, Any]:
        characters = (
            db.query(models.Character)
            .filter(models.Character.project_id == project_id, models.Character.status != "archived")
            .order_by(models.Character.importance_score.desc(), models.Character.updated_at.desc())
            .limit(30)
            .all()
        )
        entities = (
            db.query(models.StoryEntity)
            .filter(models.StoryEntity.project_id == project_id, models.StoryEntity.current_status != "archived")
            .order_by(models.StoryEntity.importance_score.desc(), models.StoryEntity.updated_at.desc())
            .limit(40)
            .all()
        )
        world_facts = (
            db.query(models.WorldFact)
            .filter(models.WorldFact.project_id == project_id)
            .order_by(models.WorldFact.importance_score.desc(), models.WorldFact.updated_at.desc())
            .limit(40)
            .all()
        )
        graph_nodes = (
            db.query(models.GraphNode)
            .filter(models.GraphNode.project_id == project_id)
            .order_by(models.GraphNode.importance_score.desc(), models.GraphNode.updated_at.desc())
            .limit(60)
            .all()
        )
        graph_edges = (
            db.query(models.GraphEdge)
            .filter(models.GraphEdge.project_id == project_id)
            .order_by(models.GraphEdge.importance_score.desc(), models.GraphEdge.updated_at.desc())
            .limit(80)
            .all()
        )
        continuity_issues = (
            db.query(models.ContinuityIssue)
            .filter(models.ContinuityIssue.project_id == project_id, models.ContinuityIssue.status == "open")
            .order_by(models.ContinuityIssue.updated_at.desc())
            .limit(30)
            .all()
        )
        foreshadowing_items = (
            db.query(models.ForeshadowingItem)
            .filter(models.ForeshadowingItem.project_id == project_id, models.ForeshadowingItem.payoff_status != "abandoned")
            .order_by(models.ForeshadowingItem.importance_score.desc(), models.ForeshadowingItem.updated_at.desc())
            .limit(40)
            .all()
        )
        creation_session = (
            db.query(models.CreationSession)
            .filter(models.CreationSession.project_id == project_id)
            .order_by(models.CreationSession.updated_at.desc())
            .first()
        )
        creation_payload = serialize_creation_session(creation_session) if creation_session else {}
        creation_state = creation_payload.get("state") if isinstance(creation_payload.get("state"), dict) else {}
        return {
            "characters": [serialize_character(item) for item in characters],
            "entities": [serialize_story_entity(item) for item in entities],
            "world_facts": [serialize_world_fact(item) for item in world_facts],
            "graph": {
                "nodes": [serialize_graph_node(item) for item in graph_nodes],
                "edges": [serialize_graph_edge(item) for item in graph_edges],
            },
            "unresolved_continuity_issues": [serialize_continuity_issue(item) for item in continuity_issues],
            "foreshadowing_items": [serialize_foreshadowing_item(item) for item in foreshadowing_items],
            "creation_session": creation_payload,
            "creation_seed": creation_state.get("seed") or creation_state.get("selected_seed") or {},
            "core_conflict_system": creation_state.get("core_conflict_system") or {},
            "novel_constitution": creation_state.get("novel_constitution") or {},
            "counts": {
                "characters": len(characters),
                "entities": len(entities),
                "world_facts": len(world_facts),
                "graph_nodes": len(graph_nodes),
                "graph_edges": len(graph_edges),
                "unresolved_continuity_issues": len(continuity_issues),
                "foreshadowing_items": len(foreshadowing_items),
            },
        }

    def _scale_plan(self, project: models.Project, request: OutlineDebateRunRequest) -> dict[str, int]:
        source = request.scale_plan if isinstance(request.scale_plan, dict) else {}

        def positive_int(value: Any, fallback: int, minimum: int = 1, maximum: int | None = None) -> int:
            try:
                number = int(value)
            except (TypeError, ValueError):
                number = int(fallback)
            number = max(minimum, number)
            if maximum is not None:
                number = min(maximum, number)
            return number

        volume_count = positive_int(
            source.get("volume_count") or request.volume_count or project.planned_volume_count,
            project.planned_volume_count or max(1, round((project.planned_chapter_count or 80) / 40)),
            maximum=30,
        )
        chapters_per_volume = positive_int(
            source.get("chapters_per_volume") or request.chapters_per_volume or project.chapters_per_volume,
            project.chapters_per_volume or max(1, ((project.planned_chapter_count or 80) + volume_count - 1) // volume_count),
            maximum=300,
        )
        chapter_count = positive_int(source.get("chapter_count"), volume_count * chapters_per_volume, maximum=6000)
        chapter_word_target = positive_int(
            source.get("chapter_word_target") or request.chapter_word_target,
            project.chapter_word_target or 2500,
            minimum=500,
            maximum=20000,
        )
        chapter_word_min = positive_int(
            source.get("chapter_word_min") or request.chapter_word_min,
            project.chapter_word_min or chapter_word_target,
            minimum=500,
            maximum=20000,
        )
        chapter_word_max = positive_int(
            source.get("chapter_word_max") or request.chapter_word_max,
            project.chapter_word_max or max(chapter_word_min, chapter_word_target),
            minimum=500,
            maximum=20000,
        )
        if chapter_word_max < chapter_word_min:
            chapter_word_min, chapter_word_max = chapter_word_max, chapter_word_min
        chapter_word_target = min(max(chapter_word_target, chapter_word_min), chapter_word_max)
        target_words = positive_int(source.get("target_words") or request.target_words, chapter_count * chapter_word_target, minimum=0, maximum=10000000)
        return {
            "target_words": target_words,
            "volume_count": volume_count,
            "chapter_count": chapter_count,
            "chapters_per_volume": chapters_per_volume,
            "chapter_word_target": chapter_word_target,
            "chapter_word_min": chapter_word_min,
            "chapter_word_max": chapter_word_max,
        }

    def _phase_context(
        self,
        db: Session,
        project: models.Project,
        session: dict[str, Any],
        phase: str,
        request: OutlineDebateRunRequest,
    ) -> dict[str, Any]:
        story_bible = db.query(models.StoryBible).filter(models.StoryBible.project_id == project.id).first()
        volumes = db.query(models.Volume).filter(models.Volume.project_id == project.id).order_by(models.Volume.volume_no.asc()).all()
        chapters = db.query(models.Chapter).filter(models.Chapter.project_id == project.id, models.Chapter.deleted_at.is_(None)).order_by(models.Chapter.chapter_no.asc()).all()
        phase_run = session.get("phase_runs", {}).get(phase, {})
        canon_context = self._canon_context(db, project.id)
        scale_plan = self._scale_plan(project, request)
        return {
            "project": serialize_project(project),
            "story_bible": serialize_story_bible(story_bible) if story_bible else {},
            "scale_plan": scale_plan,
            "canon_context": canon_context,
            "characters": canon_context["characters"],
            "entities": canon_context["entities"],
            "world_facts": canon_context["world_facts"],
            "graph": canon_context["graph"],
            "foreshadowing_items": canon_context["foreshadowing_items"],
            "unresolved_continuity_issues": canon_context["unresolved_continuity_issues"],
            "creation_seed": canon_context["creation_seed"],
            "core_conflict_system": canon_context["core_conflict_system"],
            "novel_constitution": canon_context["novel_constitution"],
            "volumes": [serialize_volume(volume) for volume in volumes],
            "chapters": [serialize_chapter(chapter) for chapter in chapters[:20]],
            "session_brief": session.get("brief", ""),
            "session_messages": session.get("messages", []),
            "user_messages": phase_run.get("user_messages", []) if isinstance(phase_run, dict) else [],
            "existing_turns": phase_run.get("turns", []) if isinstance(phase_run, dict) else [],
            "upstream_phase_runs": session.get("phase_runs", {}),
            "requirement": request.requirement,
        }

    def _load_or_create_round_phase_run(self, session: dict[str, Any], phase: str, request: OutlineDebateRunRequest) -> dict[str, Any]:
        phase_runs = session.setdefault("phase_runs", {})
        existing = phase_runs.get(phase)
        if isinstance(existing, dict) and not request.refresh_phase:
            existing.setdefault("turns", [])
            existing.setdefault("user_messages", [])
            existing.setdefault("decisions", [])
            existing.setdefault("artifacts", [])
            existing.setdefault("outline_topology", {})
            existing.setdefault("result", {})
            existing.setdefault("agent_specs", self._agent_specs())
            existing.setdefault("candidate_policy", {})
            existing.setdefault("validation_report", {})
            existing.setdefault("next_agent_name", DEBATE_AGENTS[0][0])
            self._attach_pending_session_messages(existing, session, phase)
            return existing
        now = utcnow().isoformat()
        pending_messages = self._pending_session_messages(session, phase)
        phase_run = {
            "id": generate_id("odr"),
            "phase": phase,
            "phase_label": PHASE_CONFIG[phase]["label"],
            "status": "running",
            "candidate_status": "draft",
            "started_at": now,
            "finished_at": "",
            "input": request.model_dump(mode="json"),
            "agent_specs": self._agent_specs(),
            "candidate_policy": {},
            "validation_report": {},
            "turns": [],
            "user_messages": pending_messages,
            "decisions": [],
            "artifacts": [],
            "outline_topology": {},
            "result": {},
            "next_agent_name": self._next_agent_from_pending_messages(pending_messages) or DEBATE_AGENTS[0][0],
        }
        phase_runs[phase] = phase_run
        return phase_run

    def _pending_session_messages(self, session: dict[str, Any], phase: str) -> list[dict[str, Any]]:
        messages = session.get("messages") if isinstance(session.get("messages"), list) else []
        return [
            message
            for message in messages
            if isinstance(message, dict)
            and message.get("phase") == phase
            and message.get("role") == "user"
            and not message.get("handled_by_turn_id")
        ]

    def _attach_pending_session_messages(self, phase_run: dict[str, Any], session: dict[str, Any], phase: str) -> None:
        existing_ids = {
            message.get("id")
            for message in phase_run.get("user_messages", [])
            if isinstance(message, dict) and message.get("id")
        }
        appended: list[dict[str, Any]] = []
        for message in self._pending_session_messages(session, phase):
            if message.get("id") in existing_ids:
                continue
            phase_run.setdefault("user_messages", []).append(message)
            appended.append(message)
        target_agent_name = self._next_agent_from_pending_messages(appended)
        if target_agent_name:
            phase_run["next_agent_name"] = target_agent_name

    def _next_agent_from_pending_messages(self, messages: list[dict[str, Any]]) -> str:
        for message in reversed(messages):
            target_agent_name = self._valid_agent_name(str(message.get("target_agent_name") or ""))
            if target_agent_name:
                return target_agent_name
            mentions = message.get("mentions") if isinstance(message.get("mentions"), list) else []
            for mention in mentions:
                target_agent_name = self._valid_agent_name(str(mention))
                if target_agent_name:
                    return target_agent_name
        return ""

    def _valid_agent_name(self, agent_name: str | None) -> str:
        if not agent_name:
            return ""
        if agent_name in DEBATE_AGENT_NAMES:
            return agent_name
        return DEBATE_AGENT_ALIASES.get(agent_name.lstrip("@"), "")

    def _extract_mentions(self, message: str, target_agent_name: str = "") -> list[str]:
        mentions: list[str] = []
        if target_agent_name:
            mentions.append(target_agent_name)
        for alias, agent_name in DEBATE_AGENT_ALIASES.items():
            if f"@{alias}" in message and agent_name not in mentions:
                mentions.append(agent_name)
        for agent_name in DEBATE_AGENT_NAMES:
            if f"@{agent_name}" in message and agent_name not in mentions:
                mentions.append(agent_name)
        return mentions

    def _append_user_message_to_session(self, session: dict[str, Any], request: OutlineDebateUserMessageRequest) -> dict[str, Any]:
        self._validate_phase(request.phase)
        target_agent_name = self._valid_agent_name(request.target_agent_name)
        mentions = self._extract_mentions(request.message, target_agent_name)
        message = {
            "id": generate_id("odm"),
            "phase": request.phase,
            "role": "user",
            "message": request.message,
            "target_agent_name": target_agent_name,
            "mentions": mentions,
            "created_at": utcnow().isoformat(),
            "handled_by_turn_id": "",
        }
        session.setdefault("messages", []).append(message)
        phase_run = session.setdefault("phase_runs", {}).get(request.phase)
        if isinstance(phase_run, dict):
            phase_run.setdefault("user_messages", []).append(message)
            if target_agent_name:
                phase_run["next_agent_name"] = target_agent_name
        return message

    def _next_round_agent_name(self, phase_run: dict[str, Any]) -> str:
        for message in reversed(phase_run.get("user_messages", [])):
            target_agent_name = self._valid_agent_name(message.get("target_agent_name", ""))
            if target_agent_name and not message.get("handled_by_turn_id"):
                return target_agent_name
            mentions = message.get("mentions") if isinstance(message.get("mentions"), list) else []
            for mention in mentions:
                target_agent_name = self._valid_agent_name(str(mention))
                if target_agent_name and not message.get("handled_by_turn_id"):
                    return target_agent_name
        spoken = {turn.get("agent_name") for turn in phase_run.get("turns", [])}
        for agent_name, _role in DEBATE_AGENTS:
            if agent_name not in spoken:
                return agent_name
        return ""

    def _mark_target_message_handled(self, phase_run: dict[str, Any], turn: dict[str, Any]) -> None:
        for message in reversed(phase_run.get("user_messages", [])):
            target_agent_name = self._valid_agent_name(message.get("target_agent_name", ""))
            mentions = message.get("mentions") if isinstance(message.get("mentions"), list) else []
            mentioned = {self._valid_agent_name(str(item)) for item in mentions}
            if target_agent_name == turn["agent_name"] or turn["agent_name"] in mentioned:
                message["handled_by_turn_id"] = turn["id"]
                return

    def _build_phase_run(
        self,
        db: Session,
        project: models.Project,
        session: dict[str, Any],
        phase: str,
        request: OutlineDebateRunRequest,
    ) -> dict[str, Any]:
        orchestrator = OutlineDebateOrchestrator(self)
        context = self._phase_context(db, project, session, phase, request)
        agenda = orchestrator.build_agenda(phase, request, context)
        deliberation_state = orchestrator.initial_state(agenda, request)
        turns = self._build_turns(project, phase, request, context, agenda, deliberation_state)
        cross_review = orchestrator.cross_review(deliberation_state, turns)
        result = orchestrator.synthesize_candidate_artifact(project, phase, request, turns, session, deliberation_state)
        artifacts, candidate_policy = self._build_artifacts(project, phase, request, result, turns)
        validation_report = orchestrator.validate_result(phase, result, artifacts, context)
        decisions = orchestrator.request_revision_or_finish(phase, request, result, candidate_policy, deliberation_state)
        topology = self._build_topology(phase, request, turns, decisions, artifacts)
        return self._mark_phase_run_pending({
            "id": generate_id("odr"),
            "phase": phase,
            "phase_label": PHASE_CONFIG[phase]["label"],
            "status": "succeeded",
            "started_at": utcnow().isoformat(),
            "finished_at": utcnow().isoformat(),
            "input": request.model_dump(mode="json"),
            "agent_specs": self._agent_specs(),
            "candidate_policy": candidate_policy,
            "validation_report": validation_report,
            "turns": turns,
            "decisions": decisions,
            "artifacts": artifacts,
            "outline_topology": topology,
            "debate_protocol": orchestrator.protocol(agenda, deliberation_state, cross_review, validation_report),
            "deliberation_state": deliberation_state,
            "result": result,
        })

    def _build_turns(
        self,
        project: models.Project,
        phase: str,
        request: OutlineDebateRunRequest,
        context: dict[str, Any],
        agenda: dict[str, Any] | None = None,
        deliberation_state: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        orchestrator = OutlineDebateOrchestrator(self)
        if agenda is None:
            agenda = orchestrator.build_agenda(phase, request, context)
        if deliberation_state is None:
            deliberation_state = orchestrator.initial_state(agenda, request)
        turns: list[dict[str, Any]] = []
        for index, (agent_name, role) in enumerate(DEBATE_AGENTS, start=1):
            turn = self._build_turn(project, phase, request, context, agent_name, role, index, index, agenda, deliberation_state)
            turns.append(turn)
            orchestrator.apply_turn_to_state(deliberation_state, turn)
            next_agent_name = DEBATE_AGENTS[index][0] if index < len(DEBATE_AGENTS) else ""
            self._attach_turn_display(turn, next_agent_name)
        return turns

    def _build_turn(
        self,
        project: models.Project,
        phase: str,
        request: OutlineDebateRunRequest,
        context: dict[str, Any],
        agent_name: str,
        role: str,
        round_no: int,
        agent_round: int,
        agenda: dict[str, Any] | None = None,
        deliberation_state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        phase_label = PHASE_CONFIG[phase]["label"]
        reader = project.target_reader or "目标读者体验待明确"
        requirement = request.requirement or "按现有作品信息进行结构讨论"
        agent_spec = self._agent_spec(agent_name)
        orchestrator = OutlineDebateOrchestrator(self)
        local_preview_messages = {
            "outline_debate/StoryDirectorAgent": f"{phase_label}从作品承诺出发：{project.premise}。本轮只形成候选，不写入正式正典。",
            "outline_debate/MarketPositionAgent": f"目标读者是「{reader}」。本轮要检查爽点、压迫、期待管理和平台可读性是否互相支撑。",
            "outline_debate/StructureDoctorAgent": f"结构建议围绕因果推进、阶段代价和钩子密度展开；需求是：{requirement}",
            "outline_debate/CharacterGeneratorAgent": "现有正典不足以承载阶段对抗时，提出候选角色档案卡；用户确认本阶段候选后由服务层入库。",
            "outline_debate/SettingGeneratorAgent": "现有世界规则不足以驱动冲突时，提出候选设定档案；用户确认本阶段候选后由服务层入库。",
            "outline_debate/ContinuityAuditorAgent": "检查危机、高潮、结果是否混淆，并把不确定项留作候选或风险，不硬写入正典。",
        }
        output_contract = orchestrator.turn_contract()
        local_preview_payload = {
            "stance": self._stance_for(agent_name, phase),
            "message": local_preview_messages[agent_name],
            "claims": self._claims_for(agent_name, phase, project, context),
            "objections": [],
            "proposed_decisions": [],
            "artifact_patch": {},
            "risks": self._risks_for(agent_name, phase),
            "uncertainties": [],
            "confidence": 0.65,
            "result_patch": {},
            "character_candidate": {},
            "setting_candidate": {},
            "decisions": [],
        }
        turn_context = orchestrator.turn_context(
            {
                **context,
                "phase": phase,
                "phase_label": phase_label,
                "agent_round": agent_round,
                "round_no": round_no,
                "agent_spec": agent_spec,
                "agent_skill": self._agent_skill_context(agent_spec),
            },
            agenda,
            deliberation_state,
        )
        if request.local_preview:
            payload = local_preview_payload
            llm_meta = {
                "provider": "local_preview",
                "model": request.model or "local_preview",
                "used_remote_model": False,
                "parsed": False,
                "source": "local_fallback",
                "elapsed_ms": 0,
                "schema_valid": True,
                "validation_warnings": ["local_preview=true，本轮使用本地候选草案，未调用远程模型。"],
            }
        else:
            payload, llm_meta = call_agent_json(
                llm_client=llm_client,
                agent_name=agent_name,
                role=role,
                system_prompt=DEBATE_AGENT_SYSTEM_PROMPTS.get(agent_name, role),
                task=(
                    f"执行{phase_label}讨论的第 {round_no} 个 agent turn。"
                    "必须优先遵循 context.agent_skill.content 中的角色技能文件；"
                    "请围绕 context.agenda、context.deliberation_state、context.requirement、项目资料、用户插话和上游阶段结果提出结构化意见；"
                    "必须回应前序发言，必要时提出 objections；必须给出 proposed_decisions、uncertainties、confidence。"
                    "artifact_patch 用于写入候选大纲：总纲阶段写 book_outline，卷纲阶段写 volume_outlines，章纲阶段写 chapter_outlines。"
                    "如你是角色或设定生成 Agent，可额外给出候选档案。"
                ),
                context=turn_context,
                fallback=output_contract,
                model=request.model,
                require_remote=True,
                allow_fallback=False,
            )
        return {
            "id": generate_id("turn"),
            "phase": phase,
            "round_no": round_no,
            "agent_name": agent_name,
            "role": role,
            "agent_spec": agent_spec,
            "stance": self._string_or(payload.get("stance"), local_preview_payload["stance"] if request.local_preview else ""),
            "message": self._string_or(payload.get("message"), local_preview_payload["message"] if request.local_preview else ""),
            "claims": self._list_of_strings(payload.get("claims"), local_preview_payload["claims"] if request.local_preview else []),
            "objections": self._list_of_strings(payload.get("objections"), local_preview_payload["objections"] if request.local_preview else []),
            "proposed_decisions": payload.get("proposed_decisions") if isinstance(payload.get("proposed_decisions"), list) else [],
            "artifact_patch": payload.get("artifact_patch") if isinstance(payload.get("artifact_patch"), dict) else {},
            "risks": self._list_of_strings(payload.get("risks"), local_preview_payload["risks"] if request.local_preview else []),
            "uncertainties": self._list_of_strings(payload.get("uncertainties"), local_preview_payload["uncertainties"] if request.local_preview else []),
            "confidence": self._bounded_float(payload.get("confidence"), 0.65, 0.0, 1.0),
            "result_patch": payload.get("result_patch") if isinstance(payload.get("result_patch"), dict) else (payload.get("artifact_patch") if isinstance(payload.get("artifact_patch"), dict) else {}),
            "character_candidate": payload.get("character_candidate") if isinstance(payload.get("character_candidate"), dict) else {},
            "setting_candidate": payload.get("setting_candidate") if isinstance(payload.get("setting_candidate"), dict) else {},
            "decisions": payload.get("decisions") if isinstance(payload.get("decisions"), list) else [],
            "_quality_gate": payload.get("_quality_gate", {}),
            "_llm": llm_meta,
            "output_refs": [],
        }

    async def _stream_turn_event(self, phase: str, turn: dict[str, Any]) -> Iterable[str]:
        display_text = str(turn.get("display_text") or turn.get("message") or "")
        yield _sse_block("turn", {"type": "turn", "phase": phase, "turn": turn})
        await asyncio.sleep(0)
        for char in display_text:
            yield _sse_block(
                "delta",
                {
                    "type": "delta",
                    "phase": phase,
                    "turn_id": turn.get("id", ""),
                    "agent_name": turn.get("agent_name", ""),
                    "text": char,
                },
            )
            await asyncio.sleep(0)
        yield _sse_block(
            "delta",
            {
                "type": "delta",
                "phase": phase,
                "turn_id": turn.get("id", ""),
                "agent_name": turn.get("agent_name", ""),
                "text": "",
                "done": True,
            },
        )

    def _attach_turn_display(self, turn: dict[str, Any], next_agent_name: str = "") -> None:
        current_label = self._agent_mention_label(str(turn.get("agent_name") or ""))
        next_label = self._agent_mention_label(next_agent_name)
        handoff = {
            "from_agent_name": turn.get("agent_name", ""),
            "from_label": current_label,
            "from_mention": f"@{current_label}" if current_label else "",
            "to_agent_name": next_agent_name,
            "to_label": next_label,
            "to_mention": f"@{next_label}" if next_label else "",
            "display": f"@{current_label} → @{next_label}" if next_label else f"@{current_label} → 阶段结论",
        }
        turn["next_agent_name"] = next_agent_name
        turn["handoff"] = handoff
        turn["display_text"] = self._turn_display_text(turn, handoff)

    def _turn_display_text(self, turn: dict[str, Any], handoff: dict[str, Any]) -> str:
        lines = [
            f"@{handoff.get('from_label') or turn.get('agent_name', '')} 发言",
            f"身份：{self._display_role_label(turn)}",
        ]
        if turn.get("stance"):
            lines.append(f"立场：{turn['stance']}")
        if turn.get("message"):
            lines.append("")
            lines.append(f"意见：{turn['message']}")
        structured_sections = [
            ("关键主张", turn.get("claims")),
            ("反对与质疑", turn.get("objections")),
            ("建议决议", turn.get("proposed_decisions")),
            ("候选大纲补丁", turn.get("artifact_patch")),
            ("结果补丁", turn.get("result_patch")),
            ("角色候选", turn.get("character_candidate")),
            ("设定候选", turn.get("setting_candidate")),
            ("风险", turn.get("risks")),
            ("不确定项", turn.get("uncertainties")),
            ("决议草案", turn.get("decisions")),
        ]
        for title, value in structured_sections:
            formatted = self._format_display_value(value)
            if formatted:
                lines.append("")
                lines.append(f"{title}：")
                lines.extend(formatted)
        confidence = turn.get("confidence")
        if confidence is not None:
            lines.append("")
            lines.append(f"置信度：{confidence}")
        lines.append("")
        lines.append(f"交接：{handoff.get('display')}")
        if handoff.get("to_label"):
            lines.append(f"下一位：@{handoff['to_label']}")
        else:
            lines.append("下一步：形成阶段结论")
        return "\n".join(str(line) for line in lines if str(line).strip() or line == "")

    def _format_display_value(self, value: Any, indent: int = 0) -> list[str]:
        if value in ({}, [], None, ""):
            return []
        prefix = "  " * indent
        if isinstance(value, list):
            lines: list[str] = []
            for index, item in enumerate(value, start=1):
                if isinstance(item, dict):
                    lines.append(f"{prefix}{index}.")
                    lines.extend(self._format_display_value(item, indent + 1))
                elif isinstance(item, list):
                    nested = self._format_display_value(item, indent + 1)
                    if nested:
                        lines.append(f"{prefix}{index}.")
                        lines.extend(nested)
                elif str(item).strip():
                    lines.append(f"{prefix}{index}. {str(item).strip()}")
            return lines
        if isinstance(value, dict):
            lines = []
            for key, item in value.items():
                if item in ({}, [], None, ""):
                    continue
                label = self._display_key_label(str(key))
                if isinstance(item, (dict, list)):
                    lines.append(f"{prefix}- {label}：")
                    lines.extend(self._format_display_value(item, indent + 1))
                else:
                    lines.append(f"{prefix}- {label}：{str(item).strip()}")
            return lines
        return [f"{prefix}{str(value).strip()}"] if str(value).strip() else []

    def _display_key_label(self, key: str) -> str:
        normalized = key.strip()
        if not normalized:
            return "条目"
        direct = DISPLAY_KEY_LABELS.get(normalized)
        if direct:
            return direct
        phase_match = re.fullmatch(r"phase[_\-\s]*(\d+)", normalized, flags=re.IGNORECASE)
        if phase_match:
            return f"第{self._display_number(int(phase_match.group(1)))}阶段"
        chapter_match = re.fullmatch(r"chapter[_\-\s]*(\d+)", normalized, flags=re.IGNORECASE)
        if chapter_match:
            return f"第{self._display_number(int(chapter_match.group(1)))}章"
        volume_match = re.fullmatch(r"volume[_\-\s]*(\d+)", normalized, flags=re.IGNORECASE)
        if volume_match:
            return f"第{self._display_number(int(volume_match.group(1)))}卷"
        tokens = [token for token in re.split(r"[_\-\s]+", normalized.lower()) if token]
        translated = [DISPLAY_KEY_TOKEN_LABELS.get(token, "") for token in tokens]
        if translated and all(translated):
            compact = "".join(translated)
            compact = compact.replace("章节数量", "章节数").replace("卷数量", "卷数").replace("字数目标", "目标字数")
            return compact
        return "补充项"

    def _display_role_label(self, turn: dict[str, Any]) -> str:
        agent_label = self._agent_mention_label(str(turn.get("agent_name") or ""))
        if agent_label:
            return agent_label
        role = str(turn.get("role") or "").strip()
        return role.replace(" Agent", "智能体").replace("Agent", "智能体") or "议事成员"

    def _display_number(self, value: int) -> str:
        if 0 <= value < len(_CHINESE_NUMERALS):
            return _CHINESE_NUMERALS[value]
        if 10 < value < 20:
            return f"十{_CHINESE_NUMERALS[value - 10]}"
        return str(value)

    def _agent_mention_label(self, agent_name: str) -> str:
        if not agent_name:
            return ""
        return DEBATE_AGENT_MENTION_LABELS.get(agent_name, agent_name.replace("outline_debate/", ""))

    def _string_or(self, value: Any, fallback: str) -> str:
        if isinstance(value, str) and value.strip():
            return value.strip()
        return fallback

    def _list_of_strings(self, value: Any, fallback: list[str]) -> list[str]:
        if not isinstance(value, list):
            return fallback
        items = [str(item).strip() for item in value if str(item).strip()]
        return items or fallback

    def _stance_for(self, agent_name: str, phase: str) -> str:
        if agent_name.endswith("StoryDirectorAgent"):
            return "先定承诺与边界"
        if agent_name.endswith("MarketPositionAgent"):
            return "保护目标读者体验"
        if agent_name.endswith("StructureDoctorAgent"):
            return "检查长篇结构因果"
        if agent_name.endswith("CharacterGeneratorAgent"):
            return "只补候选角色缺口"
        if agent_name.endswith("SettingGeneratorAgent"):
            return "只补候选设定缺口"
        return "守住连续性与质量门"

    def _claims_for(self, agent_name: str, phase: str, project: models.Project, context: dict[str, Any]) -> list[str]:
        if agent_name.endswith("StoryDirectorAgent"):
            return [f"{project.title}的{PHASE_CONFIG[phase]['label']}必须服务一句话故事", "所有结论保持候选态直到用户确认"]
        if agent_name.endswith("MarketPositionAgent"):
            return [f"目标读者体验来自：{project.target_reader}", "卖点必须转化为可持续冲突和章节钩子"]
        if agent_name.endswith("StructureDoctorAgent"):
            return ["危机是不可逆选择，高潮是执行选择，结果是承担后果", "卷纲与章纲不能只堆事件，必须说明状态改变"]
        if agent_name.endswith("CharacterGeneratorAgent"):
            return ["新增角色必须有剧情功能、首次需要位置和重复检查", "候选角色随用户确认由服务层入 characters 表"]
        if agent_name.endswith("SettingGeneratorAgent"):
            return ["新增设定必须解释冲突用途、伏笔用途和连续性风险", "候选设定随用户确认由服务层入 world_facts 或 entities 表"]
        return ["不确定项不硬编", "阻塞问题进入风险清单或返工建议"]

    def _risks_for(self, agent_name: str, phase: str) -> list[str]:
        if agent_name.endswith("ContinuityAuditorAgent"):
            return ["角色动机与卷/章事件脱节", "世界规则只做装饰而不驱动冲突", "章纲缺少结果后果"]
        if phase == "chapters":
            return ["连续章节钩子重复", "危机与高潮边界不清"]
        if phase == "volumes":
            return ["分卷节奏模型套模板", "卷末钩子没有改变下一卷压力"]
        return ["总纲过泛", "核心冲突无法持续支撑长篇"]

    def _build_result(
        self,
        project: models.Project,
        phase: str,
        request: OutlineDebateRunRequest,
        turns: list[dict[str, Any]],
        session: dict[str, Any],
    ) -> dict[str, Any]:
        state = {
            "source": "local_preview" if request.local_preview else "real_llm",
            "artifact_patches": [
                {"turn_id": turn.get("id", ""), "agent_name": turn.get("agent_name", ""), "patch": patch}
                for turn in turns
                for patch in (turn.get("artifact_patch"), turn.get("result_patch"))
                if isinstance(patch, dict) and patch
            ],
            "source_turn_ids": [str(turn.get("id") or "") for turn in turns if turn.get("id")],
        }
        return self._build_result_from_debate_state(project, phase, request, turns, session, state)

    def _build_result_from_debate_state(
        self,
        project: models.Project,
        phase: str,
        request: OutlineDebateRunRequest,
        turns: list[dict[str, Any]],
        session: dict[str, Any],
        deliberation_state: dict[str, Any],
    ) -> dict[str, Any]:
        generation_kind = PHASE_CONFIG[phase]["generation_kind"]
        source_turn_ids = [str(item) for item in deliberation_state.get("source_turn_ids", []) if str(item)]
        if not source_turn_ids:
            source_turn_ids = [str(turn.get("id") or "") for turn in turns if turn.get("id")]
        provenance = {
            "source": "debate_state",
            "state_id": deliberation_state.get("id", ""),
            "source_turn_ids": source_turn_ids,
            "artifact_patch_count": len(deliberation_state.get("artifact_patches", [])),
        }
        scale_plan = self._scale_plan(project, request)
        if phase == "book":
            result = {
                "generation_kind": generation_kind,
                "scale_plan": scale_plan,
                "book_outline": self._book_outline_from_debate(project, turns),
                "discussion_summary": [turn["message"] for turn in turns[:3]],
                "requires_user_confirmation": True,
                "synthesis_source": "debate_state",
                "source_turn_ids": source_turn_ids,
                "_provenance": provenance,
            }
            return self._merge_result_patches(result, turns, ("book_outline", "discussion_summary"), deliberation_state)
        if phase == "volumes":
            target_volume_no = self._target_volume_no(request)
            result = {
                "generation_kind": generation_kind,
                "scale_plan": scale_plan,
                "target_volume_no": target_volume_no,
                "expected_volume_count": scale_plan["volume_count"],
                "item_key": f"volume:{target_volume_no}",
                "volume_outlines": [self._volume_candidate_from_debate(target_volume_no, project, request, turns)],
                "upstream_book_run_id": session.get("phase_runs", {}).get("book", {}).get("id", ""),
                "requires_user_confirmation": True,
                "synthesis_source": "debate_state",
                "source_turn_ids": source_turn_ids,
                "_provenance": provenance,
            }
            return self._restrict_itemized_result(phase, request, self._merge_result_patches(result, turns, ("volume_outlines",), deliberation_state))
        target_volume_no = self._target_volume_no(request)
        target_chapter_no = self._target_chapter_no(request)
        result = {
            "generation_kind": generation_kind,
            "scale_plan": scale_plan,
            "target_volume_no": target_volume_no,
            "target_chapter_no": target_chapter_no,
            "item_key": f"chapter:{target_chapter_no}",
            "chapter_outlines": self._chapter_candidates_from_debate(project, request, turns),
            "upstream_volume_run_id": session.get("phase_runs", {}).get("volumes", {}).get("id", ""),
            "requires_user_confirmation": True,
            "synthesis_source": "debate_state",
            "source_turn_ids": source_turn_ids,
            "_provenance": provenance,
        }
        return self._restrict_itemized_result(phase, request, self._merge_result_patches(result, turns, ("chapter_outlines",), deliberation_state))

    def _merge_result_patches(
        self,
        result: dict[str, Any],
        turns: list[dict[str, Any]],
        allowed_keys: tuple[str, ...],
        deliberation_state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        merged = dict(result)
        state_patches = []
        if isinstance(deliberation_state, dict):
            state_patches = [item.get("patch") for item in deliberation_state.get("artifact_patches", []) if isinstance(item, dict)]
        turn_patches = [turn.get("artifact_patch") if turn.get("artifact_patch") else turn.get("result_patch") for turn in turns]
        for patch in [*state_patches, *turn_patches]:
            if not isinstance(patch, dict):
                continue
            for key in allowed_keys:
                value = patch.get(key)
                if value in (None, "", [], {}):
                    continue
                if isinstance(value, dict) and isinstance(merged.get(key), dict):
                    merged[key] = self._deep_merge_dicts(merged[key], value)
                else:
                    merged[key] = value
        merged["generation_kind"] = result["generation_kind"]
        merged["requires_user_confirmation"] = True
        merged["candidate_status"] = "pending_confirmation"
        return merged

    def _book_outline_from_debate(self, project: models.Project, turns: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "title": project.title,
            "premise": project.premise,
            "core_promise": self._debate_sentence(turns, ("StoryDirectorAgent", "MarketPositionAgent"), project.target_reader or project.premise),
            "main_conflict": self._debate_sentence(turns, ("StructureDoctorAgent", "StoryDirectorAgent"), project.premise or project.title),
            "ending_direction": self._debate_sentence(turns, ("ContinuityAuditorAgent", "StoryDirectorAgent"), "终局方向待用户确认。"),
            "reader_experience": project.target_reader,
        }

    def _volume_candidate_from_debate(self, volume_no: int, project: models.Project, request: OutlineDebateRunRequest, turns: list[dict[str, Any]]) -> dict[str, Any]:
        model_name = "多线群像并进" if any(key in project.genre for key in ("权谋", "战争", "群像")) else "动态长篇升级"
        scale_plan = self._scale_plan(project, request)
        chapters_per_volume = scale_plan["chapters_per_volume"]
        return {
            "volume_no": volume_no,
            "title": f"第{volume_no}卷：{self._short_label(self._debate_sentence(turns, ('StructureDoctorAgent', 'StoryDirectorAgent'), '阶段压力'))}",
            "chapter_range": f"{(volume_no - 1) * chapters_per_volume + 1}-{volume_no * chapters_per_volume}",
            "volume_function": self._debate_sentence(turns, ("StructureDoctorAgent", "StoryDirectorAgent"), "承接上游总纲并改变主角处境。"),
            "rhythm_model": {
                "model_name": model_name,
                "why_this_model": self._debate_sentence(turns, ("StructureDoctorAgent",), "根据类型、读者体验和阶段冲突选择。"),
                "phase_count": 4,
                "chapter_distribution": self._phase_distribution(chapters_per_volume, 4),
            },
            "core_goal": self._debate_sentence(turns, ("StoryDirectorAgent", "MarketPositionAgent"), "阶段目标待确认。"),
            "volume_hook": self._debate_sentence(turns, ("ContinuityAuditorAgent", "StructureDoctorAgent"), "卷末钩子待确认。"),
            "risks": self._list_from_turns(turns, "risks")[:4],
        }

    def _chapter_candidates_from_debate(self, project: models.Project, request: OutlineDebateRunRequest, turns: list[dict[str, Any]]) -> list[dict[str, Any]]:
        candidates = []
        scale_plan = self._scale_plan(project, request)
        for volume_no, chapter_no in self._chapter_candidates_for_request(request):
            crisis, climax, outcome = self._distinct_chapter_beats(turns)
            candidates.append(
                {
                    "chapter_no": chapter_no,
                    "volume_no": volume_no,
                    "title": f"第{chapter_no}章：{self._short_label(self._debate_sentence(turns, ('StructureDoctorAgent', 'StoryDirectorAgent'), '选择与后果'))}",
                    "outline": self._debate_sentence(turns, ("StoryDirectorAgent", "StructureDoctorAgent"), project.premise),
                    "pov_character": "主角",
                    "core_event": self._debate_sentence(turns, ("StoryDirectorAgent",), "本章核心事件待确认。"),
                    "conflict": self._debate_sentence(turns, ("MarketPositionAgent", "StructureDoctorAgent"), "本章冲突待确认。"),
                    "crisis": crisis,
                    "climax": climax,
                    "result": outcome,
                    "cliffhanger": self._debate_sentence(turns, ("MarketPositionAgent", "ContinuityAuditorAgent"), "章末钩子待确认。"),
                    "word_target": scale_plan["chapter_word_target"],
                    "word_range": [scale_plan["chapter_word_min"], scale_plan["chapter_word_max"]],
                }
            )
        return candidates

    def _distinct_chapter_beats(self, turns: list[dict[str, Any]]) -> tuple[str, str, str]:
        crisis = self._debate_sentence(turns, ("StructureDoctorAgent",), "本章危机待确认。")
        climax = self._debate_sentence(turns, ("StoryDirectorAgent", "StructureDoctorAgent"), "本章高潮待确认。")
        outcome = self._debate_sentence(turns, ("ContinuityAuditorAgent",), "本章结果待确认。")
        if len({crisis, climax, outcome}) == 3:
            return crisis, climax, outcome
        base = crisis or climax or outcome or "本章结构待确认"
        return (
            f"危机：围绕「{self._short_label(base)}」形成不可逆选择。",
            f"高潮：执行该选择，并让行动产生可见代价。",
            f"结果：承接代价，改变局面并留下下一章必须回应的问题。",
        )

    def _debate_sentence(self, turns: list[dict[str, Any]], agent_suffixes: tuple[str, ...], fallback: str) -> str:
        for suffix in agent_suffixes:
            for turn in turns:
                if not str(turn.get("agent_name", "")).endswith(suffix):
                    continue
                for value in [*turn.get("claims", []), turn.get("message", ""), *turn.get("proposed_decisions", []), *turn.get("risks", [])]:
                    if isinstance(value, dict):
                        value = value.get("decision") or value.get("title") or value.get("rationale") or ""
                    text = str(value).strip()
                    if text:
                        return text[:500]
        return fallback

    def _short_label(self, text: str) -> str:
        compact = str(text).replace("\n", " ").strip()
        for separator in ("。", "；", ";", ".", "，", ","):
            if separator in compact:
                compact = compact.split(separator, 1)[0]
                break
        return compact[:24] or "阶段候选"

    def _list_from_turns(self, turns: list[dict[str, Any]], key: str) -> list[str]:
        values: list[str] = []
        for turn in turns:
            values.extend(str(item).strip() for item in turn.get(key, []) if str(item).strip())
        return values

    def _deep_merge_dicts(self, base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
        merged = dict(base)
        for key, value in patch.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = self._deep_merge_dicts(merged[key], value)
            else:
                merged[key] = value
        return merged

    def _restrict_itemized_result(self, phase: str, request: OutlineDebateRunRequest, result: dict[str, Any]) -> dict[str, Any]:
        if not self._is_itemized_phase(phase):
            return result
        list_key = self._item_list_key(phase)
        id_field = self._item_no_field(phase)
        target_number = self._target_volume_no(request) if phase == "volumes" else self._target_chapter_no(request)
        values = result.get(list_key) if isinstance(result.get(list_key), list) else []
        filtered = [dict(item) for item in values if isinstance(item, dict) and int(item.get(id_field) or target_number) == target_number]
        if not filtered and values:
            first = next((dict(item) for item in values if isinstance(item, dict)), {})
            if first:
                filtered = [first]
        if filtered:
            filtered[0][id_field] = target_number
            filtered[0]["candidate_status"] = "pending_confirmation"
            filtered[0]["requires_user_confirmation"] = True
        result[list_key] = filtered
        return result

    def _volume_candidate(self, volume_no: int, project: models.Project, request: OutlineDebateRunRequest) -> dict[str, Any]:
        model_name = "多线群像并进" if any(key in project.genre for key in ("权谋", "战争", "群像")) else "动态长篇升级"
        scale_plan = self._scale_plan(project, request)
        chapters_per_volume = scale_plan["chapters_per_volume"]
        return {
            "volume_no": volume_no,
            "title": f"第{volume_no}卷：压力递进",
            "chapter_range": f"{(volume_no - 1) * chapters_per_volume + 1}-{volume_no * chapters_per_volume}",
            "volume_function": "改变主角处境、抬升对抗层级，并暴露一层世界规则。",
            "rhythm_model": {
                "model_name": model_name,
                "why_this_model": "根据类型、读者体验和阶段冲突选择，不固定套用五段模板。",
                "phase_count": 4,
                "chapter_distribution": self._phase_distribution(chapters_per_volume, 4),
            },
            "core_goal": "主角争取阶段性资源与解释权。",
            "volume_hook": "卷末出现让下一卷压力升级的新证据或新敌人。",
            "risks": ["重复升级", "角色关系缺少代价"],
        }

    def _phase_distribution(self, chapters_per_volume: int, phase_count: int) -> str:
        segment = max(1, chapters_per_volume // phase_count)
        ranges = []
        start = 1
        for index in range(1, phase_count + 1):
            end = chapters_per_volume if index == phase_count else min(chapters_per_volume, start + segment - 1)
            ranges.append(f"{start}-{end}")
            start = end + 1
        return " / ".join(ranges)

    def _chapter_candidates(self, project: models.Project, request: OutlineDebateRunRequest) -> list[dict[str, Any]]:
        candidates = []
        scale_plan = self._scale_plan(project, request)
        for volume_no, chapter_no in self._chapter_candidates_for_request(request):
            candidates.append(
                {
                    "chapter_no": chapter_no,
                    "volume_no": volume_no,
                    "title": f"第{chapter_no}章：选择的代价",
                    "outline": f"围绕「{project.premise}」推进一次行动、一次阻碍、一次后果。",
                    "pov_character": "主角",
                    "core_event": "主角为阶段目标作出不可逆选择。",
                    "conflict": "既有秩序以身份、资源或关系施压。",
                    "crisis": "主角必须在保全自身与推进目标之间二选一。",
                    "climax": "主角执行选择并付出可见代价。",
                    "result": "局面改变，留下下一章必须回应的新问题。",
                    "cliffhanger": "新的证据指向更高层规则漏洞。",
                    "word_target": scale_plan["chapter_word_target"],
                    "word_range": [scale_plan["chapter_word_min"], scale_plan["chapter_word_max"]],
                }
            )
        return candidates

    def _character_candidate(self, project: models.Project, phase: str, request: OutlineDebateRunRequest, turns: list[dict[str, Any]]) -> dict[str, Any]:
        fallback = {
            "name": f"{PHASE_CONFIG[phase]['label']}候选对手",
            "role_type": "supporting",
            "importance_level": "major" if phase == "book" else "medium",
            "summary": "用于承载阶段压力、制度执行和主角关系代价的候选角色。",
            "story_function": "把抽象秩序变成可对抗、可谈判、可误判的人。",
            "first_needed_in": {"stage": phase, "reason": request.requirement or "大纲议事发现角色承载缺口"},
            "relationship_hooks": ["与主角存在资源/身份/秘密冲突", "可连接未来伏笔回收"],
            "duplicate_check": {"strategy": "提交正典前按同名、同职能、同阵营扫描重复项", "status": "pending"},
            "activity_status": "candidate",
            "status": "candidate",
            "source": "outline_debate",
            "canon_write_suggestion": {"requires_user_approval": True, "target": "characters"},
        }
        generated = self._candidate_from_turn(turns, "CharacterGeneratorAgent", "character_candidate")
        candidate = self._deep_merge_dicts(fallback, generated) if generated else fallback
        candidate["name"] = self._string_or(candidate.get("name"), fallback["name"])
        candidate["activity_status"] = "candidate"
        candidate["status"] = "candidate"
        candidate["source"] = "outline_debate"
        suggestion = candidate.get("canon_write_suggestion") if isinstance(candidate.get("canon_write_suggestion"), dict) else {}
        suggestion.update({"requires_user_approval": True, "target": "characters"})
        candidate["canon_write_suggestion"] = suggestion
        return candidate

    def _setting_candidate(self, project: models.Project, phase: str, request: OutlineDebateRunRequest, turns: list[dict[str, Any]]) -> dict[str, Any]:
        fallback = {
            "title": f"{PHASE_CONFIG[phase]['label']}候选规则",
            "ref_type": "world_fact",
            "category": "politics" if "权谋" in project.genre else "magic_rule",
            "content": "用于解释阶段压迫来源、资源分配和主角破局代价的候选设定。",
            "first_needed_in": {"stage": phase, "reason": request.requirement or "大纲议事发现设定驱动缺口"},
            "conflict_utility": "让主角目标和既有秩序产生明确碰撞。",
            "foreshadowing_utility": "可在前期以制度细节、禁忌或异常判罚预埋。",
            "continuity_check": {"uncertainties": ["是否与既有故事圣经冲突"], "status": "pending_user_review"},
            "activity_status": "candidate",
            "status": "candidate",
            "source": "outline_debate",
            "canon_write_suggestion": {"requires_user_approval": True, "target": "world_facts"},
        }
        generated = self._candidate_from_turn(turns, "SettingGeneratorAgent", "setting_candidate")
        candidate = self._deep_merge_dicts(fallback, generated) if generated else fallback
        candidate["title"] = self._string_or(candidate.get("title"), fallback["title"])
        candidate["activity_status"] = "candidate"
        candidate["status"] = "candidate"
        candidate["source"] = "outline_debate"
        suggestion = candidate.get("canon_write_suggestion") if isinstance(candidate.get("canon_write_suggestion"), dict) else {}
        suggestion.update({"requires_user_approval": True, "target": "world_facts"})
        candidate["canon_write_suggestion"] = suggestion
        return candidate

    def _candidate_from_turn(self, turns: list[dict[str, Any]], agent_suffix: str, key: str) -> dict[str, Any]:
        for turn in turns:
            if not turn.get("agent_name", "").endswith(agent_suffix):
                continue
            value = turn.get(key)
            if isinstance(value, dict) and value:
                return value
        return {}

    def _build_artifacts(
        self,
        project: models.Project,
        phase: str,
        request: OutlineDebateRunRequest,
        result: dict[str, Any],
        turns: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        candidate_policy = self._candidate_policy(phase, request, turns)
        artifacts = [
            {
                "id": generate_id("art"),
                "type": PHASE_CONFIG[phase]["result_key"],
                "title": PHASE_CONFIG[phase]["result_title"],
                "payload": result,
                "requires_user_confirmation": True,
            }
        ]
        if candidate_policy["character_gap"]["required"]:
            character_candidate = self._character_candidate(project, phase, request, turns)
            artifacts.append(
                {
                    "id": generate_id("art"),
                    "type": "character_candidate",
                    "title": character_candidate["name"],
                    "payload": character_candidate,
                    "requires_user_confirmation": True,
                }
            )
        if candidate_policy["setting_gap"]["required"]:
            setting_candidate = self._setting_candidate(project, phase, request, turns)
            artifacts.append(
                {
                    "id": generate_id("art"),
                    "type": "setting_candidate",
                    "title": setting_candidate["title"],
                    "payload": setting_candidate,
                    "requires_user_confirmation": True,
                }
            )
        return artifacts, candidate_policy

    def _candidate_policy(self, phase: str, request: OutlineDebateRunRequest, turns: list[dict[str, Any]]) -> dict[str, Any]:
        text_parts = [request.requirement]
        for turn in turns:
            text_parts.extend(
                [
                    str(turn.get("message", "")),
                    " ".join(str(item) for item in turn.get("claims", []) if item),
                    " ".join(str(item) for item in turn.get("risks", []) if item),
                ]
            )
        text = "\n".join(text_parts)
        character_generated = bool(self._candidate_from_turn(turns, "CharacterGeneratorAgent", "character_candidate"))
        setting_generated = bool(self._candidate_from_turn(turns, "SettingGeneratorAgent", "setting_candidate"))
        character_required = character_generated or self._has_candidate_gap_signal(text, "character")
        setting_required = setting_generated or self._has_candidate_gap_signal(text, "setting")
        return {
            "phase": phase,
            "character_gap": {
                "required": character_required,
                "reason": "远程 Agent 已返回候选角色" if character_generated else ("讨论文本明确存在角色缺口" if character_required else "未发现明确角色缺口"),
                "source": "agent_candidate" if character_generated else ("discussion_signal" if character_required else "not_needed"),
            },
            "setting_gap": {
                "required": setting_required,
                "reason": "远程 Agent 已返回候选设定" if setting_generated else ("讨论文本明确存在设定缺口" if setting_required else "未发现明确设定缺口"),
                "source": "agent_candidate" if setting_generated else ("discussion_signal" if setting_required else "not_needed"),
            },
        }

    def _has_candidate_gap_signal(self, text: str, gap_type: str) -> bool:
        compact = "".join(text.split())
        if gap_type == "character":
            negative_patterns = ("不新增角色", "无需新增角色", "不需要新增角色", "不生成角色", "不补角色", "不新增角色或设定", "不新增设定或角色")
            positive_patterns = ("缺角色", "角色缺口", "补角色", "新增角色", "候选角色", "角色候选", "角色承载缺口")
        else:
            negative_patterns = ("不新增设定", "无需新增设定", "不需要新增设定", "不生成设定", "不补设定", "不新增角色或设定", "不新增设定或角色")
            positive_patterns = ("缺设定", "设定缺口", "缺规则", "规则缺口", "补设定", "补规则", "新增设定", "新增规则", "候选设定", "候选规则")
        if any(pattern in compact for pattern in negative_patterns):
            return False
        return any(pattern in compact for pattern in positive_patterns)

    def _validation_report(
        self,
        phase: str,
        result: dict[str, Any],
        artifacts: list[dict[str, Any]],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        checks = [self._schema_validation_check(phase, result)]
        if phase == "volumes":
            checks.append(self._rhythm_model_check(result))
        if phase == "chapters":
            checks.append(self._crisis_climax_result_check(result))
        duplicate_check = self._duplicate_candidate_check(artifacts, context)
        if duplicate_check:
            checks.append(duplicate_check)
        checks.append(self._continuity_check(context))
        status = "passed"
        if any(check["status"] == "failed" for check in checks):
            status = "failed"
        elif any(check["status"] == "warning" for check in checks):
            status = "warning"
        return {
            "status": status,
            "checked_at": utcnow().isoformat(),
            "checks": checks,
        }

    def _schema_validation_check(self, phase: str, result: dict[str, Any]) -> dict[str, Any]:
        issues: list[str] = []
        if phase == "book":
            book_outline = result.get("book_outline") if isinstance(result.get("book_outline"), dict) else {}
            for key in ("core_promise", "main_conflict", "ending_direction", "reader_experience"):
                if book_outline.get(key) in (None, "", [], {}):
                    issues.append(f"book_outline.{key} 为空")
        elif phase == "volumes":
            volume_outlines = result.get("volume_outlines") if isinstance(result.get("volume_outlines"), list) else []
            if not volume_outlines:
                issues.append("volume_outlines 为空")
            for index, item in enumerate(volume_outlines, start=1):
                if not isinstance(item, dict):
                    issues.append(f"volume_outlines[{index}] 不是 object")
                    continue
                for key in ("volume_no", "title", "volume_function", "rhythm_model", "core_goal", "volume_hook"):
                    if item.get(key) in (None, "", [], {}):
                        issues.append(f"volume_outlines[{index}].{key} 为空")
        else:
            chapter_outlines = result.get("chapter_outlines") if isinstance(result.get("chapter_outlines"), list) else []
            if not chapter_outlines:
                issues.append("chapter_outlines 为空")
            for index, item in enumerate(chapter_outlines, start=1):
                if not isinstance(item, dict):
                    issues.append(f"chapter_outlines[{index}] 不是 object")
                    continue
                for key in ("chapter_no", "title", "outline", "pov_character", "core_event", "conflict", "crisis", "climax", "result", "cliffhanger"):
                    if item.get(key) in (None, "", [], {}):
                        issues.append(f"chapter_outlines[{index}].{key} 为空")
        return {
            "validator": "schema_validator",
            "status": "failed" if issues else "passed",
            "message": "结构字段完整" if not issues else "结构字段不完整",
            "issues": issues,
        }

    def _rhythm_model_check(self, result: dict[str, Any]) -> dict[str, Any]:
        issues: list[str] = []
        volume_outlines = result.get("volume_outlines") if isinstance(result.get("volume_outlines"), list) else []
        for index, item in enumerate(volume_outlines, start=1):
            if not isinstance(item, dict):
                continue
            rhythm_model = item.get("rhythm_model") if isinstance(item.get("rhythm_model"), dict) else {}
            for key in ("model_name", "why_this_model", "phase_count", "chapter_distribution"):
                if rhythm_model.get(key) in (None, "", [], {}):
                    issues.append(f"volume_outlines[{index}].rhythm_model.{key} 为空")
        return {
            "validator": "rhythm_model_selector",
            "status": "failed" if issues else "passed",
            "message": "卷纲包含节奏模型选择依据" if not issues else "卷纲节奏模型信息不足",
            "issues": issues,
        }

    def _crisis_climax_result_check(self, result: dict[str, Any]) -> dict[str, Any]:
        issues: list[str] = []
        chapter_outlines = result.get("chapter_outlines") if isinstance(result.get("chapter_outlines"), list) else []
        for index, item in enumerate(chapter_outlines, start=1):
            if not isinstance(item, dict):
                continue
            crisis = str(item.get("crisis") or "").strip()
            climax = str(item.get("climax") or "").strip()
            outcome = str(item.get("result") or "").strip()
            if not crisis or not climax or not outcome:
                issues.append(f"chapter_outlines[{index}] 缺少危机/高潮/结果")
                continue
            if len({crisis, climax, outcome}) < 3:
                issues.append(f"chapter_outlines[{index}] 危机、高潮、结果不应完全相同")
        return {
            "validator": "crisis_climax_result_checker",
            "status": "failed" if issues else "passed",
            "message": "章纲已区分危机、高潮、结果" if not issues else "章纲未严格区分危机、高潮、结果",
            "issues": issues,
        }

    def _duplicate_candidate_check(self, artifacts: list[dict[str, Any]], context: dict[str, Any]) -> dict[str, Any] | None:
        candidate_names: list[tuple[str, str]] = []
        for artifact in artifacts:
            if artifact.get("type") == "character_candidate" and isinstance(artifact.get("payload"), dict):
                candidate_names.append(("character", str(artifact["payload"].get("name") or "")))
            if artifact.get("type") == "setting_candidate" and isinstance(artifact.get("payload"), dict):
                candidate_names.append(("setting", str(artifact["payload"].get("title") or "")))
        if not candidate_names:
            return None
        canon_context = context.get("canon_context") if isinstance(context.get("canon_context"), dict) else {}
        existing_character_names = {str(item.get("name") or "") for item in canon_context.get("characters", []) if isinstance(item, dict)}
        existing_setting_titles = {str(item.get("title") or "") for item in canon_context.get("world_facts", []) if isinstance(item, dict)}
        issues = []
        for kind, name in candidate_names:
            if kind == "character" and name and name in existing_character_names:
                issues.append(f"候选角色可能重复：{name}")
            if kind == "setting" and name and name in existing_setting_titles:
                issues.append(f"候选设定可能重复：{name}")
        return {
            "validator": "duplicate_scanner",
            "status": "warning" if issues else "passed",
            "message": "候选重复项扫描完成",
            "issues": issues,
        }

    def _continuity_check(self, context: dict[str, Any]) -> dict[str, Any]:
        canon_context = context.get("canon_context") if isinstance(context.get("canon_context"), dict) else {}
        issues = canon_context.get("unresolved_continuity_issues") if isinstance(canon_context.get("unresolved_continuity_issues"), list) else []
        return {
            "validator": "continuity_checker",
            "status": "warning" if issues else "passed",
            "message": "存在未关闭连续性问题，阶段候选需人工确认" if issues else "未发现未关闭连续性问题",
            "issues": [str(item.get("message") or item) for item in issues[:10]],
        }

    def _build_decisions(
        self,
        phase: str,
        request: OutlineDebateRunRequest,
        result: dict[str, Any],
        candidate_policy: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        candidate_policy = candidate_policy or {}
        character_gap = candidate_policy.get("character_gap") if isinstance(candidate_policy.get("character_gap"), dict) else {}
        setting_gap = candidate_policy.get("setting_gap") if isinstance(candidate_policy.get("setting_gap"), dict) else {}
        gap_decision = "本阶段未发现必须新增角色或设定的明确缺口。"
        gap_rationale = "角色/设定生成 Agent 只在缺口明确时输出候选；对应大纲候选确认后由服务层入库。"
        if character_gap.get("required") and setting_gap.get("required"):
            gap_decision = "本阶段发现角色与设定缺口，分别生成候选 artifact，并将在确认本阶段候选时入库。"
            gap_rationale = f"{character_gap.get('reason', '')}；{setting_gap.get('reason', '')}"
        elif character_gap.get("required"):
            gap_decision = "本阶段发现角色缺口，生成候选角色 artifact，并将在确认本阶段候选时入库。"
            gap_rationale = str(character_gap.get("reason") or "讨论文本明确存在角色缺口")
        elif setting_gap.get("required"):
            gap_decision = "本阶段发现设定缺口，生成候选设定 artifact，并将在确认本阶段候选时入库。"
            gap_rationale = str(setting_gap.get("reason") or "讨论文本明确存在设定缺口")
        return [
            {
                "id": generate_id("dec"),
                "phase": phase,
                "title": f"{PHASE_CONFIG[phase]['label']}边界",
                "decision": "讨论阶段只产候选，不直接写入正式数据；确认对应候选时写入正式正典。",
                "rationale": "保持生成候选、用户确认、服务层物化和版本审计的边界。",
            },
            {
                "id": generate_id("dec"),
                "phase": phase,
                "title": "角色与设定补全",
                "decision": gap_decision,
                "rationale": gap_rationale,
            },
            {
                "id": generate_id("dec"),
                "phase": phase,
                "title": "输出结构",
                "decision": f"输出 `{result['generation_kind']}`，拓扑开关只改变解释视图，不减少内容量。",
                "rationale": "保证 topology 与 linear 模式结果结构基本相似。",
            },
        ]

    def _build_topology(
        self,
        phase: str,
        request: OutlineDebateRunRequest,
        turns: list[dict[str, Any]],
        decisions: list[dict[str, Any]],
        artifacts: list[dict[str, Any]],
    ) -> dict[str, Any]:
        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []
        events: list[dict[str, Any]] = []
        previous_id = ""
        for turn in turns:
            node_id = f"turn:{turn['id']}"
            nodes.append(
                {
                    "id": node_id,
                    "label": turn["role"],
                    "type": "agent",
                    "status": "succeeded",
                    "summary": turn["message"],
                    "agent_name": turn["agent_name"],
                    "payload": {
                        "stance": turn["stance"],
                        "claims": turn["claims"],
                        "risks": turn["risks"],
                        "llm": turn.get("_llm", {}),
                        "agent_spec": turn.get("agent_spec", self._agent_spec(turn["agent_name"])),
                    },
                }
            )
            events.append({"id": generate_id("evt"), "type": "turn", "agent_name": turn["agent_name"], "node_id": node_id, "payload": turn})
            if previous_id:
                edges.append({"id": generate_id("edge"), "source": previous_id, "target": node_id, "type": "handoff", "label": "议事交接", "reason": "按讨论顺序推进"})
            previous_id = node_id
        source_id = previous_id
        for decision in decisions:
            node_id = f"decision:{decision['id']}"
            nodes.append({"id": node_id, "label": decision["title"], "type": "decision", "status": "succeeded", "summary": decision["decision"], "payload": decision})
            edges.append({"id": generate_id("edge"), "source": source_id, "target": node_id, "type": "approves", "label": "形成决议", "reason": decision["rationale"]})
            events.append({"id": generate_id("evt"), "type": "decision", "node_id": node_id, "payload": decision})
        for artifact in artifacts:
            node_id = f"artifact:{artifact['id']}"
            nodes.append({"id": node_id, "label": artifact["title"], "type": "artifact", "status": "needs_user_review", "summary": artifact["type"], "payload": artifact})
            edges.append({"id": generate_id("edge"), "source": source_id, "target": node_id, "type": "emits", "label": "输出候选", "reason": artifact["type"]})
            events.append({"id": generate_id("evt"), "type": "artifact", "node_id": node_id, "payload": artifact})
        return {
            "mode": "topology" if request.use_topology_inference else "linear",
            "generation_kind": PHASE_CONFIG[phase]["generation_kind"],
            "nodes": nodes,
            "edges": edges,
            "events": events,
            "artifacts": artifacts,
            "metrics": {
                "mode": "topology" if request.use_topology_inference else "linear",
                "node_count": len(nodes),
                "edge_count": len(edges),
                "event_count": len(events),
                "artifact_count": len(artifacts),
                "agent_count": len(turns),
            },
        }

    def _finalize_round_phase(
        self,
        db: Session,
        job: models.GenerationJob,
        project: models.Project,
        session: dict[str, Any],
        phase: str,
        request: OutlineDebateRunRequest,
        phase_run: dict[str, Any],
    ) -> None:
        previous_phase_run = loads(dumps(phase_run), {}) if self._is_itemized_phase(phase) else None
        turns = phase_run.get("turns", [])
        orchestrator = OutlineDebateOrchestrator(self)
        context = self._phase_context(db, project, session, phase, request)
        agenda = phase_run.get("agenda") if isinstance(phase_run.get("agenda"), dict) else orchestrator.build_agenda(phase, request, context)
        deliberation_state = phase_run.get("deliberation_state") if isinstance(phase_run.get("deliberation_state"), dict) else orchestrator.initial_state(agenda, request)
        if not deliberation_state.get("turn_ids"):
            for turn in turns:
                orchestrator.apply_turn_to_state(deliberation_state, turn)
        cross_review = orchestrator.cross_review(deliberation_state, turns)
        result = orchestrator.synthesize_candidate_artifact(project, phase, request, turns, session, deliberation_state)
        artifacts, candidate_policy = self._build_artifacts(project, phase, request, result, turns)
        validation_report = orchestrator.validate_result(phase, result, artifacts, context)
        decisions = orchestrator.request_revision_or_finish(phase, request, result, candidate_policy, deliberation_state)
        topology = self._build_topology(phase, request, turns, decisions, artifacts)
        phase_run.update(
            {
                "status": "succeeded",
                "finished_at": utcnow().isoformat(),
                "agent_specs": self._agent_specs(),
                "candidate_policy": candidate_policy,
                "validation_report": validation_report,
                "decisions": decisions,
                "artifacts": artifacts,
                "outline_topology": topology,
                "debate_protocol": orchestrator.protocol(agenda, deliberation_state, cross_review, validation_report),
                "deliberation_state": deliberation_state,
                "result": result,
                "next_agent_name": "",
            }
        )
        self._mark_phase_run_pending(phase_run)
        if self._is_itemized_phase(phase):
            merged = self._merge_itemized_phase_run(previous_phase_run, phase_run, request)
            session.setdefault("phase_runs", {})[phase] = merged
            if merged is not phase_run:
                phase_run.clear()
                phase_run.update(merged)
        completed = len([run for run in session.get("phase_runs", {}).values() if isinstance(run, dict) and run.get("status") == "succeeded"])
        session["status"] = "succeeded" if completed >= len(session.get("phase_order", [])) else "in_progress"
        session["updated_at"] = utcnow().isoformat()
        job.current_agent = ""
        job.progress_json = dumps(
            {
                "current_step": phase,
                "total_steps": 3,
                "completed_steps": completed,
                "message": f"{PHASE_CONFIG[phase]['label']}已形成阶段结论",
            }
        )
        job.heartbeat_at = utcnow()
        if completed >= 3:
            job.status = "succeeded"
            job.finished_at = utcnow()
        job.result_json = dumps({"session": session})

    def _record_turn_runs(self, db: Session, job: models.GenerationJob, phase_run: dict[str, Any]) -> None:
        for turn in phase_run["turns"]:
            self._record_single_turn_run(db, job, phase_run, turn)

    def _record_single_turn_run(self, db: Session, job: models.GenerationJob, phase_run: dict[str, Any], turn: dict[str, Any]) -> None:
        db.add(
            models.AgentRun(
                id=generate_id("agn"),
                job_id=job.id,
                project_id=job.project_id,
                chapter_id=None,
                agent_name=turn["agent_name"],
                agent_role=turn["role"],
                status="succeeded",
                input_payload_json=dumps({"phase": phase_run["phase"], "input": phase_run["input"]}),
                output_payload_json=dumps({"turn": turn, "phase_run_id": phase_run["id"], "source": "outline_debate"}),
                started_at=utcnow(),
                finished_at=utcnow(),
            )
        )


outline_debate_service = OutlineDebateService()
