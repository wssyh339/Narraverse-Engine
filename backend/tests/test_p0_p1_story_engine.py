from __future__ import annotations

import json
import os
from types import SimpleNamespace

os.environ["DATABASE_URL"] = "sqlite:///./data/test_novel_agent.db"
os.environ["JOB_ARTIFACT_DIR"] = "backend/artifacts/test-runs"

from fastapi.testclient import TestClient

from app.agents.contracts import NovelStudioState
import app.agents.chapter_writing.workflow as chapter_workflow_module
from app.agents.chapter_writing.workflow import agent_workflow
from app.db import models
from app.db.session import Base, SessionLocal, engine
from app.main import app
from app.runtime.quality_gate import QualityGate
import app.services.studio_service as studio_service_module


def reset_database() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def assert_success_envelope(payload: dict) -> None:
    assert payload["success"] is True
    assert payload["error"] is None
    assert isinstance(payload["data"], dict)


class LocalFallbackLLM:
    def generate(self, _system_prompt: str, _user_prompt: str, model: str | None = None) -> SimpleNamespace:
        return SimpleNamespace(content="{}", provider="local_test", model=model or "local_test", used_remote_model=False)


def test_chapter_workflow_prepares_chapter_position_and_scene_word_budgets(monkeypatch) -> None:
    monkeypatch.setattr(chapter_workflow_module, "llm_client", LocalFallbackLLM())
    state = NovelStudioState(
        project_id="prj_prep",
        title="预算测试",
        genre="都市异能",
        target_words=100000,
        target_chapters=25,
        chapter_word_min=3600,
        chapter_word_max=4400,
        current_chapter=3,
        style_guide="动作承载信息，避免解释腔。",
        canon_context={
            "characters": [{"name": "许燃", "current_status": "刚被停职"}],
            "world_facts": [{"title": "异能备案制度", "content": "未备案能力者不得进入城区。"}],
            "story_entities": [{"name": "红色通行证", "entity_type": "item"}],
            "foreshadowing": [{"content": "通行证编号重复", "payoff_status": "planned"}],
            "previous_summaries": [{"chapter_no": 2, "summary": "许燃发现通行证编号重复。"}],
        },
        current_chapter_outline={
            "chapter_no": 3,
            "title": "红证过闸",
            "outline": "许燃冒险使用红色通行证进入城区。",
            "core_event": "红色通行证第一次暴露真实用途。",
            "conflict": "守卫系统识别出重复编号。",
            "plot_purpose": "让主角从被动调查转为主动越界。",
            "chapter_position": "推进",
            "target_emotion": "压迫后转为反击",
            "pressure_level": 7,
            "reader_pull_reason": "通行证为何能骗过第一道闸门但骗不过第二道。",
            "word_target": 4000,
        },
    )

    result = agent_workflow.run_chapter_draft(state)

    assert result.chapter_prep["chapter_position"] == "推进"
    assert result.chapter_prep["target_emotion"] == "压迫后转为反击"
    assert "红色通行证" in result.chapter_prep["required_canon"]
    assert result.chapter_card["chapter_position"] == "推进"
    assert result.chapter_card["target_emotion"] == "压迫后转为反击"
    assert result.chapter_card["word_budget"]["target"] == 4000
    scene_budgets = [scene["word_budget_min"] for scene in result.scene_outline["scenes"]]
    assert all(budget > 0 for budget in scene_budgets)
    assert sum(scene_budgets) >= 3600


def test_quality_gate_detects_degeneration_and_engineering_metadata() -> None:
    report = QualityGate().evaluate_text(
        "红证过闸\n\n作为AI，我无法继续写作。\n\n本章细纲要求主角推进伏笔。\n\n" + "重复。" * 40,
        chapter_title="红证过闸",
        minimum_words=200,
        target_words=400,
    )

    assert report["status"] == "needs_revision"
    assert report["blocking_issue_count"] >= 1
    categories = {issue["category"] for issue in report["issues"]}
    assert "model_refusal" in categories
    assert "engineering_metadata" in categories
    assert "repetition" in categories


def test_import_novel_rebuilds_existing_text_as_reviewable_project_material() -> None:
    reset_database()
    client = TestClient(app)
    created = client.post(
        "/api/projects",
        json={
            "title": "导入工程",
            "genre": "都市悬疑",
            "target_reader": "喜欢连续伏笔和案件反转的读者",
            "premise": "失业记者追查一张重复编号的通行证。",
            "style_guide": "克制、快节奏。",
            "language": "zh-CN",
            "planned_chapter_count": 25,
            "chapter_word_target": 4000,
        },
    )
    project_id = created.json()["data"]["project"]["id"]

    response = client.post(
        f"/api/projects/{project_id}/import/novel",
        json={
            "source_name": "红证样章",
            "text": "第1章 红证\n许燃收到一张编号重复的红色通行证。\n\n第2章 闸口\n他刷卡过闸，系统报警。",
            "target_platform": "qidian",
            "create_canon_proposals": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert_success_envelope(payload)
    data = payload["data"]
    assert data["import_report"]["chapter_count"] == 2
    assert data["chapters"][0]["title"] == "红证"
    assert data["chapters"][1]["chapter_no"] == 2
    assert data["reference_note"]["note_type"] == "import_report"
    assert data["canon_proposals"]

    db = SessionLocal()
    try:
        assert db.query(models.Chapter).filter(models.Chapter.project_id == project_id).count() == 2
        assert db.query(models.Note).filter(models.Note.project_id == project_id, models.Note.note_type == "import_report").count() == 1
        assert db.query(models.CanonChangeProposal).filter(models.CanonChangeProposal.project_id == project_id).count() >= 1
    finally:
        db.close()


def test_method_pack_and_reference_asset_are_reviewable_project_material() -> None:
    reset_database()
    client = TestClient(app)
    created = client.post(
        "/api/projects",
        json={
            "title": "方法包工程",
            "genre": "都市异能",
            "target_reader": "喜欢规则漏洞和连续反转的读者",
            "premise": "停职调查员用一张异常通行证拆开系统漏洞。",
            "style_guide": "动作先行，少解释。",
            "language": "zh-CN",
            "planned_chapter_count": 25,
            "chapter_word_target": 4000,
        },
    )
    project_id = created.json()["data"]["project"]["id"]

    pack_response = client.post(
        f"/api/projects/{project_id}/method-packs",
        json={
            "name": "都市规则漏洞方法包",
            "source": "oh-story-claudecode 参考拆解",
            "genre": "都市异能",
            "principles": ["每章必须改变局势", "规则漏洞必须带代价"],
            "chapter_recipe": ["开场压力", "发现异常", "选择越界", "付出代价", "章末新问题"],
            "style_rules": ["动作承载信息", "少用解释性旁白"],
            "anti_patterns": ["章节只复述设定", "AI 工程术语进入正文"],
        },
    )

    assert pack_response.status_code == 200
    pack = pack_response.json()["data"]["method_pack"]
    assert pack["note_type"] == "method_pack"
    pack_content = json.loads(pack["content"])
    assert pack_content["chapter_recipe"][0] == "开场压力"
    assert pack_content["anti_patterns"]

    asset_response = client.post(
        f"/api/projects/{project_id}/reference-assets",
        json={
            "title": "对标第一章",
            "asset_type": "chapter_excerpt",
            "source_name": "参考样章",
            "text": "第1章 红证\n许燃在雨夜收到红证。\n“别刷。”同事压低声音。\n他还是把卡贴上闸机。",
            "tags": ["开局", "压力"],
            "method_pack_id": pack["id"],
        },
    )

    assert asset_response.status_code == 200
    asset_data = asset_response.json()["data"]
    asset = asset_data["reference_asset"]
    assert asset["note_type"] == "reference_asset"
    assert asset_data["analysis"]["chapter_heading_count"] == 1
    assert asset_data["analysis"]["dialogue_line_count"] == 1

    list_response = client.get(f"/api/projects/{project_id}/reference-assets")
    listed = list_response.json()["data"]["reference_assets"]
    assert [row["id"] for row in listed] == [asset["id"]]


def test_review_mode_plan_uses_expected_agents_and_quality_gates() -> None:
    reset_database()
    client = TestClient(app)
    created = client.post(
        "/api/projects",
        json={
            "title": "审稿模式工程",
            "genre": "都市悬疑",
            "target_reader": "喜欢长线伏笔和因果反转的读者",
            "premise": "记者追查重复编号通行证。",
            "style_guide": "克制、具体。",
            "language": "zh-CN",
            "planned_chapter_count": 25,
            "chapter_word_target": 4000,
        },
    )
    project_id = created.json()["data"]["project"]["id"]
    chapter = client.post(
        f"/api/projects/{project_id}/chapters",
        json={"volume_no": 1, "title": "第1章：红证", "outline": "主角收到红证。", "word_target": 4000},
    ).json()["data"]["chapter"]

    response = client.post(
        f"/api/projects/{project_id}/review/plan",
        json={
            "mode": "full",
            "scope": "chapter",
            "chapter_id": chapter["id"],
            "instruction": "检查是否能支撑 10 万字展开",
        },
    )

    assert response.status_code == 200
    plan = response.json()["data"]["review_plan"]
    assert plan["mode"] == "full"
    assert plan["human_approval_required"] is True
    assert plan["agents"] == ["reviewer", "fact_checker", "style_unifier", "canon_curator", "chapter_planner"]
    assert "deterministic_quality_gate" in plan["quality_gates"]
    assert any(step["agent"] == "canon_curator" for step in plan["steps"])


def test_chapter_draft_persists_quality_gate_report(monkeypatch) -> None:
    reset_database()
    client = TestClient(app)
    created = client.post(
        "/api/projects",
        json={
            "title": "质量门持久化",
            "genre": "都市异能",
            "target_reader": "喜欢强冲突和规则漏洞的读者",
            "premise": "停职调查员发现通行证系统有漏洞。",
            "style_guide": "直接、具体。",
            "language": "zh-CN",
            "planned_chapter_count": 25,
            "chapter_word_target": 4000,
        },
    )
    project_id = created.json()["data"]["project"]["id"]
    chapter = client.post(
        f"/api/projects/{project_id}/chapters",
        json={"volume_no": 1, "title": "红证过闸", "outline": "许燃刷卡过闸。", "word_target": 4000},
    ).json()["data"]["chapter"]

    deterministic_report = QualityGate().evaluate_text(
        "红证过闸\n\n作为AI，我无法继续写作。",
        chapter_title="红证过闸",
        minimum_words=1,
        target_words=4000,
    )

    def fake_stream(state: NovelStudioState):
        yield state.model_copy(
            update={
                "current_agent": "canon_curator",
                "chapter_prep": {"chapter_position": "推进", "target_emotion": "压迫"},
                "chapter_card": {"chapter_title": "红证过闸", "word_budget": {"target": 4000, "minimum": 1}},
                "scene_outline": {"scenes": [{"scene_no": 1, "goal": "刷卡"}]},
                "integrated_draft": "红证过闸\n\n作为AI，我无法继续写作。",
                "review_notes": [],
                "fact_check_report": {"status": "passed", "issues": []},
                "quality_gate": deterministic_report,
                "health_check_report": {},
                "style_polished_text": "许燃刷卡过闸，警报响了。",
                "final_chapter_text": "许燃刷卡过闸，警报响了。",
                "chapter_summary": "许燃触发闸机警报。",
                "narrative_ledger": {"chapter_summary": "许燃触发闸机警报。"},
                "candidate_canon_updates": {},
                "canon_updates": {},
            }
        )

    monkeypatch.setattr(studio_service_module.chapter_writing_service, "stream_chapter_draft", fake_stream)

    response = client.post(
        f"/api/projects/{project_id}/chapters/{chapter['id']}/draft",
        json={"user_instruction": "生成正文", "idempotency_key": "quality-report-persist"},
    )

    assert response.status_code == 200
    db = SessionLocal()
    try:
        report = db.query(models.QualityReport).filter(models.QualityReport.project_id == project_id).one()
        issues = db.query(models.QualityIssue).filter(models.QualityIssue.report_id == report.id).all()
        assert report.status == "needs_revision"
        assert report.blocking_issue_count >= 1
        assert {issue.category for issue in issues} >= {"model_refusal"}
    finally:
        db.close()
