import json
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.db import models
from app.db.session import Base, engine
from app.db.session import SessionLocal
from app.main import app
import app.services.studio_service as studio_service_module


def reset_database() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def assert_success(response) -> dict:
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["error"] is None
    return payload["data"]


def assert_validation_error(response) -> dict:
    assert response.status_code == 400
    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "VALIDATION_ERROR"
    return payload["error"]


def patch_creation_session_state(session_id: str, patch: dict) -> None:
    db = SessionLocal()
    try:
        session = db.get(models.CreationSession, session_id)
        assert session is not None
        state = json.loads(session.state_json or "{}")
        state.update(patch)
        session.state_json = json.dumps(state, ensure_ascii=False)
        db.commit()
    finally:
        db.close()


def create_project(client: TestClient) -> str:
    data = assert_success(
        client.post(
            "/api/projects",
            json={
                "title": "创作 Star 测试",
                "genre": "待定",
                "target_reader": "类型小说读者",
                "premise": "先通过抽卡确定作品方向。",
                "style_guide": "节奏清晰。",
                "language": "zh-CN",
                "planned_chapter_count": 80,
                "chapter_word_target": 2200,
            },
        )
    )
    return data["project"]["id"]


def test_creation_star_options_draw_and_commit_flow() -> None:
    reset_database()
    client = TestClient(app)
    project_id = create_project(client)

    agents = assert_success(client.get("/api/agents"))["agents"]
    creation_star = next(item for item in agents if item["name"] == "creation_star")
    assert "抽卡" in creation_star["prompt"]
    assert "立项" in creation_star["prompt"]
    assert "前序环节" in creation_star["prompt"]
    assert "书名" in creation_star["prompt"]

    options = assert_success(client.get("/api/creation-star/options"))["options"]
    assert "男频" in options["channels"]
    assert "女频" in options["channels"]
    assert "玄幻" in options["genres"]
    assert "古言" in options["genres"]
    assert "强者归来" in options["tags"]
    assert "破镜重圆" in options["tags"]
    assert options["sources"]

    basic_info = {
        "channel": "男频",
        "genre": "都市",
        "subgenres": ["高武", "灵气复苏"],
        "tags": ["学院流", "升级流", "幕后流"],
        "manual_tags": ["武道高考"],
        "target_reader": "喜欢都市高武和宗门财阀化的读者",
        "target_words": 1200000,
        "style": "热血悬疑",
        "initial_idea": "现代都市里，古老宗门变成顶级教育集团。",
    }

    worldview_payload = assert_success(
        client.post(
            f"/api/projects/{project_id}/creation-star/draw",
            json={"step": "worldview", "basic_info": basic_info, "count": 9},
        )
    )
    assert worldview_payload["job"]["job_type"] == "creation_star_draw"
    assert worldview_payload["step"] == "worldview"
    assert worldview_payload["draw_id"]
    assert "现代都市里" in worldview_payload["prompt_snapshot"]["context_summary"]
    assert "世界观候选卡" in worldview_payload["prompt_snapshot"]["step_prompt"]
    assert worldview_payload["prompt_snapshot"]["generation_settings"]["temperature"] == 0.9
    assert "core_rule" in worldview_payload["prompt_snapshot"]["output_schema"]["cards"][0]
    assert len(worldview_payload["cards"]) == 9
    assert worldview_payload["cards"][0]["title"]
    assert worldview_payload["cards"][0]["tags"]
    assert worldview_payload["cards"][0]["core_rule"]
    assert worldview_payload["cards"][0]["social_pressure"]
    assert worldview_payload["cards"][0]["protagonist_entry"]
    assert worldview_payload["cards"][0]["long_form_potential"]
    assert worldview_payload["cards"][0]["reader_hooks"]

    refreshed_worldview_payload = assert_success(
        client.post(
            f"/api/projects/{project_id}/creation-star/draw",
            json={"step": "worldview", "basic_info": basic_info, "count": 9},
        )
    )
    assert refreshed_worldview_payload["draw_id"] != worldview_payload["draw_id"]
    assert refreshed_worldview_payload["cards"] != worldview_payload["cards"]

    selected_worldview = worldview_payload["cards"][0]
    protagonist_payload = assert_success(
        client.post(
            f"/api/projects/{project_id}/creation-star/draw",
            json={
                "step": "protagonist",
                "basic_info": basic_info,
                "selected_worldview": selected_worldview,
                "count": 6,
            },
        )
    )
    assert len(protagonist_payload["cards"]) == 6
    assert selected_worldview["title"] in protagonist_payload["prompt_snapshot"]["context_summary"]
    protagonist = protagonist_payload["cards"][0]
    assert protagonist["name"]
    assert protagonist["long_term_goal"]

    bible_payload = assert_success(
        client.post(
            f"/api/projects/{project_id}/creation-star/draw",
            json={
                "step": "project_bible",
                "basic_info": basic_info,
                "selected_worldview": selected_worldview,
                "selected_protagonist": protagonist,
                "count": 3,
            },
        )
    )
    assert bible_payload["project_bible"]["核心命题"]
    assert protagonist["name"] in bible_payload["prompt_snapshot"]["context_summary"]
    assert bible_payload["world_rules"]["力量体系"]
    assert bible_payload["world_rules"]["不可违反设定"]

    title_payload = assert_success(
        client.post(
            f"/api/projects/{project_id}/creation-star/draw",
            json={
                "step": "title",
                "basic_info": basic_info,
                "selected_worldview": selected_worldview,
                "selected_protagonist": protagonist,
                "project_bible": bible_payload["project_bible"],
                "world_rules": bible_payload["world_rules"],
                "count": 6,
            },
        )
    )
    assert title_payload["step"] == "title"
    assert selected_worldview["title"] in title_payload["prompt_snapshot"]["context_summary"]
    assert protagonist["name"] in title_payload["prompt_snapshot"]["context_summary"]
    assert bible_payload["project_bible"]["核心命题"][:18] in title_payload["prompt_snapshot"]["context_summary"]
    assert len(title_payload["cards"]) == 6
    assert title_payload["cards"][0]["title"]

    custom_title = {
        "id": "custom_title",
        "title": "我自定义的创作 Star 书名",
        "description": "作者手动输入并写入项目标题。",
        "tags": ["自定义"],
        "source": "manual",
    }
    committed = assert_success(
        client.post(
            f"/api/projects/{project_id}/creation-star/commit",
            json={
                "basic_info": basic_info,
                "selected_worldview": selected_worldview,
                "selected_protagonist": protagonist,
                "project_bible": bible_payload["project_bible"],
                "world_rules": bible_payload["world_rules"],
                "selected_title": custom_title,
                "user_note": "确认创作 Star 抽卡",
            },
        )
    )
    assert committed["project"]["title"] == custom_title["title"]
    assert committed["project"]["genre"] == "都市"
    assert committed["story_bible"]["world_setting"]
    assert committed["character"]["role_type"] == "protagonist"
    assert len(committed["world_facts"]) >= 6
    assert len(committed["entities"]) >= 1
    assert committed["version"]["agent_name"] == "creation_star"

    state = assert_success(client.get(f"/api/projects/{project_id}/state"))["state"]
    assert state["project"]["initial_idea"] == basic_info["initial_idea"]
    assert any(character["name"] == protagonist["name"] for character in state["characters"])
    assert any(fact["title"] == "核心命题" for fact in state["world_facts"])


def test_creation_session_decoupled_steps_and_single_card_loading() -> None:
    reset_database()
    client = TestClient(app)
    project_id = create_project(client)
    basic_info = {
        "channel": "男频",
        "genre": "都市",
        "subgenres": ["高武"],
        "tags": ["学院流", "升级流"],
        "target_reader": "喜欢高武升级和旧案悬疑的读者",
        "target_words": 1200000,
        "style": "热血悬疑",
        "initial_idea": "宗门变成教育集团，主角从武考旧案里翻身。",
    }

    session_payload = assert_success(
        client.post(
            f"/api/projects/{project_id}/creation/sessions",
            json={"basic_info": basic_info},
        )
    )
    session = session_payload["session"]
    session_id = session["id"]
    assert session["current_step"] == "brief"
    assert session["basic_info"]["genre"] == "都市"

    first_worldview = assert_success(
        client.post(
            f"/api/projects/{project_id}/creation/sessions/{session_id}/worldviews",
            json={"count": 1},
        )
    )
    assert len(first_worldview["cards"]) == 1
    assert len(first_worldview["session"]["state"]["worldview_candidates"]) == 1
    assert first_worldview["job"]["job_type"] == "creation_worldview_card"

    second_worldview = assert_success(
        client.post(
            f"/api/projects/{project_id}/creation/sessions/{session_id}/worldviews",
            json={"count": 1, "manual_input": "更强调榜单压迫"},
        )
    )
    assert len(second_worldview["cards"]) == 1
    assert len(second_worldview["session"]["state"]["worldview_candidates"]) == 2
    assert first_worldview["cards"][0]["title"] in second_worldview["prompt_snapshot"]["previous_cards_summary"]
    assert second_worldview["cards"][0]["core_rule"]
    replacement_worldview = assert_success(
        client.post(
            f"/api/projects/{project_id}/creation/sessions/{session_id}/worldviews",
            json={"count": 1, "manual_input": "完全换一批世界观", "replace_existing": True},
        )
    )
    assert len(replacement_worldview["cards"]) == 1
    assert len(replacement_worldview["session"]["state"]["worldview_candidates"]) == 1
    assert replacement_worldview["session"]["state"]["selected_worldview"]["id"] == replacement_worldview["cards"][0]["id"]
    assert replacement_worldview["session"]["state"]["protagonist_candidates"] == []
    assert replacement_worldview["session"]["state"]["title_candidates"] == []
    assert replacement_worldview["session"]["state"]["project_seed"] == {}
    assert replacement_worldview["prompt_snapshot"]["previous_cards_summary"] == "无上一批候选。"
    selected_worldview = replacement_worldview["cards"][0]

    protagonist_payload = assert_success(
        client.post(
            f"/api/projects/{project_id}/creation/sessions/{session_id}/protagonists",
            json={"count": 1, "selected_worldview": selected_worldview},
        )
    )
    assert len(protagonist_payload["cards"]) == 1
    assert protagonist_payload["session"]["state"]["selected_worldview"]["id"] == selected_worldview["id"]
    selected_protagonist = protagonist_payload["cards"][0]

    market_payload = assert_success(
        client.post(
            f"/api/projects/{project_id}/creation/sessions/{session_id}/market-position",
            json={"count": 1, "selected_protagonist": selected_protagonist},
        )
    )
    assert len(market_payload["title_candidates"]) == 1
    assert len(market_payload["market_position_candidates"]) == 1
    selected_title = market_payload["title_candidates"][0]

    seed_payload = assert_success(
        client.post(
            f"/api/projects/{project_id}/creation/sessions/{session_id}/seed",
            json={
                "selected_worldview": selected_worldview,
                "selected_protagonist": selected_protagonist,
                "selected_title": selected_title,
                "user_note": "确认立项种子",
            },
        )
    )
    assert seed_payload["project_seed"]["selected_title"]["title"] == selected_title["title"]
    assert seed_payload["session"]["current_step"] == "seed"

    conflict_payload = assert_success(client.post(f"/api/projects/{project_id}/creation/sessions/{session_id}/core-conflict", json={}))
    assert conflict_payload["core_conflict_system"]["core_conflict"]
    assert conflict_payload["job"]["current_agent"] == "chief_architect"

    constitution_payload = assert_success(client.post(f"/api/projects/{project_id}/creation/sessions/{session_id}/constitution", json={}))
    assert constitution_payload["novel_constitution"]["core_narrative_engine"]

    review_payload = assert_success(client.post(f"/api/projects/{project_id}/creation/sessions/{session_id}/constitution-review", json={}))
    assert review_payload["constitution_review"]["status"] in {"passed", "passed_with_notes", "needs_revision", "blocked"}

    patch_creation_session_state(
        session_id,
        {"constitution_review": {"status": "blocked", "blocking_issues": ["核心矛盾无法支撑长篇"], "revision_suggestions": []}},
    )
    blocked_preview = client.post(f"/api/projects/{project_id}/creation/sessions/{session_id}/canon-preview", json={})
    error = assert_validation_error(blocked_preview)
    assert "小说宪法压力测试" in error["message"]

    patch_creation_session_state(session_id, {"constitution_review": {"status": "passed_with_notes", "blocking_issues": [], "revision_suggestions": []}})
    preview_payload = assert_success(client.post(f"/api/projects/{project_id}/creation/sessions/{session_id}/canon-preview", json={}))
    assert preview_payload["canon_candidates"]["story_bible_candidate"]["main_conflict"]
    assert preview_payload["canon_candidates"]["character_candidates"]
    assert preview_payload["canon_candidates"]["entity_candidates"]
    assert preview_payload["canon_candidates"]["graph_candidate_edges"]

    state_before_commit = assert_success(client.get(f"/api/projects/{project_id}/state"))["state"]
    assert not any(fact["title"] == "核心命题" for fact in state_before_commit["world_facts"])

    incomplete_approval = client.post(
        f"/api/projects/{project_id}/creation/sessions/{session_id}/commit",
        json={"user_note": "审批不完整", "approved_canon_sections": ["project", "story_bible"]},
    )
    approval_error = assert_validation_error(incomplete_approval)
    assert "正典审批项不完整" in approval_error["message"]

    committed = assert_success(
        client.post(
            f"/api/projects/{project_id}/creation/sessions/{session_id}/commit",
            json={
                "user_note": "确认解耦创作 Star 入库",
                "approved_canon_sections": ["project", "story_bible", "characters", "entities", "world_facts", "graph"],
            },
        )
    )
    assert committed["project"]["title"] == selected_title["title"]
    assert committed["story_bible"]["main_conflict"]
    assert committed["version"]["agent_name"] == "canon_curator"
    assert committed["session"]["status"] == "committed"


def test_creation_star_draw_calls_llm_client(monkeypatch) -> None:
    class FakeLLMClient:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str | None]] = []

        def generate(self, system_prompt: str, user_prompt: str, model: str | None = None):
            payload = json.loads(user_prompt)
            self.calls.append((payload["agent_name"], model))
            return SimpleNamespace(
                content=json.dumps(
                    {
                        "step": "worldview",
                        "cards": [
                            {
                                "id": "remote_world_1",
                                "title": "远程 API 世界观",
                                "description": "由真实 Agent 调用路径返回的世界观。",
                                "tags": ["远程"],
                                "selling_point": "验证创作 Star 接入统一 LLM Client。",
                                "conflict_hook": "远程冲突钩子。",
                                "risk": "测试风险。",
                                "source": "agent",
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                provider="fake-provider",
                model=model or "fake-star-model",
                used_remote_model=True,
            )

    reset_database()
    fake_llm = FakeLLMClient()
    monkeypatch.setattr(studio_service_module, "llm_client", fake_llm)
    client = TestClient(app)
    project_id = create_project(client)

    payload = assert_success(
        client.post(
            f"/api/projects/{project_id}/creation-star/draw",
            json={
                "step": "worldview",
                "basic_info": {"genre": "都市", "target_reader": "喜欢高概念的读者", "initial_idea": "规则会回应主角批注。"},
                "count": 3,
                "model": "unit-star-model",
            },
        )
    )

    assert fake_llm.calls == [("creation_star", "unit-star-model")]
    assert payload["cards"][0]["title"] == "远程 API 世界观"
    runs = assert_success(client.get(f"/api/jobs/{payload['job']['id']}/agent-runs"))["agent_runs"]
    assert runs[0]["agent_name"] == "creation_star"
    assert runs[0]["output_payload"]["_llm"]["used_remote_model"] is True
    assert runs[0]["output_payload"]["_llm"]["provider"] == "fake-provider"
