import os
from pathlib import Path
import json
from datetime import timedelta
from types import SimpleNamespace

os.environ["DATABASE_URL"] = "sqlite:///./data/test_novel_agent.db"
os.environ["JOB_ARTIFACT_DIR"] = "backend/artifacts/test-runs"

import pytest
from fastapi.testclient import TestClient

from app.agents.contracts import NovelStudioState
from app.agents.workflow import agent_workflow
from app.agents.chapter_writing.workflow import agent_workflow as chapter_agent_workflow
from app.agents.chapter_writing.workflow import _length_requirements
import app.agents.workflow as workflow_module
import app.services.studio_service as studio_service_module
from app.db import models
from app.db.session import Base, engine, SessionLocal
from app.main import app
from app.schemas.studio import DraftChapterRequest
from app.services.serializers import serialize_chapter
from app.services.studio_service import studio_service


def reset_database() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def assert_success_envelope(payload: dict) -> None:
    assert payload["success"] is True
    assert payload["error"] is None
    assert isinstance(payload["data"], dict)
    assert payload["request_id"].startswith("req_")
    assert payload["timestamp"].endswith("Z")


def test_chapter_length_requirements_cap_project_minimum_at_explicit_chapter_target() -> None:
    requirements = _length_requirements(
        NovelStudioState(
            title="短章覆盖",
            target_words=12000,
            target_chapters=10,
            chapter_word_min=1200,
            chapter_word_max=1600,
            current_chapter=1,
            current_chapter_outline={"chapter_no": 1, "title": "第1章：短目标", "word_target": 400},
        )
    )

    assert requirements["chapter_word_target"] == 400
    assert requirements["minimum_acceptable_words"] == 400


def test_create_project_returns_project_and_story_bible() -> None:
    reset_database()
    client = TestClient(app)

    response = client.post(
        "/api/v1/projects",
        json={
            "title": "星海遗民",
            "genre": "科幻",
            "target_reader": "喜欢群像、文明冲突和长期伏笔的中文网文读者",
            "premise": "一名失忆舰长在废弃星门中醒来，发现自己可能是旧帝国覆灭的关键责任人。",
            "style_guide": "第三人称有限视角，节奏偏紧，避免过度解释设定。",
            "language": "zh-CN",
            "planned_chapter_count": 80,
            "chapter_word_target": 3000,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert_success_envelope(payload)
    project = payload["data"]["project"]
    story_bible = payload["data"]["story_bible"]
    assert project["id"].startswith("prj_")
    assert project["status"] == "draft"
    assert project["title"] == "星海遗民"
    assert story_bible["id"].startswith("bib_")
    assert story_bible["project_id"] == project["id"]
    assert story_bible["version"] == 1
    assert story_bible["themes"] == []


def test_update_story_bible_increments_version_and_returns_full_fields() -> None:
    reset_database()
    client = TestClient(app)
    created = client.post(
        "/api/v1/projects",
        json={
            "title": "雾港来信",
            "genre": "悬疑",
            "target_reader": "喜欢慢热调查和人物秘密的读者",
            "premise": "记者收到一封来自十年前死者的信。",
            "style_guide": "",
            "language": "zh-CN",
            "planned_chapter_count": 40,
            "chapter_word_target": 2500,
        },
    ).json()
    project_id = created["data"]["project"]["id"]

    response = client.put(
        f"/api/v1/projects/{project_id}/story-bible",
        json={
            "world_setting": "海港城市长期被旧案阴影笼罩。",
            "main_conflict": "主角必须查出信件来源，同时保护关键证人。",
            "themes": ["记忆", "愧疚", "真相"],
            "style_guide": "冷静、克制，避免过度煽情。",
            "narrative_pov": "third_person_limited",
            "forbidden_elements": ["无铺垫凶手", "梦境解释一切"],
            "continuity_rules": ["证据链必须可回溯。"],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert_success_envelope(payload)
    story_bible = payload["data"]["story_bible"]
    assert story_bible["project_id"] == project_id
    assert story_bible["version"] == 2
    assert story_bible["themes"] == ["记忆", "愧疚", "真相"]
    assert story_bible["forbidden_elements"] == ["无铺垫凶手", "梦境解释一切"]
    assert story_bible["continuity_rules"] == ["证据链必须可回溯。"]


def test_legacy_outline_generation_endpoints_are_removed() -> None:
    reset_database()
    client = TestClient(app)
    created = client.post(
        "/api/projects",
        json={
            "title": "大纲解耦测试",
            "genre": "都市脑洞",
            "target_reader": "喜欢反差爽点和长线伏笔的读者",
            "premise": "主角用荒诞方式击穿严肃规则。",
            "style_guide": "强反差，强钩子。",
            "language": "zh-CN",
            "planned_chapter_count": 20,
            "chapter_word_target": 2000,
        },
    ).json()
    project_id = created["data"]["project"]["id"]
    for path in [
        "/chapters/plan",
        "/outline/book/generate",
        "/outline/book/commit",
        "/outline/chapters/batch-generate",
        "/outline/chapters/commit",
    ]:
        response = client.post(f"/api/projects/{project_id}{path}", json={})
        assert response.status_code in {404, 405}


def test_update_chapter_accepts_debate_outline_specific_fields() -> None:
    reset_database()
    client = TestClient(app)
    created = client.post(
        "/api/projects",
        json={
            "title": "章纲字段清洗",
            "genre": "都市修真",
            "target_reader": "喜欢技术流爽点的读者",
            "premise": "底层药企助理发现废弃药物能撬开修行垄断。",
            "style_guide": "快节奏，强因果。",
            "language": "zh-CN",
            "planned_chapter_count": 20,
            "chapter_word_target": 2500,
        },
    ).json()
    project_id = created["data"]["project"]["id"]
    db = SessionLocal()
    try:
        chapter = models.Chapter(
            id="outline_chapter_1",
            project_id=project_id,
            volume_no=1,
            chapter_no=1,
            title="第1章：旧章纲",
            outline="旧章纲",
            status="planned",
            word_target=2500,
            sort_order=1,
        )
        db.add(chapter)
        db.commit()
    finally:
        db.close()

    response = client.put(
        f"/api/projects/{project_id}/chapters/outline_chapter_1",
        json={
            "conflict": "是否上报异常数据，还是私自保留样品？",
            "crisis": "陆辰必须在合规上报和违规保留之间做不可逆选择。",
            "climax": "陆辰关闭自动上报流程并藏起样品。",
            "outcome": "陆辰获得秘密，也背上被公司追查的风险。",
            "chapter_hook": "白鼠眼中浮现金色经脉纹路。",
            "cliffhanger": "白鼠眼中浮现金色经脉纹路。",
        },
    )

    assert response.status_code == 200
    chapter = response.json()["data"]["chapter"]
    assert chapter["crisis"] == "陆辰必须在合规上报和违规保留之间做不可逆选择。"
    assert chapter["climax"] == "陆辰关闭自动上报流程并藏起样品。"
    assert chapter["outcome"] == "陆辰获得秘密，也背上被公司追查的风险。"
    assert chapter["chapter_hook"] == "白鼠眼中浮现金色经脉纹路。"


def test_draft_chapter_async_mode_queues_then_worker_completes(monkeypatch) -> None:
    reset_database()
    client = TestClient(app)
    created = client.post(
        "/api/projects",
        json={
            "title": "单章后台生成",
            "genre": "都市修真",
            "target_reader": "喜欢长任务可恢复体验的读者",
            "premise": "主角用药物知识打开修行缺口。",
            "style_guide": "清晰、紧张。",
            "language": "zh-CN",
            "planned_chapter_count": 20,
            "chapter_word_target": 2500,
        },
    ).json()
    project_id = created["data"]["project"]["id"]
    db = SessionLocal()
    try:
        chapter = models.Chapter(
            id="async_draft_chapter_1",
            project_id=project_id,
            volume_no=1,
            chapter_no=1,
            title="第1章：后台生成",
            outline="主角发现废弃药物异常。",
            status="planned",
            word_target=2500,
            sort_order=1,
        )
        db.add(chapter)
        db.commit()
    finally:
        db.close()

    def fake_stream(state: NovelStudioState):
        base = {
            "chapter_card": {"chapter_no": 1, "chapter_title": "第1章：后台生成"},
            "scene_outline": {"scenes": [{"scene_no": 1, "goal": "发现异常"}]},
            "plot_draft": "陆辰发现废弃药物异常。",
            "dialogue_draft": "这支药不对劲。",
            "environment_draft": "禁药库灯光冷白。",
            "integrated_draft": "陆辰发现废弃药物异常。",
            "review_notes": [],
            "fact_check_report": {"status": "passed", "issues": []},
            "quality_gate": {"status": "passed"},
            "health_check_report": {},
            "style_polished_text": "陆辰发现废弃药物异常。",
            "final_chapter_text": "陆辰发现废弃药物异常。",
            "chapter_summary": "陆辰发现异常。",
            "narrative_ledger": {"chapter_summary": "陆辰发现异常。"},
            "candidate_canon_updates": {},
            "canon_updates": {},
        }
        yield state.model_copy(update={**base, "current_agent": "chapter_card"})
        yield state.model_copy(update={**base, "current_agent": "canon_curator"})

    monkeypatch.setattr(studio_service_module.chapter_writing_service, "stream_chapter_draft", fake_stream)

    db = SessionLocal()
    try:
        queued = studio_service.draft_chapter(
            db,
            project_id,
            "async_draft_chapter_1",
            DraftChapterRequest(user_instruction="后台生成正文", idempotency_key="async-draft-test", async_mode=True),
        )
        assert queued["job"]["status"] == "queued"
        assert queued["job"]["progress"]["current_step"] == "queued"
        assert queued["chapter"]["final_text"] == ""
        job_id = queued["job"]["id"]
    finally:
        db.close()

    studio_service.run_draft_chapter_job(job_id)

    job_response = client.get(f"/api/jobs/{job_id}")
    assert job_response.status_code == 200
    job = job_response.json()["data"]["job"]
    assert job["status"] == "succeeded"
    assert job["progress"]["completed_steps"] == job["progress"]["total_steps"]
    chapter = client.get(f"/api/projects/{project_id}/chapters/async_draft_chapter_1").json()["data"]["chapter"]
    assert chapter["status"] == "drafted"
    assert chapter["final_text"] == "陆辰发现废弃药物异常。"


def test_list_jobs_filters_recent_batch_jobs_by_project() -> None:
    reset_database()
    client = TestClient(app)
    created = client.post(
        "/api/projects",
        json={
            "title": "批量任务恢复",
            "genre": "科幻",
            "target_reader": "喜欢任务监控的读者",
            "premise": "主角维护一台长篇生成引擎。",
            "style_guide": "清晰。",
            "language": "zh-CN",
            "planned_chapter_count": 5,
            "chapter_word_target": 1800,
        },
    ).json()
    project_id = created["data"]["project"]["id"]
    db = SessionLocal()
    try:
        job = studio_service._create_job(
            db,
            project_id,
            None,
            "batch_generate",
            None,
            {"project_id": project_id, "chapter_start": 1, "chapter_end": 2},
            "batch-list-test",
            total_steps=2,
            queued=True,
        )
        db.commit()
        job_id = job.id
    finally:
        db.close()

    response = client.get("/api/jobs", params={"project_id": project_id, "job_type": "batch_generate", "limit": 5})
    assert response.status_code == 200
    payload = response.json()
    assert_success_envelope(payload)
    assert [item["id"] for item in payload["data"]["jobs"]] == [job_id]


def test_1_0_draft_graph_versions_and_export_flow() -> None:
    reset_database()
    client = TestClient(app)
    created = client.post(
        "/api/projects",
        json={
            "title": "测试 1.0",
            "genre": "科幻",
            "target_reader": "喜欢多 Agent 工作流的读者",
            "premise": "主角发现星门秘密。",
            "style_guide": "简洁、有悬念。",
            "language": "zh-CN",
            "planned_chapter_count": 10,
            "chapter_word_target": 1200,
        },
    ).json()
    project_id = created["data"]["project"]["id"]
    created_chapter = client.post(
        f"/api/projects/{project_id}/chapters",
        json={"volume_no": 1, "title": "第1章：星门秘密", "outline": "开篇建立秘密。", "word_target": 400},
    ).json()
    chapter_id = created_chapter["data"]["chapter"]["id"]

    draft = client.post(
        f"/api/projects/{project_id}/chapters/{chapter_id}/draft",
        json={"user_instruction": "写得紧张一点"},
    )
    assert draft.status_code == 200, draft.text
    draft_payload = draft.json()
    assert_success_envelope(draft_payload)
    assert draft_payload["data"]["job"]["status"] == "succeeded"
    assert draft_payload["data"]["chapter"]["final_text"]

    runs = client.get(f"/api/jobs/{draft_payload['data']['job']['id']}/agent-runs").json()
    agent_names = [item["agent_name"] for item in runs["data"]["agent_runs"]]
    assert len(agent_names) == 15
    assert "canon_context" in agent_names
    assert "chapter_card" in agent_names
    assert "scene_outline" in agent_names
    assert "draft_rewrite" in agent_names
    assert "quality_gate" in agent_names
    assert "post_length_review" in agent_names
    assert "narrative_ledger" in agent_names
    assert all(isinstance(item["duration_ms"], int) for item in runs["data"]["agent_runs"])
    assert all(item["output"] == item["output_payload"] for item in runs["data"]["agent_runs"])

    graph = client.get(f"/api/projects/{project_id}/graph").json()
    assert graph["data"]["graph"]["nodes"]

    versions = client.get("/api/versions").json()
    assert versions["data"]["versions"]

    exported = client.post("/api/export", json={"project_id": project_id, "format": "markdown"}).json()
    assert exported["data"]["export_job"]["status"] == "succeeded"


def test_draft_workflow_builds_context_quality_gate_and_candidate_canon_updates() -> None:
    state = NovelStudioState(
        project_id="prj_test",
        title="设定驱动测试",
        genre="奇幻",
        style_guide="克制、清晰，避免设定堆砌。",
        story_bible={"world_setting": "灵潮退去后，城邦以契约维持秩序。"},
        characters=[
            {
                "id": "char_1",
                "name": "林昭",
                "importance_level": "core",
                "importance_score": 95,
                "summary": "年轻契约师，正在寻找失踪导师。",
            }
        ],
        world_facts=[
            {
                "id": "wld_1",
                "title": "契约禁律",
                "content": "契约一旦见血成立，违约者会失去一段记忆。",
                "importance_level": "core",
                "importance_score": 92,
            }
        ],
        story_entities=[
            {
                "id": "ent_1",
                "entity_type": "item",
                "name": "裂纹铜印",
                "importance_level": "major",
                "importance_score": 80,
            }
        ],
        canon_context={
            "characters": [{"name": "林昭", "summary": "年轻契约师"}],
            "world_facts": [{"title": "契约禁律", "content": "违约者会失去记忆"}],
            "story_entities": [{"name": "裂纹铜印", "entity_type": "item"}],
            "previous_summaries": [],
        },
        current_chapter_outline={
            "chapter_no": 1,
            "title": "见血的铜印",
            "core_event": "林昭发现铜印与导师失踪有关。",
            "conflict": "她必须决定是否触发危险契约。",
        },
    )

    result = agent_workflow.run_chapter_draft(state)

    assert result.chapter_card["chapter_title"] == "见血的铜印"
    assert result.scene_outline["scenes"]
    assert result.integrated_draft
    assert result.quality_gate["status"] == "passed"
    assert result.final_chapter_text
    assert result.narrative_ledger["chapter_summary"]
    assert result.candidate_canon_updates["world_fact_updates"]
    assert "林昭" in result.plot_draft
    assert "契约禁律" in result.plot_draft


def test_chapter_draft_routes_canon_updates_to_reviewable_proposals(monkeypatch) -> None:
    reset_database()
    client = TestClient(app)
    created = client.post(
        "/api/v1/projects",
        json={
            "title": "血检候选链",
            "genre": "都市玄幻",
            "target_reader": "喜欢设定严谨和伏笔回收的读者",
            "premise": "低血统主角发现血检制度漏洞。",
            "style_guide": "冷静、压迫。",
            "language": "zh-CN",
            "planned_chapter_count": 30,
            "chapter_word_target": 2000,
        },
    ).json()
    project_id = created["data"]["project"]["id"]
    chapter = client.post(
        f"/api/v1/projects/{project_id}/chapters",
        json={"volume_no": 1, "title": "第一章：血检", "outline": "陆沉被血脉评级压制。", "word_target": 2000},
    ).json()["data"]["chapter"]

    updates = {
        "world_fact_updates": [
            {
                "category": "politics",
                "title": "血检制度漏洞",
                "content": "血检仪会被特定旧式药剂干扰。",
                "importance_score": 80,
                "confidence": 0.86,
            }
        ],
        "relation_updates": [
            {
                "source": "陆沉",
                "target": "血检制度漏洞",
                "edge_type": "discovers",
                "label": "发现",
                "importance_score": 75,
                "confidence": 0.82,
                "evidence": "第一章结尾陆沉观察到评级异常。",
            }
        ],
        "foreshadowing_updates": [
            {
                "content": "血检仪背后的旧式药剂来源仍未揭晓。",
                "planned_payoff": "第三卷揭示药剂来自王朝禁库。",
                "payoff_status": "planted",
                "importance_score": 78,
                "confidence": 0.8,
            }
        ],
    }

    def fake_stream(state: NovelStudioState):
        yield state.model_copy(
            update={
                "current_agent": "canon_curator",
                "chapter_card": {"chapter_title": "第一章：血检", "foreshadowing": "血检仪异常"},
                "scene_outline": {"scenes": [{"scene_no": 1, "goal": "暴露血检制度"}]},
                "plot_draft": "陆沉发现血检仪被旧式药剂干扰。",
                "dialogue_draft": "你不该看见这个数值。",
                "environment_draft": "检测室灯光冷白。",
                "integrated_draft": "陆沉发现血检仪被旧式药剂干扰。",
                "review_notes": [],
                "fact_check_report": {"status": "passed", "issues": []},
                "quality_gate": {"status": "passed"},
                "health_check_report": {},
                "style_polished_text": "陆沉发现血检仪被旧式药剂干扰。",
                "final_chapter_text": "陆沉发现血检仪被旧式药剂干扰。",
                "chapter_summary": "陆沉发现血检制度漏洞。",
                "narrative_ledger": {"chapter_summary": "陆沉发现血检制度漏洞。"},
                "candidate_canon_updates": updates,
                "canon_updates": updates,
            }
        )

    monkeypatch.setattr(studio_service_module.chapter_writing_service, "stream_chapter_draft", fake_stream)

    draft = client.post(
        f"/api/v1/projects/{project_id}/chapters/{chapter['id']}/draft",
        json={"user_instruction": "生成第一章正文", "idempotency_key": "draft-canon-proposals"},
    )
    assert draft.status_code == 200
    assert_success_envelope(draft.json())

    world_facts = client.get(f"/api/v1/projects/{project_id}/world-facts").json()["data"]["world_facts"]
    assert all(item["title"] != "血检制度漏洞" for item in world_facts)

    proposals = client.get(f"/api/v1/projects/{project_id}/settings/proposals?status=pending").json()["data"]["proposals"]
    target_types = {item["target_type"] for item in proposals}
    assert {"world_fact", "graph_edge", "foreshadowing"}.issubset(target_types)
    assert all(item["source_chapter"]["chapter_no"] == 1 for item in proposals)

    relation_proposal = next(item for item in proposals if item["target_type"] == "graph_edge")
    approved_relation = client.post(f"/api/v1/projects/{project_id}/settings/proposals/{relation_proposal['id']}/approve").json()["data"]
    assert approved_relation["applied_ref"]["ref_type"] == "graph_edge"
    graph = client.get(f"/api/v1/projects/{project_id}/graph").json()["data"]["graph"]
    assert any(edge["edge_type"] == "discovers" and edge["source_chapter_id"] == chapter["id"] for edge in graph["edges"])

    foreshadowing_proposal = next(item for item in proposals if item["target_type"] == "foreshadowing")
    approved_foreshadowing = client.post(f"/api/v1/projects/{project_id}/settings/proposals/{foreshadowing_proposal['id']}/approve").json()["data"]
    assert approved_foreshadowing["applied_ref"]["ref_type"] == "foreshadowing"
    foreshadowing = client.get(f"/api/v1/projects/{project_id}/foreshadowing").json()["data"]["foreshadowing_items"]
    assert any("旧式药剂来源" in item["content"] for item in foreshadowing)


def test_core_agent_workflows_call_llm_client_for_agent_nodes(monkeypatch) -> None:
    class FakeLLMClient:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str | None]] = []

        def generate(self, system_prompt: str, user_prompt: str, model: str | None = None):
            payload = json.loads(user_prompt)
            agent_name = payload["agent_name"]
            self.calls.append((agent_name, model))
            responses = {
                "chief_architect": {
                    "story_bible": {
                        "world_setting": "LLM 世界观",
                        "main_conflict": "LLM 主线冲突",
                        "themes": ["选择"],
                        "narrative_pov": "third_person_limited",
                        "style_guide": "LLM 风格",
                        "forbidden_elements": [],
                        "continuity_rules": [],
                    },
                    "characters": [{"name": "林昭", "role_type": "protagonist", "summary": "LLM 主角"}],
                    "outline": [{"volume_no": 1, "title": "LLM 第一卷"}],
                },
                "chapter_planner": {
                    "chapter_card": {
                        "chapter_no": 1,
                        "volume_no": 1,
                        "chapter_title": "LLM 第一章",
                        "pov_character": "林昭",
                        "one_sentence": "LLM 事件",
                        "main_obstacle": "LLM 冲突",
                        "irreversible_consequence": "LLM 转折",
                        "chapter_function": "LLM 功能",
                        "ending_hook": "LLM 钩子",
                        "word_target": 2000,
                    }
                },
                "plot_narrator": {"plot_draft": "LLM情节：林昭推进契约。"},
                "dialogue_writer": {"dialogue_draft": "LLM对话：你必须做选择。"},
                "environment_writer": {"environment_draft": "LLM环境：雨声压住铜印。"},
                "integrator": {"integrated_draft": "# LLM整合稿", "chapter_summary": "LLM 摘要"},
                "reviewer": {"review_notes": [{"severity": "info", "category": "logic", "message": "LLM 审核通过"}]},
                "fact_checker": {"fact_check_report": {"status": "passed", "issues": []}},
                "style_unifier": {"style_polished_text": "LLM终稿", "final_chapter_text": "LLM终稿"},
                "canon_curator": {
                    "candidate_canon_updates": {"world_fact_updates": [{"title": "LLM设定", "confidence": 0.8}]},
                    "canon_updates": {"world_fact_updates": [{"title": "LLM设定", "confidence": 0.8}]},
                },
            }
            return SimpleNamespace(
                content=json.dumps(responses[agent_name], ensure_ascii=False),
                provider="fake-provider",
                model=model or "fake-model",
                used_remote_model=True,
            )

    fake_llm = FakeLLMClient()
    monkeypatch.setattr(workflow_module, "llm_client", fake_llm)
    state = NovelStudioState(
        project_id="prj_llm",
        title="LLM 接线测试",
        genre="奇幻",
        target_reader="长篇读者",
        premise="一枚铜印会改写契约。",
        requested_model="unit-model",
        current_chapter_outline={"chapter_no": 1, "title": "铜印", "core_event": "发现铜印", "conflict": "是否触发契约"},
        canon_context={"characters": [{"name": "林昭"}], "world_facts": [{"title": "契约禁律"}], "story_entities": [{"name": "裂纹铜印"}]},
    )

    initialized = agent_workflow.run_initialization(state)
    assert initialized.novel_constitution["main_conflict"] == "LLM 主线冲突"
    assert initialized.constitution_review["status"] == "passed_with_notes"
    drafted = agent_workflow.run_chapter_draft(
        initialized.model_copy(update={"current_chapter_outline": state.current_chapter_outline, "canon_context": state.canon_context})
    )

    called_agents = [agent_name for agent_name, _ in fake_llm.calls]
    for agent_name in [
        "chief_architect",
        "chapter_planner",
        "plot_narrator",
        "dialogue_writer",
        "environment_writer",
        "integrator",
        "reviewer",
        "fact_checker",
        "style_unifier",
        "canon_curator",
    ]:
        assert agent_name in called_agents
    assert all(model == "unit-model" for _, model in fake_llm.calls)
    assert drafted.plot_draft == "LLM情节：林昭推进契约。"
    assert drafted.chapter_card["chapter_title"] == "LLM 第一章"
    assert drafted.scene_outline["scenes"]
    assert drafted.narrative_ledger["chapter_summary"] == "LLM 摘要"
    assert drafted.context_summary
    assert drafted.final_chapter_text == "LLM终稿"
    assert drafted.agent_llm_results["plot_narrator"]["used_remote_model"] is True
    assert drafted.agent_llm_results["plot_narrator"]["provider"] == "fake-provider"


def test_chapter_draft_length_guard_expands_short_final_text(monkeypatch) -> None:
    class FakeLLMClient:
        def __init__(self) -> None:
            self.calls: list[dict] = []
            self.style_unifier_calls = 0

        def generate(self, system_prompt: str, user_prompt: str, model: str | None = None):
            payload = json.loads(user_prompt)
            agent_name = payload["agent_name"]
            self.calls.append(payload)
            if agent_name == "style_unifier":
                self.style_unifier_calls += 1
                if self.style_unifier_calls == 1:
                    response = {"style_polished_text": "短章", "final_chapter_text": "短章"}
                else:
                    expanded = "第2章 · 错章\n\n" + "扩写后的完整章节正文" * 8
                    response = {
                        "style_polished_text": expanded,
                        "final_chapter_text": expanded,
                    }
            else:
                responses = {
                    "chapter_planner": {
                        "chapter_card": {
                            "chapter_title": "字数守门",
                            "one_sentence": "主角完成一次不可逆选择。",
                            "main_obstacle": "外部阻力升级。",
                        }
                    },
                    "plot_narrator": {"scene_outline": {"scenes": [{"scene_no": 1, "goal": "进入冲突"}]}, "plot_draft": "情节主干"},
                    "dialogue_writer": {"dialogue_draft": "人物对话"},
                    "environment_writer": {"environment_draft": "环境描写"},
                    "integrator": {"integrated_draft": "整合草稿", "chapter_summary": "章节摘要"},
                    "reviewer": {
                        "review_notes": [
                            {"severity": "warning", "category": "structure", "message": "本章正文字数仅3字，低于最低可接受字数。", "suggestion": "扩写。"},
                            {"severity": "info", "category": "logic", "message": "通过"},
                        ]
                    },
                    "fact_checker": {"fact_check_report": {"status": "passed", "issues": []}},
                    "canon_curator": {
                        "candidate_canon_updates": {"world_fact_updates": [{"title": "新规则", "confidence": 0.8}]},
                        "canon_updates": {"world_fact_updates": [{"title": "新规则", "confidence": 0.8}]},
                    },
                }
                response = responses.get(agent_name, {})
            return SimpleNamespace(
                content=json.dumps(response, ensure_ascii=False),
                provider="fake-provider",
                model=model or "fake-model",
                used_remote_model=True,
            )

    fake_llm = FakeLLMClient()
    monkeypatch.setattr(workflow_module, "llm_client", fake_llm)
    state = NovelStudioState(
        project_id="prj_length",
        title="字数守门测试",
        genre="玄幻",
        target_words=120,
        target_chapters=1,
        current_chapter_outline={
            "chapter_no": 1,
            "title": "字数守门",
            "core_event": "主角完成一次不可逆选择。",
            "conflict": "外部阻力升级。",
            "word_target": 80,
        },
        canon_context={"characters": [{"name": "林昭"}], "world_facts": [{"title": "契约禁律"}]},
    )

    drafted = agent_workflow.run_chapter_draft(state)

    assert fake_llm.style_unifier_calls == 2
    assert drafted.final_chapter_text.startswith("字数守门\n\n")
    assert "第2章 · 错章" not in drafted.final_chapter_text.splitlines()[0]
    assert len(drafted.final_chapter_text.replace("\n", "")) >= 68
    assert not any("低于最低可接受字数" in note.get("message", "") for note in drafted.review_notes)
    assert any(note.get("category") == "length_guard" for note in drafted.review_notes)
    assert any(note.get("category") == "post_length_review" for note in drafted.review_notes)
    assert drafted.health_check_report["post_length_review"]["status"] == "passed"
    assert drafted.health_check_report["post_length_review"]["final_words"] >= 68
    assert "style_unifier_length_guard" in drafted.agent_llm_results
    length_guard_call = next(call for call in fake_llm.calls if "低于最低可接受字数" in call["task"])
    assert length_guard_call["context"]["generation_requirements"]["chapter_word_target"] == 80


def test_chapter_draft_length_guard_retries_when_first_expansion_is_still_short(monkeypatch) -> None:
    class FakeLLMClient:
        def __init__(self) -> None:
            self.calls: list[dict] = []
            self.style_unifier_calls = 0

        def generate(self, system_prompt: str, user_prompt: str, model: str | None = None):
            payload = json.loads(user_prompt)
            agent_name = payload["agent_name"]
            self.calls.append(payload)
            if agent_name == "style_unifier":
                self.style_unifier_calls += 1
                if self.style_unifier_calls == 1:
                    response = {"style_polished_text": "短章", "final_chapter_text": "短章"}
                elif self.style_unifier_calls == 2:
                    response = {"style_polished_text": "仍然偏短" * 5, "final_chapter_text": "仍然偏短" * 5}
                else:
                    expanded = "第一章 档案编号\n\n" + "第二次扩写后的完整章节正文" * 12
                    response = {"style_polished_text": expanded, "final_chapter_text": expanded}
            else:
                responses = {
                    "chapter_planner": {"chapter_card": {"chapter_title": "字数守门", "one_sentence": "主角完成一次不可逆选择。"}},
                    "plot_narrator": {"scene_outline": {"scenes": [{"scene_no": 1, "goal": "进入冲突"}]}, "plot_draft": "情节主干"},
                    "dialogue_writer": {"dialogue_draft": "人物对话"},
                    "environment_writer": {"environment_draft": "环境描写"},
                    "integrator": {"integrated_draft": "整合草稿", "chapter_summary": "章节摘要"},
                    "reviewer": {"review_notes": [{"severity": "warning", "category": "structure", "message": "本章正文字数仅3字，低于最低可接受字数。", "suggestion": "扩写。"}]},
                    "fact_checker": {"fact_check_report": {"status": "passed", "issues": []}},
                    "canon_curator": {"candidate_canon_updates": {}, "canon_updates": {}},
                }
                response = responses.get(agent_name, {})
            return SimpleNamespace(content=json.dumps(response, ensure_ascii=False), provider="fake-provider", model=model or "fake-model", used_remote_model=True)

    fake_llm = FakeLLMClient()
    monkeypatch.setattr(workflow_module, "llm_client", fake_llm)
    state = NovelStudioState(
        project_id="prj_length_retry",
        title="字数守门测试",
        genre="玄幻",
        current_chapter_outline={
            "chapter_no": 1,
            "title": "字数守门",
            "core_event": "主角完成一次不可逆选择。",
            "word_target": 80,
        },
    )

    drafted = agent_workflow.run_chapter_draft(state)

    assert fake_llm.style_unifier_calls == 3
    assert drafted.final_chapter_text.startswith("字数守门\n\n")
    assert len(drafted.final_chapter_text.replace("\n", "")) >= 68
    length_guard = drafted.agent_llm_results["style_unifier_length_guard"]
    assert len(length_guard["attempts"]) == 2
    assert length_guard["reached_minimum"] is True
    assert drafted.health_check_report["post_length_review"]["status"] == "passed"


def test_chapter_draft_stream_emits_running_event_before_node_work() -> None:
    state = NovelStudioState(
        project_id="prj_stream_progress",
        title="流式进度",
        genre="都市",
        current_chapter_outline={"chapter_no": 1, "title": "第一章", "word_target": 8000},
    )

    first = next(chapter_agent_workflow.stream_chapter_draft(state))

    assert first.current_agent == "canon_context"
    assert first.progress_event["status"] == "running"
    assert first.progress_event["node"] == "build_context"


def test_batch_parent_progress_includes_child_fraction_eta_and_retry_metadata() -> None:
    reset_database()
    client = TestClient(app)
    project_id = client.post(
        "/api/projects",
        json={
            "title": "长任务进度",
            "genre": "玄幻",
            "target_reader": "长篇读者",
            "premise": "主角逐卷推进百万字任务。",
            "style_guide": "清晰。",
            "language": "zh-CN",
            "planned_chapter_count": 80,
            "chapter_word_target": 2500,
        },
    ).json()["data"]["project"]["id"]
    db = SessionLocal()
    try:
        parent_job = studio_service._create_job(
            db,
            project_id,
            None,
            "batch_generate",
            None,
            {"project_id": project_id, "chapter_start": 1, "chapter_end": 20},
            "batch-progress-parent",
            total_steps=20,
            queued=True,
        )
        parent_job.started_at = models.utcnow() - timedelta(seconds=120)
        parent_job.result_json = json.dumps(
            {
                "mode": "async_batch_generate",
                "requested_range": {"project_id": project_id, "chapter_start": 1, "chapter_end": 20},
                "chapter_results": [{"chapter_no": 1, "chapter_id": "chp_1", "title": "第1章", "word_count": 1000}],
                "failed_chapters": [{"chapter_no": 3, "message": "临时失败"}],
                "skipped_chapters": [],
                "last_completed_chapter_no": 1,
            },
            ensure_ascii=False,
        )
        child_job = studio_service._create_job(
            db,
            project_id,
            None,
            "draft_chapter",
            None,
            {"project_id": project_id, "chapter_id": "chp_2"},
            "batch-progress-child",
            total_steps=14,
            queued=False,
        )
        db.commit()

        state = NovelStudioState(project_id=project_id, current_chapter=2, current_agent="style_unifier")
        studio_service._record_chapter_draft_progress(
            db,
            child_job,
            state,
            previous_step=11,
            parent_job_id=parent_job.id,
            parent_chapter_no=2,
            parent_total_steps=20,
        )

        db.refresh(parent_job)
        progress = json.loads(parent_job.progress_json)
        assert progress["completed_steps"] == 1
        assert progress["child_current_step"] == "style_unifier"
        assert progress["child_step_label"] == "风格统一"
        assert progress["child_completed_steps"] == 12
        assert progress["overall_percent"] > 5
        assert progress["completed_chapters"] == 1
        assert progress["total_chapters"] == 20
        assert progress["eta_seconds"] >= 2000
        assert progress["retryable_failed_chapters"] == [3]
        assert progress["long_task"] is True
        assert progress["long_task_advice"]
    finally:
        db.close()


def test_stale_batch_running_job_is_marked_failed_and_retryable() -> None:
    reset_database()
    client = TestClient(app)
    project_id = client.post(
        "/api/projects",
        json={
            "title": "失活任务恢复",
            "genre": "玄幻",
            "target_reader": "长篇读者",
            "premise": "主角逐章推进长任务。",
            "style_guide": "清晰。",
            "language": "zh-CN",
            "planned_chapter_count": 20,
            "chapter_word_target": 8000,
        },
    ).json()["data"]["project"]["id"]
    db = SessionLocal()
    try:
        parent_job = studio_service._create_job(
            db,
            project_id,
            None,
            "batch_generate",
            None,
            {"project_id": project_id, "chapter_start": 1, "chapter_end": 5},
            "stale-batch-parent",
            total_steps=5,
            queued=True,
        )
        parent_job.status = "running"
        parent_job.started_at = models.utcnow() - timedelta(hours=3)
        parent_job.result_json = json.dumps(
            {
                "mode": "async_batch_generate",
                "requested_range": {"project_id": project_id, "chapter_start": 1, "chapter_end": 5},
                "chapter_results": [{"chapter_no": 1, "chapter_id": "chp_1", "title": "第1章", "word_count": 8000}],
                "failed_chapters": [],
                "skipped_chapters": [],
                "last_completed_chapter_no": 1,
            },
            ensure_ascii=False,
        )
        child_job = studio_service._create_job(
            db,
            project_id,
            None,
            "draft_chapter",
            None,
            {"project_id": project_id, "chapter_id": "chp_2"},
            "stale-batch-child",
            total_steps=14,
            queued=False,
        )
        db.commit()

        state = NovelStudioState(
            project_id=project_id,
            current_chapter=2,
            current_agent="style_unifier",
            progress_event={"status": "running"},
        )
        studio_service._record_chapter_draft_progress(
            db,
            child_job,
            state,
            previous_step=11,
            parent_job_id=parent_job.id,
            parent_chapter_no=2,
            parent_total_steps=5,
        )

        stale_at = models.utcnow() - timedelta(hours=2)
        parent_id = parent_job.id
        child_id = child_job.id
        parent_job = db.get(models.GenerationJob, parent_id)
        child_job = db.get(models.GenerationJob, child_id)
        parent_job.heartbeat_at = stale_at
        child_job.heartbeat_at = stale_at
        db.commit()
    finally:
        db.close()

    response = client.get(f"/api/jobs/{parent_id}")

    assert response.status_code == 200
    job = response.json()["data"]["job"]
    assert job["status"] == "failed"
    assert "后台任务中断" in job["error"]["message"]
    assert job["progress"]["current_step"] == "failed"
    assert job["progress"]["current_chapter_no"] == 2
    assert job["progress"]["retryable_failed_chapters"] == [2]
    assert "重试" in job["progress"]["message"]

    db = SessionLocal()
    try:
        child_job = db.get(models.GenerationJob, child_id)
        assert child_job.status == "failed"
        assert "后台任务中断" in child_job.error_message
    finally:
        db.close()


def test_batch_success_rejects_failed_child_job_result() -> None:
    reset_database()
    client = TestClient(app)
    project_id = client.post(
        "/api/projects",
        json={
            "title": "批量成功校验",
            "genre": "玄幻",
            "target_reader": "长篇读者",
            "premise": "主角推进长任务。",
            "style_guide": "清晰。",
            "language": "zh-CN",
            "planned_chapter_count": 1,
            "chapter_word_target": 8000,
        },
    ).json()["data"]["project"]["id"]
    chapter = client.post(
        f"/api/projects/{project_id}/chapters",
        json={"volume_no": 1, "title": "第1章：误判", "outline": "测试失败子任务不能算成功。", "word_target": 8000},
    ).json()["data"]["chapter"]
    db = SessionLocal()
    try:
        parent_job = studio_service._create_job(
            db,
            project_id,
            None,
            "batch_generate",
            None,
            {"project_id": project_id, "chapter_start": 1, "chapter_end": 1},
            "failed-child-parent",
            total_steps=1,
            queued=True,
        )
        child_job = studio_service._create_job(
            db,
            project_id,
            chapter["id"],
            "draft_chapter",
            None,
            {"project_id": project_id, "chapter_id": chapter["id"]},
            "failed-child",
            total_steps=15,
            queued=False,
        )
        child_job.status = "failed"
        child_job.error_message = "子任务失败"
        db.commit()

        request = studio_service._batch_request_from_job(parent_job)
        chapter_row = db.get(models.Chapter, chapter["id"])
        with pytest.raises(ValueError, match="子任务未成功"):
            studio_service._record_batch_chapter_success(
                db,
                parent_job,
                request,
                chapter_row,
                {"job": {"id": child_job.id, "status": "failed"}},
            )
    finally:
        db.close()


def test_batch_generate_passes_chapter_word_target_to_child_draft(monkeypatch) -> None:
    reset_database()
    client = TestClient(app)
    project_id = client.post(
        "/api/projects",
        json={
            "title": "批量字数目标",
            "genre": "玄幻",
            "target_reader": "长篇读者",
            "premise": "主角推进五十章长线。",
            "style_guide": "清晰。",
            "language": "zh-CN",
            "planned_chapter_count": 1,
            "chapter_word_target": 4000,
            "chapter_word_min": 4000,
            "chapter_word_max": 4000,
        },
    ).json()["data"]["project"]["id"]
    chapter = client.post(
        f"/api/projects/{project_id}/chapters",
        json={"volume_no": 1, "title": "第1章：目标", "outline": "验证批量生成传递字数目标。", "word_target": 4000},
    ).json()["data"]["chapter"]
    captured: list[int] = []

    def fake_draft_chapter(db, project_id_arg, chapter_id_arg, request, **kwargs):
        captured.append(request.max_words)
        chapter_row = db.get(models.Chapter, chapter_id_arg)
        chapter_row.final_text = "目标字数验证。" * 400
        chapter_row.word_count = 4000
        chapter_row.status = "drafted"
        db.commit()
        db.refresh(chapter_row)
        return {
            "job": {"id": "child_job", "status": "succeeded"},
            "chapter": serialize_chapter(chapter_row),
        }

    monkeypatch.setattr(studio_service, "draft_chapter", fake_draft_chapter)
    monkeypatch.setattr(studio_service, "_enqueue_batch_job", lambda job_id: None)
    response = client.post("/api/write/batch-generate", json={"project_id": project_id, "chapter_start": 1, "chapter_end": 1})
    assert response.status_code == 200
    parent_job_id = response.json()["data"]["job"]["id"]

    studio_service._run_batch_generate_job(parent_job_id)

    assert captured == [4000]
    job = client.get(f"/api/jobs/{parent_job_id}").json()["data"]["job"]
    assert job["status"] == "succeeded"
    assert job["result"]["chapter_results"][0]["word_count"] == 4000


def test_batch_generate_fast_draft_writes_chapter_with_single_child_job(monkeypatch) -> None:
    reset_database()
    client = TestClient(app)
    project_id = client.post(
        "/api/projects",
        json={
            "title": "快速批量正文",
            "genre": "都市异能",
            "target_reader": "长篇读者",
            "premise": "主角用记忆账本追查真相。",
            "style_guide": "紧张、清晰。",
            "language": "zh-CN",
            "planned_chapter_count": 1,
            "chapter_word_target": 1000,
            "chapter_word_min": 1000,
            "chapter_word_max": 1000,
        },
    ).json()["data"]["project"]["id"]
    chapter = client.post(
        f"/api/projects/{project_id}/chapters",
        json={"volume_no": 1, "title": "黑市修补师", "outline": "主角进入黑市修补记忆账本。", "word_target": 1000},
    ).json()["data"]["chapter"]

    calls: list[str] = []

    def fake_generate(system_prompt, user_prompt, model=None):
        calls.append(user_prompt)
        return SimpleNamespace(content="记忆账本在雨夜发烫。" * 60, provider="fake", model="fake-fast", used_remote_model=True)

    monkeypatch.setattr(studio_service_module.llm_client, "generate", fake_generate)
    monkeypatch.setattr(studio_service, "_enqueue_batch_job", lambda job_id: None)
    response = client.post(
        "/api/write/batch-generate",
        json={"project_id": project_id, "chapter_start": 1, "chapter_end": 1, "generation_options": {"fast_draft": True}},
    )
    assert response.status_code == 200
    parent_job_id = response.json()["data"]["job"]["id"]

    studio_service._run_batch_generate_job(parent_job_id)

    job = client.get(f"/api/jobs/{parent_job_id}").json()["data"]["job"]
    assert job["status"] == "succeeded"
    assert 1000 <= job["result"]["chapter_results"][0]["word_count"] <= 1050
    child_jobs = client.get("/api/jobs", params={"project_id": project_id, "job_type": "draft_chapter_fast", "limit": 5}).json()["data"]["jobs"]
    assert len(child_jobs) == 1
    assert child_jobs[0]["status"] == "succeeded"
    chapter_after = client.get(f"/api/projects/{project_id}/chapters/{chapter['id']}").json()["data"]["chapter"]
    assert chapter_after["status"] == "drafted"
    assert "记忆账本在雨夜发烫" in chapter_after["final_text"]
    assert len(calls) == 2


def test_batch_generate_fast_draft_trims_oversized_chapter(monkeypatch) -> None:
    reset_database()
    client = TestClient(app)
    project_id = client.post(
        "/api/projects",
        json={
            "title": "快速正文截断",
            "genre": "都市异能",
            "target_reader": "长篇读者",
            "premise": "主角用记忆账本追查真相。",
            "style_guide": "紧张、清晰。",
            "language": "zh-CN",
            "planned_chapter_count": 1,
            "chapter_word_target": 1000,
            "chapter_word_min": 1000,
            "chapter_word_max": 1000,
        },
    ).json()["data"]["project"]["id"]
    chapter = client.post(
        f"/api/projects/{project_id}/chapters",
        json={"volume_no": 1, "title": "超长草稿", "outline": "模型一次写太长时应截断。", "word_target": 1000},
    ).json()["data"]["chapter"]

    calls: list[str] = []

    def fake_generate(system_prompt, user_prompt, model=None):
        calls.append(user_prompt)
        return SimpleNamespace(content="记忆账本在雨夜发烫，追债人沿着伪造记录追进地下仓库。" * 120, provider="fake", model="fake-fast", used_remote_model=True)

    monkeypatch.setattr(studio_service_module.llm_client, "generate", fake_generate)
    monkeypatch.setattr(studio_service, "_enqueue_batch_job", lambda job_id: None)
    response = client.post(
        "/api/write/batch-generate",
        json={"project_id": project_id, "chapter_start": 1, "chapter_end": 1, "generation_options": {"fast_draft": True}},
    )
    assert response.status_code == 200
    parent_job_id = response.json()["data"]["job"]["id"]

    studio_service._run_batch_generate_job(parent_job_id)

    job = client.get(f"/api/jobs/{parent_job_id}").json()["data"]["job"]
    assert job["status"] == "succeeded"
    assert 1000 <= job["result"]["chapter_results"][0]["word_count"] <= 1050
    chapter_after = client.get(f"/api/projects/{project_id}/chapters/{chapter['id']}").json()["data"]["chapter"]
    assert chapter_after["word_count"] <= 1050
    assert len(calls) == 1
    db = SessionLocal()
    try:
        output = db.query(models.GenerationOutput).filter(models.GenerationOutput.chapter_id == chapter["id"]).first()
        assert output is not None
        metadata = json.loads(output.metadata_json)
        assert metadata["target_word_min"] == 1000
        assert metadata["target_word_max"] == 1050
        assert metadata["raw_words"] > metadata["actual_words"]
        assert metadata["trimmed_to_range"] is True
    finally:
        db.close()


def test_fast_draft_trim_prefers_sentence_boundary_after_soft_limit() -> None:
    text = "甲" * 1050 + "，这句话还没有结束" + "乙" * 70 + "。后续内容不应保留。"

    trimmed = studio_service._trim_fast_draft_text_to_band(text, 1000, 1050)

    trimmed_length = len(trimmed.replace("\n", ""))
    assert trimmed.endswith("。")
    assert 1050 < trimmed_length <= 1150
    assert "后续内容不应保留" not in trimmed


def test_fast_draft_trim_keeps_closing_quote_after_sentence_boundary() -> None:
    text = "甲" * 1040 + "“这句话需要闭合。”后续内容不应保留。"

    trimmed = studio_service._trim_fast_draft_text_to_band(text, 1000, 1050)

    assert trimmed.endswith("。”")
    assert "后续内容不应保留" not in trimmed


def test_fast_draft_trim_closes_unbalanced_terminal_dialogue_quote() -> None:
    text = "甲" * 1040 + "“这句话由模型直接少写右引号。"

    trimmed = studio_service._trim_fast_draft_text_to_band(text, 1000, 1200)

    assert trimmed.endswith("。”")


def test_fast_draft_trim_closes_nearest_terminal_quote_pair() -> None:
    text = "甲" * 1040 + "“外层提示：‘内层这句话少写右引号。"

    trimmed = studio_service._trim_fast_draft_text_to_band(text, 1000, 1200)

    assert trimmed.endswith("。’")


def test_fast_draft_trim_closes_terminal_ascii_quote() -> None:
    text = '甲' * 1040 + '终端标识 "#00 序列码：剩余四位未知。'

    trimmed = studio_service._trim_fast_draft_text_to_band(text, 1000, 1200)

    assert trimmed.endswith('。"')


def test_retry_batch_preserves_failed_chapters_for_next_attempt(monkeypatch) -> None:
    reset_database()
    client = TestClient(app)
    project_id = client.post(
        "/api/projects",
        json={
            "title": "重试 attempt",
            "genre": "玄幻",
            "target_reader": "长篇读者",
            "premise": "主角推进长任务。",
            "style_guide": "清晰。",
            "language": "zh-CN",
            "planned_chapter_count": 1,
            "chapter_word_target": 8000,
        },
    ).json()["data"]["project"]["id"]
    db = SessionLocal()
    try:
        parent_job = studio_service._create_job(
            db,
            project_id,
            None,
            "batch_generate",
            None,
            {"project_id": project_id, "chapter_start": 1, "chapter_end": 1},
            "retry-preserve-failed",
            total_steps=1,
            queued=True,
        )
        parent_job.status = "failed"
        parent_job.result_json = json.dumps(
            {
                "mode": "async_batch_generate",
                "requested_range": {"project_id": project_id, "chapter_start": 1, "chapter_end": 1},
                "chapter_results": [],
                "failed_chapters": [{"chapter_no": 1, "message": "旧 attempt 失败"}],
                "skipped_chapters": [],
                "last_completed_chapter_no": None,
            },
            ensure_ascii=False,
        )
        db.commit()
        monkeypatch.setattr(studio_service, "_enqueue_batch_job", lambda job_id: None)

        result = studio_service.retry_job(db, parent_job.id)

        retry_job_payload = result["job"]
        assert retry_job_payload["status"] == "queued"
        assert retry_job_payload["result"]["failed_chapters"][0]["chapter_no"] == 1
        assert retry_job_payload["progress"]["retryable_failed_chapters"] == [1]
        refreshed = db.get(models.GenerationJob, parent_job.id)
        request = studio_service._batch_request_from_job(refreshed)
        assert studio_service._batch_chapter_attempt(studio_service._batch_result_payload(refreshed, request), 1) == 2
    finally:
        db.close()


def test_batch_child_attempt_uses_existing_child_job_history_when_failures_are_collapsed(monkeypatch) -> None:
    reset_database()
    client = TestClient(app)
    project_id = client.post(
        "/api/projects",
        json={
            "title": "重试历史 attempt",
            "genre": "玄幻",
            "target_reader": "长篇读者",
            "premise": "主角推进长任务。",
            "style_guide": "清晰。",
            "language": "zh-CN",
            "planned_chapter_count": 1,
            "chapter_word_target": 8000,
        },
    ).json()["data"]["project"]["id"]
    chapter = client.post(
        f"/api/projects/{project_id}/chapters",
        json={"volume_no": 1, "title": "第1章：历史 attempt", "outline": "测试历史子任务 attempt。", "word_target": 8000},
    ).json()["data"]["chapter"]
    db = SessionLocal()
    try:
        parent_job = studio_service._create_job(
            db,
            project_id,
            None,
            "batch_generate",
            None,
            {"project_id": project_id, "chapter_start": 1, "chapter_end": 1},
            "retry-history-parent",
            total_steps=1,
            queued=True,
        )
        for attempt in (1, 2):
            child_job = studio_service._create_job(
                db,
                project_id,
                chapter["id"],
                "draft_chapter",
                None,
                {"project_id": project_id, "chapter_id": chapter["id"]},
                f"batch:{parent_job.id}:{chapter['id']}:attempt:{attempt}",
                total_steps=15,
                queued=False,
            )
            child_job.status = "failed"
        db.commit()
        result_payload = {
            "mode": "async_batch_generate",
            "requested_range": {"project_id": project_id, "chapter_start": 1, "chapter_end": 1},
            "chapter_results": [],
            "failed_chapters": [{"chapter_no": 1, "message": "折叠后的失败记录"}],
            "skipped_chapters": [],
            "last_completed_chapter_no": None,
        }

        assert studio_service._next_batch_chapter_attempt(db, parent_job.id, chapter["id"], result_payload, 1) == 3
    finally:
        db.close()


def test_retry_batch_drops_invalid_completed_chapter_results(monkeypatch) -> None:
    reset_database()
    client = TestClient(app)
    project_id = client.post(
        "/api/projects",
        json={
            "title": "重试剔除坏结果",
            "genre": "玄幻",
            "target_reader": "长篇读者",
            "premise": "主角推进长任务。",
            "style_guide": "清晰。",
            "language": "zh-CN",
            "planned_chapter_count": 1,
            "chapter_word_target": 8000,
        },
    ).json()["data"]["project"]["id"]
    chapter = client.post(
        f"/api/projects/{project_id}/chapters",
        json={"volume_no": 1, "title": "第1章：坏结果", "outline": "测试 0 字结果不能跳过。", "word_target": 8000},
    ).json()["data"]["chapter"]
    db = SessionLocal()
    try:
        parent_job = studio_service._create_job(
            db,
            project_id,
            None,
            "batch_generate",
            None,
            {"project_id": project_id, "chapter_start": 1, "chapter_end": 1},
            "retry-drop-invalid-result",
            total_steps=1,
            queued=True,
        )
        parent_job.status = "succeeded"
        parent_job.result_json = json.dumps(
            {
                "mode": "async_batch_generate",
                "requested_range": {"project_id": project_id, "chapter_start": 1, "chapter_end": 1},
                "chapter_results": [{"chapter_no": 1, "chapter_id": chapter["id"], "title": chapter["title"], "status": "planned", "word_count": 0}],
                "failed_chapters": [],
                "skipped_chapters": [],
                "last_completed_chapter_no": 1,
            },
            ensure_ascii=False,
        )
        db.commit()
        monkeypatch.setattr(studio_service, "_enqueue_batch_job", lambda job_id: None)

        result = studio_service.retry_job(db, parent_job.id)

        retry_job_payload = result["job"]
        assert retry_job_payload["result"]["chapter_results"] == []
        assert retry_job_payload["result"]["failed_chapters"][0]["chapter_no"] == 1
        assert retry_job_payload["progress"]["retryable_failed_chapters"] == [1]
        refreshed = db.get(models.GenerationJob, parent_job.id)
        request = studio_service._batch_request_from_job(refreshed)
        assert studio_service._completed_batch_chapter_numbers(studio_service._batch_result_payload(refreshed, request)) == set()
    finally:
        db.close()


def test_retry_batch_drops_under_target_chapter_results(monkeypatch) -> None:
    reset_database()
    client = TestClient(app)
    project_id = client.post(
        "/api/projects",
        json={
            "title": "重试短章结果",
            "genre": "玄幻",
            "target_reader": "长篇读者",
            "premise": "主角推进长任务。",
            "style_guide": "清晰。",
            "language": "zh-CN",
            "planned_chapter_count": 1,
            "chapter_word_target": 8000,
        },
    ).json()["data"]["project"]["id"]
    chapter = client.post(
        f"/api/projects/{project_id}/chapters",
        json={"volume_no": 1, "title": "第1章：短章结果", "outline": "测试短章不能算完成。", "word_target": 8000},
    ).json()["data"]["chapter"]
    db = SessionLocal()
    try:
        chapter_row = db.get(models.Chapter, chapter["id"])
        chapter_row.status = "drafted"
        chapter_row.final_text = "短章正文" * 100
        chapter_row.draft_text = chapter_row.final_text
        chapter_row.word_count = len(chapter_row.final_text.replace("\n", ""))
        parent_job = studio_service._create_job(
            db,
            project_id,
            None,
            "batch_generate",
            None,
            {"project_id": project_id, "chapter_start": 1, "chapter_end": 1},
            "retry-drop-under-target-result",
            total_steps=1,
            queued=True,
        )
        parent_job.status = "succeeded"
        parent_job.result_json = json.dumps(
            {
                "mode": "async_batch_generate",
                "requested_range": {"project_id": project_id, "chapter_start": 1, "chapter_end": 1},
                "chapter_results": [{"chapter_no": 1, "chapter_id": chapter["id"], "title": chapter["title"], "status": "drafted", "word_count": chapter_row.word_count}],
                "failed_chapters": [],
                "skipped_chapters": [],
                "last_completed_chapter_no": 1,
            },
            ensure_ascii=False,
        )
        db.commit()
        monkeypatch.setattr(studio_service, "_enqueue_batch_job", lambda job_id: None)

        result = studio_service.retry_job(db, parent_job.id)

        retry_job_payload = result["job"]
        assert retry_job_payload["result"]["chapter_results"] == []
        assert retry_job_payload["result"]["failed_chapters"][0]["chapter_no"] == 1
        assert "低于目标字数" in retry_job_payload["result"]["failed_chapters"][0]["message"]
    finally:
        db.close()


def test_draft_chapter_fails_when_post_length_review_needs_revision(monkeypatch) -> None:
    reset_database()
    client = TestClient(app)
    project_id = client.post(
        "/api/projects",
        json={
            "title": "短章拒绝",
            "genre": "玄幻",
            "target_reader": "长篇读者",
            "premise": "主角推进一场必须完整展开的冲突。",
            "style_guide": "清晰。",
            "language": "zh-CN",
            "planned_chapter_count": 1,
            "chapter_word_target": 1000,
        },
    ).json()["data"]["project"]["id"]
    chapter_id = client.post(
        f"/api/projects/{project_id}/chapters",
        json={"volume_no": 1, "title": "第1章：短章", "outline": "测试短章不能入库。", "word_target": 1000},
    ).json()["data"]["chapter"]["id"]

    class ShortChapterService:
        def stream_chapter_draft(self, state: NovelStudioState):
            yield state.model_copy(
                update={
                    "current_agent": "post_length_review",
                    "style_polished_text": "短章",
                    "final_chapter_text": "短章",
                    "chapter_summary": "短章摘要",
                    "quality_gate": {"status": "passed"},
                    "health_check_report": {
                        "post_length_review": {
                            "status": "needs_revision",
                            "final_words": 2,
                            "minimum_acceptable_words": 1000,
                        }
                    },
                    "review_notes": [
                        {
                            "severity": "warning",
                            "category": "post_length_review",
                            "message": "最终正文 2 字，最低要求 1000 字。",
                        }
                    ],
                }
            )

    monkeypatch.setattr(studio_service_module, "chapter_writing_service", ShortChapterService())

    response = client.post(f"/api/projects/{project_id}/chapters/{chapter_id}/draft", json={"user_instruction": "生成完整正文"})

    assert response.status_code == 400
    assert "最低字数" in response.json()["error"]["message"]
    db = SessionLocal()
    try:
        chapter = db.get(models.Chapter, chapter_id)
        assert chapter.status == "planned"
        assert chapter.word_count == 0
        job = db.query(models.GenerationJob).filter(models.GenerationJob.project_id == project_id, models.GenerationJob.job_type == "draft_chapter").first()
        assert job.status == "failed"
        assert "最低字数" in job.error_message
    finally:
        db.close()


def test_chapter_draft_running_progress_does_not_complete_step() -> None:
    reset_database()
    db = SessionLocal()
    try:
        project = models.Project(
            id="prj_running_progress",
            title="进度心跳",
            genre="都市",
            target_reader="测试读者",
            premise="测试长任务进度。",
            style_guide="",
            language="zh-CN",
            planned_chapter_count=10,
            chapter_word_target=8000,
            chapter_word_min=8000,
            chapter_word_max=8000,
            target_words=80000,
        )
        db.add(project)
        db.flush()
        job = studio_service._create_job(
            db,
            project.id,
            None,
            "draft_chapter",
            None,
            {"project_id": project.id},
            "running-progress-child",
            total_steps=15,
            queued=False,
        )
        db.commit()

        state = NovelStudioState(
            project_id=project.id,
            current_chapter=3,
            current_agent="style_unifier",
            progress_event={"status": "running"},
        )
        completed = studio_service._record_chapter_draft_progress(db, job, state, previous_step=11)

        db.refresh(job)
        progress = json.loads(job.progress_json)
        assert completed == 11
        assert progress["completed_steps"] == 11
        assert progress["current_step"] == "style_unifier"
        assert progress["current_step_status"] == "running"
        assert "正在" in progress["message"]
        assert "已完成" not in progress["message"]
    finally:
        db.close()


def test_canon_context_previous_summaries_exclude_current_chapter() -> None:
    reset_database()
    client = TestClient(app)
    project_id = client.post(
        "/api/projects",
        json={
            "title": "前文摘要过滤",
            "genre": "玄幻",
            "target_reader": "长篇读者",
            "premise": "主角调查药宗旧案。",
            "style_guide": "紧凑。",
            "language": "zh-CN",
            "planned_chapter_count": 10,
            "chapter_word_target": 2000,
        },
    ).json()["data"]["project"]["id"]
    db = SessionLocal()
    try:
        db.add_all(
            [
                models.Chapter(
                    id="chp_prev_1",
                    project_id=project_id,
                    volume_no=1,
                    chapter_no=1,
                    title="第1章",
                    outline="第一章纲",
                    summary="第一章摘要",
                    word_target=2000,
                    sort_order=1,
                ),
                models.Chapter(
                    id="chp_current_2",
                    project_id=project_id,
                    volume_no=1,
                    chapter_no=2,
                    title="第2章",
                    outline="第二章纲",
                    summary="第二章旧摘要",
                    word_target=2000,
                    sort_order=2,
                ),
            ]
        )
        db.commit()
        context = studio_service.build_canon_context(db, project_id, "chp_current_2")["canon_context"]
        previous_numbers = [item["chapter_no"] for item in context["previous_summaries"]]
        assert previous_numbers == [1]
        first_context = studio_service.build_canon_context(db, project_id, "chp_prev_1")["canon_context"]
        assert first_context["previous_summaries"] == []
    finally:
        db.close()


def test_editable_canon_and_agent_assisted_setting_generation() -> None:
    reset_database()
    client = TestClient(app)
    created = client.post(
        "/api/projects",
        json={
            "title": "设定前置编辑",
            "genre": "东方奇幻",
            "target_reader": "喜欢角色成长和严密设定的读者",
            "premise": "主角在灵潮断绝后寻找旧神留下的契约。",
            "style_guide": "稳健、细腻，设定必须服务剧情。",
            "language": "zh-CN",
            "planned_chapter_count": 12,
            "chapter_word_target": 1800,
        },
    ).json()
    project_id = created["data"]["project"]["id"]

    character = client.post(
        f"/api/projects/{project_id}/characters",
        json={
            "name": "沈砚",
            "role_type": "protagonist",
            "importance_level": "core",
            "importance_score": 96,
            "summary": "失去契约能力的前任巡夜人。",
            "appearance": "常穿旧黑袍，左手有银色旧伤。",
            "personality": "谨慎、克制，但在关键时刻敢于冒险。",
            "goals": ["找回失踪的妹妹"],
            "motivations": ["弥补过去的失误"],
            "current_status": "active",
        },
    )
    assert character.status_code == 200
    character_payload = character.json()
    assert_success_envelope(character_payload)
    character_id = character_payload["data"]["character"]["id"]

    updated_character = client.put(
        f"/api/projects/{project_id}/characters/{character_id}",
        json={"importance_score": 99, "updated_reason": "用户提前强化主角重要度。"},
    ).json()
    assert updated_character["data"]["character"]["importance_score"] == 99

    entity = client.post(
        f"/api/projects/{project_id}/entities",
        json={
            "entity_type": "item",
            "name": "裂纹铜印",
            "importance_level": "major",
            "importance_score": 82,
            "description": "能打开旧神契约档案的信物。",
            "current_status": "unclaimed",
        },
    ).json()
    assert entity["data"]["entity"]["name"] == "裂纹铜印"
    entity_id = entity["data"]["entity"]["id"]

    updated_entity = client.put(
        f"/api/projects/{project_id}/entities/{entity_id}",
        json={"current_status": "in_protagonist_possession"},
    ).json()
    assert updated_entity["data"]["entity"]["current_status"] == "in_protagonist_possession"

    fact = client.post(
        f"/api/projects/{project_id}/world-facts",
        json={
            "category": "magic_rule",
            "title": "契约反噬",
            "content": "未完成的契约会以梦境形式追索代价。",
            "importance_level": "core",
            "importance_score": 90,
            "confidence": 0.95,
            "related_entity_ids": [entity_id],
        },
    ).json()
    assert fact["data"]["world_fact"]["title"] == "契约反噬"
    fact_id = fact["data"]["world_fact"]["id"]

    updated_fact = client.put(
        f"/api/projects/{project_id}/world-facts/{fact_id}",
        json={"confidence": 0.88, "content": "未完成的契约会在梦境中追索记忆代价。"},
    ).json()
    assert updated_fact["data"]["world_fact"]["confidence"] == 0.88

    generated = client.post(
        f"/api/projects/{project_id}/settings/generate",
        json={"target": "all", "instruction": "补充第一卷可用的盟友、地点和禁忌。", "count": 2},
    )
    assert generated.status_code == 200
    generated_payload = generated.json()
    assert_success_envelope(generated_payload)
    assert generated_payload["data"]["job"]["status"] == "succeeded"
    assert len(generated_payload["data"]["characters"]) == 2
    assert len(generated_payload["data"]["entities"]) == 2
    assert len(generated_payload["data"]["world_facts"]) == 2

    graph = client.get(f"/api/projects/{project_id}/graph").json()
    labels = {node["label"] for node in graph["data"]["graph"]["nodes"]}
    assert {"沈砚", "裂纹铜印", "契约反噬"}.issubset(labels)


def test_agent_assisted_settings_generation_calls_llm_client(monkeypatch) -> None:
    class FakeLLMClient:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str | None]] = []

        def generate(self, system_prompt: str, user_prompt: str, model: str | None = None):
            payload = json.loads(user_prompt)
            agent_name = payload["agent_name"]
            self.calls.append((agent_name, model))
            if agent_name == "chief_architect":
                content = {"characters": [{"name": "远程盟友", "summary": "真实 API 生成的角色候选。"}]}
            else:
                content = {
                    "entities": [{"name": "远程地点", "description": "真实 API 生成的地点候选。"}],
                    "world_facts": [{"title": "远程禁忌", "content": "真实 API 生成的世界规则。"}],
                }
            return SimpleNamespace(
                content=json.dumps(content, ensure_ascii=False),
                provider="fake-provider",
                model=model or "fake-settings-model",
                used_remote_model=True,
            )

    reset_database()
    fake_llm = FakeLLMClient()
    monkeypatch.setattr(studio_service_module, "llm_client", fake_llm)
    client = TestClient(app)
    created = client.post(
        "/api/projects",
        json={
            "title": "设定 API 接线",
            "genre": "都市",
            "target_reader": "类型小说读者",
            "premise": "主角发现城市禁忌。",
            "style_guide": "",
            "language": "zh-CN",
            "planned_chapter_count": 10,
            "chapter_word_target": 1500,
        },
    ).json()
    project_id = created["data"]["project"]["id"]

    generated = client.post(
        f"/api/projects/{project_id}/settings/generate",
        json={"target": "all", "instruction": "补全候选设定。", "count": 1, "model": "unit-settings-model"},
    )

    assert generated.status_code == 200
    data = generated.json()["data"]
    assert ("chief_architect", "unit-settings-model") in fake_llm.calls
    assert ("canon_curator", "unit-settings-model") in fake_llm.calls
    assert data["characters"][0]["name"] == "远程盟友"
    assert data["entities"][0]["name"] == "远程地点"
    assert data["world_facts"][0]["title"] == "远程禁忌"
    runs = client.get(f"/api/jobs/{data['job']['id']}/agent-runs").json()["data"]["agent_runs"]
    assert all(run["output_payload"]["_llm"]["used_remote_model"] for run in runs)


def test_agent_assisted_settings_preview_does_not_persist_candidates() -> None:
    reset_database()
    client = TestClient(app)
    created = client.post(
        "/api/projects",
        json={
            "title": "设定预览",
            "genre": "玄幻",
            "target_reader": "喜欢设定严谨的读者",
            "premise": "主角进入一座会审判谎言的城。",
            "style_guide": "",
            "language": "zh-CN",
            "planned_chapter_count": 20,
            "chapter_word_target": 2000,
        },
    ).json()
    project_id = created["data"]["project"]["id"]
    before_characters = client.get(f"/api/projects/{project_id}/characters").json()["data"]["characters"]
    before_entities = client.get(f"/api/projects/{project_id}/entities").json()["data"]["entities"]
    before_facts = client.get(f"/api/projects/{project_id}/world-facts").json()["data"]["world_facts"]
    before_graph_nodes = client.get(f"/api/projects/{project_id}/graph").json()["data"]["graph"]["nodes"]

    preview = client.post(
        f"/api/projects/{project_id}/settings/generate",
        json={"target": "all", "instruction": "只预览候选设定，暂不入库。", "count": 2, "preview_only": True},
    )

    assert preview.status_code == 200
    payload = preview.json()
    assert_success_envelope(payload)
    data = payload["data"]
    assert data["preview_only"] is True
    assert len(data["characters"]) == 2
    assert len(data["entities"]) == 2
    assert len(data["world_facts"]) == 2

    assert client.get(f"/api/projects/{project_id}/characters").json()["data"]["characters"] == before_characters
    assert client.get(f"/api/projects/{project_id}/entities").json()["data"]["entities"] == before_entities
    assert client.get(f"/api/projects/{project_id}/world-facts").json()["data"]["world_facts"] == before_facts
    assert client.get(f"/api/projects/{project_id}/graph").json()["data"]["graph"]["nodes"] == before_graph_nodes


def test_workflows_project_delete_and_foreshadowing_lifecycle() -> None:
    reset_database()
    client = TestClient(app)
    created = client.post(
        "/api/projects",
        json={
            "title": "伏笔测试",
            "genre": "悬疑奇幻",
            "target_reader": "喜欢伏笔回收和人物反转的读者",
            "premise": "主角收到一枚只在梦中发光的旧钥匙。",
            "style_guide": "克制、悬疑、强调线索公平。",
            "language": "zh-CN",
            "planned_chapter_count": 20,
            "chapter_word_target": 2000,
        },
    ).json()
    project_id = created["data"]["project"]["id"]

    workflows = client.get("/api/workflows")
    assert workflows.status_code == 200
    workflows_payload = workflows.json()
    assert_success_envelope(workflows_payload)
    workflow_keys = {workflow["id"] for workflow in workflows_payload["data"]["workflows"]}
    assert {"initialization", "chapter_draft", "batch_generation", "outline_debate_engine"}.issubset(workflow_keys)
    agents_payload = client.get("/api/agents").json()
    assert_success_envelope(agents_payload)
    formal_agent_names = {agent["name"] for agent in agents_payload["data"]["agents"]}
    creation_workflow = next(workflow for workflow in workflows_payload["data"]["workflows"] if workflow["id"] == "creation_star_session")
    creation_nodes = {node["id"]: node for node in creation_workflow["nodes"]}
    for node_id, prompt_id in {
        "worldview_cards": "creation_worldview_draw",
        "protagonist_cards": "creation_protagonist_draw",
        "market_position": "creation_title_packaging",
    }.items():
        node = creation_nodes[node_id]
        assert node["type"] == "prompt"
        assert node["node_subtype"] == "prompt_agent"
        assert node["prompt_id"] == prompt_id
        assert node["agent_name"] == prompt_id
        assert node["configurable"] is True
    for workflow in workflows_payload["data"]["workflows"]:
        for node in workflow["nodes"]:
            agent_name = node.get("agent_name")
            if node["type"] == "agent":
                assert agent_name in formal_agent_names or node.get("node_subtype") == "runtime_agent"
                if agent_name not in formal_agent_names:
                    assert node["configurable"] is False
                    assert node["editable"] is False
            if agent_name in {"creation_worldview_draw", "creation_protagonist_draw", "creation_title_packaging"}:
                assert node["type"] == "prompt"
                assert node["configurable"] is True
    debate_workflow = next(workflow for workflow in workflows_payload["data"]["workflows"] if workflow["id"] == "outline_debate_engine")
    debate_node_ids = {node["id"] for node in debate_workflow["nodes"]}
    assert {"debate_book", "debate_volumes", "debate_chapters", "debate_character_generator", "debate_setting_generator"}.issubset(debate_node_ids)
    assert all(
        node.get("node_subtype") == "runtime_agent" and node["configurable"] is False
        for node in debate_workflow["nodes"]
        if str(node.get("agent_name") or "").startswith("outline_debate/")
    )
    assert any(edge["source"] == "debate_book" and edge["target"] == "debate_volumes" for edge in debate_workflow["edges"])
    draft_workflow = next(workflow for workflow in workflows_payload["data"]["workflows"] if workflow["id"] == "chapter_draft")
    draft_node_ids = {node["id"] for node in draft_workflow["nodes"]}
    assert {"canon_context", "quality_gate", "revise_draft", "canon_curator"}.issubset(draft_node_ids)

    character = client.post(
        f"/api/projects/{project_id}/characters",
        json={"name": "许临", "role_type": "protagonist", "importance_level": "core", "importance_score": 95},
    ).json()["data"]["character"]
    entity = client.post(
        f"/api/projects/{project_id}/entities",
        json={"entity_type": "item", "name": "旧钥匙", "importance_level": "major", "importance_score": 84},
    ).json()["data"]["entity"]
    chapter_id = client.post(
        f"/api/projects/{project_id}/chapters",
        json={"volume_no": 1, "title": "第1章：旧钥匙", "outline": "建立钥匙线索。", "word_target": 1200},
    ).json()["data"]["chapter"]["id"]
    payoff_chapter_id = client.post(
        f"/api/projects/{project_id}/chapters",
        json={"volume_no": 1, "title": "第2章：梦境回响", "outline": "建立梦境线索。", "word_target": 1200},
    ).json()["data"]["chapter"]["id"]

    suggestions = client.post(
        "/api/tools/foreshadowing",
        json={"project_id": project_id, "chapter_id": chapter_id, "instruction": "围绕旧钥匙预埋三条可回收伏笔。"},
    )
    assert suggestions.status_code == 200
    suggestions_payload = suggestions.json()
    assert_success_envelope(suggestions_payload)
    assert len(suggestions_payload["data"]["suggestions"]) == 3
    assert client.get(f"/api/projects/{project_id}/foreshadowing").json()["data"]["foreshadowing_items"] == []

    created_hook = client.post(
        f"/api/projects/{project_id}/foreshadowing",
        json={
            "chapter_id": chapter_id,
            "content": "旧钥匙只在无月夜的梦里发光。",
            "planted_chapter_id": chapter_id,
            "planned_payoff_chapter_id": payoff_chapter_id,
            "planned_payoff": "第二章揭示钥匙光芒来自失踪者的记忆残片。",
            "payoff_status": "planted",
            "importance_level": "major",
            "importance_score": 88,
            "related_character_ids": [character["id"]],
            "related_entity_ids": [entity["id"]],
            "source": "manual",
        },
    )
    assert created_hook.status_code == 200
    hook_payload = created_hook.json()
    assert_success_envelope(hook_payload)
    hook_id = hook_payload["data"]["foreshadowing_item"]["id"]

    listed = client.get(f"/api/projects/{project_id}/foreshadowing").json()
    assert len(listed["data"]["foreshadowing_items"]) == 1
    assert listed["data"]["foreshadowing_items"][0]["payoff_status"] == "planted"

    updated = client.put(
        f"/api/projects/{project_id}/foreshadowing/{hook_id}",
        json={"importance_score": 91, "planned_payoff": "第二章用记忆残片回收钥匙发光。"},
    ).json()
    assert updated["data"]["foreshadowing_item"]["importance_score"] == 91

    paid_off = client.post(
        f"/api/projects/{project_id}/foreshadowing/{hook_id}/payoff",
        json={"actual_payoff_chapter_id": payoff_chapter_id, "payoff_note": "第二章已回收钥匙光芒。"},
    ).json()
    assert paid_off["data"]["foreshadowing_item"]["payoff_status"] == "paid_off"
    assert paid_off["data"]["foreshadowing_item"]["actual_payoff_chapter_id"] == payoff_chapter_id

    graph = client.get(f"/api/projects/{project_id}/graph").json()
    graph_labels = {node["label"] for node in graph["data"]["graph"]["nodes"]}
    assert "旧钥匙只在无月夜的梦里发光。" in graph_labels
    assert graph["data"]["graph"]["edges"]

    deleted_hook = client.delete(f"/api/projects/{project_id}/foreshadowing/{hook_id}")
    assert deleted_hook.status_code == 200
    assert client.get(f"/api/projects/{project_id}/foreshadowing").json()["data"]["foreshadowing_items"] == []

    delete_project = client.delete(f"/api/projects/{project_id}")
    assert delete_project.status_code == 200
    projects_after_delete = client.get("/api/projects").json()["data"]["projects"]
    assert project_id not in {project["id"] for project in projects_after_delete}
