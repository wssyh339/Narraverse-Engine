from __future__ import annotations

import asyncio
import queue
import re
import threading
from pathlib import Path
from typing import Any, Iterable

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.agents.llm_io import call_agent_json
from app.core.config import LLMProviderResolver, get_settings
from app.core.ids import generate_id
from app.core.json import dumps, loads
from app.db import models
from app.db.models import utcnow
from app.db.session import SessionLocal
from app.schemas.outline import (
    OutlineDebateChapterAutopilotRequest,
    OutlineDebateCommitRequest,
    OutlineDebateConfirmRequest,
    OutlineDebateInterruptRequest,
    OutlineDebateRunRequest,
    OutlineDebateSessionCreateRequest,
    OutlineDebateUserMessageRequest,
)
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


DEFAULT_CHAPTER_WORD_TARGET = 8000
DEFAULT_CHAPTER_WINDOWS_PER_VOLUME = 5
OUTLINE_TEMPLATE_BLOCKLIST = (
    "待确认",
    "本章核心事件待确认",
    "本章冲突待确认",
    "本章危机待确认",
    "本章高潮待确认",
    "本章结果待确认",
    "第{chapter_no}章围绕本章核心事件推进一次行动、阻碍和后果",
    "围绕本章核心事件推进一次行动、阻碍和后果",
    "本章危机是主角必须作出不可逆选择",
    "本章高潮是主角执行选择并付出可见代价",
    "本章结果改变局面",
    "留下下一章必须回应的问题",
    "根据类型、读者体验和阶段冲突选择",
)
STATE_CHANGE_AXES = ("压力", "认知", "资源", "关系", "规则", "秘密", "代价", "目标")
FORESHADOWING_ACTIONS = ("plant", "remind", "mislead", "payoff")

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
    ("outline_debate/StoryDirectorAgent", "主持总策划席位"),
    ("outline_debate/MarketPositionAgent", "类型卖点席位"),
    ("outline_debate/StructureDoctorAgent", "结构医生席位"),
    ("outline_debate/CharacterGeneratorAgent", "角色生成席位"),
    ("outline_debate/SettingGeneratorAgent", "设定生成席位"),
    ("outline_debate/ContinuityAuditorAgent", "连续性审计席位"),
)
DEBATE_AGENT_ROLES = dict(DEBATE_AGENTS)
STORY_DIRECTOR_AGENT = "outline_debate/StoryDirectorAgent"
MARKET_POSITION_AGENT = "outline_debate/MarketPositionAgent"
STRUCTURE_DOCTOR_AGENT = "outline_debate/StructureDoctorAgent"
CHARACTER_GENERATOR_AGENT = "outline_debate/CharacterGeneratorAgent"
SETTING_GENERATOR_AGENT = "outline_debate/SettingGeneratorAgent"
CONTINUITY_AUDITOR_AGENT = "outline_debate/ContinuityAuditorAgent"
GENERATOR_AGENTS = {CHARACTER_GENERATOR_AGENT, SETTING_GENERATOR_AGENT}

DEBATE_AGENT_SYSTEM_PROMPTS: dict[str, str] = {
    "outline_debate/StoryDirectorAgent": (
        "你是大纲讨论组的主持总策划席位。你的能力是收束作品承诺、核心矛盾、阶段边界和候选产物。"
        "你必须读取 context 中的 Star 立项种子、项目资料、已确认正典和上游阶段结果。"
        "你还必须根据专席评分、阻塞项和用户插话决定下一位发言者，并输出 adopted/rejected/pending 的裁决。"
        "本轮发言不直接写库；用户确认本阶段后，服务层会把已确认的大纲、角色和设定条目立即写入正式正典。"
        "真实模型输出的 message/claims/risks 必须以中文为主，接口字段名可保留英文。"
    ),
    "outline_debate/MarketPositionAgent": (
        "你是类型卖点席位。你的能力是判断频道、类型、爽点、压迫感、情感拉扯、平台期待、追读理由和兑现节奏。"
        "你必须把读者体验转成可持续冲突、章节钩子、伏笔兑现和风险提示，不得生成空泛营销话术。"
        "真实模型输出的 message/claims/risks 必须以中文为主，接口字段名可保留英文。"
    ),
    "outline_debate/StructureDoctorAgent": (
        "你是结构医生席位。你的能力是检查长篇因果链、节奏模型、危机/高潮/结果边界、卷章功能和返工点。"
        "必须严格区分：危机是不可逆选择，高潮是执行选择，结果是承担后果。"
        "真实模型输出的 message/claims/risks 必须以中文为主，接口字段名可保留英文。"
    ),
    "outline_debate/CharacterGeneratorAgent": (
        "你是角色生成席位。你的能力是审查人物功能、关系压力、重复风险和首次需要时机。"
        "不要因轻量提及就生成完整角色卡；只有用户/主持明确要求，或角色达到中等以上重要度、影响主线/伏笔/关系压力/正典连续性时，才生成角色档案卡候选。"
        "角色必须先规划全书预计角色总量、重要性分布和本阶段新增数量；候选列表按 importance_score 递减。"
        "每张角色卡必须覆盖设定页角色字段，并兼容创作 Star 主角模板字段。"
        "讨论发言阶段不调用 characters 写入；用户确认对应阶段或条目后，由服务层立即入库，不再进入二次候选审批。"
        "真实模型输出的 message/claims/risks 必须以中文为主，接口字段名可保留英文。"
    ),
    "outline_debate/SettingGeneratorAgent": (
        "你是设定生成席位。你的能力是审查规则成本、设定冲突用途、揭示时机、伏笔用途和连续性风险。"
        "不要因轻量提及就生成完整设定；只有用户/主持明确要求，或设定达到中等以上重要度、影响选择代价/主线冲突/伏笔/正典连续性时，才生成设定候选。"
        "设定必须覆盖设定页实体或世界观事实展示字段，并说明冲突用途、限制、成本、伏笔用途、连续性风险和确认入库边界。讨论发言阶段不调用 world_facts 或 graph 写入；用户确认对应阶段或条目后，由服务层立即入库，不再进入二次候选审批。"
        "真实模型输出的 message/claims/risks 必须以中文为主，接口字段名可保留英文。"
    ),
    "outline_debate/ContinuityAuditorAgent": (
        "你是连续性审计席位。你的能力是标记不确定项、冲突风险、缺失来源、阻塞问题和需要用户确认的变更。"
        "你必须给出 pass/revise/blocked 裁决；不确定不得硬编；存在 blocking_items 时不得建议直接确认。"
        "只有用户确认阶段或条目后，正式正典变更才会由服务层直接写入。"
        "真实模型输出的 message/claims/risks 必须以中文为主，接口字段名可保留英文。"
    ),
}

DEBATE_AGENT_SKILL_SPECS: dict[str, dict[str, Any]] = {
    "outline_debate/StoryDirectorAgent": {
        "core_capability": "主持讨论、路由专席、收束作品承诺、主线冲突、阶段目标和候选结论。",
        "skill_file": "app/prompts/outline_debate_story_director_skill.md",
        "skills": ["长篇主线设计 skill", "冲突发动机 skill", "终局反推 skill", "议程压缩 skill", "专席路由 skill", "采纳否决裁决 skill"],
        "required_context_keys": ["project", "story_bible", "canon_context", "scale_plan", "upstream_phase_runs", "requirement"],
        "allowed_read_tools": ["get_project_state", "get_story_bible", "get_canon_context", "list_volumes", "list_chapters"],
        "allowed_candidate_tools": ["record_outline_piece", "record_debate_decision", "route_to_agent", "close_round", "build_outline_topology", "create_uncertainty_ticket"],
        "validators": ["schema_validator", "impact_analyzer"],
        "forbidden_tools": ["direct_formal_outline_write", "createCharacter", "createWorldFact", "createEntity"],
        "candidate_policy": "只形成待确认大纲条目；用户确认阶段后由服务层立即写入正式大纲和正典。",
    },
    "outline_debate/MarketPositionAgent": {
        "core_capability": "判断目标读者体验、类型卖点、压迫感、追读理由和期待兑现。",
        "skill_file": "app/prompts/outline_debate_market_position_skill.md",
        "skills": ["类型文卖点识别 skill", "目标读者体验建模 skill", "追读承诺账本 skill", "爽点兑现延期判断 skill", "前三章与卷末期待管理 skill"],
        "required_context_keys": ["project", "story_bible", "canon_context", "scale_plan", "requirement"],
        "allowed_read_tools": ["get_project_state", "get_story_bible", "get_canon_context", "list_chapters", "list_foreshadowing"],
        "allowed_candidate_tools": ["record_outline_piece", "create_completion_ticket"],
        "validators": ["schema_validator", "impact_analyzer"],
        "forbidden_tools": ["direct_formal_outline_write", "createCharacter", "createWorldFact", "createEntity"],
        "candidate_policy": "只把市场判断转译为冲突、钩子和风险；如需新增设定，交给设定生成席位，并在用户确认后直接入库。",
    },
    "outline_debate/StructureDoctorAgent": {
        "core_capability": "检查长篇结构、卷节奏、章节因果，以及危机/高潮/结果边界。",
        "skill_file": "app/prompts/outline_debate_structure_doctor_skill.md",
        "skills": ["节奏模型选择 skill", "危机高潮结果区分 skill", "长篇因果链检查 skill", "十章节奏窗 skill", "反派压力线结构检查 skill", "章纲密度控制 skill"],
        "required_context_keys": ["project", "story_bible", "canon_context", "scale_plan", "upstream_phase_runs", "requirement"],
        "allowed_read_tools": ["get_project_state", "get_story_bible", "get_canon_context", "list_volumes", "list_chapters", "list_foreshadowing", "get_graph"],
        "allowed_candidate_tools": ["record_outline_piece", "create_completion_ticket"],
        "validators": ["schema_validator", "rhythm_model_selector", "crisis_climax_result_checker", "impact_analyzer"],
        "forbidden_tools": ["direct_formal_outline_write", "createCharacter", "createWorldFact", "createEntity"],
        "candidate_policy": "只校正结构候选；发现结构阻塞时登记返工建议。",
    },
    "outline_debate/CharacterGeneratorAgent": {
        "core_capability": "审查人物功能与关系压力，并在达到触发门槛时生成候选角色卡。",
        "skill_file": "app/prompts/outline_debate_character_generator_skill.md",
        "skills": ["角色功能识别 skill", "人物功能审计 skill", "人物卡生成 skill", "角色关系钩子 skill", "重复角色识别 skill", "反派压力线协作 skill", "活跃状态重要度分类 skill"],
        "required_context_keys": ["project", "canon_context.characters", "canon_context.graph", "scale_plan", "requirement"],
        "allowed_read_tools": ["get_canon_context", "list_characters", "list_chapters", "list_foreshadowing", "get_graph"],
        "allowed_candidate_tools": ["create_character_candidate", "create_relationship_candidate", "record_outline_piece", "create_uncertainty_ticket"],
        "validators": ["schema_validator", "duplicate_scanner", "impact_analyzer"],
        "forbidden_tools": ["createCharacter", "direct_formal_outline_write"],
        "candidate_policy": "先输出 character_function_audit；只有用户/主持明确要求、重要度达到 medium 以上、存在 first_needed_in，或影响主线/伏笔/关系压力/正典连续性时，才生成完整 character_candidates；候选按 importance_score 递减，用户确认对应总纲/卷纲/章纲条目后由服务层立即入库，不进入二次审批。",
    },
    "outline_debate/SettingGeneratorAgent": {
        "core_capability": "审查设定冲突用途、规则成本和揭示时机，并在达到触发门槛时生成候选设定。",
        "skill_file": "app/prompts/outline_debate_setting_generator_skill.md",
        "skills": ["世界规则生成 skill", "规则成本检查 skill", "组织地点物件制度生成 skill", "设定冲突用途分析 skill", "设定揭示节奏 skill", "伏笔用途分析 skill", "正典候选归类 skill"],
        "required_context_keys": ["project", "canon_context.entities", "canon_context.world_facts", "canon_context.graph", "scale_plan", "requirement"],
        "allowed_read_tools": ["get_canon_context", "list_entities", "list_world_facts", "list_chapters", "get_graph", "list_foreshadowing"],
        "allowed_candidate_tools": ["create_setting_candidate", "create_graph_relation_candidate", "record_outline_piece", "create_uncertainty_ticket"],
        "validators": ["schema_validator", "duplicate_scanner", "continuity_checker", "impact_analyzer"],
        "forbidden_tools": ["createWorldFact", "createEntity", "direct_formal_outline_write"],
        "candidate_policy": "先输出 setting_function_audit；只有用户/主持明确要求、重要度达到 medium 以上、存在 first_needed_in，或影响选择代价/主线冲突/伏笔/正典连续性时，才生成完整 setting_candidates；候选按 importance_score 递减，用户确认对应总纲/卷纲/章纲条目后由服务层立即入库，不进入二次审批。",
    },
    "outline_debate/ContinuityAuditorAgent": {
        "core_capability": "审计连续性、正典冲突、伏笔账本、时间线和不确定项。",
        "skill_file": "app/prompts/outline_debate_continuity_auditor_skill.md",
        "skills": ["连续性审计 skill", "正典冲突检测 skill", "伏笔账本检查 skill", "时间线检查 skill", "阻塞项裁决 skill", "不确定项登记 skill"],
        "required_context_keys": ["project", "story_bible", "canon_context", "scale_plan", "upstream_phase_runs", "requirement"],
        "allowed_read_tools": ["get_project_state", "get_story_bible", "get_canon_context", "list_characters", "list_entities", "list_world_facts", "get_graph", "list_foreshadowing", "list_chapters"],
        "allowed_candidate_tools": ["create_uncertainty_ticket", "create_completion_ticket", "create_blocking_ticket", "record_outline_piece"],
        "validators": ["schema_validator", "continuity_checker", "crisis_climax_result_checker", "impact_analyzer"],
        "forbidden_tools": ["createCharacter", "createWorldFact", "createEntity", "direct_formal_outline_write"],
        "candidate_policy": "只输出风险、证据、blocking_items 和待确认项；不得把不确定内容写成正式正典；存在阻塞项时不得建议直接确认。",
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
    "chapter_windows": "章节窗口",
    "window_no": "窗口序号",
    "window_range": "窗口范围",
    "window_goal": "窗口目标",
    "window_function": "窗口功能",
    "chapter_word_max": "单章最高字数",
    "chapter_word_min": "单章最低字数",
    "chapter_word_target": "单章目标字数",
    "chapters": "章节",
    "chapters_per_volume": "每卷章节数",
    "character_candidate": "角色候选",
    "character_candidates": "角色候选列表",
    "character_count_plan": "角色数量规划",
    "claims": "关键主张",
    "cliffhanger": "章末钩子",
    "climax": "高潮",
    "confidence": "置信度",
    "decision": "裁决",
    "decision_source": "裁决来源",
    "scores": "评分",
    "score_source": "评分来源",
    "blocking_items": "阻塞项",
    "must_fix_before_confirm": "确认前必须修复",
    "challenge_targets": "质询对象",
    "response_to_objections": "回应质询",
    "adopted": "采纳项",
    "rejected": "否决项",
    "pending": "待定项",
    "next_agent": "建议下一席",
    "reader_promise_audit": "读者承诺审计",
    "structure_audit": "结构审计",
    "character_function_audit": "人物功能审计",
    "setting_function_audit": "设定功能审计",
    "candidate_trigger": "候选触发门槛",
    "audit_status": "审计状态",
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
    "quality_metrics": "质量指标",
    "state_change": "状态改变",
    "state_change_goal": "状态变化目标",
    "state_change_text": "状态改变说明",
    "foreshadowing_use": "伏笔用途",
    "foreshadowing_window_coverage": "伏笔窗口覆盖率",
    "source_window": "来源窗口",
    "source_window_detail": "来源窗口详情",
    "mini_climax": "小高潮",
    "transition_hook": "过渡钩子",
    "setting_candidate": "设定候选",
    "setting_candidates": "设定候选列表",
    "setting_count_plan": "设定数量规划",
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
                "哪些角色或设定缺口需要在本阶段确认后直接入库？",
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
            "focus_constraints": context.get("focus_constraints") or {},
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
            "character_candidates": [],
            "character_count_plan": {},
            "setting_candidate": {},
            "setting_candidates": [],
            "setting_count_plan": {},
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
    def __init__(self) -> None:
        self._chapter_autopilot_queue: queue.Queue[str] = queue.Queue()
        self._chapter_autopilot_worker_lock = threading.Lock()
        self._chapter_autopilot_worker: threading.Thread | None = None

    def validate_stream_phase_request(
        self,
        db: Session,
        project_id: str,
        session_id: str,
        phase: str,
        request: OutlineDebateRunRequest,
    ) -> None:
        """Run checks that must fail before FastAPI starts a streaming response."""
        self._validate_phase(phase)
        job = self._session_job(db, project_id, session_id)
        session = self._session_from_job(job)
        self._ensure_upstream_confirmed(session, phase, request)
        self._ensure_phase_refresh_allowed(session, phase, request)

    def start_chapter_autopilot(
        self,
        db: Session,
        project_id: str,
        session_id: str,
        request: OutlineDebateChapterAutopilotRequest,
    ) -> dict[str, Any]:
        self._project(db, project_id)
        self._session_job(db, project_id, session_id)
        start_no = int(request.start_chapter_no)
        end_no = self._chapter_autopilot_end_no(request)
        total_steps = max(1, end_no - start_no + 1)
        idem = request.idempotency_key or f"outline-debate-chapter-autopilot:{session_id}:{start_no}:{end_no}"
        existing = (
            db.query(models.GenerationJob)
            .filter(models.GenerationJob.project_id == project_id, models.GenerationJob.idempotency_key == idem)
            .first()
        )
        if existing:
            if existing.status in {"queued", "paused"}:
                self._enqueue_chapter_autopilot_job(existing.id)
            return {"job": serialize_job(existing)}
        provider = LLMProviderResolver(get_settings()).resolve(request.model)
        now = utcnow()
        result_payload = {
            "session_id": session_id,
            "project_id": project_id,
            "start_chapter_no": start_no,
            "end_chapter_no": end_no,
            "completed_chapters": [],
            "skipped_chapters": [],
            "failed_chapters": [],
        }
        job = models.GenerationJob(
            id=generate_id("job"),
            project_id=project_id,
            chapter_id=None,
            job_type="outline_debate_chapter_autopilot",
            status="queued",
            run_id=generate_id("run"),
            idempotency_key=idem,
            model=provider.model,
            request_json=dumps({"session_id": session_id, "request": request.model_dump(), "provider": provider.provider, "has_api_key": bool(provider.api_key)}),
            progress_json=dumps(
                {
                    "current_step": "queued",
                    "total_steps": total_steps,
                    "completed_steps": 0,
                    "message": "章纲议事自动推进任务已入队",
                    "start_chapter_no": start_no,
                    "end_chapter_no": end_no,
                }
            ),
            current_agent="outline_debate/chapter_autopilot",
            started_at=None,
            heartbeat_at=now,
            result_json=dumps(result_payload),
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        self._enqueue_chapter_autopilot_job(job.id)
        return {"job": serialize_job(job)}

    def _enqueue_chapter_autopilot_job(self, job_id: str) -> None:
        self._chapter_autopilot_queue.put(job_id)
        with self._chapter_autopilot_worker_lock:
            if self._chapter_autopilot_worker is not None and self._chapter_autopilot_worker.is_alive():
                return
            self._chapter_autopilot_worker = threading.Thread(
                target=self._chapter_autopilot_worker_loop,
                name="outline-debate-chapter-autopilot-worker",
                daemon=True,
            )
            self._chapter_autopilot_worker.start()

    def _chapter_autopilot_worker_loop(self) -> None:
        while True:
            job_id = self._chapter_autopilot_queue.get()
            try:
                self.run_chapter_autopilot_job(job_id)
            except Exception as exc:
                try:
                    with SessionLocal() as db:
                        job = db.get(models.GenerationJob, job_id)
                        if job is not None and job.status not in {"succeeded", "cancelled"}:
                            self._mark_chapter_autopilot_failed(db, job, exc)
                            db.commit()
                except Exception:
                    pass
            finally:
                self._chapter_autopilot_queue.task_done()

    def run_chapter_autopilot_job(self, job_id: str) -> None:
        with SessionLocal() as db:
            job = db.get(models.GenerationJob, job_id)
            if job is None or job.status in {"succeeded", "cancelled"}:
                return
            project_id = job.project_id
            session_id, request = self._chapter_autopilot_request_from_job(job)
            start_no = int(request.start_chapter_no)
            end_no = self._chapter_autopilot_end_no(request)
            result_payload = self._chapter_autopilot_result_payload(job, session_id, request)
            completed = self._chapter_autopilot_completed_numbers(result_payload)
            job.status = "running"
            job.started_at = job.started_at or utcnow()
            job.finished_at = None
            job.heartbeat_at = utcnow()
            job.current_agent = "outline_debate/chapter_autopilot"
            job.progress_json = dumps(
                self._chapter_autopilot_progress_payload(
                    request,
                    result_payload,
                    current_step="running",
                    message="章纲议事自动推进已启动",
                )
            )
            job.result_json = dumps(result_payload)
            db.commit()

        for chapter_no in range(start_no, end_no + 1):
            with SessionLocal() as db:
                job = db.get(models.GenerationJob, job_id)
                if job is None:
                    return
                project_id = job.project_id
                session_id, request = self._chapter_autopilot_request_from_job(job)
                result_payload = self._chapter_autopilot_result_payload(job, session_id, request)
                completed = self._chapter_autopilot_completed_numbers(result_payload)
                if chapter_no in completed:
                    continue
                if job.cancel_requested or job.status == "cancelled":
                    self._mark_chapter_autopilot_cancelled(db, job, request, result_payload)
                    db.commit()
                    return
                if job.status == "paused":
                    job.heartbeat_at = utcnow()
                    job.progress_json = dumps(
                        self._chapter_autopilot_progress_payload(
                            request,
                            result_payload,
                            current_step="paused",
                            current_chapter_no=chapter_no,
                            message="章纲议事自动推进已暂停，将从未完成章节继续",
                        )
                    )
                    db.commit()
                    return
                if self._chapter_candidate_already_confirmed(db, project_id, session_id, chapter_no) and not request.force_refresh_confirmed:
                    self._record_chapter_autopilot_success(db, job, request, result_payload, chapter_no, skipped=True)
                    db.commit()
                    continue
                volume_no = self._chapter_autopilot_volume_no(request, chapter_no)
                job.status = "running"
                job.current_agent = f"outline_debate/chapter_autopilot:chapter_{chapter_no}"
                job.heartbeat_at = utcnow()
                job.progress_json = dumps(
                    self._chapter_autopilot_progress_payload(
                        request,
                        result_payload,
                        current_step=f"chapter_{chapter_no}",
                        current_chapter_no=chapter_no,
                        message=f"正在议事并确认第{chapter_no}章章纲",
                    )
                )
                db.commit()

            try:
                volume_no = self._chapter_autopilot_volume_no(request, chapter_no)
                run_request = self._chapter_autopilot_run_request(request, volume_no, chapter_no)
                with SessionLocal() as db:
                    self.run_phase(db, project_id, session_id, "chapters", run_request)
                    self.confirm_phase(
                        db,
                        project_id,
                        session_id,
                        "chapters",
                        OutlineDebateConfirmRequest(item_key=f"chapter:{chapter_no}", notes="章纲自动推进确认。"),
                    )
            except Exception as exc:
                with SessionLocal() as db:
                    job = db.get(models.GenerationJob, job_id)
                    if job is not None:
                        session_id, request = self._chapter_autopilot_request_from_job(job)
                        result_payload = self._chapter_autopilot_result_payload(job, session_id, request)
                        self._record_chapter_autopilot_failure(db, job, request, result_payload, chapter_no, exc)
                        db.commit()
                return

            with SessionLocal() as db:
                job = db.get(models.GenerationJob, job_id)
                if job is None:
                    return
                session_id, request = self._chapter_autopilot_request_from_job(job)
                result_payload = self._chapter_autopilot_result_payload(job, session_id, request)
                self._record_chapter_autopilot_success(db, job, request, result_payload, chapter_no)
                db.commit()

        with SessionLocal() as db:
            job = db.get(models.GenerationJob, job_id)
            if job is None:
                return
            session_id, request = self._chapter_autopilot_request_from_job(job)
            result_payload = self._chapter_autopilot_result_payload(job, session_id, request)
            total_steps = max(1, self._chapter_autopilot_end_no(request) - int(request.start_chapter_no) + 1)
            job.status = "succeeded"
            job.finished_at = utcnow()
            job.heartbeat_at = utcnow()
            job.current_agent = "outline_debate/chapter_autopilot"
            job.progress_json = dumps(
                {
                    **self._chapter_autopilot_progress_payload(request, result_payload, current_step="completed", message="章纲议事自动推进已完成"),
                    "completed_steps": total_steps,
                }
            )
            job.result_json = dumps(result_payload)
            db.commit()

    def _chapter_autopilot_request_from_job(self, job: models.GenerationJob) -> tuple[str, OutlineDebateChapterAutopilotRequest]:
        payload = loads(job.request_json, {})
        session_id = str(payload.get("session_id") or "")
        request_payload = payload.get("request") if isinstance(payload.get("request"), dict) else {}
        request = OutlineDebateChapterAutopilotRequest.model_validate(request_payload)
        return session_id, request

    def _chapter_autopilot_end_no(self, request: OutlineDebateChapterAutopilotRequest) -> int:
        if request.end_chapter_no:
            return int(request.end_chapter_no)
        scale_plan = request.scale_plan if isinstance(request.scale_plan, dict) else {}
        try:
            planned = int(scale_plan.get("chapter_count") or 0)
        except (TypeError, ValueError):
            planned = 0
        if planned > 0:
            return planned
        return max(1, int(request.volume_count or 1) * int(request.chapters_per_volume or 1))

    def _chapter_autopilot_volume_no(self, request: OutlineDebateChapterAutopilotRequest, chapter_no: int) -> int:
        per_volume = max(1, int(request.chapters_per_volume or 1))
        return max(1, min(int(request.volume_count or 1), ((chapter_no - 1) // per_volume) + 1))

    def _chapter_autopilot_run_request(
        self,
        request: OutlineDebateChapterAutopilotRequest,
        volume_no: int,
        chapter_no: int,
    ) -> OutlineDebateRunRequest:
        payload = request.model_dump(exclude={"idempotency_key", "start_chapter_no", "end_chapter_no"})
        payload.update(
            {
                "target_volume_no": volume_no,
                "target_chapter_no": chapter_no,
                "chapter_ranges": [{"volume_no": volume_no, "start_chapter_no": chapter_no, "end_chapter_no": chapter_no}],
                "refresh_phase": True,
                "join_discussion": False,
                "finish_phase": False,
            }
        )
        return OutlineDebateRunRequest.model_validate(payload)

    def _chapter_autopilot_result_payload(
        self,
        job: models.GenerationJob,
        session_id: str,
        request: OutlineDebateChapterAutopilotRequest,
    ) -> dict[str, Any]:
        start_no = int(request.start_chapter_no)
        end_no = self._chapter_autopilot_end_no(request)
        payload = loads(job.result_json, {}) if job.result_json else {}
        if not isinstance(payload, dict):
            payload = {}
        payload.setdefault("session_id", session_id)
        payload.setdefault("project_id", job.project_id)
        payload.setdefault("start_chapter_no", start_no)
        payload.setdefault("end_chapter_no", end_no)
        payload.setdefault("completed_chapters", [])
        payload.setdefault("skipped_chapters", [])
        payload.setdefault("failed_chapters", [])
        return payload

    def _chapter_autopilot_completed_numbers(self, result_payload: dict[str, Any]) -> set[int]:
        numbers: set[int] = set()
        for item in result_payload.get("completed_chapters", []):
            try:
                numbers.add(int(item))
            except (TypeError, ValueError):
                continue
        return numbers

    def _chapter_autopilot_progress_payload(
        self,
        request: OutlineDebateChapterAutopilotRequest,
        result_payload: dict[str, Any],
        *,
        current_step: str,
        message: str,
        current_chapter_no: int | None = None,
    ) -> dict[str, Any]:
        start_no = int(request.start_chapter_no)
        end_no = self._chapter_autopilot_end_no(request)
        completed = len(self._chapter_autopilot_completed_numbers(result_payload))
        payload = {
            "current_step": current_step,
            "total_steps": max(1, end_no - start_no + 1),
            "completed_steps": completed,
            "message": message,
            "start_chapter_no": start_no,
            "end_chapter_no": end_no,
        }
        if current_chapter_no is not None:
            payload["current_chapter_no"] = current_chapter_no
        return payload

    def _record_chapter_autopilot_success(
        self,
        db: Session,
        job: models.GenerationJob,
        request: OutlineDebateChapterAutopilotRequest,
        result_payload: dict[str, Any],
        chapter_no: int,
        *,
        skipped: bool = False,
    ) -> None:
        completed = self._chapter_autopilot_completed_numbers(result_payload)
        if chapter_no not in completed:
            result_payload.setdefault("completed_chapters", []).append(chapter_no)
        if skipped and chapter_no not in {int(item) for item in result_payload.get("skipped_chapters", []) if str(item).isdigit()}:
            result_payload.setdefault("skipped_chapters", []).append(chapter_no)
        job.status = "running"
        job.heartbeat_at = utcnow()
        job.current_agent = f"outline_debate/chapter_autopilot:chapter_{chapter_no}"
        job.result_json = dumps(result_payload)
        job.progress_json = dumps(
            self._chapter_autopilot_progress_payload(
                request,
                result_payload,
                current_step=f"chapter_{chapter_no}",
                current_chapter_no=chapter_no,
                message=f"第{chapter_no}章章纲已{'跳过' if skipped else '确认'}",
            )
        )

    def _record_chapter_autopilot_failure(
        self,
        db: Session,
        job: models.GenerationJob,
        request: OutlineDebateChapterAutopilotRequest,
        result_payload: dict[str, Any],
        chapter_no: int,
        error: Exception,
    ) -> None:
        result_payload.setdefault("failed_chapters", []).append({"chapter_no": chapter_no, "error": str(error)})
        job.result_json = dumps(result_payload)
        self._mark_chapter_autopilot_failed(db, job, error)

    def _mark_chapter_autopilot_failed(self, db: Session, job: models.GenerationJob, error: Exception) -> None:
        progress = loads(job.progress_json, {})
        job.status = "failed"
        job.error_message = str(error)
        job.finished_at = utcnow()
        job.heartbeat_at = utcnow()
        job.progress_json = dumps(
            {
                "current_step": "failed",
                "total_steps": progress.get("total_steps", 1),
                "completed_steps": progress.get("completed_steps", 0),
                "message": "章纲议事自动推进失败",
            }
        )

    def _mark_chapter_autopilot_cancelled(
        self,
        db: Session,
        job: models.GenerationJob,
        request: OutlineDebateChapterAutopilotRequest,
        result_payload: dict[str, Any],
    ) -> None:
        job.status = "cancelled"
        job.finished_at = utcnow()
        job.heartbeat_at = utcnow()
        job.result_json = dumps(result_payload)
        job.progress_json = dumps(
            self._chapter_autopilot_progress_payload(
                request,
                result_payload,
                current_step="cancelled",
                message=job.cancel_reason or "章纲议事自动推进已取消",
            )
        )

    def _chapter_candidate_already_confirmed(self, db: Session, project_id: str, session_id: str, chapter_no: int) -> bool:
        try:
            session = self._session_from_job(self._session_job(db, project_id, session_id))
        except HTTPException:
            return False
        chapter_key = f"chapter:{chapter_no}"
        phase_run = session.get("phase_runs", {}).get("chapters")
        if isinstance(phase_run, dict):
            for item in phase_run.get("confirmation_items", []):
                if isinstance(item, dict) and item.get("item_key") == chapter_key and item.get("candidate_status") == "confirmed":
                    return True
        confirmed = session.get("confirmed_candidates", {}).get("chapters")
        outlines = confirmed.get("chapter_outlines") if isinstance(confirmed, dict) and isinstance(confirmed.get("chapter_outlines"), list) else []
        return any(isinstance(item, dict) and int(item.get("chapter_no") or 0) == chapter_no for item in outlines)

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
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            existing = (
                db.query(models.GenerationJob)
                .filter(models.GenerationJob.project_id == project_id, models.GenerationJob.idempotency_key == idempotency_key)
                .first()
            )
            if existing:
                return {"session": self._session_from_job(existing), "job": serialize_job(existing)}
            raise
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
        self._ensure_phase_refresh_allowed(session, phase, request)
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
        self._ensure_phase_quality_confirmable(phase_run, result)
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
            planned_volumes = self._ensure_planned_volume_shells(db, project_id, result)
            book_commit["volumes"] = [
                serialize_volume(volume)
                for volume in db.query(models.Volume)
                .filter(models.Volume.project_id == project_id)
                .order_by(models.Volume.sort_order.asc(), models.Volume.volume_no.asc())
                .all()
            ]
            commit_summary = {
                "status": "committed",
                "committed_at": now,
                "target": "story_bible_and_volume_shells",
                "story_bible_version": book_commit.get("story_bible", {}).get("version"),
                "planned_volume_count": len(planned_volumes),
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

    def _ensure_phase_quality_confirmable(self, phase_run: dict[str, Any], result: dict[str, Any]) -> None:
        validation_report = phase_run.get("validation_report") if isinstance(phase_run.get("validation_report"), dict) else {}
        if validation_report.get("status") == "failed":
            failed_checks = [
                str(check.get("validator") or check.get("message") or "validation")
                for check in validation_report.get("checks", [])
                if isinstance(check, dict) and check.get("status") == "failed"
            ]
            detail = "、".join(failed_checks[:3]) or "validation_report"
            raise _bad_request(f"{PHASE_CONFIG[phase_run['phase']]['result_title']}质量门未通过：{detail}")
        quality_metrics = result.get("quality_metrics") if isinstance(result.get("quality_metrics"), dict) else {}
        blocking_items = quality_metrics.get("blocking_items") if isinstance(quality_metrics.get("blocking_items"), list) else []
        if quality_metrics.get("status") == "failed" or blocking_items:
            evidence = ""
            first_block = blocking_items[0] if blocking_items else None
            if isinstance(first_block, dict):
                evidence = str(first_block.get("evidence") or first_block.get("type") or "")
            raise _bad_request(f"{PHASE_CONFIG[phase_run['phase']]['result_title']}质量门未通过：{evidence or 'quality_metrics'}")
        self._ensure_candidate_artifacts_confirmable(phase_run)

    def _ensure_candidate_artifacts_confirmable(self, phase_run: dict[str, Any]) -> None:
        for artifact in phase_run.get("artifacts", []):
            if not isinstance(artifact, dict) or artifact.get("type") not in {"character_candidate", "setting_candidate"}:
                continue
            payload = artifact.get("payload") if isinstance(artifact.get("payload"), dict) else {}
            candidate_source = str(payload.get("candidate_source") or artifact.get("candidate_source") or "")
            can_materialize = payload.get("can_materialize_on_confirm", artifact.get("can_materialize_on_confirm"))
            if can_materialize is False or candidate_source in {"service_fallback", "text_extracted_candidate"}:
                title = str(artifact.get("title") or payload.get("name") or payload.get("title") or artifact.get("type"))
                reason = str(payload.get("candidate_source_reason") or artifact.get("candidate_source_reason") or candidate_source or "candidate_source")
                raise _bad_request(f"{PHASE_CONFIG[phase_run['phase']]['result_title']}候选来源不允许直接确认入库：{title}（{reason}）")

    def commit_confirmed_candidates(self, db: Session, project_id: str, session_id: str, request: OutlineDebateCommitRequest) -> dict[str, Any]:
        self._project(db, project_id)
        job = self._session_job(db, project_id, session_id)
        session = self._session_from_job(job)
        confirmed_candidates = self._ensure_all_candidates_confirmed(session)
        book_outline_plan = self._book_outline_plan_from_confirmed_candidates(confirmed_candidates)
        chapter_outlines = self._chapter_outlines_from_confirmed_candidates(confirmed_candidates)

        book_commit = self._write_book_outline_plan(db, project_id, book_outline_plan)
        chapter_commit = self._commit_chapter_outline_items(
            db,
            project_id,
            chapter_outlines,
            overwrite_existing=request.overwrite_existing_chapters,
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
                "message": "已把确认条目写入正式大纲",
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
        self._ensure_phase_refresh_allowed(session, phase, request)
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
        phase_run_id = generate_id("odr")
        phase_started_at = utcnow().isoformat()
        turns: list[dict[str, Any]] = []
        while len(turns) < self._max_dynamic_turns(request):
            agent_name = self._next_dynamic_agent_name(phase, request, context, turns, phase_run=None)
            if not agent_name:
                break
            role = DEBATE_AGENT_ROLES[agent_name]
            agent_round = self._agent_round_no(agent_name, turns)
            turn = self._build_turn(project, phase, request, context, agent_name, role, len(turns) + 1, agent_round, agenda, deliberation_state)
            turns.append(turn)
            orchestrator.apply_turn_to_state(deliberation_state, turn)
            next_agent_name = self._next_dynamic_agent_name(phase, request, context, turns, phase_run=None)
            route_decision = self._route_decision_for_next_agent(phase, request, context, turns, next_agent_name, phase_run=None)
            self._attach_turn_display(turn, next_agent_name, route_decision)
            self._persist_streaming_phase_progress(
                db,
                job,
                session,
                phase,
                request,
                phase_run_id,
                phase_started_at,
                turns,
                agenda,
                deliberation_state,
                next_agent_name,
            )
            async for block in self._stream_turn_event(phase, turn):
                yield block
            await asyncio.sleep(0)

        cross_review = orchestrator.cross_review(deliberation_state, turns)
        result = orchestrator.synthesize_candidate_artifact(project, phase, request, turns, session, deliberation_state)
        artifacts, candidate_policy = self._build_artifacts(project, phase, request, result, turns, context)
        validation_report = orchestrator.validate_result(phase, result, artifacts, context)
        decisions = orchestrator.request_revision_or_finish(phase, request, result, candidate_policy, deliberation_state)
        topology = self._build_topology(phase, request, turns, decisions, artifacts)
        phase_run = self._mark_phase_run_pending(
            {
                "id": phase_run_id,
                "phase": phase,
                "phase_label": PHASE_CONFIG[phase]["label"],
                "status": "succeeded",
                "started_at": phase_started_at,
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

    def _persist_streaming_phase_progress(
        self,
        db: Session,
        job: models.GenerationJob,
        session: dict[str, Any],
        phase: str,
        request: OutlineDebateRunRequest,
        phase_run_id: str,
        started_at: str,
        turns: list[dict[str, Any]],
        agenda: dict[str, Any],
        deliberation_state: dict[str, Any],
        next_agent_name: str,
    ) -> None:
        phase_run = {
            "id": phase_run_id,
            "phase": phase,
            "phase_label": PHASE_CONFIG[phase]["label"],
            "status": "running",
            "candidate_status": "draft",
            "started_at": started_at,
            "finished_at": "",
            "input": request.model_dump(mode="json"),
            "agent_specs": self._agent_specs(),
            "candidate_policy": {},
            "validation_report": {},
            "turns": loads(dumps(turns), []),
            "user_messages": self._pending_session_messages(session, phase),
            "decisions": [],
            "artifacts": [],
            "outline_topology": self._build_topology(phase, request, turns, [], []),
            "result": {},
            "agenda": agenda,
            "deliberation_state": deliberation_state,
            "next_agent_name": next_agent_name,
        }
        session.setdefault("phase_runs", {})[phase] = phase_run
        session["current_phase"] = phase
        session["status"] = "running"
        session["updated_at"] = utcnow().isoformat()
        job.result_json = dumps({"session": session})
        job.current_agent = turns[-1]["agent_name"] if turns else ""
        job.heartbeat_at = utcnow()
        job.progress_json = dumps(
            {
                "current_step": phase,
                "total_steps": len(PHASE_ORDER),
                "completed_steps": len([run for run in session.get("phase_runs", {}).values() if isinstance(run, dict) and run.get("status") == "succeeded"]),
                "message": f"{PHASE_CONFIG[phase]['label']}已保存第{len(turns)}轮发言",
            }
        )
        db.commit()

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
        self._ensure_phase_refresh_allowed(session, phase, request)
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

        context = self._phase_context(db, project, session, phase, request)
        next_agent_name = self._next_round_agent_name(phase_run, phase, request, context)
        if not next_agent_name:
            self._finalize_round_phase(db, job, project, session, phase, request, phase_run)
            events.extend(("decision", {"type": "decision", "phase": phase, "decision": decision}) for decision in phase_run["decisions"])
            events.extend(("artifact", {"type": "artifact", "phase": phase, "artifact": artifact}) for artifact in phase_run["artifacts"])
            events.append(("done", {"type": "done", "phase": phase, "phase_run": phase_run, "session": session}))
            db.commit()
            db.refresh(job)
            return events

        orchestrator = OutlineDebateOrchestrator(self)
        agenda = phase_run.get("agenda") if isinstance(phase_run.get("agenda"), dict) else orchestrator.build_agenda(phase, request, context)
        deliberation_state = phase_run.get("deliberation_state") if isinstance(phase_run.get("deliberation_state"), dict) else orchestrator.initial_state(agenda, request)
        agent_index = self._agent_round_no(next_agent_name, phase_run.get("turns", []))
        role = DEBATE_AGENT_ROLES[next_agent_name]
        turn = self._build_turn(project, phase, request, context, next_agent_name, role, len(phase_run["turns"]) + 1, agent_index, agenda, deliberation_state)
        phase_run.setdefault("turns", []).append(turn)
        orchestrator.apply_turn_to_state(deliberation_state, turn)
        self._mark_target_message_handled(phase_run, turn)
        phase_run["status"] = "paused"
        phase_run["next_agent_name"] = self._next_round_agent_name(phase_run, phase, request, context)
        route_decision = self._route_decision_for_next_agent(phase, request, context, phase_run["turns"], phase_run["next_agent_name"], phase_run=phase_run)
        self._attach_turn_display(turn, phase_run["next_agent_name"], route_decision)
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
                    "message": "当前席位发言完成，等待用户继续或发表意见。",
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
        scale_plan = request.scale_plan if isinstance(request.scale_plan, dict) else {}
        if phase == "volumes":
            return len(self._volume_numbers_for_request(request))
        return len(self._chapter_candidates_for_request(request)) or self._bounded_int(
            scale_plan.get("chapter_count"),
            max(1, int(request.volume_count or 1) * int(request.chapters_per_volume or 1)),
            1,
            6000,
        )

    def _volume_numbers_for_request(self, request: OutlineDebateRunRequest) -> list[int]:
        if request.target_volume_no:
            return [int(request.target_volume_no)]
        if request.chapter_ranges:
            numbers = sorted({int(chapter_range.volume_no) for chapter_range in request.chapter_ranges})
            if numbers:
                return numbers
        scale_plan = request.scale_plan if isinstance(request.scale_plan, dict) else {}
        volume_count = self._bounded_int(scale_plan.get("volume_count") or request.volume_count, request.volume_count or 1, 1, 30)
        return list(range(1, volume_count + 1))

    def _chapter_ranges_for_request(self, request: OutlineDebateRunRequest) -> list[dict[str, int]]:
        if request.target_chapter_no:
            return [
                {
                    "volume_no": self._target_volume_no(request),
                    "start_chapter_no": self._target_chapter_no(request),
                    "end_chapter_no": self._target_chapter_no(request),
                }
            ]
        if request.chapter_ranges:
            ranges: list[dict[str, int]] = []
            for chapter_range in request.chapter_ranges:
                start_no = int(chapter_range.start_chapter_no)
                end_no = int(chapter_range.end_chapter_no)
                if end_no < start_no:
                    start_no, end_no = end_no, start_no
                ranges.append(
                    {
                        "volume_no": int(chapter_range.volume_no),
                        "start_chapter_no": start_no,
                        "end_chapter_no": end_no,
                    }
                )
            return ranges
        scale_plan = request.scale_plan if isinstance(request.scale_plan, dict) else {}
        chapters_per_volume = self._bounded_int(
            scale_plan.get("chapters_per_volume") or request.chapters_per_volume,
            request.chapters_per_volume or 1,
            1,
            300,
        )
        return [
            {
                "volume_no": volume_no,
                "start_chapter_no": (volume_no - 1) * chapters_per_volume + 1,
                "end_chapter_no": volume_no * chapters_per_volume,
            }
            for volume_no in self._volume_numbers_for_request(request)
        ]

    def _chapter_candidates_for_request(self, request: OutlineDebateRunRequest) -> list[tuple[int, int]]:
        candidates: list[tuple[int, int]] = []
        for chapter_range in self._chapter_ranges_for_request(request):
            for chapter_no in range(int(chapter_range["start_chapter_no"]), int(chapter_range["end_chapter_no"]) + 1):
                candidates.append((int(chapter_range["volume_no"]), chapter_no))
        return candidates or [(1, 1)]

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
            raise _bad_request(f"请先确认第{volume_no}卷卷纲条目，再进入{PHASE_CONFIG[phase]['label']}")
        upstream_run = session.get("phase_runs", {}).get(upstream_phase)
        if not isinstance(upstream_run, dict) or upstream_run.get("candidate_status") != "confirmed":
            raise _bad_request(f"请先确认{upstream_label}条目，再进入{PHASE_CONFIG[phase]['label']}")

    def _ensure_phase_refresh_allowed(self, session: dict[str, Any], phase: str, request: OutlineDebateRunRequest) -> None:
        if not request.refresh_phase or request.force_refresh_confirmed:
            return
        phase_run = session.get("phase_runs", {}).get(phase)
        if not isinstance(phase_run, dict):
            return
        confirmed_candidates = session.get("confirmed_candidates") if isinstance(session.get("confirmed_candidates"), dict) else {}
        if not self._is_itemized_phase(phase):
            if phase_run.get("candidate_status") == "confirmed" or phase in confirmed_candidates:
                raise _bad_request(f"{PHASE_CONFIG[phase]['result_title'].replace('候选', '条目')}已确认；如需重新讨论，请显式选择强制刷新。")
            return
        item_key = self._item_key_for_request(phase, request)
        for item in phase_run.get("confirmation_items", []):
            if isinstance(item, dict) and item.get("item_key") == item_key and item.get("candidate_status") == "confirmed":
                label = item.get("title") or item_key.replace("volume:", "第").replace("chapter:", "第")
                raise _bad_request(f"{label}已确认；如需重新讨论，请显式选择强制刷新。")
        phase_candidate = confirmed_candidates.get(phase) if isinstance(confirmed_candidates, dict) else None
        values = phase_candidate.get(self._item_list_key(phase)) if isinstance(phase_candidate, dict) else None
        if isinstance(values, list):
            for candidate in values:
                if isinstance(candidate, dict) and self._item_key_for_candidate(phase, candidate) == item_key:
                    label = candidate.get("title") or item_key
                    raise _bad_request(f"{label}已确认；如需重新讨论，请显式选择强制刷新。")

    def _ensure_all_candidates_confirmed(self, session: dict[str, Any]) -> dict[str, dict[str, Any]]:
        confirmed_candidates = session.setdefault("confirmed_candidates", {})
        if not isinstance(confirmed_candidates, dict):
            confirmed_candidates = {}
        phase_runs = session.get("phase_runs") if isinstance(session.get("phase_runs"), dict) else {}
        for phase in PHASE_ORDER:
            phase_run = phase_runs.get(phase)
            confirmed = confirmed_candidates.get(phase)
            if not isinstance(phase_run, dict) or phase_run.get("candidate_status") != "confirmed" or not isinstance(confirmed, dict):
                title = PHASE_CONFIG[phase]["result_title"].replace("候选", "条目")
                raise _bad_request(f"请先确认{title}，再写入正式大纲")
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
        if request.confirm_all:
            item_keys = [
                str(item.get("item_key") or "")
                for item in phase_run.get("confirmation_items", [])
                if isinstance(item, dict) and item.get("candidate_status") == "pending_confirmation" and item.get("item_key")
            ]
        else:
            item_keys = [request.item_key or self._first_pending_item_key(phase_run)]
        item_keys = [item_key for item_key in item_keys if item_key]
        if not item_keys:
            raise _bad_request(f"{PHASE_CONFIG[phase]['result_title']}缺少待确认条目")
        now = utcnow().isoformat()
        canon_updates: list[dict[str, Any]] = []
        confirmed_items: list[dict[str, Any]] = []
        for item_key in item_keys:
            item = self._candidate_item_by_key(phase_run, item_key)
            if item is None:
                raise _bad_request(f"未找到可确认条目：{item_key}")
            if item.get("candidate_status") == "stale":
                raise _bad_request(f"{item_key} 已过期，请重新议事生成后再确认")
            if request.confirm_all and item.get("candidate_status") == "confirmed":
                continue
            canon_update = self._commit_outline_item_to_canon(db, project_id, job, session, phase, item, request.notes)
            materializations = self._materialize_phase_candidate_artifacts(
                db,
                project_id,
                job,
                phase_run,
                phase,
                request.notes,
                source_chapter_id=canon_update.get("ref_id") if canon_update.get("ref_type") == "chapter" else None,
            )
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
            canon_updates.append(canon_update)
            confirmed_items.append(item)
        self._refresh_confirmation_items(phase_run)
        for item in confirmed_items:
            self._upsert_confirmed_item(session, phase, item, phase_run["candidate_status"])
        if phase_run["candidate_status"] == "confirmed":
            phase_run["confirmed_at"] = now
        phase_run["last_confirmed_item_key"] = item_keys[-1]
        if canon_updates:
            phase_run["last_canon_update"] = canon_updates[-1]
            phase_run["last_canon_updates"] = canon_updates
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
        return {"session": session, "phase_run": session["phase_runs"][phase], "canon_update": canon_updates[-1] if canon_updates else {}, "canon_updates": canon_updates, "job": serialize_job(job)}

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
        session: dict[str, Any],
        phase: str,
        item: dict[str, Any],
        notes: str,
    ) -> dict[str, Any]:
        from app.services.studio_service import studio_service

        project = self._project(db, project_id)
        if phase == "volumes":
            rough_source = self._flatten_stage_candidate(item, "volumes")
            rough_volume_no = self._bounded_int(rough_source.get("volume_no") or rough_source.get("volume") or rough_source.get("卷序"), 1, 1, 999)
            item = self._normalize_volume_candidate_for_commit(project, item, preferred_title=self._preferred_volume_title_from_book_plan(session, rough_volume_no))
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

        item = self._normalize_chapter_candidate_for_commit(project, item)
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
        name = self._canonical_canon_label(self._string_or(payload.get("name"), "未命名角色"))
        if self._is_placeholder_candidate_name(name):
            return {}
        existing = self._existing_character_by_label(db, project_id, name)
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
        relationship_hooks = payload.get("relations") if isinstance(payload.get("relations"), list) else payload.get("relationship_hooks")
        long_term_goal = self._first_string(payload.get("long_term_goal"), payload.get("long_term_desire"), fallback="")
        immediate_goal = self._first_string(payload.get("immediate_goal"), fallback="")
        inner_wound = self._first_string(payload.get("inner_wound"), fallback="")
        ability = self._first_string(payload.get("ability"), fallback="")
        ability_cost = self._first_string(payload.get("ability_cost"), fallback="")
        weakness = self._first_string(payload.get("weakness"), fallback="")
        secret = self._first_string(payload.get("secret"), fallback="")
        goals = self._clean_string_values(payload.get("goals"), long_term_goal, immediate_goal)
        motivations = self._clean_string_values(payload.get("motivations"), payload.get("motivation"), payload.get("conflict_seed"), payload.get("reader_satisfaction"))
        secrets = self._clean_string_values(payload.get("secrets"), secret)
        abilities = self._clean_string_values(payload.get("abilities"), ability, ability_cost)
        weaknesses = self._clean_string_values(payload.get("weaknesses"), weakness, inner_wound, ability_cost)
        profile = self._first_string(payload.get("profile"), payload.get("one_sentence_pitch"), payload.get("identity"), payload.get("summary"), fallback="")
        personality = self._first_string(payload.get("personality"), inner_wound, payload.get("relationship_hook"), fallback="")
        arc = self._first_string(payload.get("character_arc"), payload.get("growth_arc"), payload.get("arc"), fallback="")
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
            personality=personality,
            profile=profile,
            goals_json=dumps(goals),
            motivations_json=dumps(motivations),
            secrets_json=dumps(secrets),
            abilities_json=dumps(abilities),
            weaknesses_json=dumps(weaknesses),
            motivation=self._first_string(payload.get("motivation"), motivations[0] if motivations else "", fallback=""),
            arc=arc,
            character_arc=arc,
            current_status=self._string_or(payload.get("current_status"), "active"),
            first_appearance_chapter_id=source_chapter_id,
            last_seen_chapter_id=source_chapter_id,
            related_entity_ids_json=dumps(self._list_of_clean_strings(payload.get("related_entity_ids"))),
            related_character_ids_json=dumps(self._list_of_clean_strings(payload.get("related_character_ids"))),
            relations_json=dumps(relationship_hooks if isinstance(relationship_hooks, list) else self._list_of_clean_strings(relationship_hooks)),
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
        name = self._canonical_canon_label(self._string_or(payload.get("name") or payload.get("title"), "未命名实体"))
        if self._is_placeholder_candidate_name(name):
            return {}
        existing = self._existing_entity_by_label(db, project_id, entity_type, name)
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
        title = self._canonical_canon_label(self._string_or(payload.get("title") or payload.get("name"), "未命名世界观事实"))
        if self._is_placeholder_candidate_name(title):
            return {}
        existing = self._existing_world_fact_by_label(db, project_id, title)
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
        if raw in {"world_fact", "world_facts", "fact", "facts", "world_rule", "world_rules"}:
            return "world_fact"
        if raw in {"entity", "entities", "story_entity", "story_entities"} or payload.get("entity_type"):
            return "entity"
        return "world_fact"

    def _canonical_canon_label(self, value: str) -> str:
        label = re.sub(r"\s+", " ", str(value or "")).strip()
        while True:
            stripped = re.sub(r"\s*[（(][^（）()]{1,24}[）)]\s*$", "", label).strip()
            if stripped == label or len(stripped) < 2:
                return label
            label = stripped

    def _label_match_key(self, value: str) -> str:
        return re.sub(r"[\s·•:：,，。、《》〈〉\"'“”‘’（）()\\[\\]【】]", "", self._canonical_canon_label(value)).lower()

    def _existing_character_by_label(self, db: Session, project_id: str, label: str) -> models.Character | None:
        exact = db.query(models.Character).filter(models.Character.project_id == project_id, models.Character.name == label).first()
        if exact:
            return exact
        wanted = self._label_match_key(label)
        for row in db.query(models.Character).filter(models.Character.project_id == project_id).all():
            if self._label_match_key(row.name) == wanted:
                return row
        return None

    def _existing_entity_by_label(self, db: Session, project_id: str, entity_type: str, label: str) -> models.StoryEntity | None:
        exact = (
            db.query(models.StoryEntity)
            .filter(models.StoryEntity.project_id == project_id, models.StoryEntity.entity_type == entity_type, models.StoryEntity.name == label)
            .first()
        )
        if exact:
            return exact
        wanted = self._label_match_key(label)
        for row in db.query(models.StoryEntity).filter(models.StoryEntity.project_id == project_id, models.StoryEntity.entity_type == entity_type).all():
            if self._label_match_key(row.name) == wanted:
                return row
        return None

    def _existing_world_fact_by_label(self, db: Session, project_id: str, label: str) -> models.WorldFact | None:
        exact = db.query(models.WorldFact).filter(models.WorldFact.project_id == project_id, models.WorldFact.title == label).first()
        if exact:
            return exact
        wanted = self._label_match_key(label)
        for row in db.query(models.WorldFact).filter(models.WorldFact.project_id == project_id).all():
            if self._label_match_key(row.title) == wanted:
                return row
        return None

    def _is_placeholder_candidate_name(self, value: str) -> bool:
        compact = "".join(str(value or "").split())
        if not compact:
            return True
        placeholder_tokens = ("未命名", "待定", "占位", "placeholder", "讨论卷纲", "讨论章纲")
        return any(token.lower() in compact.lower() for token in placeholder_tokens)

    def _list_of_clean_strings(self, value: Any) -> list[str]:
        if value in (None, "", [], {}):
            return []
        if isinstance(value, str):
            stripped = value.strip()
            return [stripped] if stripped else []
        if not isinstance(value, (list, tuple, set)):
            return []
        items: list[str] = []
        for item in value:
            if isinstance(item, dict):
                continue
            stripped = str(item).strip()
            if stripped:
                items.append(stripped)
        return list(dict.fromkeys(items))

    def _clean_string_values(self, *values: Any) -> list[str]:
        items: list[str] = []
        for value in values:
            items.extend(self._list_of_clean_strings(value))
        return list(dict.fromkeys(items))

    def _first_string(self, *values: Any, fallback: str = "") -> str:
        for value in values:
            if isinstance(value, str) and value.strip():
                return value.strip()
        return fallback

    def _importance_level_from_score(self, score: int) -> str:
        if score >= 90:
            return "core"
        if score >= 70:
            return "major"
        if score >= 40:
            return "medium"
        return "minor"

    def _importance_score_for_sort(self, candidate: dict[str, Any]) -> int:
        raw_score = candidate.get("importance_score")
        if raw_score not in (None, ""):
            return self._bounded_int(raw_score, 50, 0, 100)
        level = str(candidate.get("importance_level") or "").strip().lower()
        return {"core": 95, "major": 78, "medium": 50, "minor": 25}.get(level, 50)

    def _sort_candidates_by_importance(self, candidates: list[dict[str, Any]], label_key: str) -> list[dict[str, Any]]:
        return sorted(
            candidates,
            key=lambda candidate: (self._importance_score_for_sort(candidate), str(candidate.get(label_key) or candidate.get("name") or "")),
            reverse=True,
        )

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

    def _upsert_confirmed_item(self, session: dict[str, Any], phase: str, item: dict[str, Any], candidate_status: str) -> None:
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
        phase_candidate["candidate_status"] = candidate_status
        phase_candidate["requires_user_confirmation"] = candidate_status != "confirmed"

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
        return self._write_book_outline_plan(db, project_id, self._book_outline_plan_from_book_candidate(book_candidate))

    def _write_book_outline_plan(self, db: Session, project_id: str, outline_plan: dict[str, Any]) -> dict[str, Any]:
        if not outline_plan:
            raise _bad_request("没有可写入的大纲结果")
        from app.services.studio_service import studio_service

        project = self._project(db, project_id)
        studio_service._apply_book_outline(db, project, outline_plan)
        db.flush()
        story_bible = db.query(models.StoryBible).filter(models.StoryBible.project_id == project_id).first()
        volumes = (
            db.query(models.Volume)
            .filter(models.Volume.project_id == project_id)
            .order_by(models.Volume.sort_order.asc(), models.Volume.volume_no.asc())
            .all()
        )
        return {
            "project": serialize_project(project),
            "story_bible": serialize_story_bible(story_bible) if story_bible else {},
            "volumes": [serialize_volume(item) for item in volumes],
            "outline_plan": outline_plan,
        }

    def _commit_chapter_outline_items(
        self,
        db: Session,
        project_id: str,
        chapter_outlines: list[dict[str, Any]],
        *,
        overwrite_existing: bool,
    ) -> dict[str, Any]:
        if not chapter_outlines:
            raise _bad_request("没有可写入的章纲结果")
        from app.services.studio_service import studio_service

        project = self._project(db, project_id)
        chapters = studio_service._persist_chapter_outline_candidates(db, project, chapter_outlines, None, overwrite_existing)
        db.flush()
        return {"chapters": [serialize_chapter(chapter) for chapter in chapters], "chapter_outlines": chapter_outlines}

    def _ensure_planned_volume_shells(self, db: Session, project_id: str, book_candidate: dict[str, Any]) -> list[dict[str, Any]]:
        project = self._project(db, project_id)
        scale_plan = book_candidate.get("scale_plan") if isinstance(book_candidate.get("scale_plan"), dict) else {}
        volume_count = self._bounded_int(scale_plan.get("volume_count") or project.planned_volume_count, project.planned_volume_count or 1, 1, 30)
        chapters_per_volume = self._bounded_int(
            scale_plan.get("chapters_per_volume") or project.chapters_per_volume,
            project.chapters_per_volume or max(1, (project.planned_chapter_count or volume_count) // max(1, volume_count)),
            1,
            300,
        )
        rows: list[dict[str, Any]] = []
        for volume_no in range(1, volume_count + 1):
            volume = db.query(models.Volume).filter(models.Volume.project_id == project_id, models.Volume.volume_no == volume_no).first()
            if volume is None:
                volume = models.Volume(
                    id=generate_id("vol"),
                    project_id=project_id,
                    volume_no=volume_no,
                    title=f"第{volume_no}卷",
                    sort_order=volume_no,
                    outline="",
                    status="draft",
                )
                db.add(volume)
            volume.sort_order = volume_no
            if not volume.title:
                volume.title = f"第{volume_no}卷"
            if not volume.outline:
                start = (volume_no - 1) * chapters_per_volume + 1
                volume.outline = f"章节区间：{start}-{start + chapters_per_volume - 1}\n状态：待逐卷议事确认"
            rows.append({"id": volume.id, "volume_no": volume_no, "title": volume.title})
        db.flush()
        return rows

    def _book_outline_plan_from_book_candidate(self, book_candidate: dict[str, Any]) -> dict[str, Any]:
        book_outline = book_candidate.get("book_outline") if isinstance(book_candidate.get("book_outline"), dict) else {}
        if not book_outline:
            raise _bad_request("总纲候选缺少 book_outline，无法写入正式大纲")
        normalized_book_outline = self._normalize_book_outline_for_commit(book_outline)
        scale_plan = book_candidate.get("scale_plan") if isinstance(book_candidate.get("scale_plan"), dict) else {}
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
            "parameters": {
                "target_words": scale_plan.get("target_words"),
                "volume_count": scale_plan.get("volume_count"),
                "chapters_per_volume": scale_plan.get("chapters_per_volume"),
                "chapter_word_target": scale_plan.get("chapter_word_target"),
                "chapter_word_min": scale_plan.get("chapter_word_min"),
                "chapter_word_max": scale_plan.get("chapter_word_max"),
            },
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
        normalized_volumes = [self._normalize_volume_candidate_for_commit(None, item) for item in volume_outlines if isinstance(item, dict)]
        scale_plan = book_candidate.get("scale_plan") if isinstance(book_candidate.get("scale_plan"), dict) else {}
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
                "target_words": scale_plan.get("target_words"),
                "chapters_per_volume": scale_plan.get("chapters_per_volume"),
                "chapter_word_target": scale_plan.get("chapter_word_target"),
                "chapter_word_min": scale_plan.get("chapter_word_min"),
                "chapter_word_max": scale_plan.get("chapter_word_max"),
            },
        }

    def _chapter_outlines_from_confirmed_candidates(self, confirmed_candidates: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        chapters_candidate = confirmed_candidates["chapters"]
        chapter_outlines = chapters_candidate.get("chapter_outlines") if isinstance(chapters_candidate.get("chapter_outlines"), list) else []
        normalized = [self._normalize_chapter_candidate_for_commit(None, item) for item in chapter_outlines if isinstance(item, dict)]
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
            "candidate_policy": str(base.get("candidate_policy") or "只输出待确认讨论意见，确认后由服务层入库。"),
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

    def _is_chinese_first_text(self, value: Any) -> bool:
        text = self._string_or(value, "").strip()
        if not text:
            return True
        chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
        latin_words = len(re.findall(r"\b[A-Za-z][A-Za-z0-9_-]*\b", text))
        return chinese_chars >= max(4, latin_words)

    def _ensure_remote_turn_main_fields_chinese_first(self, agent_name: str, payload: dict[str, Any]) -> None:
        fields: list[tuple[str, Any]] = [("message", payload.get("message"))]
        for index, claim in enumerate(payload.get("claims") if isinstance(payload.get("claims"), list) else []):
            fields.append((f"claims[{index}]", claim))
        for index, risk in enumerate(payload.get("risks") if isinstance(payload.get("risks"), list) else []):
            fields.append((f"risks[{index}]", risk))

        for field_name, value in fields:
            if not self._is_chinese_first_text(value):
                preview = self._string_or(value, "").strip()[:80]
                raise RuntimeError(f"{agent_name} 输出字段 {field_name} 必须以中文为主：{preview}")

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
            project.chapter_word_target or DEFAULT_CHAPTER_WORD_TARGET,
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
        chapter_window_size = positive_int(
            source.get("chapter_window_size"),
            max(1, round(chapters_per_volume / DEFAULT_CHAPTER_WINDOWS_PER_VOLUME)),
            minimum=1,
            maximum=300,
        )
        return {
            "target_words": target_words,
            "volume_count": volume_count,
            "chapter_count": chapter_count,
            "chapters_per_volume": chapters_per_volume,
            "chapter_window_size": chapter_window_size,
            "chapter_word_target": chapter_word_target,
            "chapter_word_min": chapter_word_min,
            "chapter_word_max": chapter_word_max,
        }

    def _phase_focus_constraints(self, phase: str, request: OutlineDebateRunRequest, scale_plan: dict[str, int]) -> dict[str, Any]:
        if phase == "chapters":
            expected_chapters = len(self._chapter_candidates_for_request(request))
            if request.target_chapter_no:
                volume_no = self._target_volume_no(request)
                chapter_no = self._target_chapter_no(request)
                return {
                    "mode": "single_chapter",
                    "target_volume_no": volume_no,
                    "target_chapter_no": chapter_no,
                    "item_key": f"chapter:{chapter_no}",
                    "hard_rules": [
                        f"本轮只讨论并输出第{chapter_no}章章纲候选。",
                        "不得把前三章、多章批次、相邻章节写入 artifact_patch.chapter_outlines 或 result_patch.chapter_outlines。",
                        "可以简短提及前后章作为连续性上下文，但只能作为风险、衔接或伏笔说明。",
                        f"chapter_outlines 必须只包含 chapter_no={chapter_no} 的一个对象。",
                        f"本章目标字数为 {scale_plan['chapter_word_target']} 字。",
                    ],
                }
            requested_ranges = [
                {
                    "volume_no": int(chapter_range.volume_no),
                    "start_chapter_no": int(chapter_range.start_chapter_no),
                    "end_chapter_no": int(chapter_range.end_chapter_no),
                }
                for chapter_range in request.chapter_ranges
            ] or self._chapter_ranges_for_request(request)
            return {
                "mode": "chapter_batch",
                "chapter_ranges": requested_ranges,
                "expected_chapter_count": expected_chapters,
                "chapter_window_size": scale_plan["chapter_window_size"],
                "item_key": f"chapters:{expected_chapters}",
                "hard_rules": [
                    "本轮按 chapter_ranges 或规模参数输出批量章纲候选；如果请求没有显式范围，则按 volume_count 与 chapters_per_volume 推导。",
                    "必须先形成 chapter_windows，再从窗口派生 chapter_outlines；窗口大小来自 scale_plan.chapter_window_size，不得写死固定 10 章窗口。",
                    f"chapter_outlines 必须覆盖 {expected_chapters} 个请求章节，不得只输出前三章、单章样例或模板占位。",
                    "每章必须有 state_change、foreshadowing_use、危机/高潮/结果分离和来源窗口。",
                    f"单章目标字数为 {scale_plan['chapter_word_target']} 字。",
                ],
            }
        if phase == "volumes":
            volume_numbers = self._volume_numbers_for_request(request)
            if request.target_volume_no:
                volume_no = self._target_volume_no(request)
                return {
                    "mode": "single_volume",
                    "target_volume_no": volume_no,
                    "item_key": f"volume:{volume_no}",
                    "hard_rules": [
                        f"本轮只讨论并输出第{volume_no}卷卷纲候选。",
                        "不得把全部分卷或相邻卷写入 artifact_patch.volume_outlines 或 result_patch.volume_outlines。",
                        f"volume_outlines 必须只包含 volume_no={volume_no} 的一个对象。",
                        f"本卷规划约 {scale_plan['chapters_per_volume']} 章。",
                    ],
                }
            return {
                "mode": "volume_batch",
                "target_volume_numbers": volume_numbers,
                "item_key": f"volumes:{'-'.join(str(number) for number in volume_numbers)}",
                "hard_rules": [
                    f"本轮按请求规模输出 {len(volume_numbers)} 个卷纲候选。",
                    "volume_outlines 必须覆盖 target_volume_numbers 中的全部卷号，不得只输出第一卷样例。",
                    f"每卷默认约 {scale_plan['chapters_per_volume']} 章，具体区间从规模参数动态推导。",
                ],
            }
        return {
            "mode": "book",
            "hard_rules": [
                "本轮只讨论全书总纲与分卷方向，不生成正式章纲。",
                "所有输出仍是待确认候选，用户确认后才由服务层写入正式记录。",
            ],
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
        focus_constraints = self._phase_focus_constraints(phase, request, scale_plan)
        return {
            "project": serialize_project(project),
            "story_bible": serialize_story_bible(story_bible) if story_bible else {},
            "scale_plan": scale_plan,
            "focus_constraints": focus_constraints,
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
            existing.setdefault("next_agent_name", STORY_DIRECTOR_AGENT)
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
            "next_agent_name": self._next_agent_from_pending_messages(pending_messages) or STORY_DIRECTOR_AGENT,
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

    def _next_round_agent_name(
        self,
        phase_run: dict[str, Any],
        phase: str,
        request: OutlineDebateRunRequest,
        context: dict[str, Any],
    ) -> str:
        for message in reversed(phase_run.get("user_messages", [])):
            target_agent_name = self._valid_agent_name(message.get("target_agent_name", ""))
            if target_agent_name and not message.get("handled_by_turn_id"):
                return target_agent_name
            mentions = message.get("mentions") if isinstance(message.get("mentions"), list) else []
            for mention in mentions:
                target_agent_name = self._valid_agent_name(str(mention))
                if target_agent_name and not message.get("handled_by_turn_id"):
                    return target_agent_name
        return self._next_dynamic_agent_name(phase, request, context, phase_run.get("turns", []), phase_run=phase_run)

    def _max_dynamic_turns(self, request: OutlineDebateRunRequest | None = None) -> int:
        default_turns = len(DEBATE_AGENTS) + 2
        if request is None or request.max_agent_turns is None:
            return default_turns
        return max(1, min(default_turns, int(request.max_agent_turns)))

    def _agent_round_no(self, agent_name: str, turns: list[dict[str, Any]]) -> int:
        return 1 + len([turn for turn in turns if turn.get("agent_name") == agent_name])

    def _next_dynamic_agent_name(
        self,
        phase: str,
        request: OutlineDebateRunRequest,
        context: dict[str, Any],
        turns: list[dict[str, Any]],
        *,
        phase_run: dict[str, Any] | None = None,
    ) -> str:
        if len(turns) >= self._max_dynamic_turns(request):
            return ""
        if not turns:
            return STORY_DIRECTOR_AGENT
        spoken = [str(turn.get("agent_name") or "") for turn in turns]
        spoken_set = set(spoken)
        last_agent = spoken[-1] if spoken else ""
        character_candidates = self._character_candidates_for_policy(None, phase, request, turns, context, include_fallback=False)
        setting_candidates = self._setting_candidates_for_policy(None, phase, request, turns, context, include_fallback=False)
        character_gate = self._candidate_generation_gate("character", phase, request, turns, phase_run)
        setting_gate = self._candidate_generation_gate("setting", phase, request, turns, phase_run)
        if character_gate["enabled"] and character_candidates and CHARACTER_GENERATOR_AGENT not in spoken_set and last_agent != CHARACTER_GENERATOR_AGENT:
            return CHARACTER_GENERATOR_AGENT
        if setting_gate["enabled"] and setting_candidates and SETTING_GENERATOR_AGENT not in spoken_set and last_agent != SETTING_GENERATOR_AGENT:
            return SETTING_GENERATOR_AGENT

        text = self._debate_signal_text(request, turns, phase_run)
        if character_gate["enabled"] and self._has_candidate_positive_signal(text, "character") and CHARACTER_GENERATOR_AGENT not in spoken_set:
            return CHARACTER_GENERATOR_AGENT
        if setting_gate["enabled"] and self._has_candidate_positive_signal(text, "setting") and SETTING_GENERATOR_AGENT not in spoken_set:
            return SETTING_GENERATOR_AGENT

        if MARKET_POSITION_AGENT not in spoken_set and self._should_include_market_agent(phase, text):
            return MARKET_POSITION_AGENT
        if STRUCTURE_DOCTOR_AGENT not in spoken_set:
            return STRUCTURE_DOCTOR_AGENT
        if CONTINUITY_AUDITOR_AGENT not in spoken_set:
            return CONTINUITY_AUDITOR_AGENT
        return ""

    def _candidate_generation_gate(
        self,
        kind: str,
        phase: str,
        request: OutlineDebateRunRequest,
        turns: list[dict[str, Any]],
        phase_run: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        text = self._debate_signal_text(request, turns, phase_run)
        compact = "".join(text.split())
        if kind == "character":
            structured = any(turn.get("character_candidate") or turn.get("character_candidates") for turn in turns)
            structured = structured or bool(self._candidate_dicts_from_turns(turns, "character"))
            explicit_terms = ("@角色生成", "角色生成", "角色候选", "人物卡", "新增角色", "补角色", "主角", "反派", "盟友", "导师", "对手", "背叛者", "关键人物")
            object_terms = ("角色", "人物", "主角", "反派", "对手", "盟友", "导师", "背叛", "见证者")
        else:
            structured = any(turn.get("setting_candidate") or turn.get("setting_candidates") for turn in turns)
            structured = structured or bool(self._candidate_dicts_from_turns(turns, "setting"))
            explicit_terms = ("@设定生成", "设定生成", "设定候选", "新增设定", "补设定", "世界规则", "规则成本", "组织", "地点", "物件", "制度")
            object_terms = ("设定", "规则", "组织", "地点", "物件", "资源", "禁忌", "制度", "世界观")
        impact_terms = ("重要", "核心", "主线", "卷纲", "章纲", "伏笔", "正典", "冲突", "危机", "高潮", "代价", "关系", "首次", "first_needed_in", "importance_level", "importance_score")
        if structured:
            return {"enabled": True, "reason": "已有结构化候选输出，需要进入候选处理。"}
        if any(term in compact for term in explicit_terms):
            return {"enabled": True, "reason": "用户、主持或议事文本明确要求生成候选。"}
        if any(term in compact for term in object_terms) and any(term in compact for term in impact_terms):
            return {"enabled": True, "reason": "提及对象同时影响主线、伏笔、正典、冲突或首次需要时机。"}
        if phase in {"book", "volumes"} and any(term in compact for term in object_terms) and any(term in compact for term in ("中等", "medium", "S级", "A级", "核心", "关键")):
            return {"enabled": True, "reason": "总纲/卷纲阶段出现中等以上重要对象。"}
        return {"enabled": False, "reason": "未达到重要性、明确点名或主线影响触发门槛；仅作为轻量提及处理。"}

    def _default_agent_decision(self, agent_name: str) -> str:
        if agent_name == CONTINUITY_AUDITOR_AGENT:
            return "pass"
        return "revise"

    def _default_agent_audit_status(self, agent_name: str) -> str:
        if agent_name == CONTINUITY_AUDITOR_AGENT:
            return "passed_with_notes"
        return ""

    def _default_agent_scores(self, agent_name: str) -> dict[str, int]:
        if agent_name == STORY_DIRECTOR_AGENT:
            return {"story_promise": 72, "selling": 68, "structure": 70, "character": 65, "setting": 65, "continuity": 70}
        if agent_name == MARKET_POSITION_AGENT:
            return {"selling": 72, "hook_strength": 70, "payoff_signal": 64, "genre_fit": 72, "reader_pressure": 68}
        if agent_name == STRUCTURE_DOCTOR_AGENT:
            return {"structure": 70, "causality": 68, "rhythm_fit": 70, "chapter_density": 66, "crisis_climax_result": 68}
        if agent_name == CHARACTER_GENERATOR_AGENT:
            return {"character": 68, "function_fit": 66, "motivation_strength": 64, "relationship_pressure": 64, "duplicate_safety": 70}
        if agent_name == SETTING_GENERATOR_AGENT:
            return {"setting": 68, "conflict_utility": 66, "rule_cost": 64, "reveal_timing": 64, "continuity_safety": 70}
        if agent_name == CONTINUITY_AUDITOR_AGENT:
            return {"continuity": 72, "canon_safety": 70, "timeline_safety": 68, "foreshadowing_safety": 66, "confirmation_safety": 70}
        return {}

    def _should_include_market_agent(self, phase: str, text: str) -> bool:
        compact = "".join(text.split())
        market_signals = ("读者", "类型", "卖点", "爽点", "期待", "平台", "频道", "压迫感")
        return phase in {"book", "volumes"} or any(signal in compact for signal in market_signals)

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
        artifacts, candidate_policy = self._build_artifacts(project, phase, request, result, turns, context)
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
        while len(turns) < self._max_dynamic_turns(request):
            agent_name = self._next_dynamic_agent_name(phase, request, context, turns, phase_run=None)
            if not agent_name:
                break
            role = DEBATE_AGENT_ROLES[agent_name]
            agent_round = self._agent_round_no(agent_name, turns)
            turn = self._build_turn(project, phase, request, context, agent_name, role, len(turns) + 1, agent_round, agenda, deliberation_state)
            turns.append(turn)
            orchestrator.apply_turn_to_state(deliberation_state, turn)
            next_agent_name = self._next_dynamic_agent_name(phase, request, context, turns, phase_run=None)
            route_decision = self._route_decision_for_next_agent(phase, request, context, turns, next_agent_name, phase_run=None)
            self._attach_turn_display(turn, next_agent_name, route_decision)
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
            "outline_debate/StoryDirectorAgent": f"{phase_label}从作品承诺出发：{project.premise}。本轮只形成待确认条目；用户确认后由服务层写入正式正典。",
            "outline_debate/MarketPositionAgent": f"目标读者是「{reader}」。本轮要检查爽点、压迫、期待管理和平台可读性是否互相支撑。",
            "outline_debate/StructureDoctorAgent": f"结构建议围绕因果推进、阶段代价和钩子密度展开；需求是：{requirement}",
            "outline_debate/CharacterGeneratorAgent": "本轮讨论中出现未入库新角色时，立即提出待确认角色档案；用户确认本阶段或条目后由服务层直接入库。",
            "outline_debate/SettingGeneratorAgent": "本轮讨论中出现未入库新规则、场景、地点、组织或物件时，立即提出待确认设定档案；用户确认本阶段或条目后由服务层直接入库。",
            "outline_debate/ContinuityAuditorAgent": "检查危机、高潮、结果是否混淆，并把不确定项标为待确认或风险；确认后由服务层写入正典，不硬编未确认事实。",
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
            "character_candidates": [],
            "character_count_plan": {},
            "setting_candidate": {},
            "setting_candidates": [],
            "setting_count_plan": {},
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
                    f"执行{phase_label}讨论的第 {round_no} 个席位回合。"
                    "必须优先遵循 context.agent_skill.content 中的角色技能文件；"
                    "必须逐条遵循 context.focus_constraints.hard_rules；"
                    "请围绕 context.agenda、context.deliberation_state、context.requirement、项目资料、用户插话和上游阶段结果提出结构化意见；"
                    "必须回应前序发言，必要时提出 objections；必须给出 proposed_decisions、uncertainties、confidence。"
                    "真实模型输出的 message/claims/risks 必须以中文为主，接口 JSON 字段名可以保持英文。"
                    "artifact_patch 用于写入待确认大纲：总纲阶段写 book_outline，卷纲阶段写 volume_outlines，章纲阶段可写 chapter_windows 与 chapter_outlines。"
                    "当章纲阶段 mode=single_chapter 时，chapter_outlines 只能包含 context.focus_constraints.target_chapter_no 对应的单章对象；"
                    "当章纲阶段 mode=chapter_batch 时，必须按 context.focus_constraints.chapter_ranges 与 scale_plan 动态覆盖全部请求章节，不得只输出前三章或单章样例。"
                    "如你是角色生成或设定生成席位，必须先输出功能审计；只有达到候选触发门槛的新对象才给出待确认档案，用户确认后由服务层直接入库。"
                ),
                context=turn_context,
                fallback=output_contract,
                model=request.model,
                require_remote=True,
                allow_fallback=False,
            )
            self._ensure_remote_turn_main_fields_chinese_first(agent_name, payload)
        raw_decision = payload.get("decision")
        raw_scores = payload.get("scores")
        decision = self._string_or(raw_decision, self._default_agent_decision(agent_name))
        scores = raw_scores if isinstance(raw_scores, dict) and raw_scores else self._default_agent_scores(agent_name)
        decision_source = "model" if isinstance(raw_decision, str) and raw_decision.strip() else "service_default"
        score_source = "model" if isinstance(raw_scores, dict) and raw_scores else "service_default"
        if request.local_preview:
            decision_source = "local_preview" if isinstance(raw_decision, str) and raw_decision.strip() else decision_source
            score_source = "local_preview" if isinstance(raw_scores, dict) and raw_scores else score_source
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
            "decision": decision,
            "decision_source": decision_source,
            "audit_status": self._string_or(payload.get("audit_status"), self._default_agent_audit_status(agent_name)),
            "scores": scores,
            "score_source": score_source,
            "blocking_items": payload.get("blocking_items") if isinstance(payload.get("blocking_items"), list) else [],
            "must_fix_before_confirm": payload.get("must_fix_before_confirm") if isinstance(payload.get("must_fix_before_confirm"), list) else [],
            "challenge_targets": payload.get("challenge_targets") if isinstance(payload.get("challenge_targets"), list) else [],
            "response_to_objections": payload.get("response_to_objections") if isinstance(payload.get("response_to_objections"), list) else [],
            "adopted": payload.get("adopted") if isinstance(payload.get("adopted"), list) else [],
            "rejected": payload.get("rejected") if isinstance(payload.get("rejected"), list) else [],
            "pending": payload.get("pending") if isinstance(payload.get("pending"), list) else [],
            "next_agent": self._string_or(payload.get("next_agent"), local_preview_payload.get("next_agent", "") if request.local_preview else ""),
            "reader_promise_audit": payload.get("reader_promise_audit") if isinstance(payload.get("reader_promise_audit"), dict) else {},
            "structure_audit": payload.get("structure_audit") if isinstance(payload.get("structure_audit"), dict) else {},
            "character_function_audit": payload.get("character_function_audit") if isinstance(payload.get("character_function_audit"), dict) else {},
            "setting_function_audit": payload.get("setting_function_audit") if isinstance(payload.get("setting_function_audit"), dict) else {},
            "candidate_trigger": payload.get("candidate_trigger") if isinstance(payload.get("candidate_trigger"), dict) else {},
            "result_patch": payload.get("result_patch") if isinstance(payload.get("result_patch"), dict) else (payload.get("artifact_patch") if isinstance(payload.get("artifact_patch"), dict) else {}),
            "character_candidate": payload.get("character_candidate") if isinstance(payload.get("character_candidate"), dict) else {},
            "character_candidates": payload.get("character_candidates") if isinstance(payload.get("character_candidates"), list) else [],
            "character_count_plan": payload.get("character_count_plan") if isinstance(payload.get("character_count_plan"), dict) else {},
            "setting_candidate": payload.get("setting_candidate") if isinstance(payload.get("setting_candidate"), dict) else {},
            "setting_candidates": payload.get("setting_candidates") if isinstance(payload.get("setting_candidates"), list) else [],
            "setting_count_plan": payload.get("setting_count_plan") if isinstance(payload.get("setting_count_plan"), dict) else {},
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
            await asyncio.sleep(0.001)
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

    def _route_decision_for_next_agent(
        self,
        phase: str,
        request: OutlineDebateRunRequest,
        context: dict[str, Any],
        turns: list[dict[str, Any]],
        next_agent_name: str,
        *,
        phase_run: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        current_agent = str(turns[-1].get("agent_name") or "") if turns else ""
        model_suggested_agent = self._valid_agent_name(str(turns[-1].get("next_agent") or "")) if turns else ""
        if not next_agent_name:
            return {
                "from_agent_name": current_agent,
                "selected_agent_name": "",
                "model_suggested_agent": model_suggested_agent,
                "source": "finish",
                "overridden": bool(model_suggested_agent),
                "reason": "已达到阶段发言上限或必需审查席位已完成，下一步形成阶段结论。",
            }
        for message in reversed((phase_run or {}).get("user_messages", [])):
            if not isinstance(message, dict) or message.get("handled_by_turn_id"):
                continue
            target_agent_name = self._valid_agent_name(message.get("target_agent_name", ""))
            mentions = message.get("mentions") if isinstance(message.get("mentions"), list) else []
            mentioned_agents = {self._valid_agent_name(str(item)) for item in mentions}
            if target_agent_name == next_agent_name or next_agent_name in mentioned_agents:
                return {
                    "from_agent_name": current_agent,
                    "selected_agent_name": next_agent_name,
                    "model_suggested_agent": model_suggested_agent,
                    "source": "user_message",
                    "overridden": bool(model_suggested_agent and model_suggested_agent != next_agent_name),
                    "reason": "用户未处理的 @ 指定或目标席位优先进入下一轮回应。",
                }
        if model_suggested_agent == next_agent_name:
            return {
                "from_agent_name": current_agent,
                "selected_agent_name": next_agent_name,
                "model_suggested_agent": model_suggested_agent,
                "source": "model_suggestion",
                "overridden": False,
                "reason": "模型建议的下一席通过服务层 allowlist 与阶段约束校验。",
            }
        if next_agent_name == CHARACTER_GENERATOR_AGENT:
            gate = self._candidate_generation_gate("character", phase, request, turns, phase_run)
            return {
                "from_agent_name": current_agent,
                "selected_agent_name": next_agent_name,
                "model_suggested_agent": model_suggested_agent,
                "source": "candidate_gate",
                "overridden": bool(model_suggested_agent and model_suggested_agent != next_agent_name),
                "reason": f"角色候选门槛触发：{gate['reason']}",
            }
        if next_agent_name == SETTING_GENERATOR_AGENT:
            gate = self._candidate_generation_gate("setting", phase, request, turns, phase_run)
            return {
                "from_agent_name": current_agent,
                "selected_agent_name": next_agent_name,
                "model_suggested_agent": model_suggested_agent,
                "source": "candidate_gate",
                "overridden": bool(model_suggested_agent and model_suggested_agent != next_agent_name),
                "reason": f"设定候选门槛触发：{gate['reason']}",
            }
        policy_reasons = {
            STORY_DIRECTOR_AGENT: "主持总策划负责开场、收束议程和确认候选边界。",
            MARKET_POSITION_AGENT: "类型卖点席位检查读者承诺、追读钩子和兑现路径。",
            STRUCTURE_DOCTOR_AGENT: "结构医生席位检查长篇因果、节奏模型和危机/高潮/结果边界。",
            CONTINUITY_AUDITOR_AGENT: "连续性审计席位检查正典冲突、伏笔、时间线和确认安全。",
        }
        return {
            "from_agent_name": current_agent,
            "selected_agent_name": next_agent_name,
            "model_suggested_agent": model_suggested_agent,
            "source": "phase_policy",
            "overridden": bool(model_suggested_agent and model_suggested_agent != next_agent_name),
            "reason": policy_reasons.get(next_agent_name, "服务层按阶段策略选择下一席。"),
        }

    def _attach_turn_display(self, turn: dict[str, Any], next_agent_name: str = "", route_decision: dict[str, Any] | None = None) -> None:
        current_label = self._agent_mention_label(str(turn.get("agent_name") or ""))
        next_label = self._agent_mention_label(next_agent_name)
        if route_decision is None:
            route_decision = turn.get("route_decision") if isinstance(turn.get("route_decision"), dict) else {}
        if not route_decision:
            route_decision = {
                "from_agent_name": turn.get("agent_name", ""),
                "selected_agent_name": next_agent_name,
                "model_suggested_agent": self._valid_agent_name(str(turn.get("next_agent") or "")),
                "source": "legacy_display_refresh",
                "overridden": False,
                "reason": "根据已保存的下一席刷新展示文本。",
            }
        handoff = {
            "from_agent_name": turn.get("agent_name", ""),
            "from_label": current_label,
            "from_mention": f"@{current_label}" if current_label else "",
            "to_agent_name": next_agent_name,
            "to_label": next_label,
            "to_mention": f"@{next_label}" if next_label else "",
            "display": f"@{current_label} → @{next_label}" if next_label else f"@{current_label} → 阶段结论",
            "reason": str(route_decision.get("reason") or ""),
            "source": str(route_decision.get("source") or ""),
        }
        turn["next_agent_name"] = next_agent_name
        turn["route_decision"] = route_decision
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
            ("角色数量规划", turn.get("character_count_plan")),
            ("角色候选", turn.get("character_candidate")),
            ("角色候选列表", turn.get("character_candidates")),
            ("设定数量规划", turn.get("setting_count_plan")),
            ("设定候选", turn.get("setting_candidate")),
            ("设定候选列表", turn.get("setting_candidates")),
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
        if handoff.get("reason"):
            lines.append(f"交接原因：{handoff['reason']}")
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
            return [f"{project.title}的{PHASE_CONFIG[phase]['label']}必须服务一句话故事", "所有结论先待确认，用户确认后直接入库"]
        if agent_name.endswith("MarketPositionAgent"):
            return [f"目标读者体验来自：{project.target_reader}", "卖点必须转化为可持续冲突和章节钩子"]
        if agent_name.endswith("StructureDoctorAgent"):
            return ["危机是不可逆选择，高潮是执行选择，结果是承担后果", "卷纲与章纲不能只堆事件，必须说明状态改变"]
        if agent_name.endswith("CharacterGeneratorAgent"):
            return ["新增角色必须有剧情功能、首次需要位置和重复检查", "待确认角色随用户确认由服务层入 characters 表"]
        if agent_name.endswith("SettingGeneratorAgent"):
            return ["新增设定必须解释冲突用途、伏笔用途和连续性风险", "待确认设定随用户确认由服务层入 world_facts 或 entities 表"]
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
            fallback_book_outline = self._book_outline_from_debate(project, turns)
            result = {
                "generation_kind": generation_kind,
                "scale_plan": scale_plan,
                "book_outline": fallback_book_outline,
                "discussion_summary": [turn["message"] for turn in turns[:3]],
                "requires_user_confirmation": True,
                "synthesis_source": "debate_state",
                "source_turn_ids": source_turn_ids,
                "_provenance": provenance,
            }
            merged = self._merge_result_patches(result, turns, ("book_outline", "discussion_summary"), deliberation_state)
            merged["book_outline"] = self._normalize_book_outline_candidate(fallback_book_outline, merged.get("book_outline"))
            return self._attach_phase_conclusion(project, phase, request, turns, merged)
        if phase == "volumes":
            volume_numbers = self._volume_numbers_for_request(request)
            target_volume_no = volume_numbers[0] if volume_numbers else self._target_volume_no(request)
            result = {
                "generation_kind": generation_kind,
                "scale_plan": scale_plan,
                "target_volume_no": target_volume_no,
                "target_volume_numbers": volume_numbers,
                "expected_volume_count": scale_plan["volume_count"],
                "item_key": f"volumes:{'-'.join(str(number) for number in volume_numbers)}" if len(volume_numbers) > 1 else f"volume:{target_volume_no}",
                "volume_outlines": [self._volume_candidate_from_debate(volume_no, project, request, turns) for volume_no in volume_numbers],
                "upstream_book_run_id": session.get("phase_runs", {}).get("book", {}).get("id", ""),
                "requires_user_confirmation": True,
                "synthesis_source": "debate_state",
                "source_turn_ids": source_turn_ids,
                "_provenance": provenance,
            }
            merged = self._restrict_itemized_result(phase, request, self._merge_result_patches(result, turns, ("volume_outlines",), deliberation_state))
            merged = self._ensure_complete_volume_batch(project, request, turns, merged)
            enriched = self._attach_outline_quality_metrics(phase, request, merged)
            return self._attach_phase_conclusion(project, phase, request, turns, enriched)
        target_volume_no = self._target_volume_no(request)
        target_chapter_no = self._target_chapter_no(request)
        chapter_windows = self._chapter_windows_from_debate(project, request, turns)
        result = {
            "generation_kind": generation_kind,
            "scale_plan": scale_plan,
            "target_volume_no": target_volume_no,
            "target_chapter_no": target_chapter_no,
            "expected_chapter_count": len(self._chapter_candidates_for_request(request)),
            "expected_chapter_window_count": len(chapter_windows),
            "item_key": f"chapters:{len(self._chapter_candidates_for_request(request))}" if not request.target_chapter_no else f"chapter:{target_chapter_no}",
            "chapter_windows": chapter_windows,
            "chapter_outlines": self._chapter_candidates_from_debate(project, request, turns, chapter_windows),
            "upstream_volume_run_id": session.get("phase_runs", {}).get("volumes", {}).get("id", ""),
            "requires_user_confirmation": True,
            "synthesis_source": "debate_state",
            "source_turn_ids": source_turn_ids,
            "_provenance": provenance,
        }
        merged = self._restrict_itemized_result(phase, request, self._merge_result_patches(result, turns, ("chapter_windows", "chapter_outlines"), deliberation_state))
        merged = self._ensure_complete_chapter_batch(project, request, turns, merged)
        enriched = self._attach_outline_quality_metrics(phase, request, merged)
        return self._attach_phase_conclusion(project, phase, request, turns, enriched)

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
                value = self._patch_value_for_key(patch, key)
                if value in (None, "", [], {}):
                    continue
                if key in {"volume_outlines", "chapter_outlines"}:
                    value = self._coerce_outline_items("volumes" if key == "volume_outlines" else "chapters", value)
                    if not value:
                        continue
                if isinstance(value, dict) and isinstance(merged.get(key), dict):
                    merged[key] = self._deep_merge_dicts(merged[key], value)
                elif key in {"volume_outlines", "chapter_outlines"} and isinstance(merged.get(key), list) and isinstance(value, list):
                    merged[key] = self._merge_outline_item_lists("volumes" if key == "volume_outlines" else "chapters", merged[key], value)
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

    def _normalize_book_outline_candidate(self, fallback: dict[str, Any], value: Any) -> dict[str, Any]:
        candidate = value if isinstance(value, dict) else {}
        normalized = self._deep_merge_dicts(fallback, candidate)
        main_conflict = self._string_or(
            normalized.get("main_conflict") or normalized.get("core_conflict") or normalized.get("mainline"),
            fallback.get("main_conflict") or fallback.get("premise") or fallback.get("title") or "",
        )
        normalized["main_conflict"] = main_conflict
        normalized["core_promise"] = self._string_or(normalized.get("core_promise"), fallback.get("core_promise") or main_conflict)
        normalized["ending_direction"] = self._string_or(normalized.get("ending_direction"), fallback.get("ending_direction") or "终局方向待用户确认。")
        normalized["reader_experience"] = self._string_or(normalized.get("reader_experience"), fallback.get("reader_experience") or "")
        return normalized

    def _volume_candidate_from_debate(self, volume_no: int, project: models.Project, request: OutlineDebateRunRequest, turns: list[dict[str, Any]]) -> dict[str, Any]:
        model_name = "多线群像并进" if any(key in project.genre for key in ("权谋", "战争", "群像")) else "动态长篇升级"
        scale_plan = self._scale_plan(project, request)
        chapters_per_volume = scale_plan["chapters_per_volume"]
        phase_count = self._volume_phase_count(chapters_per_volume)
        chapter_start, chapter_end = self._volume_chapter_bounds(volume_no, chapters_per_volume)
        stage_axis = STATE_CHANGE_AXES[(volume_no - 1) % len(STATE_CHANGE_AXES)]
        volume_function = self._debate_sentence(turns, ("StructureDoctorAgent", "StoryDirectorAgent"), f"围绕{stage_axis}变化承接上游总纲，并改变主角处境。")
        main_conflict = self._debate_sentence(turns, ("StructureDoctorAgent", "MarketPositionAgent"), f"本卷通过{stage_axis}升级持续压迫主线冲突。")
        ending_hook = self._debate_sentence(turns, ("ContinuityAuditorAgent", "StructureDoctorAgent"), f"本卷末让{stage_axis}问题升级为下一卷必须回应的新压力。")
        return {
            "volume_no": volume_no,
            "title": f"第{volume_no}卷：{self._short_label(self._debate_sentence(turns, ('StructureDoctorAgent', 'StoryDirectorAgent'), f'{stage_axis}升级'))}",
            "chapter_range": f"{chapter_start}-{chapter_end}",
            "volume_function": f"第{volume_no}卷围绕{stage_axis}推进：{volume_function}",
            "rhythm_model": {
                "model_name": model_name,
                "why_this_model": self._debate_sentence(turns, ("StructureDoctorAgent",), "根据类型、读者体验和阶段冲突选择。"),
                "phase_count": phase_count,
                "chapter_distribution": self._phase_distribution(chapters_per_volume, phase_count),
                "absolute_chapter_distribution": self._absolute_phase_distribution(chapter_start, chapter_end, phase_count),
            },
            "core_goal": f"第{volume_no}卷目标：{self._debate_sentence(turns, ('StoryDirectorAgent', 'MarketPositionAgent'), f'让主角在{stage_axis}上付出代价并获得阶段突破。')}",
            "main_conflict": main_conflict,
            "ending_hook": ending_hook,
            "volume_hook": ending_hook,
            "character_arc": f"主角围绕{stage_axis}从被动承压转为主动承担代价，关系网络至少改变一次。",
            "setting_reveal_plan": [f"第{chapter_start}-{chapter_end}章逐步展示与{stage_axis}相关的规则成本、限制和误导。"],
            "foreshadowing_plan": [f"本卷开端种下{stage_axis}伏笔，中段提醒或误导，卷末完成阶段兑现并转入下一卷压力。"],
            "risks": self._list_from_turns(turns, "risks")[:4],
        }

    def _volume_phase_count(self, chapters_per_volume: int) -> int:
        if chapters_per_volume >= 80:
            return 6
        if chapters_per_volume >= 45:
            return 5
        if chapters_per_volume >= 20:
            return 4
        return max(2, min(3, chapters_per_volume))

    def _volume_chapter_bounds(self, volume_no: int, chapters_per_volume: int) -> tuple[int, int]:
        start = (volume_no - 1) * chapters_per_volume + 1
        return start, start + chapters_per_volume - 1

    def _absolute_phase_distribution(self, start_chapter_no: int, end_chapter_no: int, phase_count: int) -> str:
        total = max(1, end_chapter_no - start_chapter_no + 1)
        segment = max(1, total // max(1, phase_count))
        ranges = []
        start = start_chapter_no
        for index in range(1, phase_count + 1):
            end = end_chapter_no if index == phase_count else min(end_chapter_no, start + segment - 1)
            ranges.append(f"{start}-{end}")
            start = end + 1
        return " / ".join(ranges)

    def _chapter_window_size(self, request: OutlineDebateRunRequest) -> int:
        scale_plan = self._scale_plan_from_request_only(request)
        requested_count = len(self._chapter_candidates_for_request(request))
        if requested_count <= 1:
            return 1
        explicit_size = self._bounded_int(scale_plan.get("chapter_window_size"), 0, 0, 300)
        if explicit_size:
            return max(1, min(explicit_size, requested_count))
        chapters_per_volume = self._bounded_int(scale_plan.get("chapters_per_volume") or request.chapters_per_volume, request.chapters_per_volume or requested_count, 1, 300)
        return max(1, min(requested_count, round(chapters_per_volume / DEFAULT_CHAPTER_WINDOWS_PER_VOLUME)))

    def _scale_plan_from_request_only(self, request: OutlineDebateRunRequest) -> dict[str, int]:
        source = request.scale_plan if isinstance(request.scale_plan, dict) else {}
        volume_count = self._bounded_int(source.get("volume_count") or request.volume_count, request.volume_count or 1, 1, 30)
        chapters_per_volume = self._bounded_int(source.get("chapters_per_volume") or request.chapters_per_volume, request.chapters_per_volume or 1, 1, 300)
        chapter_count = self._bounded_int(source.get("chapter_count"), volume_count * chapters_per_volume, 1, 6000)
        chapter_window_size = self._bounded_int(
            source.get("chapter_window_size"),
            max(1, round(chapters_per_volume / DEFAULT_CHAPTER_WINDOWS_PER_VOLUME)),
            1,
            300,
        )
        return {
            "volume_count": volume_count,
            "chapters_per_volume": chapters_per_volume,
            "chapter_count": chapter_count,
            "chapter_window_size": chapter_window_size,
        }

    def _chapter_windows_from_debate(self, project: models.Project, request: OutlineDebateRunRequest, turns: list[dict[str, Any]]) -> list[dict[str, Any]]:
        windows: list[dict[str, Any]] = []
        window_size = self._chapter_window_size(request)
        premise_label = self._short_label(project.premise or project.title)
        chapter_ranges = self._chapter_ranges_for_request(request)
        final_requested_chapter = max(int(chapter_range["end_chapter_no"]) for chapter_range in chapter_ranges) if chapter_ranges else 1
        for chapter_range in chapter_ranges:
            volume_no = int(chapter_range["volume_no"])
            current = int(chapter_range["start_chapter_no"])
            end_no = int(chapter_range["end_chapter_no"])
            local_window_no = 1
            while current <= end_no:
                window_end = min(end_no, current + window_size - 1)
                axis = STATE_CHANGE_AXES[(len(windows)) % len(STATE_CHANGE_AXES)]
                window_no = len(windows) + 1
                function = self._window_function_for_index(window_no)
                is_volume_final = window_end == end_no
                is_final_window = window_end == final_requested_chapter
                stage_goal = f"围绕「{premise_label}」让{axis}发生可见变化，并完成{function}。"
                main_pressure = self._safe_debate_sentence(turns, ("StructureDoctorAgent", "MarketPositionAgent"), "反对力量必须把抽象压力落到可行动的选择上。")
                foreshadowing_plan = self._window_foreshadowing_plan(axis, current, window_end, is_volume_final, is_final_window)
                mini_crisis = f"窗口危机：主角必须在{axis}继续恶化前作出不可逆选择。"
                mini_climax = f"窗口高潮：第{window_end}章执行选择并兑现{axis}的阶段代价。"
                transition_hook = (
                    f"第{window_end}章完成卷末功能，并把{axis}压力转入下一卷。"
                    if is_volume_final and not is_final_window
                    else (
                        f"第{window_end}章完成阶段收束，并留下后续创作方向钩子。"
                        if is_final_window
                        else f"第{window_end}章把{axis}的新问题交给下一窗口。"
                    )
                )
                windows.append(
                    {
                        "window_no": window_no,
                        "volume_no": volume_no,
                        "local_window_no": local_window_no,
                        "start_chapter_no": current,
                        "end_chapter_no": window_end,
                        "chapter_range": f"{current}-{window_end}",
                        "window_range": f"{current}-{window_end}",
                        "window_size": window_end - current + 1,
                        "window_axis": axis,
                        "window_function": function,
                        "stage_goal": stage_goal,
                        "window_goal": stage_goal,
                        "reader_promise": self._safe_debate_sentence(turns, ("MarketPositionAgent",), f"读者在本窗口期待看到{axis}升级、代价兑现和新钩子。"),
                        "main_pressure": main_pressure,
                        "opposition_pressure": main_pressure,
                        "state_change_goal": f"{axis}从窗口开局状态推进到必须承担代价的新状态。",
                        "new_information": f"本窗口揭示一条与{axis}相关的新信息，改变主角判断。",
                        "relationship_change": f"至少一组关系因{axis}压力出现信任、债务或立场变化。",
                        "resource_change": f"主角资源、筹码或行动空间因{axis}变化出现增减。",
                        "rule_or_setting_reveal": f"展示一条与{axis}有关的规则、限制、成本或误导。",
                        **foreshadowing_plan,
                        "mini_crisis": mini_crisis,
                        "mini_climax": mini_climax,
                        "transition_hook": transition_hook,
                        "payoff_expectation": self._safe_debate_sentence(turns, ("MarketPositionAgent", "ContinuityAuditorAgent"), "本窗口至少种下、提醒或回收一个可追踪期待。"),
                        "volume_function_role": "volume_climax" if is_volume_final else "mid_volume_window",
                        "final_function_role": "book_or_phase_turn" if is_final_window else "",
                        "risk": f"{axis}变化若没有具体代价，窗口会退化为事件流水账。",
                        "source": "debate_state_window_synthesis",
                    }
                )
                current = window_end + 1
                local_window_no += 1
        return windows

    def _window_function_for_index(self, window_no: int) -> str:
        functions = ("建立压力", "扩大误差", "付出代价", "揭示规则", "反转目标", "兑现伏笔", "重组关系", "打开新局")
        return functions[(window_no - 1) % len(functions)]

    def _window_foreshadowing_plan(self, axis: str, start_chapter_no: int, end_chapter_no: int, is_volume_final: bool, is_final_window: bool) -> dict[str, list[str]]:
        return {
            "foreshadowing_to_plant": [f"第{start_chapter_no}章种下{axis}异常或代价的证据。"],
            "foreshadowing_to_remind": [f"窗口中段提醒{axis}伏笔仍在影响选择。"],
            "foreshadowing_to_mislead": [f"用{axis}相关误导制造错误判断，但保留可回溯证据。"],
            "foreshadowing_to_payoff": [
                (
                    f"第{end_chapter_no}章完成卷末/阶段兑现。"
                    if is_volume_final or is_final_window
                    else f"第{end_chapter_no}章完成窗口级小兑现。"
                )
            ],
        }

    def _chapter_candidates_from_debate(
        self,
        project: models.Project,
        request: OutlineDebateRunRequest,
        turns: list[dict[str, Any]],
        chapter_windows: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        candidates = []
        scale_plan = self._scale_plan(project, request)
        windows = chapter_windows or self._chapter_windows_from_debate(project, request, turns)
        window_by_chapter: dict[int, dict[str, Any]] = {}
        for window in windows:
            for chapter_no in range(int(window["start_chapter_no"]), int(window["end_chapter_no"]) + 1):
                window_by_chapter[chapter_no] = window
        for volume_no, chapter_no in self._chapter_candidates_for_request(request):
            window = window_by_chapter.get(chapter_no) or {
                "window_no": 1,
                "volume_no": volume_no,
                "start_chapter_no": chapter_no,
                "end_chapter_no": chapter_no,
                "window_range": f"{chapter_no}-{chapter_no}",
                "window_axis": STATE_CHANGE_AXES[(chapter_no - 1) % len(STATE_CHANGE_AXES)],
                "window_function": "建立压力",
                "window_goal": "完成本章必要状态改变。",
                "opposition_pressure": "反对力量制造选择压力。",
                "payoff_expectation": "保留可追踪期待。",
            }
            window_start = int(window.get("start_chapter_no") or chapter_no)
            window_end = int(window.get("end_chapter_no") or chapter_no)
            within_window = chapter_no - window_start + 1
            axis = str(window.get("window_axis") or STATE_CHANGE_AXES[(chapter_no - 1) % len(STATE_CHANGE_AXES)])
            state_change = self._chapter_state_change(axis, chapter_no, window_start, window_end)
            foreshadowing_use = self._chapter_foreshadowing_use(chapter_no, window_start, window_end)
            state_change_text = self._state_change_text(state_change)
            foreshadowing_use_text = self._foreshadowing_use_text(foreshadowing_use)
            crisis, climax, outcome = self._distinct_chapter_beats(turns, chapter_no, state_change_text, window)
            short_goal = self._short_label(str(window.get("window_goal") or project.premise or project.title))
            is_volume_end = chapter_no == window_end and str(window.get("volume_function_role") or "") == "volume_climax"
            is_final_turn = chapter_no == window_end and str(window.get("final_function_role") or "") == "book_or_phase_turn"
            milestone_function = "book_or_phase_turn" if is_final_turn else ("volume_climax" if is_volume_end else "")
            title = f"第{chapter_no}章：{self._chapter_title_for_window(chapter_no, within_window, axis, short_goal)}"
            conflict = self._chapter_conflict_for_window(project, chapter_no, axis, window, within_window)
            core_event = f"主角围绕{axis}作出一次可见行动，迫使局面从窗口开局状态推进到第{within_window}个变化点。"
            hook = f"章末把{axis}的新问题交给{self._next_chapter_label(chapter_no, window_end)}。"
            outline_body = self._chapter_outline_body(
                title=title,
                project=project,
                chapter_no=chapter_no,
                volume_no=volume_no,
                window=window,
                core_event=core_event,
                conflict=conflict,
                crisis=crisis,
                climax=climax,
                outcome=outcome,
                hook=hook,
                state_change_text=state_change_text,
                foreshadowing_use_text=foreshadowing_use_text,
                milestone_function=milestone_function,
            )
            candidates.append(
                {
                    "chapter_no": chapter_no,
                    "volume_no": volume_no,
                    "window_no": int(window.get("window_no") or 1),
                    "title": title,
                    "outline": outline_body,
                    "outline_summary": f"本章承接第{window.get('window_no')}窗口「{short_goal}」，让{state_change_text}，并通过{foreshadowing_use_text}维持下一步追读。",
                    "pov_character": "主角",
                    "core_event": core_event,
                    "conflict": conflict,
                    "crisis": crisis,
                    "climax": climax,
                    "result": outcome,
                    "hook": hook,
                    "cliffhanger": hook,
                    "state_change": state_change,
                    "state_change_text": state_change_text,
                    "foreshadowing_use": foreshadowing_use,
                    "reader_promise": str(window.get("reader_promise") or "本章继续兑现窗口级追读承诺。"),
                    "continuity_risk": f"若{axis}变化没有被后续章节承接，将形成状态断裂。",
                    "milestone_function": milestone_function,
                    "source_window": str(window.get("window_range") or f"{window_start}-{window_end}"),
                    "source_window_detail": {
                        "window_no": int(window.get("window_no") or 1),
                        "window_range": str(window.get("window_range") or f"{window_start}-{window_end}"),
                        "window_function": str(window.get("window_function") or ""),
                        "mini_climax": str(window.get("mini_climax") or ""),
                        "transition_hook": str(window.get("transition_hook") or ""),
                    },
                    "word_target": scale_plan["chapter_word_target"],
                    "word_range": [scale_plan["chapter_word_min"], scale_plan["chapter_word_max"]],
                }
            )
        return candidates

    def _chapter_title_for_window(self, chapter_no: int, within_window: int, axis: str, short_goal: str) -> str:
        labels = ("开口", "逼近", "试探", "反压", "折返", "摊牌", "余震", "换局")
        label = labels[(within_window - 1) % len(labels)]
        return self._short_label(f"{axis}{label}{chapter_no}-{short_goal}")

    def _chapter_conflict_for_window(
        self,
        project: models.Project,
        chapter_no: int,
        axis: str,
        window: dict[str, Any],
        within_window: int,
    ) -> str:
        pressure = str(window.get("main_pressure") or window.get("opposition_pressure") or "").strip()
        if self._contains_outline_template(pressure, chapter_no) or "窗口划分" in pressure or "scale_plan" in pressure:
            pressure = ""
        if pressure:
            return pressure
        premise = self._short_label(project.premise or project.title)
        return f"围绕「{premise}」，外部压力把{axis}问题具体化为第{within_window}个选择障碍，主角必须用行动、资源或关系信用换取推进空间。"

    def _chapter_outline_body(
        self,
        *,
        title: str,
        project: models.Project,
        chapter_no: int,
        volume_no: int,
        window: dict[str, Any],
        core_event: str,
        conflict: str,
        crisis: str,
        climax: str,
        outcome: str,
        hook: str,
        state_change_text: str,
        foreshadowing_use_text: str,
        milestone_function: str,
    ) -> str:
        window_no = int(window.get("window_no") or 1)
        window_range = str(window.get("window_range") or window.get("chapter_range") or "")
        milestone = {
            "volume_climax": "本章承担卷末功能，需要完成本卷阶段危机、兑现主要代价，并把压力转入下一卷。",
            "book_or_phase_turn": "本章承担阶段收束或下一阶段钩子功能，需要完成当前大纲范围的核心回收，并打开后续创作压力。",
        }.get(milestone_function, "本章承担窗口内推进功能，需要让行动、阻碍和后果都服务下一章。")
        lines = [
            f"{title}",
            f"所属位置：第{volume_no}卷，第{chapter_no}章；来源窗口：第{window_no}窗口（{window_range}）。",
            f"窗口目标：{window.get('stage_goal') or window.get('window_goal') or project.premise}",
            f"剧情定位：{milestone}",
            f"核心事件：{core_event}",
            f"冲突设计：{conflict}",
            f"危机选择：{crisis}",
            f"高潮执行：{climax}",
            f"结果后果：{outcome}",
            f"状态变化：{state_change_text}",
            f"伏笔用途：{foreshadowing_use_text}",
            f"读者承诺：{window.get('reader_promise') or '本章继续兑现窗口级追读承诺。'}",
            f"连续性风险：若本章的状态变化没有在后续章节承接，会削弱窗口因果链。",
            f"章末钩子：{hook}",
        ]
        return "\n".join(line for line in lines if str(line).strip())

    def _attach_phase_conclusion(
        self,
        project: models.Project,
        phase: str,
        request: OutlineDebateRunRequest,
        turns: list[dict[str, Any]],
        result: dict[str, Any],
    ) -> dict[str, Any]:
        enriched = self._ensure_stage_outline_bodies(project, phase, request, turns, dict(result))
        enriched = self._attach_outline_quality_metrics(phase, request, enriched)
        enriched = self._ensure_repair_policy(enriched)
        enriched = self._attach_synthesis_provenance(enriched)
        conclusion = self._phase_conclusion(project, phase, request, turns, enriched)
        enriched["stage_conclusion"] = conclusion
        enriched["stage_conclusion_text"] = conclusion.get("body", "")
        return enriched

    def _ensure_repair_policy(self, result: dict[str, Any]) -> dict[str, Any]:
        enriched = dict(result)
        repair_policy = enriched.get("repair_policy") if isinstance(enriched.get("repair_policy"), dict) else {}
        if repair_policy:
            repair_policy.setdefault("applied", False)
            enriched["repair_policy"] = repair_policy
            return enriched
        enriched["repair_policy"] = {
            "applied": False,
            "reason": "not_required",
        }
        return enriched

    def _attach_synthesis_provenance(self, result: dict[str, Any]) -> dict[str, Any]:
        enriched = dict(result)
        provenance = enriched.get("_provenance") if isinstance(enriched.get("_provenance"), dict) else {}
        quality_metrics = enriched.get("quality_metrics") if isinstance(enriched.get("quality_metrics"), dict) else {}
        repair_policy = enriched.get("repair_policy") if isinstance(enriched.get("repair_policy"), dict) else {}
        source_turn_ids = [str(item) for item in enriched.get("source_turn_ids", []) if str(item)]
        if not source_turn_ids:
            source_turn_ids = [str(item) for item in provenance.get("source_turn_ids", []) if str(item)]
        artifact_patch_count = int(provenance.get("artifact_patch_count") or 0)
        enriched["synthesis_provenance"] = {
            "source": str(enriched.get("synthesis_source") or provenance.get("source") or "debate_state"),
            "state_id": str(provenance.get("state_id") or ""),
            "source_turn_ids": source_turn_ids,
            "source_turn_count": len(source_turn_ids),
            "artifact_patch_count": artifact_patch_count,
            "model_patch_used": artifact_patch_count > 0,
            "service_repair_applied": bool(repair_policy.get("applied")),
            "repair_reason": str(repair_policy.get("reason") or ""),
            "quality_status": str(quality_metrics.get("status") or "unknown"),
            "blocking_item_count": len(quality_metrics.get("blocking_items", [])) if isinstance(quality_metrics.get("blocking_items"), list) else 0,
        }
        return enriched

    def _ensure_stage_outline_bodies(
        self,
        project: models.Project,
        phase: str,
        request: OutlineDebateRunRequest,
        turns: list[dict[str, Any]],
        result: dict[str, Any],
    ) -> dict[str, Any]:
        if phase != "chapters":
            return result
        windows = result.get("chapter_windows") if isinstance(result.get("chapter_windows"), list) else self._chapter_windows_from_debate(project, request, turns)
        fallback_items = self._chapter_candidates_from_debate(project, request, turns, windows)
        fallback_by_key = {self._item_key_for_candidate("chapters", item): item for item in fallback_items if isinstance(item, dict)}
        incoming_items = result.get("chapter_outlines") if isinstance(result.get("chapter_outlines"), list) else []
        incoming_by_key = {
            self._item_key_for_candidate("chapters", item): item
            for item in incoming_items
            if isinstance(item, dict)
        }
        expanded: list[dict[str, Any]] = []
        for volume_no, chapter_no in self._chapter_candidates_for_request(request):
            item_key = f"chapter:{chapter_no}"
            fallback = fallback_by_key.get(item_key) or self._chapter_candidates_from_debate(project, request, turns, windows)[0]
            merged = self._merge_nonempty_outline(fallback, incoming_by_key.get(item_key, {}))
            outline = str(merged.get("outline") or "")
            if not self._outline_body_is_substantial(outline):
                merged["outline"] = fallback.get("outline", outline)
                merged["outline_expanded_from_stage_conclusion"] = True
            merged["volume_no"] = int(merged.get("volume_no") or volume_no)
            merged["chapter_no"] = int(merged.get("chapter_no") or chapter_no)
            expanded.append(merged)
        enriched = dict(result)
        enriched["chapter_windows"] = windows
        enriched["chapter_outlines"] = expanded
        if any(item.get("outline_expanded_from_stage_conclusion") for item in expanded):
            enriched["outline_expansion_policy"] = {
                "applied": True,
                "reason": "short_or_generic_chapter_outline_expanded_from_stage_conclusion",
            }
        return enriched

    def _outline_body_is_substantial(self, outline: str) -> bool:
        text = str(outline or "").strip()
        if not text or self._contains_outline_template(text):
            return False
        required_labels = ("核心事件", "冲突", "危机", "高潮", "结果", "钩子")
        label_hits = sum(1 for label in required_labels if label in text)
        return label_hits >= 4 and len(text) >= 180

    def _phase_conclusion(
        self,
        project: models.Project,
        phase: str,
        request: OutlineDebateRunRequest,
        turns: list[dict[str, Any]],
        result: dict[str, Any],
    ) -> dict[str, Any]:
        adopted = self._turn_digest(turns, ("adopted", "proposed_decisions", "claims"), limit=8)
        risks = self._turn_digest(turns, ("blocking_items", "must_fix_before_confirm", "risks", "uncertainties"), limit=8)
        title = f"{PHASE_CONFIG[phase]['label']}阶段结论"
        lines = [f"# {title}", "", f"作品：{project.title}", f"阶段目标：{request.requirement or PHASE_CONFIG[phase]['label']}", ""]
        if adopted:
            lines.append("## 采纳的讨论结论")
            lines.extend(f"- {item}" for item in adopted)
            lines.append("")
        if phase == "book":
            book_outline = result.get("book_outline") if isinstance(result.get("book_outline"), dict) else {}
            lines.append("## 总纲正文")
            for label, key in [("作品承诺", "core_promise"), ("主线冲突", "main_conflict"), ("终局方向", "ending_direction"), ("读者体验", "reader_experience")]:
                if book_outline.get(key):
                    lines.append(f"- {label}：{book_outline[key]}")
        elif phase == "volumes":
            lines.append("## 分卷结论")
            for item in result.get("volume_outlines", []) if isinstance(result.get("volume_outlines"), list) else []:
                if not isinstance(item, dict):
                    continue
                lines.extend(
                    [
                        f"### 第{item.get('volume_no')}卷 {item.get('title', '')}",
                        f"- 章节区间：{item.get('chapter_range', '')}",
                        f"- 本卷功能：{item.get('volume_function', '')}",
                        f"- 核心目标：{item.get('core_goal', '')}",
                        f"- 主线冲突：{item.get('main_conflict', '')}",
                        f"- 卷末钩子：{item.get('ending_hook') or item.get('volume_hook') or ''}",
                    ]
                )
                rhythm = item.get("rhythm_model") if isinstance(item.get("rhythm_model"), dict) else {}
                if rhythm:
                    lines.append(f"- 节奏模型：{rhythm.get('model_name', '')}；分布：{rhythm.get('absolute_chapter_distribution') or rhythm.get('chapter_distribution') or ''}")
        else:
            windows = result.get("chapter_windows") if isinstance(result.get("chapter_windows"), list) else []
            chapters = result.get("chapter_outlines") if isinstance(result.get("chapter_outlines"), list) else []
            lines.append("## 章纲阶段结论")
            lines.append(f"- 已形成章节窗口：{len(windows)} 个。")
            lines.append(f"- 已形成章节章纲：{len(chapters)} 章。")
            lines.append("")
            lines.append("## 窗口结构")
            for window in windows:
                if not isinstance(window, dict):
                    continue
                lines.extend(
                    [
                        f"### 第{window.get('window_no')}窗口（{window.get('window_range') or window.get('chapter_range')}）",
                        f"- 阶段目标：{window.get('stage_goal') or window.get('window_goal')}",
                        f"- 主压力：{window.get('main_pressure') or window.get('opposition_pressure')}",
                        f"- 小危机：{window.get('mini_crisis')}",
                        f"- 小高潮：{window.get('mini_climax')}",
                        f"- 过渡钩子：{window.get('transition_hook')}",
                    ]
                )
            milestone_chapters = [
                item
                for item in chapters
                if isinstance(item, dict) and item.get("milestone_function") in {"volume_climax", "book_or_phase_turn"}
            ]
            if milestone_chapters:
                lines.append("")
                lines.append("## 关键里程碑章节")
                for item in milestone_chapters:
                    lines.append(f"- 第{item.get('chapter_no')}章：{item.get('title')}；功能：{item.get('milestone_function')}；结果：{item.get('result')}")
            if chapters:
                lines.append("")
                lines.append("## 逐章大纲正文")
                for item in chapters:
                    if not isinstance(item, dict):
                        continue
                    lines.extend(
                        [
                            f"### 第{item.get('chapter_no')}章 {item.get('title', '')}",
                            f"- 所属卷：第{item.get('volume_no')}卷；来源窗口：{item.get('source_window') or item.get('window_no') or '未标明'}",
                            f"- 核心事件：{item.get('core_event', '')}",
                            f"- 冲突设计：{item.get('conflict', '')}",
                            f"- 危机选择：{item.get('crisis', '')}",
                            f"- 高潮执行：{item.get('climax', '')}",
                            f"- 结果后果：{item.get('result') or item.get('outcome') or ''}",
                            f"- 状态变化：{item.get('state_change_text') or self._state_change_text(item.get('state_change'))}",
                            f"- 伏笔用途：{item.get('foreshadowing_use_text') or self._foreshadowing_use_text(item.get('foreshadowing_use'))}",
                            f"- 章末钩子：{item.get('hook') or item.get('cliffhanger') or item.get('chapter_hook') or ''}",
                        ]
                    )
        if risks:
            lines.append("")
            lines.append("## 风险与确认边界")
            lines.extend(f"- {item}" for item in risks)
        return {
            "title": title,
            "phase": phase,
            "body": "\n".join(line for line in lines if str(line).strip() or line == ""),
            "source_turn_count": len(turns),
            "source_turn_ids": [str(turn.get("id") or "") for turn in turns if turn.get("id")],
        }

    def _turn_digest(self, turns: list[dict[str, Any]], keys: tuple[str, ...], limit: int = 8) -> list[str]:
        items: list[str] = []
        for turn in turns:
            for key in keys:
                value = turn.get(key)
                if isinstance(value, list):
                    for entry in value:
                        text = self._digest_text(entry)
                        if text and text not in items:
                            items.append(text)
                elif isinstance(value, dict):
                    text = self._digest_text(value)
                    if text and text not in items:
                        items.append(text)
                elif isinstance(value, str):
                    text = self._digest_text(value)
                    if text and text not in items:
                        items.append(text)
                if len(items) >= limit:
                    return items[:limit]
        return items[:limit]

    def _digest_text(self, value: Any) -> str:
        if isinstance(value, dict):
            text = str(value.get("decision") or value.get("title") or value.get("evidence") or value.get("required_fix") or value.get("rationale") or value.get("reason") or "")
        else:
            text = str(value or "")
        text = " ".join(text.split())
        if not text or self._contains_outline_template(text):
            return ""
        return text[:240]

    def _chapter_state_change(self, axis: str, chapter_no: int, window_start: int, window_end: int) -> dict[str, str]:
        if chapter_no == window_start:
            return {
                "type": axis,
                "before": "隐性问题或背景压力",
                "after": "当前必须处理的明面压力",
                "cost": "主角失去回避空间，必须投入资源或关系信用。",
            }
        if chapter_no == window_end:
            return {
                "type": axis,
                "before": "窗口内持续升级的压力",
                "after": "本窗口完成收束，并打开下一窗口无法回避的新代价",
                "cost": "阶段目标推进，但主角承担卷内或窗口级后果。",
            }
        return {
            "type": axis,
            "before": "主角仍有多种可选路径",
            "after": "行动空间收窄，必须牺牲一项资源、关系或认知确定性",
            "cost": "可用选择减少一档，反对力量获得新筹码。",
        }

    def _chapter_foreshadowing_use(self, chapter_no: int, window_start: int, window_end: int) -> dict[str, list[str]]:
        use = {"plant": [], "remind": [], "mislead": [], "payoff": []}
        if chapter_no == window_start:
            use["plant"].append("种下一个可追踪伏笔")
        elif chapter_no == window_end:
            use["payoff"].append("回收或阶段性兑现一个伏笔")
        else:
            action = FORESHADOWING_ACTIONS[(chapter_no - window_start) % len(FORESHADOWING_ACTIONS)]
            descriptions = {
                "plant": "补种一个与窗口目标相关的次级伏笔",
                "remind": "提醒上一窗口或本窗口伏笔",
                "mislead": "制造一次可解释的误导",
                "payoff": "阶段性兑现一个小伏笔",
            }
            use[action].append(descriptions[action])
        if chapter_no not in {window_start, window_end} and not use["remind"]:
            use["remind"].append("用细节提醒读者窗口伏笔仍有效")
        return use

    def _state_change_text(self, state_change: Any) -> str:
        if isinstance(state_change, dict):
            change_type = str(state_change.get("type") or "状态")
            before = str(state_change.get("before") or "旧状态")
            after = str(state_change.get("after") or "新状态")
            cost = str(state_change.get("cost") or "代价待追踪")
            return f"{change_type}从「{before}」转为「{after}」，代价是{cost}"
        return str(state_change or "状态发生可见变化")

    def _foreshadowing_use_text(self, foreshadowing_use: Any) -> str:
        if isinstance(foreshadowing_use, dict):
            parts = []
            for key in ("plant", "remind", "mislead", "payoff"):
                values = foreshadowing_use.get(key) if isinstance(foreshadowing_use.get(key), list) else []
                if values:
                    parts.append(f"{key}:{'；'.join(str(value) for value in values)}")
            return "；".join(parts) or "保持伏笔账本连续"
        return str(foreshadowing_use or "保持伏笔账本连续")

    def _next_chapter_label(self, chapter_no: int, window_end: int) -> str:
        return f"第{chapter_no + 1}章" if chapter_no < window_end else "下一窗口"

    def _distinct_chapter_beats(
        self,
        turns: list[dict[str, Any]],
        chapter_no: int | None = None,
        state_change: str = "",
        window: dict[str, Any] | None = None,
    ) -> tuple[str, str, str]:
        crisis = self._debate_sentence(turns, ("StructureDoctorAgent",), "本章危机待确认。")
        climax = self._debate_sentence(turns, ("StoryDirectorAgent", "StructureDoctorAgent"), "本章高潮待确认。")
        outcome = self._debate_sentence(turns, ("ContinuityAuditorAgent",), "本章结果待确认。")
        if self._contains_outline_template(crisis, chapter_no or 0):
            crisis = ""
        if self._contains_outline_template(climax, chapter_no or 0):
            climax = ""
        if self._contains_outline_template(outcome, chapter_no or 0):
            outcome = ""
        if (
            len({crisis, climax, outcome}) == 3
            and all((crisis, climax, outcome))
        ):
            return crisis, climax, outcome
        axis = str((window or {}).get("window_axis") or "压力")
        target = f"第{chapter_no}章" if chapter_no else "本章"
        state = state_change or f"{axis}发生不可逆变化"
        base = crisis or climax or outcome or state
        return (
            f"危机：{target}围绕「{self._short_label(base)}」形成不可逆选择，若退让则{axis}继续恶化。",
            f"高潮：{target}主角围绕{axis}执行该选择，并让行动产生可见代价。",
            f"结果：{state}，改变局面并留下后续必须回应的问题。",
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

    def _safe_debate_sentence(self, turns: list[dict[str, Any]], agent_suffixes: tuple[str, ...], fallback: str, chapter_no: int = 0) -> str:
        text = self._debate_sentence(turns, agent_suffixes, fallback)
        if self._contains_outline_template(text, chapter_no):
            return fallback
        return text

    def _contains_outline_template(self, value: Any, chapter_no: int = 0) -> bool:
        text = str(value or "")
        if not text.strip():
            return False
        for pattern in OUTLINE_TEMPLATE_BLOCKLIST:
            expected = pattern.replace("{chapter_no}", str(chapter_no)) if chapter_no else pattern.replace("{chapter_no}", "")
            if expected and expected in text:
                return True
        return False

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

    def _ensure_complete_volume_batch(
        self,
        project: models.Project,
        request: OutlineDebateRunRequest,
        turns: list[dict[str, Any]],
        result: dict[str, Any],
    ) -> dict[str, Any]:
        expected_numbers = self._volume_numbers_for_request(request)
        existing = result.get("volume_outlines") if isinstance(result.get("volume_outlines"), list) else []
        existing_by_no = {
            int(item.get("volume_no") or 0): item
            for item in existing
            if isinstance(item, dict) and int(item.get("volume_no") or 0) > 0
        }
        repaired: list[dict[str, Any]] = []
        repaired_numbers: list[int] = []
        for volume_no in expected_numbers:
            fallback = self._volume_candidate_from_debate(volume_no, project, request, turns)
            existing_item = existing_by_no.get(volume_no, {})
            merged = self._merge_nonempty_outline(fallback, existing_item)
            missing_required = any(
                merged.get(key) in (None, "", [], {})
                for key in ("volume_function", "main_conflict", "ending_hook", "character_arc", "setting_reveal_plan", "foreshadowing_plan")
            )
            if missing_required:
                merged = fallback
                repaired_numbers.append(volume_no)
            repaired.append(merged)
        enriched = dict(result)
        enriched["volume_outlines"] = repaired
        if repaired_numbers or len(existing) != len(expected_numbers):
            enriched["repair_policy"] = {
                "applied": True,
                "reason": "model_patch_missing_or_incomplete_volume_outlines",
                "repaired_volume_numbers": repaired_numbers or [number for number in expected_numbers if number not in existing_by_no],
            }
        return enriched

    def _ensure_complete_chapter_batch(
        self,
        project: models.Project,
        request: OutlineDebateRunRequest,
        turns: list[dict[str, Any]],
        result: dict[str, Any],
    ) -> dict[str, Any]:
        metrics = self._outline_quality_metrics("chapters", request, result)
        result = self._ensure_stage_outline_bodies(project, "chapters", request, turns, result)
        if metrics.get("status") == "passed":
            return result
        repaired_windows = self._chapter_windows_from_debate(project, request, turns)
        repaired_chapters = self._chapter_candidates_from_debate(project, request, turns, repaired_windows)
        enriched = dict(result)
        enriched["chapter_windows"] = repaired_windows
        enriched["chapter_outlines"] = repaired_chapters
        enriched["repair_policy"] = {
            "applied": True,
            "reason": "model_patch_failed_strict_chapter_quality_gate",
            "original_quality_status": metrics.get("status"),
            "original_blocking_items": metrics.get("blocking_items", [])[:10],
        }
        return enriched

    def _merge_nonempty_outline(self, fallback: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
        merged = dict(fallback)
        for key, value in incoming.items():
            if value in (None, "", [], {}):
                continue
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = self._deep_merge_dicts(merged[key], value)
            else:
                merged[key] = value
        return merged

    def _expected_chapter_window_count(self, request: OutlineDebateRunRequest) -> int:
        window_size = max(1, self._chapter_window_size(request))
        count = 0
        for chapter_range in self._chapter_ranges_for_request(request):
            length = max(1, int(chapter_range["end_chapter_no"]) - int(chapter_range["start_chapter_no"]) + 1)
            count += (length + window_size - 1) // window_size
        return max(1, count)

    def _attach_outline_quality_metrics(self, phase: str, request: OutlineDebateRunRequest, result: dict[str, Any]) -> dict[str, Any]:
        enriched = dict(result)
        metrics = self._book_quality_metrics(enriched) if phase == "book" else self._outline_quality_metrics(phase, request, enriched)
        enriched["quality_metrics"] = metrics
        enriched["blocking_items"] = metrics.get("blocking_items", [])
        return enriched

    def _book_quality_metrics(self, result: dict[str, Any]) -> dict[str, Any]:
        book_outline = result.get("book_outline") if isinstance(result.get("book_outline"), dict) else {}
        required_fields = ("core_promise", "main_conflict", "ending_direction", "reader_experience")
        missing_fields = [field for field in required_fields if book_outline.get(field) in (None, "", [], {})]
        blocking_items = [
            self._quality_block("book_required_field_missing", f"总纲关键字段缺失：{', '.join(missing_fields)}")
        ] if missing_fields else []
        return {
            "phase": "book",
            "status": "failed" if blocking_items else "passed",
            "required_field_coverage": round((len(required_fields) - len(missing_fields)) / len(required_fields), 4),
            "missing_fields": missing_fields,
            "blocking_items": blocking_items,
        }

    def _outline_quality_metrics(self, phase: str, request: OutlineDebateRunRequest, result: dict[str, Any]) -> dict[str, Any]:
        blocking_items: list[dict[str, Any]] = []
        metrics: dict[str, Any] = {"phase": phase}
        if phase == "volumes":
            expected_numbers = self._volume_numbers_for_request(request)
            volumes = result.get("volume_outlines") if isinstance(result.get("volume_outlines"), list) else []
            actual_numbers = [int(item.get("volume_no") or 0) for item in volumes if isinstance(item, dict)]
            missing_numbers = [number for number in expected_numbers if number not in actual_numbers]
            metrics.update(
                {
                    "expected_volume_count": len(expected_numbers),
                    "actual_volume_count": len(volumes),
                    "volume_count_match": len(volumes) == len(expected_numbers) and not missing_numbers,
                    "missing_volume_numbers": missing_numbers,
                    "rhythm_model_coverage": self._coverage(volumes, lambda item: isinstance(item.get("rhythm_model"), dict) and bool(item["rhythm_model"].get("model_name"))),
                    "volume_required_field_coverage": self._coverage(
                        volumes,
                        lambda item: all(item.get(key) not in (None, "", [], {}) for key in ("volume_function", "main_conflict", "ending_hook", "character_arc", "setting_reveal_plan", "foreshadowing_plan")),
                    ),
                }
            )
            if missing_numbers or len(volumes) != len(expected_numbers):
                blocking_items.append(self._quality_block("count_mismatch", f"卷纲数量不匹配：期望 {len(expected_numbers)}，实际 {len(volumes)}，缺失 {missing_numbers}"))
            if metrics["volume_required_field_coverage"] < 1.0:
                blocking_items.append(self._quality_block("volume_required_field_missing", f"卷纲关键字段覆盖不足：{metrics['volume_required_field_coverage']}"))
        if phase == "chapters":
            expected_chapters = self._chapter_candidates_for_request(request)
            expected_numbers = [chapter_no for _volume_no, chapter_no in expected_chapters]
            expected_volume_end_numbers = sorted({int(chapter_range["end_chapter_no"]) for chapter_range in self._chapter_ranges_for_request(request)})
            expected_final_chapter_no = expected_volume_end_numbers[-1] if expected_volume_end_numbers else 0
            chapters = result.get("chapter_outlines") if isinstance(result.get("chapter_outlines"), list) else []
            windows = result.get("chapter_windows") if isinstance(result.get("chapter_windows"), list) else []
            actual_numbers = [int(item.get("chapter_no") or 0) for item in chapters if isinstance(item, dict)]
            missing_numbers = [number for number in expected_numbers if number not in actual_numbers]
            template_hits = self._template_hits(chapters)
            title_duplicates = self._duplicate_count([str(item.get("title") or "").strip() for item in chapters if isinstance(item, dict)])
            ccr_distinct_count = sum(
                1
                for item in chapters
                if isinstance(item, dict)
                and len({str(item.get("crisis") or "").strip(), str(item.get("climax") or "").strip(), str(item.get("result") or "").strip()}) == 3
            )
            metrics.update(
                {
                    "expected_chapter_count": len(expected_numbers),
                    "actual_chapter_count": len(chapters),
                    "chapter_count_match": len(chapters) == len(expected_numbers) and not missing_numbers,
                    "missing_chapter_numbers": missing_numbers[:30],
                    "expected_chapter_window_count": self._expected_chapter_window_count(request),
                    "actual_chapter_window_count": len(windows),
                    "chapter_window_count_match": len(windows) == self._expected_chapter_window_count(request),
                    "window_required_field_coverage": self._coverage(windows, self._window_has_required_fields),
                    "window_mini_climax_coverage": self._coverage(windows, lambda item: bool(item.get("mini_climax"))),
                    "foreshadowing_window_coverage": self._coverage(windows, self._window_has_two_foreshadowing_categories),
                    "template_blocking_count": len(template_hits),
                    "template_hits": template_hits[:20],
                    "state_change_coverage": self._coverage(chapters, self._chapter_has_state_change),
                    "foreshadowing_use_coverage": self._coverage(chapters, self._chapter_has_foreshadowing_use),
                    "source_window_coverage": self._coverage(chapters, self._chapter_has_source_window),
                    "crisis_climax_result_distinct_rate": round(ccr_distinct_count / max(1, len(chapters)), 4),
                    "duplicate_title_count": title_duplicates,
                    "expected_volume_end_chapters": expected_volume_end_numbers,
                    "volume_end_function_coverage": self._coverage(
                        [item for item in chapters if isinstance(item, dict) and int(item.get("chapter_no") or 0) in expected_volume_end_numbers],
                        lambda item: item.get("milestone_function") in {"volume_climax", "book_or_phase_turn"},
                    ),
                    "final_chapter_turn_present": any(
                        isinstance(item, dict)
                        and int(item.get("chapter_no") or 0) == expected_final_chapter_no
                        and item.get("milestone_function") == "book_or_phase_turn"
                        for item in chapters
                    ),
                }
            )
            if missing_numbers or len(chapters) != len(expected_numbers):
                blocking_items.append(self._quality_block("count_mismatch", f"章纲数量不匹配：期望 {len(expected_numbers)}，实际 {len(chapters)}，缺失前30项 {missing_numbers[:30]}"))
            if len(windows) != self._expected_chapter_window_count(request):
                blocking_items.append(self._quality_block("window_mismatch", f"章节窗口数量不匹配：期望 {self._expected_chapter_window_count(request)}，实际 {len(windows)}"))
            if metrics["window_required_field_coverage"] < 1.0:
                blocking_items.append(self._quality_block("window_required_field_missing", f"章节窗口关键字段覆盖不足：{metrics['window_required_field_coverage']}"))
            if metrics["window_mini_climax_coverage"] < 1.0:
                blocking_items.append(self._quality_block("window_mini_climax_missing", f"mini_climax 覆盖率不足：{metrics['window_mini_climax_coverage']}"))
            if metrics["foreshadowing_window_coverage"] < 0.8:
                blocking_items.append(self._quality_block("foreshadowing_window_missing", f"伏笔窗口覆盖率不足：{metrics['foreshadowing_window_coverage']}"))
            if template_hits:
                blocking_items.append(self._quality_block("template_placeholder", f"章纲存在模板占位或待确认句：{len(template_hits)} 处"))
            if metrics["state_change_coverage"] < 0.95:
                blocking_items.append(self._quality_block("state_change_missing", f"state_change 覆盖率不足：{metrics['state_change_coverage']}"))
            if metrics["foreshadowing_use_coverage"] < 0.9:
                blocking_items.append(self._quality_block("foreshadowing_use_missing", f"foreshadowing_use 覆盖率不足：{metrics['foreshadowing_use_coverage']}"))
            if metrics["crisis_climax_result_distinct_rate"] < 0.95:
                blocking_items.append(self._quality_block("crisis_climax_result_duplicate", f"危机/高潮/结果分离率不足：{metrics['crisis_climax_result_distinct_rate']}"))
            if metrics["volume_end_function_coverage"] < 1.0:
                blocking_items.append(self._quality_block("volume_end_function_missing", f"卷末章节功能覆盖不足：{metrics['volume_end_function_coverage']}"))
            if not metrics["final_chapter_turn_present"]:
                blocking_items.append(self._quality_block("final_chapter_turn_missing", f"最终章节 {expected_final_chapter_no} 缺少阶段收束或下一阶段钩子功能。"))
        metrics["blocking_items"] = blocking_items
        metrics["status"] = "failed" if blocking_items else "passed"
        return metrics

    def _quality_block(self, issue_type: str, evidence: str) -> dict[str, str]:
        return {"severity": "blocking", "type": issue_type, "evidence": evidence, "required_fix": "重新生成或修订候选，直到满足严格验收指标。"}

    def _coverage(self, items: list[Any], predicate: Any) -> float:
        if not items:
            return 0.0
        passed = sum(1 for item in items if isinstance(item, dict) and predicate(item))
        return round(passed / len(items), 4)

    def _window_has_required_fields(self, item: dict[str, Any]) -> bool:
        required = (
            "stage_goal",
            "reader_promise",
            "main_pressure",
            "state_change_goal",
            "new_information",
            "relationship_change",
            "resource_change",
            "rule_or_setting_reveal",
            "mini_crisis",
            "mini_climax",
            "transition_hook",
            "risk",
        )
        return all(item.get(key) not in (None, "", [], {}) for key in required)

    def _window_has_two_foreshadowing_categories(self, item: dict[str, Any]) -> bool:
        count = 0
        for key in ("foreshadowing_to_plant", "foreshadowing_to_remind", "foreshadowing_to_mislead", "foreshadowing_to_payoff"):
            value = item.get(key)
            if isinstance(value, list) and value:
                count += 1
        return count >= 2

    def _chapter_has_state_change(self, item: dict[str, Any]) -> bool:
        value = item.get("state_change")
        return isinstance(value, dict) and all(value.get(key) for key in ("type", "before", "after", "cost"))

    def _chapter_has_foreshadowing_use(self, item: dict[str, Any]) -> bool:
        value = item.get("foreshadowing_use")
        if not isinstance(value, dict):
            return False
        return any(isinstance(value.get(key), list) and value.get(key) for key in ("plant", "remind", "mislead", "payoff"))

    def _chapter_has_source_window(self, item: dict[str, Any]) -> bool:
        if isinstance(item.get("source_window"), str) and item.get("source_window").strip():
            return True
        detail = item.get("source_window_detail")
        return isinstance(detail, dict) and bool(detail.get("window_no"))

    def _duplicate_count(self, values: list[str]) -> int:
        seen: set[str] = set()
        duplicates = 0
        for value in values:
            if not value:
                continue
            if value in seen:
                duplicates += 1
            seen.add(value)
        return duplicates

    def _template_hits(self, chapters: list[Any]) -> list[dict[str, Any]]:
        hits: list[dict[str, Any]] = []
        for item in chapters:
            if not isinstance(item, dict):
                continue
            chapter_no = int(item.get("chapter_no") or 0)
            text = " ".join(str(item.get(key) or "") for key in ("title", "outline", "core_event", "conflict", "crisis", "climax", "result", "cliffhanger"))
            if self._contains_outline_template(text, chapter_no):
                matched = next((pattern.replace("{chapter_no}", str(chapter_no)) for pattern in OUTLINE_TEMPLATE_BLOCKLIST if pattern.replace("{chapter_no}", str(chapter_no)) in text), "template")
                hits.append({"chapter_no": chapter_no, "pattern": matched})
        return hits

    def _deep_merge_dicts(self, base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
        merged = dict(base)
        for key, value in patch.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = self._deep_merge_dicts(merged[key], value)
            else:
                merged[key] = value
        return merged

    def _patch_value_for_key(self, patch: dict[str, Any], key: str) -> Any:
        aliases = {
            "book_outline": ("book_outline", "book_outline_candidate", "outline", "macro_outline", "全书总纲", "总纲候选"),
            "volume_outlines": ("volume_outlines", "volume_outline_candidates", "volumes", "volume_candidates", "逐卷大纲", "卷纲候选", "卷纲列表"),
            "chapter_windows": ("chapter_windows", "chapter_outline_windows", "windows", "章纲窗口", "章节窗口"),
            "chapter_outlines": ("chapter_outlines", "chapter_outline_candidates", "chapters", "chapter_candidates", "章纲候选", "章纲列表"),
        }.get(key, (key,))
        for alias in aliases:
            value = patch.get(alias)
            if value not in (None, "", [], {}):
                return value
        return None

    def _coerce_outline_items(self, phase: str, value: Any) -> list[dict[str, Any]]:
        if value in (None, "", [], {}):
            return []
        aliases = ("volume_outlines", "volume_outline_candidates", "volumes", "逐卷大纲", "卷纲候选") if phase == "volumes" else (
            "chapter_outlines",
            "chapter_outline_candidates",
            "chapters",
            "章纲候选",
        )
        if isinstance(value, list):
            items: list[dict[str, Any]] = []
            for item in value:
                items.extend(self._coerce_outline_items(phase, item))
            return items
        if not isinstance(value, dict):
            return []
        for alias in aliases:
            nested = value.get(alias)
            if nested not in (None, "", [], {}):
                return self._coerce_outline_items(phase, nested)
        phase_items: list[dict[str, Any]] = []
        for key, item in value.items():
            if not isinstance(item, dict):
                continue
            match = re.fullmatch(r"(?:phase|volume|chapter)[_\-\s]*(\d+)", str(key), flags=re.IGNORECASE)
            if not match:
                continue
            number = int(match.group(1))
            id_field = self._item_no_field(phase)
            phase_items.append({id_field: int(item.get(id_field) or number), **item})
        if phase_items:
            return phase_items
        return [dict(value)]

    def _merge_outline_item_lists(self, phase: str, existing: Any, incoming: Any) -> list[dict[str, Any]]:
        id_field = self._item_no_field(phase)
        merged_by_number: dict[int, dict[str, Any]] = {}
        for source in (self._coerce_outline_items(phase, existing), self._coerce_outline_items(phase, incoming)):
            for item in source:
                number = int(item.get(id_field) or len(merged_by_number) + 1)
                merged_by_number[number] = {**merged_by_number.get(number, {}), **item, id_field: number}
        return [merged_by_number[number] for number in sorted(merged_by_number)]

    def _value_from_aliases(self, item: dict[str, Any], *aliases: str, fallback: Any = "") -> Any:
        for alias in aliases:
            value = item.get(alias)
            if value not in (None, "", [], {}):
                return value
        return fallback

    def _flatten_stage_candidate(self, item: dict[str, Any], phase: str) -> dict[str, Any]:
        flattened = dict(item)
        for key, value in item.items():
            if not isinstance(value, dict):
                continue
            if re.fullmatch(r"(?:phase|volume|chapter)[_\-\s]*\d+", str(key), flags=re.IGNORECASE):
                flattened = {**value, **flattened}
                if phase == "volumes" and not flattened.get("volume_no"):
                    match = re.search(r"(\d+)", str(key))
                    if match:
                        flattened["volume_no"] = int(match.group(1))
                if phase == "chapters" and not flattened.get("chapter_no"):
                    match = re.search(r"(\d+)", str(key))
                    if match:
                        flattened["chapter_no"] = int(match.group(1))
        return flattened

    def _normalize_volume_candidate_for_commit(self, project: models.Project | None, item: dict[str, Any], preferred_title: str = "") -> dict[str, Any]:
        source = self._flatten_stage_candidate(item, "volumes")
        volume_no = self._bounded_int(source.get("volume_no") or source.get("volume") or source.get("卷序"), 1, 1, 999)
        chapters_per_volume = self._bounded_int(
            source.get("chapters_per_volume") or (project.chapters_per_volume if project is not None else None),
            project.chapters_per_volume if project is not None and project.chapters_per_volume else 40,
            1,
            300,
        )
        chapter_range = str(
            self._value_from_aliases(
                source,
                "chapter_range",
                "chapters",
                "chapter_ranges",
                "章节区间",
                fallback=f"{(volume_no - 1) * chapters_per_volume + 1}-{volume_no * chapters_per_volume}",
            )
        )
        stage_goal = self._value_from_aliases(source, "stage_goal", "phase_goal", "core_goal", "本卷目标", "阶段目标")
        main_conflict = self._value_from_aliases(source, "main_conflict", "conflict", "main_track", "主线冲突", "主线")
        boundary = self._value_from_aliases(source, "boundary", "volume_hook", "final_hook", "cliffhanger", "阶段边界", "卷末钩子")
        cost = self._value_from_aliases(source, "cost", "price", "代价")
        raw_title = str(self._value_from_aliases(source, "title", fallback="")).strip()
        explicit_title = str(self._value_from_aliases(source, "标题", "卷名", "name", fallback="")).strip()
        upstream_title = str(preferred_title or "").strip()
        if explicit_title and (not raw_title or self._looks_like_generated_volume_title(raw_title, volume_no)):
            title = explicit_title
        elif upstream_title and self._looks_like_generated_volume_title(raw_title, volume_no):
            title = upstream_title
        else:
            title = str(self._value_from_aliases(source, "title", "标题", "name", "卷名", fallback=f"第{volume_no}卷")).strip() or f"第{volume_no}卷"
        rhythm = source.get("rhythm_model") if isinstance(source.get("rhythm_model"), dict) else {}
        normalized = {
            **source,
            "volume_no": volume_no,
            "title": title if title.startswith(f"第{volume_no}卷") else title,
            "chapter_range": chapter_range,
            "volume_function": str(self._value_from_aliases(source, "volume_function", "function", "本卷功能", fallback=stage_goal or main_conflict or "推动主线升级并改变主角处境。")),
            "rhythm_model": {
                "model_name": str(self._value_from_aliases(rhythm, "model_name", "name", "模型", fallback="动态长篇升级")),
                "why_this_model": str(self._value_from_aliases(rhythm, "why_this_model", "reason", "选择理由", fallback="根据题材、目标读者和本卷功能动态选择，不强制套用固定模板。")),
                "phase_count": self._bounded_int(rhythm.get("phase_count") or rhythm.get("阶段数"), 4, 1, 12),
                "chapter_distribution": str(self._value_from_aliases(rhythm, "chapter_distribution", "distribution", "分布", fallback=chapter_range)),
            },
            "core_goal": str(stage_goal or self._value_from_aliases(source, "goal", "目标", fallback="完成本卷阶段目标。")),
            "main_track": str(main_conflict or self._value_from_aliases(source, "main_track", fallback="主线目标推进。")),
            "hidden_track": str(self._value_from_aliases(source, "hidden_track", "暗线", fallback="暗线推进一格。")),
            "character_track": str(self._value_from_aliases(source, "character_track", "人物线", fallback="人物关系或认知发生变化。")),
            "world_reveal": str(self._value_from_aliases(source, "world_reveal", "世界揭示", fallback="揭开世界规则的一层新解释。")),
            "opposition_pressure": str(self._value_from_aliases(source, "opposition_pressure", "enemy_pressure", "阻力压力", fallback=main_conflict or "阶段反对力量升级。")),
            "volume_hook": str(boundary or self._value_from_aliases(source, "hook", fallback="卷末留下通向下一卷的新问题。")),
        }
        risks = source.get("risks") if isinstance(source.get("risks"), list) else []
        if cost:
            risks = [*risks, f"代价：{cost}"]
        normalized["risks"] = risks or ["节奏重复", "暗线推进不足"]
        return normalized

    def _preferred_volume_title_from_book_plan(self, session: dict[str, Any], volume_no: int) -> str:
        confirmed = session.get("confirmed_candidates") if isinstance(session.get("confirmed_candidates"), dict) else {}
        book = confirmed.get("book") if isinstance(confirmed, dict) else {}
        book_outline = book.get("book_outline") if isinstance(book, dict) and isinstance(book.get("book_outline"), dict) else {}
        volume_plan = book_outline.get("volume_plan") if isinstance(book_outline.get("volume_plan"), list) else []
        for candidate in volume_plan:
            if not isinstance(candidate, dict):
                continue
            number = self._bounded_int(candidate.get("volume_no") or candidate.get("volume") or candidate.get("卷序"), 0, 0, 999)
            if number != volume_no:
                continue
            title = str(self._value_from_aliases(candidate, "title", "标题", "卷名", "name", fallback="")).strip()
            if title:
                return title
        return ""

    def _looks_like_generated_volume_title(self, title: str, volume_no: int) -> bool:
        value = str(title or "").strip()
        if not value:
            return True
        generated_markers = ("适合采用", "节奏模型", "每5章", "候选结构", "读者期待", "结构可行", "阶段压力")
        if any(marker in value for marker in generated_markers):
            return True
        prefix = f"第{volume_no}卷"
        return value.startswith(prefix) and "：" in value and len(value) > 18

    def _parse_chinese_number(self, value: str) -> int | None:
        numerals = {char: index for index, char in enumerate(_CHINESE_NUMERALS)}
        text = str(value or "").strip()
        if not text:
            return None
        if text in numerals:
            return numerals[text]
        if text == "十":
            return 10
        if "十" in text:
            left, _, right = text.partition("十")
            tens = numerals.get(left, 1) if left else 1
            ones = numerals.get(right, 0) if right else 0
            return tens * 10 + ones
        return None

    def _chapter_references_in_text(self, value: str) -> list[int]:
        text = str(value or "")
        refs = [int(match.group(1)) for match in re.finditer(r"第\s*(\d+)\s*章", text)]
        for match in re.finditer(r"第\s*([零一二三四五六七八九十百千万两]+)\s*章", text):
            parsed = self._parse_chinese_number(match.group(1).replace("两", "二"))
            if parsed is not None:
                refs.append(parsed)
        return refs

    def _looks_like_multi_chapter_scope_text(self, value: Any, target_chapter_no: int) -> bool:
        text = str(value or "")
        if not text.strip():
            return False
        compact = "".join(text.split())
        if any(marker in compact for marker in ("前三章", "前3章", "前二章", "前两章", "多章候选", "多章批次")):
            return True
        refs = self._chapter_references_in_text(text)
        return any(ref != target_chapter_no for ref in refs)

    def _single_chapter_text_or_fallback(self, value: Any, target_chapter_no: int, fallback: str) -> str:
        text = str(value or "").strip()
        if text and not self._looks_like_multi_chapter_scope_text(text, target_chapter_no):
            return text
        fallback_text = str(fallback or "").strip()
        if fallback_text and not self._looks_like_multi_chapter_scope_text(fallback_text, target_chapter_no):
            return fallback_text
        return f"第{target_chapter_no}章围绕本章核心事件推进一次行动、阻碍、不可逆选择和后果。"

    def _chapter_title_or_fallback(self, value: Any, target_chapter_no: int, seed_text: str) -> str:
        title = str(value or "").strip()
        title = re.sub(rf"^第\s*{target_chapter_no}\s*章\s*[：:、\\-—]*\s*", "", title).strip()
        bad_markers = ("危机严格成立", "必须在", "高潮", "结果", "candidate", "outline", "chapter_")
        if (
            not title
            or len(title) > 18
            or any(marker in title for marker in bad_markers)
            or self._looks_like_multi_chapter_scope_text(title, target_chapter_no)
        ):
            title = self._short_label(seed_text)
        if not title or self._looks_like_multi_chapter_scope_text(title, target_chapter_no):
            title = "选择的代价"
        for separator in ("，", "、", "；", ";", "。", ".", ","):
            if separator in title:
                title = title.split(separator, 1)[0].strip()
                break
        return title[:18]

    def _normalize_chapter_candidate_for_commit(self, project: models.Project | None, item: dict[str, Any]) -> dict[str, Any]:
        source = self._flatten_stage_candidate(item, "chapters")
        chapter_no = self._bounded_int(source.get("chapter_no") or source.get("chapter") or source.get("章序"), 1, 1, 99999)
        volume_no = self._bounded_int(source.get("volume_no") or source.get("volume") or source.get("卷序"), 1, 1, 999)
        chapter_word_target = project.chapter_word_target if project is not None and project.chapter_word_target else DEFAULT_CHAPTER_WORD_TARGET
        core_event_fallback = f"第{chapter_no}章围绕本章核心事件推进一次行动、阻碍和后果。"
        core_event = self._single_chapter_text_or_fallback(
            self._value_from_aliases(source, "core_event", "event", "核心事件", fallback=""),
            chapter_no,
            core_event_fallback,
        )
        outline = self._single_chapter_text_or_fallback(
            self._value_from_aliases(source, "outline", "summary", "chapter_outline", "章纲", fallback=""),
            chapter_no,
            core_event,
        )
        conflict = self._single_chapter_text_or_fallback(
            self._value_from_aliases(source, "conflict", "main_conflict", "章内冲突", fallback=""),
            chapter_no,
            "本章冲突围绕主角行动与既有秩序压力展开。",
        )
        crisis = self._single_chapter_text_or_fallback(
            self._value_from_aliases(source, "crisis", "危机", fallback=""),
            chapter_no,
            "本章危机是主角必须作出不可逆选择。",
        )
        climax = self._single_chapter_text_or_fallback(
            self._value_from_aliases(source, "climax", "高潮", fallback=""),
            chapter_no,
            "本章高潮是主角执行选择并付出可见代价。",
        )
        outcome = self._single_chapter_text_or_fallback(
            self._value_from_aliases(source, "outcome", "result", "结果", fallback=""),
            chapter_no,
            "本章结果改变局面，并留下下一章必须回应的问题。",
        )
        cliffhanger = self._single_chapter_text_or_fallback(
            self._value_from_aliases(source, "chapter_hook", "hook", "cliffhanger", "章末钩子", fallback=""),
            chapter_no,
            "章末出现通向下一章的新压力或新证据。",
        )
        title = self._chapter_title_or_fallback(self._value_from_aliases(source, "title", "name", "章名", fallback=""), chapter_no, core_event)
        return {
            **source,
            "chapter_no": chapter_no,
            "volume_no": volume_no,
            "title": title,
            "outline": outline,
            "pov_character": str(self._value_from_aliases(source, "pov_character", "pov", "POV", fallback="主角")),
            "core_event": core_event,
            "conflict": conflict,
            "crisis": crisis,
            "climax": climax,
            "outcome": outcome,
            "result": outcome,
            "chapter_hook": cliffhanger,
            "cliffhanger": cliffhanger,
            "word_target": self._bounded_int(source.get("word_target") or source.get("chapter_word_target"), chapter_word_target, 500, 20000),
        }

    def _restrict_itemized_result(self, phase: str, request: OutlineDebateRunRequest, result: dict[str, Any]) -> dict[str, Any]:
        if not self._is_itemized_phase(phase):
            return result
        list_key = self._item_list_key(phase)
        id_field = self._item_no_field(phase)
        target_number = self._target_volume_no(request) if phase == "volumes" else self._target_chapter_no(request)
        allowed_numbers = {target_number}
        if phase == "volumes" and not request.target_volume_no:
            allowed_numbers = set(self._volume_numbers_for_request(request))
        if phase == "chapters" and not request.target_chapter_no:
            allowed_numbers = {chapter_no for _volume_no, chapter_no in self._chapter_candidates_for_request(request)}
        values = self._coerce_outline_items(phase, result.get(list_key))
        filtered = [
            dict(item)
            for item in values
            if isinstance(item, dict) and int(item.get(id_field) or target_number) in allowed_numbers
        ]
        if not filtered and values:
            first = next((dict(item) for item in values if isinstance(item, dict)), {})
            if first:
                filtered = [first]
        normalized_items: list[dict[str, Any]] = []
        for index, item in enumerate(filtered):
            item_number = int(item.get(id_field) or (target_number if len(allowed_numbers) == 1 else sorted(allowed_numbers)[min(index, len(allowed_numbers) - 1)]))
            item[id_field] = item_number
            if phase == "volumes":
                item = self._normalize_volume_candidate_for_commit(None, item)
            else:
                item = self._normalize_chapter_candidate_for_commit(None, item)
            item["candidate_status"] = "pending_confirmation"
            item["requires_user_confirmation"] = True
            normalized_items.append(item)
        filtered = sorted(normalized_items, key=lambda item: int(item.get(id_field) or 0))
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
        fallback_name = self._fallback_character_candidate_name(project, phase)
        importance_score = 78 if phase == "book" else 58
        identity = f"{fallback_name}是{PHASE_CONFIG[phase]['label']}中把制度压力落到主角身上的关键角色。"
        story_function = "把抽象秩序变成可对抗、可谈判、可误判的人。"
        relationship_hooks = ["与主角存在资源、身份或秘密冲突", "可连接未来伏笔回收与关系反转"]
        long_term_goal = "维持自身代表的秩序或完成与主角目标相冲突的私人目标。"
        immediate_goal = "在首次登场阶段迫使主角付出一次可见代价。"
        inner_wound = "相信秩序必须优先于个体选择，因此容易把人当成规则零件。"
        ability = "能调动制度资源、人情债或信息差制造压迫。"
        ability_cost = "每次强行推进秩序都会暴露其派系利益和私人软肋。"
        fallback = {
            "name": fallback_name,
            "aliases": [],
            "role": "supporting",
            "role_type": "supporting",
            "importance_level": "major" if phase == "book" else "medium",
            "importance_score": importance_score,
            "title": identity,
            "one_sentence_pitch": f"{fallback_name}让主角第一次意识到，对手不是单个人，而是一套会反击的规则。",
            "identity": identity,
            "opening_situation": f"首次在{PHASE_CONFIG[phase]['label']}中作为压力执行者或关系阻断者出现。",
            "world_rule_connection": "其身份、权限或秘密必须绑定当前世界规则，不能只作为普通阻碍。",
            "long_term_desire": long_term_goal,
            "long_term_goal": long_term_goal,
            "immediate_goal": immediate_goal,
            "inner_wound": inner_wound,
            "ability": ability,
            "ability_cost": ability_cost,
            "weakness": "过度依赖规则授权，面对主角的非典型选择时容易误判。",
            "secret": "与当前阶段的旧案、利益链或规则漏洞存在未公开关联。",
            "growth_arc": "从规则执行者或关系压力源，逐步暴露其真实立场、代价与可被反转的弱点。",
            "character_arc": "从规则执行者或关系压力源，逐步暴露其真实立场、代价与可被反转的弱点。",
            "summary": f"{fallback_name}用于承载阶段压力、制度执行和主角关系代价。",
            "appearance": "外在设计需能体现其权力来源、职业痕迹或与主角阶层的反差。",
            "personality": f"{inner_wound}；说话与行动习惯应体现其执行压力的方式。",
            "profile": f"{identity} {story_function}",
            "goals": [long_term_goal, immediate_goal],
            "motivations": ["维护自身秩序位置", "压制主角造成的规则裂缝"],
            "secrets": ["与当前阶段核心规则或旧案存在未公开关联"],
            "abilities": [ability, ability_cost],
            "weaknesses": ["过度依赖规则授权", "容易低估主角的非典型选择"],
            "reader_satisfaction": "读者期待看到主角用选择、证据或关系反击这名角色背后的规则。",
            "long_form_potential": "可随卷推进从执行压力、私人秘密、派系利益到关系反转逐层展开。",
            "writing_risk": "避免只当工具人登场，必须让其私人目标和世界规则同时成立。",
            "risk": "避免只当工具人登场，必须让其私人目标和世界规则同时成立。",
            "revision_hint": "若角色显得扁平，优先补强私人欲望、能力代价和与主角的互相误判。",
            "tags": ["大纲议事", PHASE_CONFIG[phase]["label"], "压力角色"],
            "first_needed_in": {"stage": phase, "reason": request.requirement or "大纲议事发现角色承载缺口"},
            "relationship_hooks": relationship_hooks,
            "relationship_hook": relationship_hooks[0],
            "conflict_seed": f"{fallback_name}越试图完成“{immediate_goal}”，越会把主角推向更高代价的选择。",
            "related_entity_ids": [],
            "related_character_ids": [],
            "relations": relationship_hooks,
            "current_status": "active",
            "updated_reason": "outline_debate_candidate",
            "duplicate_check": {"strategy": "提交正典前按同名、同职能、同阵营扫描重复项", "status": "pending"},
            "activity_status": "candidate",
            "status": "candidate",
            "source": "outline_debate",
            "candidate_source": "service_fallback",
            "candidate_source_reason": "服务层根据讨论缺口生成的占位候选，缺少模型结构化候选证据。",
            "can_materialize_on_confirm": False,
            "canon_write_suggestion": {
                "requires_user_approval": True,
                "target": "characters",
                "write_policy": "review_required_before_materialization",
            },
        }
        generated = self._candidate_from_turn(turns, "CharacterGeneratorAgent", "character_candidate")
        candidate = self._deep_merge_dicts(fallback, generated) if generated else fallback
        candidate["name"] = self._string_or(candidate.get("name"), fallback["name"])
        candidate["activity_status"] = "candidate"
        candidate["status"] = "candidate"
        candidate["source"] = "outline_debate"
        if generated:
            self._annotate_candidate_source(candidate, "model_candidate", True, "角色生成席位提供了结构化候选。")
        else:
            self._annotate_candidate_source(candidate, "service_fallback", False, "服务层根据讨论缺口生成的占位候选，缺少模型结构化候选证据。")
        suggestion = candidate.get("canon_write_suggestion") if isinstance(candidate.get("canon_write_suggestion"), dict) else {}
        suggestion.update(
            {
                "requires_user_approval": not bool(candidate.get("can_materialize_on_confirm")),
                "target": "characters",
                "write_policy": "direct_on_outline_confirmation" if candidate.get("can_materialize_on_confirm") else "review_required_before_materialization",
            }
        )
        candidate["canon_write_suggestion"] = suggestion
        return candidate

    def _setting_candidate(self, project: models.Project, phase: str, request: OutlineDebateRunRequest, turns: list[dict[str, Any]]) -> dict[str, Any]:
        fallback_title = self._fallback_setting_candidate_title(project, phase)
        importance_score = 76 if phase == "book" else 56
        content = f"{fallback_title}用于解释阶段压迫来源、资源分配和主角破局代价。"
        fallback = {
            "title": fallback_title,
            "name": fallback_title,
            "ref_type": "world_fact",
            "category": "politics" if "权谋" in project.genre else "magic_rule",
            "entity_type": "",
            "content": content,
            "description": content,
            "importance_level": "major" if phase == "book" else "medium",
            "importance_score": importance_score,
            "confidence": 0.82,
            "current_status": "active",
            "related_entity_ids": [],
            "first_needed_in": {"stage": phase, "reason": request.requirement or "大纲议事发现设定驱动缺口"},
            "conflict_utility": "让主角目标和既有秩序产生明确碰撞。",
            "foreshadowing_utility": "可在前期以制度细节、禁忌或异常判罚预埋。",
            "limitation": "规则必须有边界和可被主角利用或误读的缝隙。",
            "cost": "触碰该设定会带来身份、资源、关系或时间线代价。",
            "continuity_check": {"uncertainties": ["是否与既有故事圣经冲突"], "status": "pending_user_review"},
            "activity_status": "candidate",
            "status": "candidate",
            "source": "outline_debate",
            "candidate_source": "service_fallback",
            "candidate_source_reason": "服务层根据讨论缺口生成的占位候选，缺少模型结构化候选证据。",
            "can_materialize_on_confirm": False,
            "canon_write_suggestion": {
                "requires_user_approval": True,
                "target": "world_facts",
                "write_policy": "review_required_before_materialization",
            },
        }
        generated = self._candidate_from_turn(turns, "SettingGeneratorAgent", "setting_candidate")
        candidate = self._deep_merge_dicts(fallback, generated) if generated else fallback
        candidate["title"] = self._string_or(candidate.get("title"), fallback["title"])
        candidate["activity_status"] = "candidate"
        candidate["status"] = "candidate"
        candidate["source"] = "outline_debate"
        if generated:
            self._annotate_candidate_source(candidate, "model_candidate", True, "设定生成席位提供了结构化候选。")
        else:
            self._annotate_candidate_source(candidate, "service_fallback", False, "服务层根据讨论缺口生成的占位候选，缺少模型结构化候选证据。")
        suggestion = candidate.get("canon_write_suggestion") if isinstance(candidate.get("canon_write_suggestion"), dict) else {}
        suggestion.update(
            {
                "requires_user_approval": not bool(candidate.get("can_materialize_on_confirm")),
                "target": suggestion.get("target") or candidate.get("ref_type") or "world_facts",
                "write_policy": "direct_on_outline_confirmation" if candidate.get("can_materialize_on_confirm") else "review_required_before_materialization",
            }
        )
        candidate["canon_write_suggestion"] = suggestion
        return candidate

    def _annotate_candidate_source(self, candidate: dict[str, Any], candidate_source: str, can_materialize_on_confirm: bool, reason: str) -> dict[str, Any]:
        candidate["candidate_source"] = candidate_source
        candidate["can_materialize_on_confirm"] = can_materialize_on_confirm
        candidate["candidate_source_reason"] = reason
        suggestion = candidate.get("canon_write_suggestion") if isinstance(candidate.get("canon_write_suggestion"), dict) else {}
        suggestion["requires_user_approval"] = not can_materialize_on_confirm
        suggestion["write_policy"] = "direct_on_outline_confirmation" if can_materialize_on_confirm else "review_required_before_materialization"
        candidate["canon_write_suggestion"] = suggestion
        return candidate

    def _candidate_from_turn(self, turns: list[dict[str, Any]], agent_suffix: str, key: str) -> dict[str, Any]:
        for turn in turns:
            if not turn.get("agent_name", "").endswith(agent_suffix):
                continue
            value = turn.get(key)
            if isinstance(value, dict) and value:
                return value
            for patch_key in ("artifact_patch", "result_patch"):
                patch = turn.get(patch_key)
                if not isinstance(patch, dict):
                    continue
                nested = patch.get(key)
                if isinstance(nested, dict) and nested:
                    return nested
                plural = patch.get(f"{key}s") or patch.get(key.replace("_candidate", "_candidates"))
                if isinstance(plural, list):
                    first = next((item for item in plural if isinstance(item, dict) and item), None)
                    if first:
                        return first
        return {}

    def _fallback_character_candidate_name(self, project: models.Project, phase: str) -> str:
        text = f"{project.title} {project.premise} {project.genre}"
        if "试药" in text or "药" in text:
            return "试药项目执行者"
        if "禁令" in text:
            return "禁令执行者"
        if "宗门" in text:
            return "宗门执法者"
        if "财团" in text or "集团" in text:
            return "财团执行官"
        if "皇" in text or "朝廷" in text:
            return "朝廷监察使"
        return f"{PHASE_CONFIG[phase]['label']}压力执行者"

    def _fallback_setting_candidate_title(self, project: models.Project, phase: str) -> str:
        text = f"{project.title} {project.premise} {project.genre}"
        if "试药" in text or "药" in text:
            return "人体试药监管规则"
        if "禁令" in text:
            return "血脉禁令执行规则"
        if "宗门" in text:
            return "宗门继承禁令"
        if "财团" in text or "集团" in text:
            return "财团资源垄断规则"
        if "皇" in text or "朝廷" in text:
            return "朝廷监察制度"
        return f"{PHASE_CONFIG[phase]['label']}压力规则"

    def _build_artifacts(
        self,
        project: models.Project,
        phase: str,
        request: OutlineDebateRunRequest,
        result: dict[str, Any],
        turns: list[dict[str, Any]],
        context: dict[str, Any] | None = None,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        candidate_policy = self._candidate_policy(project, phase, request, turns, context or {})
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
            for character_candidate in candidate_policy["character_gap"].get("candidates", []):
                can_materialize = character_candidate.get("can_materialize_on_confirm", True) is not False
                artifacts.append(
                    {
                        "id": generate_id("art"),
                        "type": "character_candidate",
                        "title": character_candidate["name"],
                        "payload": character_candidate,
                        "requires_user_confirmation": not can_materialize,
                        "candidate_source": character_candidate.get("candidate_source", "model_candidate"),
                        "candidate_source_reason": character_candidate.get("candidate_source_reason", ""),
                        "can_materialize_on_confirm": can_materialize,
                    }
                )
        if candidate_policy["setting_gap"]["required"]:
            for setting_candidate in candidate_policy["setting_gap"].get("candidates", []):
                can_materialize = setting_candidate.get("can_materialize_on_confirm", True) is not False
                artifacts.append(
                    {
                        "id": generate_id("art"),
                        "type": "setting_candidate",
                        "title": setting_candidate["title"],
                        "payload": setting_candidate,
                        "requires_user_confirmation": not can_materialize,
                        "candidate_source": setting_candidate.get("candidate_source", "model_candidate"),
                        "candidate_source_reason": setting_candidate.get("candidate_source_reason", ""),
                        "can_materialize_on_confirm": can_materialize,
                    }
                )
        return artifacts, candidate_policy

    def _candidate_policy(
        self,
        project: models.Project,
        phase: str,
        request: OutlineDebateRunRequest,
        turns: list[dict[str, Any]],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        text = self._debate_signal_text(request, turns)
        character_candidates = self._character_candidates_for_policy(project, phase, request, turns, context, include_fallback=True)
        setting_candidates = self._setting_candidates_for_policy(project, phase, request, turns, context, include_fallback=True)
        character_gate = self._candidate_generation_gate("character", phase, request, turns)
        setting_gate = self._candidate_generation_gate("setting", phase, request, turns)
        character_blocked = self._has_candidate_negative_signal(text, "character")
        setting_blocked = self._has_candidate_negative_signal(text, "setting")
        character_signal = self._has_candidate_positive_signal(text, "character")
        setting_signal = self._has_candidate_positive_signal(text, "setting")
        if not character_gate["enabled"]:
            character_candidates = []
        if not setting_gate["enabled"]:
            setting_candidates = []
        character_required = False if character_blocked else character_gate["enabled"] and (bool(character_candidates) or character_signal)
        setting_required = False if setting_blocked else setting_gate["enabled"] and (bool(setting_candidates) or setting_signal)
        if character_required and not character_candidates:
            character_candidates = [self._character_candidate(project, phase, request, turns)]
        if setting_required and not setting_candidates:
            setting_candidates = [self._setting_candidate(project, phase, request, turns)]
        character_count_plan = self._character_count_plan_for_policy(project, phase, request, turns, character_candidates)
        setting_count_plan = self._setting_count_plan_for_policy(project, phase, request, turns, setting_candidates)
        character_source = self._candidate_policy_source(character_candidates, character_required, character_blocked, character_gate, "character")
        setting_source = self._candidate_policy_source(setting_candidates, setting_required, setting_blocked, setting_gate, "setting")
        return {
            "phase": phase,
            "character_gap": {
                "required": character_required,
                "reason": (
                    "用户明确要求不新增角色"
                    if character_blocked
                    else (
                        f"未达到角色候选触发门槛：{character_gate['reason']}"
                        if not character_gate["enabled"]
                        else ("讨论中出现未入库角色，已生成候选" if character_candidates else ("讨论文本明确要求生成角色" if character_required else "未发现新角色"))
                    )
                ),
                "source": character_source,
                "trigger_gate": character_gate,
                "character_count_plan": {} if character_blocked else character_count_plan,
                "candidates": [] if character_blocked else character_candidates,
            },
            "setting_gap": {
                "required": setting_required,
                "reason": (
                    "用户明确要求不新增设定"
                    if setting_blocked
                    else (
                        f"未达到设定候选触发门槛：{setting_gate['reason']}"
                        if not setting_gate["enabled"]
                        else ("讨论中出现未入库设定，已生成候选" if setting_candidates else ("讨论文本明确要求生成设定" if setting_required else "未发现新设定"))
                    )
                ),
                "source": setting_source,
                "trigger_gate": setting_gate,
                "setting_count_plan": {} if setting_blocked else setting_count_plan,
                "candidates": [] if setting_blocked else setting_candidates,
            },
        }

    def _candidate_policy_source(
        self,
        candidates: list[dict[str, Any]],
        required: bool,
        blocked: bool,
        gate: dict[str, Any],
        kind: str,
    ) -> str:
        if blocked:
            return "user_blocked"
        if not gate.get("enabled"):
            return "gate_blocked"
        sources = {str(candidate.get("candidate_source") or "") for candidate in candidates if isinstance(candidate, dict)}
        if "model_candidate" in sources:
            return "appeared_object"
        if "text_extracted_candidate" in sources:
            return "text_extracted_candidate"
        if "service_fallback" in sources:
            return "service_fallback"
        if required:
            return "discussion_signal"
        return "not_needed"

    def _debate_signal_text(
        self,
        request: OutlineDebateRunRequest,
        turns: list[dict[str, Any]],
        phase_run: dict[str, Any] | None = None,
    ) -> str:
        text_parts = [request.requirement]
        if phase_run and isinstance(phase_run.get("user_messages"), list):
            text_parts.extend(str(message.get("message") or "") for message in phase_run["user_messages"] if isinstance(message, dict))
        for turn in turns:
            text_parts.extend(
                [
                    str(turn.get("message", "")),
                    " ".join(str(item) for item in turn.get("claims", []) if item),
                    " ".join(str(item) for item in turn.get("risks", []) if item),
                    dumps(turn.get("artifact_patch", {})),
                    dumps(turn.get("result_patch", {})),
                    dumps(turn.get("character_candidate", {})),
                    dumps(turn.get("character_candidates", [])),
                    dumps(turn.get("setting_candidate", {})),
                    dumps(turn.get("setting_candidates", [])),
                    dumps(turn.get("character_function_audit", {})),
                    dumps(turn.get("setting_function_audit", {})),
                    dumps(turn.get("blocking_items", [])),
                    dumps(turn.get("must_fix_before_confirm", [])),
                ]
            )
        return "\n".join(text_parts)

    def _character_candidates_for_policy(
        self,
        project: models.Project | None,
        phase: str,
        request: OutlineDebateRunRequest,
        turns: list[dict[str, Any]],
        context: dict[str, Any],
        *,
        include_fallback: bool,
    ) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        for raw in self._candidate_dicts_from_turns(turns, "character"):
            normalized = self._normalize_character_candidate(project, phase, request, raw)
            if normalized:
                candidates.append(self._annotate_candidate_source(normalized, "model_candidate", True, "角色生成席位提供了结构化候选。"))
        for name in self._text_object_names(self._debate_signal_text(request, turns), "character"):
            normalized = self._normalize_character_candidate(project, phase, request, {"name": name})
            if normalized:
                candidates.append(self._annotate_candidate_source(normalized, "text_extracted_candidate", False, "服务层从讨论文本抽取名称，缺少完整结构化候选。"))
        candidates = self._filter_new_named_candidates(candidates, context, "character")
        if not candidates and include_fallback and self._has_candidate_positive_signal(self._debate_signal_text(request, turns), "character") and project is not None:
            candidates = [self._character_candidate(project, phase, request, turns)]
        return self._sort_candidates_by_importance(candidates, "name")

    def _setting_candidates_for_policy(
        self,
        project: models.Project | None,
        phase: str,
        request: OutlineDebateRunRequest,
        turns: list[dict[str, Any]],
        context: dict[str, Any],
        *,
        include_fallback: bool,
    ) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        for raw in self._candidate_dicts_from_turns(turns, "setting"):
            normalized = self._normalize_setting_candidate(project, phase, request, raw)
            if normalized:
                candidates.append(self._annotate_candidate_source(normalized, "model_candidate", True, "设定生成席位提供了结构化候选。"))
        for title in self._text_object_names(self._debate_signal_text(request, turns), "setting"):
            normalized = self._normalize_setting_candidate(project, phase, request, {"title": title})
            if normalized:
                candidates.append(self._annotate_candidate_source(normalized, "text_extracted_candidate", False, "服务层从讨论文本抽取名称，缺少完整结构化候选。"))
        candidates = self._filter_new_named_candidates(candidates, context, "setting")
        if not candidates and include_fallback and self._has_candidate_positive_signal(self._debate_signal_text(request, turns), "setting") and project is not None:
            candidates = [self._setting_candidate(project, phase, request, turns)]
        return self._sort_candidates_by_importance(candidates, "title")

    def _character_count_plan_for_policy(
        self,
        project: models.Project,
        phase: str,
        request: OutlineDebateRunRequest,
        turns: list[dict[str, Any]],
        candidates: list[dict[str, Any]],
    ) -> dict[str, Any]:
        generated = self._plan_from_turns(turns, "character_count_plan")
        if generated:
            return generated
        genre_text = f"{getattr(project, 'genre', '')} {getattr(project, 'channel', '')} {request.requirement}".lower()
        volume_count = self._bounded_int(getattr(request, "volume_count", None), 3, 1, 30)
        chapters_per_volume = self._bounded_int(getattr(request, "chapters_per_volume", None), 20, 1, 200)
        chapter_count = max(1, volume_count * chapters_per_volume)
        if any(token in genre_text for token in ("群像", "史诗", "epic", "家族", "朝堂", "战争")):
            planned_total = max(60, min(180, int(chapter_count * 1.2)))
            benchmark_type = "epic_or_ensemble"
        elif any(token in genre_text for token in ("推理", "悬疑", "mystery", "探案")):
            planned_total = max(18, min(45, int(chapter_count * 0.45)))
            benchmark_type = "mystery_or_suspense"
        elif any(token in genre_text for token in ("言情", "romance", "情感")):
            planned_total = max(16, min(36, int(chapter_count * 0.35)))
            benchmark_type = "romance_or_relationship"
        elif any(token in genre_text for token in ("玄幻", "奇幻", "fantasy", "科幻", "仙侠")):
            planned_total = max(45, min(120, int(chapter_count * 0.9)))
            benchmark_type = "speculative_adventure"
        else:
            planned_total = max(24, min(80, int(chapter_count * 0.6)))
            benchmark_type = "general_long_form"
        core = 1 if planned_total < 36 else 2
        major = max(4, min(12, round(planned_total * 0.14)))
        supporting = max(8, min(40, round(planned_total * 0.34)))
        minor = max(0, planned_total - core - major - supporting)
        phase_new = len(candidates)
        return {
            "benchmark_type": benchmark_type,
            "planned_total_characters": planned_total,
            "importance_distribution": {
                "core": core,
                "major": major,
                "supporting": supporting,
                "minor": minor,
            },
            "new_characters_this_phase": phase_new,
            "phase": phase,
            "ordering_rule": "character_candidates 按 importance_score 从高到低输出；同分时核心剧情功能优先。",
            "benchmark_notes": [
                "史诗奇幻或家族群像可承载极大人物表，但大纲阶段只提前规划重要性分布。",
                "推理/悬疑应控制嫌疑人与证人数量，保证读者能跟踪线索公平性。",
                "言情/关系线以少量核心关系和中等规模配角网为宜。",
            ],
        }

    def _setting_count_plan_for_policy(
        self,
        project: models.Project,
        phase: str,
        request: OutlineDebateRunRequest,
        turns: list[dict[str, Any]],
        candidates: list[dict[str, Any]],
    ) -> dict[str, Any]:
        generated = self._plan_from_turns(turns, "setting_count_plan")
        if generated:
            return generated
        return {
            "phase": phase,
            "new_settings_this_phase": len(candidates),
            "ordering_rule": "setting_candidates 按 importance_score 从高到低输出，先规则/组织/地点，后物件/场景细节。",
            "direct_update_policy": "direct_on_outline_confirmation",
            "policy_note": "用户确认对应大纲阶段或条目后直接写入设定库，不进入二次人工审批队列。",
        }

    def _plan_from_turns(self, turns: list[dict[str, Any]], key: str) -> dict[str, Any]:
        for turn in turns:
            value = turn.get(key)
            if isinstance(value, dict) and value:
                return value
            for patch_key in ("artifact_patch", "result_patch"):
                patch = turn.get(patch_key)
                if isinstance(patch, dict) and isinstance(patch.get(key), dict) and patch.get(key):
                    return patch[key]
        return {}

    def _candidate_dicts_from_turns(self, turns: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        direct_keys = (
            ("character_candidate", "character_candidates", "characters", "roles", "人物", "角色", "候选角色")
            if kind == "character"
            else ("setting_candidate", "setting_candidates", "settings", "entities", "world_facts", "world_rules", "设定", "候选设定", "世界观", "规则", "地点", "组织", "场景")
        )
        for turn in turns:
            for key in direct_keys:
                results.extend(self._coerce_candidate_dicts(turn.get(key), kind))
            for patch_key in ("artifact_patch", "result_patch"):
                patch = turn.get(patch_key)
                if not isinstance(patch, dict):
                    continue
                for key in direct_keys:
                    results.extend(self._coerce_candidate_dicts(patch.get(key), kind))
        return results

    def _coerce_candidate_dicts(self, value: Any, kind: str) -> list[dict[str, Any]]:
        if value in ({}, [], None, ""):
            return []
        if isinstance(value, list):
            items: list[dict[str, Any]] = []
            for item in value:
                items.extend(self._coerce_candidate_dicts(item, kind))
            return items
        if not isinstance(value, dict):
            return []
        marker_keys = {"name", "姓名", "角色名", "role_type", "story_function"} if kind == "character" else {
            "title",
            "name",
            "设定名",
            "标题",
            "ref_type",
            "entity_type",
            "content",
            "conflict_utility",
        }
        if any(key in value for key in marker_keys):
            return [value]
        items: list[dict[str, Any]] = []
        for nested in value.values():
            items.extend(self._coerce_candidate_dicts(nested, kind))
        return items

    def _normalize_character_candidate(
        self,
        project: models.Project | None,
        phase: str,
        request: OutlineDebateRunRequest,
        raw: dict[str, Any],
    ) -> dict[str, Any]:
        if not isinstance(raw, dict):
            return {}
        name = self._string_or(raw.get("name") or raw.get("姓名") or raw.get("角色名"), "")
        if not name or self._is_placeholder_candidate_name(name):
            return {}
        fallback = self._character_candidate(project, phase, request, []) if project is not None else {}
        merged = {**fallback, **raw}
        score = self._bounded_int(merged.get("importance_score"), self._importance_score_for_sort(merged), 0, 100)
        role_type = self._string_or(merged.get("role_type") or merged.get("role") or raw.get("角色类型"), fallback.get("role_type") or "supporting")
        long_term_goal = self._first_string(merged.get("long_term_goal"), merged.get("long_term_desire"), fallback.get("long_term_goal"), fallback="完成长期目标")
        immediate_goal = self._first_string(merged.get("immediate_goal"), fallback.get("immediate_goal"), fallback="在首次登场阶段制造选择压力")
        inner_wound = self._first_string(merged.get("inner_wound"), fallback.get("inner_wound"), fallback="尚未明确的内在伤口")
        ability = self._first_string(merged.get("ability"), fallback.get("ability"), fallback="尚未明确的优势或能力")
        ability_cost = self._first_string(merged.get("ability_cost"), fallback.get("ability_cost"), fallback="优势使用会带来可见代价")
        weakness = self._first_string(merged.get("weakness"), fallback.get("weakness"), fallback="尚未明确的弱点")
        secret = self._first_string(merged.get("secret"), fallback.get("secret"), fallback="")
        relationship_hooks = self._clean_string_values(merged.get("relationship_hooks"), merged.get("relationship_hook"), fallback.get("relationship_hooks"))
        goals = self._clean_string_values(merged.get("goals"), long_term_goal, immediate_goal)
        motivations = self._clean_string_values(
            merged.get("motivations"),
            merged.get("motivation"),
            merged.get("conflict_seed"),
            merged.get("reader_satisfaction"),
            fallback.get("motivations"),
        )
        secrets = self._clean_string_values(merged.get("secrets"), secret)
        abilities = self._clean_string_values(merged.get("abilities"), ability, ability_cost)
        weaknesses = self._clean_string_values(merged.get("weaknesses"), weakness, inner_wound)
        if ability_cost and ability_cost not in weaknesses:
            weaknesses.append(ability_cost)
        summary = self._first_string(
            merged.get("summary"),
            merged.get("one_sentence_pitch"),
            merged.get("identity"),
            raw.get("简介"),
            fallback.get("summary"),
            fallback=f"{name}是大纲议事中出现的新角色候选。",
        )
        character_arc = self._first_string(merged.get("character_arc"), merged.get("growth_arc"), merged.get("arc"), fallback.get("character_arc"), fallback="")
        candidate = {
            **merged,
            "name": name,
            "aliases": self._clean_string_values(merged.get("aliases")),
            "role": role_type,
            "role_type": role_type,
            "importance_level": self._string_or(merged.get("importance_level"), self._importance_level_from_score(score)),
            "importance_score": score,
            "title": self._first_string(merged.get("title"), merged.get("identity"), fallback.get("title"), fallback=role_type),
            "one_sentence_pitch": self._first_string(merged.get("one_sentence_pitch"), fallback.get("one_sentence_pitch"), fallback=summary),
            "identity": self._first_string(merged.get("identity"), fallback.get("identity"), fallback=summary),
            "opening_situation": self._first_string(merged.get("opening_situation"), fallback.get("opening_situation"), fallback=f"在{PHASE_CONFIG[phase]['label']}首次形成有效压力。"),
            "world_rule_connection": self._first_string(merged.get("world_rule_connection"), fallback.get("world_rule_connection"), fallback="与当前世界规则或阶段制度压力相连。"),
            "long_term_desire": long_term_goal,
            "long_term_goal": long_term_goal,
            "immediate_goal": immediate_goal,
            "inner_wound": inner_wound,
            "ability": ability,
            "ability_cost": ability_cost,
            "weakness": weakness,
            "secret": secret,
            "growth_arc": self._first_string(merged.get("growth_arc"), character_arc, fallback.get("growth_arc"), fallback=character_arc),
            "character_arc": character_arc,
            "summary": summary,
            "appearance": self._first_string(merged.get("appearance"), fallback.get("appearance"), fallback=""),
            "personality": self._first_string(merged.get("personality"), fallback.get("personality"), inner_wound, fallback=""),
            "profile": self._first_string(merged.get("profile"), fallback.get("profile"), summary, fallback=summary),
            "goals": goals,
            "motivations": motivations,
            "secrets": secrets,
            "abilities": abilities,
            "weaknesses": weaknesses,
            "reader_satisfaction": self._first_string(merged.get("reader_satisfaction"), fallback.get("reader_satisfaction"), fallback=""),
            "long_form_potential": self._first_string(merged.get("long_form_potential"), fallback.get("long_form_potential"), fallback=""),
            "writing_risk": self._first_string(merged.get("writing_risk"), merged.get("risk"), fallback.get("writing_risk"), fallback=""),
            "risk": self._first_string(merged.get("risk"), merged.get("writing_risk"), fallback.get("risk"), fallback=""),
            "revision_hint": self._first_string(merged.get("revision_hint"), fallback.get("revision_hint"), fallback=""),
            "tags": self._clean_string_values(merged.get("tags"), fallback.get("tags")),
            "story_function": self._string_or(merged.get("story_function") or raw.get("剧情功能"), fallback.get("story_function") or "承载新出现的剧情压力和关系冲突。"),
            "first_needed_in": raw.get("first_needed_in") if isinstance(raw.get("first_needed_in"), dict) else {"stage": phase, "reason": request.requirement or "大纲议事出现新角色"},
            "relationship_hooks": relationship_hooks,
            "relationship_hook": self._first_string(merged.get("relationship_hook"), relationship_hooks[0] if relationship_hooks else "", fallback=""),
            "conflict_seed": self._first_string(merged.get("conflict_seed"), fallback.get("conflict_seed"), fallback=""),
            "related_entity_ids": self._clean_string_values(merged.get("related_entity_ids")),
            "related_character_ids": self._clean_string_values(merged.get("related_character_ids")),
            "relations": merged.get("relations") if isinstance(merged.get("relations"), list) else relationship_hooks,
            "current_status": self._string_or(merged.get("current_status"), "active"),
            "updated_reason": self._first_string(merged.get("updated_reason"), fallback.get("updated_reason"), fallback="outline_debate_candidate"),
            "activity_status": "candidate",
            "status": "candidate",
            "source": "outline_debate",
            "canon_write_suggestion": {
                **(fallback.get("canon_write_suggestion") if isinstance(fallback.get("canon_write_suggestion"), dict) else {}),
                **(raw.get("canon_write_suggestion") if isinstance(raw.get("canon_write_suggestion"), dict) else {}),
                "requires_user_approval": False,
                "target": "characters",
                "write_policy": "direct_on_outline_confirmation",
            },
        }
        return candidate

    def _normalize_setting_candidate(
        self,
        project: models.Project | None,
        phase: str,
        request: OutlineDebateRunRequest,
        raw: dict[str, Any],
    ) -> dict[str, Any]:
        if not isinstance(raw, dict):
            return {}
        title = self._string_or(raw.get("title") or raw.get("name") or raw.get("设定名") or raw.get("标题"), "")
        if not title or self._is_placeholder_candidate_name(title):
            return {}
        fallback = self._setting_candidate(project, phase, request, []) if project is not None else {}
        merged = {**fallback, **raw}
        ref_type = self._string_or(merged.get("ref_type"), fallback.get("ref_type") or ("entity" if merged.get("entity_type") else "world_fact"))
        score = self._bounded_int(merged.get("importance_score"), self._importance_score_for_sort(merged), 0, 100)
        content = self._first_string(merged.get("content"), merged.get("description"), raw.get("内容"), fallback.get("content"), fallback=f"{title}是大纲议事中出现的新设定候选。")
        target = "entities" if ref_type in {"entity", "entities", "story_entity", "story_entities"} else "world_facts"
        candidate = {
            **merged,
            "title": title,
            "name": self._first_string(merged.get("name"), title, fallback=title),
            "ref_type": ref_type,
            "category": self._string_or(merged.get("category") or merged.get("entity_type"), fallback.get("category") or "world_rule"),
            "entity_type": self._string_or(merged.get("entity_type") or merged.get("category"), fallback.get("entity_type") or ""),
            "content": content,
            "description": self._first_string(merged.get("description"), content, fallback=content),
            "importance_level": self._string_or(merged.get("importance_level"), self._importance_level_from_score(score)),
            "importance_score": score,
            "confidence": self._bounded_float(merged.get("confidence"), 0.82, 0.0, 1.0),
            "current_status": self._string_or(merged.get("current_status"), "active"),
            "related_entity_ids": self._clean_string_values(merged.get("related_entity_ids")),
            "first_needed_in": merged.get("first_needed_in") if isinstance(merged.get("first_needed_in"), dict) else {"stage": phase, "reason": request.requirement or "大纲议事出现新设定"},
            "conflict_utility": self._first_string(merged.get("conflict_utility"), fallback.get("conflict_utility"), fallback=""),
            "foreshadowing_utility": self._first_string(merged.get("foreshadowing_utility"), fallback.get("foreshadowing_utility"), fallback=""),
            "limitation": self._first_string(merged.get("limitation"), fallback.get("limitation"), fallback=""),
            "cost": self._first_string(merged.get("cost"), fallback.get("cost"), fallback=""),
            "continuity_check": merged.get("continuity_check") if isinstance(merged.get("continuity_check"), dict) else fallback.get("continuity_check", {}),
            "activity_status": "candidate",
            "status": "candidate",
            "source": "outline_debate",
            "canon_write_suggestion": {
                **(fallback.get("canon_write_suggestion") if isinstance(fallback.get("canon_write_suggestion"), dict) else {}),
                **(raw.get("canon_write_suggestion") if isinstance(raw.get("canon_write_suggestion"), dict) else {}),
                "requires_user_approval": False,
                "target": target,
                "write_policy": "direct_on_outline_confirmation",
            },
        }
        return candidate

    def _filter_new_named_candidates(self, candidates: list[dict[str, Any]], context: dict[str, Any], kind: str) -> list[dict[str, Any]]:
        existing = self._existing_object_names(context, kind)
        seen: set[str] = set()
        filtered: list[dict[str, Any]] = []
        for candidate in candidates:
            name = str(candidate.get("name") if kind == "character" else candidate.get("title") or candidate.get("name") or "")
            key = self._object_name_key(name)
            if not key or key in existing or key in seen:
                continue
            seen.add(key)
            filtered.append(candidate)
        return filtered

    def _existing_object_names(self, context: dict[str, Any], kind: str) -> set[str]:
        names: set[str] = set()
        if kind == "character":
            for item in context.get("characters", []):
                if isinstance(item, dict):
                    names.add(self._object_name_key(str(item.get("name") or "")))
        else:
            for collection, key in (("entities", "name"), ("world_facts", "title")):
                for item in context.get(collection, []):
                    if isinstance(item, dict):
                        names.add(self._object_name_key(str(item.get(key) or item.get("name") or "")))
        for phase_run in (context.get("upstream_phase_runs") or {}).values():
            if not isinstance(phase_run, dict):
                continue
            for artifact in phase_run.get("artifacts", []):
                if not isinstance(artifact, dict):
                    continue
                artifact_type = artifact.get("type")
                payload = artifact.get("payload") if isinstance(artifact.get("payload"), dict) else {}
                if kind == "character" and artifact_type == "character_candidate":
                    names.add(self._object_name_key(str(payload.get("name") or "")))
                if kind == "setting" and artifact_type == "setting_candidate":
                    names.add(self._object_name_key(str(payload.get("title") or payload.get("name") or "")))
        return {name for name in names if name}

    def _object_name_key(self, value: str) -> str:
        return re.sub(r"[\s·・•.\-—_《》“”\"'：:，,。；;、（）()]+", "", str(value or "")).lower()

    def _text_object_names(self, text: str, kind: str) -> list[str]:
        compact = str(text or "")
        if kind == "character":
            patterns = (
                r"(?:新角色|新增角色|候选角色|角色名|人物名)\s*[“\"'《]([^”\"'》]{2,20})[”\"'》]",
                r"(?:新角色|新增角色|候选角色|角色名|人物名|角色|人物)\s*[：:]\s*([一-龥A-Za-z0-9·]{2,20})",
                r"(?:候选角色|角色|人物)\s*[：:]\s*([一-龥A-Za-z0-9·]{2,20})",
                r"@([一-龥A-Za-z0-9·]{2,20})(?:角色|人物)",
            )
        else:
            patterns = (
                r"(?:新设定|新增设定|候选设定|新规则|新增规则|新地点|新组织|新场景)\s*[“\"'《]([^”\"'》]{2,24})[”\"'》]",
                r"(?:新设定|新增设定|候选设定|新规则|新增规则|新地点|新组织|新场景)\s*[：:]\s*([一-龥A-Za-z0-9·]{2,24})",
                r"(?:候选设定|候选规则|设定|规则|组织|地点|场景)\s*[：:]\s*([一-龥A-Za-z0-9·]{2,24})",
                r"(?:设定名|规则名|组织名|地点名|场景名)[:：]?\s*([一-龥A-Za-z0-9·]{2,24})",
            )
        names: list[str] = []
        for pattern in patterns:
            names.extend(match.group(1).strip(" ，。；;、") for match in re.finditer(pattern, compact))
        return [name for name in names if self._looks_like_extracted_object_name(name)]

    def _looks_like_extracted_object_name(self, name: str) -> bool:
        value = str(name or "").strip(" ，。；;、")
        if not value or self._is_placeholder_candidate_name(value):
            return False
        bad_prefixes = ("或", "和", "与", "及", "时", "则", "都", "要", "如果", "出现", "未入库", "每")
        bad_fragments = (
            "即可",
            "立即",
            "需要",
            "必须",
            "候选",
            "档案",
            "功能",
            "用途",
            "确认",
            "是",
            "作为",
            "成为",
            "在前往",
            "决定",
            "是否",
            "携带",
            "开头",
            "第",
            "章",
            "都有",
            "一次",
            "躲避",
            "离厂",
            "离开",
        )
        if value.startswith(bad_prefixes):
            return False
        return not any(fragment in value for fragment in bad_fragments)

    def _has_candidate_gap_signal(self, text: str, gap_type: str) -> bool:
        if self._has_candidate_negative_signal(text, gap_type):
            return False
        return self._has_candidate_positive_signal(text, gap_type)

    def _has_candidate_negative_signal(self, text: str, gap_type: str) -> bool:
        compact = "".join(text.split())
        if gap_type == "character":
            negative_patterns = ("不新增角色", "无需新增角色", "不需要新增角色", "不生成角色", "不补角色", "不新增角色或设定", "不新增设定或角色")
        else:
            negative_patterns = ("不新增设定", "无需新增设定", "不需要新增设定", "不生成设定", "不补设定", "不新增角色或设定", "不新增设定或角色")
        return any(pattern in compact for pattern in negative_patterns)

    def _has_candidate_positive_signal(self, text: str, gap_type: str) -> bool:
        compact = "".join(text.split())
        if gap_type == "character":
            positive_patterns = ("缺角色", "角色缺口", "补角色", "新增角色", "新角色", "角色名", "候选角色", "角色候选", "角色承载缺口", "角色和设定", "角色与设定")
        else:
            positive_patterns = ("缺设定", "设定缺口", "缺规则", "规则缺口", "补设定", "补规则", "新增设定", "新设定", "新增规则", "新规则", "新地点", "新组织", "新场景", "候选设定", "候选规则", "角色和设定", "角色与设定")
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
        quality_check = self._outline_quality_check(result)
        if quality_check:
            checks.append(quality_check)
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

    def _outline_quality_check(self, result: dict[str, Any]) -> dict[str, Any] | None:
        metrics = result.get("quality_metrics") if isinstance(result.get("quality_metrics"), dict) else {}
        if not metrics:
            return None
        blocking_items = metrics.get("blocking_items") if isinstance(metrics.get("blocking_items"), list) else []
        return {
            "validator": "outline_quality_gate",
            "status": "failed" if blocking_items else "passed",
            "message": "大纲候选通过严格质量指标" if not blocking_items else "大纲候选未通过严格质量指标",
            "metrics": {key: value for key, value in metrics.items() if key != "blocking_items"},
            "issues": [str(item.get("evidence") or item) for item in blocking_items if isinstance(item, dict)],
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
                for key in ("volume_no", "title", "volume_function", "rhythm_model", "core_goal", "volume_hook", "main_conflict", "ending_hook", "character_arc", "setting_reveal_plan", "foreshadowing_plan"):
                    if item.get(key) in (None, "", [], {}):
                        issues.append(f"volume_outlines[{index}].{key} 为空")
        else:
            chapter_windows = result.get("chapter_windows") if isinstance(result.get("chapter_windows"), list) else []
            if not chapter_windows:
                issues.append("chapter_windows 为空")
            for index, item in enumerate(chapter_windows, start=1):
                if not isinstance(item, dict):
                    issues.append(f"chapter_windows[{index}] 不是 object")
                    continue
                for key in ("window_no", "volume_no", "chapter_range", "stage_goal", "main_pressure", "state_change_goal", "mini_crisis", "mini_climax", "transition_hook"):
                    if item.get(key) in (None, "", [], {}):
                        issues.append(f"chapter_windows[{index}].{key} 为空")
            chapter_outlines = result.get("chapter_outlines") if isinstance(result.get("chapter_outlines"), list) else []
            if not chapter_outlines:
                issues.append("chapter_outlines 为空")
            for index, item in enumerate(chapter_outlines, start=1):
                if not isinstance(item, dict):
                    issues.append(f"chapter_outlines[{index}] 不是 object")
                    continue
                for key in ("chapter_no", "title", "outline", "pov_character", "core_event", "conflict", "crisis", "climax", "result", "cliffhanger", "state_change", "foreshadowing_use", "source_window"):
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
        gap_rationale = "角色/设定生成席位只在缺口明确时输出待确认条目；对应大纲条目确认后由服务层直接入库。"
        if character_gap.get("required") and setting_gap.get("required"):
            gap_decision = "本阶段发现角色与设定缺口，分别生成待确认条目，并将在确认本阶段时直接入库。"
            gap_rationale = f"{character_gap.get('reason', '')}；{setting_gap.get('reason', '')}"
        elif character_gap.get("required"):
            gap_decision = "本阶段发现角色缺口，生成待确认角色条目，并将在确认本阶段时直接入库。"
            gap_rationale = str(character_gap.get("reason") or "讨论文本明确存在角色缺口")
        elif setting_gap.get("required"):
            gap_decision = "本阶段发现设定缺口，生成待确认设定条目，并将在确认本阶段时直接入库。"
            gap_rationale = str(setting_gap.get("reason") or "讨论文本明确存在设定缺口")
        return [
            {
                "id": generate_id("dec"),
                "phase": phase,
                "title": f"{PHASE_CONFIG[phase]['label']}边界",
                "decision": "讨论阶段只产待确认条目；用户确认阶段或条目时，服务层立即写入正式正典。",
                "rationale": "保持讨论可回溯、用户确认、服务层直接入库和版本审计的边界。",
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
        previous_turn: dict[str, Any] | None = None
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
                route_decision = previous_turn.get("route_decision") if isinstance(previous_turn, dict) and isinstance(previous_turn.get("route_decision"), dict) else {}
                edge_reason = str(route_decision.get("reason") or "按讨论顺序推进")
                edges.append(
                    {
                        "id": generate_id("edge"),
                        "source": previous_id,
                        "target": node_id,
                        "type": "handoff",
                        "label": "议事交接",
                        "reason": edge_reason,
                        "route_decision": route_decision,
                    }
                )
                events.append({"id": generate_id("evt"), "type": "route_decision", "node_id": node_id, "payload": route_decision})
            previous_id = node_id
            previous_turn = turn
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
        artifacts, candidate_policy = self._build_artifacts(project, phase, request, result, turns, context)
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
