from __future__ import annotations

import difflib
import json
from pathlib import Path
import random
import zipfile
from typing import Any, Iterator

from fastapi import HTTPException
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.agents.contracts import NovelStudioState
from app.agents.llm_io import call_agent_json
from app.agents.outline_swarm.service import run_outline_swarm
from app.agents.outline_swarm.swarm import OUTLINE_SWARM_AGENT_NAMES
from app.agents.prompts import AGENT_SPECS_BY_NAME, DEFAULT_AGENT_SPECS, OUTLINE_AGENT_SEQUENCE
from app.agents.workflow import agent_workflow
from app.core.config import LLMProviderResolver, get_settings
from app.core.ids import generate_id
from app.core.json import dumps, loads
from app.db import models
from app.db.models import utcnow
from app.schemas.chapter import PlanChaptersRequest
from app.schemas.studio import (
    AgentPromptUpdateRequest,
    BatchGenerateRequest,
    BranchVersionRequest,
    ChapterChatRequest,
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
from app.services.serializers import (
    isoformat,
    serialize_agent_run,
    serialize_chapter,
    serialize_character,
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
    serialize_world_fact,
)
from app.services.llm_client import llm_client


def _not_found(message: str) -> HTTPException:
    return HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": message})


def _conflict(message: str) -> HTTPException:
    return HTTPException(status_code=409, detail={"code": "CONFLICT", "message": message})


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
        return {"options": CREATION_STAR_OPTIONS}

    def creation_star_draw(self, db: Session, project_id: str, request: CreationStarDrawRequest) -> dict:
        project = self._project(db, project_id)
        job = self._create_job(db, project_id, None, "creation_star_draw", request.model, request.model_dump(), total_steps=1)
        basic = self._normalized_creation_basic(project, request.basic_info)
        draw_id = generate_id("draw")
        rng = random.SystemRandom()
        prompt_snapshot = self._creation_star_prompt_snapshot(request, basic)
        if request.step == "worldview":
            payload: dict[str, Any] = {
                "step": request.step,
                "cards": self._creation_worldview_cards(basic, request.count, request.manual_input, draw_id, rng),
            }
        elif request.step == "protagonist":
            payload = {
                "step": request.step,
                "cards": self._creation_protagonist_cards(
                    basic,
                    request.selected_worldview,
                    request.count,
                    request.manual_input,
                    draw_id,
                    rng,
                ),
            }
        elif request.step == "project_bible":
            project_bible, world_rules = self._creation_bible_and_rules(
                basic,
                request.selected_worldview,
                request.selected_protagonist,
                request.manual_input,
                rng,
            )
            payload = {"step": request.step, "project_bible": project_bible, "world_rules": world_rules, "cards": []}
        elif request.step == "world_rules":
            _, world_rules = self._creation_bible_and_rules(
                basic,
                request.selected_worldview,
                request.selected_protagonist,
                request.manual_input,
                rng,
            )
            payload = {"step": request.step, "world_rules": world_rules, "cards": []}
        elif request.step == "title":
            payload = {
                "step": request.step,
                "cards": self._creation_title_cards(
                    basic,
                    request.selected_worldview,
                    request.selected_protagonist,
                    request.project_bible,
                    request.world_rules,
                    request.count,
                    request.manual_input,
                    draw_id,
                    rng,
                ),
            }
        else:
            raise _bad_request("不支持的创作 Star 步骤", {"step": request.step})
        payload["draw_id"] = draw_id
        payload["prompt_snapshot"] = prompt_snapshot
        payload, llm_meta = call_agent_json(
            llm_client=llm_client,
            agent_name="creation_star",
            role=AGENT_SPECS_BY_NAME["creation_star"].role,
            system_prompt=AGENT_SPECS_BY_NAME["creation_star"].prompt,
            task=f"执行创作 Star 的 {request.step} 抽卡/生成步骤，输出可供用户选择或确认的结构化候选。",
            context={
                "project": serialize_project(project),
                "request": request.model_dump(),
                "basic_info": basic,
                "prompt_snapshot": prompt_snapshot,
                "fallback_output": payload,
            },
            fallback=payload,
            model=request.model,
        )
        payload["draw_id"] = payload.get("draw_id") or draw_id
        payload["prompt_snapshot"] = payload.get("prompt_snapshot") or prompt_snapshot
        payload["_llm"] = llm_meta
        self._record_agent_run(
            db,
            job,
            "creation_star",
            payload,
            {"project": serialize_project(project), "request": request.model_dump(), "prompt_snapshot": prompt_snapshot},
        )
        self._finish_job(db, job, payload)
        db.commit()
        return {"job": serialize_job(job), **payload}

    def creation_star_commit(self, db: Session, project_id: str, request: CreationStarCommitRequest) -> dict:
        project = self._project(db, project_id)
        story_bible = self._story_bible(db, project_id)
        job = self._create_job(db, project_id, None, "creation_star_commit", request.model, request.model_dump(), total_steps=4)
        basic = self._normalized_creation_basic(project, request.basic_info)
        worldview = request.selected_worldview
        protagonist = request.selected_protagonist
        selected_title = request.selected_title
        project_bible = request.project_bible
        world_rules = request.world_rules

        project.title = str(selected_title.get("title") or project.title)
        project.genre = basic["genre"]
        project.target_reader = basic["target_reader"]
        project.target_words = int(basic.get("target_words") or project.target_words or 0)
        project.initial_idea = basic.get("initial_idea", project.initial_idea)
        project.style_guide = basic.get("style", project.style_guide)
        project.premise = self._join_nonempty(
            [
                str(project_bible.get("核心命题", "")),
                str(project_bible.get("核心矛盾", "")),
                str(worldview.get("description", "")),
            ],
            "；",
        ) or project.premise

        story_bible.version += 1
        story_bible.world_setting = self._join_nonempty(
            [
                str(worldview.get("title", "")),
                str(worldview.get("description", "")),
                "力量体系：" + "、".join(self._as_str_list(world_rules.get("力量体系"))),
                "社会结构：" + "、".join(self._as_str_list(world_rules.get("社会结构"))),
            ],
            "\n",
        )
        story_bible.main_conflict = str(project_bible.get("核心矛盾", story_bible.main_conflict))
        story_bible.themes_json = dumps(self._as_str_list(project_bible.get("主线关键词")))
        story_bible.style_guide = basic.get("style", story_bible.style_guide)
        story_bible.forbidden_elements_json = dumps(self._as_str_list(world_rules.get("禁忌规则")))
        story_bible.continuity_rules_json = dumps(self._as_str_list(world_rules.get("不可违反设定")))

        character = self._upsert_creation_protagonist(db, project_id, protagonist, basic, worldview)
        entities = self._upsert_creation_entities(db, project_id, worldview, world_rules)
        facts = self._upsert_creation_world_facts(db, project_id, project_bible, world_rules, worldview)
        db.flush()
        self._link_creation_graph(db, project_id, character, entities, facts, worldview)

        output = {
            "basic_info": basic,
            "selected_worldview": worldview,
            "selected_protagonist": protagonist,
            "selected_title": selected_title,
            "project_bible": project_bible,
            "world_rules": world_rules,
        }
        self._record_agent_run(db, job, "creation_star", output, {"project": serialize_project(project)})
        version = self._snapshot(
            db,
            project_id,
            None,
            job.id,
            "creation_star",
            "creation_star_setup",
            dumps(output),
            request.user_note or "创作 Star 确认入库",
        )
        result = {
            "project": serialize_project(project),
            "story_bible": serialize_story_bible(story_bible),
            "character": serialize_character(character),
            "entities": [serialize_story_entity(item) for item in entities],
            "world_facts": [serialize_world_fact(item) for item in facts],
            "version": serialize_version_snapshot(version),
        }
        self._finish_job(db, job, result)
        db.commit()
        return {"job": serialize_job(job), **result}

    def generate_story_bible(self, db: Session, project_id: str, request: GenerateStoryBibleRequest) -> dict:
        project = self._project(db, project_id)
        story_bible = self._story_bible(db, project_id)
        job = self._create_job(db, project_id, None, "generate_story_bible", request.model, {"initial_idea": request.initial_idea})
        state = self._state_from_project(db, project, job.id)
        state.requested_model = request.model
        state.initial_idea = request.initial_idea or project.initial_idea or project.premise
        result = agent_workflow.run_initialization(state)
        self._record_agent_run(db, job, "chief_architect", self._with_llm_meta(result.story_bible, result, "chief_architect"), {"project": serialize_project(project)})
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
        self._finish_job(db, job, {"story_bible": serialize_story_bible(story_bible), "canon_updates": result.canon_updates})
        db.commit()
        return {"job": serialize_job(job), "story_bible": serialize_story_bible(story_bible), "canon_updates": result.canon_updates}

    def plan_chapters(self, db: Session, project_id: str, request: PlanChaptersRequest) -> dict:
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
        )
        state = self._state_from_project(db, project, job.id)
        state.requested_model = request.model
        state.current_chapter = request.start_chapter_no
        state.target_chapters = request.chapter_count
        result = agent_workflow.run_chapter_plan(state)
        outline_plan = self._build_long_novel_outline_plan(db, project, request, state)
        outline_plan = self._run_outline_agents_with_llm(project, request, outline_plan)
        outline_plan = self._attach_outline_swarm_plan(db, project, request, outline_plan)
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
        job = self._create_job(db, project_id, chapter_id, "draft_chapter", request.model, request.model_dump(), idem, total_steps=10)
        state = self._state_from_project(db, project, job.id)
        state.requested_model = request.model
        state.current_chapter = chapter.chapter_no
        state.current_chapter_outline = serialize_chapter(chapter)
        state.canon_context = self.build_canon_context(db, project_id, chapter_id)["canon_context"]
        result = agent_workflow.run_chapter_draft(state)
        for agent_name, payload in [
            ("canon_context", {"canon_context": result.canon_context}),
            ("plot_narrator", {"plot_draft": result.plot_draft}),
            ("dialogue_writer", {"dialogue_draft": result.dialogue_draft}),
            ("environment_writer", {"environment_draft": result.environment_draft}),
            ("integrator", {"integrated_draft": result.integrated_draft, "chapter_summary": result.chapter_summary}),
            ("reviewer", {"review_notes": result.review_notes}),
            ("fact_checker", result.fact_check_report),
            ("quality_gate", result.quality_gate),
            ("style_unifier", {"style_polished_text": result.style_polished_text, "final_chapter_text": result.final_chapter_text}),
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
            metadata_json=dumps({"review_notes": result.review_notes, "fact_check_report": result.fact_check_report, "canon_updates": result.canon_updates}),
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

    def list_agents(self, db: Session) -> dict:
        templates = {template.agent_name: template for template in db.query(models.PromptTemplate).filter(models.PromptTemplate.is_active == 1).all()}
        agents = []
        for spec in DEFAULT_AGENT_SPECS:
            template = templates.get(spec.name)
            agents.append({"name": spec.name, "role": spec.role, "order": spec.order, "prompt": template.prompt if template else spec.prompt})
        return {"agents": agents}

    def list_workflows(self) -> dict:
        agent_descriptions = {spec.name: spec.role for spec in DEFAULT_AGENT_SPECS}

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
                "id": "initialization",
                "label": "初始化项目",
                "nodes": [
                    agent_node("chief_architect", "总策划 Agent", "chief_architect", ["title", "genre", "initial_idea"], ["story_bible", "characters", "outline"], 1),
                    agent_node("canon_curator_init", "设定整理 Agent", "canon_curator", ["story_bible", "characters"], ["graph_nodes", "world_facts"], 2),
                ],
                "edges": [{"source": "chief_architect", "target": "canon_curator_init", "label": "抽取设定"}],
            },
            {
                "id": "outline_generation",
                "label": "长篇大纲推演",
                "nodes": outline_nodes,
                "edges": [
                    {"source": left, "target": right, "label": "写回 StoryState"}
                    for left, right in zip(OUTLINE_AGENT_SEQUENCE, OUTLINE_AGENT_SEQUENCE[1:])
                ],
            },
            {
                "id": "chapter_planning",
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
        return {"agent": {"name": spec.name, "role": spec.role, "order": spec.order, "prompt": template.prompt if template else spec.prompt}}

    def update_agent_prompt(self, db: Session, agent_name: str, request: AgentPromptUpdateRequest) -> dict:
        if agent_name not in AGENT_SPECS_BY_NAME:
            raise _not_found("Agent 不存在")
        template = models.PromptTemplate(
            id=generate_id("tpl"),
            agent_name=agent_name,
            template_name=request.template_name,
            prompt=request.prompt,
            is_active=0 if request.temporary else 1,
            metadata_json=dumps({"temporary": request.temporary}),
        )
        if not request.temporary:
            db.query(models.PromptTemplate).filter(models.PromptTemplate.agent_name == agent_name).update({"is_active": 0})
        db.add(template)
        db.commit()
        return {"agent": self.get_agent(db, agent_name)["agent"], "template": serialize_prompt_template(template)}

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
        )
        db.add(row)
        db.flush()
        self._ensure_graph_node(db, project_id, "character", row.id, row.name, row.importance_level, row.importance_score)
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
        for field, value in updates.items():
            if value is None:
                continue
            if field in {"aliases", "goals", "motivations", "secrets", "abilities", "weaknesses", "related_entity_ids", "related_character_ids"}:
                setattr(row, f"{field}_json", dumps(value))
            elif hasattr(row, field):
                setattr(row, field, value)
        if "role_type" in updates and row.role_type:
            row.role = row.role_type
        self._ensure_graph_node(db, project_id, "character", row.id, row.name, row.importance_level, row.importance_score)
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
        )
        db.add(row)
        db.flush()
        self._ensure_graph_node(db, project_id, "entity", row.id, row.name, row.importance_level, row.importance_score)
        db.commit()
        db.refresh(row)
        return {"entity": serialize_story_entity(row)}

    def update_entity(self, db: Session, project_id: str, entity_id: str, request: UpdateEntityRequest) -> dict:
        row = db.get(models.StoryEntity, entity_id)
        if row is None or row.project_id != project_id:
            raise _not_found("剧情实体不存在")
        for field, value in request.model_dump(exclude_unset=True).items():
            if value is not None and hasattr(row, field):
                setattr(row, field, value)
        self._ensure_graph_node(db, project_id, "entity", row.id, row.name, row.importance_level, row.importance_score)
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
            related_entity_ids_json=dumps(request.related_entity_ids),
        )
        db.add(row)
        db.flush()
        self._ensure_graph_node(db, project_id, "world_fact", row.id, row.title, row.importance_level, row.importance_score)
        db.commit()
        db.refresh(row)
        return {"world_fact": serialize_world_fact(row)}

    def update_world_fact(self, db: Session, project_id: str, fact_id: str, request: UpdateWorldFactRequest) -> dict:
        row = db.get(models.WorldFact, fact_id)
        if row is None or row.project_id != project_id:
            raise _not_found("世界观事实不存在")
        for field, value in request.model_dump(exclude_unset=True).items():
            if value is None:
                continue
            if field == "related_entity_ids":
                row.related_entity_ids_json = dumps(value)
            elif hasattr(row, field):
                setattr(row, field, value)
        self._ensure_graph_node(db, project_id, "world_fact", row.id, row.title, row.importance_level, row.importance_score)
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
        db.commit()
        db.refresh(row)
        return {"foreshadowing_item": serialize_foreshadowing_item(row)}

    def update_foreshadowing(self, db: Session, project_id: str, item_id: str, request: UpdateForeshadowingRequest) -> dict:
        row = db.get(models.ForeshadowingItem, item_id)
        if row is None or row.project_id != project_id:
            raise _not_found("伏笔不存在")
        for field, value in request.model_dump(exclude_unset=True).items():
            if value is None:
                continue
            if field in {"related_character_ids", "related_entity_ids"}:
                setattr(row, f"{field}_json", dumps(value))
            elif hasattr(row, field):
                setattr(row, field, value)
        self._sync_foreshadowing_graph(db, row)
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

    def _creation_star_prompt_snapshot(self, request: CreationStarDrawRequest, basic: dict[str, Any]) -> dict[str, Any]:
        context_summary = self._creation_star_context_summary(request, basic)
        step_prompts = {
            "worldview": "生成世界观抽卡：必须参考基本信息、标签、目标读者、初始想法和额外约束，输出差异明显的世界观卡。",
            "protagonist": "生成主角人设抽卡：必须读取已选世界观，主角的身份、欲望、能力和伤口都要服务该世界观的核心规则与冲突。",
            "project_bible": "生成项目总设定表和世界观规则表：必须读取已选世界观与主角人设，形成可长期约束正文生成的正式设定候选。",
            "world_rules": "重抽世界观规则表：必须读取基本信息、已选世界观和主角人设，只调整规则表，不破坏已确认的主线方向。",
            "title": "生成书名抽卡：必须读取基本信息、已选世界观、已选主角、项目总设定表和世界观规则表，提供多种平台感书名方向。",
        }
        return {
            "agent_name": "creation_star",
            "system_prompt": AGENT_SPECS_BY_NAME["creation_star"].prompt,
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
        cards = []
        draw_key = draw_id.rsplit("_", 1)[-1][-6:]
        for index, (title, description) in enumerate(selected_seeds):
            tag_a = self._pick(tags, index + tag_offset, "成长")
            tag_b = self._pick(tags, index + tag_offset + 1, subgenre)
            pressure = self._pick(self._random_cycle(pressures, count, rng), index, "资源垄断")
            tone = self._pick(self._random_cycle(tones, count, rng), index, "热血反抗")
            idea_hint = self._short(basic.get("initial_idea"), 42)
            cards.append(
                {
                    "id": f"worldview_{draw_key}_{index + 1}",
                    "title": title if not manual_input else f"{title}：{manual_input[:18]}",
                    "description": f"{description} 类型基底：{basic.get('channel')}/{genre}/{subgenre}；核心爽点围绕“{tag_a}”展开，主要社会压力是{pressure}。{('初始脑洞：' + idea_hint + '。') if idea_hint else ''}",
                    "tags": list(dict.fromkeys([tag_a, tag_b, genre, subgenre]))[:5],
                    "selling_point": f"把{genre}的熟悉期待、{tone}的阅读节奏和{tag_a}的持续反馈绑定到可升级的社会规则里。",
                    "conflict_hook": f"主角越接近上层资源，越会发现{pressure}本身就是阻碍。",
                    "risk": f"需要尽早明确{tag_a}的代价和边界，避免只靠设定名词堆砌。",
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
            cards.append(
                {
                    "id": f"protagonist_{draw_key}_{index + 1}",
                    "name": name,
                    "identity": identity,
                    "summary": f"{name}生在“{worldview_title}”的夹缝中，开局资源不足但能看见旧秩序的破绽；人物卖点要回应“{tag}”。",
                    "long_term_goal": f"{goal}，并正面撞上“{worldview_hook[:36]}”。",
                    "inner_wound": wound,
                    "ability": ability + "。",
                    "weakness": "不愿求助，容易把所有代价压到自己身上。",
                    "secret": "与世界观核心旧案存在未公开关联。",
                    "character_arc": f"从被“{worldview_title}”筛掉的人，成长为重新定义规则的人。",
                    "relationship_hook": relationship_hook + "。",
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

    def _run_outline_agents_with_llm(self, project: models.Project, request: PlanChaptersRequest, outline_plan: dict[str, Any]) -> dict[str, Any]:
        previous_outputs: list[dict[str, Any]] = []
        agent_outputs = dict(outline_plan.get("agent_outputs", {}))
        updated_outputs: dict[str, dict[str, Any]] = {}
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
        for agent_name in OUTLINE_AGENT_SEQUENCE:
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
                    "project": serialize_project(project),
                    "request": request.model_dump(),
                    "structured_prompt": outline_plan.get("structured_prompt", {}),
                    "story_state": outline_plan.get("story_state", {}),
                    "previous_agent_outputs": previous_outputs,
                    "fallback_output": fallback,
                },
                fallback=fallback,
                model=request.model,
            )
            payload["_llm"] = meta
            updated_outputs[agent_name] = payload
            previous_outputs.append({"agent_name": agent_name, "output": payload})
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
    ) -> dict[str, Any]:
        story_bible = db.query(models.StoryBible).filter(models.StoryBible.project_id == project.id).first()
        characters = db.query(models.Character).filter(models.Character.project_id == project.id).order_by(models.Character.importance_score.desc()).limit(8).all()
        entities = db.query(models.StoryEntity).filter(models.StoryEntity.project_id == project.id).order_by(models.StoryEntity.importance_score.desc()).limit(8).all()
        world_facts = db.query(models.WorldFact).filter(models.WorldFact.project_id == project.id).order_by(models.WorldFact.importance_score.desc()).limit(10).all()
        parameters = outline_plan.get("parameters", {})
        volume_target = int(request.volume_count or parameters.get("volume_count") or 1)
        chapter_target = int(request.chapter_count or parameters.get("chapters_per_volume") or 10)
        seed = {
            "title": project.title,
            "genre": project.genre,
            "target_reader": project.target_reader,
            "premise": project.premise,
            "one_sentence_story": project.premise,
            "worldview": story_bible.world_setting if story_bible and story_bible.world_setting else project.premise,
            "style": project.style_guide or (story_bible.style_guide if story_bible else ""),
            "target_length": f"{parameters.get('target_words', project.target_words)}字，{volume_target}卷，本次推演{chapter_target}章",
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
        swarm_result = run_outline_swarm(
            {
                "project_id": project.id,
                "seed": seed,
                "volume_target": volume_target,
                "chapter_target": chapter_target,
                "model": request.model,
                "max_iterations": 18,
            }
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
        for agent_name in OUTLINE_SWARM_AGENT_NAMES:
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

    def _create_job(self, db: Session, project_id: str, chapter_id: str | None, job_type: str, requested_model: str | None, request_payload: dict, idempotency_key: str | None = None, total_steps: int = 1) -> models.GenerationJob:
        provider = LLMProviderResolver(get_settings()).resolve(requested_model)
        job = models.GenerationJob(
            id=generate_id("job"),
            project_id=project_id,
            chapter_id=chapter_id,
            job_type=job_type,
            status="running",
            run_id=generate_id("run"),
            idempotency_key=idempotency_key or f"{job_type}:{project_id}:{chapter_id or 'project'}:{generate_id('idem')}",
            model=provider.model,
            request_json=dumps({**request_payload, "provider": provider.provider, "has_api_key": bool(provider.api_key)}),
            progress_json=dumps({"current_step": "running", "total_steps": total_steps, "completed_steps": 0, "message": "工作流正在执行"}),
            current_agent="",
            started_at=utcnow(),
            heartbeat_at=utcnow(),
        )
        db.add(job)
        db.flush()
        return job

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
            chapter.outline = item.get("outline", "")
            chapter.pov_character = item.get("pov_character", "")
            chapter.core_event = item.get("core_event", "")
            chapter.conflict = item.get("conflict", "")
            chapter.turn_point = item.get("turn_point", "")
            chapter.emotional_beats_json = dumps(item.get("emotional_beats", []))
            chapter.plot_purpose = item.get("plot_purpose", "")
            chapter.cliffhanger = item.get("cliffhanger", "")
            chapter.status = "planned"
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
            row.outline = dumps(
                {
                    "本卷主角提升目标": item.get("本卷主角提升目标", {}),
                    "剧情多轨道架构": item.get("剧情多轨道架构", {}),
                    "50章高密度剧情流水线执行协议": item.get("50章高密度剧情流水线执行协议", []),
                    "卷末大钩子": item.get("卷末大钩子", ""),
                    "全卷逻辑审计": item.get("全卷逻辑审计", {}),
                }
            )

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

    def _persist_canon_updates(self, db: Session, project_id: str, chapter_id: str | None, updates: dict[str, Any]) -> None:
        for item in updates.get("character_updates", []):
            name = item.get("name", "未命名角色")
            row = db.query(models.Character).filter(models.Character.project_id == project_id, models.Character.name == name).first()
            if row:
                row.updated_reason = item.get("updated_reason", row.updated_reason)
                row.last_seen_chapter_id = chapter_id
        for item in updates.get("entity_updates", []):
            entity = self._upsert_entity(db, project_id, item.get("entity_type", "event"), item.get("name", "未命名实体"), item.get("importance_score", 50), chapter_id)
            self._ensure_graph_node(db, project_id, "entity", entity.id, entity.name, entity.importance_level, entity.importance_score)
        for item in updates.get("world_fact_updates", []):
            fact = self._upsert_world_fact(db, project_id, item.get("category", "timeline"), item.get("title", "新世界观事实"), item.get("content", ""), "medium", item.get("importance_score", 55), item.get("confidence", 0.75), chapter_id)
            self._ensure_graph_node(db, project_id, "world_fact", fact.id, fact.title, fact.importance_level, fact.importance_score)

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
                path.write_text("%PDF-1.4\n% Novel Agent Studio text export\n" + content, encoding="utf-8")
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
