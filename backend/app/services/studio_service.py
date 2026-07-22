from __future__ import annotations

import difflib
import hashlib
import json
from pathlib import Path
import queue
import random
import re
import threading
import zipfile
from typing import Any, Iterator

from fastapi import HTTPException
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.agents.contracts import NovelStudioState
from app.agents.chapter_writing.service import chapter_writing_service
from app.agents.creation_star.service import creation_star_agent_service
from app.agents.llm_io import call_agent_json
from app.agents.prompts import AGENT_PROMPT_BINDINGS, AGENT_SPECS_BY_NAME, DEFAULT_AGENT_SPECS
from app.agents.shared.prompt_catalog import get_prompt_entry, list_prompt_lifecycle_workflows, list_prompt_workflows, load_catalog_prompt
from app.agents.shared.prompt_node_contracts import get_prompt_node_contract
from app.core.config import LLMProviderResolver, get_settings
from app.core.ids import generate_id
from app.core.json import dumps, loads
from app.db import models
from app.db.models import utcnow
from app.db.session import SessionLocal
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


DEFAULT_CHAPTER_WORD_TARGET = 8000

CHAPTER_OUTLINE_STATUS_PROTECTED = {"drafted", "completed", "finalized"}
CHAPTER_DRAFT_PROGRESS_STEPS = (
    "canon_context",
    "chapter_prep",
    "chapter_card",
    "scene_outline",
    "plot_narrator",
    "dialogue_writer",
    "environment_writer",
    "integrator",
    "reviewer",
    "fact_checker",
    "draft_rewrite",
    "quality_gate",
    "style_unifier",
    "post_length_review",
    "narrative_ledger",
    "canon_curator",
)
CHAPTER_DRAFT_STEP_LABELS = {
    "canon_context": "读取正典",
    "build_context": "读取正典",
    "chapter_prep": "写前准备",
    "chapter_card": "章节卡",
    "scene_outline": "场景细纲",
    "plot_narrator": "情节叙事",
    "dialogue_writer": "人物对话",
    "environment_writer": "环境描写",
    "integrator": "整合草稿",
    "reviewer": "审核修改",
    "fact_checker": "事实核查",
    "draft_rewrite": "草稿改写",
    "quality_gate": "质量门",
    "style_unifier": "风格统一",
    "post_length_review": "扩写后复审",
    "narrative_ledger": "章后账本",
    "canon_curator": "正典整理",
}
CREATION_CANON_APPROVAL_SECTIONS = ("project", "story_bible", "characters", "entities", "world_facts", "graph")
RUNNING_JOB_STALE_SECONDS = 30 * 60


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
    def __init__(self) -> None:
        self._job_create_lock = threading.Lock()
        self._creation_session_lock_guard = threading.Lock()
        self._creation_session_locks: dict[str, threading.Lock] = {}
        self._batch_job_queue: queue.Queue[str] = queue.Queue()
        self._batch_worker_lock = threading.Lock()
        self._batch_worker: threading.Thread | None = None

    def _creation_session_write_lock(self, session_id: str) -> threading.Lock:
        with self._creation_session_lock_guard:
            lock = self._creation_session_locks.get(session_id)
            if lock is None:
                lock = threading.Lock()
                self._creation_session_locks[session_id] = lock
            return lock

    def _create_job_committed(
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
        with self._job_create_lock:
            job = self._create_job(
                db,
                project_id,
                chapter_id,
                job_type,
                requested_model,
                request_payload,
                idempotency_key,
                total_steps,
                queued,
            )
            db.commit()
            db.refresh(job)
            return job

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
        self._apply_creation_basic_to_project(project, basic)
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

    def get_creation_profile(self, db: Session, project_id: str) -> dict:
        project = self._project(db, project_id)
        story_bible = db.query(models.StoryBible).filter(models.StoryBible.project_id == project_id).first()
        session = (
            db.query(models.CreationSession)
            .filter(models.CreationSession.project_id == project_id, models.CreationSession.status == "committed")
            .order_by(models.CreationSession.updated_at.desc())
            .first()
        )
        if session is None:
            session = (
                db.query(models.CreationSession)
                .filter(models.CreationSession.project_id == project_id)
                .order_by(models.CreationSession.updated_at.desc())
                .first()
            )
        creation_profile = self._creation_profile_from_session(session) if session else self._empty_creation_profile()
        return {
            "project": serialize_project(project),
            "story_bible": serialize_story_bible(story_bible) if story_bible else None,
            "creation_session": serialize_creation_session(session) if session else None,
            "creation_profile": creation_profile,
            "profile_summary": {
                "has_creation_star": bool(session),
                "session_status": session.status if session else "",
                "session_step": session.current_step if session else "",
                "session_updated_at": session.updated_at.isoformat() if session else None,
                "canon_sections": sorted(creation_profile.get("canon_candidates", {}).keys()) if isinstance(creation_profile.get("canon_candidates"), dict) else [],
                "confirmed": bool(creation_profile.get("confirmed_canon")),
            },
        }

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
            self._configured_creation_star_model(db, self._creation_worldview_agent_name(), request.model or state.get("model")),
            "creation_worldview_card",
            previous_cards=previous_cards,
        )
        cards = payload.get("cards") if isinstance(payload.get("cards"), list) else []
        with self._creation_session_write_lock(session_id):
            db.refresh(session)
            state = self._creation_session_state(session)
            if request.replace_existing:
                self._reset_creation_session_after(state, "worldview")
            existing_cards = state.get("worldview_candidates") if isinstance(state.get("worldview_candidates"), list) else []
            state["worldview_candidates"] = [*existing_cards, *cards]
            if cards and not state.get("selected_worldview"):
                state["selected_worldview"] = cards[0]
            session.current_step = "worldview"
            self._save_creation_session_state(session, state)
            self._finish_job(db, job, {**payload, "session_id": session.id})
            db.commit()
            db.refresh(session)
        return {"session": self._serialize_creation_session_compact(session), "job": serialize_job(job), **payload}

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
            self._configured_creation_star_model(db, self._creation_protagonist_agent_name(), request.model or state.get("model")),
            "creation_protagonist_card",
            previous_cards=previous_cards,
        )
        cards = payload.get("cards") if isinstance(payload.get("cards"), list) else []
        with self._creation_session_write_lock(session_id):
            db.refresh(session)
            state = self._creation_session_state(session)
            if request.replace_existing:
                self._reset_creation_session_after(state, "protagonist")
            existing_cards = state.get("protagonist_candidates") if isinstance(state.get("protagonist_candidates"), list) else []
            state["selected_worldview"] = worldview
            state["protagonist_candidates"] = [*existing_cards, *cards]
            if cards and not state.get("selected_protagonist"):
                state["selected_protagonist"] = cards[0]
            session.current_step = "protagonist"
            self._save_creation_session_state(session, state)
            self._finish_job(db, job, {**payload, "session_id": session.id})
            db.commit()
            db.refresh(session)
        return {"session": self._serialize_creation_session_compact(session), "job": serialize_job(job), **payload}

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
            self._configured_creation_star_model(db, self._creation_title_packaging_agent_name(), request.model or state.get("model")),
            "creation_title_packaging_card",
        )
        title_cards = payload.get("cards") if isinstance(payload.get("cards"), list) else []
        with self._creation_session_write_lock(session_id):
            db.refresh(session)
            state = self._creation_session_state(session)
            if request.replace_existing:
                self._reset_creation_session_after(state, "market_position")
            existing_cards = state.get("title_candidates") if isinstance(state.get("title_candidates"), list) else []
            state["selected_worldview"] = worldview
            state["selected_protagonist"] = protagonist
            state["title_candidates"] = [*existing_cards, *title_cards]
            state["market_position_candidates"] = []
            if title_cards and not state.get("selected_title"):
                state["selected_title"] = title_cards[0]
            selected_title = state.get("selected_title") if isinstance(state.get("selected_title"), dict) else (title_cards[0] if title_cards else {})
            if selected_title and not state.get("market_position"):
                state["market_position"] = self._title_card_to_market_position(selected_title, basic, worldview, protagonist)
            session.current_step = "market_position"
            self._save_creation_session_state(session, state)
            self._finish_job(db, job, {**payload, "title_candidates": title_cards, "market_position_candidates": [], "session_id": session.id})
            db.commit()
            db.refresh(session)
        return {
            "session": self._serialize_creation_session_compact(session),
            "job": serialize_job(job),
            "cards": title_cards,
            "title_candidates": title_cards,
            "market_position_candidates": [],
            "step": payload.get("step") or "title",
            "draw_id": payload.get("draw_id"),
            "prompt_snapshot": payload.get("prompt_snapshot", {}),
            "_llm": payload.get("_llm", {}),
        }

    def creation_session_seed(self, db: Session, project_id: str, session_id: str, request: CreationSessionSeedRequest) -> dict:
        session = self._creation_session(db, project_id, session_id)
        state = self._creation_session_state(session)
        worldview = request.selected_worldview or state.get("selected_worldview") or self._pick(state.get("worldview_candidates", []), 0, {})
        protagonist = request.selected_protagonist or state.get("selected_protagonist") or self._pick(state.get("protagonist_candidates", []), 0, {})
        title = request.selected_title or state.get("selected_title") or self._pick(state.get("title_candidates", []), 0, {})
        market_position = request.market_position or state.get("market_position") or self._title_card_to_market_position(title, loads(session.basic_info_json, {}), worldview, protagonist)
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
        context = self._creation_seed_context(project, seed, request.instruction)
        payload, job, llm_meta = self._run_structured_creation_agent(
            db,
            project,
            "creation_core_conflict",
            "chief_architect",
            "根据创作 Star 已确认的立项种子生成核心矛盾系统。必须输出 protagonist_desire、world_resistance、core_conflict、external_resistance、internal_resistance、relationship_resistance、institutional_resistance、typical_cost、long_form_engine、possible_endpoint、theme_question。",
            context,
            fallback,
            self._configured_model_for_agent(db, "creation_star_session", "chief_architect", request.model or state.get("model")),
            self._catalog_task_system_prompt("chief_architect", "core_conflict_system"),
        )
        if not isinstance(payload, dict):
            payload = fallback
        payload = {**fallback, **payload}
        state["core_conflict_system"] = payload
        session.current_step = "core_conflict"
        self._save_creation_session_state(session, state)
        self._record_agent_run(db, job, "chief_architect", {**payload, "_llm": llm_meta}, {"project_seed": seed})
        self._finish_job(db, job, {"core_conflict_system": payload, "session_id": session.id, "_llm": llm_meta})
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
        context = self._creation_seed_context(project, seed, request.instruction, core_conflict)
        payload, job, llm_meta = self._run_structured_creation_agent(
            db,
            project,
            "creation_novel_constitution",
            "chief_architect",
            "根据核心矛盾系统生成小说宪法。必须输出 basic_positioning、core_narrative_engine、protagonist_arc、world_rules、character_functions、theme_pressure、cost_mechanism、forbidden_directions、long_form_sustainability。",
            context,
            fallback,
            self._configured_model_for_agent(db, "creation_star_session", "chief_architect", request.model or state.get("model")),
            self._catalog_task_system_prompt("chief_architect", "novel_constitution"),
        )
        if not isinstance(payload, dict):
            payload = fallback
        payload = {**fallback, **payload}
        payload["core_narrative_engine"] = payload.get("core_narrative_engine") or core_conflict
        state["novel_constitution"] = payload
        session.current_step = "constitution"
        self._save_creation_session_state(session, state)
        self._record_agent_run(db, job, "chief_architect", {**payload, "_llm": llm_meta}, {"project_seed": seed, "core_conflict_system": core_conflict})
        self._finish_job(db, job, {"novel_constitution": payload, "session_id": session.id, "_llm": llm_meta})
        db.commit()
        db.refresh(session)
        return {"session": serialize_creation_session(session), "job": serialize_job(job), "novel_constitution": payload}

    def creation_session_constitution_review(self, db: Session, project_id: str, session_id: str, request: CreationSessionRunRequest) -> dict:
        project = self._project(db, project_id)
        session = self._creation_session(db, project_id, session_id)
        state = self._creation_session_state(session)
        seed = self._require_project_seed(state)
        self._apply_creation_session_run_edits(state, request)
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
        self._finish_job(db, job, {"constitution_review": payload, "session_id": session.id, "_llm": llm_meta})
        db.commit()
        db.refresh(session)
        return {"session": serialize_creation_session(session), "job": serialize_job(job), "constitution_review": payload}

    def creation_session_canon_preview(self, db: Session, project_id: str, session_id: str, request: CreationSessionRunRequest) -> dict:
        project = self._project(db, project_id)
        session = self._creation_session(db, project_id, session_id)
        state = self._creation_session_state(session)
        seed = self._require_project_seed(state)
        self._apply_creation_session_run_edits(state, request)
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
        self._apply_creation_basic_to_project(project, basic)
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
        creation_graph_edges = self._link_creation_graph(db, project_id, character, entities, facts, worldview)
        db.flush()
        canon_change_reason = request.user_note or "解耦创作 Star 确认入库"
        self._sync_canon_ref(
            db,
            project_id,
            "character",
            character,
            source_job_id=job.id,
            source_agent="canon_curator",
            change_reason=canon_change_reason,
            confidence=0.95,
        )
        for entity in entities:
            self._sync_canon_ref(
                db,
                project_id,
                "entity",
                entity,
                source_job_id=job.id,
                source_agent="canon_curator",
                change_reason=canon_change_reason,
                confidence=0.92,
            )
        for fact in facts:
            self._sync_canon_ref(
                db,
                project_id,
                "world_fact",
                fact,
                source_job_id=job.id,
                source_agent="canon_curator",
                change_reason=canon_change_reason,
                confidence=0.9,
            )
        for edge in {edge.id: edge for edge in creation_graph_edges}.values():
            self._sync_canon_ref(
                db,
                project_id,
                "graph_edge",
                edge,
                source_job_id=job.id,
                source_agent="canon_curator",
                change_reason=canon_change_reason,
                confidence=edge.confidence,
            )
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
        chapter.word_count = self._fast_draft_text_length(chapter.final_text or chapter.draft_text or "")
        db.commit()
        db.refresh(chapter)
        return {"chapter": serialize_chapter(chapter)}

    def draft_chapter(
        self,
        db: Session,
        project_id: str,
        chapter_id: str,
        request: DraftChapterRequest,
        *,
        background_tasks: Any | None = None,
        parent_job_id: str | None = None,
        parent_chapter_no: int | None = None,
        parent_total_steps: int | None = None,
    ) -> dict:
        project = self._project(db, project_id)
        chapter = self._chapter(db, project_id, chapter_id)
        idem = request.idempotency_key or f"draft:{chapter_id}:{request.mode}:{len(request.user_instruction)}"
        existing = (
            db.query(models.GenerationJob)
            .filter(models.GenerationJob.project_id == project_id, models.GenerationJob.idempotency_key == idem)
            .first()
        )
        if existing:
            payload = {"job": serialize_job(existing)}
            if request.async_mode or existing.status == "succeeded":
                payload["chapter"] = serialize_chapter(chapter)
            return payload
        queued = bool(request.async_mode and parent_job_id is None)
        job = self._create_job(
            db,
            project_id,
            chapter_id,
            "draft_chapter",
            request.model,
            request.model_dump(),
            idem,
            total_steps=len(CHAPTER_DRAFT_PROGRESS_STEPS),
            queued=queued,
        )
        if queued:
            db.commit()
            db.refresh(job)
            if background_tasks is not None:
                background_tasks.add_task(self.run_draft_chapter_job, job.id)
            return {"job": serialize_job(job), "chapter": serialize_chapter(chapter)}
        return self._execute_draft_chapter(
            db,
            project,
            chapter,
            request,
            job,
            parent_job_id=parent_job_id,
            parent_chapter_no=parent_chapter_no,
            parent_total_steps=parent_total_steps,
        )

    def run_draft_chapter_job(self, job_id: str) -> None:
        with SessionLocal() as db:
            job = db.get(models.GenerationJob, job_id)
            if job is None or job.status in {"succeeded", "cancelled"}:
                return
            try:
                request = self._draft_request_from_job(job)
                project = self._project(db, job.project_id)
                if not job.chapter_id:
                    raise _bad_request("单章正文任务缺少 chapter_id")
                chapter = self._chapter(db, job.project_id, job.chapter_id)
                self._start_job(db, job)
                self._execute_draft_chapter(db, project, chapter, request, job)
            except Exception as exc:
                job = db.get(models.GenerationJob, job_id)
                if job is not None and job.status not in {"succeeded", "failed", "cancelled"}:
                    self._fail_job(db, job, exc)
                    db.commit()

    def _draft_request_from_job(self, job: models.GenerationJob) -> DraftChapterRequest:
        payload = loads(job.request_json, {})
        allowed = {field: payload[field] for field in DraftChapterRequest.model_fields if field in payload}
        allowed["async_mode"] = False
        return DraftChapterRequest.model_validate(allowed)

    def _execute_draft_chapter(
        self,
        db: Session,
        project: models.Project,
        chapter: models.Chapter,
        request: DraftChapterRequest,
        job: models.GenerationJob,
        *,
        parent_job_id: str | None = None,
        parent_chapter_no: int | None = None,
        parent_total_steps: int | None = None,
    ) -> dict:
        project_id = project.id
        chapter_id = chapter.id
        state = self._state_from_project(db, project, job.id)
        state.requested_model = request.model
        state.agent_model_configs = self._model_configs_for_workflow(db, "chapter_draft")
        state.current_chapter = chapter.chapter_no
        current_chapter_outline = serialize_chapter(chapter)
        if request.mode == "draft":
            for stale_key in ("draft_text", "final_text", "summary", "revision_notes"):
                current_chapter_outline[stale_key] = ""
            current_chapter_outline["word_count"] = 0
        state.current_chapter_outline = current_chapter_outline
        state.canon_context = self.build_canon_context(db, project_id, chapter_id)["canon_context"]
        # Commit the job row before the long model call, otherwise SQLite can hold a write transaction for the whole draft.
        db.commit()
        db.refresh(job)
        last_progress_step = 0
        try:
            result = state
            for partial_state in chapter_writing_service.stream_chapter_draft(state):
                result = partial_state
                if not partial_state.current_agent:
                    continue
                last_progress_step = self._record_chapter_draft_progress(
                    db,
                    job,
                    partial_state,
                    last_progress_step,
                    parent_job_id=parent_job_id,
                    parent_chapter_no=parent_chapter_no,
                    parent_total_steps=parent_total_steps,
                )
        except Exception as exc:
            self._fail_job(db, job, exc)
            db.commit()
            raise
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
            ("post_length_review", {"review_notes": result.review_notes, "health_check_report": result.health_check_report.get("post_length_review", {})}),
            ("narrative_ledger", {"narrative_ledger": result.narrative_ledger}),
            ("canon_curator", result.candidate_canon_updates or result.canon_updates),
        ]:
            payload = self._with_llm_meta(payload, result, agent_name)
            self._record_agent_run(db, job, agent_name, payload, {"chapter": serialize_chapter(chapter)})
            self._snapshot(db, project_id, chapter_id, job.id, agent_name, "chapter", json.dumps(payload, ensure_ascii=False), "")
        post_length_review = result.health_check_report.get("post_length_review") if isinstance(result.health_check_report, dict) else None
        if isinstance(post_length_review, dict) and post_length_review.get("status") == "needs_revision":
            final_words = post_length_review.get("final_words")
            minimum_words = post_length_review.get("minimum_acceptable_words")
            message = f"章节正文未达到最低字数要求：当前 {final_words or 0} 字，最低字数 {minimum_words or 0} 字。"
            self._fail_job(db, job, ValueError(message))
            db.commit()
            raise _bad_request(message)
        chapter.draft_text = result.style_polished_text
        chapter.final_text = result.final_chapter_text
        chapter.summary = result.chapter_summary
        chapter.revision_notes = dumps(result.review_notes)
        chapter.status = "drafted"
        chapter.word_count = self._fast_draft_text_length(result.final_chapter_text)
        self._persist_quality_report(db, project_id, chapter_id, job.id, result.quality_gate, result.final_chapter_text)
        canon_proposals = self._create_canon_update_proposals(db, project_id, chapter_id, result.canon_updates, source_job_id=job.id)
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
                    "canon_proposals": canon_proposals,
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
                "canon_proposals": canon_proposals,
                "updated_characters": result.canon_updates.get("character_updates", []),
                "updated_entities": result.canon_updates.get("entity_updates", []),
                "updated_world_facts": result.canon_updates.get("world_fact_updates", []),
                "updated_graph_edges": result.canon_updates.get("relation_updates", []),
            },
        )
        db.commit()
        return {"job": serialize_job(job), "chapter": serialize_chapter(chapter)}

    def _persist_quality_report(
        self,
        db: Session,
        project_id: str,
        chapter_id: str,
        job_id: str,
        quality_gate: dict[str, Any],
        content: str,
    ) -> models.QualityReport:
        gate = quality_gate if isinstance(quality_gate, dict) else {}
        deterministic = gate.get("deterministic_report") if isinstance(gate.get("deterministic_report"), dict) else gate
        issues = deterministic.get("issues") if isinstance(deterministic.get("issues"), list) else []
        content_hash = hashlib.sha256((content or "").encode("utf-8")).hexdigest()
        blocking_count = int(deterministic.get("blocking_issue_count") or gate.get("blocking_issue_count") or 0)
        warning_count = int(deterministic.get("warning_issue_count") or gate.get("warning_issue_count") or 0)
        report = (
            db.query(models.QualityReport)
            .filter(models.QualityReport.chapter_id == chapter_id, models.QualityReport.content_hash == content_hash)
            .first()
        )
        if report is None:
            report = models.QualityReport(
                id=generate_id("qlt"),
                project_id=project_id,
                chapter_id=chapter_id,
                job_id=job_id,
                content_hash=content_hash,
                status=str(deterministic.get("status") or gate.get("status") or "passed"),
                score=float(deterministic.get("score") or 100),
                summary=str(deterministic.get("summary") or gate.get("message") or ""),
                blocking_issue_count=blocking_count,
                warning_issue_count=warning_count,
            )
            db.add(report)
            db.flush()
        else:
            report.job_id = job_id
            report.status = str(deterministic.get("status") or gate.get("status") or report.status)
            report.score = float(deterministic.get("score") or report.score)
            report.summary = str(deterministic.get("summary") or gate.get("message") or report.summary)
            report.blocking_issue_count = blocking_count
            report.warning_issue_count = warning_count
            db.query(models.QualityIssue).filter(models.QualityIssue.report_id == report.id).delete()
            db.flush()
        for issue in issues:
            if not isinstance(issue, dict):
                continue
            db.add(
                models.QualityIssue(
                    id=generate_id("qli"),
                    report_id=report.id,
                    severity=str(issue.get("severity") or "warning"),
                    category=str(issue.get("category") or "quality"),
                    message=str(issue.get("message") or issue.get("summary") or ""),
                    evidence=str(issue.get("evidence") or ""),
                    suggestion=str(issue.get("suggestion") or ""),
                )
            )
        return report

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
        if self._reconcile_stale_running_job(db, job):
            db.commit()
            db.refresh(job)
        return {"job": serialize_job(job)}

    def list_jobs(self, db: Session, project_id: str | None = None, job_type: str | None = None, limit: int = 20) -> dict:
        query = db.query(models.GenerationJob)
        if project_id:
            query = query.filter(models.GenerationJob.project_id == project_id)
        if job_type:
            query = query.filter(models.GenerationJob.job_type == job_type)
        jobs = query.order_by(models.GenerationJob.created_at.desc()).limit(max(1, min(limit, 100))).all()
        stale_changed = False
        for job in jobs:
            stale_changed = self._reconcile_stale_running_job(db, job) or stale_changed
        if stale_changed:
            db.commit()
            for job in jobs:
                db.refresh(job)
        return {"jobs": [serialize_job(job) for job in jobs]}

    def get_agent_runs(self, db: Session, job_id: str) -> dict:
        runs = db.query(models.AgentRun).filter(models.AgentRun.job_id == job_id).order_by(models.AgentRun.created_at.asc()).all()
        return {"agent_runs": [serialize_agent_run(run) for run in runs]}

    def retry_job(self, db: Session, job_id: str) -> dict:
        job = db.get(models.GenerationJob, job_id)
        if job is None:
            raise _not_found("任务不存在")
        if job.job_type == "batch_generate":
            request = self._batch_request_from_job(job)
            result_payload = self._batch_result_payload(job, request)
            self._reconcile_batch_result_payload(db, job, request, result_payload)
            job.result_json = dumps(result_payload)
            job.status = "queued"
            job.error_message = None
            job.cancel_requested = 0
            job.cancel_reason = ""
            job.finished_at = None
            job.progress_json = dumps(
                self._batch_progress_payload(
                    job,
                    request,
                    result_payload,
                    current_step="queued",
                    message="批量任务已重新入队，将从失败或未完成章节继续",
                )
            )
            db.commit()
            db.refresh(job)
            payload = {"job": serialize_job(job)}
            self._enqueue_batch_job(job.id)
            return payload
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
            job.cancel_requested = 0
            job.cancel_reason = ""
            job.finished_at = None
        elif action == "cancel":
            job.status = "cancelled"
            job.cancel_requested = 1
            job.cancel_reason = request.reason
            job.finished_at = utcnow()
        db.commit()
        db.refresh(job)
        payload = {"job": serialize_job(job)}
        if action == "resume" and job.job_type == "batch_generate":
            self._enqueue_batch_job(job.id)
        return payload

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
        workflow = next((workflow for workflow in self.list_workflows()["workflows"] if workflow["id"] == request.workflow_id), None)
        if workflow is None:
            raise _not_found("工作流不存在")
        configurable_agents = {
            node.get("agent_name")
            for node in workflow.get("nodes", [])
            if node.get("agent_name") and node.get("configurable", True)
        }
        if request.agent_name not in AGENT_SPECS_BY_NAME and request.agent_name not in configurable_agents:
            raise _not_found("Agent 不存在")
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

    def _configured_creation_star_model(self, db: Session, agent_name: str, requested_model: str | None = None) -> str | None:
        model = self._configured_model_for_agent(db, "creation_star_session", agent_name, requested_model)
        if model or requested_model or agent_name == "creation_star":
            return model
        return self._configured_model_for_agent(db, "creation_star_session", "creation_star", None)

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
            "outline_debate_engine": (
                [
                    "/api/projects/{project_id}/outline/debate/sessions",
                    "/api/projects/{project_id}/outline/debate/sessions/{session_id}/book/stream",
                    "/api/projects/{project_id}/outline/debate/sessions/{session_id}/book/confirm",
                    "/api/projects/{project_id}/outline/debate/sessions/{session_id}/volumes/stream",
                    "/api/projects/{project_id}/outline/debate/sessions/{session_id}/volumes/confirm",
                    "/api/projects/{project_id}/outline/debate/sessions/{session_id}/chapters/stream",
                    "/api/projects/{project_id}/outline/debate/sessions/{session_id}/chapters/confirm",
                    "/api/projects/{project_id}/outline/debate/sessions/{session_id}/commit",
                ],
                "已接入大纲议事生产线：总纲阶段级确认，卷纲逐卷讨论确认，章纲逐章讨论确认；单卷/单章确认后同步正式记录与正典版本，最终 commit 只整理已确认候选。",
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
            row = configs.get((workflow_id, agent_name)) if agent_name and node.get("configurable", True) else None
            if row:
                nodes.append({**node, "provider": row.provider, "model": row.model, "model_config_id": row.id})
            else:
                nodes.append({**node, "provider": None, "model": None, "model_config_id": None})
        return {**workflow, "nodes": nodes}

    def list_workflows(self, db: Session | None = None) -> dict:
        from app.services.outline_debate_service import DEBATE_AGENT_SKILL_SPECS

        agent_descriptions = {spec.name: spec.role for spec in DEFAULT_AGENT_SPECS}
        model_configs = self._agent_model_config_map(db) if db is not None else {}

        def agent_node(node_id: str, label: str, agent_name: str, inputs: list[str], outputs: list[str], layer: int) -> dict[str, Any]:
            return {
                "id": node_id,
                "label": label,
                "type": "agent",
                "node_subtype": "formal_agent",
                "agent_name": agent_name,
                "description": agent_descriptions.get(agent_name, label),
                "inputs": inputs,
                "outputs": outputs,
                "editable": True,
                "configurable": True,
                "node_runtime_status": "configurable_agent",
                "runtime_note": "基础 AgentSpec，可编辑提示词并设置模型覆盖；大纲议事使用 outline_debate/* 运行时席位。",
                "layer": layer,
            }

        def prompt_task_node(node_id: str, label: str, prompt_id: str, inputs: list[str], outputs: list[str], layer: int) -> dict[str, Any]:
            entry = get_prompt_entry(prompt_id)
            contract = get_prompt_node_contract(prompt_id)
            return {
                "id": node_id,
                "label": label,
                "type": "prompt",
                "node_subtype": contract.node_subtype,
                "agent_name": entry.prompt_id,
                "default_agent_name": entry.default_agent,
                "description": contract.description,
                "inputs": inputs,
                "outputs": outputs,
                "required_inputs": list(contract.required_inputs),
                "optional_inputs": list(contract.optional_inputs),
                "produces": list(contract.produces),
                "input_schema": contract.input_json_schema(),
                "output_schema": contract.output_json_schema(),
                "editable": True,
                "configurable": True,
                "node_runtime_status": "prompt_task",
                "runtime_note": f"运行名 {entry.prompt_id}，通过默认 AgentSpec 或运行时席位 {agent_descriptions.get(entry.default_agent, entry.default_agent)} 调用提示词 {prompt_id}。",
                "prompt_id": entry.prompt_id,
                "prompt_filename": entry.filename,
                "layer": layer,
            }

        def runtime_agent_node(node_id: str, label: str, agent_name: str, description: str, inputs: list[str], outputs: list[str], layer: int) -> dict[str, Any]:
            skill_spec = DEBATE_AGENT_SKILL_SPECS.get(agent_name, {})
            return {
                "id": node_id,
                "label": label,
                "type": "agent",
                "node_subtype": "runtime_agent",
                "agent_name": agent_name,
                "description": description,
                "inputs": inputs,
                "outputs": outputs,
                "editable": False,
                "configurable": False,
                "node_runtime_status": "active_runtime",
                "runtime_note": "后端运行时内部席位，真实参与工作流，但不走 /api/agents 的提示词编辑入口。",
                "allowed_read_tools": list(skill_spec.get("allowed_read_tools") or []),
                "allowed_candidate_tools": list(skill_spec.get("allowed_candidate_tools") or []),
                "validators": list(skill_spec.get("validators") or []),
                "forbidden_tools": list(skill_spec.get("forbidden_tools") or []),
                "candidate_policy": str(skill_spec.get("candidate_policy") or ""),
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
                "configurable": False,
                "node_runtime_status": "control",
                "runtime_note": "后端工作流控制节点，不是可编辑 Agent。",
                "layer": layer,
            }

        workflows = [
            {
                "id": "creation_star_session",
                "key": "creation_star_session",
                "label": "创作 Star 立项流程",
                "nodes": [
                    control_node(
                        "basic_info",
                        "1 基本信息",
                        "创建创作 Star 会话，保存频道、类型、标签、目标读者、Scale Planner 规模计划、风格和初始想法。",
                        ["channel", "genre", "tags", "target_reader", "volume_count", "chapter_count", "chapter_word_min", "chapter_word_max", "target_words", "initial_idea"],
                        ["creation_session", "basic_info"],
                        0,
                    ),
                    prompt_task_node(
                        "worldview_cards",
                        "2 世界观抽卡",
                        "creation_worldview_draw",
                        ["basic_info", "manual_input", "previous_worldview_cards"],
                        ["worldview_candidates", "prompt_snapshot"],
                        1,
                    ),
                    prompt_task_node(
                        "protagonist_cards",
                        "3 主角人设",
                        "creation_protagonist_draw",
                        ["basic_info", "selected_worldview", "manual_input"],
                        ["protagonist_candidates", "prompt_snapshot"],
                        2,
                    ),
                    prompt_task_node(
                        "market_position",
                        "4 书名与包装",
                        "creation_title_packaging",
                        ["basic_info", "selected_worldview", "selected_protagonist", "manual_input"],
                        ["title_candidates", "market_position", "prompt_snapshot"],
                        3,
                    ),
                    control_node(
                        "project_seed",
                        "5 立项种子",
                        "用户确认已选世界观、主角和书名包装后，固化为 project_seed；后续 Agent 只读取已确认种子。",
                        ["selected_worldview", "selected_protagonist", "selected_title", "market_position"],
                        ["project_seed"],
                        4,
                    ),
                    agent_node(
                        "core_constitution",
                        "6 核心与宪法",
                        "chief_architect",
                        ["project_seed", "selected_worldview", "selected_protagonist", "selected_title", "market_position"],
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
                    {"source": "market_position", "target": "project_seed", "label": "选择书名与包装"},
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
                "id": "outline_debate_engine",
                "key": "outline_debate_engine",
                "label": "大纲议事引擎",
                "nodes": [
                    control_node("debate_session", "议事会话", "创建三阶段大纲议事会话，保存每个阶段的 turns、decisions、artifacts 和 outline_topology。", ["project_id", "brief"], ["outline_debate_session"], 0),
                    runtime_agent_node("debate_book", "讨论总纲", "outline_debate/StoryDirectorAgent", "主持总策划席位：主持总纲阶段，锁定作品承诺、主线冲突、长线伏笔和终局方向。", ["outline_debate_session", "project", "canon_context"], ["book_outline_candidate", "book_decisions"], 1),
                    runtime_agent_node("debate_market_position", "类型卖点审查", "outline_debate/MarketPositionAgent", "类型卖点席位：检查目标读者、爽点承诺、追读理由、期待兑现和平台可读性。", ["outline_debate_session", "project", "canon_context"], ["market_position_decisions", "selling_point_risks"], 1),
                    runtime_agent_node("debate_volumes", "逐卷讨论卷纲", "outline_debate/StructureDoctorAgent", "结构医生席位：逐卷选择节奏模型，检查阶段目标、因果递进和卷末钩子。", ["book_outline_candidate", "target_volume_no", "rhythm_constraints"], ["volume_outline_candidate", "volume_decisions", "volume_canon_version"], 2),
                    runtime_agent_node("debate_chapters", "逐章讨论章纲", "outline_debate/ContinuityAuditorAgent", "连续性审计席位：逐章检查危机、高潮、结果、伏笔和正典风险。", ["volume_outline_candidate", "target_chapter_no"], ["chapter_outline_candidate", "chapter_decisions", "chapter_canon_version"], 3),
                    runtime_agent_node("debate_character_generator", "大纲角色生成", "outline_debate/CharacterGeneratorAgent", "角色生成席位：只在大纲缺口需要时生成角色，并在确认后物化为正式角色正典。", ["phase_gap", "existing_characters"], ["character_candidate"], 4),
                    runtime_agent_node("debate_setting_generator", "大纲设定生成", "outline_debate/SettingGeneratorAgent", "设定生成席位：只在大纲缺口需要时生成地点、组织、规则或物件，并在确认后物化为正式设定。", ["phase_gap", "existing_settings"], ["setting_candidate"], 4),
                    control_node("debate_user_confirm", "逐项确认", "总纲按阶段确认；卷纲与章纲按 item_key 确认，确认后写入对应大纲记录，并把角色/设定候选同步物化为正式正典与版本。", ["phase_artifacts", "item_key"], ["approved_outline_candidates", "canon_versions", "canon_materializations"], 5),
                ],
                "edges": [
                    {"source": "debate_session", "target": "debate_book", "label": "启动讨论总纲"},
                    {"source": "debate_book", "target": "debate_market_position", "label": "校验读者承诺"},
                    {"source": "debate_market_position", "target": "debate_volumes", "label": "可读取总纲候选和卖点风险"},
                    {"source": "debate_volumes", "target": "debate_chapters", "label": "可读取卷纲候选"},
                    {"source": "debate_book", "target": "debate_character_generator", "label": "发现角色缺口"},
                    {"source": "debate_book", "target": "debate_setting_generator", "label": "发现设定缺口"},
                    {"source": "debate_volumes", "target": "debate_character_generator", "label": "发现分卷角色缺口"},
                    {"source": "debate_chapters", "target": "debate_setting_generator", "label": "发现章纲设定缺口"},
                    {"source": "debate_character_generator", "target": "debate_user_confirm", "label": "确认后角色入库"},
                    {"source": "debate_setting_generator", "target": "debate_user_confirm", "label": "确认后设定入库"},
                    {"source": "debate_chapters", "target": "debate_user_confirm", "label": "单章候选待确认"},
                ],
            },
            {
                "id": "chapter_draft",
                "key": "chapter_draft",
                "label": "单章正文生成",
                "nodes": [
                    control_node("canon_context", "canon_context", "聚合项目、故事圣经、角色、实体、图谱和前文摘要。", ["project_id", "chapter_id"], ["canon_context"], 0),
                    prompt_task_node("chapter_prep", "章节写前准备", "chapter_prep", ["chapter_outline", "canon_context", "narrative_ledger", "reference_assets"], ["chapter_prep"], 1),
                    agent_node("plot_narrator", "情节叙事 Agent", "plot_narrator", ["canon_context", "chapter_outline", "chapter_prep"], ["plot_draft"], 2),
                    agent_node("dialogue_writer", "人物对话 Agent", "dialogue_writer", ["plot_draft", "characters"], ["dialogue_draft"], 3),
                    agent_node("environment_writer", "环境描写 Agent", "environment_writer", ["plot_draft", "story_entities"], ["environment_draft"], 3),
                    agent_node("integrator", "整合输出 Agent", "integrator", ["plot_draft", "dialogue_draft", "environment_draft"], ["integrated_draft", "chapter_summary"], 4),
                    agent_node("reviewer", "审核修改 Agent", "reviewer", ["integrated_draft"], ["review_notes"], 5),
                    agent_node("fact_checker", "事实核查 Agent", "fact_checker", ["integrated_draft", "world_facts"], ["fact_check_report"], 5),
                    control_node("quality_gate", "quality_gate", "检查 blocking/error 问题，决定是否进入修订回路。", ["review_notes", "fact_check_report"], ["quality_gate"], 6),
                    control_node("revise_draft", "revise_draft", "按质量门意见进行一次受控修订。", ["integrated_draft", "review_notes"], ["integrated_draft"], 7),
                    agent_node("style_unifier", "风格统一 Agent", "style_unifier", ["integrated_draft", "style_guide"], ["final_chapter_text"], 8),
                    agent_node("canon_curator", "设定整理 Agent", "canon_curator", ["final_chapter_text", "chapter_summary"], ["canon_updates", "candidate_canon_updates"], 9),
                ],
                "edges": [
                    {"source": "canon_context", "target": "chapter_prep", "label": "固化写前准备"},
                    {"source": "chapter_prep", "target": "plot_narrator", "label": "提供章节位置和预算"},
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
            self._folder_node("folder:volumes", "root", "分卷纲要", 5),
            self._folder_node("folder:chapters", "root", "章节纲要", 8),
            self._folder_node("folder:characters", "root", "人物", 10),
            self._folder_node("folder:entities", "root", "剧情实体", 20),
            self._folder_node("folder:world_facts", "root", "世界观事实", 30),
            self._folder_node("folder:foreshadowing", "root", "伏笔", 40),
            self._folder_node("folder:graph_edges", "root", "关系图谱", 50),
        ]
        group_nodes: dict[str, dict[str, Any]] = {}

        def add_group(node_id: str, parent_id: str, title: str, sort_order: int) -> str:
            if node_id not in group_nodes:
                group_nodes[node_id] = self._folder_node(node_id, parent_id, title, sort_order)
            return node_id

        for row in db.query(models.Volume).filter(models.Volume.project_id == project_id).order_by(models.Volume.sort_order.asc(), models.Volume.volume_no.asc()).all():
            content = serialize_volume(row)
            node = self._ensure_canon_node(
                db,
                project_id,
                "volume",
                row.id,
                row.title,
                "major",
                row.status,
                {"group": "folder:volumes", "volume_no": row.volume_no},
                parent_id="folder:volumes",
            )
            payload = serialize_canon_node(node, content)
            metadata = payload.get("metadata", {})
            payload["parent_id"] = metadata.get("custom_folder_id") or metadata.get("display_parent_id") or "folder:volumes"
            nodes.append(payload)

        for row in db.query(models.Chapter).filter(models.Chapter.project_id == project_id, models.Chapter.deleted_at.is_(None)).order_by(models.Chapter.sort_order.asc(), models.Chapter.chapter_no.asc()).all():
            content = serialize_chapter(row)
            group_id = add_group(
                f"folder:chapters:volume:{row.volume_no}",
                "folder:chapters",
                f"第{row.volume_no}卷",
                80 + row.volume_no,
            )
            node = self._ensure_canon_node(
                db,
                project_id,
                "chapter",
                row.id,
                row.title,
                "medium",
                row.status,
                {"group": group_id, "volume_no": row.volume_no, "chapter_no": row.chapter_no},
                parent_id=group_id,
            )
            payload = serialize_canon_node(node, content)
            metadata = payload.get("metadata", {})
            payload["parent_id"] = metadata.get("custom_folder_id") or metadata.get("display_parent_id") or group_id
            nodes.append(payload)

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

        for row in db.query(models.GraphEdge).filter(models.GraphEdge.project_id == project_id).order_by(models.GraphEdge.updated_at.desc()).all():
            content = self._canon_ref_content("graph_edge", row)
            node = self._ensure_canon_node(
                db,
                project_id,
                "graph_edge",
                row.id,
                self._canon_ref_title("graph_edge", content),
                "medium",
                "active",
                {"group": "folder:graph_edges", "source_chapter_id": row.source_chapter_id},
                parent_id="folder:graph_edges",
            )
            payload = serialize_canon_node(node, content)
            metadata = payload.get("metadata", {})
            payload["parent_id"] = metadata.get("custom_folder_id") or metadata.get("display_parent_id") or "folder:graph_edges"
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
        return {"nodes": [*nodes[:8], *group_nodes.values(), *custom_folders, *nodes[8:]], "health": self._canon_health(db, project_id)}

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
        chapter_lookup = self._chapter_summary_lookup(db, project_id)
        versions = (
            db.query(models.CanonVersion)
            .filter(models.CanonVersion.project_id == project_id, models.CanonVersion.ref_type == ref_type, models.CanonVersion.ref_id == ref_id)
            .order_by(models.CanonVersion.version_no.asc())
            .all()
        )
        return {"versions": [self._enrich_source_chapter(serialize_canon_version(row), chapter_lookup) for row in versions]}

    def get_canon_version_timeline(
        self,
        db: Session,
        project_id: str,
        *,
        ref_type: str | None = None,
        ref_id: str | None = None,
        chapter_id: str | None = None,
    ) -> dict:
        self._project(db, project_id)
        normalized_ref_type = self._normalize_canon_ref_type(ref_type) if ref_type else None
        chapter_lookup = self._chapter_summary_lookup(db, project_id)
        chapter_rows = (
            db.query(models.Chapter)
            .filter(models.Chapter.project_id == project_id, models.Chapter.deleted_at.is_(None))
            .order_by(models.Chapter.sort_order.asc(), models.Chapter.chapter_no.asc())
            .all()
        )
        timeline_by_chapter: dict[str, dict[str, Any]] = {
            chapter.id: {
                "chapter": self._chapter_summary(chapter),
                "versions": [],
                "proposals": [],
                "snapshots": [],
                "events": [],
            }
            for chapter in chapter_rows
        }
        unbound = {"versions": [], "proposals": [], "snapshots": [], "events": []}
        events: list[dict[str, Any]] = []

        version_query = db.query(models.CanonVersion).filter(models.CanonVersion.project_id == project_id)
        if normalized_ref_type:
            version_query = version_query.filter(models.CanonVersion.ref_type == normalized_ref_type)
        if ref_id:
            version_query = version_query.filter(models.CanonVersion.ref_id == ref_id)
        if chapter_id:
            version_query = version_query.filter(models.CanonVersion.source_chapter_id == chapter_id)
        versions = version_query.order_by(models.CanonVersion.created_at.asc(), models.CanonVersion.version_no.asc()).all()
        for row in versions:
            payload = self._enrich_source_chapter(serialize_canon_version(row), chapter_lookup)
            event = {
                **payload,
                "event_type": "version",
                "chapter": payload.get("source_chapter"),
                "title": self._canon_ref_title(row.ref_type, payload.get("content", {})),
            }
            self._append_timeline_event(timeline_by_chapter, unbound, row.source_chapter_id, "versions", payload, event)
            events.append(event)

        proposal_query = db.query(models.CanonChangeProposal).filter(models.CanonChangeProposal.project_id == project_id)
        if normalized_ref_type:
            proposal_query = proposal_query.filter(models.CanonChangeProposal.target_type == normalized_ref_type)
        if ref_id:
            proposal_query = proposal_query.filter(models.CanonChangeProposal.target_id == ref_id)
        if chapter_id:
            proposal_query = proposal_query.filter(models.CanonChangeProposal.source_chapter_id == chapter_id)
        proposals = proposal_query.order_by(models.CanonChangeProposal.created_at.asc()).all()
        for row in proposals:
            payload = self._enrich_source_chapter(serialize_canon_proposal(row), chapter_lookup)
            event = {
                **payload,
                "event_type": "proposal",
                "ref_type": payload["target_type"],
                "ref_id": payload.get("target_id"),
                "chapter": payload.get("source_chapter"),
                "title": self._canon_ref_title(payload["target_type"], payload.get("after", {})),
            }
            self._append_timeline_event(timeline_by_chapter, unbound, row.source_chapter_id, "proposals", payload, event)
            events.append(event)

        snapshot_query = db.query(models.VersionSnapshot).filter(models.VersionSnapshot.project_id == project_id)
        if chapter_id:
            snapshot_query = snapshot_query.filter(models.VersionSnapshot.chapter_id == chapter_id)
        if normalized_ref_type or ref_id:
            snapshot_rows = []
        else:
            snapshot_rows = snapshot_query.order_by(models.VersionSnapshot.created_at.asc()).all()
        for row in snapshot_rows:
            payload = serialize_version_snapshot(row)
            payload = self._enrich_source_chapter({**payload, "source_chapter_id": row.chapter_id}, chapter_lookup)
            event = {
                **payload,
                "event_type": "snapshot",
                "ref_type": "chapter",
                "ref_id": row.chapter_id,
                "chapter": payload.get("source_chapter"),
                "title": f"{row.agent_name} · {row.content_type}",
            }
            self._append_timeline_event(timeline_by_chapter, unbound, row.chapter_id, "snapshots", payload, event)
            events.append(event)

        events.sort(key=lambda item: item.get("created_at") or "")
        chapters = list(timeline_by_chapter.values())
        return {
            "chapters": chapters,
            "events": events,
            "unbound": unbound,
            "summary": {
                "chapter_count": len(chapters),
                "event_count": len(events),
                "version_count": len(versions),
                "proposal_count": len(proposals),
                "snapshot_count": len(snapshot_rows),
            },
            "filters": {"ref_type": normalized_ref_type, "ref_id": ref_id, "chapter_id": chapter_id},
        }

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
        chapter_lookup = self._chapter_summary_lookup(db, project_id)
        query = db.query(models.CanonChangeProposal).filter(models.CanonChangeProposal.project_id == project_id)
        if status:
            query = query.filter(models.CanonChangeProposal.approval_status == status)
        rows = query.order_by(models.CanonChangeProposal.created_at.desc()).all()
        return {"proposals": [self._enrich_source_chapter(serialize_canon_proposal(row), chapter_lookup) for row in rows]}

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
        elif target_type == "foreshadowing":
            result = self.create_foreshadowing(
                db,
                project_id,
                CreateForeshadowingRequest(
                    chapter_id=payload.get("chapter_id") or proposal.source_chapter_id,
                    content=str(payload.get("content") or "未命名伏笔"),
                    planted_chapter_id=payload.get("planted_chapter_id") or proposal.source_chapter_id,
                    planned_payoff_chapter_id=payload.get("planned_payoff_chapter_id"),
                    actual_payoff_chapter_id=payload.get("actual_payoff_chapter_id"),
                    planned_payoff=str(payload.get("planned_payoff") or ""),
                    payoff_status=payload.get("payoff_status") or "planned",
                    importance_level=payload.get("importance_level") or "medium",
                    importance_score=int(payload.get("importance_score") or 50),
                    related_character_ids=list(payload.get("related_character_ids") or []),
                    related_entity_ids=list(payload.get("related_entity_ids") or []),
                    source="agent",
                ),
            )
            applied = {"ref_type": "foreshadowing", "ref_id": result["foreshadowing_item"]["id"], "item": result["foreshadowing_item"]}
        elif target_type == "graph_edge":
            edge = self._create_graph_edge_from_payload(db, project_id, payload, source_chapter_id=proposal.source_chapter_id)
            db.flush()
            content = self._canon_ref_content("graph_edge", edge)
            version = self._record_canon_version(
                db,
                project_id,
                "graph_edge",
                edge.id,
                content,
                source_chapter_id=proposal.source_chapter_id,
                source_job_id=proposal.source_job_id,
                source_agent=proposal.source_agent,
                change_reason=request.user_note if request and request.user_note else proposal.reason,
                confidence=proposal.confidence,
            )
            self._ensure_canon_node(
                db,
                project_id,
                "graph_edge",
                edge.id,
                self._canon_ref_title("graph_edge", content),
                "medium",
                "active",
                {"last_proposal_id": proposal.id},
            )
            applied = {"ref_type": "graph_edge", "ref_id": edge.id, "item": content, "version": serialize_canon_version(version)}
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
        previous_query = db.query(models.Chapter).filter(models.Chapter.project_id == project_id, models.Chapter.summary != "")
        if chapter is not None:
            previous_query = previous_query.filter(models.Chapter.chapter_no < chapter.chapter_no)
        context = {
            "project": serialize_project(project),
            "story_bible": serialize_story_bible(story_bible) if story_bible else None,
            "chapter": serialize_chapter(chapter) if chapter else None,
            "characters": [serialize_character(item) for item in characters],
            "world_facts": [serialize_world_fact(item) for item in facts],
            "story_entities": [serialize_story_entity(item) for item in entities],
            "graph": self.get_graph(db, project_id, chapter_id).get("graph", {}),
            "unresolved_continuity_issues": [serialize_continuity_issue(item) for item in issues],
            "previous_summaries": [serialize_chapter(item) for item in previous_query.order_by(models.Chapter.chapter_no.desc()).limit(5).all()],
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
        if not request.chapter_id:
            chapters = db.query(models.Chapter).filter(models.Chapter.project_id == request.project_id).order_by(models.Chapter.chapter_no.asc()).all()
            if not chapters:
                raise _bad_request("项目还没有章节，请先在大纲议事中确认章纲，或手动创建章节")
            request.chapter_id = chapters[0].id
        return self.draft_chapter(db, request.project_id, request.chapter_id, DraftChapterRequest(user_instruction=request.instruction, model=request.model))

    def batch_generate(self, db: Session, request: BatchGenerateRequest) -> dict:
        if request.chapter_end < request.chapter_start:
            raise _bad_request("结束章节不能小于起始章节")
        self._project(db, request.project_id)
        chapter_numbers = list(range(request.chapter_start, request.chapter_end + 1))
        self._ensure_batch_text_chapters_exist(db, request.project_id, chapter_numbers)
        job = self._create_job(
            db,
            request.project_id,
            None,
            "batch_generate",
            request.model,
            request.model_dump(),
            total_steps=len(chapter_numbers),
            queued=True,
        )
        job.result_json = dumps(self._initial_batch_result_payload(request))
        db.commit()
        db.refresh(job)
        payload = {"job": serialize_job(job), "chapters": []}
        self._enqueue_batch_job(job.id)
        return payload

    def _ensure_batch_text_chapters_exist(self, db: Session, project_id: str, chapter_numbers: list[int]) -> None:
        existing_numbers = {
            row.chapter_no
            for row in db.query(models.Chapter.chapter_no)
            .filter(
                models.Chapter.project_id == project_id,
                models.Chapter.chapter_no.in_(chapter_numbers),
                models.Chapter.deleted_at.is_(None),
            )
            .all()
        }
        missing = [chapter_no for chapter_no in chapter_numbers if chapter_no not in existing_numbers]
        if missing:
            preview = "、".join(str(item) for item in missing[:20])
            suffix = "……" if len(missing) > 20 else ""
            raise _bad_request(
                f"请先确认章纲/创建章节，再批量生成正文；缺少章节：{preview}{suffix}",
                {"missing_chapter_numbers": missing},
            )

    def _initial_batch_result_payload(self, request: BatchGenerateRequest) -> dict[str, Any]:
        return {
            "mode": "async_batch_generate",
            "requested_range": {
                "project_id": request.project_id,
                "chapter_start": request.chapter_start,
                "chapter_end": request.chapter_end,
            },
            "chapter_results": [],
            "failed_chapters": [],
            "skipped_chapters": [],
            "last_completed_chapter_no": None,
        }

    def _batch_result_payload(self, job: models.GenerationJob, request: BatchGenerateRequest) -> dict[str, Any]:
        result = loads(job.result_json, {}) if job.result_json else {}
        if not isinstance(result, dict):
            result = {}
        base = self._initial_batch_result_payload(request)
        base.update(result)
        for key in ("chapter_results", "failed_chapters", "skipped_chapters"):
            if not isinstance(base.get(key), list):
                base[key] = []
        return base

    def _batch_request_from_job(self, job: models.GenerationJob) -> BatchGenerateRequest:
        payload = loads(job.request_json, {})
        allowed = {field: payload[field] for field in BatchGenerateRequest.model_fields if field in payload}
        return BatchGenerateRequest.model_validate(allowed)

    def _chapter_step_label(self, agent_name: str | None) -> str:
        if not agent_name:
            return "章节生成"
        return CHAPTER_DRAFT_STEP_LABELS.get(agent_name, agent_name)

    def _failed_batch_chapter_numbers(self, result_payload: dict[str, Any]) -> list[int]:
        numbers: list[int] = []
        for item in result_payload.get("failed_chapters", []):
            if not isinstance(item, dict):
                continue
            try:
                numbers.append(int(item.get("chapter_no")))
            except (TypeError, ValueError):
                continue
        return sorted(set(numbers))

    def _batch_progress_payload(
        self,
        job: models.GenerationJob,
        request: BatchGenerateRequest,
        result_payload: dict[str, Any],
        *,
        current_step: str,
        message: str,
        current_chapter_no: int | None = None,
        child_job_id: str | None = None,
        child_current_step: str | None = None,
        child_current_step_status: str | None = None,
        child_total_steps: int | None = None,
        child_completed_steps: int | None = None,
    ) -> dict[str, Any]:
        total_chapters = max(1, request.chapter_end - request.chapter_start + 1)
        completed_chapters = len(self._completed_batch_chapter_numbers(result_payload))
        failed_chapters = self._failed_batch_chapter_numbers(result_payload)
        child_fraction = 0.0
        if child_total_steps and child_total_steps > 0 and child_completed_steps is not None:
            child_fraction = min(1.0, max(0.0, child_completed_steps / child_total_steps))
        overall_percent = 100 if completed_chapters >= total_chapters else round(((completed_chapters + child_fraction) / total_chapters) * 100)
        started_at = job.started_at or job.created_at
        elapsed_seconds: int | None = None
        average_chapter_seconds: int | None = None
        eta_seconds: int | None = None
        if started_at:
            now = utcnow()
            if started_at.tzinfo is None and now.tzinfo is not None:
                now = now.replace(tzinfo=None)
            elif started_at.tzinfo is not None and now.tzinfo is None:
                started_at = started_at.replace(tzinfo=None)
            elapsed_seconds = max(0, int((now - started_at).total_seconds()))
            if completed_chapters > 0 and elapsed_seconds > 0:
                average_chapter_seconds = max(1, int(elapsed_seconds / completed_chapters))
                remaining = max(0.0, total_chapters - completed_chapters - child_fraction)
                eta_seconds = int(average_chapter_seconds * remaining)
        long_task = total_chapters >= 10
        long_task_advice: list[str] = []
        if long_task:
            long_task_advice.append("建议按分卷或 20-50 章分批观察质量，再继续更长范围。")
            long_task_advice.append("保持浏览器打开可看实时进度；关闭后可用任务 ID 恢复。")
        if failed_chapters:
            long_task_advice.append("失败章节会保留在结果里，点击重试会从未完成章节继续。")
        payload: dict[str, Any] = {
            "current_step": current_step,
            "total_steps": total_chapters,
            "completed_steps": completed_chapters,
            "current_chapter_no": current_chapter_no,
            "message": message,
            "total_chapters": total_chapters,
            "completed_chapters": completed_chapters,
            "overall_percent": min(100, max(0, overall_percent)),
            "elapsed_seconds": elapsed_seconds,
            "average_chapter_seconds": average_chapter_seconds,
            "eta_seconds": eta_seconds,
            "retryable_failed_chapters": failed_chapters,
            "long_task": long_task,
            "long_task_advice": long_task_advice,
        }
        if child_current_step:
            payload.update(
                {
                    "child_job_id": child_job_id,
                    "child_current_step": child_current_step,
                    "child_current_step_status": child_current_step_status,
                    "child_step_label": self._chapter_step_label(child_current_step),
                    "child_total_steps": child_total_steps,
                    "child_completed_steps": child_completed_steps,
                }
            )
        return payload

    def _seconds_since_job_heartbeat(self, job: models.GenerationJob) -> int | None:
        heartbeat = job.heartbeat_at or job.started_at or job.created_at
        if heartbeat is None:
            return None
        now = utcnow()
        if heartbeat.tzinfo is None and now.tzinfo is not None:
            now = now.replace(tzinfo=None)
        elif heartbeat.tzinfo is not None and now.tzinfo is None:
            heartbeat = heartbeat.replace(tzinfo=None)
        return max(0, int((now - heartbeat).total_seconds()))

    def _is_stale_running_job(self, job: models.GenerationJob) -> bool:
        if job.status != "running":
            return False
        elapsed = self._seconds_since_job_heartbeat(job)
        return elapsed is not None and elapsed >= RUNNING_JOB_STALE_SECONDS

    def _batch_current_chapter_no_from_progress(self, progress: dict[str, Any]) -> int | None:
        raw_chapter_no = progress.get("current_chapter_no")
        try:
            if raw_chapter_no is not None:
                return int(raw_chapter_no)
        except (TypeError, ValueError):
            pass
        current_step = str(progress.get("current_step") or "")
        match = re.search(r"chapter_(\d+)", current_step)
        if match:
            return int(match.group(1))
        return None

    def _mark_stale_child_job_failed(self, job: models.GenerationJob, message: str) -> None:
        progress = loads(job.progress_json, {})
        job.status = "failed"
        job.error_message = message
        job.finished_at = utcnow()
        job.heartbeat_at = utcnow()
        job.progress_json = dumps(
            {
                "current_step": "failed",
                "total_steps": progress.get("total_steps", 1),
                "completed_steps": progress.get("completed_steps", 0),
                "current_chapter_no": progress.get("current_chapter_no"),
                "message": message,
                "retryable": True,
                "stale": True,
            }
        )

    def _mark_stale_batch_job_failed(self, db: Session, job: models.GenerationJob, message: str) -> bool:
        progress = loads(job.progress_json, {})
        if not isinstance(progress, dict):
            progress = {}
        child_job_id = str(progress.get("child_job_id") or "")
        if child_job_id:
            child_job = db.get(models.GenerationJob, child_job_id)
            if child_job is not None and child_job.status == "running":
                if not self._is_stale_running_job(child_job):
                    return False
                self._mark_stale_child_job_failed(child_job, message)
        request = self._batch_request_from_job(job)
        result_payload = self._batch_result_payload(job, request)
        current_chapter_no = self._batch_current_chapter_no_from_progress(progress)
        if current_chapter_no is not None:
            result_payload["failed_chapters"] = [
                item
                for item in result_payload.get("failed_chapters", [])
                if not isinstance(item, dict) or int(item.get("chapter_no", -1)) != current_chapter_no
            ]
            result_payload["failed_chapters"].append(
                {
                    "chapter_no": current_chapter_no,
                    "message": message,
                    "failed_at": isoformat(utcnow()),
                    "retryable": True,
                    "source": "stale_job_reconciliation",
                }
            )
        job.status = "failed"
        job.error_message = message
        job.finished_at = utcnow()
        job.heartbeat_at = utcnow()
        job.result_json = dumps(result_payload)
        job.progress_json = dumps(
            self._batch_progress_payload(
                job,
                request,
                result_payload,
                current_step="failed",
                current_chapter_no=current_chapter_no,
                message="后台任务中断，已保留完成章节；点击重试会从未完成章节继续。",
            )
        )
        return True

    def _reconcile_stale_running_job(self, db: Session, job: models.GenerationJob) -> bool:
        if not self._is_stale_running_job(job):
            return False
        message = "后台任务中断或服务重启，任务已标记为失败；点击重试可从未完成章节继续。"
        if job.job_type == "batch_generate":
            return self._mark_stale_batch_job_failed(db, job, message)
        if job.job_type == "draft_chapter":
            self._mark_stale_child_job_failed(job, message)
            return True
        return False

    def _enqueue_batch_job(self, job_id: str) -> None:
        self._ensure_batch_worker()
        self._batch_job_queue.put(job_id)

    def _ensure_batch_worker(self) -> None:
        with self._batch_worker_lock:
            if self._batch_worker is not None and self._batch_worker.is_alive():
                return
            self._batch_worker = threading.Thread(target=self._batch_worker_loop, name="batch-generate-worker", daemon=True)
            self._batch_worker.start()

    def _batch_worker_loop(self) -> None:
        while True:
            job_id = self._batch_job_queue.get()
            try:
                self._run_batch_generate_job(job_id)
            except Exception as exc:
                try:
                    with SessionLocal() as db:
                        job = db.get(models.GenerationJob, job_id)
                        if job is not None and job.status not in {"succeeded", "cancelled"}:
                            self._fail_job(db, job, exc)
                            db.commit()
                except Exception:
                    pass
            finally:
                self._batch_job_queue.task_done()

    def _batch_fast_draft_enabled(self, request: BatchGenerateRequest) -> bool:
        options = request.generation_options if isinstance(request.generation_options, dict) else {}
        return bool(options.get("fast_draft") or options.get("draft_mode") == "fast_draft")

    def _batch_local_fast_draft_enabled(self, request: BatchGenerateRequest) -> bool:
        options = request.generation_options if isinstance(request.generation_options, dict) else {}
        return bool(options.get("local_fast_draft") or options.get("instant_local_draft") or options.get("draft_mode") in {"local_fast_draft", "instant_local_draft"})

    def _clean_fast_draft_text(self, text: str, chapter_no: int) -> str:
        cleaned = str(text or "").strip()
        cleaned = re.sub(r"^```(?:markdown|text)?", "", cleaned).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
        lines = [line.rstrip() for line in cleaned.splitlines()]
        while lines and not lines[0].strip():
            lines.pop(0)
        if lines and (lines[0].lstrip().startswith("#") or re.match(rf"^\s*第\s*{chapter_no}\s*章", lines[0])):
            lines.pop(0)
        return "\n".join(lines).strip()

    def _fast_draft_text_length(self, text: str) -> int:
        return len(re.sub(r"\s+", "", str(text or "")))

    def _fast_draft_length_band(self, chapter_target: int) -> tuple[int, int]:
        target = int(chapter_target or DEFAULT_CHAPTER_WORD_TARGET)
        target = max(1, target)
        upper_buffer = max(50, int(target * 0.05))
        return target, target + upper_buffer

    def _close_fast_draft_terminal_quote(self, text: str) -> str:
        stripped = str(text or "").rstrip()
        if not stripped or stripped[-1] not in set("。！？!?…；;"):
            return stripped
        candidate_close_mark: str | None = None
        candidate_index = -1
        for open_mark, close_mark in (("“", "”"), ("‘", "’"), ("「", "」"), ("『", "』")):
            open_index = stripped.rfind(open_mark)
            if open_index > stripped.rfind(close_mark) and open_index > candidate_index:
                candidate_index = open_index
                candidate_close_mark = close_mark
        ascii_quote_index = stripped.rfind('"')
        if stripped.count('"') % 2 == 1 and ascii_quote_index > candidate_index:
            candidate_close_mark = '"'
        if candidate_close_mark:
            return stripped + candidate_close_mark
        return stripped

    def _trim_fast_draft_text_to_band(self, text: str, minimum_words: int, maximum_words: int) -> str:
        cleaned = str(text or "").strip()
        if self._fast_draft_text_length(cleaned) <= maximum_words:
            return self._close_fast_draft_terminal_quote(cleaned)
        minimum_words = max(1, int(minimum_words))
        maximum_words = max(minimum_words, int(maximum_words))
        sentence_breaks = set("。！？!?…；;」』”’）)】》")
        sentence_lookahead = max(100, int(minimum_words * 0.03))
        hard_maximum_words = maximum_words + sentence_lookahead
        visible_count = 0
        hard_cut_index = len(cleaned)
        best_sentence_index: int | None = None
        next_sentence_index: int | None = None
        for index, char in enumerate(cleaned):
            if char not in {"\r", "\n"}:
                visible_count += 1
            if minimum_words <= visible_count <= maximum_words and char in sentence_breaks:
                best_sentence_index = index + 1
            elif maximum_words < visible_count <= hard_maximum_words and char in sentence_breaks:
                next_sentence_index = index + 1
                break
            if visible_count >= maximum_words:
                hard_cut_index = index + 1
            if visible_count >= hard_maximum_words:
                break
        cut_index = best_sentence_index or next_sentence_index or hard_cut_index
        closing_marks = set("”’」』）)】》")
        while cut_index < len(cleaned) and cleaned[cut_index] in closing_marks:
            cut_index += 1
        return self._close_fast_draft_terminal_quote(cleaned[:cut_index])

    def _fast_draft_parent_progress(
        self,
        db: Session,
        parent_job_id: str | None,
        parent_chapter_no: int | None,
        parent_total_steps: int | None,
        child_job: models.GenerationJob,
        message: str,
    ) -> None:
        if not parent_job_id or not parent_chapter_no or not parent_total_steps:
            return
        parent_job = db.get(models.GenerationJob, parent_job_id)
        if parent_job is None or parent_job.status in {"succeeded", "failed", "cancelled"}:
            return
        request = self._batch_request_from_job(parent_job)
        result_payload = self._batch_result_payload(parent_job, request)
        parent_job.status = "running"
        parent_job.current_agent = f"batch_generate:chapter_{parent_chapter_no}:fast_draft"
        parent_job.heartbeat_at = utcnow()
        progress = self._batch_progress_payload(
            parent_job,
            request,
            result_payload,
            current_step=f"chapter_{parent_chapter_no}:fast_draft",
            current_chapter_no=parent_chapter_no,
            message=message,
        )
        child_progress = loads(child_job.progress_json, {})
        progress.update(
            {
                "child_job_id": child_job.id,
                "child_current_step": "fast_draft",
                "child_current_step_status": child_job.status,
                "child_step_label": "快速正文",
                "child_total_steps": 1,
                "child_completed_steps": child_progress.get("completed_steps", 0),
            }
        )
        parent_job.progress_json = dumps(progress)

    def _generate_fast_batch_chapter(
        self,
        db: Session,
        project_id: str,
        chapter_id: str,
        request: BatchGenerateRequest,
        chapter_max_words: int,
        attempt: int,
        *,
        parent_job_id: str | None,
        parent_chapter_no: int | None,
        parent_total_steps: int | None,
    ) -> dict[str, Any]:
        project = self._project(db, project_id)
        chapter = self._chapter(db, project_id, chapter_id)
        idem = f"batch-fast:{parent_job_id}:{chapter_id}:attempt:{attempt}"
        existing = (
            db.query(models.GenerationJob)
            .filter(models.GenerationJob.project_id == project_id, models.GenerationJob.idempotency_key == idem)
            .first()
        )
        if existing:
            return {"job": serialize_job(existing), "chapter": serialize_chapter(chapter)}

        child_job = self._create_job(
            db,
            project_id,
            chapter_id,
            "draft_chapter_fast",
            request.model,
            {
                "mode": "fast_draft",
                "chapter_no": chapter.chapter_no,
                "max_words": chapter_max_words,
                "generation_options": request.generation_options,
            },
            idem,
            total_steps=1,
            queued=False,
        )
        self._start_job(db, child_job)
        self._fast_draft_parent_progress(db, parent_job_id, parent_chapter_no, parent_total_steps, child_job, f"第{chapter.chapter_no}章：快速正文正在执行")
        canon_context = self.build_canon_context(db, project_id, chapter_id)["canon_context"]
        previous_chapters = (
            db.query(models.Chapter)
            .filter(models.Chapter.project_id == project_id, models.Chapter.chapter_no < chapter.chapter_no, models.Chapter.deleted_at.is_(None))
            .order_by(models.Chapter.chapter_no.desc())
            .limit(3)
            .all()
        )
        previous_summaries = [
            {"chapter_no": item.chapter_no, "title": item.title, "summary": item.summary, "tail": (item.final_text or item.draft_text or "")[-500:]}
            for item in reversed(previous_chapters)
        ]
        db.commit()
        db.refresh(child_job)

        target_min_words, target_max_words = self._fast_draft_length_band(chapter_max_words)
        if self._batch_local_fast_draft_enabled(request):
            text = self._local_fast_draft_text(project, chapter, previous_summaries, target_min_words, target_max_words)
            raw_word_count = self._fast_draft_text_length(text)
            used_remote = False
            model_name = "local_fast_draft"
            provider_name = "local"
            expansion_count = 0
        else:
            system_prompt = (
                "你是长篇小说快速正文 Agent。请直接输出中文小说正文，不要输出解释、目录、Markdown 标题或大纲。"
                "必须遵守正典、章纲、视角和风格；正文要有完整场景推进、对话、行动、危机、高潮和结果。"
            )
            user_payload = {
                "project": serialize_project(project),
                "chapter": serialize_chapter(chapter),
                "canon_context": canon_context,
                "previous_summaries": previous_summaries,
                "target_words": chapter_max_words,
                "target_word_min": target_min_words,
                "target_word_max": target_max_words,
                "instruction": (
                    f"生成第{chapter.chapter_no}章《{chapter.title}》完整正文，正文长度控制在 {target_min_words}-{target_max_words} 个中文字符之间，"
                    f"接近 {chapter_max_words} 字，不要超过 {target_max_words} 字，并在自然句子边界收束。"
                    "保持悬疑、制度压迫和规则漏洞爽点。只输出正文。"
                ),
            }
            result = llm_client.generate(system_prompt, dumps(user_payload), request.model)
            text = self._clean_fast_draft_text(result.content, chapter.chapter_no)
            raw_word_count = self._fast_draft_text_length(text)
            used_remote = bool(result.used_remote_model)
            model_name = result.model
            provider_name = result.provider
            expansion_count = 0
            while self._fast_draft_text_length(text) < target_min_words and expansion_count < 2:
                current_words = self._fast_draft_text_length(text)
                remaining_min = max(1, target_min_words - current_words)
                remaining_max = max(remaining_min, target_max_words - current_words)
                expand_payload = {
                    **user_payload,
                    "existing_text": text,
                    "current_words": current_words,
                    "remaining_word_min": remaining_min,
                    "remaining_word_max": remaining_max,
                    "instruction": (
                        f"在不重复原文的前提下续写第{chapter.chapter_no}章，只补足 {remaining_min}-{remaining_max} 个中文字符。"
                        f"合并后总长度必须控制在 {target_min_words}-{target_max_words} 字之间，并在自然句子边界收束。只输出可直接续接的正文段落。"
                    ),
                }
                expansion = llm_client.generate(system_prompt, dumps(expand_payload), request.model)
                text = (text.rstrip() + "\n\n" + self._clean_fast_draft_text(expansion.content, chapter.chapter_no)).strip()
                raw_word_count = self._fast_draft_text_length(text)
                used_remote = bool(result.used_remote_model or expansion.used_remote_model)
                model_name = expansion.model or result.model
                provider_name = expansion.provider or result.provider
                expansion_count += 1
        text = self._trim_fast_draft_text_to_band(text, target_min_words, target_max_words)

        summary = f"第{chapter.chapter_no}章《{chapter.title}》完成快速正文，围绕{chapter.core_event or chapter.outline}推进。"
        chapter.draft_text = text
        chapter.final_text = text
        chapter.summary = summary
        chapter.revision_notes = dumps(
            {
                "mode": "fast_draft",
                "note": "20万字闭环压力测试快速正文。",
                "target_word_min": target_min_words,
                "target_word_max": target_max_words,
            }
        )
        chapter.status = "drafted"
        chapter.word_count = self._fast_draft_text_length(text)
        output = models.GenerationOutput(
            id=generate_id("out"),
            project_id=project_id,
            chapter_id=chapter_id,
            job_id=child_job.id,
            output_type="chapter_draft_fast",
            title=chapter.title,
            content=text,
            summary=summary,
            metadata_json=dumps(
                {
                    "mode": "fast_draft",
                    "target_words": chapter_max_words,
                    "target_word_min": target_min_words,
                    "target_word_max": target_max_words,
                    "actual_words": chapter.word_count,
                    "raw_words": raw_word_count,
                    "expansion_count": expansion_count,
                    "trimmed_to_range": raw_word_count != chapter.word_count,
                    "_llm": {
                        "provider": provider_name,
                        "model": model_name,
                        "used_remote_model": used_remote,
                    },
                }
            ),
        )
        db.add(output)
        self._record_agent_run(
            db,
            child_job,
            "fast_draft_writer",
            {
                "final_chapter_text": text,
                "summary": summary,
                "_llm": {"provider": provider_name, "model": model_name, "used_remote_model": used_remote},
            },
            {"chapter": serialize_chapter(chapter), "mode": "fast_draft"},
        )
        self._snapshot(db, project_id, chapter_id, child_job.id, "fast_draft_writer", "chapter", text, "快速正文生成")
        self._finish_job(db, child_job, {"chapter": serialize_chapter(chapter), "draft_text": text, "polished_text": text, "mode": "fast_draft"})
        self._fast_draft_parent_progress(db, parent_job_id, parent_chapter_no, parent_total_steps, child_job, f"第{chapter.chapter_no}章：快速正文已完成")
        db.commit()
        db.refresh(chapter)
        db.refresh(child_job)
        return {"job": serialize_job(child_job), "chapter": serialize_chapter(chapter)}

    def _local_fast_draft_text(
        self,
        project: models.Project,
        chapter: models.Chapter,
        previous_summaries: list[dict[str, Any]],
        target_min_words: int,
        target_max_words: int,
    ) -> str:
        title = chapter.title or f"第{chapter.chapter_no}章"
        premise = project.premise or project.initial_idea or project.title
        outline = chapter.outline or chapter.core_event or "主角面对新的压力并作出选择。"
        core_event = chapter.core_event or outline
        conflict = chapter.conflict or "反对力量把压力落到具体行动上。"
        crisis = chapter.crisis or "主角必须在退让与冒险之间作出不可逆选择。"
        climax = chapter.climax or "主角执行选择，让局面产生可见变化。"
        outcome = chapter.outcome or chapter.turn_point or chapter.summary or "局面改变，并留下下一章必须回应的问题。"
        hook = chapter.cliffhanger or "新的问题在章末浮出水面。"
        previous_tail = "；".join(str(item.get("summary") or item.get("title") or "") for item in previous_summaries[-2:] if isinstance(item, dict))
        viewpoint = chapter.pov_character or "林小满"
        beat_templates = [
            f"{viewpoint}站在这一章的开端时，最先感到的不是胜算，而是从四面八方压下来的荒诞感。{premise}这件事仍像一根细刺，扎在她的判断里。{previous_tail or '前面的余波还没有散去'}，她知道自己不能再把所有问题都当成玩笑。",
            f"眼前的麻烦很快变得具体。{core_event}周围人的目光、规矩的缝隙、资源的短缺和关系里的试探一起逼近。她习惯用一句不合时宜的俏皮话把气氛打歪，可这一次，笑声刚冒头，就被更重的沉默压了回去。",
            f"{conflict}这不是单纯的阻拦，而像一张写满条款的网。每一条都在提醒她：接地气的创意可以让她看见路，也会让她暴露位置。宋小鱼若在旁边，必定会先翻白眼，再伸手替她挡住最危险的一下；若不在旁边，那份空缺反而让她更清楚自己必须独自扛住这一段。",
            f"她试着拆解局面，把荒唐拆成可执行的小步。第一步是确认规则，第二步是找到规则没写清的角落，第三步则是把一句看似不体面的念头塞进那个角落。她越想越觉得好笑，也越想越害怕，因为好笑意味着可能成功，害怕意味着成功之后一定有人追来。",
            f"危机真正到来时，没有锣鼓，也没有谁郑重宣布。{crisis}她忽然明白，所谓选择从来不是挑一条轻松的路，而是在两种代价里承认自己更愿意承担哪一种。她能退，可退回去以后，之前所有灵感、所有欠下的人情、所有已经被点亮的希望都会一起熄灭。",
            f"于是她行动了。{climax}那一瞬间，空气像被一句冷笑话切开，紧绷的规则出现细小的裂纹。她没有把自己伪装成庄重的天才，也没有假装懂那些高高在上的术语，只是把最接近生活的念头推到前面，让它替自己撞门。",
            f"撞门的声音比预想中更响。有人错愕，有人恼怒，也有人忍不住笑出声。笑声一旦出现，局面就不再只属于审查和禁令。{outcome}她看见压力换了一种形状，从看不见的威胁变成了必须立刻处理的后果。",
            f"代价随后抵达。灵感的余波像涟漪一样散开，熟悉的危险感贴着脊背往上爬。她知道某些人会记录这次异常，某些规则会因此收紧，某些关系会被迫站队。但她也第一次如此确定：只要还有人能从荒诞里获得一点勇气，这条路就不算白走。",
            f"章末，{hook}她没有立刻庆祝，只把那句差点脱口而出的玩笑咽回去，换成一次更谨慎的呼吸。远处似乎有新的目光落下，近处也有未解决的债等着清算。她朝前走了一步，知道下一步不会更轻松，却已经没有回头的理由。",
        ]
        paragraphs: list[str] = []
        index = 0
        while self._fast_draft_text_length("\n\n".join(paragraphs)) < target_min_words:
            base = beat_templates[index % len(beat_templates)]
            cycle = index // len(beat_templates)
            if cycle:
                base = (
                    f"事情又向前推了一层。第{chapter.chapter_no}章的压力没有因为一次行动就消失，反而把更多细节逼到台前。"
                    f"{base}"
                )
            paragraphs.append(base)
            index += 1
        return self._trim_fast_draft_text_to_band("\n\n".join(paragraphs), target_min_words, target_max_words)

    def _run_batch_generate_job(self, job_id: str) -> None:
        with SessionLocal() as db:
            job = db.get(models.GenerationJob, job_id)
            if job is None or job.status in {"succeeded", "cancelled"}:
                return
            request = self._batch_request_from_job(job)
            chapter_numbers = list(range(request.chapter_start, request.chapter_end + 1))
            result_payload = self._batch_result_payload(job, request)
            self._reconcile_batch_result_payload(db, job, request, result_payload)
            completed_numbers = self._completed_batch_chapter_numbers(result_payload)
            job.status = "running"
            job.started_at = job.started_at or utcnow()
            job.finished_at = None
            job.heartbeat_at = utcnow()
            job.current_agent = "batch_generate"
            job.progress_json = dumps(
                self._batch_progress_payload(
                    job,
                    request,
                    result_payload,
                    current_step="running",
                    message="批量正文生成后台任务已启动",
                )
            )
            job.result_json = dumps(result_payload)
            db.commit()

        for chapter_no in chapter_numbers:
            should_continue = self._prepare_batch_chapter(job_id, request, chapter_no, len(chapter_numbers))
            if not should_continue:
                return
            with SessionLocal() as db:
                job = db.get(models.GenerationJob, job_id)
                if job is None:
                    return
                result_payload = self._batch_result_payload(job, request)
                if chapter_no in self._completed_batch_chapter_numbers(result_payload):
                    continue
                chapter = (
                    db.query(models.Chapter)
                    .filter(
                        models.Chapter.project_id == request.project_id,
                        models.Chapter.chapter_no == chapter_no,
                        models.Chapter.deleted_at.is_(None),
                    )
                    .first()
                )
                if chapter is None:
                    self._record_batch_chapter_failure(db, job, request, chapter_no, ValueError(f"第{chapter_no}章不存在或已归档"))
                    db.commit()
                    return
                chapter_id = chapter.id
                chapter_max_words = int(chapter.word_target or 0)
                if chapter_max_words <= 0:
                    project = db.get(models.Project, request.project_id)
                    chapter_max_words = int((project.chapter_word_target if project else 0) or DEFAULT_CHAPTER_WORD_TARGET)
                attempt = self._next_batch_chapter_attempt(db, job_id, chapter_id, result_payload, chapter_no)
            try:
                with SessionLocal() as chapter_db:
                    if self._batch_fast_draft_enabled(request):
                        chapter_result = self._generate_fast_batch_chapter(
                            chapter_db,
                            request.project_id,
                            chapter_id,
                            request,
                            chapter_max_words,
                            attempt,
                            parent_job_id=job_id,
                            parent_chapter_no=chapter_no,
                            parent_total_steps=len(chapter_numbers),
                        )
                    else:
                        chapter_result = self.draft_chapter(
                            chapter_db,
                            request.project_id,
                            chapter_id,
                            DraftChapterRequest(
                                user_instruction=f"批量生成。请按本章目标字数约 {chapter_max_words} 字生成完整正文。",
                                max_words=chapter_max_words,
                                model=request.model,
                                idempotency_key=f"batch:{job_id}:{chapter_id}:attempt:{attempt}",
                            ),
                            parent_job_id=job_id,
                            parent_chapter_no=chapter_no,
                            parent_total_steps=len(chapter_numbers),
                        )
            except Exception as exc:
                with SessionLocal() as db:
                    job = db.get(models.GenerationJob, job_id)
                    if job is not None:
                        self._record_batch_chapter_failure(db, job, request, chapter_no, exc)
                        db.commit()
                return
            with SessionLocal() as db:
                job = db.get(models.GenerationJob, job_id)
                if job is None:
                    return
                chapter = db.get(models.Chapter, chapter_id)
                if chapter is None:
                    self._record_batch_chapter_failure(db, job, request, chapter_no, ValueError(f"第{chapter_no}章生成后无法读取"))
                    db.commit()
                    return
                self._record_batch_chapter_success(db, job, request, chapter, chapter_result)
                db.commit()

        with SessionLocal() as db:
            job = db.get(models.GenerationJob, job_id)
            if job is None:
                return
            if job.cancel_requested or job.status == "cancelled":
                self._mark_batch_cancelled(db, job)
                db.commit()
                return
            if job.status == "paused":
                return
            request = self._batch_request_from_job(job)
            result_payload = self._batch_result_payload(job, request)
            self._finish_job(db, job, result_payload)
            db.commit()

    def _prepare_batch_chapter(self, job_id: str, request: BatchGenerateRequest, chapter_no: int, total_steps: int) -> bool:
        with SessionLocal() as db:
            job = db.get(models.GenerationJob, job_id)
            if job is None:
                return False
            result_payload = self._batch_result_payload(job, request)
            completed_numbers = self._completed_batch_chapter_numbers(result_payload)
            if chapter_no in completed_numbers:
                return True
            if job.cancel_requested or job.status == "cancelled":
                self._mark_batch_cancelled(db, job)
                db.commit()
                return False
            if job.status == "paused":
                job.heartbeat_at = utcnow()
                job.progress_json = dumps(
                    self._batch_progress_payload(
                        job,
                        request,
                        result_payload,
                        current_step="paused",
                        current_chapter_no=chapter_no,
                        message="批量任务已暂停，将在恢复后从未完成章节继续",
                    )
                )
                db.commit()
                return False
            job.status = "running"
            job.current_agent = f"batch_generate:chapter_{chapter_no}"
            job.heartbeat_at = utcnow()
            job.progress_json = dumps(
                self._batch_progress_payload(
                    job,
                    request,
                    result_payload,
                    current_step=f"chapter_{chapter_no}",
                    current_chapter_no=chapter_no,
                    message=f"正在生成第{chapter_no}章正文",
                )
            )
            db.commit()
            return True

    def _completed_batch_chapter_numbers(self, result_payload: dict[str, Any]) -> set[int]:
        numbers: set[int] = set()
        for item in result_payload.get("chapter_results", []):
            if not isinstance(item, dict):
                continue
            try:
                numbers.add(int(item.get("chapter_no")))
            except (TypeError, ValueError):
                continue
        return numbers

    def _reconcile_batch_result_payload(
        self,
        db: Session,
        job: models.GenerationJob,
        request: BatchGenerateRequest,
        result_payload: dict[str, Any],
    ) -> bool:
        changed = False
        valid_results: list[dict[str, Any]] = []
        failed_chapters = [item for item in result_payload.get("failed_chapters", []) if isinstance(item, dict)]
        failed_numbers = self._failed_batch_chapter_numbers({"failed_chapters": failed_chapters})
        for item in result_payload.get("chapter_results", []):
            if not isinstance(item, dict):
                changed = True
                continue
            try:
                chapter_no = int(item.get("chapter_no"))
            except (TypeError, ValueError):
                changed = True
                continue
            chapter = (
                db.query(models.Chapter)
                .filter(
                    models.Chapter.project_id == job.project_id,
                    models.Chapter.chapter_no == chapter_no,
                    models.Chapter.deleted_at.is_(None),
                )
                .first()
            )
            chapter_text = (chapter.final_text or chapter.draft_text) if chapter is not None else ""
            minimum_words = int(chapter.word_target or 0) if chapter is not None else 0
            meets_length = minimum_words <= 0 or (chapter is not None and chapter.word_count >= minimum_words)
            is_valid = (
                chapter is not None
                and chapter.status in {"drafted", "completed", "finalized"}
                and chapter.word_count > 0
                and meets_length
                and bool(chapter_text.strip())
            )
            if is_valid:
                refreshed = {
                    **item,
                    "chapter_no": chapter.chapter_no,
                    "chapter_id": chapter.id,
                    "title": chapter.title,
                    "status": chapter.status,
                    "word_count": chapter.word_count,
                    "chapter": serialize_chapter(chapter),
                }
                valid_results.append(refreshed)
                if refreshed != item:
                    changed = True
                continue
            if chapter_no not in failed_numbers:
                if chapter is not None and chapter.word_count > 0 and minimum_words > 0 and chapter.word_count < minimum_words:
                    message = f"章节正文低于目标字数：当前 {chapter.word_count} 字，目标 {minimum_words} 字"
                else:
                    message = "章节正文未成功写入，已从完成结果剔除并等待重试"
                failed_chapters.append(
                    {
                        "chapter_no": chapter_no,
                        "message": message,
                        "failed_at": isoformat(utcnow()),
                        "retryable": True,
                        "source": "batch_result_reconciliation",
                    }
                )
                failed_numbers.append(chapter_no)
            changed = True
        valid_results.sort(key=lambda item: int(item.get("chapter_no", 0)))
        if changed:
            result_payload["chapter_results"] = valid_results
            result_payload["failed_chapters"] = failed_chapters
            result_payload["last_completed_chapter_no"] = valid_results[-1]["chapter_no"] if valid_results else None
        return changed

    def _batch_chapter_attempt(self, result_payload: dict[str, Any], chapter_no: int) -> int:
        attempts = 1
        for item in result_payload.get("failed_chapters", []):
            if not isinstance(item, dict):
                continue
            try:
                if int(item.get("chapter_no")) == chapter_no:
                    attempts += 1
            except (TypeError, ValueError):
                continue
        return attempts

    def _next_batch_chapter_attempt(
        self,
        db: Session,
        job_id: str,
        chapter_id: str,
        result_payload: dict[str, Any],
        chapter_no: int,
    ) -> int:
        next_attempt = self._batch_chapter_attempt(result_payload, chapter_no)
        prefix = f"batch:{job_id}:{chapter_id}:attempt:"
        existing_jobs = (
            db.query(models.GenerationJob.idempotency_key)
            .filter(
                models.GenerationJob.job_type == "draft_chapter",
                models.GenerationJob.chapter_id == chapter_id,
                models.GenerationJob.idempotency_key.like(f"{prefix}%"),
            )
            .all()
        )
        max_existing_attempt = 0
        for (idempotency_key,) in existing_jobs:
            match = re.search(r":attempt:(\d+)$", idempotency_key or "")
            if not match:
                continue
            max_existing_attempt = max(max_existing_attempt, int(match.group(1)))
        return max(next_attempt, max_existing_attempt + 1)

    def _record_batch_chapter_success(
        self,
        db: Session,
        job: models.GenerationJob,
        request: BatchGenerateRequest,
        chapter: models.Chapter,
        chapter_result: dict[str, Any],
    ) -> None:
        result_payload = self._batch_result_payload(job, request)
        child_job = chapter_result.get("job") if isinstance(chapter_result, dict) else None
        if not isinstance(child_job, dict) or child_job.get("status") != "succeeded":
            raise ValueError(f"第{chapter.chapter_no}章子任务未成功，不能记录为批量完成")
        chapter_payload = chapter_result.get("chapter") if isinstance(chapter_result, dict) else None
        if not isinstance(chapter_payload, dict):
            chapter_payload = serialize_chapter(chapter)
        chapter_text = chapter.final_text or chapter.draft_text or ""
        if chapter.status not in {"drafted", "completed", "finalized"} or chapter.word_count <= 0 or not chapter_text.strip():
            raise ValueError(f"第{chapter.chapter_no}章正文未成功写入，不能记录为批量完成")
        if chapter.word_target > 0 and chapter.word_count < chapter.word_target:
            raise ValueError(f"第{chapter.chapter_no}章正文低于目标字数：当前 {chapter.word_count} 字，目标 {chapter.word_target} 字")
        chapter_summary = {
            "chapter_no": chapter.chapter_no,
            "chapter_id": chapter.id,
            "title": chapter.title,
            "status": chapter.status,
            "word_count": chapter.word_count,
            "job_id": child_job.get("id") if isinstance(child_job, dict) else None,
            "chapter": chapter_payload,
        }
        result_payload["chapter_results"] = [
            item
            for item in result_payload.get("chapter_results", [])
            if not isinstance(item, dict) or int(item.get("chapter_no", -1)) != chapter.chapter_no
        ]
        result_payload["chapter_results"].append(chapter_summary)
        result_payload["chapter_results"].sort(key=lambda item: int(item.get("chapter_no", 0)) if isinstance(item, dict) else 0)
        result_payload["failed_chapters"] = [
            item
            for item in result_payload.get("failed_chapters", [])
            if not isinstance(item, dict) or int(item.get("chapter_no", -1)) != chapter.chapter_no
        ]
        result_payload["last_completed_chapter_no"] = chapter.chapter_no
        completed_steps = len(self._completed_batch_chapter_numbers(result_payload))
        total_steps = request.chapter_end - request.chapter_start + 1
        job.error_message = None
        job.heartbeat_at = utcnow()
        job.result_json = dumps(result_payload)
        if job.cancel_requested or job.status == "cancelled":
            self._mark_batch_cancelled(db, job)
            return
        paused_after_current_chapter = job.status == "paused"
        job.status = "paused" if paused_after_current_chapter else "running"
        job.progress_json = dumps(
            self._batch_progress_payload(
                job,
                request,
                result_payload,
                current_step="paused" if paused_after_current_chapter else f"chapter_{chapter.chapter_no}_done",
                current_chapter_no=chapter.chapter_no,
                message=f"第{chapter.chapter_no}章已完成并提交，任务已暂停" if paused_after_current_chapter else f"第{chapter.chapter_no}章已完成并提交",
            )
        )

    def _record_batch_chapter_failure(
        self,
        db: Session,
        job: models.GenerationJob,
        request: BatchGenerateRequest,
        chapter_no: int,
        error: Exception,
    ) -> None:
        result_payload = self._batch_result_payload(job, request)
        message = str(error)
        result_payload["failed_chapters"] = [
            item
            for item in result_payload.get("failed_chapters", [])
            if not isinstance(item, dict) or int(item.get("chapter_no", -1)) != chapter_no
        ]
        result_payload["failed_chapters"].append({"chapter_no": chapter_no, "message": message, "failed_at": isoformat(utcnow())})
        completed_steps = len(self._completed_batch_chapter_numbers(result_payload))
        total_steps = request.chapter_end - request.chapter_start + 1
        job.status = "failed"
        job.error_message = message
        job.finished_at = utcnow()
        job.heartbeat_at = utcnow()
        job.result_json = dumps(result_payload)
        job.progress_json = dumps(
            self._batch_progress_payload(
                job,
                request,
                result_payload,
                current_step="failed",
                current_chapter_no=chapter_no,
                message=f"第{chapter_no}章生成失败，可重试继续",
            )
        )

    def _mark_batch_cancelled(self, db: Session, job: models.GenerationJob) -> None:
        request = self._batch_request_from_job(job)
        result_payload = self._batch_result_payload(job, request)
        progress = loads(job.progress_json, {})
        job.status = "cancelled"
        job.cancel_requested = 1
        job.finished_at = utcnow()
        job.heartbeat_at = utcnow()
        job.progress_json = dumps(
            self._batch_progress_payload(
                job,
                request,
                result_payload,
                current_step="cancelled",
                current_chapter_no=progress.get("current_chapter_no"),
                message="批量任务已取消",
            )
        )

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
        def positive_int(value: Any, fallback: int, minimum: int = 1, maximum: int | None = None) -> int:
            try:
                number = int(value)
            except (TypeError, ValueError):
                number = int(fallback)
            number = max(minimum, number)
            if maximum is not None:
                number = min(maximum, number)
            return number

        manual_tags = self._as_str_list(basic_info.get("manual_tags"))
        tags = [*self._as_str_list(basic_info.get("tags")), *manual_tags]
        genre = str(basic_info.get("genre") or project.genre or "类型小说")
        subgenres = self._as_str_list(basic_info.get("subgenres"))
        chapter_count = positive_int(
            basic_info.get("chapter_count") or basic_info.get("planned_chapter_count"),
            project.planned_chapter_count or 80,
            maximum=5000,
        )
        volume_count = positive_int(basic_info.get("volume_count"), max(1, round(chapter_count / 40)), maximum=30)
        chapters_per_volume = positive_int(
            basic_info.get("chapters_per_volume"),
            max(1, (chapter_count + volume_count - 1) // volume_count),
            maximum=300,
        )
        if not basic_info.get("chapter_count") and not basic_info.get("planned_chapter_count") and basic_info.get("volume_count") and basic_info.get("chapters_per_volume"):
            chapter_count = volume_count * chapters_per_volume
        chapter_word_min = positive_int(
            basic_info.get("chapter_word_min"),
            basic_info.get("chapter_word_target") or project.chapter_word_target or DEFAULT_CHAPTER_WORD_TARGET,
            minimum=500,
            maximum=20000,
        )
        chapter_word_target_fallback = positive_int(
            basic_info.get("chapter_word_target"),
            project.chapter_word_target or chapter_word_min,
            minimum=500,
            maximum=20000,
        )
        chapter_word_max = positive_int(
            basic_info.get("chapter_word_max"),
            max(chapter_word_min, chapter_word_target_fallback),
            minimum=500,
            maximum=20000,
        )
        if chapter_word_max < chapter_word_min:
            chapter_word_min, chapter_word_max = chapter_word_max, chapter_word_min
        chapter_word_target = positive_int(
            basic_info.get("chapter_word_target"),
            round((chapter_word_min + chapter_word_max) / 2),
            minimum=500,
            maximum=20000,
        )
        chapter_word_target = min(max(chapter_word_target, chapter_word_min), chapter_word_max)
        target_words = chapter_count * chapter_word_target
        scale_plan = {
            "target_words": target_words,
            "volume_count": volume_count,
            "chapter_count": chapter_count,
            "chapters_per_volume": chapters_per_volume,
            "chapter_word_target": chapter_word_target,
            "chapter_word_min": chapter_word_min,
            "chapter_word_max": chapter_word_max,
        }
        return {
            "channel": str(basic_info.get("channel") or "通用"),
            "genre": genre,
            "subgenres": subgenres,
            "tags": list(dict.fromkeys(tags)),
            "manual_tags": manual_tags,
            "target_reader": str(basic_info.get("target_reader") or project.target_reader or "类型小说读者"),
            "target_words": target_words,
            "volume_count": volume_count,
            "chapter_count": chapter_count,
            "planned_chapter_count": chapter_count,
            "chapters_per_volume": chapters_per_volume,
            "chapter_word_target": chapter_word_target,
            "chapter_word_min": chapter_word_min,
            "chapter_word_max": chapter_word_max,
            "scale_plan": scale_plan,
            "style": str(basic_info.get("style") or project.style_guide or "清晰、有悬念"),
            "initial_idea": str(basic_info.get("initial_idea") or project.initial_idea or project.premise),
        }

    def _apply_creation_basic_to_project(self, project: models.Project, basic: dict[str, Any]) -> None:
        project.genre = str(basic.get("genre") or project.genre or "")
        project.target_reader = str(basic.get("target_reader") or project.target_reader or "")
        project.target_words = int(basic.get("target_words") or project.target_words or 0)
        project.planned_chapter_count = int(
            basic.get("chapter_count") or basic.get("planned_chapter_count") or project.planned_chapter_count or 1
        )
        project.planned_volume_count = int(basic.get("volume_count") or project.planned_volume_count or 1)
        project.chapters_per_volume = int(basic.get("chapters_per_volume") or project.chapters_per_volume or 1)
        project.chapter_word_target = int(basic.get("chapter_word_target") or project.chapter_word_target or DEFAULT_CHAPTER_WORD_TARGET)
        project.chapter_word_min = int(basic.get("chapter_word_min") or project.chapter_word_min or project.chapter_word_target)
        project.chapter_word_max = int(basic.get("chapter_word_max") or project.chapter_word_max or project.chapter_word_target)
        project.initial_idea = str(basic.get("initial_idea") or project.initial_idea or "")
        project.style_guide = str(basic.get("style") or project.style_guide or "")
        project.updated_at = utcnow()

    def _creation_basic_suggestions_prompt_snapshot(self, basic: dict[str, Any], request: CreationBasicSuggestionsRequest) -> dict[str, Any]:
        return {
            "agent_name": "creation_basic_suggestions",
            "workflow_id": "creation_star_session",
            "required_inputs": ["basic_info", "manual_input", "previous_suggestions"],
            "context_summary": (
                f"频道={basic.get('channel')}；类型={basic.get('genre')}；细分={self._short('、'.join(self._as_str_list(basic.get('subgenres'))), 80)}；"
                f"标签={self._short('、'.join(self._as_str_list(basic.get('tags'))), 100)}；目标读者={self._short(basic.get('target_reader'), 100)}；"
                f"Scale Planner={basic.get('volume_count')}卷/{basic.get('chapter_count')}章/"
                f"每章{basic.get('chapter_word_min')}-{basic.get('chapter_word_max')}字/"
                f"目标总字数={basic.get('target_words')}；风格={self._short(basic.get('style'), 80)}；初始想法={self._short(basic.get('initial_idea'), 160)}；"
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

    def _empty_creation_profile(self) -> dict[str, Any]:
        return {
            "basic_info": {},
            "selected_worldview": {},
            "selected_protagonist": {},
            "selected_title": {},
            "market_position": {},
            "project_seed": {},
            "core_conflict_system": {},
            "novel_constitution": {},
            "constitution_review": {},
            "canon_candidates": {},
            "confirmed_canon": {},
        }

    def _creation_profile_from_session(self, session: models.CreationSession) -> dict[str, Any]:
        state = self._creation_session_state(session)
        seed = state.get("project_seed") if isinstance(state.get("project_seed"), dict) else {}
        confirmed = state.get("confirmed_canon") if isinstance(state.get("confirmed_canon"), dict) else {}

        def pick_dict(*keys: str) -> dict[str, Any]:
            for key in keys:
                value = state.get(key)
                if isinstance(value, dict) and value:
                    return value
                value = seed.get(key)
                if isinstance(value, dict) and value:
                    return value
                value = confirmed.get(key)
                if isinstance(value, dict) and value:
                    return value
            return {}

        basic_info = loads(session.basic_info_json, {})
        if not isinstance(basic_info, dict):
            basic_info = {}
        seed_basic = seed.get("basic_info")
        if isinstance(seed_basic, dict):
            basic_info = {**basic_info, **seed_basic}
        return {
            "basic_info": basic_info,
            "selected_worldview": pick_dict("selected_worldview"),
            "selected_protagonist": pick_dict("selected_protagonist"),
            "selected_title": pick_dict("selected_title"),
            "market_position": pick_dict("market_position"),
            "project_seed": seed,
            "core_conflict_system": pick_dict("core_conflict_system"),
            "novel_constitution": pick_dict("novel_constitution"),
            "constitution_review": pick_dict("constitution_review"),
            "canon_candidates": pick_dict("canon_candidates"),
            "confirmed_canon": confirmed,
        }

    def _creation_session_state_summary(self, session: models.CreationSession) -> dict[str, Any]:
        state = self._creation_session_state(session)

        def card_count(key: str) -> int:
            value = state.get(key)
            return len(value) if isinstance(value, list) else 0

        def selected_id(key: str) -> str:
            value = state.get(key)
            if isinstance(value, dict):
                return str(value.get("id") or "")
            return ""

        market_position = state.get("market_position") if isinstance(state.get("market_position"), dict) else {}
        constitution_review = state.get("constitution_review") if isinstance(state.get("constitution_review"), dict) else {}
        canon_candidates = state.get("canon_candidates") if isinstance(state.get("canon_candidates"), dict) else {}
        return {
            "model": state.get("model"),
            "worldview_candidates_count": card_count("worldview_candidates"),
            "protagonist_candidates_count": card_count("protagonist_candidates"),
            "title_candidates_count": card_count("title_candidates"),
            "market_position_candidates_count": card_count("market_position_candidates"),
            "selected_worldview_id": selected_id("selected_worldview"),
            "selected_protagonist_id": selected_id("selected_protagonist"),
            "selected_title_id": selected_id("selected_title"),
            "has_market_position": bool(market_position),
            "market_position_source": str(market_position.get("source") or ""),
            "has_project_seed": bool(state.get("project_seed")),
            "has_core_conflict_system": bool(state.get("core_conflict_system")),
            "has_novel_constitution": bool(state.get("novel_constitution")),
            "constitution_review_status": str(constitution_review.get("status") or ""),
            "canon_candidate_sections": sorted(str(key) for key in canon_candidates.keys()),
        }

    def _serialize_creation_session_compact(self, session: models.CreationSession) -> dict[str, Any]:
        payload = serialize_creation_session(session)
        payload["state"] = self._creation_session_state_summary(session)
        return payload

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

    def _creation_title_packaging_agent_name(self) -> str:
        return "creation_title_packaging"

    def _creation_title_packaging_system_prompt(self) -> str:
        return load_catalog_prompt("creation_title_packaging")

    def _creation_title_packaging_runtime_strategy(self) -> dict[str, Any]:
        legacy_prompt_chars = (
            len(AGENT_SPECS_BY_NAME["creation_star"].prompt)
            + len(load_catalog_prompt("core_conflict_system"))
            + len(load_catalog_prompt("novel_constitution"))
        )
        dedicated_prompt_chars = len(self._creation_title_packaging_system_prompt())
        return {
            "selected": "dedicated_title_packaging_prompt",
            "reason": "书名与包装抽卡只需要已选世界观和主角，生成标题、广告句、核心卖点、读者期待和平台风格；核心矛盾系统和小说宪法延后到用户确认立项种子后生成。",
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
        job = self._create_job_committed(db, project.id, None, job_type, model, request.model_dump(), total_steps=1)
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
            agent_name = self._creation_title_packaging_agent_name()
            role = "书名与包装抽卡 Agent"
            system_prompt = self._creation_title_packaging_system_prompt()
            task = f"执行创作 Star 书名与包装逐卡抽卡。count={count} 时只输出本轮新增书名包装候选；不要生成世界观、主角人设、核心矛盾系统或小说宪法。"
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
        self._require_creation_remote_json(step, llm_meta)
        if not isinstance(payload, dict):
            payload = fallback
        cards = payload.get("cards")
        if not isinstance(cards, list) or not cards:
            payload["cards"] = fallback["cards"]
        if step == "worldview":
            payload["cards"] = self._normalize_creation_worldview_cards(payload["cards"])
        if step == "protagonist":
            payload["cards"] = self._normalize_creation_protagonist_cards(payload["cards"])
        if step == "title":
            payload["cards"] = self._normalize_creation_title_packaging_cards(payload["cards"])
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
        system_prompt: str | None = None,
    ) -> tuple[dict[str, Any], models.GenerationJob, dict[str, Any]]:
        job = self._create_job_committed(db, project.id, None, job_type, model, context, total_steps=1)
        payload, llm_meta = call_agent_json(
            llm_client=llm_client,
            agent_name=agent_name,
            role=AGENT_SPECS_BY_NAME[agent_name].role,
            system_prompt=system_prompt or AGENT_SPECS_BY_NAME[agent_name].prompt,
            task=task,
            context={**context, "fallback_output": fallback},
            fallback=fallback,
            model=model,
        )
        self._require_creation_remote_json(agent_name, llm_meta)
        return payload if isinstance(payload, dict) else fallback, job, llm_meta

    def _require_creation_remote_json(self, stage: str, llm_meta: dict[str, Any]) -> None:
        if not get_settings().llm_require_remote:
            return
        if llm_meta.get("used_remote_model") is True and llm_meta.get("parsed") is True and llm_meta.get("schema_valid") is True:
            return
        raise _bad_request(
            f"{stage} 真实 LLM 输出未通过 JSON 质量门，已阻止写入下游状态",
            {
                "provider": llm_meta.get("provider", ""),
                "model": llm_meta.get("model", ""),
                "used_remote_model": llm_meta.get("used_remote_model"),
                "parsed": llm_meta.get("parsed"),
                "schema_valid": llm_meta.get("schema_valid"),
                "validation_warnings": llm_meta.get("validation_warnings", []),
            },
        )

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

    def _apply_creation_session_run_edits(self, state: dict[str, Any], request: CreationSessionRunRequest) -> None:
        if request.core_conflict_system:
            state["core_conflict_system"] = request.core_conflict_system
        if request.novel_constitution:
            state["novel_constitution"] = request.novel_constitution

    def _catalog_task_system_prompt(self, agent_name: str, prompt_id: str) -> str:
        return (
            f"{AGENT_SPECS_BY_NAME[agent_name].prompt}\n\n"
            "## 当前任务专用提示词\n"
            f"### prompt_id={prompt_id}\n"
            f"{load_catalog_prompt(prompt_id)}"
        )

    def _creation_seed_context(
        self,
        project: models.Project,
        seed: dict[str, Any],
        instruction: str = "",
        core_conflict: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        basic = seed.get("basic_info") if isinstance(seed.get("basic_info"), dict) else {}
        worldview = seed.get("selected_worldview") if isinstance(seed.get("selected_worldview"), dict) else {}
        protagonist = seed.get("selected_protagonist") if isinstance(seed.get("selected_protagonist"), dict) else {}
        title = seed.get("selected_title") if isinstance(seed.get("selected_title"), dict) else {}
        market = seed.get("market_position") if isinstance(seed.get("market_position"), dict) else {}
        context: dict[str, Any] = {
            "project": serialize_project(project),
            "project_seed": seed,
            "basic_info": basic,
            "selected_worldview": worldview,
            "selected_protagonist": protagonist,
            "selected_title": title,
            "market_position": market,
            "canon_context": {},
            "instruction": instruction,
        }
        if core_conflict is not None:
            context["core_conflict_system"] = core_conflict
        return context

    def _core_conflict_from_seed(self, seed: dict[str, Any]) -> dict[str, Any]:
        worldview = seed.get("selected_worldview") if isinstance(seed.get("selected_worldview"), dict) else {}
        protagonist = seed.get("selected_protagonist") if isinstance(seed.get("selected_protagonist"), dict) else {}
        basic = seed.get("basic_info") if isinstance(seed.get("basic_info"), dict) else {}
        title = seed.get("selected_title") if isinstance(seed.get("selected_title"), dict) else {}
        market = seed.get("market_position") if isinstance(seed.get("market_position"), dict) else {}
        protagonist_name = str(protagonist.get("name") or "主角")
        desire = str(protagonist.get("long_term_desire") or protagonist.get("long_term_goal") or "夺回选择命运的主动权")
        world_pressure = str(
            worldview.get("conflict_engine_seed")
            or worldview.get("conflict_hook")
            or worldview.get("social_pressure")
            or "旧秩序、资源垄断和关系压力阻止主角前进"
        )
        relationship_hooks = protagonist.get("relationship_hooks") or protagonist.get("relationship_hook") or "关键关系既提供帮助也制造误判。"
        relationship_resistance = "、".join(self._as_str_list(relationship_hooks)) or str(relationship_hooks)
        selling_point = market.get("core_selling_point") or title.get("core_selling_point") or title.get("selling_point") or worldview.get("selling_point")
        reader_expectation = market.get("reader_expectation") or title.get("reader_expectation")
        ability_cost = protagonist.get("ability_cost") or "能力越有效，越会放大身份暴露、关系误伤或资源透支。"
        core_conflict = f"{protagonist_name}想要{desire}，但{world_pressure}。"
        return {
            "protagonist_desire": desire,
            "world_resistance": world_pressure,
            "core_conflict": core_conflict,
            "external_resistance": worldview.get("social_pressure") or worldview.get("description") or f"{basic.get('genre', '世界')}规则持续制造外部压力。",
            "internal_resistance": protagonist.get("inner_wound") or "主角害怕再次被旧秩序定义。",
            "relationship_resistance": relationship_resistance,
            "institutional_resistance": "资格、资源、榜单、势力分配共同构成制度阻力。",
            "typical_cost": str(ability_cost),
            "long_form_engine": str(selling_point or reader_expectation or "欲望、阻力、选择和代价可持续循环升级，支撑长篇连载。"),
            "possible_endpoint": "主角重新定义规则，但必须承担新秩序的代价。",
            "theme_question": "普通人能否在不被旧秩序同化的前提下夺回选择权。",
        }

    def _novel_constitution_from_seed(self, seed: dict[str, Any], core_conflict: dict[str, Any]) -> dict[str, Any]:
        basic = seed.get("basic_info") if isinstance(seed.get("basic_info"), dict) else {}
        worldview = seed.get("selected_worldview") if isinstance(seed.get("selected_worldview"), dict) else {}
        protagonist = seed.get("selected_protagonist") if isinstance(seed.get("selected_protagonist"), dict) else {}
        title = seed.get("selected_title") if isinstance(seed.get("selected_title"), dict) else {}
        market = seed.get("market_position") if isinstance(seed.get("market_position"), dict) else {}
        tags = self._as_str_list(basic.get("tags")) or self._as_str_list(worldview.get("tags"))
        rule = worldview.get("core_world_rule") or worldview.get("core_rule") or worldview.get("description") or "世界规则必须持续制造选择与代价。"
        resource_system = worldview.get("power_or_resource_system") or worldview.get("resource_system") or "权力和资源由明面制度与暗面势力共同分配。"
        return {
            "basic_positioning": {
                "genre": basic.get("genre") or "类型小说",
                "tone": basic.get("style") or "清晰、有悬念",
                "target_reader_experience": basic.get("target_reader") or "类型小说读者",
                "story_keywords": tags[:8],
                "type_promise": market.get("core_selling_point") or title.get("core_selling_point") or worldview.get("selling_point") or "稳定兑现主角成长、规则压力和阶段爽点。",
            },
            "core_narrative_engine": core_conflict,
            "protagonist_arc": {
                "opening_state": protagonist.get("identity") or "被旧秩序限制的人",
                "surface_goal": protagonist.get("long_term_desire") or protagonist.get("long_term_goal") or core_conflict.get("protagonist_desire"),
                "deep_need": "夺回解释自身命运的主动权。",
                "largest_flaw": protagonist.get("weakness") or "习惯独自承担代价。",
                "ending_state": core_conflict.get("possible_endpoint"),
            },
            "world_rules": {
                "primary_logic": rule,
                "power_distribution": resource_system,
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

    def _normalize_creation_title_packaging_cards(self, cards: list[Any]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for index, raw_card in enumerate(cards):
            if not isinstance(raw_card, dict):
                continue
            card = dict(raw_card)
            if not card.get("id"):
                card["id"] = f"title_packaging_remote_{index + 1}"
            if not card.get("core_selling_point") and card.get("selling_point"):
                card["core_selling_point"] = card.get("selling_point")
            if not card.get("selling_point") and card.get("core_selling_point"):
                card["selling_point"] = card.get("core_selling_point")
            if not card.get("subtitle") and card.get("platform_style"):
                card["subtitle"] = card.get("platform_style")
            if not card.get("platform_style"):
                card["platform_style"] = "平台感命名"
            if not card.get("one_sentence_ad") and card.get("description"):
                card["one_sentence_ad"] = card.get("description")
            if not card.get("reader_expectation") and card.get("selling_point"):
                card["reader_expectation"] = f"期待前三章兑现：{self._short(card.get('selling_point'), 80)}"
            if not card.get("worldview_hook"):
                card["worldview_hook"] = card.get("description") or card.get("selling_point") or ""
            if not card.get("protagonist_hook"):
                card["protagonist_hook"] = card.get("one_sentence_ad") or card.get("description") or ""
            if not card.get("risk"):
                card["risk"] = "需要根据目标平台压缩标题长度，并在前三章快速兑现核心卖点。"
            if not card.get("revision_hint"):
                card["revision_hint"] = "可微调命名句式、题材关键词密度或主角处境钩子。"
            if not isinstance(card.get("tags"), list):
                card["tags"] = self._as_str_list(card.get("tags")) or ["书名包装"]
            normalized.append(card)
        return normalized

    def _creation_title_packaging_output_schema(self) -> dict[str, Any]:
        return {
            "cards": [
                {
                    "id": "title_packaging_<draw>_<index>",
                    "title": "书名候选，必须有平台感和题材识别度",
                    "subtitle": "副标题或包装方向",
                    "description": "说明这个命名方向如何绑定世界观、主角处境和读者钩子",
                    "platform_style": "强钩子口语化 / 题材直给 / 人物命运 / 悬疑旧案 / 热血爽点 / 文学感 / 反差脑洞 / 长线史诗",
                    "one_sentence_ad": "一句话广告语，可用于简介首句或封面推广语",
                    "core_selling_point": "核心卖点，必须来自已选世界观和主角",
                    "selling_point": "兼容字段，内容等同或略短于 core_selling_point",
                    "reader_expectation": "读者看到书名与卖点后，会期待前三章兑现什么",
                    "worldview_hook": "从已选世界观提炼出的包装钩子",
                    "protagonist_hook": "从已选主角提炼出的包装钩子",
                    "risk": "使用这个书名与卖点时的创作或市场风险",
                    "revision_hint": "作者最值得修改的方向",
                    "tags": ["标签 1", "标签 2", "标签 3"],
                }
            ]
        }

    def _title_card_to_market_position(
        self,
        title_card: dict[str, Any] | None,
        basic: dict[str, Any],
        worldview: dict[str, Any],
        protagonist: dict[str, Any],
    ) -> dict[str, Any]:
        card = title_card if isinstance(title_card, dict) else {}
        tags = self._as_str_list(card.get("tags")) or self._as_str_list(basic.get("tags")) or self._as_str_list(worldview.get("tags"))
        selling_point = (
            card.get("core_selling_point")
            or card.get("selling_point")
            or worldview.get("selling_point")
            or protagonist.get("reader_satisfaction")
            or "高概念长篇卖点"
        )
        hook = (
            card.get("one_sentence_ad")
            or card.get("worldview_hook")
            or card.get("protagonist_hook")
            or worldview.get("conflict_engine_seed")
            or protagonist.get("conflict_seed")
            or ""
        )
        return {
            "id": str(card.get("id") or "market_from_title_packaging"),
            "title": card.get("title") or worldview.get("title") or basic.get("genre") or "未命名作品",
            "target_reader": basic.get("target_reader") or "类型小说读者",
            "platform_fit": card.get("platform_style") or basic.get("channel") or "通用",
            "selling_point": selling_point,
            "core_selling_point": selling_point,
            "hook": hook,
            "reader_expectation": card.get("reader_expectation") or "前三章兑现题材承诺、主角处境和核心爽点。",
            "risk": card.get("risk") or worldview.get("risk") or "需要在前三章快速展示规则、代价和主角欲望。",
            "tags": list(dict.fromkeys([*tags[:6], str(basic.get("genre") or "类型小说")])),
            "source": "title_packaging",
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
            "title": "生成书名与包装抽卡：必须读取基本信息、已选世界观和已选主角，只生成标题、广告句、核心卖点、读者期待、平台风格和风险提示。",
        }
        if request.step == "worldview":
            agent_name = self._creation_worldview_agent_name()
            prompt_id = "creation_worldview_draw"
            system_prompt = self._creation_worldview_system_prompt()
        elif request.step == "protagonist":
            agent_name = self._creation_protagonist_agent_name()
            prompt_id = "creation_protagonist_draw"
            system_prompt = self._creation_protagonist_system_prompt()
        elif request.step == "title":
            agent_name = self._creation_title_packaging_agent_name()
            prompt_id = "creation_title_packaging"
            system_prompt = self._creation_title_packaging_system_prompt()
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
                "title": ["basic_info", "selected_worldview", "selected_protagonist"],
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
        if request.step == "title":
            snapshot["output_schema"] = self._creation_title_packaging_output_schema()
            snapshot["runtime_strategy"] = self._creation_title_packaging_runtime_strategy()
            snapshot["generation_settings"] = {
                "temperature": 0.86,
                "top_p": 0.92,
                "max_tokens": 2200,
                "count": request.count,
                "presence_penalty": 0.3,
                "frequency_penalty": 0.25,
            }
            snapshot["dedupe_rules"] = [
                "不能使用与上一批相同的命名句式",
                "不能使用与上一批相同的卖点角度",
                "不能使用与上一批相同的平台风格",
                "不能只替换主角名、地名或题材名词",
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
                f"已选世界观：{self._short(worldview.get('title'), 80)}；{self._short(worldview.get('description'), 180)}；冲突发动机种子={self._short(worldview.get('conflict_engine_seed') or worldview.get('conflict_hook'), 120)}。"
            )
        if protagonist:
            pieces.append(
                f"已选主角：{self._short(protagonist.get('name'), 60)}；身份={self._short(protagonist.get('identity'), 120)}；长期欲望={self._short(protagonist.get('long_term_desire') or protagonist.get('long_term_goal'), 140)}；成长弧={self._short(protagonist.get('character_arc'), 140)}。"
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
            platform_style = self._pick(style_labels, index, "平台感")
            selling_point = f"标题直接暴露题材钩子、主角处境或爽点承诺，并呼应冲突种子：{core_conflict[:42]}。"
            one_sentence_ad = (
                f"{protagonist_name}在{worldview_title}里撞上{resource}与旧秩序，"
                f"用{keyword}打出第一轮破局。"
            )
            cards.append(
                {
                    "id": f"title_packaging_{draw_key}_{index + 1}",
                    "title": title[:60],
                    "subtitle": platform_style,
                    "description": f"命名方向：{platform_style}。突出{basic.get('genre', '类型')}、{keyword}、{resource}和“{worldview_title}”的核心差异点。",
                    "platform_style": platform_style,
                    "one_sentence_ad": one_sentence_ad,
                    "core_selling_point": selling_point,
                    "selling_point": selling_point,
                    "reader_expectation": f"前三章期待看到{protagonist_name}被规则压住、发现{resource}破局点，并兑现{keyword}爽点。",
                    "worldview_hook": worldview.get("conflict_engine_seed") or worldview.get("conflict_hook") or worldview.get("core_rule") or worldview_title,
                    "protagonist_hook": protagonist.get("conflict_seed") or protagonist.get("long_term_goal") or protagonist.get("identity") or protagonist_name,
                    "risk": "正式使用前可按目标平台调短或增强关键词密度，避免信息过载。",
                    "revision_hint": "可根据平台风格压缩标题长度，或把主角处境换成更强开局钩子。",
                    "tags": list(dict.fromkeys([basic.get("genre", "类型"), keyword, resource, platform_style]))[:4],
                    "draw_id": draw_id,
                    "source": "agent",
                }
            )
        return self._normalize_creation_title_packaging_cards(cards)

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
            row = (
                db.query(models.Character)
                .filter(
                    models.Character.project_id == project_id,
                    models.Character.source == "project_seed",
                    models.Character.role_type == "protagonist",
                    models.Character.name.in_(["待定主角", "未命名主角"]),
                )
                .first()
            )
            if row is None:
                row = models.Character(id=generate_id("chr"), project_id=project_id, name=name, role="protagonist", role_type="protagonist")
                db.add(row)
            else:
                row.name = name
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
    ) -> list[models.GraphEdge]:
        character_node = self._ensure_graph_node(db, project_id, "character", character.id, character.name, character.importance_level, character.importance_score)
        edges: list[models.GraphEdge] = []
        for entity in entities:
            entity_node = self._ensure_graph_node(db, project_id, "entity", entity.id, entity.name, entity.importance_level, entity.importance_score)
            edges.append(
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
            )
        for fact in facts[:4]:
            fact_node = self._ensure_graph_node(db, project_id, "world_fact", fact.id, fact.title, fact.importance_level, fact.importance_score)
            edges.append(
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
            )
        return edges

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
            chapter_word_min=project.chapter_word_min or 0,
            chapter_word_max=project.chapter_word_max or 0,
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
            ("主线冲突", "main_conflict"),
            ("主线", "main_track"),
            ("暗线", "hidden_track"),
            ("人物线", "character_track"),
            ("世界揭示", "world_reveal"),
            ("阻力压力", "opposition_pressure"),
            ("主角变化", "protagonist_change"),
            ("人物弧光", "character_arc"),
        ]:
            value = item.get(key)
            if value:
                lines.append(f"{label}：{value if isinstance(value, str) else dumps(value)}")
        for label, key in [
            ("设定揭示计划", "setting_reveal_plan"),
            ("伏笔计划", "foreshadowing_plan"),
        ]:
            value = item.get(key)
            if isinstance(value, list) and value:
                lines.append(f"{label}：")
                lines.extend(f"- {entry}" for entry in value)
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
        if item.get("ending_hook") or item.get("volume_hook"):
            lines.append(f"卷末钩子：{item.get('ending_hook') or item.get('volume_hook')}")
        if item.get("risks"):
            lines.append(f"风险：{', '.join([str(risk) for risk in item['risks']])}")
        return "\n".join([line for line in lines if line.strip()])

    def _normalize_chapter_outline_item(self, item: dict[str, Any], project: models.Project) -> dict[str, Any]:
        chapter_no = int(item.get("chapter_no") or 1)
        volume_no = int(item.get("volume_no") or 1)
        chapter_hook = str(item.get("chapter_hook") or item.get("cliffhanger") or item.get("hook") or "")
        outcome = str(item.get("outcome") or item.get("result") or "")
        outline = str(item.get("outline") or item.get("outline_body") or item.get("story_function") or "")
        if "\n" not in outline and any(item.get(key) for key in ("core_event", "conflict", "crisis", "climax", "result", "state_change", "foreshadowing_use", "source_window")):
            outline = self._format_dynamic_chapter_outline_text(item, outcome, chapter_hook)
        return {
            "chapter_no": chapter_no,
            "volume_no": volume_no,
            "title": str(item.get("title") or f"第{chapter_no}章"),
            "outline": outline,
            "pov_character": str(item.get("pov_character") or ""),
            "core_event": str(item.get("core_event") or item.get("action") or ""),
            "conflict": str(item.get("conflict") or item.get("opposition_force") or ""),
            "crisis": str(item.get("crisis") or ""),
            "climax": str(item.get("climax") or ""),
            "outcome": outcome,
            "turn_point": str(item.get("turn_point") or item.get("state_change") or outcome),
            "emotional_beats": item.get("emotional_beats") if isinstance(item.get("emotional_beats"), list) else [],
            "plot_purpose": str(item.get("plot_purpose") or item.get("story_function") or ""),
            "cliffhanger": chapter_hook,
            "chapter_hook": chapter_hook,
            "foreshadowing_plants": item.get("foreshadowing_plants") if isinstance(item.get("foreshadowing_plants"), list) else [],
            "foreshadowing_payoffs": item.get("foreshadowing_payoffs") if isinstance(item.get("foreshadowing_payoffs"), list) else [],
            "canon_updates": item.get("canon_updates") if isinstance(item.get("canon_updates"), list) else [],
            "continuity_risks": item.get("continuity_risks") if isinstance(item.get("continuity_risks"), list) else [],
            "word_target": int(item.get("word_target") or project.chapter_word_target),
        }

    def _format_dynamic_chapter_outline_text(self, item: dict[str, Any], outcome: str, chapter_hook: str) -> str:
        def as_text(value: Any) -> str:
            if value in (None, "", [], {}):
                return ""
            if isinstance(value, str):
                return value
            return dumps(value)

        source_window = item.get("source_window")
        if isinstance(item.get("source_window_detail"), dict):
            detail = item["source_window_detail"]
            source_window = source_window or detail.get("window_range") or detail.get("window_no")
        lines = [
            f"章节定位：第{item.get('volume_no', '')}卷第{item.get('chapter_no', '')}章，来源窗口：{source_window or '未标明'}",
            f"标题：{item.get('title', '')}",
            f"核心事件：{item.get('core_event', '')}",
            f"冲突设计：{item.get('conflict', '')}",
            f"危机选择：{item.get('crisis', '')}",
            f"高潮执行：{item.get('climax', '')}",
            f"结果后果：{outcome}",
            f"状态变化：{as_text(item.get('state_change'))}",
            f"伏笔用途：{as_text(item.get('foreshadowing_use'))}",
            f"读者承诺：{item.get('reader_promise', '')}",
            f"连续性风险：{item.get('continuity_risk', '')}",
            f"章末钩子：{chapter_hook}",
        ]
        if item.get("milestone_function"):
            lines.insert(2, f"阶段功能：{item['milestone_function']}")
        return "\n".join(line for line in lines if str(line).strip() and not str(line).endswith("："))

    def _chapter_outline_canon_payload(self, item: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
        raw_updates = item.get("canon_updates") if isinstance(item.get("canon_updates"), list) else []
        payload: dict[str, list[dict[str, Any]]] = {"character_updates": [], "entity_updates": [], "world_fact_updates": []}
        chapter_no = int(item.get("chapter_no") or 0)
        for index, update in enumerate(raw_updates, start=1):
            if isinstance(update, dict):
                kind = str(update.get("type") or update.get("ref_type") or update.get("kind") or "").lower()
                name = str(update.get("name") or update.get("title") or "").strip()
                content = str(update.get("content") or update.get("description") or update.get("update") or update.get("reason") or "").strip()
                confidence = float(update.get("confidence") or 0.75)
                importance_score = int(update.get("importance_score") or 55)
                if kind in {"character", "role", "人物", "角色"} and name:
                    payload["character_updates"].append({"name": name, "updated_reason": content or "章纲确认更新"})
                    continue
                if kind in {"entity", "event", "item", "organization", "location", "势力", "地点", "物件", "事件", "组织"} and name:
                    payload["entity_updates"].append(
                        {
                            "name": name,
                            "entity_type": str(update.get("entity_type") or kind or "event"),
                            "importance_score": importance_score,
                        }
                    )
                    continue
                title = name or f"第{chapter_no}章正典更新{index}"
                payload["world_fact_updates"].append(
                    {
                        "title": title,
                        "content": content or title,
                        "category": str(update.get("category") or "chapter_outline"),
                        "confidence": confidence,
                        "importance_score": importance_score,
                    }
                )
                continue
            text = str(update or "").strip()
            if text:
                payload["world_fact_updates"].append(
                    {
                        "title": f"第{chapter_no}章正典更新{index}",
                        "content": text,
                        "category": "chapter_outline",
                        "confidence": 0.75,
                        "importance_score": 55,
                    }
                )
        return {key: value for key, value in payload.items() if value}

    def _persist_chapter_outline_candidates(
        self,
        db: Session,
        project: models.Project,
        candidates: list[dict[str, Any]],
        job_id: str | None,
        overwrite_existing: bool,
    ) -> list[models.Chapter]:
        normalized = [self._normalize_chapter_outline_item(item, project) for item in candidates]
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
            chapter.crisis = item["crisis"]
            chapter.climax = item["climax"]
            chapter.outcome = item["outcome"]
            chapter.turn_point = item["turn_point"]
            chapter.emotional_beats_json = dumps(item["emotional_beats"])
            chapter.plot_purpose = item["plot_purpose"]
            chapter.cliffhanger = item["cliffhanger"]
            chapter.chapter_hook = item["chapter_hook"]
            chapter.foreshadowing_plants_json = dumps(item["foreshadowing_plants"])
            chapter.foreshadowing_payoffs_json = dumps(item["foreshadowing_payoffs"])
            chapter.canon_updates_json = dumps(item["canon_updates"])
            chapter.continuity_risks_json = dumps(item["continuity_risks"])
            chapter.word_target = int(item["word_target"])
            chapter.sort_order = chapter_no
            if chapter.status not in CHAPTER_OUTLINE_STATUS_PROTECTED and not chapter.draft_text and not chapter.final_text:
                chapter.status = "planned"
            chapter.deleted_at = None
            chapters.append(chapter)
            db.flush()
            self._snapshot(db, project.id, chapter.id, job_id, "outline_debate", "chapter_outline", dumps(item), "大纲议事章纲确认写入")
            canon_payload = self._chapter_outline_canon_payload(item)
            if canon_payload:
                self._persist_canon_updates(db, project.id, chapter.id, canon_payload)
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

    def _chapter_draft_step_number(self, agent_name: str, previous_step: int) -> int:
        normalized = "canon_context" if agent_name == "build_context" else agent_name
        try:
            current = CHAPTER_DRAFT_PROGRESS_STEPS.index(normalized) + 1
        except ValueError:
            current = previous_step
        return max(previous_step, min(current, len(CHAPTER_DRAFT_PROGRESS_STEPS)))

    def _record_chapter_draft_progress(
        self,
        db: Session,
        job: models.GenerationJob,
        state: NovelStudioState,
        previous_step: int,
        *,
        parent_job_id: str | None = None,
        parent_chapter_no: int | None = None,
        parent_total_steps: int | None = None,
    ) -> int:
        current_agent = state.current_agent or "chapter_draft"
        total_steps = len(CHAPTER_DRAFT_PROGRESS_STEPS)
        progress_event = state.progress_event if isinstance(state.progress_event, dict) else {}
        step_status = str(progress_event.get("status") or "completed")
        is_running = step_status == "running"
        completed_steps = previous_step if is_running else self._chapter_draft_step_number(current_agent, previous_step)
        step_label = self._chapter_step_label(current_agent)
        message = str(progress_event.get("message") or "").strip()
        if not message and is_running:
            message = f"{step_label}正在执行，远程模型生成时可能需要等待。"
        elif not message:
            message = f"{current_agent} 已完成"
        if not is_running and current_agent == "quality_gate" and isinstance(state.quality_gate, dict) and state.quality_gate.get("status") == "passed":
            message = "质量门已通过，正在进入风格统一与字数扩写，长章节可能需要等待。"
        elif not is_running and current_agent == "style_unifier":
            message = "风格统一与字数扩写已完成"
        job.current_agent = current_agent
        job.heartbeat_at = utcnow()
        job.progress_json = dumps(
            {
                "current_step": current_agent,
                "current_step_label": step_label,
                "current_step_status": step_status,
                "total_steps": total_steps,
                "completed_steps": completed_steps,
                "message": message,
                "current_chapter_no": state.current_chapter,
            }
        )
        if parent_job_id and parent_chapter_no and parent_total_steps:
            parent_job = db.get(models.GenerationJob, parent_job_id)
            if parent_job is not None and parent_job.status not in {"succeeded", "failed", "cancelled"}:
                parent_request = self._batch_request_from_job(parent_job)
                parent_result = self._batch_result_payload(parent_job, parent_request)
                parent_job.status = "running"
                parent_job.current_agent = f"batch_generate:chapter_{parent_chapter_no}:{current_agent}"
                parent_job.heartbeat_at = utcnow()
                parent_job.progress_json = dumps(
                    self._batch_progress_payload(
                        parent_job,
                        parent_request,
                        parent_result,
                        current_step=f"chapter_{parent_chapter_no}:{current_agent}",
                        current_chapter_no=parent_chapter_no,
                        child_job_id=job.id,
                        child_current_step=current_agent,
                        child_current_step_status=step_status,
                        child_total_steps=total_steps,
                        child_completed_steps=completed_steps,
                        message=f"第{parent_chapter_no}章：{step_label}{'正在执行' if is_running else '已完成'}",
                    )
                )
        db.commit()
        return completed_steps

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
        if job.job_type == "batch_generate":
            request = self._batch_request_from_job(job)
            job.progress_json = dumps(self._batch_progress_payload(job, request, result, current_step="completed", message="任务已完成"))
        else:
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
        job.heartbeat_at = utcnow()

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
        legacy_phase_key = "50章" + "高密度剧情流水线执行协议"
        phase_blocks = item.get("阶段剧情推进协议") or item.get("剧情推进协议") or item.get(legacy_phase_key) or []
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
            "阶段剧情推进协议：",
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
            "volumes": "volume",
            "volume_outline": "volume",
            "chapters": "chapter",
            "chapter_outline": "chapter",
            "characters": "character",
            "story_character": "character",
            "entities": "entity",
            "story_entity": "entity",
            "world_facts": "world_fact",
            "world_fact": "world_fact",
            "foreshadowing_items": "foreshadowing",
            "foreshadowing": "foreshadowing",
            "graph_edges": "graph_edge",
            "graph_edge": "graph_edge",
            "relation": "graph_edge",
            "relations": "graph_edge",
        }
        normalized = mapping.get(normalized, normalized)
        if normalized not in {"volume", "chapter", "character", "entity", "world_fact", "foreshadowing", "graph_edge"}:
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
        if ref_type == "volume":
            return db.query(models.Volume).filter(models.Volume.project_id == project_id, models.Volume.status != "archived").all()
        if ref_type == "chapter":
            return db.query(models.Chapter).filter(models.Chapter.project_id == project_id, models.Chapter.deleted_at.is_(None)).all()
        if ref_type == "character":
            return db.query(models.Character).filter(models.Character.project_id == project_id, models.Character.status != "archived").all()
        if ref_type == "entity":
            return db.query(models.StoryEntity).filter(models.StoryEntity.project_id == project_id, models.StoryEntity.current_status != "archived").all()
        if ref_type == "world_fact":
            return db.query(models.WorldFact).filter(models.WorldFact.project_id == project_id).all()
        if ref_type == "foreshadowing":
            return db.query(models.ForeshadowingItem).filter(models.ForeshadowingItem.project_id == project_id, models.ForeshadowingItem.payoff_status != "abandoned").all()
        if ref_type == "graph_edge":
            return db.query(models.GraphEdge).filter(models.GraphEdge.project_id == project_id).all()
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

    def _chapter_summary(self, chapter: models.Chapter | None) -> dict[str, Any] | None:
        if chapter is None:
            return None
        return {"id": chapter.id, "volume_no": chapter.volume_no, "chapter_no": chapter.chapter_no, "title": chapter.title}

    def _chapter_summary_lookup(self, db: Session, project_id: str) -> dict[str, dict[str, Any]]:
        return {
            chapter.id: self._chapter_summary(chapter)
            for chapter in db.query(models.Chapter).filter(models.Chapter.project_id == project_id).all()
        }

    def _enrich_source_chapter(self, payload: dict[str, Any], chapter_lookup: dict[str, dict[str, Any]]) -> dict[str, Any]:
        source_chapter_id = payload.get("source_chapter_id")
        payload["source_chapter"] = chapter_lookup.get(source_chapter_id) if source_chapter_id else None
        return payload

    def _append_timeline_event(
        self,
        timeline_by_chapter: dict[str, dict[str, Any]],
        unbound: dict[str, list[Any]],
        chapter_id: str | None,
        bucket: str,
        payload: dict[str, Any],
        event: dict[str, Any],
    ) -> None:
        target = timeline_by_chapter.get(chapter_id) if chapter_id else None
        if target is None:
            unbound[bucket].append(payload)
            unbound["events"].append(event)
            return
        target[bucket].append(payload)
        target["events"].append(event)

    def _canon_ref_content(self, ref_type: str, row: Any) -> dict[str, Any]:
        if ref_type == "volume":
            return serialize_volume(row)
        if ref_type == "chapter":
            return serialize_chapter(row)
        if ref_type == "character":
            return serialize_character(row)
        if ref_type == "entity":
            return serialize_story_entity(row)
        if ref_type == "world_fact":
            return serialize_world_fact(row)
        if ref_type == "foreshadowing":
            return serialize_foreshadowing_item(row)
        if ref_type == "graph_edge":
            return serialize_graph_edge(row)
        raise _bad_request("不支持的设定类型", {"ref_type": ref_type})

    def _canon_ref_title(self, ref_type: str, content: dict[str, Any]) -> str:
        if ref_type == "volume":
            return str(content.get("title") or f"第{content.get('volume_no') or ''}卷").strip()
        if ref_type == "chapter":
            return str(content.get("title") or f"第{content.get('chapter_no') or ''}章").strip()
        if ref_type == "world_fact":
            return str(content.get("title") or "未命名世界观事实")
        if ref_type == "foreshadowing":
            return str(content.get("content") or "未命名伏笔")[:48]
        if ref_type == "graph_edge":
            return str(content.get("label") or content.get("edge_type") or "未命名关系")
        return str(content.get("name") or content.get("title") or "未命名设定")

    def _canon_ref_row(self, db: Session, project_id: str, ref_type: str, ref_id: str) -> Any:
        model_by_type = {
            "volume": models.Volume,
            "chapter": models.Chapter,
            "character": models.Character,
            "entity": models.StoryEntity,
            "world_fact": models.WorldFact,
            "foreshadowing": models.ForeshadowingItem,
            "graph_edge": models.GraphEdge,
        }
        model = model_by_type[ref_type]
        row = db.get(model, ref_id)
        if row is None or row.project_id != project_id:
            raise _not_found("设定不存在")
        return row

    def _apply_canon_content(self, row: Any, ref_type: str, content: dict[str, Any]) -> None:
        if ref_type == "volume":
            for field in ("title", "outline", "status", "sort_order"):
                if field in content and hasattr(row, field):
                    setattr(row, field, content[field])
            if "volume_no" in content:
                row.volume_no = int(content["volume_no"])
            return
        if ref_type == "chapter":
            for field in ("title", "outline", "pov_character", "core_event", "conflict", "turn_point", "plot_purpose", "cliffhanger", "status", "sort_order"):
                if field in content and hasattr(row, field):
                    setattr(row, field, content[field])
            if "volume_no" in content:
                row.volume_no = int(content["volume_no"])
            if "chapter_no" in content:
                row.chapter_no = int(content["chapter_no"])
            if "word_target" in content:
                row.word_target = int(content["word_target"])
            if "emotional_beats" in content:
                row.emotional_beats_json = dumps(content["emotional_beats"] or [])
            return
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
            return
        if ref_type == "graph_edge":
            for field in ("edge_type", "label", "importance_score", "confidence", "evidence", "source_chapter_id"):
                if field in content and hasattr(row, field):
                    setattr(row, field, content[field])

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
        graph_edges = db.query(models.GraphEdge).filter(models.GraphEdge.project_id == project_id).count()
        versioned_refs = {
            (row.ref_type, row.ref_id)
            for row in db.query(models.CanonVersion.ref_type, models.CanonVersion.ref_id).filter(models.CanonVersion.project_id == project_id).all()
        }
        official_refs: set[tuple[str, str]] = set()
        official_refs.update(("character", row.id) for row in db.query(models.Character.id).filter(models.Character.project_id == project_id, models.Character.status != "archived").all())
        official_refs.update(("entity", row.id) for row in db.query(models.StoryEntity.id).filter(models.StoryEntity.project_id == project_id, models.StoryEntity.current_status != "archived").all())
        official_refs.update(("world_fact", row.id) for row in db.query(models.WorldFact.id).filter(models.WorldFact.project_id == project_id).all())
        official_refs.update(("foreshadowing", row.id) for row in db.query(models.ForeshadowingItem.id).filter(models.ForeshadowingItem.project_id == project_id, models.ForeshadowingItem.payoff_status != "abandoned").all())
        official_refs.update(("graph_edge", row.id) for row in db.query(models.GraphEdge.id).filter(models.GraphEdge.project_id == project_id).all())
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
                "graph_edges": graph_edges,
            },
            "recommendations": [
                "优先审批候选设定，避免正文生成读取到未确认事实。",
                "低置信度设定建议补充来源章节或标记为待确认。",
                "核心人物和世界规则建议锁定后再进入批量正文生成。",
            ],
        }

    def _create_canon_update_proposals(
        self,
        db: Session,
        project_id: str,
        chapter_id: str | None,
        updates: dict[str, Any],
        *,
        source_job_id: str | None = None,
    ) -> list[dict[str, Any]]:
        chapter_lookup = self._chapter_summary_lookup(db, project_id)
        proposals: list[dict[str, Any]] = []

        def add_proposal(
            target_type: str,
            after: dict[str, Any],
            *,
            target_id: str | None = None,
            operation: str = "create",
            before: dict[str, Any] | None = None,
            confidence: float = 0.8,
            reason: str = "章后设定整理候选",
        ) -> None:
            proposal = self._create_canon_proposal(
                db,
                project_id,
                target_type,
                after,
                target_id=target_id,
                operation=operation,
                before=before,
                source_chapter_id=chapter_id,
                source_job_id=source_job_id,
                source_agent="canon_curator",
                confidence=confidence,
                reason=reason,
            )
            proposals.append(self._enrich_source_chapter(serialize_canon_proposal(proposal), chapter_lookup))

        for item in updates.get("character_updates", []):
            name = str(item.get("name") or "未命名角色")
            existing = db.query(models.Character).filter(models.Character.project_id == project_id, models.Character.name == name).first()
            confidence = float(item.get("confidence") or 0.8)
            if existing:
                before = self._canon_ref_content("character", existing)
                after = dict(before)
                for key, value in item.items():
                    if value not in (None, ""):
                        after[key] = value
                after["last_seen_chapter_id"] = chapter_id
                add_proposal("character", after, target_id=existing.id, operation="update", before=before, confidence=confidence)
            else:
                add_proposal(
                    "character",
                    {
                        "name": name,
                        "role_type": item.get("role_type") or item.get("role") or "supporting",
                        "importance_level": item.get("importance_level") or "medium",
                        "importance_score": int(item.get("importance_score") or 50),
                        "summary": str(item.get("summary") or item.get("profile") or ""),
                        "current_status": item.get("current_status") or "active",
                        "source_chapter_id": chapter_id,
                    },
                    confidence=confidence,
                )

        for item in updates.get("entity_updates", []):
            entity_type = str(item.get("entity_type") or "event")
            name = str(item.get("name") or "未命名实体")
            existing = (
                db.query(models.StoryEntity)
                .filter(models.StoryEntity.project_id == project_id, models.StoryEntity.entity_type == entity_type, models.StoryEntity.name == name)
                .first()
            )
            confidence = float(item.get("confidence") or 0.8)
            if existing:
                before = self._canon_ref_content("entity", existing)
                after = dict(before)
                for key, value in item.items():
                    if value not in (None, ""):
                        after[key] = value
                after["last_seen_chapter_id"] = chapter_id
                add_proposal("entity", after, target_id=existing.id, operation="update", before=before, confidence=confidence)
            else:
                add_proposal(
                    "entity",
                    {
                        "entity_type": entity_type,
                        "name": name,
                        "importance_level": item.get("importance_level") or "medium",
                        "importance_score": int(item.get("importance_score") or 50),
                        "description": str(item.get("description") or item.get("content") or ""),
                        "current_status": item.get("current_status") or "active",
                        "source": "agent",
                        "source_chapter_id": chapter_id,
                    },
                    confidence=confidence,
                )

        for item in updates.get("world_fact_updates", []):
            title = str(item.get("title") or "新世界观事实")
            existing = db.query(models.WorldFact).filter(models.WorldFact.project_id == project_id, models.WorldFact.title == title).first()
            confidence = float(item.get("confidence") or 0.75)
            if existing:
                before = self._canon_ref_content("world_fact", existing)
                after = dict(before)
                for key, value in item.items():
                    if value not in (None, ""):
                        after[key] = value
                after["source_chapter_id"] = chapter_id
                add_proposal("world_fact", after, target_id=existing.id, operation="update", before=before, confidence=confidence)
            else:
                add_proposal(
                    "world_fact",
                    {
                        "category": item.get("category") or "timeline",
                        "title": title,
                        "content": str(item.get("content") or ""),
                        "importance_level": item.get("importance_level") or "medium",
                        "importance_score": int(item.get("importance_score") or 55),
                        "confidence": confidence,
                        "related_entity_ids": list(item.get("related_entity_ids") or []),
                        "source_chapter_id": chapter_id,
                    },
                    confidence=confidence,
                )

        for item in updates.get("relation_updates", []):
            source_label = str(item.get("source_label") or item.get("source") or "未命名关系来源")
            target_label = str(item.get("target_label") or item.get("target") or "未命名关系目标")
            confidence = float(item.get("confidence") or 0.8)
            add_proposal(
                "graph_edge",
                {
                    "source_label": source_label,
                    "target_label": target_label,
                    "source_ref_type": item.get("source_ref_type"),
                    "source_ref_id": item.get("source_ref_id"),
                    "target_ref_type": item.get("target_ref_type"),
                    "target_ref_id": item.get("target_ref_id"),
                    "edge_type": item.get("edge_type") or "related_to",
                    "label": item.get("label") or item.get("edge_type") or "关联",
                    "importance_score": int(item.get("importance_score") or 60),
                    "confidence": confidence,
                    "evidence": str(item.get("evidence") or ""),
                    "source_chapter_id": chapter_id,
                },
                confidence=confidence,
                reason="章后关系图谱候选",
            )

        for item in updates.get("foreshadowing_updates", []):
            content = str(item.get("content") or "").strip()
            if not content:
                continue
            confidence = float(item.get("confidence") or 0.8)
            add_proposal(
                "foreshadowing",
                {
                    "chapter_id": chapter_id,
                    "content": content,
                    "planted_chapter_id": item.get("planted_chapter_id") or chapter_id,
                    "planned_payoff_chapter_id": item.get("planned_payoff_chapter_id"),
                    "actual_payoff_chapter_id": item.get("actual_payoff_chapter_id"),
                    "planned_payoff": str(item.get("planned_payoff") or ""),
                    "payoff_status": item.get("payoff_status") or "planned",
                    "importance_level": item.get("importance_level") or "medium",
                    "importance_score": int(item.get("importance_score") or 50),
                    "related_character_ids": list(item.get("related_character_ids") or []),
                    "related_entity_ids": list(item.get("related_entity_ids") or []),
                    "source": "agent",
                },
                confidence=confidence,
                reason="章后伏笔候选",
            )
        return proposals

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

    def _graph_node_for_relation_endpoint(
        self,
        db: Session,
        project_id: str,
        *,
        ref_type: str | None = None,
        ref_id: str | None = None,
        label: str = "",
    ) -> models.GraphNode:
        normalized_ref_type: str | None = None
        if ref_type and ref_id:
            normalized_ref_type = self._normalize_canon_ref_type(ref_type)
            row = self._canon_ref_row(db, project_id, normalized_ref_type, ref_id)
            content = self._canon_ref_content(normalized_ref_type, row)
            return self._ensure_graph_node(
                db,
                project_id,
                "clue" if normalized_ref_type == "foreshadowing" else normalized_ref_type,
                ref_id,
                self._canon_ref_title(normalized_ref_type, content),
                str(content.get("importance_level") or "medium"),
                int(content.get("importance_score") or 50),
            )
        clean_label = str(label or "未命名节点").strip() or "未命名节点"
        existing_node = db.query(models.GraphNode).filter(models.GraphNode.project_id == project_id, models.GraphNode.label == clean_label).first()
        if existing_node:
            return existing_node
        character = db.query(models.Character).filter(models.Character.project_id == project_id, models.Character.name == clean_label).first()
        if character:
            return self._ensure_graph_node(db, project_id, "character", character.id, character.name, character.importance_level, character.importance_score)
        entity = db.query(models.StoryEntity).filter(models.StoryEntity.project_id == project_id, models.StoryEntity.name == clean_label).first()
        if entity:
            return self._ensure_graph_node(db, project_id, "entity", entity.id, entity.name, entity.importance_level, entity.importance_score)
        fact = db.query(models.WorldFact).filter(models.WorldFact.project_id == project_id, models.WorldFact.title == clean_label).first()
        if fact:
            return self._ensure_graph_node(db, project_id, "world_fact", fact.id, fact.title, fact.importance_level, fact.importance_score)
        ref_key = re.sub(r"[^0-9A-Za-z_\-\u4e00-\u9fff]+", "_", clean_label).strip("_")[:80] or generate_id("concept")
        return self._ensure_graph_node(db, project_id, "concept", f"concept:{ref_key}", clean_label, "medium", 50)

    def _create_graph_edge_from_payload(
        self,
        db: Session,
        project_id: str,
        payload: dict[str, Any],
        *,
        source_chapter_id: str | None = None,
    ) -> models.GraphEdge:
        source_node = self._graph_node_for_relation_endpoint(
            db,
            project_id,
            ref_type=payload.get("source_ref_type"),
            ref_id=payload.get("source_ref_id"),
            label=str(payload.get("source_label") or payload.get("source") or "未命名关系来源"),
        )
        target_node = self._graph_node_for_relation_endpoint(
            db,
            project_id,
            ref_type=payload.get("target_ref_type"),
            ref_id=payload.get("target_ref_id"),
            label=str(payload.get("target_label") or payload.get("target") or "未命名关系目标"),
        )
        return self._ensure_graph_edge(
            db,
            project_id,
            source_node.id,
            target_node.id,
            str(payload.get("edge_type") or "related_to"),
            str(payload.get("label") or payload.get("edge_type") or "关联"),
            int(payload.get("importance_score") or 60),
            confidence=float(payload.get("confidence") or 0.8),
            evidence=str(payload.get("evidence") or ""),
            source_chapter_id=payload.get("source_chapter_id") or source_chapter_id,
        )

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
