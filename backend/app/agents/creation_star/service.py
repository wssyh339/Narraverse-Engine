from __future__ import annotations

import random
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.agents.creation_star.state import CreationStarState
from app.agents.llm_io import call_agent_json
from app.agents.prompts import AGENT_SPECS_BY_NAME
from app.core.ids import generate_id
from app.core.json import dumps
from app.schemas.studio import CreationStarCommitRequest, CreationStarDrawRequest
from app.services.llm_client import llm_client
from app.services.serializers import (
    serialize_character,
    serialize_job,
    serialize_project,
    serialize_story_bible,
    serialize_story_entity,
    serialize_version_snapshot,
    serialize_world_fact,
)


def _bad_request(message: str, details: dict[str, Any] | None = None) -> HTTPException:
    return HTTPException(status_code=400, detail={"code": "VALIDATION_ERROR", "message": message, "details": details or {}})


def build_creation_star_state(project_id: str, current_step: str, previous_steps: dict[str, Any] | None = None) -> CreationStarState:
    return CreationStarState(project_id=project_id, current_step=current_step, previous_steps=previous_steps or {})


class CreationStarAgentService:
    def options(self, options: dict[str, Any]) -> dict[str, Any]:
        return {"options": options}

    def draw(self, studio: Any, db: Session, project_id: str, request: CreationStarDrawRequest, llm_client_instance: Any | None = None) -> dict[str, Any]:
        project = studio._project(db, project_id)
        model_agent = "creation_star"
        if request.step == "worldview":
            model_agent = studio._creation_worldview_agent_name()
        elif request.step == "protagonist":
            model_agent = studio._creation_protagonist_agent_name()
        elif request.step == "title":
            model_agent = studio._creation_title_packaging_agent_name()
        if hasattr(studio, "_configured_creation_star_model"):
            model = studio._configured_creation_star_model(db, model_agent, request.model)
        else:
            model = studio._configured_model_for_agent(db, "creation_star_session", model_agent, request.model)
            if model is None and request.model is None and model_agent != "creation_star":
                model = studio._configured_model_for_agent(db, "creation_star_session", "creation_star", None)
        job = studio._create_job(db, project_id, None, "creation_star_draw", model, request.model_dump(), total_steps=1)
        basic = studio._normalized_creation_basic(project, request.basic_info)
        draw_id = generate_id("draw")
        rng = random.SystemRandom()
        prompt_snapshot = studio._creation_star_prompt_snapshot(request, basic)
        if request.step == "worldview":
            payload: dict[str, Any] = {
                "step": request.step,
                "cards": studio._creation_worldview_cards(basic, request.count, request.manual_input, draw_id, rng),
            }
        elif request.step == "protagonist":
            payload = {
                "step": request.step,
                "cards": studio._creation_protagonist_cards(
                    basic,
                    request.selected_worldview,
                    request.count,
                    request.manual_input,
                    draw_id,
                    rng,
                ),
            }
        elif request.step == "project_bible":
            project_bible, world_rules = studio._creation_bible_and_rules(
                basic,
                request.selected_worldview,
                request.selected_protagonist,
                request.manual_input,
                rng,
            )
            payload = {"step": request.step, "project_bible": project_bible, "world_rules": world_rules, "cards": []}
        elif request.step == "world_rules":
            _, world_rules = studio._creation_bible_and_rules(
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
                "cards": studio._creation_title_cards(
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
        if request.step == "worldview":
            agent_name = studio._creation_worldview_agent_name()
            role = "世界观抽卡 Agent"
            system_prompt = studio._creation_worldview_system_prompt()
            task = "执行创作 Star 世界观抽卡，只输出候选世界观和冲突发动机种子；不要生成核心矛盾系统或小说宪法。"
        elif request.step == "protagonist":
            agent_name = studio._creation_protagonist_agent_name()
            role = "主角人设抽卡 Agent"
            system_prompt = studio._creation_protagonist_system_prompt()
            task = "执行创作 Star 主角人设抽卡，只输出候选主角和主角侧 conflict_seed；不要生成核心矛盾系统或小说宪法。"
        elif request.step == "title":
            agent_name = studio._creation_title_packaging_agent_name()
            role = "书名与包装抽卡 Agent"
            system_prompt = studio._creation_title_packaging_system_prompt()
            task = "执行创作 Star 书名与包装抽卡，只输出候选标题、广告句、核心卖点、读者期待、平台风格和风险提示；不要生成核心矛盾系统或小说宪法。"
        else:
            agent_name = "creation_star"
            role = AGENT_SPECS_BY_NAME["creation_star"].role
            system_prompt = AGENT_SPECS_BY_NAME["creation_star"].prompt
            task = f"执行创作 Star 的 {request.step} 抽卡/生成步骤，输出可供用户选择或确认的结构化候选。"
        payload, llm_meta = call_agent_json(
            llm_client=llm_client_instance or llm_client,
            agent_name=agent_name,
            role=role,
            system_prompt=system_prompt,
            task=task,
            context={
                "project": serialize_project(project),
                "request": request.model_dump(),
                "basic_info": basic,
                "prompt_snapshot": prompt_snapshot,
                "fallback_output": payload,
            },
            fallback=payload,
            model=model,
        )
        if request.step == "worldview":
            payload["cards"] = studio._normalize_creation_worldview_cards(payload.get("cards") if isinstance(payload.get("cards"), list) else [])
        if request.step == "protagonist":
            payload["cards"] = studio._normalize_creation_protagonist_cards(payload.get("cards") if isinstance(payload.get("cards"), list) else [])
        if request.step == "title":
            payload["cards"] = studio._normalize_creation_title_packaging_cards(payload.get("cards") if isinstance(payload.get("cards"), list) else [])
        payload["draw_id"] = payload.get("draw_id") or draw_id
        payload["prompt_snapshot"] = payload.get("prompt_snapshot") or prompt_snapshot
        payload["_llm"] = llm_meta
        studio._record_agent_run(
            db,
            job,
            agent_name,
            payload,
            {"project": serialize_project(project), "request": request.model_dump(), "prompt_snapshot": prompt_snapshot},
        )
        studio._finish_job(db, job, payload)
        db.commit()
        return {"job": serialize_job(job), **payload}

    def commit(self, studio: Any, db: Session, project_id: str, request: CreationStarCommitRequest) -> dict[str, Any]:
        project = studio._project(db, project_id)
        story_bible = studio._story_bible(db, project_id)
        job = studio._create_job(db, project_id, None, "creation_star_commit", request.model, request.model_dump(), total_steps=4)
        basic = studio._normalized_creation_basic(project, request.basic_info)
        worldview = request.selected_worldview
        protagonist = request.selected_protagonist
        selected_title = request.selected_title
        project_bible = request.project_bible
        world_rules = request.world_rules

        project.title = str(selected_title.get("title") or project.title)
        project.genre = basic["genre"]
        project.target_reader = basic["target_reader"]
        project.target_words = int(basic.get("target_words") or project.target_words or 0)
        project.planned_chapter_count = int(basic.get("chapter_count") or basic.get("planned_chapter_count") or project.planned_chapter_count)
        project.planned_volume_count = int(basic.get("volume_count") or project.planned_volume_count or 1)
        project.chapters_per_volume = int(basic.get("chapters_per_volume") or project.chapters_per_volume or 1)
        project.chapter_word_target = int(basic.get("chapter_word_target") or project.chapter_word_target)
        project.chapter_word_min = int(basic.get("chapter_word_min") or project.chapter_word_min or project.chapter_word_target)
        project.chapter_word_max = int(basic.get("chapter_word_max") or project.chapter_word_max or project.chapter_word_target)
        project.initial_idea = basic.get("initial_idea", project.initial_idea)
        project.style_guide = basic.get("style", project.style_guide)
        project.premise = studio._join_nonempty(
            [
                str(project_bible.get("核心命题", "")),
                str(project_bible.get("核心矛盾", "")),
                str(worldview.get("description", "")),
            ],
            "；",
        ) or project.premise

        story_bible.version += 1
        story_bible.world_setting = studio._join_nonempty(
            [
                str(worldview.get("title", "")),
                str(worldview.get("description", "")),
                "力量体系：" + "、".join(studio._as_str_list(world_rules.get("力量体系"))),
                "社会结构：" + "、".join(studio._as_str_list(world_rules.get("社会结构"))),
            ],
            "\n",
        )
        story_bible.main_conflict = str(project_bible.get("核心矛盾", story_bible.main_conflict))
        story_bible.themes_json = dumps(studio._as_str_list(project_bible.get("主线关键词")))
        story_bible.style_guide = basic.get("style", story_bible.style_guide)
        story_bible.forbidden_elements_json = dumps(studio._as_str_list(world_rules.get("禁忌规则")))
        story_bible.continuity_rules_json = dumps(studio._as_str_list(world_rules.get("不可违反设定")))

        character = studio._upsert_creation_protagonist(db, project_id, protagonist, basic, worldview)
        entities = studio._upsert_creation_entities(db, project_id, worldview, world_rules)
        facts = studio._upsert_creation_world_facts(db, project_id, project_bible, world_rules, worldview)
        db.flush()
        studio._link_creation_graph(db, project_id, character, entities, facts, worldview)

        output = {
            "basic_info": basic,
            "selected_worldview": worldview,
            "selected_protagonist": protagonist,
            "selected_title": selected_title,
            "project_bible": project_bible,
            "world_rules": world_rules,
        }
        studio._record_agent_run(db, job, "creation_star", output, {"project": serialize_project(project)})
        version = studio._snapshot(
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
        studio._finish_job(db, job, result)
        db.commit()
        return {"job": serialize_job(job), **result}


creation_star_agent_service = CreationStarAgentService()

__all__ = ["CreationStarAgentService", "creation_star_agent_service", "build_creation_star_state"]
