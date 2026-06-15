from __future__ import annotations

import difflib
import json
from pathlib import Path
import random
import zipfile
from typing import Any, Callable, Iterator

from fastapi import HTTPException
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.agents.contracts import NovelStudioState
from app.agents.chapter_writing.service import chapter_writing_service
from app.agents.creation_star.service import creation_star_agent_service
from app.agents.llm_io import call_agent_json
from app.agents.outline_swarm.service import run_outline_swarm
from app.agents.outline_swarm.swarm import OUTLINE_SWARM_AGENT_NAMES
from app.agents.prompts import AGENT_PROMPT_BINDINGS, AGENT_SPECS_BY_NAME, DEFAULT_AGENT_SPECS, OUTLINE_AGENT_SEQUENCE
from app.agents.shared.prompt_catalog import get_prompt_entry, list_prompt_lifecycle_workflows, list_prompt_workflows, load_catalog_prompt
from app.core.config import LLMProviderResolver, get_settings
from app.core.ids import generate_id
from app.core.json import dumps, loads
from app.db import models
from app.db.models import utcnow
from app.db.session import SessionLocal
from app.schemas.chapter import PlanChaptersRequest
from app.schemas.outline import (
    BookOutlineCommitRequest,
    BookOutlineGenerateRequest,
    ChapterOutlineBatchGenerateRequest,
    ChapterOutlineCommitRequest,
)
from app.schemas.studio import (
    AgentModelConfigRequest,
    AgentPromptUpdateRequest,
    BatchGenerateRequest,
    BranchVersionRequest,
    CanonBulkArchiveRequest,
    CanonDuplicateScanRequest,
    CanonExportRequest,
    CanonFolderRequest,
    CanonLockFieldsRequest,
    CanonNodeMoveRequest,
    CanonProposalDecisionRequest,
    CanonRollbackRequest,
    ChapterChatRequest,
    CreationBasicSuggestionsRequest,
    CreationSessionCardRequest,
    CreationSessionCommitRequest,
    CreationSessionCreateRequest,
    CreationSessionRunRequest,
    CreationSessionSeedRequest,
    CreationStarCommitRequest,
    CreationStarDrawRequest,
    CreateCharacterRequest,
    CreateEntityRequest,
    CreateForeshadowingRequest,
    CreateWorldFactRequest,
    DraftChapterRequest,
    ExportRequest,
    ExportTemplateRequest,
    GenerateSettingRequest,
    GenerateStoryBibleRequest,
    ImportPromptTemplatesRequest,
    JobControlRequest,
    LearnStyleRequest,
    PartialRewriteRequest,
    PromptTemplateRequest,
    QueryKnowledgeRequest,
    RewriteChapterRequest,
    RollbackVersionRequest,
    SummaryRequest,
    TextToolRequest,
    UpdateChapterRequest,
    UpdateCharacterRequest,
    UpdateEntityRequest,
    UpdateForeshadowingRequest,
    UpdateWorldFactRequest,
    PayoffForeshadowingRequest,
    VersionCompareRequest,
    WriteGenerateRequest,
)
from app.services.llm_catalog import catalog_payload
from app.services.serializers import (
    isoformat,
    serialize_agent_run,
    serialize_canon_node,
    serialize_canon_proposal,
    serialize_canon_version,
    serialize_chapter,
    serialize_character,
    serialize_creation_session,
    serialize_continuity_issue,
    serialize_export_job,
    serialize_foreshadowing_item,
    serialize_generation_output,
    serialize_graph_edge,
    serialize_graph_node,
    serialize_job,
    serialize_prompt_template,
    serialize_project,
    serialize_story_bible,
    serialize_story_entity,
    serialize_version_snapshot,
    serialize_volume,
    serialize_world_fact,
)
from app.services.llm_client import llm_client


BOOK_OUTLINE_AGENT_SEQUENCE = tuple(agent for agent in OUTLINE_AGENT_SEQUENCE if agent != "beat_control")
BOOK_OUTLINE_SWARM_AGENT_NAMES = tuple(agent for agent in OUTLINE_SWARM_AGENT_NAMES if agent != "BeatControllerAgent")
CHAPTER_OUTLINE_AGENT_SEQUENCE = ("beat_control", "foreshadowing_manager", "logic_audit")
CREATION_CANON_APPROVAL_SECTIONS = ("project", "story_bible", "characters", "entities", "world_facts", "graph")
TOPOLOGY_ARTIFACT_EVENT_TYPES = {"outline_piece", "canon_candidate", "completion_ticket", "uncertainty_ticket"}


def _outline_swarm_agent_names_for_generation_kind(generation_kind: str) -> tuple[str, ...]:
    if generation_kind == "book_outline":
        return BOOK_OUTLINE_SWARM_AGENT_NAMES
    return OUTLINE_SWARM_AGENT_NAMES


def _not_found(message: str) -> HTTPException:
    return HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": message})


def _conflict(message: str, details: dict[str, Any] | None = None) -> HTTPException:
    return HTTPException(status_code=409, detail={"code": "CONFLICT", "message": message, "details": details or {}})


def _bad_request(message: str, details: dict[str, Any] | None = None) -> HTTPException:
    return HTTPException(status_code=400, detail={"code": "VALIDATION_ERROR", "message": message, "details": details or {}})


CREATION_STAR_OPTIONS: dict[str, Any] = {
    "channels": ["男频", "女频", "无CP", "纯爱", "百合", "衍生", "通用"],
    "genres": [
        "玄幻",
        "奇幻",
        "武侠",
        "仙侠",
        "都市",
        "现实",
        "历史",
        "军事",
        "游戏",
        "体育",
        "科幻",
        "悬疑",
        "灵异",
        "轻小说",
        "二次元",
        "古言",
        "现言",
        "幻想言情",
        "青春校园",
        "豪门",
        "职场",
        "种田",
        "美食",
        "无限流",
        "末世",
        "星际",
        "赛博",
        "克苏鲁",
    ],
    "subgenres": [
        "东方玄幻",
        "异世大陆",
        "高武世界",
        "王朝争霸",
        "修真文明",
        "古典仙侠",
        "幻想修仙",
        "都市异能",
        "都市高武",
        "娱乐圈",
        "年代文",
        "宫斗宅斗",
        "架空历史",
        "历史权谋",
        "刑侦推理",
        "规则怪谈",
        "直播文",
        "快穿",
        "系统流",
        "重生",
        "穿越",
        "马甲文",
        "团宠",
        "先婚后爱",
        "破镜重圆",
        "追妻火葬场",
        "群像",
        "经营建设",
        "基建种田",
        "御兽",
        "卡牌",
        "机甲",
        "星际文明",
        "无限副本",
        "末日求生",
        "灵气复苏",
        "学院流",
        "宗门流",
        "家族流",
    ],
    "tags": [
        "爽文",
        "升级流",
        "强者归来",
        "废柴流",
        "复仇",
        "权谋",
        "成长",
        "热血",
        "轻松",
        "沙雕",
        "脑洞",
        "悬疑",
        "黑暗流",
        "幕后流",
        "无敌流",
        "苟道",
        "种田",
        "基建",
        "经营",
        "卡牌",
        "御兽",
        "机甲",
        "星际",
        "灵气复苏",
        "学院流",
        "宗门流",
        "家族流",
        "赛博朋克",
        "克苏鲁",
        "规则怪谈",
        "直播",
        "群像",
        "反转",
        "悬念",
        "救赎",
        "虐恋",
        "甜宠",
        "双强",
        "强强",
        "欢喜冤家",
        "先婚后爱",
        "破镜重圆",
        "追妻",
        "马甲",
        "团宠",
        "女强",
        "大女主",
        "真假千金",
        "萌宝",
        "宫斗",
        "宅斗",
        "美食",
        "职场",
        "娱乐圈",
        "年代",
        "治愈",
        "轻喜剧",
        "慢热",
        "快节奏",
        "多视角",
        "单元剧",
    ],
    "styles": ["热血爽快", "轻松脑洞", "悬疑克制", "文艺细腻", "群像史诗", "暗黑压迫", "甜宠轻喜", "现实锋利"],
    "target_word_bands": [
        {"label": "短长篇 30-50 万字", "value": 400000},
        {"label": "中长篇 80-120 万字", "value": 1000000},
        {"label": "长篇 150-250 万字", "value": 2000000},
        {"label": "超长篇 300 万字以上", "value": 3000000},
    ],
    "sources": [
        {"name": "起点中文网全部作品分类", "url": "https://www.qidian.com/all"},
        {"name": "晋江文学城作品检索/类型体系", "url": "https://www.jjwxc.net"},
        {"name": "番茄小说分类", "url": "https://fanqienovel.com"},
        {"name": "纵横中文网分类", "url": "https://www.zongheng.com"},
    ],
}


class StudioService:
    def creation_star_options(self) -> dict:
        return creation_star_agent_service.options(CREATION_STAR_OPTIONS)

    def creation_star_draw(self, db: Session, project_id: str, request: CreationStarDrawRequest) -> dict:
        return creation_star_agent_service.draw(self, db, project_id, request, llm_client_instance=llm_client)

    def creation_star_commit(self, db: Session, project_id: str, request: CreationStarCommitRequest) -> dict:
        return creation_star_agent_service.commit(self, db, project_id, request)

    def creation_basic_suggestions(self, db: Session, project_id: str, request: CreationBasicSuggestionsRequest) -> dict:
        project = self._project(db, project_id)
        basic = self._normalized_creation_basic(project, request.basic_info)
        for visible_text_field in ("target_reader", "initial_idea"):
            if not str(request.basic_info.get(visible_text_field) or "").strip():
                basic[visible_text_field] = ""
        model = self._configured_model_for_agent(db, "creation_star_session", "creation_star", request.model)
        prompt_snapshot = self._creation_basic_suggestions_prompt_snapshot(basic, request)
        fallback = {
            "suggestions": self._local_creation_basic_suggestions(basic, request.manual_input, request.count),
            "prompt_snapshot": prompt_snapshot,
        }
        payload, llm_meta = call_agent_json(
            llm_client=llm_client,
            agent_name="creation_basic_suggestions",
            role="创作 Star 基本信息灵感选项生成器",
            system_prompt=(
                "你是创作 Star 基本信息页的灵感选项生成器。你只生成候选标签、脑洞和抽卡约束，"
                "不得替用户确认正式设定，不得写正文。每次刷新都要明显区别 previous_suggestions，"
                "围绕当前频道、类型、标签、目标读者、目标字数、风格、初始想法和额外约束，"
                "输出可直接应用到 initial_idea 或 manual_input 的短建议。"
            ),
            task=(
                "为创作 Star 基本信息页 03 初始想法与抽卡约束生成一批可点击建议。"
                "suggestions 必须同时覆盖 target=initial_idea 与 target=manual_input。"
            ),
            context={
                "project": {"id": project.id, "title": project.title, "language": project.language},
                "basic_info": basic,
                "manual_input": request.manual_input,
                "previous_suggestions": request.previous_suggestions[-12:],
                "count": request.count,
                "output_contract": {
                    "suggestions": [
                        {
                            "id": "idea_or_constraint_id",
                            "target": "initial_idea | manual_input",
                            "title": "8-16 字按钮标题",
                            "content": "可追加到输入框的一句话或短段落",
                            "tags": ["标签"],
                            "reason": "为什么适合当前立项",
                        }
                    ]
                },
            },
            fallback=fallback,
            model=model,
        )
        suggestions = self._normalize_creation_basic_suggestions(payload.get("suggestions"), fallback["suggestions"], request.count)
        suggestions = self._dedupe_creation_basic_suggestions(suggestions, request.previous_suggestions, fallback["suggestions"], request.count)
        return {
            "suggestions": suggestions,
            "prompt_snapshot": payload.get("prompt_snapshot") if isinstance(payload.get("prompt_snapshot"), dict) else prompt_snapshot,
            "llm": llm_meta,
        }

    def create_creation_session(self, db: Session, project_id: str, request: CreationSessionCreateRequest) -> dict:
        project = self._project(db, project_id)
        basic = self._normalized_creation_basic(project, request.basic_info)
        state = {
            "worldview_candidates": [],
            "protagonist_candidates": [],
            "title_candidates": [],
            "market_position_candidates": [],
            "project_seed": {},
            "core_conflict_system": {},
            "novel_constitution": {},
            "constitution_review": {},
            "canon_candidates": {},
            "model": request.model,
        }
        session = models.CreationSession(
            id=generate_id("crs"),
            project_id=project_id,
            status="draft",
            current_step="brief",
            basic_info_json=dumps(basic),
            state_json=dumps(state),
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        return {"session": serialize_creation_session(session)}

    def get_creation_session(self, db: Session, project_id: str, session_id: str) -> dict:
        return {"session": serialize_creation_session(self._creation_session(db, project_id, session_id))}

    def creation_session_worldviews(self, db: Session, project_id: str, session_id: str, request: CreationSessionCardRequest) -> dict:
        project = self._project(db, project_id)
        session = self._creation_session(db, project_id, session_id)
        basic = loads(session.basic_info_json, {})
        state = self._creation_session_state(session)
        if request.replace_existing:
            self._reset_creation_session_after(state, "worldview")
        previous_cards = state.get("worldview_candidates") if isinstance(state.get("worldview_candidates"), list) else []
        payload, job = self._run_creation_star_draw_step(
            db,
            project,
            "worldview",
            basic,
            {},
            {},
            {},
            {},
            request.count,
            request.manual_input,
            self._configured_model_for_agent(db, "creation_star_session", "creation_star", request.model or state.get("model")),
            "creation_worldview_card",
            previous_cards=previous_cards,
        )
        cards = payload.get("cards") if isinstance(payload.get("cards"), list) else []
        state["worldview_candidates"] = [*state.get("worldview_candidates", []), *cards]
        if cards and not state.get("selected_worldview"):
            state["selected_worldview"] = cards[0]
        session.current_step = "worldview"
        self._save_creation_session_state(session, state)
        self._finish_job(db, job, {**payload, "session_id": session.id})
        db.commit()
        db.refresh(session)
        return {"session": serialize_creation_session(session), "job": serialize_job(job), **payload}

    def creation_session_protagonists(self, db: Session, project_id: str, session_id: str, request: CreationSessionCardRequest) -> dict:
        project = self._project(db, project_id)
        session = self._creation_session(db, project_id, session_id)
        basic = loads(session.basic_info_json, {})
        state = self._creation_session_state(session)
        worldview = request.selected_worldview or state.get("selected_worldview") or self._pick(state.get("worldview_candidates", []), 0, {})
        if not worldview:
            raise _bad_request("请先选择或生成世界观卡片")
        if request.replace_existing:
            self._reset_creation_session_after(state, "protagonist")
        state["selected_worldview"] = worldview
        previous_cards = state.get("protagonist_candidates") if isinstance(state.get("protagonist_candidates"), list) else []
        payload, job = self._run_creation_star_draw_step(
            db,
            project,
            "protagonist",
            basic,
            worldview,
            {},
            {},
            {},
            request.count,
            request.manual_input,
            self._configured_model_for_agent(db, "creation_star_session", "creation_star", request.model or state.get("model")),
            "creation_protagonist_card",
            previous_cards=previous_cards,
        )
        cards = payload.get("cards") if isinstance(payload.get("cards"), list) else []
        state["protagonist_candidates"] = [*state.get("protagonist_candidates", []), *cards]
        if cards and not state.get("selected_protagonist"):
            state["selected_protagonist"] = cards[0]
        session.current_step = "protagonist"
        self._save_creation_session_state(session, state)
        self._finish_job(db, job, {**payload, "session_id": session.id})
        db.commit()
        db.refresh(session)
        return {"session": serialize_creation_session(session), "job": serialize_job(job), **payload}

    def creation_session_market_position(self, db: Session, project_id: str, session_id: str, request: CreationSessionCardRequest) -> dict:
        project = self._project(db, project_id)
        session = self._creation_session(db, project_id, session_id)
        basic = loads(session.basic_info_json, {})
        state = self._creation_session_state(session)
        worldview = request.selected_worldview or state.get("selected_worldview") or self._pick(state.get("worldview_candidates", []), 0, {})
        protagonist = request.selected_protagonist or state.get("selected_protagonist") or self._pick(state.get("protagonist_candidates", []), 0, {})
        if not worldview or not protagonist:
            raise _bad_request("请先选择世界观和主角人设")
        if request.replace_existing:
            self._reset_creation_session_after(state, "market_position")
        state["selected_worldview"] = worldview
        state["selected_protagonist"] = protagonist
        rng = random.SystemRandom()
        provisional_bible, provisional_rules = self._creation_bible_and_rules(basic, worldview, protagonist, request.manual_input, rng)
        payload, job = self._run_creation_star_draw_step(
            db,
            project,
            "title",
            basic,
            worldview,
            protagonist,
            provisional_bible,
            provisional_rules,
            request.count,
            request.manual_input,
            self._configured_model_for_agent(db, "creation_star_session", "creation_star", request.model or state.get("model")),
            "creation_market_position_card",
        )
        title_cards = payload.get("cards") if isinstance(payload.get("cards"), list) else []
        market_cards = self._creation_market_position_cards(basic, worldview, protagonist, title_cards, request.count, job.id)
        state["title_candidates"] = [*state.get("title_candidates", []), *title_cards]
        state["market_position_candidates"] = [*state.get("market_position_candidates", []), *market_cards]
        if title_cards and not state.get("selected_title"):
            state["selected_title"] = title_cards[0]
        if market_cards and not state.get("market_position"):
            state["market_position"] = market_cards[0]
        session.current_step = "market_position"
        self._save_creation_session_state(session, state)
        self._finish_job(db, job, {**payload, "market_position_candidates": market_cards, "session_id": session.id})
        db.commit()
        db.refresh(session)
        return {
            "session": serialize_creation_session(session),
            "job": serialize_job(job),
            "title_candidates": title_cards,
            "market_position_candidates": market_cards,
            "prompt_snapshot": payload.get("prompt_snapshot", {}),
        }

    def creation_session_seed(self, db: Session, project_id: str, session_id: str, request: CreationSessionSeedRequest) -> dict:
        session = self._creation_session(db, project_id, session_id)
        state = self._creation_session_state(session)
        worldview = request.selected_worldview or state.get("selected_worldview") or self._pick(state.get("worldview_candidates", []), 0, {})
        protagonist = request.selected_protagonist or state.get("selected_protagonist") or self._pick(state.get("protagonist_candidates", []), 0, {})
        title = request.selected_title or state.get("selected_title") or self._pick(state.get("title_candidates", []), 0, {})
        market_position = request.market_position or state.get("market_position") or self._pick(state.get("market_position_candidates", []), 0, {})
        if not worldview or not protagonist:
            raise _bad_request("立项种子至少需要已选世界观和主角人设")
        project_seed = {
            "basic_info": loads(session.basic_info_json, {}),
            "selected_worldview": worldview,
            "selected_protagonist": protagonist,
            "selected_title": title,
            "market_position": market_position,
            "user_note": request.user_note,
        }
        state["selected_worldview"] = worldview
        state["selected_protagonist"] = protagonist
        state["selected_title"] = title
        state["market_position"] = market_position
        state["project_seed"] = project_seed
        session.current_step = "seed"
        self._save_creation_session_state(session, state)
        db.commit()
        db.refresh(session)
        return {"session": serialize_creation_session(session), "project_seed": project_seed}

    def creation_session_core_conflict(self, db: Session, project_id: str, session_id: str, request: CreationSessionRunRequest) -> dict:
        project = self._project(db, project_id)
        session = self._creation_session(db, project_id, session_id)
        state = self._creation_session_state(session)
        seed = self._require_project_seed(state)
        fallback = self._core_conflict_from_seed(seed)
        payload, job, llm_meta = self._run_structured_creation_agent(
            db,
            project,
            "creation_core_conflict",
            "chief_architect",
            "根据创作 Star 已确认的立项种子生成核心矛盾系统。必须输出 protagonist_desire、world_resistance、core_conflict、external_resistance、internal_resistance、relationship_resistance、institutional_resistance、typical_cost、long_form_engine、possible_endpoint、theme_question。",
            {"project": serialize_project(project), "project_seed": seed, "instruction": request.instruction},
            fallback,
            self._configured_model_for_agent(db, "creation_star_session", "chief_architect", request.model or state.get("model")),
        )
        if not isinstance(payload, dict):
            payload = fallback
        payload = {**fallback, **payload}
        state["core_conflict_system"] = payload
        session.current_step = "core_conflict"
        self._save_creation_session_state(session, state)
        self._record_agent_run(db, job, "chief_architect", {**payload, "_llm": llm_meta}, {"project_seed": seed})
        self._finish_job(db, job, {"core_conflict_system": payload, "session_id": session.id})
        db.commit()
        db.refresh(session)
        return {"session": serialize_creation_session(session), "job": serialize_job(job), "core_conflict_system": payload}

    def creation_session_constitution(self, db: Session, project_id: str, session_id: str, request: CreationSessionRunRequest) -> dict:
        project = self._project(db, project_id)
        session = self._creation_session(db, project_id, session_id)
        state = self._creation_session_state(session)
        seed = self._require_project_seed(state)
        core_conflict = state.get("core_conflict_system") or self._core_conflict_from_seed(seed)
        fallback = self._novel_constitution_from_seed(seed, core_conflict)
        payload, job, llm_meta = self._run_structured_creation_agent(
            db,
            project,
            "creation_novel_constitution",
            "chief_architect",
            "根据核心矛盾系统生成小说宪法。必须输出 basic_positioning、core_narrative_engine、protagonist_arc、world_rules、character_functions、theme_pressure、cost_mechanism、forbidden_directions、long_form_sustainability。",
            {"project": serialize_project(project), "project_seed": seed, "core_conflict_system": core_conflict, "instruction": request.instruction},
            fallback,
            self._configured_model_for_agent(db, "creation_star_session", "chief_architect", request.model or state.get("model")),
        )
        if not isinstance(payload, dict):
            payload = fallback
        payload = {**fallback, **payload}
        payload["core_narrative_engine"] = payload.get("core_narrative_engine") or core_conflict
        state["novel_constitution"] = payload
        session.current_step = "constitution"
        self._save_creation_session_state(session, state)
        self._record_agent_run(db, job, "chief_architect", {**payload, "_llm": llm_meta}, {"project_seed": seed, "core_conflict_system": core_conflict})
        self._finish_job(db, job, {"novel_constitution": payload, "session_id": session.id})
        db.commit()
        db.refresh(session)
        return {"session": serialize_creation_session(session), "job": serialize_job(job), "novel_constitution": payload}

    def creation_session_constitution_review(self, db: Session, project_id: str, session_id: str, request: CreationSessionRunRequest) -> dict:
        project = self._project(db, project_id)
        session = self._creation_session(db, project_id, session_id)
        state = self._creation_session_state(session)
        seed = self._require_project_seed(state)
        constitution = state.get("novel_constitution") or self._novel_constitution_from_seed(seed, state.get("core_conflict_system") or {})
        fallback = self._constitution_review_from_constitution(constitution)
        payload, job, llm_meta = self._run_structured_creation_agent(
            db,
            project,
            "creation_constitution_review",
            "reviewer",
            "对小说宪法做压力测试。必须输出 status、largest_strength、largest_risk、blocking_issues、revision_suggestions、recommended_next_stage。status 只能是 passed、passed_with_notes、needs_revision、blocked。",
            {"project": serialize_project(project), "project_seed": seed, "novel_constitution": constitution, "instruction": request.instruction},
            fallback,
            self._configured_model_for_agent(db, "creation_star_session", "reviewer", request.model or state.get("model")),
        )
        if not isinstance(payload, dict):
            payload = fallback
        payload = {**fallback, **payload}
        if payload.get("status") not in {"passed", "passed_with_notes", "needs_revision", "blocked"}:
            payload["status"] = fallback["status"]
        state["constitution_review"] = payload
        session.current_step = "constitution_review"
        self._save_creation_session_state(session, state)
        self._record_agent_run(db, job, "reviewer", {**payload, "_llm": llm_meta}, {"project_seed": seed, "novel_constitution": constitution})
        self._finish_job(db, job, {"constitution_review": payload, "session_id": session.id})
        db.commit()
        db.refresh(session)
        return {"session": serialize_creation_session(session), "job": serialize_job(job), "constitution_review": payload}

    def creation_session_canon_preview(self, db: Session, project_id: str, session_id: str, request: CreationSessionRunRequest) -> dict:
        project = self._project(db, project_id)
        session = self._creation_session(db, project_id, session_id)
        state = self._creation_session_state(session)
        seed = self._require_project_seed(state)
        self._require_creation_constitution_ready(state)
        candidates = self._canon_candidates_from_creation_state(project, loads(session.basic_info_json, {}), state)
        payload, job, llm_meta = self._run_structured_creation_agent(
            db,
            project,
            "creation_canon_preview",
            "canon_curator",
            "把创作 Star 立项种子、核心矛盾、小说宪法和压力测试结果映射为待用户确认的正典候选。不要写入正式设定集。",
            {"project": serialize_project(project), "project_seed": seed, "creation_state": state, "instruction": request.instruction},
            {"canon_candidates": candidates},
            self._configured_model_for_agent(db, "creation_star_session", "canon_curator", request.model or state.get("model")),
        )
        if isinstance(payload, dict) and isinstance(payload.get("canon_candidates"), dict):
            candidates = {**candidates, **payload["canon_candidates"]}
        state["canon_candidates"] = candidates
        state["project_bible"] = candidates.get("project_bible", state.get("project_bible", {}))
        state["world_rules"] = candidates.get("world_rules", state.get("world_rules", {}))
        session.current_step = "canon_preview"
        self._save_creation_session_state(session, state)
        self._record_agent_run(db, job, "canon_curator", {"canon_candidates": candidates, "_llm": llm_meta}, {"project_seed": seed, "creation_state": state})
        self._finish_job(db, job, {"canon_candidates": candidates, "session_id": session.id})
        db.commit()
        db.refresh(session)
        return {"session": serialize_creation_session(session), "job": serialize_job(job), "canon_candidates": candidates}

    def creation_session_commit(self, db: Session, project_id: str, session_id: str, request: CreationSessionCommitRequest) -> dict:
        project = self._project(db, project_id)
        story_bible = self._story_bible(db, project_id)
        session = self._creation_session(db, project_id, session_id)
        state = self._creation_session_state(session)
        seed = self._require_project_seed(state)
        self._require_creation_constitution_ready(state)
        self._require_approved_canon_sections(request.approved_canon_sections)
        candidates = state.get("canon_candidates")
        if not isinstance(candidates, dict) or not candidates:
            candidates = self._canon_candidates_from_creation_state(project, loads(session.basic_info_json, {}), state)
            state["canon_candidates"] = candidates
        basic = loads(session.basic_info_json, {})
        worldview = seed.get("selected_worldview") or {}
        protagonist = seed.get("selected_protagonist") or {}
        selected_title = seed.get("selected_title") or {}
        project_bible = candidates.get("project_bible") or self._project_bible_from_creation_state(state)
        world_rules = candidates.get("world_rules") or self._world_rules_from_creation_state(state)
        story_candidate = candidates.get("story_bible_candidate") if isinstance(candidates.get("story_bible_candidate"), dict) else {}
        job = self._create_job(
            db,
            project_id,
            None,
            "creation_canon_commit",
            self._configured_model_for_agent(db, "creation_star_session", "canon_curator", request.model or state.get("model")),
            {"session_id": session_id},
            total_steps=2,
        )

        project.title = str(selected_title.get("title") or project.title)
        project.genre = basic.get("genre", project.genre)
        project.target_reader = basic.get("target_reader", project.target_reader)
        project.target_words = int(basic.get("target_words") or project.target_words or 0)
        project.initial_idea = basic.get("initial_idea", project.initial_idea)
        project.style_guide = basic.get("style", project.style_guide)
        project.premise = story_candidate.get("main_conflict") or project_bible.get("核心矛盾") or project.premise

        story_bible.version += 1
        story_bible.world_setting = story_candidate.get("world_setting") or story_bible.world_setting
        story_bible.main_conflict = story_candidate.get("main_conflict") or project_bible.get("核心矛盾") or story_bible.main_conflict
        story_bible.themes_json = dumps(story_candidate.get("themes") or project_bible.get("主线关键词") or [])
        story_bible.style_guide = story_candidate.get("style_guide") or basic.get("style", story_bible.style_guide)
        story_bible.narrative_pov = story_candidate.get("narrative_pov") or story_bible.narrative_pov
        story_bible.forbidden_elements_json = dumps(story_candidate.get("forbidden_elements") or world_rules.get("禁忌规则") or [])
        story_bible.continuity_rules_json = dumps(story_candidate.get("continuity_rules") or world_rules.get("不可违反设定") or [])

        character = self._upsert_creation_protagonist(db, project_id, protagonist, basic, worldview)
        entities = self._upsert_creation_entities(db, project_id, worldview, world_rules)
        facts = self._upsert_creation_world_facts(db, project_id, project_bible, world_rules, worldview)
        db.flush()
        self._link_creation_graph(db, project_id, character, entities, facts, worldview)
        output = {
            "project_seed": seed,
            "core_conflict_system": state.get("core_conflict_system", {}),
            "novel_constitution": state.get("novel_constitution", {}),
            "constitution_review": state.get("constitution_review", {}),
            "canon_candidates": candidates,
        }
        self._record_agent_run(db, job, "canon_curator", output, {"session_id": session_id, "project_seed": seed})
        version = self._snapshot(
            db,
            project_id,
            None,
            job.id,
            "canon_curator",
            "creation_session_canon",
            dumps(output),
            request.user_note or "解耦创作 Star 确认入库",
        )
        session.status = "committed"
        session.current_step = "committed"
        state["confirmed_canon"] = output
        self._save_creation_session_state(session, state)
        result = {
            "project": serialize_project(project),
            "story_bible": serialize_story_bible(story_bible),
            "character": serialize_character(character),
            "entities": [serialize_story_entity(item) for item in entities],
            "world_facts": [serialize_world_fact(item) for item in facts],
            "version": serialize_version_snapshot(version),
            "session": serialize_creation_session(session),
        }
        self._finish_job(db, job, result)
        db.commit()
        db.refresh(session)
        result["session"] = serialize_creation_session(session)
        result["job"] = serialize_job(job)
        return result

    def generate_story_bible(self, db: Session, project_id: str, request: GenerateStoryBibleRequest) -> dict:
        project = self._project(db, project_id)
        story_bible = self._story_bible(db, project_id)
        job = self._create_job(db, project_id, None, "generate_story_bible", request.model, {"initial_idea": request.initial_idea})
        state = self._state_from_project(db, project, job.id)
        state.requested_model = request.model
        state.agent_model_configs = self._model_configs_for_workflow(db, "initialization")
        state.initial_idea = request.initial_idea or project.initial_idea or project.premise
        result = chapter_writing_service.run_initialization(state)
        self._record_agent_run(
            db,
            job,
            "chief_architect",
            self._with_llm_meta(
                {
                    "core_conflict_system": result.core_conflict_system,
                    "novel_constitution": result.novel_constitution,
                    "constitution_review": result.constitution_review,
                    "story_bible": result.story_bible,
                },
                result,
                "chief_architect",
            ),
            {"project": serialize_project(project)},
        )
        self._record_agent_run(db, job, "canon_curator", self._with_llm_meta(result.canon_updates, result, "canon_curator"), {"story_bible": result.story_bible})

        story_bible.version += 1
        story_bible.world_setting = result.story_bible.get("world_setting", story_bible.world_setting)
        story_bible.main_conflict = result.story_bible.get("main_conflict", story_bible.main_conflict)
        story_bible.themes_json = dumps(result.story_bible.get("themes", []))
        story_bible.style_guide = result.story_bible.get("style_guide", story_bible.style_guide)
        story_bible.narrative_pov = result.story_bible.get("narrative_pov", story_bible.narrative_pov)
        story_bible.forbidden_elements_json = dumps(result.story_bible.get("forbidden_elements", []))
        story_bible.continuity_rules_json = dumps(result.story_bible.get("continuity_rules", []))
        self._upsert_workflow_characters(db, project_id, result.characters, job.id)
        self._upsert_world_fact(
            db,
            project_id,
            "history",
            "总策划生成的世界观",
            story_bible.world_setting,
            "core",
            90,
            0.85,
            None,
        )
        self._snapshot(db, project_id, None, job.id, "chief_architect", "story_bible", dumps(result.story_bible), "初始化项目工作流")
        self._finish_job(
            db,
            job,
            {
                "core_conflict_system": result.core_conflict_system,
                "novel_constitution": result.novel_constitution,
                "constitution_review": result.constitution_review,
                "story_bible": serialize_story_bible(story_bible),
                "canon_updates": result.canon_updates,
            },
        )
        db.commit()
        return {
            "job": serialize_job(job),
            "core_conflict_system": result.core_conflict_system,
            "novel_constitution": result.novel_constitution,
            "constitution_review": result.constitution_review,
            "story_bible": serialize_story_bible(story_bible),
            "canon_updates": result.canon_updates,
        }

    def plan_chapters(self, db: Session, project_id: str, request: PlanChaptersRequest, background_tasks: Any | None = None) -> dict:
        project = self._project(db, project_id)
        existing = (
            db.query(models.GenerationJob)
            .filter(models.GenerationJob.project_id == project_id, models.GenerationJob.idempotency_key == request.idempotency_key)
            .first()
        )
        if existing:
            return {"job": serialize_job(existing)}
        end = request.start_chapter_no + request.chapter_count - 1
        existing_chapters = (
            db.query(models.Chapter)
            .filter(models.Chapter.project_id == project_id, models.Chapter.chapter_no >= request.start_chapter_no, models.Chapter.chapter_no <= end)
            .all()
        )
        if existing_chapters and not request.overwrite_existing:
            raise _conflict("章节范围已存在，且 overwrite_existing=false")
        job = self._create_job(
            db,
            project_id,
            None,
            "plan_chapters",
            request.model,
            request.model_dump(),
            request.idempotency_key,
            total_steps=len(OUTLINE_AGENT_SEQUENCE) + len(OUTLINE_SWARM_AGENT_NAMES),
            queued=request.async_mode,
        )
        if request.async_mode:
            db.commit()
            db.refresh(job)
            if background_tasks is not None:
                background_tasks.add_task(self.run_plan_chapters_job, job.id)
            return {"job": serialize_job(job), "chapters": [], "outline_plan": None}

        return self._execute_plan_chapters(db, project, request, job)

    def generate_book_outline(self, db: Session, project_id: str, request: BookOutlineGenerateRequest, background_tasks: Any | None = None) -> dict:
        project = self._project(db, project_id)
        existing = (
            db.query(models.GenerationJob)
            .filter(models.GenerationJob.project_id == project_id, models.GenerationJob.idempotency_key == request.idempotency_key)
            .first()
        )
        if existing:
            result = loads(existing.result_json, {}) if existing.result_json else {}
            return {"job": serialize_job(existing), "outline_plan": result.get("outline_plan")}
        total_steps = len(BOOK_OUTLINE_AGENT_SEQUENCE) + (len(BOOK_OUTLINE_SWARM_AGENT_NAMES) if request.use_topology_inference else 0)
        job = self._create_job(
            db,
            project_id,
            None,
            "book_outline",
            request.model,
            request.model_dump(),
            request.idempotency_key,
            total_steps=total_steps,
            queued=request.async_mode,
        )
        if request.async_mode:
            outline_plan = self._build_initial_book_outline_plan(db, project, request)
            job.result_json = dumps({"outline_plan": outline_plan, "chapters": [], "status": "skeleton"})
            db.commit()
            db.refresh(job)
            if background_tasks is not None:
                background_tasks.add_task(self.run_book_outline_job, job.id)
            return {"job": serialize_job(job), "outline_plan": outline_plan}
        return self._execute_book_outline(db, project, request, job)

    def run_book_outline_job(self, job_id: str) -> None:
        db = SessionLocal()
        try:
            job = db.get(models.GenerationJob, job_id)
            if job is None or job.status == "succeeded":
                return
            request = self._book_outline_request_from_job(job)
            project = self._project(db, job.project_id)
            self._start_job(db, job)
            self._execute_book_outline(db, project, request, job)
        except Exception as exc:  # pragma: no cover - API level verifies failed state
            db.rollback()
            job = db.get(models.GenerationJob, job_id)
            if job is not None:
                self._fail_job(db, job, exc)
                db.commit()
        finally:
            db.close()

    def commit_book_outline(self, db: Session, project_id: str, request: BookOutlineCommitRequest) -> dict:
        project = self._project(db, project_id)
        outline_plan = request.outline_plan
        if request.job_id:
            job = db.get(models.GenerationJob, request.job_id)
            if job is None or job.project_id != project_id:
                raise _not_found("大纲推演任务不存在")
            result = loads(job.result_json, {}) if job.result_json else {}
            outline_plan = result.get("outline_plan") or outline_plan
        if not outline_plan:
            raise _bad_request("没有可写入的大纲结果")
        self._apply_book_outline(db, project, outline_plan)
        db.commit()
        story_bible = self._story_bible(db, project_id)
        volumes = (
            db.query(models.Volume)
            .filter(models.Volume.project_id == project_id)
            .order_by(models.Volume.sort_order.asc(), models.Volume.volume_no.asc())
            .all()
        )
        return {
            "project": serialize_project(project),
            "story_bible": serialize_story_bible(story_bible),
            "volumes": [serialize_volume(item) for item in volumes],
            "outline_plan": outline_plan,
        }

    def generate_chapter_outlines_batch(self, db: Session, project_id: str, request: ChapterOutlineBatchGenerateRequest, background_tasks: Any | None = None) -> dict:
        self._project(db, project_id)
        existing = (
            db.query(models.GenerationJob)
            .filter(models.GenerationJob.project_id == project_id, models.GenerationJob.idempotency_key == request.idempotency_key)
            .first()
        )
        if existing:
            result = loads(existing.result_json, {}) if existing.result_json else {}
            return {"job": serialize_job(existing), "chapter_outlines": result.get("chapter_outlines", [])}
        self._ensure_batch_can_generate(db, project_id, request)
        job = self._create_job(
            db,
            project_id,
            None,
            "chapter_outline_batch",
            request.model,
            request.model_dump(),
            request.idempotency_key,
            total_steps=len(CHAPTER_OUTLINE_AGENT_SEQUENCE),
            queued=request.async_mode,
        )
        if request.async_mode:
            db.commit()
            db.refresh(job)
            if background_tasks is not None:
                background_tasks.add_task(self.run_chapter_outline_batch_job, job.id)
            return {"job": serialize_job(job), "chapter_outlines": []}
        project = self._project(db, project_id)
        return self._execute_chapter_outline_batch(db, project, request, job)

    def run_chapter_outline_batch_job(self, job_id: str) -> None:
        db = SessionLocal()
        try:
            job = db.get(models.GenerationJob, job_id)
            if job is None or job.status == "succeeded":
                return
            request = self._chapter_outline_batch_request_from_job(job)
            project = self._project(db, job.project_id)
            self._start_job(db, job)
            self._execute_chapter_outline_batch(db, project, request, job)
        except Exception as exc:  # pragma: no cover - API level verifies failed state
            db.rollback()
            job = db.get(models.GenerationJob, job_id)
            if job is not None:
                self._fail_job(db, job, exc)
                db.commit()
        finally:
            db.close()

    def commit_chapter_outlines(self, db: Session, project_id: str, request: ChapterOutlineCommitRequest) -> dict:
        project = self._project(db, project_id)
        chapter_outlines = request.chapter_outlines
        overwrite_existing = request.overwrite_existing
        job_id: str | None = None
        if request.job_id:
            job = db.get(models.GenerationJob, request.job_id)
            if job is None or job.project_id != project_id:
                raise _not_found("章纲生成任务不存在")
            result = loads(job.result_json, {}) if job.result_json else {}
            chapter_outlines = result.get("chapter_outlines") or chapter_outlines
            overwrite_existing = bool(loads(job.request_json, {}).get("overwrite_existing", overwrite_existing))
            job_id = job.id
        if not chapter_outlines:
            raise _bad_request("没有可写入的章纲结果")
        chapters = self._persist_chapter_outline_candidates(db, project, chapter_outlines, job_id, overwrite_existing)
        db.commit()
        for chapter in chapters:
            db.refresh(chapter)
        return {"chapters": [serialize_chapter(chapter) for chapter in chapters], "chapter_outlines": chapter_outlines}

    def run_plan_chapters_job(self, job_id: str) -> None:
        db = SessionLocal()
        try:
            job = db.get(models.GenerationJob, job_id)
            if job is None or job.status == "succeeded":
                return
            request = self._plan_request_from_job(job)
            project = self._project(db, job.project_id)
            self._start_job(db, job)
            self._execute_plan_chapters(db, project, request, job)
        except Exception as exc:  # pragma: no cover - exercised through API level failure state
            db.rollback()
            job = db.get(models.GenerationJob, job_id)
            if job is not None:
                self._fail_job(db, job, exc)
                db.commit()
        finally:
            db.close()

    def _execute_plan_chapters(self, db: Session, project: models.Project, request: PlanChaptersRequest, job: models.GenerationJob) -> dict:
        project_id = project.id
        state = self._state_from_project(db, project, job.id)
        state.requested_model = request.model
        state.agent_model_configs = self._model_configs_for_workflow(db, "chapter_planning")
        state.current_chapter = request.start_chapter_no
        state.target_chapters = request.chapter_count
        result = chapter_writing_service.run_chapter_plan(state)
        outline_plan = self._build_long_novel_outline_plan(db, project, request, state)
        project_snapshot = serialize_project(project)
        db.commit()
        total_steps = len(OUTLINE_AGENT_SEQUENCE) + len(OUTLINE_SWARM_AGENT_NAMES)

        def on_outline_agent(agent_name: str, completed_steps: int) -> None:
            self._update_job_progress(db, job, agent_name, completed_steps, total_steps, f"{agent_name} 已完成")

        outline_plan = self._run_outline_agents_with_llm(db, project_snapshot, request, outline_plan, progress_callback=on_outline_agent)
        project = self._project(db, project_id)

        def on_swarm_progress(swarm_state: dict[str, Any]) -> None:
            completed_steps = min(total_steps - 1, len(OUTLINE_AGENT_SEQUENCE) + int(swarm_state.get("iteration_count") or 0))
            active_agent = str(swarm_state.get("active_agent") or "outline_swarm")
            self._update_job_progress(db, job, f"outline_swarm/{active_agent}", completed_steps, total_steps, f"{active_agent} 正在推演")

        outline_plan = self._attach_outline_swarm_plan(db, project, request, outline_plan, progress_callback=on_swarm_progress)
        planned_chapters = outline_plan["chapters"]
        if request.target_words is not None:
            project.target_words = request.target_words
        if request.volume_count is not None and request.chapters_per_volume is not None:
            project.planned_chapter_count = request.volume_count * request.chapters_per_volume
        if request.chapter_word_target is not None:
            project.chapter_word_target = request.chapter_word_target
        self._sync_outline_volumes(db, project, outline_plan["10卷单元总表"])
        outline_agent_outputs = outline_plan.get("agent_outputs", {})
        previous_outputs: list[str] = []
        for agent_name in OUTLINE_AGENT_SEQUENCE:
            self._record_agent_run(
                db,
                job,
                agent_name,
                outline_agent_outputs.get(agent_name, {}),
                {
                    "request": request.model_dump(),
                    "structured_prompt": outline_plan["structured_prompt"],
                    "story_state": outline_plan.get("story_state", {}),
                    "previous_agents": previous_outputs,
                },
            )
            previous_outputs.append(agent_name)
        self._record_outline_swarm_agent_runs(db, job, request, outline_plan)
        chapters = self._persist_planned_chapters(db, project, planned_chapters, request, job.id)
        self._finish_job(
            db,
            job,
            {
                "chapters": [serialize_chapter(chapter) for chapter in chapters],
                "outline_plan": {key: value for key, value in outline_plan.items() if key != "chapters"},
                "canon_updates": result.canon_updates,
            },
        )
        db.commit()
        return {
            "job": serialize_job(job),
            "chapters": [serialize_chapter(chapter) for chapter in chapters],
            "outline_plan": {key: value for key, value in outline_plan.items() if key != "chapters"},
        }

    def _execute_book_outline(self, db: Session, project: models.Project, request: BookOutlineGenerateRequest, job: models.GenerationJob) -> dict:
        plan_request = self._book_outline_to_plan_request(project, request)
        state = self._state_from_project(db, project, job.id)
        state.requested_model = request.model
        state.agent_model_configs = self._model_configs_for_workflow(db, "outline_generation")
        state.current_chapter = 1
        state.target_chapters = project.planned_chapter_count
        outline_plan = self._build_long_novel_outline_plan(db, project, plan_request, state)
        outline_plan = self._normalize_book_outline_plan(project, plan_request, outline_plan)
        project_snapshot = serialize_project(project)
        db.commit()
        total_steps = len(BOOK_OUTLINE_AGENT_SEQUENCE) + (len(BOOK_OUTLINE_SWARM_AGENT_NAMES) if request.use_topology_inference else 0)

        def on_outline_agent(agent_name: str, completed_steps: int) -> None:
            self._update_job_progress(db, job, agent_name, completed_steps, total_steps, f"{agent_name} 已完成")

        outline_plan = self._run_outline_agents_with_llm(
            db,
            project_snapshot,
            plan_request,
            outline_plan,
            agent_sequence=BOOK_OUTLINE_AGENT_SEQUENCE,
            progress_callback=on_outline_agent,
        )
        outline_plan = self._normalize_book_outline_plan(project, plan_request, outline_plan)
        outline_plan["revision_route"] = self._build_outline_revision_route(outline_plan)
        project = self._project(db, project.id)

        if request.use_topology_inference:
            def on_swarm_progress(swarm_state: dict[str, Any]) -> None:
                completed_steps = min(total_steps - 1, len(BOOK_OUTLINE_AGENT_SEQUENCE) + int(swarm_state.get("iteration_count") or 0))
                active_agent = str(swarm_state.get("active_agent") or "outline_swarm")
                if active_agent == "BeatControllerAgent":
                    active_agent = "ForeshadowingAgent"
                self._update_job_progress(db, job, f"outline_swarm/{active_agent}", completed_steps, total_steps, f"{active_agent} 正在推演")

            outline_plan = self._attach_outline_swarm_plan(db, project, plan_request, outline_plan, generation_kind="book_outline", progress_callback=on_swarm_progress)
        outline_plan = self._normalize_book_outline_plan(project, plan_request, outline_plan)
        outline_plan["revision_route"] = self._build_outline_revision_route(outline_plan)
        outline_plan["change_summary"] = self._build_book_outline_change_summary(db, project, outline_plan)
        outline_plan["outline_topology"] = self._build_outline_topology(
            generation_kind="book_outline",
            mode="topology" if request.use_topology_inference else "linear",
            agent_sequence=BOOK_OUTLINE_AGENT_SEQUENCE,
            outline_plan=outline_plan,
            swarm_result=outline_plan.get("outline_swarm") if request.use_topology_inference else None,
            planned_swarm_agents=BOOK_OUTLINE_SWARM_AGENT_NAMES if request.use_topology_inference else (),
        )
        outline_agent_outputs = outline_plan.get("agent_outputs", {})
        previous_outputs: list[str] = []
        for agent_name in BOOK_OUTLINE_AGENT_SEQUENCE:
            self._record_agent_run(
                db,
                job,
                agent_name,
                outline_agent_outputs.get(agent_name, {}),
                {
                    "request": request.model_dump(),
                    "structured_prompt": outline_plan.get("structured_prompt", {}),
                    "story_state": outline_plan.get("story_state", {}),
                    "previous_agents": previous_outputs,
                },
            )
            previous_outputs.append(agent_name)
        if request.use_topology_inference:
            self._record_outline_swarm_agent_runs(db, job, plan_request, outline_plan)
        self._finish_job(db, job, {"outline_plan": outline_plan, "chapters": []})
        db.commit()
        return {"job": serialize_job(job), "outline_plan": outline_plan}

    def _execute_chapter_outline_batch(self, db: Session, project: models.Project, request: ChapterOutlineBatchGenerateRequest, job: models.GenerationJob) -> dict:
        self._ensure_batch_can_generate(db, project.id, request)
        chapter_outlines = self._build_chapter_outline_candidates(db, project, request)
        context = self._chapter_outline_batch_context(db, project, request, chapter_outlines)
        topology_instruction = (
            "拓扑推演开启：请把章纲候选按依赖、冲突、伏笔、回收、风险和审查关系组织；保持与线性模式相同的章纲字段与章节数量。"
            if request.use_topology_inference
            else "拓扑推演关闭：请按线性章纲生产链生成；保持与拓扑模式相同的章纲字段与章节数量。"
        )
        total_steps = len(CHAPTER_OUTLINE_AGENT_SEQUENCE)
        payload: dict[str, Any] = {"chapter_beats": chapter_outlines}
        previous_outputs: list[dict[str, Any]] = []
        for index, agent_name in enumerate(CHAPTER_OUTLINE_AGENT_SEQUENCE, start=1):
            spec = AGENT_SPECS_BY_NAME[agent_name]
            fallback = payload if agent_name == "beat_control" else {"chapter_beats": chapter_outlines}
            output, meta = call_agent_json(
                llm_client=llm_client,
                agent_name=agent_name,
                role=spec.role,
                system_prompt=spec.prompt,
                task=f"基于已确认总纲、卷纲和正典上下文，生成或审查本批章纲候选。不要改写总纲和卷纲。{topology_instruction}",
                context={**context, "topology_mode": "topology" if request.use_topology_inference else "linear", "previous_agent_outputs": previous_outputs},
                fallback=fallback,
                model=self._configured_model_for_agent(db, "chapter_planning", agent_name, request.model),
            )
            output["_llm"] = meta
            if agent_name == "beat_control":
                candidate = output.get("chapter_beats")
                if isinstance(candidate, list) and candidate:
                    chapter_outlines = [self._normalize_chapter_outline_item(item, project, request) for item in candidate if isinstance(item, dict)]
                    payload = {"chapter_beats": chapter_outlines}
            previous_outputs.append({"agent_name": agent_name, "output": output})
            self._record_agent_run(db, job, agent_name, output, {"request": request.model_dump(), "context": {**context, "topology_mode": "topology" if request.use_topology_inference else "linear"}})
            self._update_job_progress(db, job, agent_name, index, total_steps, f"{agent_name} 已完成")
        outline_plan = {
            "generation_kind": "chapter_outline_batch",
            "chapter_outlines": chapter_outlines,
            "batch_request": request.model_dump(),
        }
        outline_plan["outline_topology"] = self._build_outline_topology(
            generation_kind="chapter_outline_batch",
            mode="topology" if request.use_topology_inference else "linear",
            agent_sequence=CHAPTER_OUTLINE_AGENT_SEQUENCE,
            outline_plan=outline_plan,
        )
        result = {
            "generation_kind": "chapter_outline_batch",
            "chapter_outlines": chapter_outlines,
            "outline_plan": outline_plan,
        }
        self._finish_job(db, job, result)
        db.commit()
        return {"job": serialize_job(job), "chapter_outlines": chapter_outlines, "outline_plan": result["outline_plan"]}

    def list_chapters(self, db: Session, project_id: str) -> dict:
        self._project(db, project_id)
        chapters = (
            db.query(models.Chapter)
            .filter(models.Chapter.project_id == project_id, models.Chapter.deleted_at.is_(None))
            .order_by(models.Chapter.sort_order.asc(), models.Chapter.chapter_no.asc())
            .all()
        )
        return {"chapters": [serialize_chapter(chapter) for chapter in chapters]}

    def get_chapter(self, db: Session, project_id: str, chapter_id: str) -> dict:
        chapter = self._chapter(db, project_id, chapter_id)
        return {"chapter": serialize_chapter(chapter)}

    def update_chapter(self, db: Session, project_id: str, chapter_id: str, request: UpdateChapterRequest) -> dict:
        chapter = self._chapter(db, project_id, chapter_id)
        updates = request.model_dump(exclude_unset=True)
        if "final_text" in updates and updates["final_text"] != chapter.final_text:
            self._snapshot(
                db,
                project_id,
                chapter_id,
                None,
                "user",
                "chapter",
                chapter.final_text or chapter.draft_text or chapter.outline,
                "手动保存前自动快照",
            )
        for field, value in updates.items():
            if value is None:
                continue
            if field == "emotional_beats":
                chapter.emotional_beats_json = dumps(value)
            elif hasattr(chapter, field):
                setattr(chapter, field, value)
        chapter.word_count = len((chapter.final_text or chapter.draft_text).replace("\n", ""))
        db.commit()
        db.refresh(chapter)
        return {"chapter": serialize_chapter(chapter)}

    def draft_chapter(self, db: Session, project_id: str, chapter_id: str, request: DraftChapterRequest) -> dict:
        project = self._project(db, project_id)
        chapter = self._chapter(db, project_id, chapter_id)
        idem = request.idempotency_key or f"draft:{chapter_id}:{request.mode}:{len(request.user_instruction)}"
        existing = (
            db.query(models.GenerationJob)
            .filter(models.GenerationJob.project_id == project_id, models.GenerationJob.idempotency_key == idem)
            .first()
        )
        if existing:
            return {"job": serialize_job(existing)}
        job = self._create_job(db, project_id, chapter_id, "draft_chapter", request.model, request.model_dump(), idem, total_steps=14)
        state = self._state_from_project(db, project, job.id)
        state.requested_model = request.model
        state.agent_model_configs = self._model_configs_for_workflow(db, "chapter_draft")
        state.current_chapter = chapter.chapter_no
        state.current_chapter_outline = serialize_chapter(chapter)
        state.canon_context = self.build_canon_context(db, project_id, chapter_id)["canon_context"]
        result = chapter_writing_service.run_chapter_draft(state)
        for agent_name, payload in [
            ("canon_context", {"canon_context": result.canon_context}),
            ("chapter_card", {"chapter_card": result.chapter_card}),
            ("scene_outline", {"scene_outline": result.scene_outline}),
            ("plot_narrator", {"plot_draft": result.plot_draft}),
            ("dialogue_writer", {"dialogue_draft": result.dialogue_draft}),
            ("environment_writer", {"environment_draft": result.environment_draft}),
            ("integrator", {"integrated_draft": result.integrated_draft, "chapter_summary": result.chapter_summary}),
            ("reviewer", {"review_notes": result.review_notes, "health_check_report": result.health_check_report}),
            ("fact_checker", result.fact_check_report),
            ("draft_rewrite", {"integrated_draft": result.integrated_draft}),
            ("quality_gate", result.quality_gate),
            ("style_unifier", {"style_polished_text": result.style_polished_text, "final_chapter_text": result.final_chapter_text}),
            ("narrative_ledger", {"narrative_ledger": result.narrative_ledger}),
            ("canon_curator", result.candidate_canon_updates or result.canon_updates),
        ]:
            payload = self._with_llm_meta(payload, result, agent_name)
            self._record_agent_run(db, job, agent_name, payload, {"chapter": serialize_chapter(chapter)})
            self._snapshot(db, project_id, chapter_id, job.id, agent_name, "chapter", json.dumps(payload, ensure_ascii=False), "")
        chapter.draft_text = result.style_polished_text
        chapter.final_text = result.final_chapter_text
        chapter.summary = result.chapter_summary
        chapter.revision_notes = dumps(result.review_notes)
        chapter.status = "drafted"
        chapter.word_count = len(result.final_chapter_text.replace("\n", ""))
        self._persist_canon_updates(db, project_id, chapter_id, result.canon_updates)
        output = models.GenerationOutput(
            id=generate_id("out"),
            project_id=project_id,
            chapter_id=chapter_id,
            job_id=job.id,
            output_type="chapter_draft",
            title=chapter.title,
            content=result.final_chapter_text,
            summary=result.chapter_summary,
            metadata_json=dumps(
                {
                    "chapter_card": result.chapter_card,
                    "scene_outline": result.scene_outline,
                    "review_notes": result.review_notes,
                    "health_check_report": result.health_check_report,
                    "fact_check_report": result.fact_check_report,
                    "narrative_ledger": result.narrative_ledger,
                    "canon_updates": result.canon_updates,
                }
            ),
        )
        db.add(output)
        self._finish_job(
            db,
            job,
            {
                "chapter": serialize_chapter(chapter),
                "draft_text": result.style_polished_text,
                "polished_text": result.final_chapter_text,
                "continuity_issues": result.continuity_issues,
                "chapter_card": result.chapter_card,
                "scene_outline": result.scene_outline,
                "narrative_ledger": result.narrative_ledger,
                "canon_updates": result.canon_updates,
                "updated_characters": result.canon_updates.get("character_updates", []),
                "updated_entities": result.canon_updates.get("entity_updates", []),
                "updated_world_facts": result.canon_updates.get("world_fact_updates", []),
                "updated_graph_edges": result.canon_updates.get("relation_updates", []),
            },
        )
        db.commit()
        return {"job": serialize_job(job), "chapter": serialize_chapter(chapter)}

    def rewrite_chapter(self, db: Session, project_id: str, chapter_id: str, request: RewriteChapterRequest) -> dict:
        return self.draft_chapter(db, project_id, chapter_id, DraftChapterRequest(mode="rewrite", user_instruction=request.instruction, model=request.model))

    def partial_rewrite_chapter(self, db: Session, project_id: str, chapter_id: str, request: PartialRewriteRequest) -> dict:
        instruction = f"只改写以下片段：{request.selection}\n要求：{request.instruction}"
        return self.draft_chapter(db, project_id, chapter_id, DraftChapterRequest(mode="partial_rewrite", user_instruction=instruction, model=request.model))

    def stream_chapter_chat(self, db: Session, project_id: str, chapter_id: str, request: ChapterChatRequest) -> Iterator[str]:
        project = self._project(db, project_id)
        chapter = self._chapter(db, project_id, chapter_id)
        if request.selection_start is not None and request.selection_end is not None and request.selection_end < request.selection_start:
            raise _bad_request("选区结束位置不能小于开始位置")
        canon_context = self.build_canon_context(db, project_id, chapter_id)["canon_context"]
        source_text = request.chapter_text or chapter.final_text or chapter.draft_text or chapter.outline
        selected_text = request.selected_text.strip()
        system_prompt, user_prompt = self._chapter_chat_prompts(project, chapter, canon_context, source_text, selected_text, request)
        selection = {
            "start": request.selection_start,
            "end": request.selection_end,
            "has_selection": bool(selected_text),
        }

        def events() -> Iterator[str]:
            yield self._sse_event(
                "meta",
                {
                    "type": "meta",
                    "provider": LLMProviderResolver(get_settings()).resolve(request.model).provider,
                    "model": LLMProviderResolver(get_settings()).resolve(request.model).model,
                    "selection": selection,
                    "message": "已读取当前章节、选区和 canon_context，正在生成修改建议。",
                },
            )
            result = llm_client.generate(system_prompt, user_prompt, request.model)
            parsed = self._parse_chapter_chat_payload(result.content)
            if not result.used_remote_model or not parsed.get("replacement"):
                parsed = self._local_chapter_chat_payload(selected_text or source_text, request)
            replacement = str(parsed.get("replacement", "")).strip()
            reasoning = str(parsed.get("reasoning", "")).strip() or "已基于当前章节上下文生成局部修改建议。"
            checklist = parsed.get("checklist")
            if not isinstance(checklist, list):
                checklist = ["保持事件不漂移", "保留人物视角", "等待用户确认后再写入正文"]
            for chunk in self._chunk_text(replacement, 36):
                yield self._sse_event("delta", {"type": "delta", "text": chunk})
            yield self._sse_event(
                "result",
                {
                    "type": "result",
                    "replacement": replacement,
                    "reasoning": reasoning,
                    "checklist": [str(item) for item in checklist][:6],
                    "selection": selection,
                    "provider": result.provider,
                    "model": result.model,
                    "used_remote_model": result.used_remote_model,
                },
            )
            yield self._sse_event("done", {"type": "done"})

        return events()

    def get_job(self, db: Session, job_id: str) -> dict:
        job = db.get(models.GenerationJob, job_id)
        if job is None:
            raise _not_found("任务不存在")
        return {"job": serialize_job(job)}

    def get_agent_runs(self, db: Session, job_id: str) -> dict:
        runs = db.query(models.AgentRun).filter(models.AgentRun.job_id == job_id).order_by(models.AgentRun.created_at.asc()).all()
        return {"agent_runs": [serialize_agent_run(run) for run in runs]}

    def retry_job(self, db: Session, job_id: str) -> dict:
        job = db.get(models.GenerationJob, job_id)
        if job is None:
            raise _not_found("任务不存在")
        job.status = "queued"
        job.error_message = None
        job.progress_json = dumps({"current_step": "queued", "total_steps": 1, "completed_steps": 0, "message": "任务已重新入队"})
        db.commit()
        return {"job": serialize_job(job)}

    def control_job(self, db: Session, request: JobControlRequest, action: str) -> dict:
        job = db.get(models.GenerationJob, request.job_id)
        if job is None:
            raise _not_found("任务不存在")
        if action == "pause":
            job.status = "paused"
        elif action == "resume":
            job.status = "queued"
        elif action == "cancel":
            job.status = "cancelled"
            job.cancel_requested = 1
            job.cancel_reason = request.reason
            job.finished_at = utcnow()
        db.commit()
        return {"job": serialize_job(job)}

    def list_llm_models(self) -> dict:
        settings = get_settings()
        resolver = LLMProviderResolver(settings)
        resolved = resolver.resolve()
        configured = bool(resolved.api_key)
        payload = catalog_payload(default_model=resolved.model, default_provider=resolved.provider)
        providers = []
        for provider in payload["providers"]:
            provider_config = resolver.resolve(f"{provider['id']}:{provider['default_model']}")
            providers.append(
                {
                    **provider,
                    "configured": bool(provider_config.api_key),
                    "active": provider_config.provider == resolved.provider,
                }
            )
        active_provider = next((provider for provider in providers if provider["active"]), None)
        api_key_env = active_provider["api_key_env"] if active_provider else "LLM_API_KEY"
        if resolved.provider == "qwen":
            api_key_env = "QWEN_API_KEY / DASHSCOPE_API_KEY / LLM_API_KEY"
        remote_note = "远程模型调用会失败" if settings.llm_require_remote else "将使用本地降级草案"
        payload.update(
            {
                "configured": configured,
                "default_provider_configured": configured,
                "require_remote": settings.llm_require_remote,
                "configuration_warning": ""
                if configured
                else f"LLM 未配置：当前默认 {resolved.provider}/{resolved.model} 未检测到 API Key（{api_key_env}），{remote_note}。",
                "providers": providers,
            }
        )
        return payload

    def _serialize_agent_model_config(self, row: models.AgentModelConfig) -> dict[str, Any]:
        return {
            "id": row.id,
            "workflow_id": row.workflow_id,
            "agent_name": row.agent_name,
            "provider": row.provider,
            "model": row.model,
            "metadata": loads(row.metadata_json, {}),
            "created_at": isoformat(row.created_at),
            "updated_at": isoformat(row.updated_at),
        }

    def _agent_model_config_rows(self, db: Session) -> list[models.AgentModelConfig]:
        query = db.query(models.AgentModelConfig)
        if not hasattr(query, "order_by"):
            return []
        return query.order_by(models.AgentModelConfig.workflow_id.asc(), models.AgentModelConfig.agent_name.asc()).all()

    def _agent_model_config_map(self, db: Session) -> dict[tuple[str, str], models.AgentModelConfig]:
        return {(row.workflow_id, row.agent_name): row for row in self._agent_model_config_rows(db)}

    def _agent_model_configs_by_agent(self, db: Session) -> dict[str, dict[str, dict[str, Any]]]:
        grouped: dict[str, dict[str, dict[str, Any]]] = {}
        for row in self._agent_model_config_rows(db):
            grouped.setdefault(row.agent_name, {})[row.workflow_id] = self._serialize_agent_model_config(row)
        return grouped

    def list_agent_model_configs(self, db: Session) -> dict:
        return {"configs": [self._serialize_agent_model_config(row) for row in self._agent_model_config_rows(db)]}

    def update_agent_model_config(self, db: Session, request: AgentModelConfigRequest) -> dict:
        if request.agent_name not in AGENT_SPECS_BY_NAME:
            raise _not_found("Agent 不存在")
        workflow_ids = {workflow["id"] for workflow in self.list_workflows()["workflows"]}
        if request.workflow_id not in workflow_ids:
            raise _not_found("工作流不存在")
        provider_config = LLMProviderResolver(get_settings()).resolve(request.model)
        model_to_store = request.model if ":" in request.model else provider_config.model
        row = (
            db.query(models.AgentModelConfig)
            .filter(models.AgentModelConfig.workflow_id == request.workflow_id, models.AgentModelConfig.agent_name == request.agent_name)
            .first()
        )
        if row is None:
            row = models.AgentModelConfig(
                id=generate_id("amc"),
                workflow_id=request.workflow_id,
                agent_name=request.agent_name,
                provider=provider_config.provider,
                model=model_to_store,
                metadata_json=dumps({"requested_model": request.model}),
            )
            db.add(row)
        else:
            row.provider = provider_config.provider
            row.model = model_to_store
            row.metadata_json = dumps({"requested_model": request.model})
            row.updated_at = utcnow()
        db.commit()
        db.refresh(row)
        return {"config": self._serialize_agent_model_config(row)}

    def delete_agent_model_config(self, db: Session, workflow_id: str, agent_name: str) -> dict:
        row = (
            db.query(models.AgentModelConfig)
            .filter(models.AgentModelConfig.workflow_id == workflow_id, models.AgentModelConfig.agent_name == agent_name)
            .first()
        )
        if row is None:
            return {"deleted": False, "workflow_id": workflow_id, "agent_name": agent_name}
        db.delete(row)
        db.commit()
        return {"deleted": True, "workflow_id": workflow_id, "agent_name": agent_name}

    def _configured_model_for_agent(self, db: Session, workflow_id: str, agent_name: str, requested_model: str | None = None) -> str | None:
        if requested_model:
            return requested_model
        row = (
            db.query(models.AgentModelConfig.model)
            .filter(models.AgentModelConfig.workflow_id == workflow_id, models.AgentModelConfig.agent_name == agent_name)
            .first()
        )
        return row[0] if row else None

    def _model_configs_for_workflow(self, db: Session, workflow_id: str) -> dict[str, str]:
        rows = db.query(models.AgentModelConfig).filter(models.AgentModelConfig.workflow_id == workflow_id).all()
        return {row.agent_name: row.model for row in rows}

    def list_agents(self, db: Session) -> dict:
        templates = {template.agent_name: template for template in db.query(models.PromptTemplate).filter(models.PromptTemplate.is_active == 1).all()}
        model_configs = self._agent_model_configs_by_agent(db)
        agents = []
        for spec in DEFAULT_AGENT_SPECS:
            template = templates.get(spec.name)
            agents.append(self._serialize_agent_config(spec, template, model_configs.get(spec.name, {})))
        return {"agents": agents}

    def _serialize_agent_config(self, spec: Any, template: models.PromptTemplate | None = None, model_configs: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
        prompt_ids = list(AGENT_PROMPT_BINDINGS.get(spec.name, ()))
        return {
            "name": spec.name,
            "role": spec.role,
            "order": spec.order,
            "prompt": template.prompt if template else spec.prompt,
            "default_prompt": spec.prompt,
            "is_custom": template is not None,
            "active_template_id": template.id if template else None,
            "prompt_ids": prompt_ids,
            "prompt_titles": {prompt_id: get_prompt_entry(prompt_id).title for prompt_id in prompt_ids},
            "model_configs": model_configs or {},
        }

    def _workflow_runtime_metadata(self, workflow_id: str) -> dict[str, Any]:
        active: dict[str, tuple[list[str], str]] = {
            "initialization": (
                ["/api/projects/{project_id}/story-bible/generate"],
                "已接入 chapter_writing_service.run_initialization，用于故事圣经生成。",
            ),
            "outline_generation": (
                ["/api/projects/{project_id}/chapters/plan", "/api/projects/{project_id}/outline/book/generate"],
                "已接入 OUTLINE_AGENT_SEQUENCE 和 outline_swarm，用于旧章节规划与新版总纲/卷纲生成。",
            ),
            "chapter_planning": (
                ["/api/projects/{project_id}/chapters/plan"],
                "已接入 chapter_writing_service.run_chapter_plan，并作为章节规划前置链路。",
            ),
            "chapter_draft": (
                ["/api/projects/{project_id}/chapters/{chapter_id}/draft", "/api/write/generate"],
                "已接入 chapter_writing_service.run_chapter_draft，用于单章正文生成。",
            ),
            "batch_generation": (
                ["/api/write/batch-generate"],
                "已接入 batch_generate，逐章复用单章正文生成并保存任务结果。",
            ),
            "creation_star_session": (
                [
                    "/api/projects/{project_id}/creation/sessions",
                    "/api/projects/{project_id}/creation/sessions/{session_id}/worldviews",
                    "/api/projects/{project_id}/creation/sessions/{session_id}/protagonists",
                    "/api/projects/{project_id}/creation/sessions/{session_id}/market-position",
                    "/api/projects/{project_id}/creation/sessions/{session_id}/seed",
                    "/api/projects/{project_id}/creation/sessions/{session_id}/core-conflict",
                    "/api/projects/{project_id}/creation/sessions/{session_id}/constitution",
                    "/api/projects/{project_id}/creation/sessions/{session_id}/constitution-review",
                    "/api/projects/{project_id}/creation/sessions/{session_id}/canon-preview",
                    "/api/projects/{project_id}/creation/sessions/{session_id}/commit",
                ],
                "已接入新版创作 Star 会话式接口：creation_star 抽卡、chief_architect 生成核心与宪法、reviewer 压力测试、canon_curator 正典预览与提交。",
            ),
        }
        if workflow_id in active:
            entrypoints, note = active[workflow_id]
            return {"runtime_status": "active_runtime", "entrypoints": entrypoints, "runtime_note": note}
        return {
            "runtime_status": "applied_via_prompt_binding",
            "entrypoints": ["/api/agents", "AGENT_SPECS_BY_NAME / AgentSpec prompt binding"],
            "runtime_note": "提示词流程已通过 AgentSpec 的提示词库绑定被实际 Agent 调用；不是独立 API 执行入口。",
        }

    def _with_workflow_runtime_metadata(self, workflow: dict[str, Any]) -> dict[str, Any]:
        return {**workflow, **self._workflow_runtime_metadata(str(workflow.get("id", "")))}

    def _apply_agent_model_configs_to_workflow(
        self,
        workflow: dict[str, Any],
        configs: dict[tuple[str, str], models.AgentModelConfig],
    ) -> dict[str, Any]:
        workflow_id = str(workflow.get("id") or workflow.get("key") or "")
        nodes: list[dict[str, Any]] = []
        for node in workflow.get("nodes", []):
            agent_name = node.get("agent_name")
            row = configs.get((workflow_id, agent_name)) if agent_name else None
            if row:
                nodes.append({**node, "provider": row.provider, "model": row.model, "model_config_id": row.id})
            else:
                nodes.append({**node, "provider": None, "model": None, "model_config_id": None})
        return {**workflow, "nodes": nodes}

    def list_workflows(self, db: Session | None = None) -> dict:
        agent_descriptions = {spec.name: spec.role for spec in DEFAULT_AGENT_SPECS}
        model_configs = self._agent_model_config_map(db) if db is not None else {}

        def agent_node(node_id: str, label: str, agent_name: str, inputs: list[str], outputs: list[str], layer: int) -> dict[str, Any]:
            return {
                "id": node_id,
                "label": label,
                "type": "agent",
                "agent_name": agent_name,
                "description": agent_descriptions.get(agent_name, label),
                "inputs": inputs,
                "outputs": outputs,
                "editable": True,
                "layer": layer,
            }

        def control_node(node_id: str, label: str, description: str, inputs: list[str], outputs: list[str], layer: int) -> dict[str, Any]:
            return {
                "id": node_id,
                "label": label,
                "type": "control",
                "agent_name": None,
                "description": description,
                "inputs": inputs,
                "outputs": outputs,
                "editable": True,
                "layer": layer,
            }

        outline_stage_by_agent = {
            "editor_orchestrator": "S1",
            "one_sentence_expansion": "S1",
            "genre_market_position": "S2",
            "world_bible": "S3",
            "protagonist_arc": "S4",
            "character_tree": "S5",
            "faction_conflict": "S5",
            "power_system": "S5",
            "full_structure": "S7",
            "volume_outline": "S9",
            "beat_control": "S10",
            "foreshadowing_manager": "S8",
            "logic_audit": "S11",
        }
        outline_output_by_agent = {
            "editor_orchestrator": ["dispatch_decision", "hard_requirements"],
            "one_sentence_expansion": ["故事核心"],
            "genre_market_position": ["类型卖点定位"],
            "world_bible": ["世界圣经"],
            "protagonist_arc": ["主角成长线"],
            "character_tree": ["人物树"],
            "faction_conflict": ["势力冲突表"],
            "power_system": ["金手指升级体系"],
            "full_structure": ["全书10卷总纲"],
            "volume_outline": ["逐卷50章大纲"],
            "beat_control": ["章节节拍表"],
            "foreshadowing_manager": ["伏笔账本"],
            "logic_audit": ["逻辑审计报告", "最终修订版纲要"],
        }
        outline_nodes = [
            {
                "id": agent_name,
                "label": AGENT_SPECS_BY_NAME[agent_name].role,
                "type": "agent",
                "agent_name": agent_name,
                "description": agent_descriptions.get(agent_name, agent_name),
                "inputs": ["StoryState", "上游 Agent 输出"] if index else ["raw_worldview", "one_sentence_story", "ProjectConfig"],
                "outputs": outline_output_by_agent.get(agent_name, []),
                "editable": True,
                "layer": index + 1,
                "stage": outline_stage_by_agent.get(agent_name, "S0"),
            }
            for index, agent_name in enumerate(OUTLINE_AGENT_SEQUENCE)
        ]
        workflows = [
            {
                "id": "creation_star_session",
                "key": "creation_star_session",
                "label": "创作 Star 立项流程",
                "nodes": [
                    control_node(
                        "basic_info",
                        "1 基本信息",
                        "创建创作 Star 会话，保存频道、类型、标签、目标读者、目标字数、风格和初始想法。",
                        ["channel", "genre", "tags", "target_reader", "target_words", "initial_idea"],
                        ["creation_session", "basic_info"],
                        0,
                    ),
                    agent_node(
                        "worldview_cards",
                        "2 世界观抽卡",
                        "creation_star",
                        ["basic_info", "manual_input", "previous_worldview_cards"],
                        ["worldview_candidates", "prompt_snapshot"],
                        1,
                    ),
                    agent_node(
                        "protagonist_cards",
                        "3 主角人设",
                        "creation_star",
                        ["basic_info", "selected_worldview", "manual_input"],
                        ["protagonist_candidates", "prompt_snapshot"],
                        2,
                    ),
                    agent_node(
                        "market_position",
                        "4 标题与卖点",
                        "creation_star",
                        ["basic_info", "selected_worldview", "selected_protagonist", "manual_input"],
                        ["title_candidates", "market_position_candidates", "prompt_snapshot"],
                        3,
                    ),
                    control_node(
                        "project_seed",
                        "5 立项种子",
                        "用户确认已选世界观、主角、标题和市场定位后，固化为 project_seed；后续 Agent 只读取已确认种子。",
                        ["selected_worldview", "selected_protagonist", "selected_title", "market_position"],
                        ["project_seed"],
                        4,
                    ),
                    agent_node(
                        "core_constitution",
                        "6 核心与宪法",
                        "chief_architect",
                        ["project_seed"],
                        ["core_conflict_system", "novel_constitution"],
                        5,
                    ),
                    agent_node(
                        "constitution_review",
                        "7 压力测试",
                        "reviewer",
                        ["project_seed", "core_conflict_system", "novel_constitution"],
                        ["constitution_review"],
                        6,
                    ),
                    agent_node(
                        "canon_preview",
                        "8 正典预览",
                        "canon_curator",
                        ["project_seed", "core_conflict_system", "novel_constitution", "constitution_review"],
                        ["canon_candidates"],
                        7,
                    ),
                    agent_node(
                        "commit_creation",
                        "9 完成创建",
                        "canon_curator",
                        ["canon_candidates", "approved_canon_sections"],
                        ["project", "story_bible", "characters", "entities", "world_facts", "graph", "version_snapshot"],
                        8,
                    ),
                ],
                "edges": [
                    {"source": "basic_info", "target": "worldview_cards", "label": "创建会话"},
                    {"source": "worldview_cards", "target": "protagonist_cards", "label": "选择世界观"},
                    {"source": "protagonist_cards", "target": "market_position", "label": "选择主角"},
                    {"source": "market_position", "target": "project_seed", "label": "选择标题与卖点"},
                    {"source": "project_seed", "target": "core_constitution", "label": "确认立项种子"},
                    {"source": "core_constitution", "target": "constitution_review", "label": "压力测试"},
                    {"source": "constitution_review", "target": "core_constitution", "label": "needs_revision / blocked"},
                    {"source": "constitution_review", "target": "canon_preview", "label": "passed / passed_with_notes"},
                    {"source": "canon_preview", "target": "commit_creation", "label": "审批六项后提交"},
                ],
            },
            {
                "id": "initialization",
                "key": "initialization",
                "label": "初始化项目",
                "nodes": [
                    agent_node("chief_architect", "总策划 Agent", "chief_architect", ["title", "genre", "initial_idea"], ["story_bible", "characters", "outline"], 1),
                    agent_node("canon_curator_init", "设定整理 Agent", "canon_curator", ["story_bible", "characters"], ["graph_nodes", "world_facts"], 2),
                ],
                "edges": [{"source": "chief_architect", "target": "canon_curator_init", "label": "抽取设定"}],
            },
            {
                "id": "outline_generation",
                "key": "outline_generation",
                "label": "长篇大纲推演",
                "nodes": outline_nodes,
                "edges": [
                    {"source": left, "target": right, "label": "写回 StoryState"}
                    for left, right in zip(OUTLINE_AGENT_SEQUENCE, OUTLINE_AGENT_SEQUENCE[1:])
                ],
            },
            {
                "id": "chapter_planning",
                "key": "chapter_planning",
                "label": "章节规划",
                "nodes": [
                    agent_node("chapter_planner", "章节规划 Agent", "chapter_planner", ["outline", "canon_context"], ["chapters"], 1),
                    agent_node("reviewer_plan", "审核修改 Agent", "reviewer", ["chapters"], ["review_notes"], 2),
                    agent_node("canon_curator_plan", "设定整理 Agent", "canon_curator", ["chapters", "review_notes"], ["canon_updates"], 3),
                ],
                "edges": [
                    {"source": "chapter_planner", "target": "reviewer_plan", "label": "审校规划"},
                    {"source": "reviewer_plan", "target": "canon_curator_plan", "label": "整理设定"},
                ],
            },
            {
                "id": "chapter_draft",
                "key": "chapter_draft",
                "label": "单章正文生成",
                "nodes": [
                    control_node("canon_context", "canon_context", "聚合项目、故事圣经、角色、实体、图谱和前文摘要。", ["project_id", "chapter_id"], ["canon_context"], 0),
                    agent_node("plot_narrator", "情节叙事 Agent", "plot_narrator", ["canon_context", "chapter_outline"], ["plot_draft"], 1),
                    agent_node("dialogue_writer", "人物对话 Agent", "dialogue_writer", ["plot_draft", "characters"], ["dialogue_draft"], 2),
                    agent_node("environment_writer", "环境描写 Agent", "environment_writer", ["plot_draft", "story_entities"], ["environment_draft"], 2),
                    agent_node("integrator", "整合输出 Agent", "integrator", ["plot_draft", "dialogue_draft", "environment_draft"], ["integrated_draft", "chapter_summary"], 3),
                    agent_node("reviewer", "审核修改 Agent", "reviewer", ["integrated_draft"], ["review_notes"], 4),
                    agent_node("fact_checker", "事实核查 Agent", "fact_checker", ["integrated_draft", "world_facts"], ["fact_check_report"], 4),
                    control_node("quality_gate", "quality_gate", "检查 blocking/error 问题，决定是否进入修订回路。", ["review_notes", "fact_check_report"], ["quality_gate"], 5),
                    control_node("revise_draft", "revise_draft", "按质量门意见进行一次受控修订。", ["integrated_draft", "review_notes"], ["integrated_draft"], 6),
                    agent_node("style_unifier", "风格统一 Agent", "style_unifier", ["integrated_draft", "style_guide"], ["final_chapter_text"], 7),
                    agent_node("canon_curator", "设定整理 Agent", "canon_curator", ["final_chapter_text", "chapter_summary"], ["canon_updates", "candidate_canon_updates"], 8),
                ],
                "edges": [
                    {"source": "canon_context", "target": "plot_narrator", "label": "提供设定上下文"},
                    {"source": "plot_narrator", "target": "dialogue_writer", "label": "补对话"},
                    {"source": "plot_narrator", "target": "environment_writer", "label": "补场景"},
                    {"source": "dialogue_writer", "target": "integrator", "label": "对话层"},
                    {"source": "environment_writer", "target": "integrator", "label": "环境层"},
                    {"source": "integrator", "target": "reviewer", "label": "审校"},
                    {"source": "integrator", "target": "fact_checker", "label": "核查"},
                    {"source": "reviewer", "target": "quality_gate", "label": "问题列表"},
                    {"source": "fact_checker", "target": "quality_gate", "label": "事实报告"},
                    {"source": "quality_gate", "target": "revise_draft", "label": "needs_revision"},
                    {"source": "quality_gate", "target": "style_unifier", "label": "passed"},
                    {"source": "revise_draft", "target": "style_unifier", "label": "修订后"},
                    {"source": "style_unifier", "target": "canon_curator", "label": "更新设定"},
                ],
            },
            {
                "id": "batch_generation",
                "key": "batch_generation",
                "label": "批量生成",
                "nodes": [
                    control_node("batch_generate", "batch_generate", "创建批量任务并逐章派发单章正文生成。", ["chapter_start", "chapter_end"], ["jobs"], 1),
                    control_node("chapter_draft_subflow", "单章正文生成子流程", "复用单章正文生成工作流。", ["chapter"], ["final_chapter_text"], 2),
                    control_node("version_snapshot", "版本快照节点", "每章完成后保存版本快照和 Agent 轨迹。", ["final_chapter_text"], ["version_snapshots"], 3),
                    control_node("batch_review", "集中审核节点", "批量完成后进入集中浏览和审核。", ["chapters"], ["review_queue"], 4),
                ],
                "edges": [
                    {"source": "batch_generate", "target": "chapter_draft_subflow", "label": "逐章生成"},
                    {"source": "chapter_draft_subflow", "target": "version_snapshot", "label": "保存快照"},
                    {"source": "version_snapshot", "target": "batch_review", "label": "集中审核"},
                ],
            },
        ]
        workflows = [
            self._apply_agent_model_configs_to_workflow(self._with_workflow_runtime_metadata(workflow), model_configs)
            for workflow in workflows
        ]
        workflows.extend(
            [
                self._apply_agent_model_configs_to_workflow(self._with_workflow_runtime_metadata(workflow), model_configs)
                for workflow in list_prompt_lifecycle_workflows()
            ]
        )
        workflows.extend(
            [
                self._apply_agent_model_configs_to_workflow(self._with_workflow_runtime_metadata(workflow), model_configs)
                for workflow in list_prompt_workflows()
            ]
        )
        return {"workflows": workflows}

    def get_agent(self, db: Session, agent_name: str) -> dict:
        spec = AGENT_SPECS_BY_NAME.get(agent_name)
        if spec is None:
            raise _not_found("Agent 不存在")
        template = (
            db.query(models.PromptTemplate)
            .filter(models.PromptTemplate.agent_name == agent_name, models.PromptTemplate.is_active == 1)
            .first()
        )
        model_configs = self._agent_model_configs_by_agent(db).get(agent_name, {})
        return {"agent": self._serialize_agent_config(spec, template, model_configs)}

    def update_agent_prompt(self, db: Session, agent_name: str, request: AgentPromptUpdateRequest) -> dict:
        spec = AGENT_SPECS_BY_NAME.get(agent_name)
        if spec is None:
            raise _not_found("Agent 不存在")
        template = (
            db.query(models.PromptTemplate)
            .filter(models.PromptTemplate.agent_name == agent_name, models.PromptTemplate.template_name == request.template_name)
            .first()
        )
        if not request.temporary:
            db.query(models.PromptTemplate).filter(models.PromptTemplate.agent_name == agent_name).update({"is_active": 0})
        if template is None:
            template = models.PromptTemplate(
                id=generate_id("tpl"),
                agent_name=agent_name,
                template_name=request.template_name,
                prompt=request.prompt,
                is_active=0 if request.temporary else 1,
                metadata_json=dumps({"temporary": request.temporary}),
            )
            db.add(template)
        else:
            template.prompt = request.prompt
            template.is_active = 0 if request.temporary else 1
            template.metadata_json = dumps({"temporary": request.temporary})
            template.updated_at = utcnow()
        db.commit()
        db.refresh(template)
        model_configs = self._agent_model_configs_by_agent(db).get(agent_name, {})
        return {"agent": self._serialize_agent_config(spec, None if request.temporary else template, model_configs), "template": serialize_prompt_template(template)}

    def restore_agent_prompt(self, db: Session, agent_name: str) -> dict:
        spec = AGENT_SPECS_BY_NAME.get(agent_name)
        if spec is None:
            raise _not_found("Agent 不存在")
        db.query(models.PromptTemplate).filter(models.PromptTemplate.agent_name == agent_name).update({"is_active": 0})
        db.commit()
        model_configs = self._agent_model_configs_by_agent(db).get(agent_name, {})
        return {"agent": self._serialize_agent_config(spec, None, model_configs)}

    def create_prompt_template(self, db: Session, request: PromptTemplateRequest) -> dict:
        template = models.PromptTemplate(
            id=generate_id("tpl"),
            agent_name=request.agent_name,
            template_name=request.template_name,
            prompt=request.prompt,
            is_active=1 if request.activate else 0,
            metadata_json=dumps(request.metadata),
        )
        if request.activate:
            db.query(models.PromptTemplate).filter(models.PromptTemplate.agent_name == request.agent_name).update({"is_active": 0})
        db.add(template)
        db.commit()
        return {"template": serialize_prompt_template(template)}

    def list_prompt_templates(self, db: Session) -> dict:
        templates = db.query(models.PromptTemplate).order_by(models.PromptTemplate.agent_name.asc(), models.PromptTemplate.created_at.desc()).all()
        return {"templates": [serialize_prompt_template(template) for template in templates]}

    def import_prompt_templates(self, db: Session, request: ImportPromptTemplatesRequest) -> dict:
        imported = [self.create_prompt_template(db, item)["template"] for item in request.templates]
        return {"templates": imported}

    def export_prompt_templates(self, db: Session) -> dict:
        return self.list_prompt_templates(db)

    def list_canon_tree(self, db: Session, project_id: str) -> dict:
        self._project(db, project_id)
        nodes: list[dict[str, Any]] = [
            self._folder_node("root", None, "设定集", 0),
            self._folder_node("folder:characters", "root", "人物", 10),
            self._folder_node("folder:entities", "root", "剧情实体", 20),
            self._folder_node("folder:world_facts", "root", "世界观事实", 30),
            self._folder_node("folder:foreshadowing", "root", "伏笔", 40),
        ]
        group_nodes: dict[str, dict[str, Any]] = {}

        def add_group(node_id: str, parent_id: str, title: str, sort_order: int) -> str:
            if node_id not in group_nodes:
                group_nodes[node_id] = self._folder_node(node_id, parent_id, title, sort_order)
            return node_id

        for row in db.query(models.Character).filter(models.Character.project_id == project_id).order_by(models.Character.importance_score.desc()).all():
            content = serialize_character(row)
            group_id = add_group(
                f"folder:characters:{row.importance_level}:{row.current_status}",
                "folder:characters",
                f"{self._importance_label(row.importance_level)} · {row.current_status or 'active'}",
                100 + self._importance_order(row.importance_level),
            )
            node = self._ensure_canon_node(
                db,
                project_id,
                "character",
                row.id,
                row.name,
                row.importance_level,
                row.current_status or row.status,
                {"group": group_id, "source": row.source},
                parent_id=group_id,
            )
            payload = serialize_canon_node(node, content)
            metadata = payload.get("metadata", {})
            payload["parent_id"] = metadata.get("custom_folder_id") or metadata.get("display_parent_id") or group_id
            nodes.append(payload)

        for row in db.query(models.StoryEntity).filter(models.StoryEntity.project_id == project_id).order_by(models.StoryEntity.importance_score.desc()).all():
            content = serialize_story_entity(row)
            group_id = add_group(
                f"folder:entities:{row.entity_type}",
                "folder:entities",
                self._entity_type_label(row.entity_type),
                200 + self._text_order(row.entity_type),
            )
            node = self._ensure_canon_node(
                db,
                project_id,
                "entity",
                row.id,
                row.name,
                row.importance_level,
                row.current_status,
                {"group": group_id, "entity_type": row.entity_type, "source": row.source},
                parent_id=group_id,
            )
            payload = serialize_canon_node(node, content)
            metadata = payload.get("metadata", {})
            payload["parent_id"] = metadata.get("custom_folder_id") or metadata.get("display_parent_id") or group_id
            nodes.append(payload)

        for row in db.query(models.WorldFact).filter(models.WorldFact.project_id == project_id).order_by(models.WorldFact.importance_score.desc()).all():
            content = serialize_world_fact(row)
            group_id = add_group(
                f"folder:world_facts:{row.category}",
                "folder:world_facts",
                self._world_fact_category_label(row.category),
                300 + self._text_order(row.category),
            )
            node = self._ensure_canon_node(
                db,
                project_id,
                "world_fact",
                row.id,
                row.title,
                row.importance_level,
                "active",
                {"group": group_id, "category": row.category, "confidence": row.confidence},
                parent_id=group_id,
            )
            payload = serialize_canon_node(node, content)
            metadata = payload.get("metadata", {})
            payload["parent_id"] = metadata.get("custom_folder_id") or metadata.get("display_parent_id") or group_id
            nodes.append(payload)

        for row in db.query(models.ForeshadowingItem).filter(models.ForeshadowingItem.project_id == project_id).order_by(models.ForeshadowingItem.importance_score.desc()).all():
            content = serialize_foreshadowing_item(row)
            group_id = add_group(
                f"folder:foreshadowing:{row.payoff_status}",
                "folder:foreshadowing",
                self._foreshadowing_status_label(row.payoff_status),
                400 + self._text_order(row.payoff_status),
            )
            node = self._ensure_canon_node(
                db,
                project_id,
                "foreshadowing",
                row.id,
                row.content[:48] or "未命名伏笔",
                row.importance_level,
                row.payoff_status,
                {"group": group_id, "source": row.source},
                parent_id=group_id,
            )
            payload = serialize_canon_node(node, content)
            metadata = payload.get("metadata", {})
            payload["parent_id"] = metadata.get("custom_folder_id") or metadata.get("display_parent_id") or group_id
            nodes.append(payload)

        db.commit()
        custom_folders = []
        for folder in (
            db.query(models.CanonNode)
            .filter(models.CanonNode.project_id == project_id, models.CanonNode.node_type == "folder")
            .order_by(models.CanonNode.sort_order.asc(), models.CanonNode.created_at.asc())
            .all()
        ):
            payload = serialize_canon_node(folder)
            metadata = payload.get("metadata", {})
            payload["parent_id"] = metadata.get("display_parent_id") or folder.parent_id or "root"
            custom_folders.append(payload)
        return {"nodes": [*nodes[:5], *group_nodes.values(), *custom_folders, *nodes[5:]], "health": self._canon_health(db, project_id)}

    def get_canon_health(self, db: Session, project_id: str) -> dict:
        self._project(db, project_id)
        return {"health": self._canon_health(db, project_id)}

    def create_canon_folder(self, db: Session, project_id: str, request: CanonFolderRequest) -> dict:
        self._project(db, project_id)
        folder = models.CanonNode(
            id=generate_id("cnd"),
            project_id=project_id,
            parent_id=request.parent_id if request.parent_id and not request.parent_id.startswith("folder:") else None,
            node_type="folder",
            ref_type="folder",
            ref_id=generate_id("fld"),
            title=request.title,
            sort_order=request.sort_order,
            status="active",
            importance_level="medium",
            activity_status="active",
            metadata_json=dumps({"custom_folder": True, "display_parent_id": request.parent_id or "root"}),
        )
        db.add(folder)
        db.commit()
        db.refresh(folder)
        payload = serialize_canon_node(folder)
        payload["parent_id"] = payload.get("metadata", {}).get("display_parent_id") or folder.parent_id or "root"
        return {"node": payload}

    def move_canon_node(self, db: Session, project_id: str, node_id: str, request: CanonNodeMoveRequest) -> dict:
        self._project(db, project_id)
        node = db.get(models.CanonNode, node_id)
        if node is None or node.project_id != project_id:
            raise _not_found("设定树节点不存在")
        metadata = loads(node.metadata_json, {})
        parent_id = request.parent_id or "root"
        if parent_id == node.id:
            raise _bad_request("不能把节点移动到自身之下")
        real_parent = db.get(models.CanonNode, parent_id) if parent_id and not parent_id.startswith("folder:") else None
        node.parent_id = real_parent.id if real_parent and real_parent.project_id == project_id else None
        node.sort_order = request.sort_order
        metadata["display_parent_id"] = parent_id
        if node.node_type == "item":
            metadata["custom_folder_id"] = parent_id
            db.query(models.CanonClassification).filter(
                models.CanonClassification.project_id == project_id,
                models.CanonClassification.ref_type == node.ref_type,
                models.CanonClassification.ref_id == node.ref_id,
                models.CanonClassification.dimension == "custom_folder",
            ).delete()
            db.add(
                models.CanonClassification(
                    id=generate_id("ccl"),
                    project_id=project_id,
                    ref_type=node.ref_type,
                    ref_id=node.ref_id,
                    dimension="custom_folder",
                    value=parent_id,
                )
            )
        node.metadata_json = dumps(metadata)
        node.updated_at = utcnow()
        db.commit()
        db.refresh(node)
        payload = serialize_canon_node(node)
        payload["parent_id"] = metadata.get("display_parent_id") or node.parent_id or "root"
        return {"node": payload}

    def set_canon_locks(self, db: Session, project_id: str, ref_type: str, ref_id: str, request: CanonLockFieldsRequest) -> dict:
        ref_type = self._normalize_canon_ref_type(ref_type)
        row = self._canon_ref_row(db, project_id, ref_type, ref_id)
        content = self._canon_ref_content(ref_type, row)
        node = self._ensure_canon_node(
            db,
            project_id,
            ref_type,
            ref_id,
            self._canon_ref_title(ref_type, content),
            str(content.get("importance_level") or "medium"),
            str(content.get("current_status") or content.get("payoff_status") or "active"),
            {},
        )
        metadata = loads(node.metadata_json, {})
        metadata["locked_fields"] = sorted({field for field in request.locked_fields if field})
        if request.reason:
            metadata["lock_reason"] = request.reason
        node.metadata_json = dumps(metadata)
        node.updated_at = utcnow()
        db.commit()
        db.refresh(node)
        return {"node": serialize_canon_node(node, content)}

    def get_canon_impact(self, db: Session, project_id: str, ref_type: str, ref_id: str) -> dict:
        ref_type = self._normalize_canon_ref_type(ref_type)
        row = self._canon_ref_row(db, project_id, ref_type, ref_id)
        content = self._canon_ref_content(ref_type, row)
        title = self._canon_ref_title(ref_type, content)
        terms = [term for term in {title, str(content.get("name") or ""), str(content.get("title") or "")} if term]
        chapters = []
        for chapter in db.query(models.Chapter).filter(models.Chapter.project_id == project_id).order_by(models.Chapter.chapter_no.asc()).all():
            haystack = "\n".join([chapter.title, chapter.outline, chapter.core_event, chapter.conflict, chapter.summary, chapter.draft_text, chapter.final_text])
            if any(term and term in haystack for term in terms):
                chapters.append(
                    {
                        "id": chapter.id,
                        "chapter_no": chapter.chapter_no,
                        "title": chapter.title,
                        "match_reason": "文本引用",
                        "status": chapter.status,
                    }
                )
        graph_node_types = [ref_type]
        if ref_type == "foreshadowing":
            graph_node_types = ["clue"]
        graph_node = (
            db.query(models.GraphNode)
            .filter(models.GraphNode.project_id == project_id, models.GraphNode.ref_id == ref_id, models.GraphNode.node_type.in_(graph_node_types))
            .first()
        )
        graph_edges: list[dict[str, Any]] = []
        related_nodes: list[dict[str, Any]] = []
        if graph_node:
            edges = (
                db.query(models.GraphEdge)
                .filter(or_(models.GraphEdge.source_node_id == graph_node.id, models.GraphEdge.target_node_id == graph_node.id))
                .order_by(models.GraphEdge.importance_score.desc())
                .all()
            )
            graph_edges = [serialize_graph_edge(edge) for edge in edges]
            related_ids = {edge.source_node_id for edge in edges} | {edge.target_node_id for edge in edges}
            related_ids.discard(graph_node.id)
            if related_ids:
                related_nodes = [serialize_graph_node(node) for node in db.query(models.GraphNode).filter(models.GraphNode.id.in_(related_ids)).all()]
        versions = self.list_canon_versions(db, project_id, ref_type, ref_id)["versions"]
        proposals = [
            serialize_canon_proposal(proposal)
            for proposal in db.query(models.CanonChangeProposal)
            .filter(models.CanonChangeProposal.project_id == project_id, models.CanonChangeProposal.target_type == ref_type)
            .filter((models.CanonChangeProposal.target_id == ref_id) | (models.CanonChangeProposal.after_json.contains(ref_id)) | (models.CanonChangeProposal.before_json.contains(ref_id)))
            .order_by(models.CanonChangeProposal.created_at.desc())
            .limit(20)
            .all()
        ]
        foreshadowing_refs = []
        if ref_type in {"character", "entity"}:
            column = models.ForeshadowingItem.related_character_ids_json if ref_type == "character" else models.ForeshadowingItem.related_entity_ids_json
            foreshadowing_refs = [
                serialize_foreshadowing_item(item)
                for item in db.query(models.ForeshadowingItem).filter(models.ForeshadowingItem.project_id == project_id, column.contains(ref_id)).limit(20).all()
            ]
        return {
            "ref": {"ref_type": ref_type, "ref_id": ref_id, "title": title, "content": content},
            "chapters": chapters,
            "graph": {"node": serialize_graph_node(graph_node) if graph_node else None, "edges": graph_edges, "related_nodes": related_nodes},
            "versions": versions,
            "proposals": proposals,
            "foreshadowing": foreshadowing_refs,
            "summary": {
                "chapter_count": len(chapters),
                "relation_count": len(graph_edges),
                "version_count": len(versions),
                "proposal_count": len(proposals),
                "foreshadowing_count": len(foreshadowing_refs),
            },
        }

    def scan_canon_duplicates(self, db: Session, project_id: str, request: CanonDuplicateScanRequest) -> dict:
        self._project(db, project_id)
        refs: list[dict[str, Any]] = []
        for ref_type in request.ref_types:
            normalized = self._normalize_canon_ref_type(ref_type)
            rows = self._canon_rows_for_type(db, project_id, normalized)
            for row in rows:
                content = self._canon_ref_content(normalized, row)
                refs.append({"ref_type": normalized, "ref_id": row.id, "title": self._canon_ref_title(normalized, content), "content": content})
        candidates: list[dict[str, Any]] = []
        proposals: list[dict[str, Any]] = []
        for index, left in enumerate(refs):
            for right in refs[index + 1 :]:
                if left["ref_type"] != right["ref_type"]:
                    continue
                score = self._similarity_score(left["title"], right["title"])
                if score < request.threshold:
                    continue
                source, target = (right, left) if len(right["title"]) < len(left["title"]) else (left, right)
                candidate = {"source": source, "target": target, "score": round(score, 3), "reason": "名称近似或同名"}
                candidates.append(candidate)
                if not request.create_proposals:
                    continue
                exists = (
                    db.query(models.CanonChangeProposal)
                    .filter(
                        models.CanonChangeProposal.project_id == project_id,
                        models.CanonChangeProposal.operation == "merge",
                        models.CanonChangeProposal.approval_status == "pending",
                        models.CanonChangeProposal.target_type == target["ref_type"],
                        models.CanonChangeProposal.target_id == target["ref_id"],
                        models.CanonChangeProposal.after_json.contains(source["ref_id"]),
                    )
                    .first()
                )
                if exists:
                    proposals.append(serialize_canon_proposal(exists))
                    continue
                merged = self._merge_canon_content(target["content"], source["content"], target["ref_type"])
                proposal = self._create_canon_proposal(
                    db,
                    project_id,
                    target["ref_type"],
                    {"source_ref_type": source["ref_type"], "source_ref_id": source["ref_id"], "target_ref_type": target["ref_type"], "target_ref_id": target["ref_id"], "merged_content": merged},
                    target_id=target["ref_id"],
                    operation="merge",
                    before={"source": source["content"], "target": target["content"]},
                    source_agent="duplicate_scanner",
                    confidence=min(0.98, max(0.55, score)),
                    reason=f"可能重复：{source['title']} → {target['title']}",
                )
                proposals.append(serialize_canon_proposal(proposal))
        db.commit()
        return {"candidates": candidates, "proposals": proposals}

    def export_canon_package(self, db: Session, project_id: str, request: CanonExportRequest) -> dict:
        project = self._project(db, project_id)
        story_bible = db.query(models.StoryBible).filter(models.StoryBible.project_id == project_id).first()
        tree = self.list_canon_tree(db, project_id)
        package = {
            "project": serialize_project(project),
            "story_bible": serialize_story_bible(story_bible) if story_bible else None,
            "tree": tree["nodes"],
            "health": tree["health"],
            "characters": self.list_characters(db, project_id)["characters"],
            "entities": self.list_entities(db, project_id)["entities"],
            "world_facts": self.list_world_facts(db, project_id)["world_facts"],
            "foreshadowing": self.list_foreshadowing(db, project_id)["foreshadowing_items"],
            "graph": self.get_graph(db, project_id)["graph"],
            "versions": [
                serialize_canon_version(row)
                for row in db.query(models.CanonVersion).filter(models.CanonVersion.project_id == project_id).order_by(models.CanonVersion.created_at.desc()).all()
            ],
            "proposals": self.list_canon_proposals(db, project_id)["proposals"],
            "exported_at": isoformat(utcnow()),
        }
        if request.format == "markdown":
            content = self._render_canon_markdown(package)
        else:
            content = json.dumps(package, ensure_ascii=False, indent=2)
        return {"filename": f"{project.title}-canon.{ 'md' if request.format == 'markdown' else 'json' }", "format": request.format, "content": content, "package": package if request.format == "json" else None}

    def list_canon_versions(self, db: Session, project_id: str, ref_type: str, ref_id: str) -> dict:
        ref_type = self._normalize_canon_ref_type(ref_type)
        self._project(db, project_id)
        versions = (
            db.query(models.CanonVersion)
            .filter(models.CanonVersion.project_id == project_id, models.CanonVersion.ref_type == ref_type, models.CanonVersion.ref_id == ref_id)
            .order_by(models.CanonVersion.version_no.asc())
            .all()
        )
        return {"versions": [serialize_canon_version(row) for row in versions]}

    def rollback_canon_version(self, db: Session, project_id: str, ref_type: str, ref_id: str, version_id: str, request: CanonRollbackRequest) -> dict:
        ref_type = self._normalize_canon_ref_type(ref_type)
        version = db.get(models.CanonVersion, version_id)
        if version is None or version.project_id != project_id or version.ref_type != ref_type or version.ref_id != ref_id:
            raise _not_found("设定版本不存在")
        row = self._canon_ref_row(db, project_id, ref_type, ref_id)
        content = loads(version.content_json, {})
        self._apply_canon_content(row, ref_type, content)
        db.flush()
        current = self._canon_ref_content(ref_type, row)
        rollback_version = self._record_canon_version(
            db,
            project_id,
            ref_type,
            ref_id,
            current,
            source_chapter_id=version.source_chapter_id,
            source_job_id=version.source_job_id,
            source_agent="rollback",
            change_reason=request.user_note or f"回滚到版本 {version.version_no}",
            confidence=version.confidence,
        )
        self._ensure_canon_node(
            db,
            project_id,
            ref_type,
            ref_id,
            self._canon_ref_title(ref_type, current),
            str(current.get("importance_level") or "medium"),
            str(current.get("current_status") or current.get("payoff_status") or "active"),
            {"rollback_from_version": version.version_no},
        )
        db.commit()
        db.refresh(row)
        payload_key = {"character": "character", "entity": "entity", "world_fact": "world_fact", "foreshadowing": "foreshadowing"}.get(ref_type, "item")
        return {
            "rolled_back": True,
            payload_key: self._canon_ref_content(ref_type, row),
            "item": self._canon_ref_content(ref_type, row),
            "version": serialize_canon_version(rollback_version),
        }

    def list_canon_proposals(self, db: Session, project_id: str, status: str | None = None) -> dict:
        self._project(db, project_id)
        query = db.query(models.CanonChangeProposal).filter(models.CanonChangeProposal.project_id == project_id)
        if status:
            query = query.filter(models.CanonChangeProposal.approval_status == status)
        rows = query.order_by(models.CanonChangeProposal.created_at.desc()).all()
        return {"proposals": [serialize_canon_proposal(row) for row in rows]}

    def approve_canon_proposal(self, db: Session, project_id: str, proposal_id: str, request: CanonProposalDecisionRequest | None = None) -> dict:
        proposal = db.get(models.CanonChangeProposal, proposal_id)
        if proposal is None or proposal.project_id != project_id:
            raise _not_found("设定候选不存在")
        if proposal.approval_status != "pending":
            raise _bad_request("设定候选已处理")
        target_type = self._normalize_canon_ref_type(proposal.target_type)
        payload = loads(proposal.after_json, {})
        applied: dict[str, Any]
        if proposal.operation == "update":
            if not proposal.target_id:
                raise _bad_request("更新类候选缺少目标设定")
            row = self._canon_ref_row(db, project_id, target_type, proposal.target_id)
            self._apply_canon_content(row, target_type, payload)
            db.flush()
            current = self._canon_ref_content(target_type, row)
            version = self._record_canon_version(
                db,
                project_id,
                target_type,
                proposal.target_id,
                current,
                source_chapter_id=proposal.source_chapter_id,
                source_job_id=proposal.source_job_id,
                source_agent=proposal.source_agent,
                change_reason=request.user_note if request and request.user_note else proposal.reason,
                confidence=proposal.confidence,
            )
            self._ensure_canon_node(
                db,
                project_id,
                target_type,
                proposal.target_id,
                self._canon_ref_title(target_type, current),
                str(current.get("importance_level") or "medium"),
                str(current.get("current_status") or current.get("payoff_status") or "active"),
                {"last_proposal_id": proposal.id},
            )
            applied = {"ref_type": target_type, "ref_id": proposal.target_id, "item": current, "version": serialize_canon_version(version)}
        elif proposal.operation == "archive":
            if not proposal.target_id:
                raise _bad_request("归档类候选缺少目标设定")
            result = self.archive_canon_items(db, project_id, CanonBulkArchiveRequest(ref_type=target_type, ref_ids=[proposal.target_id], reason=request.user_note if request and request.user_note else proposal.reason))
            applied = {"ref_type": target_type, "ref_id": proposal.target_id, "item": result["archived"][0]}
        elif proposal.operation == "merge":
            source_ref_type = self._normalize_canon_ref_type(str(payload.get("source_ref_type") or target_type))
            source_ref_id = str(payload.get("source_ref_id") or "")
            target_ref_type = self._normalize_canon_ref_type(str(payload.get("target_ref_type") or target_type))
            target_ref_id = str(payload.get("target_ref_id") or proposal.target_id or "")
            if not source_ref_id or not target_ref_id:
                raise _bad_request("合并类候选缺少来源或目标设定")
            target_row = self._canon_ref_row(db, project_id, target_ref_type, target_ref_id)
            source_row = self._canon_ref_row(db, project_id, source_ref_type, source_ref_id)
            merged = payload.get("merged_content") if isinstance(payload.get("merged_content"), dict) else self._merge_canon_content(self._canon_ref_content(target_ref_type, target_row), self._canon_ref_content(source_ref_type, source_row), target_ref_type)
            self._apply_canon_content(target_row, target_ref_type, merged)
            if hasattr(source_row, "status"):
                source_row.status = "archived"
            if hasattr(source_row, "current_status"):
                source_row.current_status = "archived"
            if hasattr(source_row, "payoff_status"):
                source_row.payoff_status = "abandoned"
            db.flush()
            target_content = self._canon_ref_content(target_ref_type, target_row)
            source_content = self._canon_ref_content(source_ref_type, source_row)
            target_version = self._record_canon_version(db, project_id, target_ref_type, target_ref_id, target_content, source_agent="merge", change_reason=request.user_note if request and request.user_note else proposal.reason, confidence=proposal.confidence)
            source_version = self._record_canon_version(db, project_id, source_ref_type, source_ref_id, source_content, source_agent="merge", change_reason=f"合并归档到 {target_ref_id}", confidence=proposal.confidence)
            self._ensure_canon_node(db, project_id, target_ref_type, target_ref_id, self._canon_ref_title(target_ref_type, target_content), str(target_content.get("importance_level") or "medium"), str(target_content.get("current_status") or target_content.get("payoff_status") or "active"), {"merged_from": source_ref_id})
            source_node = self._ensure_canon_node(db, project_id, source_ref_type, source_ref_id, self._canon_ref_title(source_ref_type, source_content), str(source_content.get("importance_level") or "medium"), "archived", {"merged_into": target_ref_id})
            source_node.status = "archived"
            applied = {
                "ref_type": target_ref_type,
                "ref_id": target_ref_id,
                "item": target_content,
                "source_ref": {"ref_type": source_ref_type, "ref_id": source_ref_id, "version": serialize_canon_version(source_version)},
                "version": serialize_canon_version(target_version),
            }
        elif proposal.operation != "create":
            raise _bad_request("不支持的设定候选操作", {"operation": proposal.operation})
        elif target_type == "character":
            result = self.create_character(
                db,
                project_id,
                CreateCharacterRequest(
                    name=str(payload.get("name") or "未命名角色"),
                    aliases=list(payload.get("aliases") or []),
                    role_type=payload.get("role_type") or payload.get("role") or "supporting",
                    importance_level=payload.get("importance_level") or "medium",
                    importance_score=int(payload.get("importance_score") or 50),
                    summary=str(payload.get("summary") or payload.get("profile") or ""),
                    appearance=str(payload.get("appearance") or ""),
                    personality=str(payload.get("personality") or ""),
                    goals=list(payload.get("goals") or []),
                    motivations=list(payload.get("motivations") or []),
                    secrets=list(payload.get("secrets") or []),
                    abilities=list(payload.get("abilities") or []),
                    weaknesses=list(payload.get("weaknesses") or []),
                    character_arc=str(payload.get("character_arc") or payload.get("arc") or ""),
                    current_status=str(payload.get("current_status") or "active"),
                    related_entity_ids=list(payload.get("related_entity_ids") or []),
                    related_character_ids=list(payload.get("related_character_ids") or []),
                    updated_reason=request.user_note if request and request.user_note else proposal.reason,
                    source_chapter_id=proposal.source_chapter_id or payload.get("source_chapter_id"),
                    source_agent=proposal.source_agent,
                ),
            )
            applied = {"ref_type": "character", "ref_id": result["character"]["id"], "item": result["character"]}
        elif target_type == "entity":
            result = self.create_entity(
                db,
                project_id,
                CreateEntityRequest(
                    entity_type=payload.get("entity_type") or "item",
                    name=str(payload.get("name") or "未命名实体"),
                    importance_level=payload.get("importance_level") or "medium",
                    importance_score=int(payload.get("importance_score") or 50),
                    description=str(payload.get("description") or ""),
                    current_status=str(payload.get("current_status") or "active"),
                    source=str(payload.get("source") or proposal.source_agent),
                    source_chapter_id=proposal.source_chapter_id or payload.get("source_chapter_id"),
                    source_agent=proposal.source_agent,
                ),
            )
            applied = {"ref_type": "entity", "ref_id": result["entity"]["id"], "item": result["entity"]}
        elif target_type == "world_fact":
            result = self.create_world_fact(
                db,
                project_id,
                CreateWorldFactRequest(
                    category=payload.get("category") or "timeline",
                    title=str(payload.get("title") or "未命名世界观事实"),
                    content=str(payload.get("content") or ""),
                    importance_level=payload.get("importance_level") or "medium",
                    importance_score=int(payload.get("importance_score") or 50),
                    confidence=float(payload.get("confidence") or proposal.confidence or 0.8),
                    related_entity_ids=list(payload.get("related_entity_ids") or []),
                    source_chapter_id=proposal.source_chapter_id or payload.get("source_chapter_id"),
                    source_agent=proposal.source_agent,
                ),
            )
            applied = {"ref_type": "world_fact", "ref_id": result["world_fact"]["id"], "item": result["world_fact"]}
        else:
            raise _bad_request("不支持的设定候选类型", {"target_type": proposal.target_type})
        proposal.approval_status = "approved"
        proposal.target_id = applied["ref_id"]
        proposal.decided_at = utcnow()
        db.commit()
        db.refresh(proposal)
        return {"proposal": serialize_canon_proposal(proposal), "applied_ref": applied}

    def reject_canon_proposal(self, db: Session, project_id: str, proposal_id: str, request: CanonProposalDecisionRequest | None = None) -> dict:
        proposal = db.get(models.CanonChangeProposal, proposal_id)
        if proposal is None or proposal.project_id != project_id:
            raise _not_found("设定候选不存在")
        if proposal.approval_status != "pending":
            raise _bad_request("设定候选已处理")
        note = request.user_note if request else ""
        proposal.approval_status = "rejected"
        proposal.reason = f"{proposal.reason}\n拒绝原因：{note}".strip()
        proposal.decided_at = utcnow()
        db.commit()
        db.refresh(proposal)
        return {"proposal": serialize_canon_proposal(proposal)}

    def archive_canon_items(self, db: Session, project_id: str, request: CanonBulkArchiveRequest) -> dict:
        ref_type = self._normalize_canon_ref_type(request.ref_type)
        archived: list[dict[str, Any]] = []
        for ref_id in request.ref_ids:
            row = self._canon_ref_row(db, project_id, ref_type, ref_id)
            if hasattr(row, "status"):
                row.status = "archived"
            if hasattr(row, "current_status"):
                row.current_status = "archived"
            node = self._ensure_canon_node(
                db,
                project_id,
                ref_type,
                ref_id,
                self._canon_ref_title(ref_type, self._canon_ref_content(ref_type, row)),
                getattr(row, "importance_level", "medium"),
                "archived",
                {"archive_reason": request.reason},
            )
            node.status = "archived"
            content = self._canon_ref_content(ref_type, row)
            version = self._record_canon_version(db, project_id, ref_type, ref_id, content, source_agent="manual", change_reason=request.reason or "批量归档")
            archived.append({"ref_type": ref_type, "ref_id": ref_id, "version": serialize_canon_version(version)})
        db.commit()
        return {"archived": archived}

    def list_characters(self, db: Session, project_id: str) -> dict:
        self._project(db, project_id)
        rows = db.query(models.Character).filter(models.Character.project_id == project_id).order_by(models.Character.importance_score.desc()).all()
        return {"characters": [serialize_character(row) for row in rows]}

    def create_character(self, db: Session, project_id: str, request: CreateCharacterRequest) -> dict:
        self._project(db, project_id)
        existing = db.query(models.Character).filter(models.Character.project_id == project_id, models.Character.name == request.name).first()
        if existing:
            raise _conflict("同名角色已存在")
        row = models.Character(
            id=generate_id("chr"),
            project_id=project_id,
            name=request.name,
            role=request.role_type,
            role_type=request.role_type,
            importance_level=request.importance_level,
            importance_score=request.importance_score,
            summary=request.summary,
            appearance=request.appearance,
            personality=request.personality,
            goals_json=dumps(request.goals),
            motivations_json=dumps(request.motivations),
            secrets_json=dumps(request.secrets),
            abilities_json=dumps(request.abilities),
            weaknesses_json=dumps(request.weaknesses),
            character_arc=request.character_arc,
            current_status=request.current_status,
            aliases_json=dumps(request.aliases),
            related_entity_ids_json=dumps(request.related_entity_ids),
            related_character_ids_json=dumps(request.related_character_ids),
            updated_reason=request.updated_reason,
            source="manual",
            first_appearance_chapter_id=request.source_chapter_id,
            last_seen_chapter_id=request.source_chapter_id,
        )
        db.add(row)
        db.flush()
        self._ensure_graph_node(db, project_id, "character", row.id, row.name, row.importance_level, row.importance_score)
        self._sync_canon_ref(
            db,
            project_id,
            "character",
            row,
            source_chapter_id=request.source_chapter_id,
            source_agent=request.source_agent,
            change_reason=request.updated_reason,
        )
        db.commit()
        db.refresh(row)
        return {"character": serialize_character(row)}

    def get_character(self, db: Session, project_id: str, character_id: str) -> dict:
        row = db.get(models.Character, character_id)
        if row is None or row.project_id != project_id:
            raise _not_found("角色不存在")
        return {"character": serialize_character(row)}

    def update_character(self, db: Session, project_id: str, character_id: str, request: UpdateCharacterRequest) -> dict:
        row = db.get(models.Character, character_id)
        if row is None or row.project_id != project_id:
            raise _not_found("角色不存在")
        updates = request.model_dump(exclude_unset=True)
        source_chapter_id = updates.pop("source_chapter_id", None)
        source_agent = updates.pop("source_agent", None) or "manual"
        before_content = self._canon_ref_content("character", row)
        proposed_content = dict(before_content)
        for field, value in updates.items():
            if value is not None:
                proposed_content[field] = value
        self._guard_locked_fields_or_propose(db, project_id, "character", character_id, source_agent, before_content, proposed_content, source_chapter_id=source_chapter_id)
        for field, value in updates.items():
            if value is None:
                continue
            if field in {"aliases", "goals", "motivations", "secrets", "abilities", "weaknesses", "related_entity_ids", "related_character_ids"}:
                setattr(row, f"{field}_json", dumps(value))
            elif hasattr(row, field):
                setattr(row, field, value)
        if "role_type" in updates and row.role_type:
            row.role = row.role_type
        if source_chapter_id:
            if not row.first_appearance_chapter_id:
                row.first_appearance_chapter_id = source_chapter_id
            row.last_seen_chapter_id = source_chapter_id
        self._ensure_graph_node(db, project_id, "character", row.id, row.name, row.importance_level, row.importance_score)
        self._sync_canon_ref(
            db,
            project_id,
            "character",
            row,
            source_chapter_id=source_chapter_id,
            source_agent=source_agent,
            change_reason=row.updated_reason,
        )
        db.commit()
        db.refresh(row)
        return {"character": serialize_character(row)}

    def delete_character(self, db: Session, project_id: str, character_id: str) -> dict:
        row = db.get(models.Character, character_id)
        if row is None or row.project_id != project_id:
            raise _not_found("角色不存在")
        db.query(models.GraphNode).filter(models.GraphNode.project_id == project_id, models.GraphNode.node_type == "character", models.GraphNode.ref_id == character_id).delete()
        db.delete(row)
        db.commit()
        return {"deleted": True, "character_id": character_id}

    def list_entities(self, db: Session, project_id: str) -> dict:
        self._project(db, project_id)
        rows = db.query(models.StoryEntity).filter(models.StoryEntity.project_id == project_id).order_by(models.StoryEntity.importance_score.desc()).all()
        return {"entities": [serialize_story_entity(row) for row in rows]}

    def create_entity(self, db: Session, project_id: str, request: CreateEntityRequest) -> dict:
        self._project(db, project_id)
        existing = (
            db.query(models.StoryEntity)
            .filter(models.StoryEntity.project_id == project_id, models.StoryEntity.entity_type == request.entity_type, models.StoryEntity.name == request.name)
            .first()
        )
        if existing:
            raise _conflict("同名同类型实体已存在")
        row = models.StoryEntity(
            id=generate_id("ent"),
            project_id=project_id,
            entity_type=request.entity_type,
            name=request.name,
            importance_level=request.importance_level,
            importance_score=request.importance_score,
            description=request.description,
            current_status=request.current_status,
            source=request.source,
            first_appearance_chapter_id=request.source_chapter_id,
            last_seen_chapter_id=request.source_chapter_id,
        )
        db.add(row)
        db.flush()
        self._ensure_graph_node(db, project_id, "entity", row.id, row.name, row.importance_level, row.importance_score)
        self._sync_canon_ref(
            db,
            project_id,
            "entity",
            row,
            source_chapter_id=request.source_chapter_id,
            source_agent=request.source_agent,
            change_reason=f"{request.source} 创建实体",
        )
        db.commit()
        db.refresh(row)
        return {"entity": serialize_story_entity(row)}

    def update_entity(self, db: Session, project_id: str, entity_id: str, request: UpdateEntityRequest) -> dict:
        row = db.get(models.StoryEntity, entity_id)
        if row is None or row.project_id != project_id:
            raise _not_found("剧情实体不存在")
        updates = request.model_dump(exclude_unset=True)
        source_chapter_id = updates.pop("source_chapter_id", None)
        source_agent = updates.pop("source_agent", None) or "manual"
        before_content = self._canon_ref_content("entity", row)
        proposed_content = dict(before_content)
        for field, value in updates.items():
            if value is not None:
                proposed_content[field] = value
        self._guard_locked_fields_or_propose(db, project_id, "entity", entity_id, source_agent, before_content, proposed_content, source_chapter_id=source_chapter_id)
        for field, value in updates.items():
            if value is not None and hasattr(row, field):
                setattr(row, field, value)
        if source_chapter_id:
            if not row.first_appearance_chapter_id:
                row.first_appearance_chapter_id = source_chapter_id
            row.last_seen_chapter_id = source_chapter_id
        self._ensure_graph_node(db, project_id, "entity", row.id, row.name, row.importance_level, row.importance_score)
        self._sync_canon_ref(
            db,
            project_id,
            "entity",
            row,
            source_chapter_id=source_chapter_id,
            source_agent=source_agent,
            change_reason="更新剧情实体",
        )
        db.commit()
        db.refresh(row)
        return {"entity": serialize_story_entity(row)}

    def delete_entity(self, db: Session, project_id: str, entity_id: str) -> dict:
        row = db.get(models.StoryEntity, entity_id)
        if row is None or row.project_id != project_id:
            raise _not_found("剧情实体不存在")
        db.query(models.GraphNode).filter(models.GraphNode.project_id == project_id, models.GraphNode.node_type == "entity", models.GraphNode.ref_id == entity_id).delete()
        db.delete(row)
        db.commit()
        return {"deleted": True, "entity_id": entity_id}

    def list_world_facts(self, db: Session, project_id: str) -> dict:
        self._project(db, project_id)
        rows = db.query(models.WorldFact).filter(models.WorldFact.project_id == project_id).order_by(models.WorldFact.importance_score.desc()).all()
        return {"world_facts": [serialize_world_fact(row) for row in rows]}

    def create_world_fact(self, db: Session, project_id: str, request: CreateWorldFactRequest) -> dict:
        self._project(db, project_id)
        existing = db.query(models.WorldFact).filter(models.WorldFact.project_id == project_id, models.WorldFact.title == request.title).first()
        if existing:
            raise _conflict("同名世界观事实已存在")
        row = models.WorldFact(
            id=generate_id("wld"),
            project_id=project_id,
            category=request.category,
            title=request.title,
            content=request.content,
            importance_level=request.importance_level,
            importance_score=request.importance_score,
            confidence=request.confidence,
            source_chapter_id=request.source_chapter_id,
            related_entity_ids_json=dumps(request.related_entity_ids),
        )
        db.add(row)
        db.flush()
        self._ensure_graph_node(db, project_id, "world_fact", row.id, row.title, row.importance_level, row.importance_score)
        self._sync_canon_ref(
            db,
            project_id,
            "world_fact",
            row,
            source_chapter_id=request.source_chapter_id,
            source_agent=request.source_agent,
            change_reason="创建世界观事实",
            confidence=request.confidence,
        )
        db.commit()
        db.refresh(row)
        return {"world_fact": serialize_world_fact(row)}

    def update_world_fact(self, db: Session, project_id: str, fact_id: str, request: UpdateWorldFactRequest) -> dict:
        row = db.get(models.WorldFact, fact_id)
        if row is None or row.project_id != project_id:
            raise _not_found("世界观事实不存在")
        updates = request.model_dump(exclude_unset=True)
        source_agent = updates.pop("source_agent", None) or "manual"
        source_chapter_id = updates.get("source_chapter_id")
        before_content = self._canon_ref_content("world_fact", row)
        proposed_content = dict(before_content)
        for field, value in updates.items():
            if value is not None:
                proposed_content[field] = value
        self._guard_locked_fields_or_propose(db, project_id, "world_fact", fact_id, source_agent, before_content, proposed_content, source_chapter_id=source_chapter_id)
        for field, value in updates.items():
            if value is None:
                continue
            if field == "related_entity_ids":
                row.related_entity_ids_json = dumps(value)
            elif hasattr(row, field):
                setattr(row, field, value)
        self._ensure_graph_node(db, project_id, "world_fact", row.id, row.title, row.importance_level, row.importance_score)
        self._sync_canon_ref(
            db,
            project_id,
            "world_fact",
            row,
            source_chapter_id=row.source_chapter_id,
            source_agent=source_agent,
            change_reason="更新世界观事实",
            confidence=row.confidence,
        )
        db.commit()
        db.refresh(row)
        return {"world_fact": serialize_world_fact(row)}

    def delete_world_fact(self, db: Session, project_id: str, fact_id: str) -> dict:
        row = db.get(models.WorldFact, fact_id)
        if row is None or row.project_id != project_id:
            raise _not_found("世界观事实不存在")
        db.query(models.GraphNode).filter(models.GraphNode.project_id == project_id, models.GraphNode.node_type == "world_fact", models.GraphNode.ref_id == fact_id).delete()
        db.delete(row)
        db.commit()
        return {"deleted": True, "world_fact_id": fact_id}

    def generate_settings(self, db: Session, project_id: str, request: GenerateSettingRequest) -> dict:
        project = self._project(db, project_id)
        job = self._create_job(db, project_id, None, "generate_settings", request.model, request.model_dump(), total_steps=3)
        created_characters: list[dict[str, Any]] = []
        created_entities: list[dict[str, Any]] = []
        created_world_facts: list[dict[str, Any]] = []
        instruction = request.instruction or project.premise or "补充可供后续章节调用的设定。"
        if request.preview_only:
            timestamp = isoformat(utcnow())

            def merge_candidate(fallback: dict[str, Any], candidate: Any, field_map: dict[str, str]) -> dict[str, Any]:
                if not isinstance(candidate, dict):
                    return fallback
                item = dict(fallback)
                for target_key, source_key in field_map.items():
                    value = candidate.get(source_key) if source_key in candidate else candidate.get(target_key)
                    if value not in (None, ""):
                        item[target_key] = value
                return item

            if request.target in {"characters", "all"}:
                role_templates = [
                    ("关键盟友", "supporting", "major", 78),
                    ("隐秘对手", "antagonist", "major", 76),
                    ("线索见证人", "supporting", "medium", 62),
                ]
                fallback_characters = []
                for index in range(request.count):
                    label, role_type, level, score = role_templates[index % len(role_templates)]
                    fallback_characters.append(
                        {
                            "id": f"preview_chr_{index + 1}",
                            "project_id": project_id,
                            "name": f"{label}{index + 1}",
                            "aliases": [],
                            "role": role_type,
                            "role_type": role_type,
                            "importance_level": level,
                            "importance_score": max(45, score - index),
                            "summary": f"Agent 根据“{instruction}”生成的{label}候选，确认后才会写入正式角色卡。",
                            "appearance": "",
                            "personality": "目标明确，拥有可被剧情检验的弱点。",
                            "profile": "",
                            "goals": ["推动第一卷主线", "制造与主角价值观相关的选择"],
                            "motivations": ["保护自身秘密", "改变当前秩序"],
                            "secrets": [],
                            "abilities": [],
                            "weaknesses": [],
                            "character_arc": "从功能性出场逐步显露个人选择与代价。",
                            "current_status": "candidate",
                            "related_entity_ids": [],
                            "related_character_ids": [],
                            "updated_reason": "agent_assisted_setting_preview",
                            "relations": [],
                            "status": "active",
                            "source": "agent",
                            "created_at": timestamp,
                            "updated_at": timestamp,
                        }
                    )
                character_payload, character_meta = call_agent_json(
                    llm_client=llm_client,
                    agent_name="chief_architect",
                    role=AGENT_SPECS_BY_NAME["chief_architect"].role,
                    system_prompt=AGENT_SPECS_BY_NAME["chief_architect"].prompt,
                    task="为项目生成候选角色卡预览。必须输出 characters 数组；不要假定已写入正式设定。",
                    context={"project": serialize_project(project), "target": request.target, "instruction": instruction, "count": request.count, "preview_only": True},
                    fallback={"characters": fallback_characters},
                    model=request.model,
                )
                created_characters = [
                    merge_candidate(fallback, candidate, {"name": "name", "summary": "summary", "personality": "personality", "character_arc": "character_arc"})
                    for fallback, candidate in zip(fallback_characters, character_payload.get("characters", []))
                ] or fallback_characters
                self._record_agent_run(db, job, "chief_architect", {"characters": created_characters, "_llm": character_meta, "preview_only": True}, {"instruction": instruction})

            if request.target in {"entities", "all"}:
                entity_templates = [
                    ("location", "关键地点", "第一卷反复出现的行动舞台。"),
                    ("organization", "隐秘组织", "掌握规则解释权的势力。"),
                    ("item", "核心物件", "连接角色秘密与世界观规则的信物。"),
                ]
                fallback_entities = []
                for index in range(request.count):
                    entity_type, label, description = entity_templates[index % len(entity_templates)]
                    fallback_entities.append(
                        {
                            "id": f"preview_ent_{index + 1}",
                            "project_id": project_id,
                            "entity_type": entity_type,
                            "name": f"{label}{index + 1}",
                            "importance_level": "major" if index == 0 else "medium",
                            "importance_score": max(45, 76 - index),
                            "description": f"{description} Agent 生成依据：{instruction}",
                            "current_status": "candidate",
                            "source": "agent",
                            "created_at": timestamp,
                            "updated_at": timestamp,
                        }
                    )
                entity_payload, entity_meta = call_agent_json(
                    llm_client=llm_client,
                    agent_name="canon_curator",
                    role=AGENT_SPECS_BY_NAME["canon_curator"].role,
                    system_prompt=AGENT_SPECS_BY_NAME["canon_curator"].prompt,
                    task="为项目生成候选剧情实体预览。必须输出 entities 数组；不要假定已写入正式设定。",
                    context={"project": serialize_project(project), "target": request.target, "instruction": instruction, "count": request.count, "preview_only": True},
                    fallback={"entities": fallback_entities},
                    model=request.model,
                )
                created_entities = [
                    merge_candidate(fallback, candidate, {"entity_type": "entity_type", "name": "name", "description": "description"})
                    for fallback, candidate in zip(fallback_entities, entity_payload.get("entities", []))
                ] or fallback_entities
                self._record_agent_run(db, job, "canon_curator", {"entities": created_entities, "_llm": entity_meta, "preview_only": True}, {"instruction": instruction})

            if request.target in {"world_facts", "all"}:
                fact_templates = [
                    ("culture", "社会禁忌", "能制造角色选择压力的公共规则。"),
                    ("history", "旧事件", "解释当前冲突来源的历史事实。"),
                    ("magic_rule", "能力规则", "限制角色行动并提供伏笔回收空间的规则。"),
                ]
                fallback_world_facts = []
                for index in range(request.count):
                    category, label, content = fact_templates[index % len(fact_templates)]
                    fallback_world_facts.append(
                        {
                            "id": f"preview_wld_{index + 1}",
                            "project_id": project_id,
                            "category": category,
                            "title": f"{label}{index + 1}",
                            "content": f"{content} Agent 生成依据：{instruction}",
                            "importance_level": "major" if index == 0 else "medium",
                            "importance_score": max(45, 80 - index),
                            "confidence": 0.65,
                            "source_chapter_id": None,
                            "related_entity_ids": [],
                            "created_at": timestamp,
                            "updated_at": timestamp,
                        }
                    )
                fact_payload, fact_meta = call_agent_json(
                    llm_client=llm_client,
                    agent_name="canon_curator",
                    role=AGENT_SPECS_BY_NAME["canon_curator"].role,
                    system_prompt=AGENT_SPECS_BY_NAME["canon_curator"].prompt,
                    task="为项目生成候选世界观事实预览。必须输出 world_facts 数组；不要假定已写入正式设定。",
                    context={"project": serialize_project(project), "target": request.target, "instruction": instruction, "count": request.count, "preview_only": True},
                    fallback={"world_facts": fallback_world_facts},
                    model=request.model,
                )
                created_world_facts = [
                    merge_candidate(fallback, candidate, {"category": "category", "title": "title", "content": "content"})
                    for fallback, candidate in zip(fallback_world_facts, fact_payload.get("world_facts", []))
                ] or fallback_world_facts
                self._record_agent_run(db, job, "canon_curator", {"world_facts": created_world_facts, "_llm": fact_meta, "preview_only": True}, {"instruction": instruction})

            proposals: list[dict[str, Any]] = []
            for item in created_characters:
                proposal = self._create_canon_proposal(
                    db,
                    project_id,
                    "character",
                    item,
                    source_job_id=job.id,
                    source_agent="chief_architect",
                    confidence=float(item.get("confidence") or 0.8),
                    reason=instruction,
                )
                proposals.append(serialize_canon_proposal(proposal))
            for item in created_entities:
                proposal = self._create_canon_proposal(
                    db,
                    project_id,
                    "entity",
                    item,
                    source_job_id=job.id,
                    source_agent="canon_curator",
                    confidence=float(item.get("confidence") or 0.8),
                    reason=instruction,
                )
                proposals.append(serialize_canon_proposal(proposal))
            for item in created_world_facts:
                proposal = self._create_canon_proposal(
                    db,
                    project_id,
                    "world_fact",
                    item,
                    source_chapter_id=item.get("source_chapter_id"),
                    source_job_id=job.id,
                    source_agent="canon_curator",
                    confidence=float(item.get("confidence") or 0.8),
                    reason=instruction,
                )
                proposals.append(serialize_canon_proposal(proposal))

            self._finish_job(
                db,
                job,
                {
                    "characters": created_characters,
                    "entities": created_entities,
                    "world_facts": created_world_facts,
                    "proposals": proposals,
                    "instruction": instruction,
                    "preview_only": True,
                },
            )
            db.commit()
            return {
                "job": serialize_job(job),
                "characters": created_characters,
                "entities": created_entities,
                "world_facts": created_world_facts,
                "proposals": proposals,
                "preview_only": True,
            }

        if request.target in {"characters", "all"}:
            existing_count = db.query(models.Character).filter(models.Character.project_id == project_id).count()
            role_templates = [
                ("关键盟友", "supporting", "major", 78),
                ("隐秘对手", "antagonist", "major", 76),
                ("线索见证人", "supporting", "medium", 62),
            ]
            rows = []
            for index in range(request.count):
                label, role_type, level, score = role_templates[index % len(role_templates)]
                name = f"{label}{existing_count + index + 1}"
                row = models.Character(
                    id=generate_id("chr"),
                    project_id=project_id,
                    name=name,
                    role=role_type,
                    role_type=role_type,
                    importance_level=level,
                    importance_score=max(45, score - index),
                    summary=f"Agent 根据“{instruction}”生成的{label}，用于提前完善角色卡。",
                    personality="目标明确，拥有可被剧情检验的弱点。",
                    goals_json=dumps(["推动第一卷主线", "制造与主角价值观相关的选择"]),
                    motivations_json=dumps(["保护自身秘密", "改变当前秩序"]),
                    character_arc="从功能性出场逐步显露个人选择与代价。",
                    current_status="candidate",
                    updated_reason="agent_assisted_setting_generation",
                    source="agent",
                )
                db.add(row)
                db.flush()
                self._ensure_graph_node(db, project_id, "character", row.id, row.name, row.importance_level, row.importance_score)
                rows.append(row)
            db.flush()
            character_payload, character_meta = call_agent_json(
                llm_client=llm_client,
                agent_name="chief_architect",
                role=AGENT_SPECS_BY_NAME["chief_architect"].role,
                system_prompt=AGENT_SPECS_BY_NAME["chief_architect"].prompt,
                task="为项目生成候选角色卡。必须输出 characters 数组。",
                context={"project": serialize_project(project), "target": request.target, "instruction": instruction, "count": request.count},
                fallback={"characters": [serialize_character(row) for row in rows]},
                model=request.model,
            )
            for row, candidate in zip(rows, character_payload.get("characters", [])):
                if not isinstance(candidate, dict):
                    continue
                row.name = str(candidate.get("name") or row.name)[:120]
                row.summary = str(candidate.get("summary") or candidate.get("profile") or row.summary)
                row.personality = str(candidate.get("personality") or row.personality)
                row.character_arc = str(candidate.get("character_arc") or candidate.get("arc") or row.character_arc)
                self._ensure_graph_node(db, project_id, "character", row.id, row.name, row.importance_level, row.importance_score)
            for row in rows:
                self._sync_canon_ref(
                    db,
                    project_id,
                    "character",
                    row,
                    source_job_id=job.id,
                    source_agent="chief_architect",
                    change_reason="agent_assisted_setting_generation",
                )
            created_characters = [serialize_character(row) for row in rows]
            self._record_agent_run(db, job, "chief_architect", {"characters": created_characters, "_llm": character_meta}, {"instruction": instruction})

        if request.target in {"entities", "all"}:
            existing_count = db.query(models.StoryEntity).filter(models.StoryEntity.project_id == project_id).count()
            entity_templates = [
                ("location", "关键地点", "第一卷反复出现的行动舞台。"),
                ("organization", "隐秘组织", "掌握规则解释权的势力。"),
                ("item", "核心物件", "连接角色秘密与世界观规则的信物。"),
            ]
            rows = []
            for index in range(request.count):
                entity_type, label, description = entity_templates[index % len(entity_templates)]
                row = models.StoryEntity(
                    id=generate_id("ent"),
                    project_id=project_id,
                    entity_type=entity_type,
                    name=f"{label}{existing_count + index + 1}",
                    importance_level="major" if index == 0 else "medium",
                    importance_score=max(45, 76 - index),
                    description=f"{description} Agent 生成依据：{instruction}",
                    current_status="candidate",
                    source="agent",
                )
                db.add(row)
                db.flush()
                self._ensure_graph_node(db, project_id, "entity", row.id, row.name, row.importance_level, row.importance_score)
                rows.append(row)
            db.flush()
            entity_payload, entity_meta = call_agent_json(
                llm_client=llm_client,
                agent_name="canon_curator",
                role=AGENT_SPECS_BY_NAME["canon_curator"].role,
                system_prompt=AGENT_SPECS_BY_NAME["canon_curator"].prompt,
                task="为项目生成候选剧情实体。必须输出 entities 数组。",
                context={"project": serialize_project(project), "target": request.target, "instruction": instruction, "count": request.count},
                fallback={"entities": [serialize_story_entity(row) for row in rows]},
                model=request.model,
            )
            for row, candidate in zip(rows, entity_payload.get("entities", [])):
                if not isinstance(candidate, dict):
                    continue
                row.name = str(candidate.get("name") or row.name)[:120]
                row.description = str(candidate.get("description") or row.description)
                self._ensure_graph_node(db, project_id, "entity", row.id, row.name, row.importance_level, row.importance_score)
            for row in rows:
                self._sync_canon_ref(
                    db,
                    project_id,
                    "entity",
                    row,
                    source_job_id=job.id,
                    source_agent="canon_curator",
                    change_reason="agent_assisted_setting_generation",
                )
            created_entities = [serialize_story_entity(row) for row in rows]
            self._record_agent_run(db, job, "canon_curator", {"entities": created_entities, "_llm": entity_meta}, {"instruction": instruction})

        if request.target in {"world_facts", "all"}:
            existing_count = db.query(models.WorldFact).filter(models.WorldFact.project_id == project_id).count()
            fact_templates = [
                ("culture", "社会禁忌", "能制造角色选择压力的公共规则。"),
                ("history", "旧事件", "解释当前冲突来源的历史事实。"),
                ("magic_rule", "能力规则", "限制角色行动并提供伏笔回收空间的规则。"),
            ]
            rows = []
            for index in range(request.count):
                category, label, content = fact_templates[index % len(fact_templates)]
                row = models.WorldFact(
                    id=generate_id("wld"),
                    project_id=project_id,
                    category=category,
                    title=f"{label}{existing_count + index + 1}",
                    content=f"{content} Agent 生成依据：{instruction}",
                    importance_level="major" if index == 0 else "medium",
                    importance_score=max(45, 80 - index),
                    confidence=0.65,
                    related_entity_ids_json="[]",
                )
                db.add(row)
                db.flush()
                self._ensure_graph_node(db, project_id, "world_fact", row.id, row.title, row.importance_level, row.importance_score)
                rows.append(row)
            db.flush()
            fact_payload, fact_meta = call_agent_json(
                llm_client=llm_client,
                agent_name="canon_curator",
                role=AGENT_SPECS_BY_NAME["canon_curator"].role,
                system_prompt=AGENT_SPECS_BY_NAME["canon_curator"].prompt,
                task="为项目生成候选世界观事实。必须输出 world_facts 数组。",
                context={"project": serialize_project(project), "target": request.target, "instruction": instruction, "count": request.count},
                fallback={"world_facts": [serialize_world_fact(row) for row in rows]},
                model=request.model,
            )
            for row, candidate in zip(rows, fact_payload.get("world_facts", [])):
                if not isinstance(candidate, dict):
                    continue
                row.title = str(candidate.get("title") or row.title)[:160]
                row.content = str(candidate.get("content") or row.content)
                self._ensure_graph_node(db, project_id, "world_fact", row.id, row.title, row.importance_level, row.importance_score)
            for row in rows:
                self._sync_canon_ref(
                    db,
                    project_id,
                    "world_fact",
                    row,
                    source_job_id=job.id,
                    source_agent="canon_curator",
                    change_reason="agent_assisted_setting_generation",
                    confidence=row.confidence,
                )
            created_world_facts = [serialize_world_fact(row) for row in rows]
            self._record_agent_run(db, job, "canon_curator", {"world_facts": created_world_facts, "_llm": fact_meta}, {"instruction": instruction})

        self._finish_job(
            db,
            job,
            {
                "characters": created_characters,
                "entities": created_entities,
                "world_facts": created_world_facts,
                "instruction": instruction,
            },
        )
        db.commit()
        return {
            "job": serialize_job(job),
            "characters": created_characters,
            "entities": created_entities,
            "world_facts": created_world_facts,
            "preview_only": False,
        }

    def get_graph(self, db: Session, project_id: str, chapter_id: str | None = None) -> dict:
        self._project(db, project_id)
        nodes = db.query(models.GraphNode).filter(models.GraphNode.project_id == project_id).all()
        edge_query = db.query(models.GraphEdge).filter(models.GraphEdge.project_id == project_id)
        if chapter_id:
            edge_query = edge_query.filter((models.GraphEdge.source_chapter_id == chapter_id) | (models.GraphEdge.source_chapter_id.is_(None)))
        edges = edge_query.all()
        return {"graph": {"nodes": [serialize_graph_node(node) for node in nodes], "edges": [serialize_graph_edge(edge) for edge in edges]}}

    def refresh_canon(self, db: Session, project_id: str) -> dict:
        project = self._project(db, project_id)
        chapters = db.query(models.Chapter).filter(models.Chapter.project_id == project_id, models.Chapter.final_text != "").all()
        updates = {"refreshed_chapters": len(chapters), "created_entities": 0, "created_world_facts": 0}
        for chapter in chapters:
            self._persist_canon_updates(
                db,
                project_id,
                chapter.id,
                {
                    "entity_updates": [{"name": f"第{chapter.chapter_no}章事件", "entity_type": "event", "importance_score": 55}],
                    "world_fact_updates": [{"title": f"第{chapter.chapter_no}章剧情事实", "category": "timeline", "confidence": 0.8}],
                },
            )
            updates["created_entities"] += 1
            updates["created_world_facts"] += 1
        db.commit()
        return {"project": serialize_project(project), "canon_updates": updates}

    def build_canon_context(self, db: Session, project_id: str, chapter_id: str | None = None) -> dict:
        project = self._project(db, project_id)
        story_bible = db.query(models.StoryBible).filter(models.StoryBible.project_id == project_id).first()
        characters = (
            db.query(models.Character)
            .filter(models.Character.project_id == project_id)
            .order_by(models.Character.importance_score.desc())
            .limit(12)
            .all()
        )
        facts = db.query(models.WorldFact).filter(models.WorldFact.project_id == project_id).order_by(models.WorldFact.importance_score.desc()).limit(20).all()
        entities = db.query(models.StoryEntity).filter(models.StoryEntity.project_id == project_id).order_by(models.StoryEntity.importance_score.desc()).limit(20).all()
        issues = db.query(models.ContinuityIssue).filter(models.ContinuityIssue.project_id == project_id, models.ContinuityIssue.status == "open").limit(20).all()
        chapter = db.get(models.Chapter, chapter_id) if chapter_id else None
        context = {
            "project": serialize_project(project),
            "story_bible": serialize_story_bible(story_bible) if story_bible else None,
            "chapter": serialize_chapter(chapter) if chapter else None,
            "characters": [serialize_character(item) for item in characters],
            "world_facts": [serialize_world_fact(item) for item in facts],
            "story_entities": [serialize_story_entity(item) for item in entities],
            "graph": self.get_graph(db, project_id, chapter_id).get("graph", {}),
            "unresolved_continuity_issues": [serialize_continuity_issue(item) for item in issues],
            "previous_summaries": [serialize_chapter(item) for item in db.query(models.Chapter).filter(models.Chapter.project_id == project_id, models.Chapter.summary != "").order_by(models.Chapter.chapter_no.desc()).limit(5).all()],
        }
        return {"canon_context": context}

    def list_versions(self, db: Session, chapter_id: str | None = None) -> dict:
        query = db.query(models.VersionSnapshot)
        if chapter_id:
            query = query.filter(models.VersionSnapshot.chapter_id == chapter_id)
        rows = query.order_by(models.VersionSnapshot.created_at.desc()).all()
        return {"versions": [serialize_version_snapshot(row) for row in rows]}

    def compare_versions(self, db: Session, request: VersionCompareRequest) -> dict:
        left = db.get(models.VersionSnapshot, request.left_version_id)
        right = db.get(models.VersionSnapshot, request.right_version_id)
        if left is None or right is None:
            raise _not_found("版本不存在")
        diff = list(difflib.unified_diff(left.content.splitlines(), right.content.splitlines(), fromfile=left.id, tofile=right.id, lineterm=""))
        return {"left": serialize_version_snapshot(left), "right": serialize_version_snapshot(right), "diff": diff}

    def rollback_version(self, db: Session, version_id: str, request: RollbackVersionRequest) -> dict:
        version = db.get(models.VersionSnapshot, version_id)
        if version is None:
            raise _not_found("版本不存在")
        if version.chapter_id:
            chapter = db.get(models.Chapter, version.chapter_id)
            if chapter:
                chapter.final_text = version.content
                chapter.draft_text = version.content
                chapter.status = "drafted"
                self._snapshot(db, chapter.project_id, chapter.id, version.job_id, "user", "chapter", version.content, request.user_note or "回滚版本")
        db.commit()
        return {"version": serialize_version_snapshot(version), "rolled_back": True}

    def branch_version(self, db: Session, version_id: str, request: BranchVersionRequest) -> dict:
        version = db.get(models.VersionSnapshot, version_id)
        if version is None:
            raise _not_found("版本不存在")
        clone = models.VersionSnapshot(
            id=generate_id("ver"),
            project_id=version.project_id,
            chapter_id=version.chapter_id,
            job_id=version.job_id,
            agent_name=version.agent_name,
            content_type=version.content_type,
            content=version.content,
            metadata_json=version.metadata_json,
            user_note=request.user_note,
            branch_name=request.branch_name,
        )
        db.add(clone)
        db.commit()
        return {"version": serialize_version_snapshot(clone)}

    def list_foreshadowing(self, db: Session, project_id: str) -> dict:
        self._project(db, project_id)
        rows = (
            db.query(models.ForeshadowingItem)
            .filter(models.ForeshadowingItem.project_id == project_id)
            .order_by(models.ForeshadowingItem.importance_score.desc(), models.ForeshadowingItem.updated_at.desc())
            .all()
        )
        return {"foreshadowing_items": [serialize_foreshadowing_item(row) for row in rows]}

    def create_foreshadowing(self, db: Session, project_id: str, request: CreateForeshadowingRequest) -> dict:
        self._project(db, project_id)
        row = models.ForeshadowingItem(
            id=generate_id("fsh"),
            project_id=project_id,
            chapter_id=request.chapter_id,
            content=request.content,
            planted_chapter_id=request.planted_chapter_id or request.chapter_id,
            planned_payoff_chapter_id=request.planned_payoff_chapter_id,
            actual_payoff_chapter_id=request.actual_payoff_chapter_id,
            planned_payoff=request.planned_payoff,
            payoff_status=request.payoff_status,
            importance_level=request.importance_level,
            importance_score=request.importance_score,
            related_character_ids_json=dumps(request.related_character_ids),
            related_entity_ids_json=dumps(request.related_entity_ids),
            source=request.source,
        )
        db.add(row)
        db.flush()
        self._sync_foreshadowing_graph(db, row)
        self._sync_canon_ref(db, project_id, "foreshadowing", row, source_chapter_id=row.planted_chapter_id, source_agent=row.source, change_reason="创建伏笔")
        db.commit()
        db.refresh(row)
        return {"foreshadowing_item": serialize_foreshadowing_item(row)}

    def update_foreshadowing(self, db: Session, project_id: str, item_id: str, request: UpdateForeshadowingRequest) -> dict:
        row = db.get(models.ForeshadowingItem, item_id)
        if row is None or row.project_id != project_id:
            raise _not_found("伏笔不存在")
        updates = request.model_dump(exclude_unset=True)
        before_content = self._canon_ref_content("foreshadowing", row)
        proposed_content = dict(before_content)
        for field, value in updates.items():
            if value is not None:
                proposed_content[field] = value
        self._guard_locked_fields_or_propose(db, project_id, "foreshadowing", item_id, str(updates.pop("source_agent", "manual") or "manual"), before_content, proposed_content)
        for field, value in updates.items():
            if value is None:
                continue
            if field in {"related_character_ids", "related_entity_ids"}:
                setattr(row, f"{field}_json", dumps(value))
            elif hasattr(row, field):
                setattr(row, field, value)
        self._sync_foreshadowing_graph(db, row)
        self._sync_canon_ref(db, project_id, "foreshadowing", row, source_chapter_id=row.planted_chapter_id, source_agent="manual", change_reason="更新伏笔")
        db.commit()
        db.refresh(row)
        return {"foreshadowing_item": serialize_foreshadowing_item(row)}

    def delete_foreshadowing(self, db: Session, project_id: str, item_id: str) -> dict:
        row = db.get(models.ForeshadowingItem, item_id)
        if row is None or row.project_id != project_id:
            raise _not_found("伏笔不存在")
        node = (
            db.query(models.GraphNode)
            .filter(models.GraphNode.project_id == project_id, models.GraphNode.node_type == "clue", models.GraphNode.ref_id == item_id)
            .first()
        )
        if node:
            db.query(models.GraphEdge).filter(or_(models.GraphEdge.source_node_id == node.id, models.GraphEdge.target_node_id == node.id)).delete(synchronize_session=False)
            db.delete(node)
        db.delete(row)
        db.commit()
        return {"deleted": True, "foreshadowing_id": item_id}

    def payoff_foreshadowing(self, db: Session, project_id: str, item_id: str, request: PayoffForeshadowingRequest) -> dict:
        row = db.get(models.ForeshadowingItem, item_id)
        if row is None or row.project_id != project_id:
            raise _not_found("伏笔不存在")
        row.payoff_status = "paid_off"
        row.actual_payoff_chapter_id = request.actual_payoff_chapter_id
        if request.payoff_note:
            row.planned_payoff = request.payoff_note
        self._sync_foreshadowing_graph(db, row, payoff=True)
        self._sync_canon_ref(db, project_id, "foreshadowing", row, source_chapter_id=request.actual_payoff_chapter_id, source_agent="manual", change_reason="回收伏笔")
        db.commit()
        db.refresh(row)
        return {"foreshadowing_item": serialize_foreshadowing_item(row)}

    def generate_summary(self, db: Session, request: SummaryRequest) -> dict:
        self._project(db, request.project_id)
        query = db.query(models.Chapter).filter(models.Chapter.project_id == request.project_id)
        if request.chapter_start:
            query = query.filter(models.Chapter.chapter_no >= request.chapter_start)
        if request.chapter_end:
            query = query.filter(models.Chapter.chapter_no <= request.chapter_end)
        chapters = query.order_by(models.Chapter.chapter_no.asc()).all()
        text = "；".join([chapter.summary or f"第{chapter.chapter_no}章：{chapter.outline}" for chapter in chapters]) or "暂无章节内容。"
        return {"summary": text[:800], "chapter_count": len(chapters)}

    def foreshadowing(self, db: Session, request: TextToolRequest) -> dict:
        context = self.build_canon_context(db, request.project_id, request.chapter_id)["canon_context"]
        characters = context.get("characters", [])
        entities = context.get("story_entities", [])
        first_character = characters[0] if characters else {}
        first_entity = entities[0] if entities else {}
        character_name = first_character.get("name", "主角")
        entity_name = first_entity.get("name", "关键线索")
        instruction = request.instruction or request.text or "围绕当前章节预埋可回收伏笔。"
        suggestions = [
            {
                "content": f"{entity_name}在本章出现一个反常细节，但角色暂时误解其用途。",
                "planned_payoff": "后续用该细节解释关键规则或反转角色认知。",
                "payoff_status": "candidate",
                "importance_level": "major",
                "importance_score": 82,
                "related_character_ids": [first_character.get("id")] if first_character.get("id") else [],
                "related_entity_ids": [first_entity.get("id")] if first_entity.get("id") else [],
                "source": "agent",
            },
            {
                "content": f"{character_name}无意中回避一个名字，暗示旧关系尚未公开。",
                "planned_payoff": "在人物关系冲突升级时回收，解释其选择代价。",
                "payoff_status": "candidate",
                "importance_level": "medium",
                "importance_score": 72,
                "related_character_ids": [first_character.get("id")] if first_character.get("id") else [],
                "related_entity_ids": [],
                "source": "agent",
            },
            {
                "content": f"当前章节结尾留下与“{instruction[:40]}”相关的异常结果。",
                "planned_payoff": "在 3-6 章后用一次行动失败或成功回收。",
                "payoff_status": "candidate",
                "importance_level": "medium",
                "importance_score": 68,
                "related_character_ids": [first_character.get("id")] if first_character.get("id") else [],
                "related_entity_ids": [first_entity.get("id")] if first_entity.get("id") else [],
                "source": "agent",
            },
        ]
        return {"suggestions": suggestions, "canon_context_used": {"characters": len(characters), "entities": len(entities), "chapter_id": request.chapter_id}}

    def cliffhanger(self, db: Session, request: TextToolRequest) -> dict:
        return {
            "suggestions": [
                "让角色发现一条与既有认知相反的证据。",
                "让盟友在结尾提出代价更高的选择。",
                "让一个低重要度实体突然连接到核心伏笔。",
            ]
        }

    def fact_check(self, db: Session, request: TextToolRequest) -> dict:
        return {"report": {"status": "passed_with_notes", "issues": [{"severity": "info", "message": "请确认专有名词是否符合项目世界观规则。"}]}}

    def consistency_check(self, db: Session, request: TextToolRequest) -> dict:
        context = self.build_canon_context(db, request.project_id, request.chapter_id)["canon_context"]
        return {"report": {"status": "checked", "context_items": len(context.get("characters", [])) + len(context.get("world_facts", [])), "issues": context.get("unresolved_continuity_issues", [])}}

    def learn_style(self, db: Session, request: LearnStyleRequest) -> dict:
        profile = models.StyleProfile(
            id=generate_id("sty"),
            project_id=request.project_id,
            name=request.name,
            sample_text=request.sample_text,
            profile=f"句长均值约 {max(1, len(request.sample_text) // max(1, request.sample_text.count('。') + 1))} 字；建议保持样本文本的节奏、意象密度和叙述距离。",
            active=1,
        )
        db.add(profile)
        db.commit()
        return {"style_profile": {"id": profile.id, "name": profile.name, "profile": profile.profile, "active": bool(profile.active)}}

    def query_knowledge(self, db: Session, request: QueryKnowledgeRequest) -> dict:
        characters = self.list_characters(db, request.project_id)["characters"]
        entities = self.list_entities(db, request.project_id)["entities"]
        facts = self.list_world_facts(db, request.project_id)["world_facts"]
        pool = characters + entities + facts
        terms = [term for term in request.question.replace("？", " ").replace("?", " ").split() if term]
        matches = [item for item in pool if any(term in json.dumps(item, ensure_ascii=False) for term in terms)] if terms else pool[:5]
        return {"answer": "已根据当前设定集返回相关条目。", "matches": matches[:10]}

    def write_generate(self, db: Session, request: WriteGenerateRequest) -> dict:
        if request.workflow_type == "plan_chapters":
            return self.plan_chapters(
                db,
                request.project_id,
                PlanChaptersRequest(
                    volume_title="自动规划",
                    start_chapter_no=1,
                    chapter_count=3,
                    outline_requirement=request.instruction or "规划下一组章节",
                    overwrite_existing=True,
                    idempotency_key=f"write-plan:{request.project_id}:{len(request.instruction)}",
                    model=request.model,
                ),
            )
        if not request.chapter_id:
            chapters = db.query(models.Chapter).filter(models.Chapter.project_id == request.project_id).order_by(models.Chapter.chapter_no.asc()).all()
            if not chapters:
                raise _bad_request("项目还没有章节，请先生成章节规划")
            request.chapter_id = chapters[0].id
        return self.draft_chapter(db, request.project_id, request.chapter_id, DraftChapterRequest(user_instruction=request.instruction, model=request.model))

    def batch_generate(self, db: Session, request: BatchGenerateRequest) -> dict:
        project = self._project(db, request.project_id)
        job = self._create_job(db, request.project_id, None, "batch_generate", request.model, request.model_dump(), total_steps=request.chapter_end - request.chapter_start + 1)
        generated = []
        for chapter_no in range(request.chapter_start, request.chapter_end + 1):
            chapter = db.query(models.Chapter).filter(models.Chapter.project_id == request.project_id, models.Chapter.chapter_no == chapter_no).first()
            if chapter is None:
                chapter = models.Chapter(
                    id=generate_id("chp"),
                    project_id=request.project_id,
                    volume_no=1,
                    chapter_no=chapter_no,
                    title=f"第{chapter_no}章",
                    outline="批量生成占位章节规划",
                    word_target=project.chapter_word_target,
                )
                db.add(chapter)
                db.flush()
            result = self.draft_chapter(
                db,
                request.project_id,
                chapter.id,
                DraftChapterRequest(
                    user_instruction="批量生成",
                    model=request.model,
                    idempotency_key=f"batch:{job.id}:{chapter.id}",
                ),
            )
            generated.append(result["chapter"])
        self._finish_job(db, job, {"chapters": generated})
        db.commit()
        return {"job": serialize_job(job), "chapters": generated}

    def export(self, db: Session, request: ExportRequest) -> dict:
        project = self._project(db, request.project_id)
        chapters_query = db.query(models.Chapter).filter(models.Chapter.project_id == request.project_id)
        if request.volume_no:
            chapters_query = chapters_query.filter(models.Chapter.volume_no == request.volume_no)
        if request.chapter_start:
            chapters_query = chapters_query.filter(models.Chapter.chapter_no >= request.chapter_start)
        if request.chapter_end:
            chapters_query = chapters_query.filter(models.Chapter.chapter_no <= request.chapter_end)
        chapters = chapters_query.order_by(models.Chapter.chapter_no.asc()).all()
        content = self._render_export_content(project, chapters, request)
        export_dir = Path(get_settings().job_artifact_dir).parent / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)
        export_id = generate_id("exp")
        suffix = {"markdown": "md", "word": "docx"}.get(request.format, request.format)
        path = export_dir / f"{export_id}.{suffix}"
        self._write_export_file(path, content, request.format, project.title)
        row = models.ExportJob(
            id=export_id,
            project_id=request.project_id,
            export_format=request.format,
            status="succeeded",
            options_json=dumps(request.model_dump()),
            output_path=str(path),
            finished_at=utcnow(),
        )
        db.add(row)
        db.commit()
        return {"export_job": serialize_export_job(row), "preview": content[:2000]}

    def export_templates(self) -> dict:
        return {
            "templates": [
                {"name": "default", "label": "通用格式"},
                {"name": "qidian", "label": "起点章节格式"},
                {"name": "jjwxc", "label": "晋江章节格式"},
                {"name": "fanqie", "label": "番茄章节格式"},
            ]
        }

    def create_export_template(self, request: ExportTemplateRequest) -> dict:
        return {"template": request.model_dump()}

    def _normalized_creation_basic(self, project: models.Project, basic_info: dict[str, Any]) -> dict[str, Any]:
        manual_tags = self._as_str_list(basic_info.get("manual_tags"))
        tags = [*self._as_str_list(basic_info.get("tags")), *manual_tags]
        genre = str(basic_info.get("genre") or project.genre or "类型小说")
        subgenres = self._as_str_list(basic_info.get("subgenres"))
        return {
            "channel": str(basic_info.get("channel") or "通用"),
            "genre": genre,
            "subgenres": subgenres,
            "tags": list(dict.fromkeys(tags)),
            "manual_tags": manual_tags,
            "target_reader": str(basic_info.get("target_reader") or project.target_reader or "类型小说读者"),
            "target_words": int(basic_info.get("target_words") or project.target_words or project.planned_chapter_count * project.chapter_word_target),
            "style": str(basic_info.get("style") or project.style_guide or "清晰、有悬念"),
            "initial_idea": str(basic_info.get("initial_idea") or project.initial_idea or project.premise),
        }

    def _creation_basic_suggestions_prompt_snapshot(self, basic: dict[str, Any], request: CreationBasicSuggestionsRequest) -> dict[str, Any]:
        return {
            "agent_name": "creation_basic_suggestions",
            "workflow_id": "creation_star_session",
            "required_inputs": ["basic_info", "manual_input", "previous_suggestions"],
            "context_summary": (
                f"频道={basic.get('channel')}；类型={basic.get('genre')}；细分={self._short('、'.join(self._as_str_list(basic.get('subgenres'))), 80)}；"
                f"标签={self._short('、'.join(self._as_str_list(basic.get('tags'))), 100)}；目标读者={self._short(basic.get('target_reader'), 100)}；"
                f"目标字数={basic.get('target_words')}；风格={self._short(basic.get('style'), 80)}；初始想法={self._short(basic.get('initial_idea'), 160)}；"
                f"额外约束={self._short(request.manual_input, 160)}。"
            ),
            "generation_settings": {
                "count": request.count,
                "temperature": 0.85,
                "refresh_policy": "avoid_previous_suggestions",
            },
            "output_schema": {
                "suggestions": [
                    {
                        "id": "idea_<index> | constraint_<index>",
                        "target": "initial_idea | manual_input",
                        "title": "短标题",
                        "content": "点击后追加到对应输入框的内容",
                        "tags": ["标签"],
                        "reason": "适配理由",
                    }
                ]
            },
        }

    def _local_creation_basic_suggestions(self, basic: dict[str, Any], manual_input: str, count: int) -> list[dict[str, Any]]:
        genre = str(basic.get("genre") or "类型小说")
        reader = str(basic.get("target_reader") or "类型小说读者")
        style = str(basic.get("style") or "清晰、有悬念")
        tags = self._as_str_list(basic.get("tags")) or [genre]
        seed = str(basic.get("initial_idea") or "主角从一次具体危机进入高压世界")
        idea_templates = [
            (
                "旧案入口",
                f"{seed}；开局让主角接触一件被压下的旧案，旧案同时暴露世界规则和第一位强阻力。",
                ["开局钩子", self._pick(tags, 0, genre)],
            ),
            (
                "规则漏洞",
                f"主角发现{genre}世界里一条只对底层无效的隐藏规则，并用它换来第一次胜利和更大代价。",
                ["规则反转", self._pick(tags, 1, genre)],
            ),
            (
                "关系压力",
                f"把主角最想保护的人放进制度缝隙里，让每次升级都同时带来关系误解和外部追捕。",
                ["人物羁绊", "代价机制"],
            ),
            (
                "升级阶梯",
                f"设计一条从个人危机到城市级、势力级、时代级的升级阶梯，每一阶段都替换新的压迫来源。",
                ["长篇容量", "卷纲支撑"],
            ),
        ]
        constraint_templates = [
            (
                "压迫优先",
                f"刷新抽卡时优先生成能持续压迫主角的制度、资源或身份规则，避免只写背景说明。",
                ["抽卡约束", "世界规则"],
            ),
            (
                "爽点绑定代价",
                f"面向{reader}，每个爽点都要绑定一个新问题或后续代价，不能只靠外挂碾压。",
                ["读者体验", "代价"],
            ),
            (
                "保留风格",
                f"输出保持{style}，但每张卡都要给出容易翻车的风险和可修改方向。",
                ["风格约束", "风险提示"],
            ),
            (
                "避开重复",
                f"继续刷新时避开上一批已有的世界规则、主角入口和卖点表达，额外参考：{manual_input or '暂无额外约束'}。",
                ["去重", "刷新"],
            ),
        ]
        suggestions: list[dict[str, Any]] = []
        for index, (title, content, item_tags) in enumerate(idea_templates, start=1):
            suggestions.append(
                {
                    "id": f"idea_local_{index}",
                    "target": "initial_idea",
                    "title": title,
                    "content": content,
                    "tags": item_tags,
                    "reason": "补足可进入世界观抽卡的主角入口、规则压力或长篇容量。",
                    "source": "local_fallback",
                }
            )
        for index, (title, content, item_tags) in enumerate(constraint_templates, start=1):
            suggestions.append(
                {
                    "id": f"constraint_local_{index}",
                    "target": "manual_input",
                    "title": title,
                    "content": content,
                    "tags": item_tags,
                    "reason": "作为抽卡约束传入后续逐卡生成，不会直接写入正式设定。",
                    "source": "local_fallback",
                }
            )
        return suggestions[: max(2, count)]

    def _normalize_creation_basic_suggestions(
        self,
        suggestions: Any,
        fallback: list[dict[str, Any]],
        count: int,
    ) -> list[dict[str, Any]]:
        raw_items = suggestions if isinstance(suggestions, list) else fallback
        normalized: list[dict[str, Any]] = []
        allowed_targets = {"initial_idea", "manual_input"}
        for index, item in enumerate(raw_items, start=1):
            if not isinstance(item, dict):
                continue
            target = str(item.get("target") or ("initial_idea" if index % 2 else "manual_input"))
            if target not in allowed_targets:
                target = "initial_idea" if len(normalized) % 2 == 0 else "manual_input"
            title = self._short(item.get("title"), 24) or ("想法建议" if target == "initial_idea" else "约束建议")
            content = str(item.get("content") or item.get("description") or "").strip()
            if not content:
                continue
            normalized.append(
                {
                    "id": str(item.get("id") or f"{target}_{index}"),
                    "target": target,
                    "title": title,
                    "content": content,
                    "tags": self._as_str_list(item.get("tags"))[:5],
                    "reason": self._short(item.get("reason"), 140),
                    "source": str(item.get("source") or "agent"),
                }
            )
        targets = {item["target"] for item in normalized}
        if not {"initial_idea", "manual_input"}.issubset(targets):
            existing_ids = {item["id"] for item in normalized}
            for item in fallback:
                if item["target"] not in targets and item["id"] not in existing_ids:
                    normalized.append(item)
                    targets.add(item["target"])
        return normalized[: max(2, count)]

    def _dedupe_creation_basic_suggestions(
        self,
        suggestions: list[dict[str, Any]],
        previous_suggestions: list[dict[str, Any]],
        fallback: list[dict[str, Any]],
        count: int,
    ) -> list[dict[str, Any]]:
        previous_keys = {
            self._creation_basic_suggestion_key(item)
            for item in previous_suggestions
            if isinstance(item, dict) and self._creation_basic_suggestion_key(item)
        }
        if not previous_keys:
            return suggestions[: max(2, count)]
        result: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in suggestions:
            key = self._creation_basic_suggestion_key(item)
            if not key or key in previous_keys or key in seen:
                continue
            result.append(item)
            seen.add(key)
        for item in fallback:
            key = self._creation_basic_suggestion_key(item)
            if key and key not in previous_keys and key not in seen:
                result.append(item)
                seen.add(key)
            if len(result) >= count:
                break
        return (result or suggestions)[: max(2, count)]

    def _creation_basic_suggestion_key(self, item: dict[str, Any]) -> str:
        return "||".join([str(item.get("target") or "").strip(), str(item.get("title") or "").strip(), str(item.get("content") or "").strip()])

    def _creation_session(self, db: Session, project_id: str, session_id: str) -> models.CreationSession:
        session = db.get(models.CreationSession, session_id)
        if session is None or session.project_id != project_id:
            raise _not_found("创作 Star 会话不存在")
        return session

    def _creation_session_state(self, session: models.CreationSession) -> dict[str, Any]:
        state = loads(session.state_json, {})
        return state if isinstance(state, dict) else {}

    def _save_creation_session_state(self, session: models.CreationSession, state: dict[str, Any]) -> None:
        session.state_json = dumps(state)
        session.updated_at = utcnow()

    def _reset_creation_session_after(self, state: dict[str, Any], step: str) -> None:
        downstream_keys = {
            "project_seed",
            "core_conflict_system",
            "novel_constitution",
            "constitution_review",
            "canon_candidates",
            "project_bible",
            "world_rules",
            "confirmed_canon",
        }
        if step == "worldview":
            downstream_keys.update(
                {
                    "worldview_candidates",
                    "selected_worldview",
                    "protagonist_candidates",
                    "selected_protagonist",
                    "title_candidates",
                    "selected_title",
                    "market_position_candidates",
                    "market_position",
                }
            )
        elif step == "protagonist":
            downstream_keys.update(
                {
                    "protagonist_candidates",
                    "selected_protagonist",
                    "title_candidates",
                    "selected_title",
                    "market_position_candidates",
                    "market_position",
                }
            )
        elif step == "market_position":
            downstream_keys.update({"title_candidates", "selected_title", "market_position_candidates", "market_position"})
        for key in downstream_keys:
            if key.endswith("_candidates"):
                state[key] = []
            else:
                state[key] = {}

    def _require_creation_constitution_ready(self, state: dict[str, Any]) -> dict[str, Any]:
        review = state.get("constitution_review")
        if not isinstance(review, dict) or not review:
            raise _bad_request("请先完成小说宪法压力测试")
        status = str(review.get("status") or "")
        blocking = review.get("blocking_issues")
        has_blocking = isinstance(blocking, list) and bool(blocking)
        if status not in {"passed", "passed_with_notes"} or has_blocking:
            raise _bad_request(
                "小说宪法压力测试未通过，不能进入正典预览或提交",
                {"status": status, "blocking_issues": blocking or []},
            )
        return review

    def _require_approved_canon_sections(self, approved_sections: list[str] | None) -> tuple[str, ...]:
        if approved_sections is None:
            return CREATION_CANON_APPROVAL_SECTIONS
        approved = set(approved_sections)
        required = set(CREATION_CANON_APPROVAL_SECTIONS)
        missing = sorted(required - approved)
        unknown = sorted(approved - required)
        if missing or unknown:
            raise _bad_request("正典审批项不完整", {"missing": missing, "unknown": unknown})
        return CREATION_CANON_APPROVAL_SECTIONS

    def _creation_worldview_agent_name(self) -> str:
        return "creation_worldview_draw"

    def _creation_worldview_system_prompt(self) -> str:
        return load_catalog_prompt("creation_worldview_draw")

    def _creation_worldview_runtime_strategy(self) -> dict[str, Any]:
        legacy_prompt_chars = (
            len(AGENT_SPECS_BY_NAME["creation_star"].prompt)
            + len(load_catalog_prompt("core_conflict_system"))
            + len(load_catalog_prompt("novel_constitution"))
        )
        dedicated_prompt_chars = len(self._creation_worldview_system_prompt())
        return {
            "selected": "dedicated_worldview_prompt",
            "reason": "世界观抽卡只需要候选世界规则和冲突发动机种子；核心矛盾系统和小说宪法延后到用户选定世界观后生成。",
            "legacy_total_prompt_chars": legacy_prompt_chars,
            "dedicated_prompt_chars": dedicated_prompt_chars,
            "comparison_basis": "prompt_chars_before_remote_call",
        }

    def _creation_protagonist_agent_name(self) -> str:
        return "creation_protagonist_draw"

    def _creation_protagonist_system_prompt(self) -> str:
        return load_catalog_prompt("creation_protagonist_draw")

    def _creation_protagonist_runtime_strategy(self) -> dict[str, Any]:
        legacy_prompt_chars = (
            len(AGENT_SPECS_BY_NAME["creation_star"].prompt)
            + len(load_catalog_prompt("core_conflict_system"))
            + len(load_catalog_prompt("novel_constitution"))
        )
        dedicated_prompt_chars = len(self._creation_protagonist_system_prompt())
        return {
            "selected": "dedicated_protagonist_prompt",
            "reason": "主角人设抽卡只需要候选主角、能力代价、关系钩子和主角侧 conflict_seed；核心矛盾系统和小说宪法延后到用户确认立项种子后生成。",
            "legacy_total_prompt_chars": legacy_prompt_chars,
            "dedicated_prompt_chars": dedicated_prompt_chars,
            "comparison_basis": "prompt_chars_before_remote_call",
        }

    def _run_creation_star_draw_step(
        self,
        db: Session,
        project: models.Project,
        step: str,
        basic: dict[str, Any],
        selected_worldview: dict[str, Any],
        selected_protagonist: dict[str, Any],
        project_bible: dict[str, Any],
        world_rules: dict[str, Any],
        count: int,
        manual_input: str,
        model: str | None,
        job_type: str,
        previous_cards: list[dict[str, Any]] | None = None,
    ) -> tuple[dict[str, Any], models.GenerationJob]:
        request = CreationStarDrawRequest(
            step=step,  # type: ignore[arg-type]
            basic_info=basic,
            selected_worldview=selected_worldview,
            selected_protagonist=selected_protagonist,
            project_bible=project_bible,
            world_rules=world_rules,
            count=count,
            manual_input=manual_input,
            model=model,
        )
        job = self._create_job(db, project.id, None, job_type, model, request.model_dump(), total_steps=1)
        draw_id = generate_id("draw")
        rng = random.SystemRandom()
        prompt_snapshot = self._creation_star_prompt_snapshot(request, basic, previous_cards=previous_cards)
        if step == "worldview":
            fallback: dict[str, Any] = {
                "step": step,
                "cards": self._creation_worldview_cards(basic, count, manual_input, draw_id, rng),
            }
        elif step == "protagonist":
            fallback = {
                "step": step,
                "cards": self._creation_protagonist_cards(basic, selected_worldview, count, manual_input, draw_id, rng),
            }
        elif step == "title":
            fallback = {
                "step": step,
                "cards": self._creation_title_cards(
                    basic,
                    selected_worldview,
                    selected_protagonist,
                    project_bible,
                    world_rules,
                    count,
                    manual_input,
                    draw_id,
                    rng,
                ),
            }
        else:
            raise _bad_request("不支持的创作 Star 会话步骤", {"step": step})
        fallback["draw_id"] = draw_id
        fallback["prompt_snapshot"] = prompt_snapshot
        if step == "worldview":
            agent_name = self._creation_worldview_agent_name()
            role = "世界观抽卡 Agent"
            system_prompt = self._creation_worldview_system_prompt()
            task = f"执行创作 Star 世界观逐卡抽卡。count={count} 时只输出本轮新增世界观候选；不要生成核心矛盾系统或小说宪法。"
        elif step == "protagonist":
            agent_name = self._creation_protagonist_agent_name()
            role = "主角人设抽卡 Agent"
            system_prompt = self._creation_protagonist_system_prompt()
            task = f"执行创作 Star 主角人设逐卡抽卡。count={count} 时只输出本轮新增主角候选；不要生成核心矛盾系统或小说宪法。"
        else:
            agent_name = "creation_star"
            role = AGENT_SPECS_BY_NAME["creation_star"].role
            system_prompt = AGENT_SPECS_BY_NAME["creation_star"].prompt
            task = f"执行解耦创作 Star 的 {step} 单步生成。count={count} 时只输出本轮新增候选。"
        payload, llm_meta = call_agent_json(
            llm_client=llm_client,
            agent_name=agent_name,
            role=role,
            system_prompt=system_prompt,
            task=task,
            context={
                "project": serialize_project(project),
                "request": request.model_dump(),
                "basic_info": basic,
                "prompt_snapshot": prompt_snapshot,
                "fallback_output": fallback,
            },
            fallback=fallback,
            model=model,
        )
        if not isinstance(payload, dict):
            payload = fallback
        cards = payload.get("cards")
        if not isinstance(cards, list) or not cards:
            payload["cards"] = fallback["cards"]
        if step == "worldview":
            payload["cards"] = self._normalize_creation_worldview_cards(payload["cards"])
        if step == "protagonist":
            payload["cards"] = self._normalize_creation_protagonist_cards(payload["cards"])
        payload["step"] = payload.get("step") or step
        payload["draw_id"] = payload.get("draw_id") or draw_id
        payload["prompt_snapshot"] = payload.get("prompt_snapshot") or prompt_snapshot
        payload["_llm"] = llm_meta
        self._record_agent_run(
            db,
            job,
            agent_name,
            payload,
            {"project": serialize_project(project), "request": request.model_dump(), "prompt_snapshot": prompt_snapshot},
        )
        return payload, job

    def _run_structured_creation_agent(
        self,
        db: Session,
        project: models.Project,
        job_type: str,
        agent_name: str,
        task: str,
        context: dict[str, Any],
        fallback: dict[str, Any],
        model: str | None,
    ) -> tuple[dict[str, Any], models.GenerationJob, dict[str, Any]]:
        job = self._create_job(db, project.id, None, job_type, model, context, total_steps=1)
        payload, llm_meta = call_agent_json(
            llm_client=llm_client,
            agent_name=agent_name,
            role=AGENT_SPECS_BY_NAME[agent_name].role,
            system_prompt=AGENT_SPECS_BY_NAME[agent_name].prompt,
            task=task,
            context={**context, "fallback_output": fallback},
            fallback=fallback,
            model=model,
        )
        return payload if isinstance(payload, dict) else fallback, job, llm_meta

    def _creation_market_position_cards(
        self,
        basic: dict[str, Any],
        worldview: dict[str, Any],
        protagonist: dict[str, Any],
        title_cards: list[dict[str, Any]],
        count: int,
        job_id: str,
    ) -> list[dict[str, Any]]:
        tags = self._as_str_list(basic.get("tags")) or self._as_str_list(worldview.get("tags")) or [basic.get("genre", "类型小说")]
        title = title_cards[0].get("title") if title_cards else worldview.get("title", basic.get("genre", "新书"))
        reader = basic.get("target_reader") or "类型小说读者"
        selling = title_cards[0].get("selling_point") if title_cards else worldview.get("selling_point", "高概念长篇卖点")
        cards = []
        for index in range(max(1, count)):
            tag = self._pick(tags, index, "成长")
            cards.append(
                {
                    "id": f"market_{job_id[-8:]}_{index + 1}",
                    "title": f"{basic.get('genre', '类型')} · {tag} · {title}",
                    "target_reader": reader,
                    "platform_fit": basic.get("channel", "通用"),
                    "selling_point": selling,
                    "hook": worldview.get("conflict_hook") or protagonist.get("long_term_goal") or "主角正面撞上旧秩序。",
                    "risk": worldview.get("risk") or "需要在前三章快速展示规则、代价和主角欲望。",
                    "tags": list(dict.fromkeys([*tags[:4], str(basic.get("genre") or "类型小说")])),
                    "source": "agent",
                }
            )
        return cards

    def _require_project_seed(self, state: dict[str, Any]) -> dict[str, Any]:
        seed = state.get("project_seed")
        if not isinstance(seed, dict) or not seed:
            raise _bad_request("请先确认立项种子")
        return seed

    def _core_conflict_from_seed(self, seed: dict[str, Any]) -> dict[str, Any]:
        worldview = seed.get("selected_worldview") if isinstance(seed.get("selected_worldview"), dict) else {}
        protagonist = seed.get("selected_protagonist") if isinstance(seed.get("selected_protagonist"), dict) else {}
        basic = seed.get("basic_info") if isinstance(seed.get("basic_info"), dict) else {}
        protagonist_name = str(protagonist.get("name") or "主角")
        desire = str(protagonist.get("long_term_goal") or "夺回选择命运的主动权")
        world_pressure = str(worldview.get("conflict_hook") or "旧秩序、资源垄断和关系压力阻止主角前进")
        core_conflict = f"{protagonist_name}想要{desire}，但{world_pressure}。"
        return {
            "protagonist_desire": desire,
            "world_resistance": world_pressure,
            "core_conflict": core_conflict,
            "external_resistance": worldview.get("description") or f"{basic.get('genre', '世界')}规则持续制造外部压力。",
            "internal_resistance": protagonist.get("inner_wound") or "主角害怕再次被旧秩序定义。",
            "relationship_resistance": protagonist.get("relationship_hook") or "关键关系既提供帮助也制造误判。",
            "institutional_resistance": "资格、资源、榜单、势力分配共同构成制度阻力。",
            "typical_cost": "每次前进都必须付出资源、关系、名誉或认知代价。",
            "long_form_engine": "欲望、阻力、选择和代价可持续循环升级，支撑长篇连载。",
            "possible_endpoint": "主角重新定义规则，但必须承担新秩序的代价。",
            "theme_question": "普通人能否在不被旧秩序同化的前提下夺回选择权。",
        }

    def _novel_constitution_from_seed(self, seed: dict[str, Any], core_conflict: dict[str, Any]) -> dict[str, Any]:
        basic = seed.get("basic_info") if isinstance(seed.get("basic_info"), dict) else {}
        worldview = seed.get("selected_worldview") if isinstance(seed.get("selected_worldview"), dict) else {}
        protagonist = seed.get("selected_protagonist") if isinstance(seed.get("selected_protagonist"), dict) else {}
        tags = self._as_str_list(basic.get("tags")) or self._as_str_list(worldview.get("tags"))
        return {
            "basic_positioning": {
                "genre": basic.get("genre") or "类型小说",
                "tone": basic.get("style") or "清晰、有悬念",
                "target_reader_experience": basic.get("target_reader") or "类型小说读者",
                "story_keywords": tags[:8],
                "type_promise": worldview.get("selling_point") or "稳定兑现主角成长、规则压力和阶段爽点。",
            },
            "core_narrative_engine": core_conflict,
            "protagonist_arc": {
                "opening_state": protagonist.get("identity") or "被旧秩序限制的人",
                "surface_goal": protagonist.get("long_term_goal") or core_conflict.get("protagonist_desire"),
                "deep_need": "夺回解释自身命运的主动权。",
                "largest_flaw": protagonist.get("weakness") or "习惯独自承担代价。",
                "ending_state": core_conflict.get("possible_endpoint"),
            },
            "world_rules": {
                "primary_logic": worldview.get("description") or "世界规则必须持续制造选择与代价。",
                "power_distribution": "权力和资源由明面制度与暗面势力共同分配。",
                "rules_not_to_break": ["胜利必须有代价", "新增设定必须可追溯", "主角认知不能越过亲历和被告知的信息"],
            },
            "character_functions": {
                "protagonist": protagonist.get("name") or "主角",
                "antagonist": "代表旧秩序合理性与压迫性的核心对手",
                "mirror": "走向另一种答案的镜像人物",
                "ally": "既帮助主角也迫使主角付出关系代价的人",
            },
            "theme_pressure": {
                "core_question": core_conflict.get("theme_question"),
                "wrong_answer": "只要赢就可以复制旧秩序。",
                "final_answer": "真正的胜利是让后来者不必重复同样的压迫。",
            },
            "cost_mechanism": ["获得力量必须付出代价", "赢得关系必须承担误解或牺牲", "靠近真相会改变主角处境"],
            "forbidden_directions": ["无铺垫反转", "机械降神", "无代价复活", "主角动机突变"],
            "long_form_sustainability": "核心矛盾可通过地图、制度、关系、真相和代价逐层升级。",
        }

    def _constitution_review_from_constitution(self, constitution: dict[str, Any]) -> dict[str, Any]:
        engine = constitution.get("core_narrative_engine") if isinstance(constitution.get("core_narrative_engine"), dict) else {}
        return {
            "status": "passed_with_notes",
            "largest_strength": "核心矛盾、代价机制和世界规则能形成持续推进。",
            "largest_risk": "需要在章纲阶段持续检查爽点兑现和设定边界，避免规则只停留在说明层。",
            "blocking_issues": [],
            "revision_suggestions": ["前三章尽快展示主角欲望、世界阻力和一次明确代价。", "卷纲中为每卷设置一条不可逆状态变化。"],
            "recommended_next_stage": "canon_preview" if engine else "core_conflict",
        }

    def _project_bible_from_creation_state(self, state: dict[str, Any]) -> dict[str, Any]:
        seed = state.get("project_seed") if isinstance(state.get("project_seed"), dict) else {}
        constitution = state.get("novel_constitution") if isinstance(state.get("novel_constitution"), dict) else {}
        core = state.get("core_conflict_system") if isinstance(state.get("core_conflict_system"), dict) else {}
        protagonist = seed.get("selected_protagonist") if isinstance(seed.get("selected_protagonist"), dict) else {}
        keywords = self._as_str_list(constitution.get("basic_positioning", {}).get("story_keywords") if isinstance(constitution.get("basic_positioning"), dict) else [])
        return {
            "核心命题": constitution.get("theme_pressure", {}).get("core_question") if isinstance(constitution.get("theme_pressure"), dict) else core.get("theme_question", ""),
            "核心矛盾": core.get("core_conflict", ""),
            "主角长期目标": protagonist.get("long_term_goal") or core.get("protagonist_desire", ""),
            "最终结局方向": core.get("possible_endpoint", ""),
            "主线关键词": keywords or ["成长", "代价", "破局"],
        }

    def _world_rules_from_creation_state(self, state: dict[str, Any]) -> dict[str, Any]:
        constitution = state.get("novel_constitution") if isinstance(state.get("novel_constitution"), dict) else {}
        rules = constitution.get("world_rules") if isinstance(constitution.get("world_rules"), dict) else {}
        return {
            "力量体系": self._as_str_list(rules.get("primary_logic")) or ["力量必须经由训练、资源或风险获得"],
            "社会结构": ["明面制度与暗面势力共同分配资源", "普通人需要通过资格或战绩获得上升通道"],
            "资源系统": ["资格", "证据", "训练资源", "关系信用"],
            "势力分布": ["官方机构", "旧秩序代表", "地下资源网络", "主角同盟"],
            "禁忌规则": self._as_str_list(constitution.get("forbidden_directions")) or ["无铺垫反转", "机械降神"],
            "不可违反设定": self._as_str_list(rules.get("rules_not_to_break")) or ["新增设定必须可追溯"],
        }

    def _canon_candidates_from_creation_state(self, project: models.Project, basic: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        seed = state.get("project_seed") if isinstance(state.get("project_seed"), dict) else {}
        worldview = seed.get("selected_worldview") if isinstance(seed.get("selected_worldview"), dict) else {}
        protagonist = seed.get("selected_protagonist") if isinstance(seed.get("selected_protagonist"), dict) else {}
        core = state.get("core_conflict_system") if isinstance(state.get("core_conflict_system"), dict) else self._core_conflict_from_seed(seed)
        constitution = state.get("novel_constitution") if isinstance(state.get("novel_constitution"), dict) else self._novel_constitution_from_seed(seed, core)
        project_bible = self._project_bible_from_creation_state({**state, "core_conflict_system": core, "novel_constitution": constitution})
        world_rules = self._world_rules_from_creation_state({**state, "novel_constitution": constitution})
        story_bible_candidate = {
            "world_setting": "\n".join(
                [
                    str(worldview.get("title") or project.title),
                    str(worldview.get("description") or project.premise),
                    "世界规则：" + "；".join(self._as_str_list(world_rules.get("不可违反设定"))),
                ]
            ),
            "main_conflict": project_bible.get("核心矛盾") or project.premise,
            "themes": project_bible.get("主线关键词") or [],
            "style_guide": basic.get("style") or project.style_guide,
            "narrative_pov": "third_person_limited",
            "forbidden_elements": world_rules.get("禁忌规则") or [],
            "continuity_rules": world_rules.get("不可违反设定") or [],
        }
        protagonist_name = str(protagonist.get("name") or "待定主角")
        return {
            "story_bible_candidate": story_bible_candidate,
            "character_candidates": [
                {
                    "name": protagonist_name,
                    "role_type": "protagonist",
                    "importance_level": "core",
                    "importance_score": 100,
                    "summary": protagonist.get("summary") or protagonist.get("identity") or "创作 Star 确认的主角。",
                    "goals": [project_bible.get("主角长期目标", "")],
                    "character_arc": protagonist.get("character_arc") or "从被规则限制到重新定义规则。",
                }
            ],
            "entity_candidates": [
                {"entity_type": "organization", "name": self._pick(self._as_str_list(world_rules.get("势力分布")), 0, "核心势力"), "importance_level": "core"},
                {"entity_type": "rule", "name": self._pick(self._as_str_list(world_rules.get("力量体系")), 0, "核心规则"), "importance_level": "core"},
            ],
            "world_fact_candidates": [
                {"category": "culture", "title": "核心命题", "content": project_bible.get("核心命题", ""), "importance_level": "core"},
                {"category": "politics", "title": "核心矛盾", "content": project_bible.get("核心矛盾", ""), "importance_level": "core"},
                {"category": "taboo", "title": "不可违反设定", "content": "；".join(self._as_str_list(world_rules.get("不可违反设定"))), "importance_level": "core"},
            ],
            "graph_candidate_edges": [
                {"source": protagonist_name, "target": worldview.get("title") or project.title, "edge_type": "rooted_in", "label": "主角由立项世界观生成"},
            ],
            "project_bible": project_bible,
            "world_rules": world_rules,
            "constitution_review": state.get("constitution_review", {}),
        }

    def _creation_worldview_step_prompt(self) -> str:
        return (
            "你正在执行创作 Star 的“世界观抽卡”环节。你的任务不是写正文，也不是写普通设定简介，"
            "而是生成可供作者选择和编辑的世界观候选卡。\n\n"
            "必须参考前序基本信息：频道、类型、细分类型、标签、目标读者、目标字数、风格、初始想法、"
            "用户手动补充，以及上一批候选摘要。\n\n"
            "每张卡必须像立项天花板测试：读者一眼能看出题材组合、世界为什么特殊、主角为什么会被卷入、"
            "冲突为什么能长期升级、爽点从哪里来。\n\n"
            "每批卡之间必须差异明显。差异不允许只体现在名称替换，而要体现在核心世界规则、社会压迫机制、"
            "主角切入方式、长线主线和爽点机制上。\n\n"
            "允许较高随机性和跨类型混搭，但内部逻辑必须自洽。不要提前写正文，不要替用户最终确认设定；"
            "所有输出都只是候选，用户确认后才允许写入正式设定集。"
        )

    def _normalize_creation_worldview_cards(self, cards: list[Any]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for index, raw_card in enumerate(cards):
            if not isinstance(raw_card, dict):
                continue
            card = dict(raw_card)
            if not card.get("id"):
                card["id"] = f"worldview_remote_{index + 1}"
            if not card.get("core_rule") and card.get("core_world_rule"):
                card["core_rule"] = card.get("core_world_rule")
            if not card.get("core_world_rule") and card.get("core_rule"):
                card["core_world_rule"] = card.get("core_rule")
            if not card.get("conflict_engine_seed") and card.get("conflict_hook"):
                card["conflict_engine_seed"] = card.get("conflict_hook")
            if not card.get("conflict_hook") and card.get("conflict_engine_seed"):
                card["conflict_hook"] = card.get("conflict_engine_seed")
            if not card.get("selling_point") and card.get("one_sentence_pitch"):
                card["selling_point"] = card.get("one_sentence_pitch")
            if not card.get("risk") and card.get("writing_risk"):
                card["risk"] = card.get("writing_risk")
            if not card.get("writing_risk") and card.get("risk"):
                card["writing_risk"] = card.get("risk")
            normalized.append(card)
        return normalized

    def _creation_worldview_output_schema(self) -> dict[str, Any]:
        return {
            "cards": [
                {
                    "id": "worldview_<draw>_<index>",
                    "title": "8-18 字，有网文立项感的世界观卡标题",
                    "summary": "一句话概括这个世界观",
                    "one_sentence_pitch": "一句话看出题材组合、核心规则、社会压力、主角入口和爽点来源",
                    "description": "说明世界基础设定、核心规则、社会压力和主角处境",
                    "genre_mix": ["类型组合 1", "类型组合 2"],
                    "core_world_rule": "这个世界最核心、最能持续制造剧情的运行规则",
                    "core_rule": "这个世界最核心、最能持续制造剧情的规则",
                    "social_pressure": "这个世界如何压迫主角或普通人",
                    "power_or_resource_system": "力量、资源、身份、系统、金手指或规则机制",
                    "conflict_engine_seed": "冲突发动机种子：可以在选定世界观后继续发展为核心矛盾系统的原始压力",
                    "protagonist_entry": "主角从哪里切入这个世界，为什么非他不可",
                    "long_form_potential": "为什么它能支撑长篇、多卷、多阶段升级",
                    "key_entities": ["关键组织、资源、地点、制度或禁忌"],
                    "rules_not_to_break": ["后续写作不能随便破坏的世界边界"],
                    "reader_hooks": ["爽点 1", "爽点 2", "爽点 3"],
                    "tags": ["标签 1", "标签 2", "标签 3", "标签 4"],
                    "selling_point": "面向目标读者的核心卖点",
                    "conflict_hook": "兼容字段，内容等同或略短于 conflict_engine_seed",
                    "writing_risk": "这个设定写作时最容易翻车的问题",
                    "risk": "这个设定写作时最容易翻车的问题",
                    "revision_hint": "用户手动修改时最值得调整的方向",
                    "difference_from_previous_batch": "与上一批候选在核心规则、社会压迫、主角入口或爽点机制上的差异",
                }
            ]
        }

    def _normalize_creation_protagonist_cards(self, cards: list[Any]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for index, raw_card in enumerate(cards):
            if not isinstance(raw_card, dict):
                continue
            card = dict(raw_card)
            if not card.get("id"):
                card["id"] = f"protagonist_remote_{index + 1}"
            if not card.get("long_term_goal") and card.get("long_term_desire"):
                card["long_term_goal"] = card.get("long_term_desire")
            if not card.get("long_term_desire") and card.get("long_term_goal"):
                card["long_term_desire"] = card.get("long_term_goal")
            if not card.get("character_arc") and card.get("growth_arc"):
                card["character_arc"] = card.get("growth_arc")
            if not card.get("growth_arc") and card.get("character_arc"):
                card["growth_arc"] = card.get("character_arc")
            relationship_hooks = card.get("relationship_hooks")
            if not card.get("relationship_hook") and isinstance(relationship_hooks, list):
                card["relationship_hook"] = "；".join(str(item) for item in relationship_hooks if item)
            if not isinstance(relationship_hooks, list) and card.get("relationship_hook"):
                card["relationship_hooks"] = [str(card.get("relationship_hook"))]
            if not card.get("risk") and card.get("writing_risk"):
                card["risk"] = card.get("writing_risk")
            if not card.get("writing_risk") and card.get("risk"):
                card["writing_risk"] = card.get("risk")
            if not card.get("summary") and card.get("one_sentence_pitch"):
                card["summary"] = card.get("one_sentence_pitch")
            normalized.append(card)
        return normalized

    def _creation_protagonist_output_schema(self) -> dict[str, Any]:
        return {
            "cards": [
                {
                    "id": "protagonist_<draw>_<index>",
                    "name": "主角名",
                    "title": "人设卡标题",
                    "one_sentence_pitch": "一句话说明这个主角为什么适合已选世界观",
                    "identity": "开局身份",
                    "opening_situation": "开局处境",
                    "world_rule_connection": "主角与世界核心规则的咬合点",
                    "long_term_desire": "长期欲望",
                    "long_term_goal": "兼容字段，内容等同或略短于 long_term_desire",
                    "immediate_goal": "开局可行动目标",
                    "inner_wound": "内在伤口",
                    "ability": "能力或优势",
                    "ability_cost": "能力代价",
                    "weakness": "弱点",
                    "secret": "秘密",
                    "growth_arc": "成长弧",
                    "character_arc": "兼容字段，内容等同或略短于 growth_arc",
                    "relationship_hooks": ["可制造冲突的关系钩子"],
                    "relationship_hook": "兼容字段，内容可从 relationship_hooks 中提炼",
                    "conflict_seed": "可进入下一阶段核心矛盾系统的主角侧种子，但不要展开成完整核心矛盾系统",
                    "reader_satisfaction": "读者爽点来源",
                    "long_form_potential": "长篇成长空间",
                    "writing_risk": "写作风险",
                    "risk": "兼容字段，内容等同或略短于 writing_risk",
                    "revision_hint": "修改建议",
                    "tags": ["标签 1", "标签 2", "标签 3"],
                }
            ]
        }

    def _creation_previous_worldviews_summary(self, previous_cards: list[dict[str, Any]] | None) -> str:
        if not previous_cards:
            return "无上一批候选。"
        pieces = []
        for card in previous_cards[-6:]:
            pieces.append(
                " / ".join(
                    [
                        self._short(card.get("title"), 36),
                        f"核心规则={self._short(card.get('core_rule'), 52)}",
                        f"社会压力={self._short(card.get('social_pressure'), 52)}",
                        f"主角入口={self._short(card.get('protagonist_entry'), 52)}",
                    ]
                )
            )
        return "\n".join(pieces)

    def _creation_previous_protagonists_summary(self, previous_cards: list[dict[str, Any]] | None) -> str:
        if not previous_cards:
            return "无上一批候选。"
        pieces = []
        for card in previous_cards[-6:]:
            pieces.append(
                " / ".join(
                    [
                        self._short(card.get("name") or card.get("title"), 36),
                        f"身份={self._short(card.get('identity'), 52)}",
                        f"欲望={self._short(card.get('long_term_desire') or card.get('long_term_goal'), 52)}",
                        f"代价={self._short(card.get('ability_cost'), 52)}",
                        f"关系={self._short(card.get('relationship_hook'), 52)}",
                    ]
                )
            )
        return "\n".join(pieces)

    def _creation_star_prompt_snapshot(
        self,
        request: CreationStarDrawRequest,
        basic: dict[str, Any],
        previous_cards: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        context_summary = self._creation_star_context_summary(request, basic)
        step_prompts = {
            "worldview": self._creation_worldview_step_prompt(),
            "protagonist": "生成主角人设抽卡：必须读取已选世界观，主角的身份、欲望、能力和伤口都要服务该世界观的核心规则与冲突。",
            "project_bible": "生成项目总设定表和世界观规则表：必须读取已选世界观与主角人设，形成可长期约束正文生成的正式设定候选。",
            "world_rules": "重抽世界观规则表：必须读取基本信息、已选世界观和主角人设，只调整规则表，不破坏已确认的主线方向。",
            "title": "生成书名抽卡：必须读取基本信息、已选世界观、已选主角、项目总设定表和世界观规则表，提供多种平台感书名方向。",
        }
        if request.step == "worldview":
            agent_name = self._creation_worldview_agent_name()
            prompt_id = "creation_worldview_draw"
            system_prompt = self._creation_worldview_system_prompt()
        elif request.step == "protagonist":
            agent_name = self._creation_protagonist_agent_name()
            prompt_id = "creation_protagonist_draw"
            system_prompt = self._creation_protagonist_system_prompt()
        else:
            agent_name = "creation_star"
            prompt_id = ""
            system_prompt = AGENT_SPECS_BY_NAME["creation_star"].prompt
        snapshot = {
            "agent_name": agent_name,
            "prompt_id": prompt_id,
            "system_prompt": system_prompt,
            "step_prompt": step_prompts.get(request.step, "生成创作 Star 候选卡。"),
            "context_summary": context_summary,
            "required_previous_data": {
                "worldview": ["basic_info"],
                "protagonist": ["basic_info", "selected_worldview"],
                "project_bible": ["basic_info", "selected_worldview", "selected_protagonist"],
                "world_rules": ["basic_info", "selected_worldview", "selected_protagonist"],
                "title": ["basic_info", "selected_worldview", "selected_protagonist", "project_bible", "world_rules"],
            }.get(request.step, []),
        }
        if request.step == "worldview":
            snapshot["previous_cards_summary"] = self._creation_previous_worldviews_summary(previous_cards)
            snapshot["output_schema"] = self._creation_worldview_output_schema()
            snapshot["runtime_strategy"] = self._creation_worldview_runtime_strategy()
            snapshot["generation_settings"] = {
                "temperature": 0.9,
                "top_p": 0.95,
                "max_tokens": 3000,
                "count": request.count,
                "presence_penalty": 0.4,
                "frequency_penalty": 0.3,
            }
            snapshot["dedupe_rules"] = [
                "不能使用与上一批相同的核心世界规则",
                "不能使用与上一批相同的社会压迫机制",
                "不能使用与上一批相同的主角切入方式",
                "不能只替换名词或地名",
            ]
        if request.step == "protagonist":
            snapshot["previous_cards_summary"] = self._creation_previous_protagonists_summary(previous_cards)
            snapshot["output_schema"] = self._creation_protagonist_output_schema()
            snapshot["runtime_strategy"] = self._creation_protagonist_runtime_strategy()
            snapshot["generation_settings"] = {
                "temperature": 0.88,
                "top_p": 0.95,
                "max_tokens": 3000,
                "count": request.count,
                "presence_penalty": 0.35,
                "frequency_penalty": 0.25,
            }
            snapshot["dedupe_rules"] = [
                "不能使用与上一批相同的开局身份",
                "不能使用与上一批相同的长期欲望",
                "不能使用与上一批相同的能力代价",
                "不能使用与上一批相同的关系钩子",
                "不能只替换姓名或职业",
            ]
        return snapshot

    def _creation_star_context_summary(self, request: CreationStarDrawRequest, basic: dict[str, Any]) -> str:
        worldview = request.selected_worldview
        protagonist = request.selected_protagonist
        project_bible = request.project_bible
        world_rules = request.world_rules
        pieces = [
            f"基本信息：频道={basic.get('channel')}；类型={basic.get('genre')}；细分={self._short('、'.join(basic.get('subgenres', [])), 80)}；标签={self._short('、'.join(basic.get('tags', [])), 100)}；目标读者={self._short(basic.get('target_reader'), 100)}；风格={self._short(basic.get('style'), 80)}；初始想法={self._short(basic.get('initial_idea'), 180)}。",
        ]
        if worldview:
            pieces.append(
                f"已选世界观：{self._short(worldview.get('title'), 80)}；{self._short(worldview.get('description'), 180)}；冲突钩子={self._short(worldview.get('conflict_hook'), 120)}。"
            )
        if protagonist:
            pieces.append(
                f"已选主角：{self._short(protagonist.get('name'), 60)}；身份={self._short(protagonist.get('identity'), 120)}；长期目标={self._short(protagonist.get('long_term_goal'), 140)}；成长弧={self._short(protagonist.get('character_arc'), 140)}。"
            )
        if project_bible:
            pieces.append(
                f"项目总设定：核心命题={self._short(project_bible.get('核心命题'), 180)}；核心矛盾={self._short(project_bible.get('核心矛盾'), 180)}；主线关键词={self._short('、'.join(self._as_str_list(project_bible.get('主线关键词'))), 100)}。"
            )
        if world_rules:
            pieces.append(
                f"世界观规则：力量体系={self._short('、'.join(self._as_str_list(world_rules.get('力量体系'))), 140)}；资源系统={self._short('、'.join(self._as_str_list(world_rules.get('资源系统'))), 140)}；不可违反设定={self._short('、'.join(self._as_str_list(world_rules.get('不可违反设定'))), 160)}。"
            )
        if request.manual_input:
            pieces.append(f"本轮额外要求：{self._short(request.manual_input, 160)}。")
        return "\n".join(pieces)

    def _short(self, value: Any, limit: int = 120) -> str:
        text = "、".join(self._as_str_list(value)) if isinstance(value, list) else str(value or "")
        text = " ".join(text.split())
        return text[:limit]

    def _random_cycle(self, values: list[Any], count: int, rng: random.SystemRandom) -> list[Any]:
        if not values:
            return []
        result: list[Any] = []
        while len(result) < count:
            batch = list(values)
            rng.shuffle(batch)
            result.extend(batch)
        return result[:count]

    def _creation_worldview_cards(
        self,
        basic: dict[str, Any],
        count: int,
        manual_input: str,
        draw_id: str,
        rng: random.SystemRandom,
    ) -> list[dict[str, Any]]:
        genre = basic["genre"]
        subgenre = self._pick(basic["subgenres"], 0, genre)
        tags = basic["tags"] or ["成长", "冲突", "悬念"]
        seeds = [
            ("灵气复苏，武道高考", "古老修行门派伪装成顶级教育集团，城市升学、资源垄断和武道资格绑定。"),
            ("财阀当道，隐世古宗", "现代都市表面由资本治理，暗面由宗门掌控经济命脉和超凡武力。"),
            ("深渊入侵，武馆镇守", "异次元裂缝降临各大城市，热武器失效，古武馆成为人类抵抗前线。"),
            ("宗门财团化，城市擂台", "宗门以财团、俱乐部和高校形态运作，天才争夺从考场延伸到地下擂台。"),
            ("气血镇诡，猎魔机构", "城市怪谈由气血低谷滋生，武者既是公务体系成员也是民间传说猎人。"),
            ("赛博高武，义体真气", "科技义体和传统真气互相排斥，主角夹在新旧秩序之间寻找第三道路。"),
            ("废土都市，遗迹复苏", "灾后城市围绕远古宗门遗迹建立，功法、粮食和安全区资格成为硬通货。"),
            ("黑暗森林，吃人魔窟", "修炼资源极度匮乏，所谓名门正派建立在吞噬他人气运的黑规则上。"),
            ("星际武道，都市星港", "地球都市成为星港，宗门跨星系开荒，武装势力和教育系统合一。"),
            ("规则校园，榜单支配", "校园、宗门和城市榜单绑定生存资源，违反排名规则的人会被系统性抹除。"),
            ("神明退场，职业武者", "神明留下的职业牌照成为城市阶层入口，普通人只能通过武考夺路。"),
            ("旧案封城，宗门审判", "一桩被宗门共同掩盖的旧案让城市成为封闭试炼场。"),
        ]
        pressures = ["升学筛选", "资源垄断", "身份债务", "榜单支配", "旧案追责", "边境危机", "信仰崩塌", "资本围猎"]
        tones = ["高压爽文", "悬疑升级", "群像暗线", "热血反抗", "轻脑洞", "冷峻权谋"]
        selected_seeds = self._random_cycle(seeds, count, rng)
        tag_offset = rng.randrange(len(tags)) if tags else 0
        resource_systems = [
            "资格牌照、考试名额和秘传功法共同构成上升通道",
            "气血值、债务契约和榜单排名绑定生存资源",
            "旧宗门遗产、城市许可证和黑市情报互相制衡",
            "义体零件、真气节点和官方积分决定阶层位置",
            "怪谈规则、镇压功勋和亲属担保共同决定安全区资格",
        ]
        protagonist_entries = [
            "主角从被筛掉的底层候选者切入，因一次违规操作看见规则漏洞",
            "主角卷入旧案重审，被迫在公开制度和暗面宗门之间求生",
            "主角原本只是旁观者，却因亲近之人被规则吞噬而必须破局",
            "主角掌握一条不被承认的成长路径，因此同时被官方和地下势力盯上",
            "主角被错误标记为危险样本，只能用反常识行动证明旧秩序有罪",
        ]
        long_form_engines = [
            "可通过考试、城市、势力、遗迹和真相五级地图持续扩展，每卷改变一层规则。",
            "资源争夺、身份晋升、关系误判和旧案真相能循环升级，适合多卷连载。",
            "每个阶段都能引出新的规则漏洞和更高层监管者，形成长期追读钩子。",
            "主角每次胜利都会暴露更深制度问题，推动个人爽点升级为世界级冲突。",
            "明线成长、暗线追凶、势力博弈和禁忌规则可并行推进，支撑长篇结构。",
        ]
        cards = []
        draw_key = draw_id.rsplit("_", 1)[-1][-6:]
        for index, (title, description) in enumerate(selected_seeds):
            tag_a = self._pick(tags, index + tag_offset, "成长")
            tag_b = self._pick(tags, index + tag_offset + 1, subgenre)
            pressure = self._pick(self._random_cycle(pressures, count, rng), index, "资源垄断")
            tone = self._pick(self._random_cycle(tones, count, rng), index, "热血反抗")
            resource_system = self._pick(self._random_cycle(resource_systems, count, rng), index, "资格与资源绑定")
            protagonist_entry = self._pick(self._random_cycle(protagonist_entries, count, rng), index, "主角从底层破局")
            long_form_potential = self._pick(self._random_cycle(long_form_engines, count, rng), index, "规则逐卷升级")
            core_rule = f"{pressure}不是背景，而是会惩罚越界者的硬规则；主角必须找到规则漏洞才能上升。"
            social_pressure = f"{pressure}把普通人的升学、工作、资源和亲密关系绑定在同一套评价体系里。"
            conflict_engine_seed = f"主角想夺回选择权，但维护{pressure}的组织会不断升级封锁与污名。"
            idea_hint = self._short(basic.get("initial_idea"), 42)
            one_sentence_pitch = f"{genre}/{subgenre}混合{tone}，以{pressure}作为硬规则，主角从规则漏洞切入并持续制造{tag_a}爽点。"
            cards.append(
                {
                    "id": f"worldview_{draw_key}_{index + 1}",
                    "title": title if not manual_input else f"{title}：{manual_input[:18]}",
                    "summary": f"{genre}/{subgenre}框架下，{pressure}变成可见规则，主角用非常规路径撬动旧秩序。",
                    "one_sentence_pitch": one_sentence_pitch,
                    "description": f"{description} 类型基底：{basic.get('channel')}/{genre}/{subgenre}；核心爽点围绕“{tag_a}”展开，主要社会压力是{pressure}。{('初始脑洞：' + idea_hint + '。') if idea_hint else ''}",
                    "genre_mix": list(dict.fromkeys([genre, subgenre, tag_a, tone]))[:4],
                    "core_world_rule": core_rule,
                    "core_rule": core_rule,
                    "social_pressure": social_pressure,
                    "power_or_resource_system": resource_system,
                    "conflict_engine_seed": conflict_engine_seed,
                    "protagonist_entry": protagonist_entry,
                    "long_form_potential": long_form_potential,
                    "key_entities": [f"{pressure}监管者", f"{subgenre}资源", "主角入口组织"],
                    "rules_not_to_break": ["胜利必须有代价", f"{pressure}必须能持续影响资源分配", "新规则必须能追溯到世界基础设定"],
                    "reader_hooks": [
                        f"{tag_a}带来的即时反馈",
                        f"主角钻破{pressure}规则的反差爽点",
                        f"{tone}节奏下的势力破防",
                    ],
                    "tags": list(dict.fromkeys([tag_a, tag_b, genre, subgenre]))[:5],
                    "selling_point": f"把{genre}的熟悉期待、{tone}的阅读节奏和{tag_a}的持续反馈绑定到可升级的社会规则里。",
                    "conflict_hook": conflict_engine_seed,
                    "writing_risk": f"需要尽早明确{tag_a}的代价和边界，避免只靠设定名词堆砌。",
                    "risk": f"需要尽早明确{tag_a}的代价和边界，避免只靠设定名词堆砌。",
                    "revision_hint": f"可重点调整{pressure}的表现形式、主角切入身份，或把{tag_b}强化成第一卷主钩子。",
                    "difference_from_previous_batch": f"本卡以{pressure}作为压迫核心，并以{protagonist_entry[:24]}作为主角入口。",
                    "draw_id": draw_id,
                    "source": "agent",
                }
            )
        return cards

    def _creation_protagonist_cards(
        self,
        basic: dict[str, Any],
        worldview: dict[str, Any],
        count: int,
        manual_input: str,
        draw_id: str,
        rng: random.SystemRandom,
    ) -> list[dict[str, Any]]:
        worldview_title = str(worldview.get("title") or "未定世界观")
        worldview_hook = str(worldview.get("conflict_hook") or "旧秩序阻挡主角接近核心资源")
        worldview_tags = self._as_str_list(worldview.get("tags"))
        archetypes = [
            ("沈砚", "被宗门财团拒收的武考复读生", "查清父亲旧案，夺回被剥夺的武道资格", "害怕自己永远只是被选择的人"),
            ("林照夜", "能看见气血债务的贫民区少女", "用规则漏洞救出被宗门抵押的家人", "每次使用能力都会暴露自身秘密"),
            ("许临", "前天才教练的失格弟子", "重建被污名化的旧武馆", "曾在关键比赛中临阵退缩"),
            ("周观澜", "财阀学校的奖学金边缘人", "进入核心圈层后掀翻资源垄断", "越成功越像自己讨厌的人"),
            ("姜别鹤", "替人背锅的地下擂台陪练", "找出真正操控擂台事故的人", "身体里封着失控的旧功法"),
            ("闻青棠", "记录禁忌规则的图书管理员", "证明禁术并非邪道而是被篡改的历史", "知识越多越容易成为规则祭品"),
        ]
        ability_angles = [
            "能把被忽略的规则转化为可验证的战术优势",
            "能从失败记录里反推出对手弱点",
            "能临时借用旧时代遗留规则，但每次都会留下痕迹",
            "能把他人的资源债务转成可谈判筹码",
            "能感知世界观规则的漏洞，却必须用个人代价补上",
        ]
        relationship_angles = [
            "与既是竞争者又是证人的关键角色形成互相利用的同盟",
            "被上层势力扶植为样板，又暗中拆解对方的控制链",
            "和一名掌握旧案碎片的反派继承人互相试探",
            "被导师当成棋子，却逐步夺回叙事主动权",
        ]
        selected_archetypes = self._random_cycle(archetypes, count, rng)
        draw_key = draw_id.rsplit("_", 1)[-1][-6:]
        cards = []
        for index, (name, identity, goal, wound) in enumerate(selected_archetypes):
            tag = self._pick([*worldview_tags, *basic.get("tags", [])], index + rng.randrange(3), "成长")
            ability = self._pick(self._random_cycle(ability_angles, count, rng), index, ability_angles[0])
            relationship_hook = self._pick(self._random_cycle(relationship_angles, count, rng), index, relationship_angles[0])
            if manual_input:
                identity = f"{identity}，同时背负“{manual_input[:18]}”"
            opening_situation = f"开局被“{worldview_title}”的核心规则卡住，必须用一次不可回头的行动证明自己仍有资格。"
            world_rule_connection = f"{name}的身份、能力或秘密与“{worldview_hook[:48]}”直接相连，越行动越暴露世界规则的漏洞。"
            ability_cost = "每次使用优势都会增加身份暴露、关系误解或资源债务。"
            conflict_seed = f"{name}想完成“{goal}”，但“{worldview_hook[:44]}”会持续把他推向更高代价。"
            reader_satisfaction = f"爽点来自{name}用“{tag}”反向拆解世界规则，而不是单纯变强碾压。"
            long_form_potential = "能力代价、身份升级、秘密揭露和关系重组可以按卷推进。"
            cards.append(
                {
                    "id": f"protagonist_{draw_key}_{index + 1}",
                    "name": name,
                    "title": identity,
                    "one_sentence_pitch": f"{name}是被“{worldview_title}”筛到边缘的人，却拥有反向理解规则的入口。",
                    "identity": identity,
                    "opening_situation": opening_situation,
                    "world_rule_connection": world_rule_connection,
                    "long_term_desire": f"{goal}，并正面撞上“{worldview_hook[:36]}”。",
                    "summary": f"{name}生在“{worldview_title}”的夹缝中，开局资源不足但能看见旧秩序的破绽；人物卖点要回应“{tag}”。",
                    "long_term_goal": f"{goal}，并正面撞上“{worldview_hook[:36]}”。",
                    "immediate_goal": "先夺回一个被世界规则剥夺的资格、亲密关系或公开解释权。",
                    "inner_wound": wound,
                    "ability": ability + "。",
                    "ability_cost": ability_cost,
                    "weakness": "不愿求助，容易把所有代价压到自己身上。",
                    "secret": "与世界观核心旧案存在未公开关联。",
                    "growth_arc": f"从被“{worldview_title}”筛掉的人，成长为重新定义规则的人。",
                    "character_arc": f"从被“{worldview_title}”筛掉的人，成长为重新定义规则的人。",
                    "relationship_hooks": [relationship_hook + "。"],
                    "relationship_hook": relationship_hook + "。",
                    "conflict_seed": conflict_seed,
                    "reader_satisfaction": reader_satisfaction,
                    "long_form_potential": long_form_potential,
                    "writing_risk": "需要让人物欲望先于设定展示，避免主角沦为解释世界规则的工具。",
                    "risk": "需要让人物欲望先于设定展示，避免主角沦为解释世界规则的工具。",
                    "revision_hint": "可重点调整私人欲望、能力代价或关键关系，让主角更像人而不是设定入口。",
                    "tags": list(dict.fromkeys([*basic.get("tags", [])[:3], "成长", "反转"])),
                    "source_worldview_id": worldview.get("id"),
                    "draw_id": draw_id,
                    "source": "agent",
                }
            )
        return cards

    def _creation_bible_and_rules(
        self,
        basic: dict[str, Any],
        worldview: dict[str, Any],
        protagonist: dict[str, Any],
        manual_input: str,
        rng: random.SystemRandom,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        protagonist_name = str(protagonist.get("name") or "主角")
        worldview_title = str(worldview.get("title") or "核心世界观")
        tags = basic.get("tags", [])
        extra_keywords = self._random_cycle(["成长", "代价", "复仇", "权力", "牺牲", "真相", "秩序", "救赎", "自由"], 4, rng)
        keywords = list(dict.fromkeys([*self._random_cycle(tags, min(len(tags), 4), rng), *extra_keywords]))[:6] or ["成长", "权力", "牺牲"]
        ending_options = [
            "主角揭开世界规则被篡改的真相，建立新的分配秩序，但必须付出私人关系或力量代价。",
            "主角赢得最终资格，却发现真正的胜利是让后来者不再重复自己的苦难。",
            "主角推翻旧秩序的一部分，同时保留必要的规则边界，留下可续写的新矛盾。",
            "主角没有成为新的掌权者，而是把权力拆成公开、可验证、可监督的规则。",
        ]
        force_pool = [
            "官方武考署",
            "宗门财团联盟",
            "地下擂台",
            "旧武馆遗民",
            "深渊/诡异污染源",
            "城市监管委员会",
            "学院董事会",
            "禁术收藏者",
            "遗迹开采公司",
        ]
        resource_pool = [
            "气血药剂",
            "遗迹名额",
            "宗门推荐信",
            "城市擂台积分",
            "禁术残页",
            "职业牌照",
            "榜单豁免权",
            "旧案证据链",
            "星港通行证",
        ]
        power_pool = [
            f"{worldview_title}专属的等级/资格双轨成长",
            "功法必须通过实战或代价验证",
            "越级战斗需要明确资源、情报或地形优势",
            "规则漏洞只能短期套利，长期会反噬关系网",
            "核心能力必须绑定人物伤口，不能无成本变强",
        ]
        social_pool = [
            "表层由学校、公司、官方赛事管理",
            "暗层由宗门、财阀、武馆和监管机构分配资格",
            "底层普通人通过考试、擂台或黑市获得上升通道",
            f"{protagonist_name}所在阶层天然缺少解释权",
            "公开规则与实际资源分配长期错位",
        ]
        project_bible = {
            "核心命题": f"在{worldview_title}中，普通人能否在不被旧秩序同化的前提下夺回选择权。",
            "核心矛盾": f"{protagonist_name}想实现“{protagonist.get('long_term_goal', '改变命运')}”，但宗门、财阀和既得利益者阻止真相公开。",
            "主角长期目标": str(protagonist.get("long_term_goal") or "打破资源垄断并完成自我证明"),
            "最终结局方向": self._pick(self._random_cycle(ending_options, 1, rng), 0, ending_options[0]),
            "主线关键词": keywords,
        }
        world_rules = {
            "力量体系": self._random_cycle(power_pool, 3, rng),
            "社会结构": self._random_cycle(social_pool, 3, rng),
            "资源系统": self._random_cycle(resource_pool, 5, rng),
            "势力分布": self._random_cycle(force_pool, 5, rng),
            "禁忌规则": ["不得无代价复活", "不得让高阶力量随意降维救场", "不得让核心证据脱离前文铺垫突然出现"],
            "不可违反设定": [
                "力量提升必须有训练、资源或风险来源",
                f"{worldview_title}的核心社会压力不能被单章轻易解决",
                f"{protagonist_name}每次胜利都必须改变关系网或暴露新风险",
            ],
        }
        if manual_input:
            project_bible["核心命题"] = f"{project_bible['核心命题']} 作者额外指定：{manual_input[:80]}"
        return project_bible, world_rules

    def _creation_title_cards(
        self,
        basic: dict[str, Any],
        worldview: dict[str, Any],
        protagonist: dict[str, Any],
        project_bible: dict[str, Any],
        world_rules: dict[str, Any],
        count: int,
        manual_input: str,
        draw_id: str,
        rng: random.SystemRandom,
    ) -> list[dict[str, Any]]:
        protagonist_name = str(protagonist.get("name") or "主角")
        worldview_title = str(worldview.get("title") or basic.get("genre") or "新世界")
        keywords = self._as_str_list(project_bible.get("主线关键词")) or basic.get("tags", []) or ["成长", "权力"]
        resources = self._as_str_list(world_rules.get("资源系统")) or ["资格", "气血", "旧案"]
        core_conflict = str(project_bible.get("核心矛盾") or worldview.get("conflict_hook") or "改写旧秩序")
        title_subject = self._pick([protagonist_name, self._pick(resources, 0, "资格"), self._pick(keywords, 0, "成长"), worldview_title], rng.randrange(4), protagonist_name)
        patterns = [
            f"{protagonist_name}的{self._pick(resources, 0, '武考')}名单",
            f"我在{worldview_title}里改写规则",
            f"{self._pick(keywords, 0, '成长')}之后，宗门向我低头",
            f"被退学后，我继承了旧武馆",
            f"高武都市：从{self._pick(resources, 1, '气血')}负债开始",
            f"旧案封城那一年",
            f"他们叫我规则漏洞",
            f"{worldview_title}：主角不是天才",
            f"我把宗门开成了学校",
            f"无月夜，气血发光",
            f"第一名的资格是偷来的",
            f"城市擂台没有明天",
        ]
        platform_styles = [
            ("强钩子口语", f"开局被夺{self._pick(resources, 0, '资格')}，我把规则重写了"),
            ("题材直给", f"{basic.get('genre', '类型')}：{worldview_title}"),
            ("人物命运", f"{protagonist_name}不接受被安排的人生"),
            ("悬疑旧案", f"{self._pick(resources, 1, '旧案')}失踪后的第七年"),
            ("热血爽点", f"从{self._pick(resources, 2, '擂台')}开始镇压旧秩序"),
            ("文学感", f"{title_subject}在无月夜发光"),
            ("反差脑洞", f"宗门财团叫我去上班"),
            ("长线史诗", f"{worldview_title}编年史"),
        ]
        selected_patterns = self._random_cycle([*patterns, *[item[1] for item in platform_styles]], count, rng)
        style_labels = self._random_cycle([item[0] for item in platform_styles], count, rng)
        cards = []
        draw_key = draw_id.rsplit("_", 1)[-1][-6:]
        for index, title in enumerate(selected_patterns):
            if manual_input:
                title = f"{title}：{manual_input[:10]}"
            keyword = self._pick(keywords, index + rng.randrange(max(len(keywords), 1)), "成长")
            resource = self._pick(resources, index + rng.randrange(max(len(resources), 1)), "资源")
            cards.append(
                {
                    "id": f"title_{draw_key}_{index + 1}",
                    "title": title[:60],
                    "description": f"命名方向：{self._pick(style_labels, index, '平台感')}。突出{basic.get('genre', '类型')}、{keyword}、{resource}和“{worldview_title}”的核心差异点。",
                    "tags": list(dict.fromkeys([basic.get("genre", "类型"), keyword, resource, self._pick(style_labels, index, "平台感")]))[:4],
                    "selling_point": f"标题直接暴露题材钩子、主角处境或爽点承诺，并呼应核心矛盾：{core_conflict[:42]}。",
                    "risk": "正式使用前可按目标平台调短或增强关键词密度，避免信息过载。",
                    "draw_id": draw_id,
                    "source": "agent",
                }
            )
        return cards

    def _upsert_creation_protagonist(
        self,
        db: Session,
        project_id: str,
        protagonist: dict[str, Any],
        basic: dict[str, Any],
        worldview: dict[str, Any],
    ) -> models.Character:
        name = str(protagonist.get("name") or "未命名主角")
        row = db.query(models.Character).filter(models.Character.project_id == project_id, models.Character.name == name).first()
        if row is None:
            row = models.Character(id=generate_id("chr"), project_id=project_id, name=name, role="protagonist", role_type="protagonist")
            db.add(row)
        row.role = "protagonist"
        row.role_type = "protagonist"
        row.importance_level = "core"
        row.importance_score = 100
        row.summary = str(protagonist.get("summary") or protagonist.get("identity") or "")
        row.personality = self._join_nonempty([str(protagonist.get("inner_wound", "")), str(protagonist.get("relationship_hook", ""))], "；")
        row.goals_json = dumps([str(protagonist.get("long_term_goal") or "完成长期目标")])
        row.motivations_json = dumps([f"回应{basic.get('channel', '通用')}读者期待", str(worldview.get("conflict_hook", ""))])
        row.secrets_json = dumps([str(protagonist.get("secret") or "与核心旧案相关")])
        row.abilities_json = dumps([str(protagonist.get("ability") or "规则洞察")])
        row.weaknesses_json = dumps([str(protagonist.get("weakness") or "过度独自承担")])
        row.character_arc = str(protagonist.get("character_arc") or "从被规则筛掉的人成长为改写规则的人")
        row.current_status = "active"
        row.updated_reason = "creation_star_commit"
        row.source = "agent"
        self._ensure_graph_node(db, project_id, "character", row.id, row.name, row.importance_level, row.importance_score)
        return row

    def _upsert_creation_entities(self, db: Session, project_id: str, worldview: dict[str, Any], world_rules: dict[str, Any]) -> list[models.StoryEntity]:
        candidates = [
            ("concept", str(worldview.get("title") or "核心世界观"), str(worldview.get("description") or "")),
            ("organization", self._pick(self._as_str_list(world_rules.get("势力分布")), 0, "核心势力"), "创作 Star 确认的主要势力。"),
            ("item", self._pick(self._as_str_list(world_rules.get("资源系统")), 0, "核心资源"), "创作 Star 确认的关键资源。"),
        ]
        rows: list[models.StoryEntity] = []
        for entity_type, name, description in candidates:
            row = self._upsert_entity(db, project_id, entity_type, name, 82, None)
            row.description = description
            row.importance_level = "major"
            row.current_status = "active"
            row.source = "creation_star"
            self._ensure_graph_node(db, project_id, "entity", row.id, row.name, row.importance_level, row.importance_score)
            rows.append(row)
        return rows

    def _upsert_creation_world_facts(
        self,
        db: Session,
        project_id: str,
        project_bible: dict[str, Any],
        world_rules: dict[str, Any],
        worldview: dict[str, Any],
    ) -> list[models.WorldFact]:
        facts: list[tuple[str, str, Any, str, int]] = [
            ("culture", "核心命题", project_bible.get("核心命题"), "core", 100),
            ("politics", "核心矛盾", project_bible.get("核心矛盾"), "core", 98),
            ("timeline", "主角长期目标", project_bible.get("主角长期目标"), "core", 94),
            ("timeline", "最终结局方向", project_bible.get("最终结局方向"), "major", 88),
            ("magic_rule", "力量体系", world_rules.get("力量体系"), "core", 96),
            ("culture", "社会结构", world_rules.get("社会结构"), "major", 88),
            ("economy", "资源系统", world_rules.get("资源系统"), "major", 84),
            ("organization", "势力分布", world_rules.get("势力分布"), "major", 86),
            ("taboo", "禁忌规则", world_rules.get("禁忌规则"), "core", 92),
            ("taboo", "不可违反设定", world_rules.get("不可违反设定"), "core", 95),
            ("history", "创作 Star 世界观", worldview.get("description"), "major", 86),
        ]
        rows: list[models.WorldFact] = []
        for category, title, content, level, score in facts:
            text = "；".join(self._as_str_list(content)) if isinstance(content, list) else str(content or "")
            row = self._upsert_world_fact(db, project_id, category, title, text, level, score, 0.9, None)
            self._ensure_graph_node(db, project_id, "world_fact", row.id, row.title, row.importance_level, row.importance_score)
            rows.append(row)
        return rows

    def _link_creation_graph(
        self,
        db: Session,
        project_id: str,
        character: models.Character,
        entities: list[models.StoryEntity],
        facts: list[models.WorldFact],
        worldview: dict[str, Any],
    ) -> None:
        character_node = self._ensure_graph_node(db, project_id, "character", character.id, character.name, character.importance_level, character.importance_score)
        for entity in entities:
            entity_node = self._ensure_graph_node(db, project_id, "entity", entity.id, entity.name, entity.importance_level, entity.importance_score)
            self._ensure_graph_edge(
                db,
                project_id,
                character_node.id,
                entity_node.id,
                "creation_star_related",
                "创作 Star 关联",
                82,
                confidence=0.9,
                evidence=str(worldview.get("title", "")),
            )
        for fact in facts[:4]:
            fact_node = self._ensure_graph_node(db, project_id, "world_fact", fact.id, fact.title, fact.importance_level, fact.importance_score)
            self._ensure_graph_edge(
                db,
                project_id,
                character_node.id,
                fact_node.id,
                "driven_by",
                "驱动主线",
                88,
                confidence=0.9,
                evidence=fact.content,
            )

    def _as_str_list(self, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str):
            return [item.strip() for item in value.replace("，", ",").replace("；", ",").split(",") if item.strip()]
        return [str(value)]

    def _pick(self, values: list[str], index: int, fallback: str) -> str:
        if not values:
            return fallback
        return values[index % len(values)]

    def _join_nonempty(self, values: list[str], separator: str) -> str:
        return separator.join([value for value in values if value])

    def _with_llm_meta(self, payload: Any, result: NovelStudioState, agent_name: str) -> dict[str, Any]:
        if isinstance(payload, dict):
            wrapped = dict(payload)
        else:
            wrapped = {"value": payload}
        meta = result.agent_llm_results.get(agent_name)
        if meta:
            wrapped["_llm"] = meta
        return wrapped

    def _run_outline_agents_with_llm(
        self,
        db: Session,
        project: models.Project | dict[str, Any],
        request: PlanChaptersRequest,
        outline_plan: dict[str, Any],
        agent_sequence: tuple[str, ...] | list[str] | None = None,
        progress_callback: Callable[[str, int], None] | None = None,
    ) -> dict[str, Any]:
        project_payload = project if isinstance(project, dict) else serialize_project(project)
        previous_outputs: list[dict[str, Any]] = []
        agent_outputs = dict(outline_plan.get("agent_outputs", {}))
        updated_outputs: dict[str, dict[str, Any]] = {}
        sequence = list(agent_sequence or OUTLINE_AGENT_SEQUENCE)
        output_key_by_agent = {
            "one_sentence_expansion": "故事核心",
            "genre_market_position": "类型卖点定位",
            "world_bible": "世界圣经",
            "protagonist_arc": "主角成长线",
            "character_tree": "人物树",
            "faction_conflict": "势力冲突表",
            "power_system": "金手指升级体系",
            "full_structure": "全书10卷总纲",
            "volume_outline": "逐卷50章大纲",
            "beat_control": "章节节拍表",
            "foreshadowing_manager": "伏笔账本",
            "logic_audit": "逻辑审计报告",
        }
        for index, agent_name in enumerate(sequence, start=1):
            spec = AGENT_SPECS_BY_NAME[agent_name]
            fallback = agent_outputs.get(agent_name, {})
            if not isinstance(fallback, dict):
                fallback = {"value": fallback}
            payload, meta = call_agent_json(
                llm_client=llm_client,
                agent_name=agent_name,
                role=spec.role,
                system_prompt=spec.prompt,
                task=(
                    "参与长篇大纲推演流水线。读取 structured_prompt、story_state、previous_agent_outputs 和当前 fallback，"
                    "输出该 Agent 负责的结构化 JSON。"
                ),
                context={
                    "project": project_payload,
                    "request": request.model_dump(),
                    "structured_prompt": outline_plan.get("structured_prompt", {}),
                    "story_state": outline_plan.get("story_state", {}),
                    "previous_agent_outputs": previous_outputs,
                    "fallback_output": fallback,
                },
                fallback=fallback,
                model=self._configured_model_for_agent(db, "outline_generation", agent_name, request.model),
            )
            payload["_llm"] = meta
            updated_outputs[agent_name] = payload
            previous_outputs.append({"agent_name": agent_name, "output": payload})
            if progress_callback is not None:
                progress_callback(agent_name, index)
        outline_plan["agent_outputs"] = updated_outputs
        for agent_name, output_key in output_key_by_agent.items():
            if agent_name in updated_outputs:
                payload = updated_outputs[agent_name]
                if agent_name == "volume_outline":
                    outline_plan[output_key] = payload.get("volumes", payload)
                elif agent_name == "beat_control":
                    outline_plan[output_key] = payload.get("beat_sheets", payload)
                else:
                    outline_plan[output_key] = payload
        if "13Agent推演链" in outline_plan:
            for item in outline_plan["13Agent推演链"]:
                meta = updated_outputs.get(item.get("agent_name", ""), {}).get("_llm", {})
                if meta:
                    item["used_remote_model"] = meta.get("used_remote_model", False)
                    item["provider"] = meta.get("provider", "")
                    item["model"] = meta.get("model", "")
        return outline_plan

    def _attach_outline_swarm_plan(
        self,
        db: Session,
        project: models.Project,
        request: PlanChaptersRequest,
        outline_plan: dict[str, Any],
        generation_kind: str = "legacy_plan_chapters",
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        project_snapshot = serialize_project(project)
        story_bible = db.query(models.StoryBible).filter(models.StoryBible.project_id == project.id).first()
        characters = db.query(models.Character).filter(models.Character.project_id == project.id).order_by(models.Character.importance_score.desc()).limit(8).all()
        entities = db.query(models.StoryEntity).filter(models.StoryEntity.project_id == project.id).order_by(models.StoryEntity.importance_score.desc()).limit(8).all()
        world_facts = db.query(models.WorldFact).filter(models.WorldFact.project_id == project.id).order_by(models.WorldFact.importance_score.desc()).limit(10).all()
        parameters = outline_plan.get("parameters", {})
        volume_target = int(request.volume_count or parameters.get("volume_count") or 1)
        chapter_target = int(request.chapter_count or parameters.get("chapters_per_volume") or 10)
        seed = {
            "title": project_snapshot["title"],
            "genre": project_snapshot["genre"],
            "target_reader": project_snapshot["target_reader"],
            "premise": project_snapshot["premise"],
            "one_sentence_story": project_snapshot["premise"],
            "worldview": story_bible.world_setting if story_bible and story_bible.world_setting else project_snapshot["premise"],
            "style": project_snapshot["style_guide"] or (story_bible.style_guide if story_bible else ""),
            "target_length": f"{parameters.get('target_words', project_snapshot.get('target_words'))}字，{volume_target}卷，本次推演{chapter_target}章",
            "outline_requirement": request.outline_requirement,
            "characters": [serialize_character(character) for character in characters],
            "story_entities": [serialize_story_entity(entity) for entity in entities],
            "world_facts": [serialize_world_fact(fact) for fact in world_facts],
            "legacy_outline_summary": {
                "structured_prompt": outline_plan.get("structured_prompt", {}),
                "world_bible": outline_plan.get("世界圣经", {}),
                "volume_count": len(outline_plan.get("10卷单元总表", [])),
            },
        }
        db.commit()
        swarm_result = run_outline_swarm(
            {
                "project_id": project_snapshot["id"],
                "seed": seed,
                "generation_kind": generation_kind,
                "volume_target": volume_target,
                "chapter_target": chapter_target,
                "model": request.model,
                "max_iterations": 18,
            },
            progress_callback=progress_callback,
        )
        outline_plan["outline_swarm"] = swarm_result
        outline_plan["outline_swarm_agent_trace"] = swarm_result.get("agent_trace", [])
        outline_plan["outline_swarm_llm_results"] = swarm_result.get("agent_llm_results", {})
        return outline_plan

    def _record_outline_swarm_agent_runs(
        self,
        db: Session,
        job: models.GenerationJob,
        request: PlanChaptersRequest,
        outline_plan: dict[str, Any],
    ) -> None:
        swarm_result = outline_plan.get("outline_swarm")
        if not isinstance(swarm_result, dict):
            return
        trace_events = swarm_result.get("agent_trace", [])
        if not isinstance(trace_events, list):
            trace_events = []
        llm_results = swarm_result.get("agent_llm_results", {})
        if not isinstance(llm_results, dict):
            llm_results = {}
        generation_kind = str(outline_plan.get("generation_kind") or "legacy_plan_chapters")
        expected_agent_names = set(_outline_swarm_agent_names_for_generation_kind(generation_kind))
        trace_agent_names = {
            str(event.get("agent_name"))
            for event in trace_events
            if isinstance(event, dict) and event.get("agent_name")
        }
        executed_agent_names = [agent_name for agent_name in OUTLINE_SWARM_AGENT_NAMES if agent_name in expected_agent_names and (agent_name in trace_agent_names or agent_name in llm_results)]
        for agent_name in executed_agent_names:
            agent_trace = [
                event
                for event in trace_events
                if isinstance(event, dict) and event.get("agent_name") == agent_name
            ]
            self._record_agent_run(
                db,
                job,
                f"outline_swarm/{agent_name}",
                {
                    "agent_name": agent_name,
                    "status": swarm_result.get("status", "running"),
                    "iteration_count": swarm_result.get("iteration_count"),
                    "active_agent": swarm_result.get("active_agent"),
                    "trace_events": agent_trace,
                    "_llm": llm_results.get(agent_name, {}),
                },
                {
                    "source": "outline_swarm",
                    "request": request.model_dump(),
                    "swarm_status": swarm_result.get("status", "running"),
                    "trace_event_count": len(agent_trace),
                },
            )

    def _agent_role_label(self, agent_name: str) -> str:
        normalized = agent_name.removeprefix("outline_swarm/")
        spec = AGENT_SPECS_BY_NAME.get(agent_name) or AGENT_SPECS_BY_NAME.get(normalized)
        if spec is not None:
            return spec.role
        swarm_labels = {
            "StoryDirectorAgent": "故事总导演 Agent",
            "WhyInterrogatorAgent": "为什么审问 Agent",
            "WorldSettingAgent": "世界构建 Agent",
            "CharacterArcAgent": "人物弧光 Agent",
            "ConflictAgent": "冲突矩阵 Agent",
            "PlotArchitectAgent": "长篇结构 Agent",
            "BeatControllerAgent": "章节节拍 Agent",
            "ForeshadowingAgent": "伏笔设计 Agent",
            "EntityExtractorAgent": "实体抽取 Agent",
            "ContinuityAgent": "连续性审查 Agent",
        }
        return swarm_labels.get(normalized, normalized)

    def _topology_node(
        self,
        node_id: str,
        label: str,
        node_type: str,
        summary: str,
        *,
        status: str = "succeeded",
        agent_name: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        node: dict[str, Any] = {
            "id": node_id,
            "label": label,
            "type": node_type,
            "status": status,
            "summary": summary,
        }
        if agent_name:
            node["agent_name"] = agent_name
        if payload:
            node["payload"] = payload
        return node

    def _topology_edge(self, source: str, target: str, edge_type: str, label: str, *, reason: str = "", weight: float = 1.0) -> dict[str, Any]:
        return {
            "id": f"{edge_type}:{source}->{target}",
            "source": source,
            "target": target,
            "type": edge_type,
            "label": label,
            "reason": reason,
            "weight": weight,
        }

    def _summarize_topology_payload(self, payload: Any, limit: int = 160) -> str:
        if payload is None:
            return ""
        if isinstance(payload, str):
            return payload[:limit]
        if isinstance(payload, dict):
            for key in ("kind", "title", "name", "question", "message", "summary", "content"):
                value = payload.get(key)
                if value:
                    return str(value)[:limit]
        return dumps(payload)[:limit]

    def _append_outline_artifact_nodes(
        self,
        nodes: list[dict[str, Any]],
        edges: list[dict[str, Any]],
        artifacts: list[dict[str, Any]],
        source_node_id: str,
        outline_plan: dict[str, Any],
        generation_kind: str,
    ) -> None:
        artifact_specs: list[tuple[str, str, str, Any]] = []
        if generation_kind == "chapter_outline_batch":
            artifact_specs.append(("chapter_outlines", "章纲候选", "chapter_outline", outline_plan.get("chapter_outlines", [])))
        else:
            artifact_specs.extend(
                [
                    ("book_outline", "全书总纲", "book_outline", outline_plan.get("book_outline") or outline_plan.get("全书10卷总纲")),
                    ("volume_outlines", "分卷卷纲", "volume_outline", outline_plan.get("volume_outlines") or outline_plan.get("10卷单元总表")),
                    ("logic_audit", "结构审查", "gate_report", outline_plan.get("逻辑审计报告")),
                ]
            )
        for key, label, artifact_type, payload in artifact_specs:
            if payload in (None, "", [], {}):
                continue
            count = len(payload) if isinstance(payload, list) else 1
            artifact_id = f"artifact:{generation_kind}:{key}"
            artifact = {
                "id": artifact_id,
                "label": label,
                "type": artifact_type,
                "summary": self._summarize_topology_payload(payload),
                "source_node_id": source_node_id,
                "count": count,
            }
            artifacts.append(artifact)
            nodes.append(self._topology_node(artifact_id, label, "artifact", f"生成 {count} 项{label}", payload={"artifact_type": artifact_type, "count": count}))
            edges.append(self._topology_edge(source_node_id, artifact_id, "emits", "产出", reason=f"{label}由推演链生成"))

    def _build_outline_topology(
        self,
        *,
        generation_kind: str,
        mode: str,
        agent_sequence: tuple[str, ...] | list[str],
        outline_plan: dict[str, Any],
        swarm_result: dict[str, Any] | None = None,
        planned_swarm_agents: tuple[str, ...] | list[str] = (),
        planned_status: str = "succeeded",
    ) -> dict[str, Any]:
        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []
        events: list[dict[str, Any]] = []
        artifacts: list[dict[str, Any]] = []
        seen_nodes: set[str] = set()
        agent_outputs = outline_plan.get("agent_outputs") if isinstance(outline_plan.get("agent_outputs"), dict) else {}
        swarm_llm_results = outline_plan.get("outline_swarm_llm_results") if isinstance(outline_plan.get("outline_swarm_llm_results"), dict) else {}
        allowed_swarm_agent_names = set(_outline_swarm_agent_names_for_generation_kind(generation_kind))

        def llm_meta_for(agent_name: str) -> dict[str, Any]:
            normalized = agent_name.removeprefix("outline_swarm/")
            if agent_name.startswith("outline_swarm/"):
                meta = swarm_llm_results.get(normalized)
                return meta if isinstance(meta, dict) else {}
            output = agent_outputs.get(agent_name)
            if isinstance(output, dict) and isinstance(output.get("_llm"), dict):
                return output["_llm"]
            return {}

        def add_agent(agent_name: str, *, prefix: str = "agent", status: str = "succeeded", summary: str | None = None) -> str:
            node_id = f"{prefix}:{agent_name}"
            if node_id not in seen_nodes:
                seen_nodes.add(node_id)
                llm_meta = llm_meta_for(agent_name)
                payload = {"llm": llm_meta} if llm_meta else None
                nodes.append(
                    self._topology_node(
                        node_id,
                        self._agent_role_label(agent_name),
                        "agent",
                        summary or f"{self._agent_role_label(agent_name)}参与{generation_kind}推演。",
                        status=status,
                        agent_name=agent_name,
                        payload=payload,
                    )
                )
            return node_id

        previous_node_id = ""
        for agent_name in agent_sequence:
            node_id = add_agent(agent_name, status=planned_status)
            events.append(
                {
                    "id": f"event:{generation_kind}:{agent_name}:linear",
                    "agent_name": agent_name,
                    "event_type": "agent_step",
                    "message": "线性大纲 Agent 完成结构推演",
                    "node_id": node_id,
                }
            )
            if previous_node_id:
                edges.append(self._topology_edge(previous_node_id, node_id, "handoff", "交接", reason="线性 Agent 顺序执行"))
            previous_node_id = node_id

        trace_events = []
        if swarm_result and isinstance(swarm_result.get("agent_trace"), list):
            trace_events = [event for event in swarm_result["agent_trace"] if isinstance(event, dict)]
        if planned_swarm_agents and (not trace_events or planned_status != "succeeded"):
            previous_planned_node_id = previous_node_id
            for agent_name in planned_swarm_agents:
                node_id = add_agent(
                    f"outline_swarm/{agent_name}",
                    prefix="agent",
                    status=planned_status,
                    summary=f"{self._agent_role_label(agent_name)}计划参与{generation_kind}拓扑推演。",
                )
                if previous_planned_node_id:
                    edges.append(self._topology_edge(previous_planned_node_id, node_id, "handoff", "计划交接", reason="任务创建时的拓扑骨架"))
                previous_planned_node_id = node_id
        previous_swarm_node_id = ""
        first_swarm_node_id = ""
        for index, event in enumerate(trace_events):
            agent_name = str(event.get("agent_name") or "outline_swarm")
            if agent_name not in allowed_swarm_agent_names:
                continue
            node_id = add_agent(f"outline_swarm/{agent_name}", prefix="agent")
            first_swarm_node_id = first_swarm_node_id or node_id
            event_id = f"event:{generation_kind}:swarm:{index}"
            event_type = str(event.get("event_type") or "agent_step")
            payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
            events.append(
                {
                    "id": event_id,
                    "timestamp": event.get("timestamp"),
                    "agent_name": agent_name,
                    "event_type": event_type,
                    "message": event.get("message", ""),
                    "node_id": node_id,
                    "payload": payload,
                }
            )
            next_agent = payload.get("next_agent")
            if event_type == "agent_step" and next_agent and str(next_agent) in allowed_swarm_agent_names:
                target_node_id = add_agent(f"outline_swarm/{next_agent}", prefix="agent")
                edges.append(self._topology_edge(node_id, target_node_id, "handoff", "Swarm 交接", reason=str(event.get("message") or "")))
            elif previous_swarm_node_id and previous_swarm_node_id != node_id:
                edges.append(self._topology_edge(previous_swarm_node_id, node_id, "depends_on", "承接", reason="Swarm trace 顺序承接", weight=0.7))
            if event_type in TOPOLOGY_ARTIFACT_EVENT_TYPES:
                artifact_id = f"artifact:{generation_kind}:trace:{index}"
                artifact = {
                    "id": artifact_id,
                    "label": str(event.get("message") or event_type),
                    "type": event_type,
                    "summary": self._summarize_topology_payload(payload),
                    "source_node_id": node_id,
                    "count": 1,
                }
                artifacts.append(artifact)
                nodes.append(self._topology_node(artifact_id, artifact["label"], "artifact", artifact["summary"], payload={"artifact_type": event_type}))
                edges.append(self._topology_edge(node_id, artifact_id, "emits", "记录产物", reason=event_type))
            previous_swarm_node_id = node_id

        if first_swarm_node_id and previous_node_id:
            edges.append(self._topology_edge(previous_node_id, first_swarm_node_id, "handoff", "进入拓扑推演", reason="线性结构交给 Swarm 做动态推演"))

        source_node_id = previous_swarm_node_id or previous_node_id or (nodes[-1]["id"] if nodes else "agent:outline")
        self._append_outline_artifact_nodes(nodes, edges, artifacts, source_node_id, outline_plan, generation_kind)
        revision_route = outline_plan.get("revision_route") if isinstance(outline_plan.get("revision_route"), dict) else {}
        if revision_route.get("revision_required"):
            route_node_id = f"decision:{generation_kind}:revision_route"
            nodes.append(
                self._topology_node(
                    route_node_id,
                    "返工路由",
                    "decision",
                    "逻辑审计发现阻塞问题，按问题类型路由回对应 Agent。",
                    status="blocked",
                    payload={"revision_route": revision_route},
                )
            )
            edges.append(self._topology_edge(source_node_id, route_node_id, "blocks", "触发返工", reason="logic_audit blocking / needs_revision"))
            for route in revision_route.get("routes", []):
                if not isinstance(route, dict):
                    continue
                target_agent = str(route.get("to_agent") or "")
                if not target_agent:
                    continue
                target_node_id = add_agent(target_agent, status="pending")
                edges.append(self._topology_edge(route_node_id, target_node_id, "revises", "返工", reason=str(route.get("reason") or "")))
        metrics = {
            "mode": mode,
            "node_count": len(nodes),
            "edge_count": len(edges),
            "event_count": len(events),
            "artifact_count": len(artifacts),
            "agent_count": len([node for node in nodes if node.get("type") == "agent"]),
        }
        return {
            "mode": mode,
            "generation_kind": generation_kind,
            "nodes": nodes,
            "edges": edges,
            "events": events,
            "artifacts": artifacts,
            "metrics": metrics,
        }

    def _project(self, db: Session, project_id: str) -> models.Project:
        project = db.get(models.Project, project_id)
        if project is None:
            raise _not_found("项目不存在")
        return project

    def _story_bible(self, db: Session, project_id: str) -> models.StoryBible:
        story_bible = db.query(models.StoryBible).filter(models.StoryBible.project_id == project_id).first()
        if story_bible is None:
            raise _not_found("故事圣经不存在")
        return story_bible

    def _chapter(self, db: Session, project_id: str, chapter_id: str) -> models.Chapter:
        chapter = db.get(models.Chapter, chapter_id)
        if chapter is None or chapter.project_id != project_id:
            raise _not_found("章节不存在")
        return chapter

    def _state_from_project(self, db: Session, project: models.Project, job_id: str) -> NovelStudioState:
        story_bible = db.query(models.StoryBible).filter(models.StoryBible.project_id == project.id).first()
        return NovelStudioState(
            project_id=project.id,
            title=project.title,
            genre=project.genre,
            target_words=project.target_words or project.planned_chapter_count * project.chapter_word_target,
            target_chapters=project.planned_chapter_count,
            current_volume=project.current_volume,
            current_chapter=project.current_chapter,
            target_reader=project.target_reader,
            premise=project.premise,
            style_guide=project.style_guide,
            initial_idea=project.initial_idea,
            world_setting=story_bible.world_setting if story_bible else "",
            story_bible=serialize_story_bible(story_bible) if story_bible else {},
            characters=[serialize_character(item) for item in db.query(models.Character).filter(models.Character.project_id == project.id).all()],
            world_facts=[serialize_world_fact(item) for item in db.query(models.WorldFact).filter(models.WorldFact.project_id == project.id).all()],
            story_entities=[serialize_story_entity(item) for item in db.query(models.StoryEntity).filter(models.StoryEntity.project_id == project.id).all()],
            job_id=job_id,
        )

    def _create_job(
        self,
        db: Session,
        project_id: str,
        chapter_id: str | None,
        job_type: str,
        requested_model: str | None,
        request_payload: dict,
        idempotency_key: str | None = None,
        total_steps: int = 1,
        queued: bool = False,
    ) -> models.GenerationJob:
        provider = LLMProviderResolver(get_settings()).resolve(requested_model)
        now = utcnow()
        job = models.GenerationJob(
            id=generate_id("job"),
            project_id=project_id,
            chapter_id=chapter_id,
            job_type=job_type,
            status="queued" if queued else "running",
            run_id=generate_id("run"),
            idempotency_key=idempotency_key or f"{job_type}:{project_id}:{chapter_id or 'project'}:{generate_id('idem')}",
            model=provider.model,
            request_json=dumps({**request_payload, "provider": provider.provider, "has_api_key": bool(provider.api_key)}),
            progress_json=dumps(
                {
                    "current_step": "queued" if queued else "running",
                    "total_steps": total_steps,
                    "completed_steps": 0,
                    "message": "任务已入队，等待后台推演" if queued else "工作流正在执行",
                }
            ),
            current_agent="",
            started_at=None if queued else now,
            heartbeat_at=now,
        )
        db.add(job)
        db.flush()
        return job

    def _plan_request_from_job(self, job: models.GenerationJob) -> PlanChaptersRequest:
        payload = loads(job.request_json, {})
        allowed = {field: payload[field] for field in PlanChaptersRequest.model_fields if field in payload}
        allowed["async_mode"] = False
        return PlanChaptersRequest.model_validate(allowed)

    def _book_outline_request_from_job(self, job: models.GenerationJob) -> BookOutlineGenerateRequest:
        payload = loads(job.request_json, {})
        allowed = {field: payload[field] for field in BookOutlineGenerateRequest.model_fields if field in payload}
        allowed["async_mode"] = False
        return BookOutlineGenerateRequest.model_validate(allowed)

    def _chapter_outline_batch_request_from_job(self, job: models.GenerationJob) -> ChapterOutlineBatchGenerateRequest:
        payload = loads(job.request_json, {})
        allowed = {field: payload[field] for field in ChapterOutlineBatchGenerateRequest.model_fields if field in payload}
        allowed["async_mode"] = False
        return ChapterOutlineBatchGenerateRequest.model_validate(allowed)

    def _book_outline_to_plan_request(self, project: models.Project, request: BookOutlineGenerateRequest) -> PlanChaptersRequest:
        chapter_count = max(1, min(100, int(request.chapters_per_volume or 50)))
        topology_instruction = (
            "拓扑推演开启：按 Agent 交接、依赖、产物、审查和候选正典关系组织推演；不得减少总纲、卷纲字段或内容量。"
            if request.use_topology_inference
            else "拓扑推演关闭：按线性 Agent 链生成；不得减少总纲、卷纲字段或内容量，并保持与拓扑模式基本一致的输出结构。"
        )
        return PlanChaptersRequest(
            volume_title="第一卷",
            start_chapter_no=1,
            chapter_count=chapter_count,
            outline_requirement=f"{request.outline_requirement}\n\n{topology_instruction}",
            overwrite_existing=True,
            idempotency_key=f"{request.idempotency_key}:internal-plan",
            target_words=request.target_words or project.target_words or max(30000, project.planned_chapter_count * project.chapter_word_target),
            volume_count=request.volume_count,
            chapters_per_volume=request.chapters_per_volume,
            chapter_word_target=request.chapter_word_target or project.chapter_word_target,
            model=request.model,
            async_mode=False,
        )

    def _build_initial_book_outline_plan(self, db: Session, project: models.Project, request: BookOutlineGenerateRequest) -> dict[str, Any]:
        plan_request = self._book_outline_to_plan_request(project, request)
        outline_plan: dict[str, Any] = {
            "generation_kind": "book_outline",
            "parameters": {
                "target_words": plan_request.target_words,
                "volume_count": plan_request.volume_count,
                "chapters_per_volume": plan_request.chapters_per_volume,
                "chapter_word_target": plan_request.chapter_word_target,
                "use_topology_inference": request.use_topology_inference,
            },
            "book_outline": {},
            "volume_outlines": [],
            "10卷单元总表": [],
            "change_summary": {},
            "revision_route": {"revision_required": False, "routes": [], "issues": [], "status": "planned"},
        }
        outline_plan["change_summary"] = self._build_book_outline_change_summary(db, project, outline_plan)
        outline_plan["outline_topology"] = self._build_outline_topology(
            generation_kind="book_outline",
            mode="topology" if request.use_topology_inference else "linear",
            agent_sequence=BOOK_OUTLINE_AGENT_SEQUENCE,
            outline_plan=outline_plan,
            planned_swarm_agents=BOOK_OUTLINE_SWARM_AGENT_NAMES if request.use_topology_inference else (),
            planned_status="pending",
        )
        return outline_plan

    def _build_book_outline_change_summary(self, db: Session, project: models.Project, outline_plan: dict[str, Any]) -> dict[str, Any]:
        story_bible = db.query(models.StoryBible).filter(models.StoryBible.project_id == project.id).first()
        volume_outlines = outline_plan.get("volume_outlines") if isinstance(outline_plan.get("volume_outlines"), list) else []
        existing_volumes = {
            row.volume_no: row
            for row in db.query(models.Volume).filter(models.Volume.project_id == project.id).all()
        }
        incoming_numbers = [
            int(item.get("volume_no") or index)
            for index, item in enumerate(volume_outlines, start=1)
            if isinstance(item, dict)
        ]
        overwritten = [volume_no for volume_no in incoming_numbers if volume_no in existing_volumes]
        created = [volume_no for volume_no in incoming_numbers if volume_no not in existing_volumes]
        parameters = outline_plan.get("parameters") if isinstance(outline_plan.get("parameters"), dict) else {}
        return {
            "source": "book_outline_preview",
            "requires_user_confirmation": True,
            "will_update": [
                "project.target_words",
                "project.planned_chapter_count",
                "project.chapter_word_target",
                "story_bible.world_setting",
                "story_bible.main_conflict",
                "story_bible.themes",
                "volumes.title",
                "volumes.outline",
            ],
            "story_bible_version": story_bible.version if story_bible else None,
            "target_words": parameters.get("target_words"),
            "volume_count": parameters.get("volume_count") or len(volume_outlines),
            "will_create_volume_numbers": created,
            "will_overwrite_volume_numbers": overwritten,
            "preserved_manual_settings": [
                "不创建或覆盖章节正文",
                "不直接覆盖角色卡、实体、世界事实或图谱",
                "不删除未出现在本次预览中的既有章节",
                "AI 新设定仍需用户确认后才能进入正式设定集",
            ],
        }

    def _collect_audit_issues(self, audit_payload: Any) -> list[dict[str, Any]]:
        if not isinstance(audit_payload, dict):
            return []
        issues: list[dict[str, Any]] = []
        for key in ("issues", "blocking_issues", "revision_suggestions"):
            value = audit_payload.get(key)
            if not isinstance(value, list):
                continue
            for item in value:
                if isinstance(item, dict):
                    issues.append(item)
                elif item:
                    issues.append({"severity": "warning", "issue": str(item)})
        return issues

    def _route_outline_issue(self, issue: dict[str, Any]) -> str:
        text = dumps(issue)
        if any(keyword in text for keyword in ("世界", "规则", "设定", "力量体系", "圣经")):
            return "world_bible"
        if any(keyword in text for keyword in ("卷", "结构", "节奏", "断裂", "阶段", "主线")):
            return "full_structure" if "全书" in text or "结构" in text else "volume_outline"
        if any(keyword in text for keyword in ("伏笔", "回收", "暗线", "线索")):
            return "foreshadowing_manager"
        if any(keyword in text for keyword in ("人物", "主角", "欲望", "成长")):
            return "protagonist_arc"
        return "editor_orchestrator"

    def _build_outline_revision_route(self, outline_plan: dict[str, Any]) -> dict[str, Any]:
        agent_outputs = outline_plan.get("agent_outputs") if isinstance(outline_plan.get("agent_outputs"), dict) else {}
        audit_payload = outline_plan.get("逻辑审计报告")
        if not isinstance(audit_payload, dict):
            audit_payload = agent_outputs.get("logic_audit") if isinstance(agent_outputs.get("logic_audit"), dict) else {}
        issues = self._collect_audit_issues(audit_payload)
        status = str(audit_payload.get("status") or audit_payload.get("conclusion") or "")
        passed = audit_payload.get("passed")
        blocking_issues = [
            issue
            for issue in issues
            if str(issue.get("severity") or issue.get("level") or "").lower() in {"blocking", "error", "fatal", "a", "a级"}
            or "blocking" in str(issue).lower()
        ]
        revision_required = bool(audit_payload.get("revision_required") or blocking_issues or passed is False or status in {"blocked", "needs_revision", "需要返工"})
        routes = []
        for issue in blocking_issues or issues[:3]:
            target = self._route_outline_issue(issue)
            routes.append(
                {
                    "from_agent": "logic_audit",
                    "to_agent": target,
                    "reason": str(issue.get("issue") or issue.get("message") or issue.get("suggestion") or issue)[:240],
                    "status": "planned" if revision_required else "informational",
                }
            )
        return {
            "revision_required": revision_required,
            "status": "needs_revision" if revision_required else "passed",
            "issues": issues,
            "routes": routes if revision_required else [],
        }

    def _normalize_book_outline_plan(self, project: models.Project, request: PlanChaptersRequest, outline_plan: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(outline_plan)
        normalized["generation_kind"] = "book_outline"
        normalized.pop("chapters", None)
        normalized.pop("章节节拍表", None)
        story_state = normalized.get("story_state")
        if isinstance(story_state, dict):
            story_state = dict(story_state)
            story_state.pop("beat_sheets", None)
            normalized["story_state"] = story_state
        volume_source = normalized.get("volume_outlines") or normalized.get("10卷单元总表") or normalized.get("逐卷50章大纲") or []
        if not isinstance(volume_source, list):
            volume_source = []
        volume_outlines = self._dynamic_volume_outlines(volume_source, project.genre, int(request.chapters_per_volume or project.chapter_word_target or 50))
        normalized["volume_outlines"] = volume_outlines
        normalized["10卷单元总表"] = volume_outlines
        book_outline = normalized.get("book_outline")
        if not isinstance(book_outline, dict):
            full_structure = normalized.get("全书10卷总纲")
            if not isinstance(full_structure, dict):
                full_structure = {}
            book_outline = {
                "title": project.title,
                "genre": project.genre,
                "premise": project.premise,
                "core_theme": "主角在长期冲突中以有代价的选择回应世界压力。",
                "core_conflict": full_structure.get("full_story_one_sentence") or project.premise,
                "protagonist_long_term_goal": "持续夺回解释自身命运和世界规则的主动权。",
                "ending_direction": full_structure.get("ending_closure_design", {}),
                "mainline_keywords": ["成长", "代价", "破局", "伏笔", "终局"],
            }
        normalized["book_outline"] = book_outline
        return normalized

    def _dynamic_volume_outlines(self, volumes: list[dict[str, Any]], genre: str, chapters_per_volume: int) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for index, item in enumerate(volumes, start=1):
            if not isinstance(item, dict):
                continue
            volume_no = int(item.get("volume_no") or item.get("volume") or "".join([char for char in str(item.get("第X卷", index)) if char.isdigit()]) or index)
            phase_source = item.get("phases") or item.get("50章高密度剧情流水线执行协议") or []
            if not isinstance(phase_source, list):
                phase_source = []
            rhythm = self._choose_rhythm_model(genre, item, max(1, len(phase_source) or 4), chapters_per_volume)
            normalized.append(
                {
                    "volume_no": volume_no,
                    "title": str(item.get("title") or item.get("卷名") or f"第{volume_no}卷"),
                    "chapter_range": str(item.get("chapter_range") or item.get("章节区间") or self._chapter_range_from_volume_no(volume_no, chapters_per_volume)),
                    "volume_function": str(item.get("volume_function") or item.get("core_goal") or "推动主线升级并改变主角处境。"),
                    "rhythm_model": rhythm,
                    "core_goal": str(item.get("core_goal") or item.get("主线") or item.get("剧情多轨道架构", {}).get("主线", "完成本卷阶段目标。")),
                    "main_track": str(item.get("main_track") or item.get("剧情多轨道架构", {}).get("主线", "主线目标推进。")),
                    "hidden_track": str(item.get("hidden_track") or item.get("剧情多轨道架构", {}).get("暗线", "暗线推进一格。")),
                    "character_track": str(item.get("character_track") or item.get("relationship_change") or "人物关系或认知发生变化。"),
                    "world_reveal": str(item.get("world_reveal") or "揭开世界规则的一层新解释。"),
                    "opposition_pressure": str(item.get("opposition_pressure") or item.get("core_enemy_or_pressure") or "阶段反对力量升级。"),
                    "protagonist_change": item.get("protagonist_change") or item.get("protagonist_upgrade") or item.get("本卷主角提升目标", {}),
                    "phases": self._normalize_volume_phases(phase_source),
                    "volume_hook": str(item.get("volume_hook") or item.get("final_hook") or item.get("卷末大钩子") or "卷末留下通向下一卷的新问题。"),
                    "continuity_requirements": item.get("continuity_requirements") if isinstance(item.get("continuity_requirements"), list) else ["不得推翻已确认世界规则", "暗线必须承接上一卷"],
                    "risks": item.get("risks") if isinstance(item.get("risks"), list) else ["节奏重复", "暗线推进不足"],
                    "revision_suggestions": item.get("revision_suggestions") if isinstance(item.get("revision_suggestions"), list) else [],
                }
            )
        return normalized

    def _choose_rhythm_model(self, genre: str, item: dict[str, Any], phase_count: int, chapters_per_volume: int) -> dict[str, Any]:
        genre_text = f"{genre} {item}".lower()
        if any(keyword in genre_text for keyword in ("悬疑", "推理", "怪谈", "规则")):
            model_name = "线索递进 + 反转揭示"
            recommended_count = 4
        elif any(keyword in genre_text for keyword in ("权谋", "历史", "战争", "群像")):
            model_name = "多线群像并进"
            recommended_count = 6
        elif any(keyword in genre_text for keyword in ("言情", "情感", "青春")):
            model_name = "关系阶段递进"
            recommended_count = 4
        elif any(keyword in genre_text for keyword in ("玄幻", "仙侠", "升级", "高武")):
            model_name = "地图进阶 + 力量升级"
            recommended_count = 5
        else:
            model_name = "动态长篇升级"
            recommended_count = max(3, min(6, phase_count))
        count = max(3, min(7, recommended_count))
        segment = max(1, chapters_per_volume // count)
        distribution = []
        start = 1
        for phase_no in range(1, count + 1):
            end = chapters_per_volume if phase_no == count else min(chapters_per_volume, start + segment - 1)
            distribution.append(f"{start}-{end}")
            start = end + 1
        return {
            "model_name": model_name,
            "phase_count": count,
            "why_this_model": "根据题材、目标读者和本卷功能动态选择，不强制套用固定五段模板。",
            "chapter_distribution": " / ".join(distribution),
        }

    def _normalize_volume_phases(self, phases: list[Any]) -> list[dict[str, Any]]:
        normalized = []
        for index, phase in enumerate(phases, start=1):
            if not isinstance(phase, dict):
                continue
            normalized.append(
                {
                    "phase_no": index,
                    "phase_name": str(phase.get("phase") or phase.get("name") or f"阶段{index}"),
                    "chapter_range": str(phase.get("章节区间") or phase.get("chapter_range") or ""),
                    "dramatic_function": str(phase.get("dramatic_function") or phase.get("function") or phase.get("name") or "推进本卷阶段目标。"),
                    "entry_condition": str(phase.get("entry_condition") or "承接上一阶段结果。"),
                    "exit_condition": str(phase.get("exit_condition") or "制造下一阶段压力。"),
                    "key_events": phase.get("major_events") if isinstance(phase.get("major_events"), list) else [str(phase.get(f"大事件{i}", "")) for i in range(1, 6) if phase.get(f"大事件{i}")],
                    "main_reversal": str(phase.get("main_reversal") or phase.get("turning_point") or "阶段信息产生反转。"),
                    "cost": str(phase.get("cost") or "主角付出资源、关系、身份或认知代价。"),
                    "payoff": str(phase.get("payoff") or "兑现阶段目标或爽点。"),
                    "next_pressure": str(phase.get("next_pressure") or "暴露更高层压力。"),
                }
            )
        return normalized

    def _chapter_range_from_volume_no(self, volume_no: int, chapters_per_volume: int) -> str:
        start = (volume_no - 1) * chapters_per_volume + 1
        return f"{start}-{start + chapters_per_volume - 1}"

    def _apply_book_outline(self, db: Session, project: models.Project, outline_plan: dict[str, Any]) -> None:
        story_bible = self._story_bible(db, project.id)
        parameters = outline_plan.get("parameters") if isinstance(outline_plan.get("parameters"), dict) else {}
        book_outline = outline_plan.get("book_outline") if isinstance(outline_plan.get("book_outline"), dict) else {}
        world_bible = outline_plan.get("世界圣经") if isinstance(outline_plan.get("世界圣经"), dict) else {}
        volume_outlines = outline_plan.get("volume_outlines") if isinstance(outline_plan.get("volume_outlines"), list) else []
        if parameters.get("target_words") is not None:
            project.target_words = int(parameters["target_words"])
        if parameters.get("volume_count") is not None and parameters.get("chapters_per_volume") is not None:
            project.planned_chapter_count = int(parameters["volume_count"]) * int(parameters["chapters_per_volume"])
        if parameters.get("chapter_word_target") is not None:
            project.chapter_word_target = int(parameters["chapter_word_target"])
        story_bible.world_setting = self._outline_text_block(world_bible or book_outline)
        story_bible.main_conflict = str(book_outline.get("core_conflict") or book_outline.get("mainline") or project.premise)
        keywords = book_outline.get("mainline_keywords")
        if not isinstance(keywords, list):
            keywords = ["主线", "成长", "代价", "伏笔"]
        story_bible.themes_json = dumps([str(item) for item in keywords[:8]])
        story_bible.style_guide = project.style_guide or story_bible.style_guide
        story_bible.version += 1
        story_bible.updated_at = utcnow()
        for item in volume_outlines:
            if not isinstance(item, dict):
                continue
            volume_no = int(item.get("volume_no") or len(volume_outlines) + 1)
            row = db.query(models.Volume).filter(models.Volume.project_id == project.id, models.Volume.volume_no == volume_no).first()
            if row is None:
                row = models.Volume(
                    id=generate_id("vol"),
                    project_id=project.id,
                    volume_no=volume_no,
                    title=str(item.get("title") or f"第{volume_no}卷"),
                    sort_order=volume_no,
                )
                db.add(row)
            row.title = str(item.get("title") or row.title)
            row.outline = self._format_dynamic_volume_outline_text(item)
            row.status = "active"
            row.sort_order = volume_no

    def _outline_text_block(self, payload: dict[str, Any]) -> str:
        if not payload:
            return ""
        return "\n".join(self._format_mapping_lines(payload))

    def _format_dynamic_volume_outline_text(self, item: dict[str, Any]) -> str:
        lines = [
            f"卷名：{item.get('title', '')}",
            f"章节区间：{item.get('chapter_range', '')}",
            f"本卷功能：{item.get('volume_function', '')}",
        ]
        rhythm = item.get("rhythm_model")
        if isinstance(rhythm, dict):
            lines.extend(
                [
                    "节奏模型：",
                    f"- 模型：{rhythm.get('model_name', '')}",
                    f"- 阶段数：{rhythm.get('phase_count', '')}",
                    f"- 分布：{rhythm.get('chapter_distribution', '')}",
                    f"- 选择理由：{rhythm.get('why_this_model', '')}",
                ]
            )
        for label, key in [
            ("核心目标", "core_goal"),
            ("主线", "main_track"),
            ("暗线", "hidden_track"),
            ("人物线", "character_track"),
            ("世界揭示", "world_reveal"),
            ("阻力压力", "opposition_pressure"),
            ("主角变化", "protagonist_change"),
        ]:
            value = item.get(key)
            if value:
                lines.append(f"{label}：{value if isinstance(value, str) else dumps(value)}")
        phases = item.get("phases")
        if isinstance(phases, list) and phases:
            lines.append("阶段设计：")
            for phase in phases:
                if not isinstance(phase, dict):
                    continue
                lines.append(f"- {phase.get('phase_name', '阶段')}（{phase.get('chapter_range', '')}）：{phase.get('dramatic_function', '')}")
                events = phase.get("key_events")
                if isinstance(events, list):
                    for event in events[:5]:
                        lines.append(f"  - {event}")
        if item.get("volume_hook"):
            lines.append(f"卷末钩子：{item['volume_hook']}")
        if item.get("risks"):
            lines.append(f"风险：{', '.join([str(risk) for risk in item['risks']])}")
        return "\n".join([line for line in lines if line.strip()])

    def _ensure_batch_can_generate(self, db: Session, project_id: str, request: ChapterOutlineBatchGenerateRequest) -> None:
        if request.overwrite_existing:
            return
        requested_numbers = self._chapter_numbers_from_ranges(request)
        existing = (
            db.query(models.Chapter)
            .filter(models.Chapter.project_id == project_id, models.Chapter.chapter_no.in_(requested_numbers), models.Chapter.deleted_at.is_(None))
            .all()
        )
        if existing:
            raise _conflict("章纲范围已存在，且 overwrite_existing=false")

    def _chapter_numbers_from_ranges(self, request: ChapterOutlineBatchGenerateRequest) -> list[int]:
        numbers: list[int] = []
        for item in request.chapter_ranges:
            numbers.extend(range(item.start_chapter_no, item.end_chapter_no + 1))
        return sorted(dict.fromkeys(numbers))

    def _chapter_outline_batch_context(
        self,
        db: Session,
        project: models.Project,
        request: ChapterOutlineBatchGenerateRequest,
        chapter_outlines: list[dict[str, Any]],
    ) -> dict[str, Any]:
        story_bible = db.query(models.StoryBible).filter(models.StoryBible.project_id == project.id).first()
        volumes = db.query(models.Volume).filter(models.Volume.project_id == project.id).order_by(models.Volume.volume_no.asc()).all()
        return {
            "project": serialize_project(project),
            "story_bible": serialize_story_bible(story_bible) if story_bible else {},
            "volumes": [serialize_volume(volume) for volume in volumes],
            "chapter_ranges": [item.model_dump() for item in request.chapter_ranges],
            "generation_requirement": request.generation_requirement,
            "fallback_chapter_outlines": chapter_outlines,
        }

    def _build_chapter_outline_candidates(self, db: Session, project: models.Project, request: ChapterOutlineBatchGenerateRequest) -> list[dict[str, Any]]:
        volumes = {
            volume.volume_no: volume
            for volume in db.query(models.Volume).filter(models.Volume.project_id == project.id).all()
        }
        candidates: list[dict[str, Any]] = []
        for item in request.chapter_ranges:
            volume = volumes.get(item.volume_no)
            if volume is None:
                raise _bad_request(f"第{item.volume_no}卷不存在，请先确认总纲和卷纲")
            for chapter_no in range(item.start_chapter_no, item.end_chapter_no + 1):
                candidates.append(
                    {
                        "chapter_no": chapter_no,
                        "volume_no": item.volume_no,
                        "title": f"第{chapter_no}章：{self._chapter_title_seed(volume, chapter_no)}",
                        "outline": f"承接「{volume.title}」卷纲，推进本批要求：{request.generation_requirement or '按已确认卷纲生成连续章纲'}。",
                        "pov_character": "主角",
                        "core_event": "围绕本卷核心目标推进一个明确因果节点。",
                        "conflict": "主角目标与本卷阻力正面相撞。",
                        "turn_point": "本章中段出现新信息或误判，改变下一步行动。",
                        "emotional_beats": ["目标", "阻碍", "行动", "代价", "钩子"],
                        "plot_purpose": "承接卷纲，制造下一章问题。",
                        "cliffhanger": "以未解决选择、反常线索或敌方动作收束。",
                        "word_target": project.chapter_word_target,
                    }
                )
        return candidates

    def _chapter_title_seed(self, volume: models.Volume, chapter_no: int) -> str:
        seeds = ["目标浮现", "线索偏转", "阻力升级", "代价出现", "钩子落下"]
        return f"{volume.title}·{seeds[(chapter_no - 1) % len(seeds)]}"

    def _normalize_chapter_outline_item(self, item: dict[str, Any], project: models.Project, request: ChapterOutlineBatchGenerateRequest) -> dict[str, Any]:
        chapter_no = int(item.get("chapter_no") or 1)
        volume_no = int(item.get("volume_no") or 1)
        return {
            "chapter_no": chapter_no,
            "volume_no": volume_no,
            "title": str(item.get("title") or f"第{chapter_no}章"),
            "outline": str(item.get("outline") or item.get("story_function") or "推进本章剧情节点。"),
            "pov_character": str(item.get("pov_character") or "主角"),
            "core_event": str(item.get("core_event") or item.get("action") or "主角采取行动推进目标。"),
            "conflict": str(item.get("conflict") or item.get("opposition_force") or "主角目标遭遇阻力。"),
            "turn_point": str(item.get("turn_point") or item.get("state_change") or "状态发生改变。"),
            "emotional_beats": item.get("emotional_beats") if isinstance(item.get("emotional_beats"), list) else ["目标", "阻碍", "代价", "钩子"],
            "plot_purpose": str(item.get("plot_purpose") or item.get("story_function") or "服务本批章纲因果链。"),
            "cliffhanger": str(item.get("cliffhanger") or item.get("hook") or "留下下一章钩子。"),
            "word_target": int(item.get("word_target") or project.chapter_word_target),
        }

    def _persist_chapter_outline_candidates(
        self,
        db: Session,
        project: models.Project,
        candidates: list[dict[str, Any]],
        job_id: str | None,
        overwrite_existing: bool,
    ) -> list[models.Chapter]:
        normalized = [self._normalize_chapter_outline_item(item, project, ChapterOutlineBatchGenerateRequest(chapter_ranges=[{"volume_no": int(item.get("volume_no", 1)), "start_chapter_no": int(item.get("chapter_no", 1)), "end_chapter_no": int(item.get("chapter_no", 1))}], idempotency_key="commit")) for item in candidates]
        numbers = [int(item["chapter_no"]) for item in normalized]
        existing_by_no = {
            chapter.chapter_no: chapter
            for chapter in db.query(models.Chapter).filter(models.Chapter.project_id == project.id, models.Chapter.chapter_no.in_(numbers)).all()
        }
        chapters: list[models.Chapter] = []
        for item in normalized:
            chapter_no = int(item["chapter_no"])
            chapter = existing_by_no.get(chapter_no)
            if chapter is not None and chapter.deleted_at is None and not overwrite_existing:
                raise _conflict(f"第{chapter_no}章已存在，且 overwrite_existing=false")
            if chapter is None:
                chapter = models.Chapter(
                    id=generate_id("chp"),
                    project_id=project.id,
                    volume_no=int(item["volume_no"]),
                    chapter_no=chapter_no,
                    title=item["title"],
                    word_target=int(item["word_target"]),
                    sort_order=chapter_no,
                )
                db.add(chapter)
            chapter.volume_no = int(item["volume_no"])
            chapter.title = item["title"]
            chapter.outline = item["outline"]
            chapter.pov_character = item["pov_character"]
            chapter.core_event = item["core_event"]
            chapter.conflict = item["conflict"]
            chapter.turn_point = item["turn_point"]
            chapter.emotional_beats_json = dumps(item["emotional_beats"])
            chapter.plot_purpose = item["plot_purpose"]
            chapter.cliffhanger = item["cliffhanger"]
            chapter.word_target = int(item["word_target"])
            chapter.sort_order = chapter_no
            chapter.status = "planned"
            chapter.deleted_at = None
            chapters.append(chapter)
            self._snapshot(db, project.id, chapter.id, job_id, "chapter_outline_batch", "chapter_outline", dumps(item), "批量章纲确认写入")
        return chapters

    def _start_job(self, db: Session, job: models.GenerationJob) -> None:
        total_steps = max(int(loads(job.progress_json, {}).get("total_steps", 1)), 1)
        job.status = "running"
        job.started_at = job.started_at or utcnow()
        job.heartbeat_at = utcnow()
        job.progress_json = dumps(
            {
                "current_step": "running",
                "total_steps": total_steps,
                "completed_steps": 0,
                "message": "后台推演已启动",
            }
        )
        db.commit()

    def _update_job_progress(self, db: Session, job: models.GenerationJob, current_agent: str, completed_steps: int, total_steps: int, message: str) -> None:
        job.current_agent = current_agent
        job.heartbeat_at = utcnow()
        job.progress_json = dumps(
            {
                "current_step": current_agent,
                "total_steps": total_steps,
                "completed_steps": max(0, min(completed_steps, total_steps)),
                "message": message,
            }
        )
        db.commit()

    def _fail_job(self, db: Session, job: models.GenerationJob, error: Exception) -> None:
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
                "message": "任务执行失败",
            }
        )

    def _finish_job(self, db: Session, job: models.GenerationJob, result: dict) -> None:
        total_steps = max(int(loads(job.progress_json, {}).get("total_steps", 1)), 1)
        job.status = "succeeded"
        job.progress_json = dumps(
            {
                "current_step": "completed",
                "total_steps": total_steps,
                "completed_steps": total_steps,
                "message": "任务已完成",
            }
        )
        job.result_json = dumps(result)
        job.finished_at = utcnow()

    def _record_agent_run(self, db: Session, job: models.GenerationJob, agent_name: str, output: dict, input_payload: dict) -> models.AgentRun:
        spec = AGENT_SPECS_BY_NAME.get(agent_name)
        run = models.AgentRun(
            id=generate_id("agn"),
            job_id=job.id,
            project_id=job.project_id,
            chapter_id=job.chapter_id,
            agent_name=agent_name,
            agent_role=spec.role if spec else agent_name,
            status="succeeded",
            input_payload_json=dumps(input_payload),
            output_payload_json=dumps(output),
            started_at=utcnow(),
            finished_at=utcnow(),
        )
        job.current_agent = agent_name
        db.add(run)
        return run

    def _snapshot(self, db: Session, project_id: str, chapter_id: str | None, job_id: str | None, agent_name: str, content_type: str, content: str, user_note: str) -> models.VersionSnapshot:
        version = models.VersionSnapshot(
            id=generate_id("ver"),
            project_id=project_id,
            chapter_id=chapter_id,
            job_id=job_id,
            agent_name=agent_name,
            content_type=content_type,
            content=content,
            metadata_json=dumps({"created_by": agent_name}),
            user_note=user_note,
            branch_name="main",
        )
        db.add(version)
        return version

    def _persist_planned_chapters(self, db: Session, project: models.Project, planned: list[dict[str, Any]], request: PlanChaptersRequest, job_id: str) -> list[models.Chapter]:
        chapters = []
        existing_by_no = {
            chapter.chapter_no: chapter
            for chapter in db.query(models.Chapter)
            .filter(models.Chapter.project_id == project.id, models.Chapter.chapter_no >= request.start_chapter_no, models.Chapter.chapter_no < request.start_chapter_no + request.chapter_count)
            .all()
        }
        for item in planned:
            chapter_no = int(item["chapter_no"])
            chapter = existing_by_no.get(chapter_no)
            if chapter is None:
                max_sort_order = db.query(func.max(models.Chapter.sort_order)).filter(models.Chapter.project_id == project.id).scalar() or 0
                chapter = models.Chapter(
                    id=generate_id("chp"),
                    project_id=project.id,
                    volume_no=int(item.get("volume_no", 1)),
                    chapter_no=chapter_no,
                    title=item.get("title", f"第{chapter_no}章"),
                    word_target=int(item.get("word_target", project.chapter_word_target)),
                    sort_order=max_sort_order + len(chapters) + 1,
                )
                db.add(chapter)
            chapter.title = item.get("title", chapter.title)
            chapter.volume_no = int(item.get("volume_no", chapter.volume_no or 1))
            chapter.word_target = int(item.get("word_target", chapter.word_target or project.chapter_word_target))
            chapter.sort_order = chapter_no
            chapter.outline = item.get("outline", "")
            chapter.pov_character = item.get("pov_character", "")
            chapter.core_event = item.get("core_event", "")
            chapter.conflict = item.get("conflict", "")
            chapter.turn_point = item.get("turn_point", "")
            chapter.emotional_beats_json = dumps(item.get("emotional_beats", []))
            chapter.plot_purpose = item.get("plot_purpose", "")
            chapter.cliffhanger = item.get("cliffhanger", "")
            chapter.status = "planned"
            chapter.deleted_at = None
            chapters.append(chapter)
            self._snapshot(db, project.id, chapter.id, job_id, "chapter_planner", "chapter_outline", dumps(item), "章节规划")
        return chapters

    def _build_long_novel_outline_plan(
        self,
        db: Session,
        project: models.Project,
        request: PlanChaptersRequest,
        state: NovelStudioState,
    ) -> dict[str, Any]:
        story_bible = db.query(models.StoryBible).filter(models.StoryBible.project_id == project.id).first()
        characters = db.query(models.Character).filter(models.Character.project_id == project.id).order_by(models.Character.importance_score.desc()).all()
        entities = db.query(models.StoryEntity).filter(models.StoryEntity.project_id == project.id).order_by(models.StoryEntity.importance_score.desc()).limit(8).all()
        world_facts = db.query(models.WorldFact).filter(models.WorldFact.project_id == project.id).order_by(models.WorldFact.importance_score.desc()).limit(10).all()
        protagonist = next((character for character in characters if character.role_type == "protagonist"), characters[0] if characters else None)
        antagonist = next((character for character in characters if character.role_type == "antagonist"), None)
        target_words = request.target_words or project.target_words or project.planned_chapter_count * project.chapter_word_target
        chapter_word_target = request.chapter_word_target or project.chapter_word_target
        volume_count = request.volume_count or max(1, project.current_volume, 3)
        chapters_per_volume = request.chapters_per_volume or max(1, project.planned_chapter_count // volume_count)
        genre = project.genre or state.genre or "类型小说"
        protagonist_name = protagonist.name if protagonist else "主角"
        antagonist_name = antagonist.name if antagonist else "核心反派/阻力势力"
        setting_titles = [fact.title for fact in world_facts[:6]] or ["核心规则", "主线暗线", "力量代价"]
        entity_names = [entity.name for entity in entities[:6]] or ["核心地图", "关键组织", "关键物件"]
        main_conflict = story_bible.main_conflict if story_bible and story_bible.main_conflict else project.premise
        style = project.style_guide or (story_bible.style_guide if story_bible else "") or "高密度、强钩子、因果链清晰"
        structured_prompt = {
            "role": "顶级长篇网文总编 + 爽文结构设计师",
            "task": "不要写正文，只生成全书大纲、卷纲和本次章节纲。",
            "parameters": {
                "target_words": target_words,
                "volume_count": volume_count,
                "chapters_per_volume": chapters_per_volume,
                "chapter_word_target": chapter_word_target,
                "start_chapter_no": request.start_chapter_no,
                "chapter_count": request.chapter_count,
            },
            "source_context": {
                "title": project.title,
                "genre": genre,
                "target_reader": project.target_reader,
                "premise": project.premise,
                "initial_idea": project.initial_idea,
                "style": style,
                "protagonist": protagonist_name,
                "antagonist": antagonist_name,
                "story_bible": serialize_story_bible(story_bible) if story_bible else {},
                "core_characters": [serialize_character(character) for character in characters[:8]],
                "core_entities": [serialize_story_entity(entity) for entity in entities[:8]],
                "world_facts": [serialize_world_fact(fact) for fact in world_facts[:10]],
            },
            "output_contract": ["世界圣经", f"{volume_count}卷单元总表", f"{request.chapter_count}章章纲", "全卷逻辑审计"],
            "rules": [
                "每卷必须推动主线升级",
                "每卷必须有一个反派或势力破防",
                "每卷必须有主角能力或地位变化",
                "暗线必须逐卷推进，不能断",
                "不要写成散点脑洞，要保证因果链",
                "不要输出正文，只输出大纲",
            ],
        }
        world_bible = {
            "题材定性与世界蓝图": f"《{project.title}》定位为{genre}长篇，面向{project.target_reader}。世界蓝图围绕“{project.premise or main_conflict}”展开，所有地图、势力和规则都服务主线升级。",
            "核心灵感锚定": project.initial_idea or project.premise or request.outline_requirement,
            "主角金手指机制": self._join_nonempty(
                [
                    f"{protagonist_name}的核心能力/优势必须与设定事实“{self._pick(setting_titles, 0, '核心规则')}”绑定。",
                    "能力每次升级都需要情绪、资源、情报或关系代价，不能无成本膨胀。",
                ],
                " ",
            ),
            "等级体系": [
                f"入局期：第1卷，理解{self._pick(setting_titles, 0, '核心规则')}。",
                f"扩张期：第2-{max(2, volume_count // 2)}卷，主角进入{self._pick(entity_names, 0, '核心地图')}并获得地位。",
                f"破局期：第{max(3, volume_count // 2 + 1)}-{volume_count}卷，暗线真相和终局势力正面碰撞。",
            ],
            "四大成长线": {
                "A. 能力/系统线": f"{protagonist_name}从被动使用能力，逐步理解规则代价并反向设计战局。",
                "B. 势力/世界线": f"从{self._pick(entity_names, 0, '局部地图')}扩展到全局秩序，逐卷揭开{main_conflict}背后的结构性问题。",
                "C. 社会地位与反馈线": "从被质疑、被围观、被利用，到成为能改变资源分配和舆论反馈的核心变量。",
                "D. 情感/羁绊线": "同伴、导师、对手和副线角色不断制造选择代价，避免主角只靠外挂推进。",
            },
            f"{volume_count}卷生态人物树": [
                {
                    "卷区间": f"第{index + 1}卷",
                    "核心人物生态": [protagonist_name, antagonist_name, self._pick([character.name for character in characters], index + 1, "阶段盟友")],
                    "人物功能": "主角、阶段阻力、信息差角色和情感代价角色形成闭环。",
                }
                for index in range(volume_count)
            ],
        }
        volume_table: list[dict[str, Any]] = []
        phase_names = [
            ("Phase 1【目标+主线引入】", "目标建立、地图开启、第一波规则展示"),
            ("Phase 2【阻碍+支线并行】", "阻力升级、支线并行、反派第一次压制"),
            ("Phase 3【伏笔揭露+多转折铺垫】", "旧伏笔变成新解释，多线索逼近同一个真相"),
            ("Phase 4【爆发+情绪释放】", "主角用前文积累反打，阶段反派或势力破防"),
            ("Phase 5【收尾+地位转化】", "回收本卷目标，改变主角地位并抛出下一卷钩子"),
        ]
        for index in range(volume_count):
            volume_no = index + 1
            start = (volume_no - 1) * chapters_per_volume + 1
            end = volume_no * chapters_per_volume
            title = request.volume_title if volume_no == max(1, ((request.start_chapter_no - 1) // chapters_per_volume) + 1) else f"第{volume_no}卷：{self._pick(['入局', '破圈', '失控', '围猎', '反杀', '裂变', '登阶', '真相', '终局', '新秩序'], index, '升级')}"
            phase_blocks = []
            for phase_index, (phase_name, phase_goal) in enumerate(phase_names):
                phase_start = start + phase_index * max(1, chapters_per_volume // 5)
                phase_end = min(end, phase_start + max(1, chapters_per_volume // 5) - 1)
                phase_blocks.append(
                    {
                        "phase": phase_name,
                        "章节区间": f"{phase_start}-{phase_end}章",
                        "全部出场角色": [protagonist_name, antagonist_name, self._pick([character.name for character in characters], phase_index + index, "阶段角色")],
                        "大事件1": f"{phase_goal}，围绕{self._pick(setting_titles, phase_index, '核心规则')}制造新问题。",
                        "大事件2": f"{self._pick(entity_names, phase_index, '关键地点')}的资源或情报被重新分配。",
                        "大事件3": f"{antagonist_name}或其代理势力逼迫{protagonist_name}付出代价。",
                        "大事件4": "暗线露出一条可追踪证据，不直接揭底。",
                        "大事件5": "阶段选择改变角色关系或公众反馈。",
                    }
                )
            volume_table.append(
                {
                    "第X卷": f"第{volume_no}卷",
                    "章节区间": f"{start}-{end}章",
                    "卷名": title,
                    "核心地图": self._pick(entity_names, index, "核心地图"),
                    "本卷主角提升目标": {
                        "能力": f"掌握{self._pick(setting_titles, index, '核心规则')}的新用法。",
                        "金手指": "从被动触发转为主动设计触发条件。",
                        "地位": f"从第{volume_no - 1}卷结果中获得新的社会位置或敌对关注。",
                        "情感/人际": "新增一个羁绊、债务或背叛风险。",
                    },
                    "剧情多轨道架构": {
                        "主线": f"{protagonist_name}推进长期目标，本卷解决一个阶段目标并制造下一卷问题。",
                        "暗线": f"{main_conflict}背后的真相推进一格，不断指向最终卷。",
                    },
                    "50章高密度剧情流水线执行协议": phase_blocks,
                    "卷末大钩子": f"{protagonist_name}以为解决了{title}的核心问题，却发现{self._pick(setting_titles, index + 1, '更大规则')}才是真正入口。",
                    "全卷逻辑审计": {
                        "冲突审计": "Yes：主角阶段目标与势力阻力正面相撞。",
                        "代价审计": "Yes：能力、关系、地位至少一项付出代价。",
                        "爽感审计": "Yes：阶段势力破防，主角获得可见反馈。",
                        "钩子审计": "Yes：卷末钩子必须引向下一卷地图或暗线真相。",
                    },
                }
            )
        chapters = []
        for offset in range(request.chapter_count):
            chapter_no = request.start_chapter_no + offset
            volume_no = ((chapter_no - 1) // chapters_per_volume) + 1
            phase_index = min(4, ((chapter_no - 1) % chapters_per_volume) // max(1, chapters_per_volume // 5))
            volume_outline = volume_table[min(volume_no - 1, len(volume_table) - 1)]
            phase = volume_outline["50章高密度剧情流水线执行协议"][phase_index]
            chapters.append(
                {
                    "chapter_no": chapter_no,
                    "volume_no": volume_no,
                    "title": f"第{chapter_no}章：{self._pick(['入局', '试探', '破防', '反转', '钩子'], offset, '推进')}",
                    "outline": f"承接《{project.title}》总纲，本章位于{volume_outline['卷名']}的{phase['phase']}。围绕“{request.outline_requirement}”推进一个因果节点，不写散点脑洞。",
                    "pov_character": protagonist_name,
                    "core_event": phase["大事件1"],
                    "conflict": f"{protagonist_name}的阶段目标与{antagonist_name}代表的阻力正面碰撞。",
                    "turn_point": phase["大事件4"],
                    "emotional_beats": ["目标", "阻碍", "误判", "反击", "钩子"],
                    "plot_purpose": f"推进主线升级，服务{volume_outline['剧情多轨道架构']['主线']}",
                    "cliffhanger": f"{phase['大事件5']}，并把读者推向下一章。",
                    "word_target": chapter_word_target,
                }
            )
        outline_state_payload = self._build_outline_state_payload(
            project=project,
            request=request,
            state=state,
            target_words=target_words,
            volume_count=volume_count,
            chapters_per_volume=chapters_per_volume,
            chapter_word_target=chapter_word_target,
            genre=genre,
            protagonist_name=protagonist_name,
            antagonist_name=antagonist_name,
            main_conflict=main_conflict,
            setting_titles=setting_titles,
            entity_names=entity_names,
            style=style,
            world_bible=world_bible,
            volume_table=volume_table,
            chapters=chapters,
            characters=[serialize_character(character) for character in characters[:12]],
        )
        return {
            "parameters": {
                "target_words": target_words,
                "volume_count": volume_count,
                "chapters_per_volume": chapters_per_volume,
                "chapter_word_target": chapter_word_target,
            },
            "structured_prompt": structured_prompt,
            "世界圣经": world_bible,
            "10卷单元总表": volume_table,
            "chapters": chapters,
            **outline_state_payload,
        }

    def _build_outline_state_payload(
        self,
        project: models.Project,
        request: PlanChaptersRequest,
        state: NovelStudioState,
        target_words: int,
        volume_count: int,
        chapters_per_volume: int,
        chapter_word_target: int,
        genre: str,
        protagonist_name: str,
        antagonist_name: str,
        main_conflict: str,
        setting_titles: list[str],
        entity_names: list[str],
        style: str,
        world_bible: dict[str, Any],
        volume_table: list[dict[str, Any]],
        chapters: list[dict[str, Any]],
        characters: list[dict[str, Any]],
    ) -> dict[str, Any]:
        one_sentence = project.premise or state.initial_idea or request.outline_requirement
        config = {
            "project_name": project.title,
            "genre": genre,
            "tone": style,
            "target_words": target_words,
            "target_volumes": volume_count,
            "chapters_per_volume": chapters_per_volume,
            "words_per_chapter": chapter_word_target,
            "must_keep_elements": [project.initial_idea or project.premise, request.outline_requirement],
            "forbidden_elements": ["无铺垫反转", "机械降神", "主角无代价碾压", "伏笔只埋不收"],
        }
        story_kernel = {
            "one_sentence_story": one_sentence,
            "core_story": f"{protagonist_name}围绕“{one_sentence}”被推入长期冲突，在每卷付出代价、扩大地图并逼近终局真相。",
            "protagonist_desire": f"{protagonist_name}想夺回解释自身命运和世界规则的主动权。",
            "core_conflict": main_conflict,
            "failure_cost": "如果失败，主角会失去关系、地位和揭开真相的资格，世界旧秩序继续吞掉后来者。",
            "long_term_engines": ["阶段地图升级", "势力利益冲突", "金手指代价反噬", "人物秘密揭露", "终局真相分卷推进"],
            "ending_directions": ["主角改写旧规则但保留必要代价", "终局伏笔回收后建立新秩序", "主角完成认知成长而非单纯变强"],
            "suitability_score": 86.0,
        }
        market_position = {
            "type_positioning": {
                "main_type": genre,
                "sub_types": ["升级流", "悬疑暗线", "势力博弈"],
                "tags": list(dict.fromkeys([genre, "长线伏笔", "阶段破局", "成长代价"])),
            },
            "target_readers": project.target_reader,
            "core_selling_points": [
                f"{protagonist_name}的能力与世界规则绑定，爽点来自破局而不是无脑碾压。",
                "每卷都有独立地图和阶段势力破防。",
                "暗线真相、人物秘密和伏笔账本持续推进。",
            ],
            "differentiation": f"把“{one_sentence}”拆成世界规则、人物成长和势力冲突三条可追读链。",
            "core_emotions": ["爽", "燃", "悬疑", "压迫", "反转"],
            "satisfaction_types": ["规则套利", "弱势反打", "身份翻转", "势力破防", "旧案揭露", "同伴救场", "代价换胜", "卷末大钩子"],
            "fatigue_risks": ["连续靠同一种能力解题", "反派只负责震惊", "世界真相揭露过快"],
            "type_boundaries": ["不写正文", "不让设定说明替代行动冲突", "不让终局秘密提前摊牌"],
        }
        schema_world_bible = {
            "world_summary": world_bible["题材定性与世界蓝图"],
            "base_rules": [
                "所有新增设定必须能转化为行动冲突。",
                "主角能力升级必须存在限制、代价或反噬。",
                "势力变化必须回应资源、地位或真相分配。",
                "暗线每卷至少推进一次，不能断裂。",
                "卷末钩子必须连接下一卷地图、敌人或真相。",
            ],
            "power_system": {
                "levels": world_bible["等级体系"],
                "source": self._pick(setting_titles, 0, "核心规则"),
                "upgrade_method": "通过阶段目标、资源交换、情报验证和关系代价逐卷升级。",
                "cost": "每次升级至少损耗资源、关系、身份安全或心理稳定性之一。",
                "limits": "不能跳过前置认知；越级使用必须有明确代价。",
                "loss_of_control_risk": "能力被敌方识破后会反向制造陷阱。",
            },
            "social_structure": {
                "surface_society": "公开秩序提供规则解释。",
                "inner_society": "核心势力通过资源、资格和信息差维持优势。",
                "official_organizations": [self._pick(entity_names, 0, "官方组织")],
                "civilian_organizations": [self._pick(entity_names, 1, "民间组织")],
                "underground_organizations": [self._pick(entity_names, 2, "地下势力")],
                "supernatural_organizations": [self._pick(entity_names, 3, "超常组织")],
            },
            "factions": [
                {
                    "name": self._pick(entity_names, index, f"阶段势力{index + 1}"),
                    "position": "阶段阻力/资源持有者",
                    "goal": f"围绕{self._pick(setting_titles, index, '核心规则')}维持自身优势。",
                    "resources": [self._pick(setting_titles, index, "关键资源")],
                    "representatives": [antagonist_name],
                    "relation_to_protagonist": "从利用、误解到围剿，再到终局正面碰撞。",
                    "conflicts_it_can_create": ["资源封锁", "舆论围剿", "规则误导", "关系撕裂"],
                }
                for index in range(min(5, max(1, volume_count)))
            ],
            "resources": [{"name": name, "plot_value": "制造争夺、交换和代价"} for name in setting_titles[:5]],
            "map_layers": [self._pick(entity_names, index, f"第{index + 1}层地图") for index in range(min(6, volume_count))],
            "historical_secrets": [
                f"{self._pick(setting_titles, 0, '旧规则')}曾被关键势力篡改。",
                f"{protagonist_name}与终局真相存在未公开关联。",
            ],
            "final_secret": f"{main_conflict}并非单一反派造成，而是旧秩序长期分配规则失衡的结果。",
            "forbidden_changes": config["forbidden_elements"],
        }
        protagonist_arcs = [
            {
                "volume": index + 1,
                "external_goal": f"解决第{index + 1}卷阶段目标，并进入{self._pick(entity_names, index, '新地图')}。",
                "internal_change": "从被规则驱赶，逐步学会主动定义选择边界。",
                "ability_change": f"掌握{self._pick(setting_titles, index, '核心规则')}的新用法。",
                "relationship_change": "新增羁绊、债务、背叛风险或公众反馈。",
                "cost": "暴露能力线索，消耗资源，或牺牲一段安全关系。",
            }
            for index in range(volume_count)
        ]
        character_tree = {
            "character_function_overview": "主角、阶段反派、盟友、信息差角色、情感代价角色和终局见证者共同支撑长篇。",
            "core_character_tree": characters
            or [
                {
                    "name": protagonist_name,
                    "initial_identity": "被卷入核心冲突的人",
                    "faction": "主角阵营",
                    "first_volume": 1,
                    "surface_goal": "解决眼前危机",
                    "deep_desire": "夺回选择权",
                    "secret": "与旧规则有关",
                    "relation_to_protagonist_start": "本人",
                    "relation_to_protagonist_end": "完成认知成长",
                    "representative_conflict": main_conflict,
                    "arc": "从被动承受到主动承担",
                    "final_fate": "参与建立新秩序",
                    "can_die_or_exit": False,
                }
            ],
            "protagonist_camp": {"members": [protagonist_name], "internal_tension": "胜利代价和公开真相的风险不断拉扯。"},
            "villain_chain": [
                {
                    "volume": index + 1,
                    "villain": f"{antagonist_name}代理人{index + 1}",
                    "desire": "维护阶段资源和规则解释权。",
                    "why_against_protagonist": f"{protagonist_name}的行动威胁其利益。",
                    "world_pressure_represented": self._pick(setting_titles, index, "世界压力"),
                    "how_they_fail": "被主角利用前文伏笔和规则限制反制。",
                    "consequence_after_failure": "更高层势力开始直接关注主角。",
                }
                for index in range(volume_count)
            ],
            "relationship_network": "关系从试探、债务、互信、背叛风险逐步进入终局共同选择。",
            "character_arc_audit": {"tool_like_characters": [], "fix_suggestions": ["新增角色必须补齐欲望、秘密和退场条件。"]},
        }
        faction_conflicts = {
            "core_conflict_one_sentence": main_conflict,
            "factions": schema_world_bible["factions"],
            "faction_relationships": "阶段势力之间既互相利用又竞争资源，主角不断把局部冲突推向全局冲突。",
            "conflict_escalation_chain": [
                {
                    "volume": index + 1,
                    "surface_conflict": f"争夺{self._pick(setting_titles, index, '关键资源')}的解释权。",
                    "deep_conflict": "谁有资格定义世界规则。",
                    "why_protagonist_gets_involved": "阶段目标和长期欲望被同一规则卡住。",
                    "enemy_pressure": "资源封锁、身份污名、关系威胁和规则陷阱。",
                    "volume_end_escalation": "局部胜利暴露更高层敌人。",
                }
                for index in range(volume_count)
            ],
            "local_to_global_escalation_path": "个人危机 -> 阶段势力冲突 -> 资源分配冲突 -> 旧秩序真相 -> 终局重构。",
            "conflict_repetition_risks": [{"risk": "每卷都用同类敌人压制。", "alternative": "轮换资源战、舆论战、关系战、规则战和真相战。"}],
        }
        power_progression = {
            "cheat_one_sentence": f"{protagonist_name}能通过理解并批注{self._pick(setting_titles, 0, '核心规则')}来制造阶段性破局机会。",
            "basic_rules": {
                "trigger_condition": "必须先获得足够情报或付出可见代价。",
                "reward_mechanism": "获得一次规则解释、资源置换或局部反制机会。",
                "exchange_mechanism": "以记忆、关系信任、身份安全或稀缺资源交换。",
                "cooldown_or_limits": "同类场景不能连续使用；越级使用会暴露弱点。",
                "side_effects": "敌人逐步学会反向设置诱饵。",
                "loss_of_control_risk": "错误批注会强化敌方规则。",
            },
            "upgrade_route": [
                {
                    "volume": item["volume"],
                    "unlocked_ability": item["ability_change"],
                    "use_case": item["external_goal"],
                    "limit": "必须有前文铺垫和代价。",
                    "cost": item["cost"],
                    "signature_satisfaction_scene": "用旧伏笔反制阶段势力。",
                }
                for item in protagonist_arcs
            ],
            "enemy_counter_methods": ["伪造情报", "污染资源", "绑架关系", "诱导越级", "公开污名", "切断补给"],
            "failure_scenarios": ["信息不足", "代价不可接受", "关系被牵连", "敌人主动设局"],
            "satisfaction_expression": "爽点来自理解规则后的反打、身份翻转和势力破防，避免单纯数值碾压。",
            "power_inflation_control": {"abilities_to_delay": ["终局规则改写", "无成本复盘"], "abilities_requiring_cost": ["越级反杀", "公开改变秩序"]},
        }
        ten_volume_table = []
        volume_outlines = []
        beat_sheets = []
        for index, item in enumerate(volume_table):
            volume_no = index + 1
            phases = []
            chapter_start = (volume_no - 1) * chapters_per_volume + 1
            chapter_end = volume_no * chapters_per_volume
            for phase_index, phase in enumerate(item["50章高密度剧情流水线执行协议"]):
                phases.append(
                    {
                        "phase": phase_index + 1,
                        "name": phase["phase"],
                        "chapter_range": phase["章节区间"],
                        "characters": phase["全部出场角色"],
                        "major_events": [
                            {
                                "event_no": event_no,
                                "event": phase[f"大事件{event_no}"],
                                "conflict": "目标、阻力、信息差和代价正面碰撞。",
                                "effect": "推动主线或暗线，不作为散点脑洞存在。",
                            }
                            for event_no in range(1, 6)
                        ],
                    }
                )
            ten_volume_table.append(
                {
                    "volume": volume_no,
                    "title": item["卷名"],
                    "chapter_range": item["章节区间"],
                    "core_map": item["核心地图"],
                    "main_plot": item["剧情多轨道架构"]["主线"],
                    "hidden_plot": item["剧情多轨道架构"]["暗线"],
                    "core_enemy_or_pressure": f"{antagonist_name}及其阶段代理压力",
                    "protagonist_upgrade": item["本卷主角提升目标"],
                    "relationship_change": item["本卷主角提升目标"]["情感/人际"],
                    "world_reveal": f"揭开{self._pick(setting_titles, index, '核心规则')}的一层误导版本。",
                    "final_hook": item["卷末大钩子"],
                    "next_volume_connection": "卷末钩子直接引向下一卷地图、敌人或真相。",
                }
            )
            volume_outlines.append(
                {
                    "volume": volume_no,
                    "chapter_range": item["章节区间"],
                    "title": item["卷名"],
                    "core_map": item["核心地图"],
                    "protagonist_upgrade_goal": item["本卷主角提升目标"],
                    "multi_track_plot": item["剧情多轨道架构"],
                    "phases": phases,
                    "final_hook": item["卷末大钩子"],
                    "change_summary": {
                        "protagonist": "能力、地位或认知至少一项发生可见变化。",
                        "world": "地图扩大或规则解释更新。",
                        "relationships": "羁绊、债务、背叛风险或公众反馈改变。",
                        "foreshadowing": "新增并推进至少一条跨卷伏笔。",
                        "enemy": "阶段势力破防并引出更高层压力。",
                    },
                    "risks": ["爽点重复", "战力膨胀过快", "暗线推进不足"],
                }
            )
            ten_chapter_loops = []
            for loop_index in range(5):
                loop_start = chapter_start + loop_index * max(1, chapters_per_volume // 5)
                loop_end = min(chapter_end, loop_start + max(1, chapters_per_volume // 5) - 1)
                ten_chapter_loops.append(
                    {
                        "chapter_range": f"{loop_start}-{loop_end}",
                        "small_goal": f"完成第{loop_index + 1}个阶段目标。",
                        "small_obstacle": "遭遇资源、关系、情报或规则阻碍。",
                        "small_climax": "用前文铺垫完成一次局部反打。",
                        "emotional_reward": self._pick(["压迫释放", "爽点兑现", "真相逼近", "关系升温", "身份翻转"], loop_index, "阶段回报"),
                        "new_problem": "胜利暴露下一层风险。",
                    }
                )
            beat_sheets.append(
                {
                    "volume": volume_no,
                    "emotional_curve": "悬疑 -> 压迫 -> 误判 -> 反转 -> 爽感爆发 -> 余波 -> 新危机",
                    "phase_beat_functions": [
                        {
                            "phase": phase["phase"],
                            "function": phase["name"],
                            "main_emotion": self._pick(["压迫", "试探", "反转", "爆发", "余波"], idx, "推进"),
                            "mini_climax_position": phase["chapter_range"].split("-")[-1],
                            "ending_hook": "阶段结尾必须留下新问题。",
                        }
                        for idx, phase in enumerate(phases)
                    ],
                    "ten_chapter_loops": ten_chapter_loops,
                    "chapter_function_table": [
                        {
                            "chapter": chapter_no,
                            "function": "目标/阻力/变化/回报/钩子",
                            "protagonist_goal": f"推进第{volume_no}卷阶段目标。",
                            "obstacle": f"{antagonist_name}相关压力升级。",
                            "emotion": self._pick(["目标", "阻碍", "误判", "反击", "钩子"], chapter_no, "推进"),
                            "information_gain": f"获得关于{self._pick(setting_titles, chapter_no, '核心规则')}的新信息。",
                            "ending_hook": "以选择、反常细节或敌方动作收束。",
                            "satisfaction_type": self._pick(market_position["satisfaction_types"], chapter_no, "阶段爽点"),
                        }
                        for chapter_no in range(chapter_start, chapter_end + 1)
                    ],
                    "repetition_check": {
                        "same_enemy_type": "不得连续两段循环使用同类敌人。",
                        "same_battle_type": "战斗、调查、谈判、舆论和潜入轮换。",
                        "same_comedy_type": "轻松桥段只作为节奏缓冲。",
                        "same_shock_reaction": "减少围观震惊，增加实际后果。",
                        "same_exposition_type": "设定通过行动、交易和失败揭露。",
                    },
                    "revision_suggestions": [],
                }
            )
        full_structure = {
            "full_story_one_sentence": story_kernel["core_story"],
            "story_stages": [
                {"stage_name": "开局入局", "volume_range": "1-3", "main_function": "建立卖点、基础世界和主角欲望", "reader_emotion": "新鲜、爽、悬疑", "protagonist_change": "从被动承受转向主动破局"},
                {"stage_name": "中段扩张", "volume_range": f"4-{max(6, volume_count - 3)}", "main_function": "扩大地图、揭开世界真相", "reader_emotion": "压迫、反转、格局扩大", "protagonist_change": "从局部胜利者变成秩序变量"},
                {"stage_name": "终局闭环", "volume_range": f"{max(7, volume_count - 2)}-{volume_count}", "main_function": "解决核心危机并回收伏笔", "reader_emotion": "燃、宿命感、闭环", "protagonist_change": "完成认知和能力闭环"},
            ],
            "ten_volume_table": ten_volume_table,
            "upgrade_curve": {
                "map": [item["core_map"] for item in ten_volume_table],
                "enemy": [item["core_enemy_or_pressure"] for item in ten_volume_table],
                "truth": [item["world_reveal"] for item in ten_volume_table],
                "status": [item["protagonist_upgrade"]["地位"] for item in ten_volume_table],
                "ability": [item["protagonist_upgrade"]["能力"] for item in ten_volume_table],
                "emotion_intensity": ["低", "中", "中高", "高", "高", "更高", "压迫", "爆发", "终局", "闭环"][:volume_count],
            },
            "ending_closure_design": {
                "main_plot_closure": ["核心矛盾正面解决", "世界规则完成重构"],
                "character_closure": ["主角认知闭环", "主要关系完成选择"],
                "foreshadowing_closure": ["终局伏笔回收", "误导版本反转为真相"],
            },
        }
        foreshadowing_ledger = [
            {
                "id": f"F{index + 1:03d}",
                "name": f"{self._pick(setting_titles, index, '核心伏笔')}的误导版本",
                "first_appearance": f"第{index * chapters_per_volume + 1}章",
                "surface_meaning": "看似普通规则或线索。",
                "true_meaning": "指向终局真相的一部分。",
                "related_characters": [protagonist_name],
                "related_factions": [self._pick(entity_names, index, "阶段势力")],
                "importance": "high" if index < 2 else "medium",
                "progress_nodes": [f"第{index + 1}卷推进", f"第{min(volume_count, index + 3)}卷变体出现"],
                "misdirection_nodes": [f"第{index + 2}卷给出错误解释"],
                "payoff_node": f"第{max(index + 4, volume_count)}卷回收",
                "payoff_method": "用角色选择和规则反制完成原来如此的回收。",
                "status": "developing",
                "risk": "如果中段不推进，会在终局显得突兀。",
            }
            for index in range(min(5, volume_count))
        ]
        foreshadowing_plan = {
            "foreshadowing_overview": "伏笔围绕规则误导、人物秘密、势力旧账和终局真相四类账本推进。",
            "ledger": foreshadowing_ledger,
            "volume_foreshadowing_plan": [
                {
                    "volume": index + 1,
                    "new_foreshadowing": [f"第{index + 1}卷新增规则误导"],
                    "progressed_foreshadowing": [foreshadowing_ledger[index % len(foreshadowing_ledger)]["id"]],
                    "paid_off_foreshadowing": [] if index < 2 else [foreshadowing_ledger[(index - 2) % len(foreshadowing_ledger)]["id"]],
                    "volume_end_hook_foreshadowing": [f"第{index + 1}卷卷末钩子伏笔"],
                }
                for index in range(volume_count)
            ],
            "risk_check": {"too_abrupt": [], "missing_payoff": [], "paid_off_too_late": [], "weak_relation_to_main_plot": [], "can_be_merged": []},
            "revision_suggestions": [],
        }
        audit_report = {
            "stage": "S11",
            "conclusion": "当前纲要可以进入最终修订版输出；未发现 A 级崩坏问题。",
            "overall_conclusion": "通过：主线、卷级目标、成长体系、势力冲突、伏笔和节拍形成闭环。",
            "issues": [],
            "passed": True,
            "next_agent": None,
            "revision_required": False,
            "special_audits": {
                "main_plot": {"conclusion": "清晰", "problems": [], "suggestions": []},
                "characters": {"conclusion": "具备弧线", "problems": [], "suggestions": ["后续新增角色继续补欲望和秘密。"]},
                "world_bible": {"conclusion": "规则可制造冲突", "problems": [], "suggestions": []},
                "power_inflation": {"conclusion": "有代价和限制", "problems": [], "suggestions": []},
                "beat": {"conclusion": "具备阶段闭环", "problems": [], "suggestions": []},
                "foreshadowing": {"conclusion": "账本可追踪", "problems": [], "suggestions": []},
                "repetition": {"conclusion": "已标记轮换策略", "problems": [], "suggestions": []},
                "ending_closure": {"conclusion": "终局闭环明确", "problems": [], "suggestions": []},
            },
            "revision_plan": ["保持主角长期欲望", "每卷检查代价和钩子", "正文生成前继续同步伏笔账本"],
            "pass_status": "通过",
            "next_step": "输出最终修订版纲要",
        }
        final_outline = {
            "title": project.title,
            "summary": story_kernel["core_story"],
            "story_state_version": "outline-v1",
            "ready_for_chapter_planning": True,
            "chapters_generated_this_request": len(chapters),
            "must_preserve": config["must_keep_elements"],
            "audit": audit_report,
        }
        story_state = {
            "config": config,
            "kernel": story_kernel,
            "raw_worldview": state.world_setting or project.premise,
            "market_position": market_position,
            "world_bible": schema_world_bible,
            "protagonist_arcs": protagonist_arcs,
            "characters": character_tree["core_character_tree"],
            "faction_conflicts": faction_conflicts,
            "power_progression": power_progression,
            "full_structure": full_structure,
            "volumes": volume_outlines,
            "beat_sheets": beat_sheets,
            "foreshadowing_ledger": foreshadowing_ledger,
            "audit_reports": [audit_report],
            "revision_history": [{"stage": "S12", "action": "逻辑审计无 A/B 级阻塞，生成最终修订版纲要。"}],
            "current_stage": "S13_FINAL_OUTLINE",
            "version": "outline-v1",
        }
        stage_flow = [
            {"stage": "S0", "name": "项目初始化", "agent_name": None, "writes": ["config", "raw_worldview"]},
            {"stage": "S1", "name": "故事核心推演", "agent_name": "one_sentence_expansion", "writes": ["kernel"]},
            {"stage": "S2", "name": "类型卖点定位", "agent_name": "genre_market_position", "writes": ["market_position"]},
            {"stage": "S3", "name": "世界观圣经生成", "agent_name": "world_bible", "writes": ["world_bible"]},
            {"stage": "S4", "name": "主角成长线生成", "agent_name": "protagonist_arc", "writes": ["protagonist_arcs"]},
            {"stage": "S5", "name": "人物树/势力冲突/金手指体系生成", "agent_name": "character_tree,faction_conflict,power_system", "writes": ["characters", "faction_conflicts", "power_progression"]},
            {"stage": "S6", "name": "总编整合第一版 Story Bible", "agent_name": "editor_orchestrator", "writes": ["hard_requirements"]},
            {"stage": "S7", "name": "全书10卷结构推演", "agent_name": "full_structure", "writes": ["full_structure"]},
            {"stage": "S8", "name": "伏笔账本生成", "agent_name": "foreshadowing_manager", "writes": ["foreshadowing_ledger"]},
            {"stage": "S9", "name": "逐卷50章大纲推演", "agent_name": "volume_outline", "writes": ["volumes"]},
            {"stage": "S10", "name": "章节节拍表生成", "agent_name": "beat_control", "writes": ["beat_sheets"]},
            {"stage": "S11", "name": "逻辑审计", "agent_name": "logic_audit", "writes": ["audit_reports"]},
            {"stage": "S12", "name": "返工修订", "agent_name": "editor_orchestrator", "writes": ["revision_history"]},
            {"stage": "S13", "name": "最终完整故事纲要输出", "agent_name": None, "writes": ["final_outline"]},
        ]
        agent_outputs = {
            "editor_orchestrator": {
                "current_judgment": "可以进入逐卷大纲和章节规划。",
                "core_issues": [],
                "dispatch_decision": {"next_agent": "one_sentence_expansion", "task": "从一句话故事建立长篇核心。"},
                "hard_requirements": config["forbidden_elements"],
                "pass_criteria": ["A 级问题为 0", "每卷都有目标、阻力、代价、钩子", "伏笔有回收路径"],
            },
            "one_sentence_expansion": story_kernel,
            "genre_market_position": market_position,
            "world_bible": schema_world_bible,
            "protagonist_arc": {"volume_growth": protagonist_arcs, "non_breaking_principles": ["欲望不断线", "胜利必须有代价", "认知成长与能力成长对应"]},
            "character_tree": character_tree,
            "faction_conflict": faction_conflicts,
            "power_system": power_progression,
            "full_structure": full_structure,
            "volume_outline": {"volumes": volume_outlines},
            "beat_control": {"beat_sheets": beat_sheets},
            "foreshadowing_manager": foreshadowing_plan,
            "logic_audit": audit_report,
        }
        output_key_by_agent = {
            "editor_orchestrator": "总编统筹决策",
            "one_sentence_expansion": "故事核心",
            "genre_market_position": "类型卖点定位",
            "world_bible": "世界圣经",
            "protagonist_arc": "主角成长线",
            "character_tree": "人物树",
            "faction_conflict": "势力冲突表",
            "power_system": "金手指升级体系",
            "full_structure": "全书10卷总纲",
            "volume_outline": "逐卷50章大纲",
            "beat_control": "章节节拍表",
            "foreshadowing_manager": "伏笔账本",
            "logic_audit": "逻辑审计报告",
        }
        agent_chain = [
            {
                "agent_name": agent_name,
                "role": AGENT_SPECS_BY_NAME[agent_name].role,
                "stage": next((item["stage"] for item in stage_flow if item["agent_name"] and agent_name in item["agent_name"].split(",")), "S0"),
                "output_key": output_key_by_agent[agent_name],
                "status": "succeeded",
            }
            for agent_name in OUTLINE_AGENT_SEQUENCE
        ]
        return {
            "story_state": story_state,
            "推演状态机流程": stage_flow,
            "13Agent推演链": agent_chain,
            "agent_outputs": agent_outputs,
            "故事核心": story_kernel,
            "类型卖点定位": market_position,
            "主角成长线": protagonist_arcs,
            "人物树": character_tree,
            "势力冲突表": faction_conflicts,
            "金手指升级体系": power_progression,
            "全书10卷总纲": full_structure,
            "逐卷50章大纲": volume_outlines,
            "章节节拍表": beat_sheets,
            "伏笔账本": foreshadowing_plan,
            "逻辑审计报告": audit_report,
            "最终修订版纲要": final_outline,
        }

    def _sync_outline_volumes(self, db: Session, project: models.Project, volume_table: list[dict[str, Any]]) -> None:
        for item in volume_table:
            label = str(item.get("第X卷") or "")
            volume_no = int("".join([char for char in label if char.isdigit()]) or len(volume_table))
            row = db.query(models.Volume).filter(models.Volume.project_id == project.id, models.Volume.volume_no == volume_no).first()
            if row is None:
                row = models.Volume(id=generate_id("vol"), project_id=project.id, volume_no=volume_no, title=item.get("卷名", f"第{volume_no}卷"), sort_order=volume_no)
                db.add(row)
            row.title = item.get("卷名", row.title)
            row.outline = self._format_volume_outline_text(item)

    def _format_mapping_lines(self, payload: dict[str, Any], indent: str = "") -> list[str]:
        lines: list[str] = []
        for key, value in payload.items():
            if isinstance(value, dict):
                lines.append(f"{indent}{key}：")
                lines.extend(self._format_mapping_lines(value, f"{indent}  "))
            elif isinstance(value, list):
                lines.append(f"{indent}{key}：{'、'.join(str(item) for item in value) if value else '暂无'}")
            else:
                lines.append(f"{indent}{key}：{value or '暂无'}")
        return lines

    def _format_volume_outline_text(self, item: dict[str, Any]) -> str:
        phase_blocks = item.get("50章高密度剧情流水线执行协议", [])
        lines = [
            f"{item.get('第X卷', '分卷')}：{item.get('卷名', '未命名卷')}",
            f"章节区间：{item.get('章节区间', '未设置')}",
            f"核心地图：{item.get('核心地图', '未设置')}",
            "",
            "本卷主角提升目标：",
            *self._format_mapping_lines(item.get("本卷主角提升目标", {}) if isinstance(item.get("本卷主角提升目标"), dict) else {}, "  "),
            "",
            "剧情多轨道架构：",
            *self._format_mapping_lines(item.get("剧情多轨道架构", {}) if isinstance(item.get("剧情多轨道架构"), dict) else {}, "  "),
            "",
            "50章高密度剧情流水线执行协议：",
        ]
        for phase in phase_blocks if isinstance(phase_blocks, list) else []:
            if not isinstance(phase, dict):
                continue
            lines.append(f"{phase.get('phase', 'Phase')}（{phase.get('章节区间', '章节区间未设置')}）：")
            for event_no in range(1, 6):
                event = phase.get(f"大事件{event_no}")
                if event:
                    lines.append(f"  大事件{event_no}：{event}")
        lines.extend(
            [
                "",
                f"卷末大钩子：{item.get('卷末大钩子', '未设置')}",
                "",
                "全卷逻辑审计：",
                *self._format_mapping_lines(item.get("全卷逻辑审计", {}) if isinstance(item.get("全卷逻辑审计"), dict) else {}, "  "),
            ]
        )
        return "\n".join(line for line in lines if line is not None).strip()

    def _upsert_workflow_characters(self, db: Session, project_id: str, characters: list[dict[str, Any]], job_id: str) -> None:
        for item in characters:
            name = item.get("name", "未命名角色")
            row = db.query(models.Character).filter(models.Character.project_id == project_id, models.Character.name == name).first()
            if row is None:
                row = models.Character(id=generate_id("chr"), project_id=project_id, name=name, role=item.get("role_type", "supporting"))
                db.add(row)
            row.role_type = item.get("role_type", row.role_type)
            row.importance_level = item.get("importance_level", row.importance_level)
            row.importance_score = int(item.get("importance_score", row.importance_score))
            row.summary = item.get("summary", row.summary)
            row.goals_json = dumps(item.get("goals", loads(row.goals_json, [])))
            row.character_arc = item.get("character_arc", row.character_arc)
            row.updated_reason = f"Agent workflow {job_id}"
            self._ensure_graph_node(db, project_id, "character", row.id, row.name, row.importance_level, row.importance_score)
            db.flush()
            self._sync_canon_ref(
                db,
                project_id,
                "character",
                row,
                source_agent="chapter_writing",
                source_job_id=job_id,
                change_reason=row.updated_reason,
            )

    def _folder_node(self, node_id: str, parent_id: str | None, title: str, sort_order: int) -> dict[str, Any]:
        return {
            "id": node_id,
            "project_id": "",
            "parent_id": parent_id,
            "node_type": "folder",
            "ref_type": "folder",
            "ref_id": node_id.removeprefix("folder:"),
            "title": title,
            "sort_order": sort_order,
            "status": "active",
            "importance_level": "medium",
            "activity_status": "active",
            "metadata": {},
            "content": None,
            "created_at": None,
            "updated_at": None,
        }

    def _normalize_canon_ref_type(self, ref_type: str) -> str:
        normalized = ref_type.strip().replace("-", "_").lower()
        mapping = {
            "characters": "character",
            "story_character": "character",
            "entities": "entity",
            "story_entity": "entity",
            "world_facts": "world_fact",
            "world_fact": "world_fact",
            "foreshadowing_items": "foreshadowing",
            "foreshadowing": "foreshadowing",
        }
        normalized = mapping.get(normalized, normalized)
        if normalized not in {"character", "entity", "world_fact", "foreshadowing"}:
            raise _bad_request("不支持的设定类型", {"ref_type": ref_type})
        return normalized

    def _importance_order(self, value: str) -> int:
        return {"core": 0, "major": 1, "medium": 2, "minor": 3}.get(value, 9)

    def _text_order(self, value: str) -> int:
        return sum(ord(char) for char in value[:8]) % 100

    def _importance_label(self, value: str) -> str:
        return {"core": "核心", "major": "重要", "medium": "中等", "minor": "次要"}.get(value, value or "中等")

    def _entity_type_label(self, value: str) -> str:
        labels = {
            "location": "地点",
            "organization": "组织",
            "item": "物品",
            "event": "事件",
            "concept": "概念",
            "rule": "规则",
            "clue": "线索",
            "timeline_event": "时间线事件",
        }
        return labels.get(value, value or "实体")

    def _world_fact_category_label(self, value: str) -> str:
        labels = {
            "geography": "地理",
            "history": "历史",
            "magic_rule": "能力/规则",
            "technology": "技术",
            "politics": "政治",
            "culture": "文化",
            "economy": "经济",
            "religion": "宗教",
            "organization": "组织",
            "timeline": "时间线",
            "taboo": "禁忌",
        }
        return labels.get(value, value or "事实")

    def _foreshadowing_status_label(self, value: str) -> str:
        labels = {"planned": "计划中", "planted": "已埋设", "paid_off": "已回收", "abandoned": "已废弃", "candidate": "候选"}
        return labels.get(value, value or "伏笔")

    def _canon_rows_for_type(self, db: Session, project_id: str, ref_type: str) -> list[Any]:
        ref_type = self._normalize_canon_ref_type(ref_type)
        if ref_type == "character":
            return db.query(models.Character).filter(models.Character.project_id == project_id, models.Character.status != "archived").all()
        if ref_type == "entity":
            return db.query(models.StoryEntity).filter(models.StoryEntity.project_id == project_id, models.StoryEntity.current_status != "archived").all()
        if ref_type == "world_fact":
            return db.query(models.WorldFact).filter(models.WorldFact.project_id == project_id).all()
        if ref_type == "foreshadowing":
            return db.query(models.ForeshadowingItem).filter(models.ForeshadowingItem.project_id == project_id, models.ForeshadowingItem.payoff_status != "abandoned").all()
        return []

    def _similarity_score(self, left: str, right: str) -> float:
        left_norm = "".join(str(left or "").lower().split())
        right_norm = "".join(str(right or "").lower().split())
        if not left_norm or not right_norm:
            return 0.0
        if left_norm == right_norm:
            return 1.0
        if left_norm in right_norm or right_norm in left_norm:
            return 0.86
        return difflib.SequenceMatcher(None, left_norm, right_norm).ratio()

    def _merge_canon_content(self, target: dict[str, Any], source: dict[str, Any], ref_type: str) -> dict[str, Any]:
        merged = dict(target)
        for key, value in source.items():
            if key in {"id", "project_id", "created_at", "updated_at"}:
                continue
            current = merged.get(key)
            if isinstance(current, list) or isinstance(value, list):
                merged[key] = list(dict.fromkeys([*(current if isinstance(current, list) else ([] if current in (None, "") else [current])), *(value if isinstance(value, list) else ([] if value in (None, "") else [value]))]))
            elif current in (None, "") and value not in (None, ""):
                merged[key] = value
            elif key in {"summary", "description", "content", "planned_payoff"} and value and value != current:
                merged[key] = f"{current}\n\n合并补充：{value}".strip()
            elif key in {"importance_score"}:
                merged[key] = max(int(current or 0), int(value or 0))
            elif key in {"confidence"}:
                merged[key] = max(float(current or 0), float(value or 0))
        merged["updated_reason"] = "重复项合并" if ref_type == "character" else merged.get("updated_reason", "重复项合并")
        return merged

    def _render_canon_markdown(self, package: dict[str, Any]) -> str:
        project = package["project"]
        lines = [f"# {project['title']} 正典包", "", f"- 题材：{project.get('genre', '')}", f"- 目标读者：{project.get('target_reader', '')}", f"- 导出时间：{package.get('exported_at')}", ""]
        if package.get("story_bible"):
            bible = package["story_bible"]
            lines.extend(["## 故事圣经", "", bible.get("world_setting", ""), "", f"主线冲突：{bible.get('main_conflict', '')}", ""])
        sections = [
            ("人物", "characters", "name", "summary"),
            ("实体", "entities", "name", "description"),
            ("世界事实", "world_facts", "title", "content"),
            ("伏笔", "foreshadowing", "content", "planned_payoff"),
        ]
        for title, key, name_field, body_field in sections:
            lines.extend([f"## {title}", ""])
            for item in package.get(key, []):
                lines.extend([f"### {item.get(name_field, '未命名')}", "", str(item.get(body_field, "")), ""])
        lines.extend(["## 版本索引", ""])
        for version in package.get("versions", []):
            lines.append(f"- {version['ref_type']}:{version['ref_id']} v{version['version_no']} · {version.get('source_agent', '')} · {version.get('change_reason', '')}")
        lines.extend(["", "## 候选审计", ""])
        for proposal in package.get("proposals", []):
            lines.append(f"- {proposal['operation']} {proposal['target_type']} · {proposal['approval_status']} · {proposal.get('reason', '')}")
        return "\n".join(lines).strip() + "\n"

    def _locked_fields_for_ref(self, db: Session, project_id: str, ref_type: str, ref_id: str) -> list[str]:
        node = db.query(models.CanonNode).filter(models.CanonNode.project_id == project_id, models.CanonNode.ref_type == ref_type, models.CanonNode.ref_id == ref_id).first()
        if not node:
            return []
        return list(loads(node.metadata_json, {}).get("locked_fields") or [])

    def _locked_field_changes(self, locked_fields: list[str], before: dict[str, Any], after: dict[str, Any]) -> list[str]:
        changed = []
        for field in locked_fields:
            if field in after and json.dumps(before.get(field), ensure_ascii=False, sort_keys=True) != json.dumps(after.get(field), ensure_ascii=False, sort_keys=True):
                changed.append(field)
        return changed

    def _guard_locked_fields_or_propose(
        self,
        db: Session,
        project_id: str,
        ref_type: str,
        ref_id: str,
        source_agent: str,
        before: dict[str, Any],
        after: dict[str, Any],
        *,
        source_chapter_id: str | None = None,
        reason: str = "锁定字段保护",
    ) -> None:
        if source_agent in {"manual", "user", "rollback"}:
            return
        locked = self._locked_fields_for_ref(db, project_id, ref_type, ref_id)
        changed = self._locked_field_changes(locked, before, after)
        if not changed:
            return
        proposal = self._create_canon_proposal(
            db,
            project_id,
            ref_type,
            after,
            target_id=ref_id,
            operation="update",
            before=before,
            source_chapter_id=source_chapter_id,
            source_agent=source_agent,
            confidence=0.8,
            reason=f"{reason}：{', '.join(changed)}",
        )
        db.commit()
        raise _conflict("设定字段已锁定，Agent 更新已转入候选变更池", {"locked_fields": changed, "proposal_id": proposal.id})

    def _canon_ref_content(self, ref_type: str, row: Any) -> dict[str, Any]:
        if ref_type == "character":
            return serialize_character(row)
        if ref_type == "entity":
            return serialize_story_entity(row)
        if ref_type == "world_fact":
            return serialize_world_fact(row)
        if ref_type == "foreshadowing":
            return serialize_foreshadowing_item(row)
        raise _bad_request("不支持的设定类型", {"ref_type": ref_type})

    def _canon_ref_title(self, ref_type: str, content: dict[str, Any]) -> str:
        if ref_type == "world_fact":
            return str(content.get("title") or "未命名世界观事实")
        if ref_type == "foreshadowing":
            return str(content.get("content") or "未命名伏笔")[:48]
        return str(content.get("name") or content.get("title") or "未命名设定")

    def _canon_ref_row(self, db: Session, project_id: str, ref_type: str, ref_id: str) -> Any:
        model_by_type = {
            "character": models.Character,
            "entity": models.StoryEntity,
            "world_fact": models.WorldFact,
            "foreshadowing": models.ForeshadowingItem,
        }
        model = model_by_type[ref_type]
        row = db.get(model, ref_id)
        if row is None or row.project_id != project_id:
            raise _not_found("设定不存在")
        return row

    def _apply_canon_content(self, row: Any, ref_type: str, content: dict[str, Any]) -> None:
        if ref_type == "character":
            for field in ("name", "role", "role_type", "importance_level", "importance_score", "summary", "appearance", "personality", "character_arc", "current_status", "updated_reason", "status", "source"):
                if field in content and hasattr(row, field):
                    setattr(row, field, content[field])
            for field in ("aliases", "goals", "motivations", "secrets", "abilities", "weaknesses", "related_entity_ids", "related_character_ids", "relations"):
                if field in content:
                    setattr(row, f"{field}_json", dumps(content[field] or []))
            return
        if ref_type == "entity":
            for field in ("entity_type", "name", "importance_level", "importance_score", "description", "current_status", "source"):
                if field in content and hasattr(row, field):
                    setattr(row, field, content[field])
            return
        if ref_type == "world_fact":
            for field in ("category", "title", "content", "importance_level", "importance_score", "confidence", "source_chapter_id"):
                if field in content and hasattr(row, field):
                    setattr(row, field, content[field])
            if "related_entity_ids" in content:
                row.related_entity_ids_json = dumps(content.get("related_entity_ids") or [])
            return
        if ref_type == "foreshadowing":
            for field in ("content", "planted_chapter_id", "planned_payoff_chapter_id", "actual_payoff_chapter_id", "planned_payoff", "payoff_status", "importance_level", "importance_score", "source"):
                if field in content and hasattr(row, field):
                    setattr(row, field, content[field])
            if "related_character_ids" in content:
                row.related_character_ids_json = dumps(content.get("related_character_ids") or [])
            if "related_entity_ids" in content:
                row.related_entity_ids_json = dumps(content.get("related_entity_ids") or [])

    def _ensure_canon_node(
        self,
        db: Session,
        project_id: str,
        ref_type: str,
        ref_id: str,
        title: str,
        importance_level: str,
        activity_status: str,
        metadata: dict[str, Any] | None = None,
        *,
        parent_id: str | None = None,
    ) -> models.CanonNode:
        row = db.query(models.CanonNode).filter(models.CanonNode.project_id == project_id, models.CanonNode.ref_type == ref_type, models.CanonNode.ref_id == ref_id).first()
        if row is None:
            row = models.CanonNode(id=generate_id("cnd"), project_id=project_id, ref_type=ref_type, ref_id=ref_id, title=title)
            db.add(row)
        existing_metadata = loads(row.metadata_json, {})
        if parent_id and not parent_id.startswith("folder:"):
            row.parent_id = parent_id
        elif parent_id:
            existing_metadata["display_parent_id"] = parent_id
        row.node_type = "item"
        row.title = title
        row.importance_level = importance_level or "medium"
        row.activity_status = activity_status or "active"
        merged_metadata = {**existing_metadata, **(metadata or {})}
        row.metadata_json = dumps(merged_metadata)
        row.updated_at = utcnow()
        return row

    def _next_canon_version_no(self, db: Session, project_id: str, ref_type: str, ref_id: str) -> int:
        current = (
            db.query(func.max(models.CanonVersion.version_no))
            .filter(models.CanonVersion.project_id == project_id, models.CanonVersion.ref_type == ref_type, models.CanonVersion.ref_id == ref_id)
            .scalar()
        )
        return int(current or 0) + 1

    def _record_canon_version(
        self,
        db: Session,
        project_id: str,
        ref_type: str,
        ref_id: str,
        content: dict[str, Any],
        *,
        source_chapter_id: str | None = None,
        source_job_id: str | None = None,
        source_agent: str = "manual",
        change_reason: str = "",
        confidence: float = 1.0,
    ) -> models.CanonVersion:
        version = models.CanonVersion(
            id=generate_id("cvn"),
            project_id=project_id,
            ref_type=ref_type,
            ref_id=ref_id,
            version_no=self._next_canon_version_no(db, project_id, ref_type, ref_id),
            content_json=dumps(content),
            source_chapter_id=source_chapter_id,
            source_job_id=source_job_id,
            source_agent=source_agent,
            change_reason=change_reason,
            confidence=float(confidence),
        )
        db.add(version)
        db.flush()
        return version

    def _sync_canon_ref(
        self,
        db: Session,
        project_id: str,
        ref_type: str,
        row: Any,
        *,
        source_chapter_id: str | None = None,
        source_job_id: str | None = None,
        source_agent: str = "manual",
        change_reason: str = "",
        confidence: float | None = None,
    ) -> models.CanonVersion:
        content = self._canon_ref_content(ref_type, row)
        self._ensure_canon_node(
            db,
            project_id,
            ref_type,
            row.id,
            self._canon_ref_title(ref_type, content),
            str(content.get("importance_level") or "medium"),
            str(content.get("current_status") or content.get("payoff_status") or "active"),
            {"source_agent": source_agent, "source_chapter_id": source_chapter_id},
        )
        return self._record_canon_version(
            db,
            project_id,
            ref_type,
            row.id,
            content,
            source_chapter_id=source_chapter_id,
            source_job_id=source_job_id,
            source_agent=source_agent,
            change_reason=change_reason,
            confidence=float(confidence if confidence is not None else content.get("confidence") or 1.0),
        )

    def _create_canon_proposal(
        self,
        db: Session,
        project_id: str,
        target_type: str,
        after: dict[str, Any],
        *,
        target_id: str | None = None,
        operation: str = "create",
        before: dict[str, Any] | None = None,
        source_chapter_id: str | None = None,
        source_job_id: str | None = None,
        source_agent: str = "agent",
        confidence: float = 0.8,
        reason: str = "",
    ) -> models.CanonChangeProposal:
        proposal = models.CanonChangeProposal(
            id=generate_id("cpr"),
            project_id=project_id,
            target_type=self._normalize_canon_ref_type(target_type),
            target_id=target_id,
            operation=operation,
            before_json=dumps(before or {}),
            after_json=dumps(after),
            source_chapter_id=source_chapter_id,
            source_job_id=source_job_id,
            source_agent=source_agent,
            confidence=float(confidence),
            reason=reason,
        )
        db.add(proposal)
        db.flush()
        return proposal

    def _canon_health(self, db: Session, project_id: str) -> dict[str, Any]:
        characters = db.query(models.Character).filter(models.Character.project_id == project_id, models.Character.status != "archived").count()
        entities = db.query(models.StoryEntity).filter(models.StoryEntity.project_id == project_id, models.StoryEntity.current_status != "archived").count()
        world_facts = db.query(models.WorldFact).filter(models.WorldFact.project_id == project_id).count()
        foreshadowing = db.query(models.ForeshadowingItem).filter(models.ForeshadowingItem.project_id == project_id, models.ForeshadowingItem.payoff_status != "abandoned").count()
        versioned_refs = {
            (row.ref_type, row.ref_id)
            for row in db.query(models.CanonVersion.ref_type, models.CanonVersion.ref_id).filter(models.CanonVersion.project_id == project_id).all()
        }
        official_refs: set[tuple[str, str]] = set()
        official_refs.update(("character", row.id) for row in db.query(models.Character.id).filter(models.Character.project_id == project_id, models.Character.status != "archived").all())
        official_refs.update(("entity", row.id) for row in db.query(models.StoryEntity.id).filter(models.StoryEntity.project_id == project_id, models.StoryEntity.current_status != "archived").all())
        official_refs.update(("world_fact", row.id) for row in db.query(models.WorldFact.id).filter(models.WorldFact.project_id == project_id).all())
        official_refs.update(("foreshadowing", row.id) for row in db.query(models.ForeshadowingItem.id).filter(models.ForeshadowingItem.project_id == project_id, models.ForeshadowingItem.payoff_status != "abandoned").all())
        pending = db.query(models.CanonChangeProposal).filter(models.CanonChangeProposal.project_id == project_id, models.CanonChangeProposal.approval_status == "pending").count()
        low_confidence_facts = db.query(models.WorldFact).filter(models.WorldFact.project_id == project_id, models.WorldFact.confidence < 0.7).count()
        low_confidence_proposals = db.query(models.CanonChangeProposal).filter(models.CanonChangeProposal.project_id == project_id, models.CanonChangeProposal.approval_status == "pending", models.CanonChangeProposal.confidence < 0.7).count()
        return {
            "official_count": len(official_refs),
            "versioned_count": len(official_refs.intersection(versioned_refs)),
            "unversioned_count": len(official_refs.difference(versioned_refs)),
            "pending_proposal_count": pending,
            "low_confidence_count": low_confidence_facts + low_confidence_proposals,
            "conflict_count": 0,
            "by_type": {
                "characters": characters,
                "entities": entities,
                "world_facts": world_facts,
                "foreshadowing": foreshadowing,
            },
            "recommendations": [
                "优先审批候选设定，避免正文生成读取到未确认事实。",
                "低置信度设定建议补充来源章节或标记为待确认。",
                "核心人物和世界规则建议锁定后再进入批量正文生成。",
            ],
        }

    def _persist_canon_updates(self, db: Session, project_id: str, chapter_id: str | None, updates: dict[str, Any]) -> None:
        for item in updates.get("character_updates", []):
            name = item.get("name", "未命名角色")
            row = db.query(models.Character).filter(models.Character.project_id == project_id, models.Character.name == name).first()
            if row:
                row.updated_reason = item.get("updated_reason", row.updated_reason)
                row.last_seen_chapter_id = chapter_id
                self._sync_canon_ref(
                    db,
                    project_id,
                    "character",
                    row,
                    source_chapter_id=chapter_id,
                    source_agent="canon_curator",
                    change_reason=row.updated_reason,
                )
        for item in updates.get("entity_updates", []):
            entity = self._upsert_entity(db, project_id, item.get("entity_type", "event"), item.get("name", "未命名实体"), item.get("importance_score", 50), chapter_id)
            self._ensure_graph_node(db, project_id, "entity", entity.id, entity.name, entity.importance_level, entity.importance_score)
            self._sync_canon_ref(
                db,
                project_id,
                "entity",
                entity,
                source_chapter_id=chapter_id,
                source_agent="canon_curator",
                change_reason="章后设定整理",
            )
        for item in updates.get("world_fact_updates", []):
            fact = self._upsert_world_fact(db, project_id, item.get("category", "timeline"), item.get("title", "新世界观事实"), item.get("content", ""), "medium", item.get("importance_score", 55), item.get("confidence", 0.75), chapter_id)
            self._ensure_graph_node(db, project_id, "world_fact", fact.id, fact.title, fact.importance_level, fact.importance_score)
            self._sync_canon_ref(
                db,
                project_id,
                "world_fact",
                fact,
                source_chapter_id=chapter_id,
                source_agent="canon_curator",
                change_reason="章后设定整理",
                confidence=fact.confidence,
            )

    def _upsert_entity(self, db: Session, project_id: str, entity_type: str, name: str, importance_score: int, chapter_id: str | None) -> models.StoryEntity:
        row = db.query(models.StoryEntity).filter(models.StoryEntity.project_id == project_id, models.StoryEntity.entity_type == entity_type, models.StoryEntity.name == name).first()
        if row is None:
            row = models.StoryEntity(id=generate_id("ent"), project_id=project_id, entity_type=entity_type, name=name, importance_score=int(importance_score), first_appearance_chapter_id=chapter_id, source="canon_curator")
            db.add(row)
        row.last_seen_chapter_id = chapter_id
        return row

    def _upsert_world_fact(self, db: Session, project_id: str, category: str, title: str, content: str, importance_level: str, importance_score: int, confidence: float, chapter_id: str | None) -> models.WorldFact:
        row = db.query(models.WorldFact).filter(models.WorldFact.project_id == project_id, models.WorldFact.title == title).first()
        if row is None:
            row = models.WorldFact(id=generate_id("wld"), project_id=project_id, category=category, title=title)
            db.add(row)
        row.content = content or row.content
        row.importance_level = importance_level
        row.importance_score = int(importance_score)
        row.confidence = float(confidence)
        row.source_chapter_id = chapter_id
        return row

    def _ensure_graph_node(self, db: Session, project_id: str, node_type: str, ref_id: str, label: str, importance_level: str, importance_score: int) -> models.GraphNode:
        row = db.query(models.GraphNode).filter(models.GraphNode.project_id == project_id, models.GraphNode.node_type == node_type, models.GraphNode.ref_id == ref_id).first()
        if row is None:
            row = models.GraphNode(id=generate_id("gnd"), project_id=project_id, node_type=node_type, ref_id=ref_id, label=label)
            db.add(row)
        row.label = label
        row.importance_level = importance_level
        row.importance_score = int(importance_score)
        return row

    def _ensure_graph_edge(
        self,
        db: Session,
        project_id: str,
        source_node_id: str,
        target_node_id: str,
        edge_type: str,
        label: str,
        importance_score: int,
        confidence: float = 0.8,
        evidence: str = "",
        source_chapter_id: str | None = None,
    ) -> models.GraphEdge:
        db.flush()
        row = (
            db.query(models.GraphEdge)
            .filter(
                models.GraphEdge.project_id == project_id,
                models.GraphEdge.source_node_id == source_node_id,
                models.GraphEdge.target_node_id == target_node_id,
                models.GraphEdge.edge_type == edge_type,
            )
            .first()
        )
        if row is None:
            row = models.GraphEdge(
                id=generate_id("ged"),
                project_id=project_id,
                source_node_id=source_node_id,
                target_node_id=target_node_id,
                edge_type=edge_type,
            )
            db.add(row)
        row.label = label
        row.importance_score = int(importance_score)
        row.confidence = float(confidence)
        row.evidence = evidence
        row.source_chapter_id = source_chapter_id
        return row

    def _sync_foreshadowing_graph(self, db: Session, item: models.ForeshadowingItem, payoff: bool = False) -> None:
        clue_node = self._ensure_graph_node(db, item.project_id, "clue", item.id, item.content, item.importance_level, item.importance_score)
        related_character_ids = loads(item.related_character_ids_json, [])
        related_entity_ids = loads(item.related_entity_ids_json, [])
        for character_id in related_character_ids:
            character = db.get(models.Character, character_id)
            if character is None or character.project_id != item.project_id:
                continue
            character_node = self._ensure_graph_node(db, item.project_id, "character", character.id, character.name, character.importance_level, character.importance_score)
            self._ensure_graph_edge(
                db,
                item.project_id,
                clue_node.id,
                character_node.id,
                "related_character",
                "关联角色",
                item.importance_score,
                evidence=item.content,
                source_chapter_id=item.chapter_id,
            )
        for entity_id in related_entity_ids:
            entity = db.get(models.StoryEntity, entity_id)
            if entity is None or entity.project_id != item.project_id:
                continue
            entity_node = self._ensure_graph_node(db, item.project_id, "entity", entity.id, entity.name, entity.importance_level, entity.importance_score)
            self._ensure_graph_edge(
                db,
                item.project_id,
                clue_node.id,
                entity_node.id,
                "related_entity",
                "关联实体",
                item.importance_score,
                evidence=item.content,
                source_chapter_id=item.chapter_id,
            )
        if payoff and item.actual_payoff_chapter_id:
            chapter = db.get(models.Chapter, item.actual_payoff_chapter_id)
            if chapter and chapter.project_id == item.project_id:
                chapter_node = self._ensure_graph_node(
                    db,
                    item.project_id,
                    "chapter",
                    chapter.id,
                    f"第{chapter.chapter_no}章 {chapter.title}",
                    "medium",
                    60,
                )
                self._ensure_graph_edge(
                    db,
                    item.project_id,
                    clue_node.id,
                    chapter_node.id,
                    "paid_off_in",
                    "回收于",
                    item.importance_score,
                    confidence=1.0,
                    evidence=item.planned_payoff,
                    source_chapter_id=chapter.id,
                )

    def _chapter_chat_prompts(
        self,
        project: models.Project,
        chapter: models.Chapter,
        canon_context: dict[str, Any],
        source_text: str,
        selected_text: str,
        request: ChapterChatRequest,
    ) -> tuple[str, str]:
        mode_labels = {
            "revise": "按用户要求局部改写",
            "polish": "润色语言和氛围",
            "expand": "扩写细节但不改变事件",
            "tighten": "压缩冗余并增强节奏",
            "continue": "承接当前片段续写",
        }
        story_bible = canon_context.get("story_bible") or {}
        characters = canon_context.get("characters", [])[:6]
        world_facts = canon_context.get("world_facts", [])[:8]
        issues = canon_context.get("unresolved_continuity_issues", [])[:6]
        system_prompt = (
            "你是长篇小说章节局部修改助手。你必须严格基于 canon_context 和当前章节，"
            "只产出可由用户确认后应用的修改建议，不得声称已经写入正文或设定集。"
            "如果用户提供选区，只改写选区；如果没有选区，给出适合追加或替换当前位置的建议。"
            "返回必须是 JSON，不要 Markdown 代码块。格式："
            '{"replacement":"建议文本","reasoning":"修改理由","checklist":["检查点"]}'
        )
        user_prompt = "\n".join(
            [
                f"项目：{project.title} / {project.genre}",
                f"章节：第{chapter.chapter_no}章《{chapter.title}》",
                f"章节目标：{chapter.outline or '未填写'}",
                f"风格要求：{project.style_guide or story_bible.get('style_guide') or '保持当前文本风格'}",
                f"世界观：{story_bible.get('world_setting') or project.premise}",
                f"当前模式：{mode_labels.get(request.mode, mode_labels['revise'])}",
                f"用户要求：{request.instruction}",
                "核心角色：" + json.dumps(characters, ensure_ascii=False)[:2400],
                "关键世界事实：" + json.dumps(world_facts, ensure_ascii=False)[:2400],
                "连续性问题：" + json.dumps(issues, ensure_ascii=False)[:1600],
                "待修改选区：" + (selected_text or "无选区，请基于当前正文给出可应用建议。"),
                "当前章节正文：" + source_text[:12000],
                "输出要求：replacement 只能包含建议文本本身；不要解释流程；不要覆盖用户手动设定；不要引入低置信度新设定。",
            ]
        )
        return system_prompt, user_prompt

    def _parse_chapter_chat_payload(self, content: str) -> dict[str, Any]:
        stripped = content.strip()
        if stripped.startswith("```"):
            stripped = stripped.strip("`")
            if stripped.startswith("json"):
                stripped = stripped[4:].strip()
        try:
            parsed = json.loads(stripped)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            start = stripped.find("{")
            end = stripped.rfind("}")
            if start >= 0 and end > start:
                try:
                    parsed = json.loads(stripped[start : end + 1])
                    return parsed if isinstance(parsed, dict) else {}
                except json.JSONDecodeError:
                    return {}
        return {}

    def _local_chapter_chat_payload(self, source_text: str, request: ChapterChatRequest) -> dict[str, Any]:
        source = source_text.strip() or "（当前没有可改写文本，请先选择或输入正文片段。）"
        prefix = {
            "revise": "按要求调整",
            "polish": "润色氛围",
            "expand": "补足细节",
            "tighten": "压缩节奏",
            "continue": "顺势续写",
        }.get(request.mode, "按要求调整")
        replacement = source
        if request.mode == "continue":
            replacement = f"{source}\n\n　　她没有立刻移开目光，而是顺着这份异常继续追问下去。"
        elif request.mode == "tighten":
            replacement = source.replace("慢慢", "").replace("一点一点", "")
        elif request.mode == "expand":
            replacement = f"{source}\n\n　　空气像被谁按低了一寸，连停在耳边的呼吸声都显得陌生。"
        return {
            "replacement": replacement,
            "reasoning": f"本地降级建议：未调用远程模型，已保留原片段并按“{request.instruction}”给出可验证的{prefix}草案。",
            "checklist": ["未直接写入正文", "保留原始事件", "需要用户确认后应用"],
        }

    def _sse_event(self, event: str, payload: dict[str, Any]) -> str:
        return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

    def _chunk_text(self, text: str, size: int) -> Iterator[str]:
        for index in range(0, len(text), size):
            yield text[index : index + size]

    def _render_export_content(self, project: models.Project, chapters: list[models.Chapter], request: ExportRequest) -> str:
        lines = [f"# {project.title}", "", f"题材：{project.genre}", f"目标读者：{project.target_reader}", ""]
        if request.include_summary:
            lines.extend(["## 简介", project.premise, ""])
        for chapter in chapters:
            lines.extend([f"## 第{chapter.chapter_no}章 {chapter.title}", "", chapter.final_text or chapter.draft_text or chapter.outline, ""])
        return "\n".join(lines)

    def _write_export_file(self, path: Path, content: str, fmt: str, title: str) -> None:
        if fmt in {"markdown", "txt", "html", "pdf"}:
            if fmt == "html":
                path.write_text(f"<html><head><title>{title}</title></head><body><pre>{content}</pre></body></html>", encoding="utf-8")
            elif fmt == "pdf":
                # Minimal readable text payload with .pdf extension for MVP export preview.
                path.write_text("%PDF-1.4\n% Narraverse Engine text export\n" + content, encoding="utf-8")
            else:
                path.write_text(content, encoding="utf-8")
            return
        if fmt == "epub":
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("mimetype", "application/epub+zip")
                archive.writestr("OEBPS/content.xhtml", f"<html><body><pre>{content}</pre></body></html>")
            return
        if fmt == "word":
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("[Content_Types].xml", "<?xml version='1.0'?><Types xmlns='http://schemas.openxmlformats.org/package/2006/content-types'><Default Extension='xml' ContentType='application/xml'/><Override PartName='/word/document.xml' ContentType='application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml'/></Types>")
                archive.writestr("word/document.xml", f"<?xml version='1.0'?><w:document xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'><w:body><w:p><w:r><w:t>{content[:30000]}</w:t></w:r></w:p></w:body></w:document>")


studio_service = StudioService()
