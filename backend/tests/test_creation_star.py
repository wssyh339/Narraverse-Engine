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


def add_unrelated_graph_edge(project_id: str) -> str:
    db = SessionLocal()
    try:
        source = models.GraphNode(
            id="gn_existing_source",
            project_id=project_id,
            node_type="entity",
            ref_id="existing_source",
            label="旧势力",
            importance_level="medium",
            importance_score=50,
        )
        target = models.GraphNode(
            id="gn_existing_target",
            project_id=project_id,
            node_type="entity",
            ref_id="existing_target",
            label="旧地点",
            importance_level="medium",
            importance_score=50,
        )
        edge = models.GraphEdge(
            id="ged_existing_unrelated",
            project_id=project_id,
            source_node_id=source.id,
            target_node_id=target.id,
            edge_type="manual_relation",
            label="旧关系",
            importance_score=40,
            confidence=0.7,
            evidence="提交创作 Star 前已存在的人工关系。",
        )
        db.add_all([source, target])
        db.flush()
        db.add(edge)
        db.commit()
        return edge.id
    finally:
        db.close()


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
        "volume_count": 10,
        "chapter_count": 400,
        "chapter_word_min": 2400,
        "chapter_word_max": 3600,
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
    assert session["basic_info"]["target_words"] == 1200000
    assert session["basic_info"]["volume_count"] == 10
    assert session["basic_info"]["chapter_count"] == 400
    assert session["basic_info"]["chapter_word_target"] == 3000
    assert session["basic_info"]["chapters_per_volume"] == 40
    project_after_session = assert_success(client.get(f"/api/projects/{project_id}"))["project"]
    assert project_after_session["target_words"] == 1200000
    assert project_after_session["planned_volume_count"] == 10
    assert project_after_session["planned_chapter_count"] == 400
    assert project_after_session["chapters_per_volume"] == 40
    assert project_after_session["chapter_word_target"] == 3000

    first_worldview = assert_success(
        client.post(
            f"/api/projects/{project_id}/creation/sessions/{session_id}/worldviews",
            json={"count": 1},
        )
    )
    assert len(first_worldview["cards"]) == 1
    assert first_worldview["session"]["state"]["worldview_candidates_count"] == 1
    assert "worldview_candidates" not in first_worldview["session"]["state"]
    assert first_worldview["job"]["job_type"] == "creation_worldview_card"
    assert first_worldview["job"]["result"]["_llm"]["elapsed_ms"] >= 0

    second_worldview = assert_success(
        client.post(
            f"/api/projects/{project_id}/creation/sessions/{session_id}/worldviews",
            json={"count": 1, "manual_input": "更强调榜单压迫"},
        )
    )
    assert len(second_worldview["cards"]) == 1
    assert second_worldview["session"]["state"]["worldview_candidates_count"] == 2
    assert first_worldview["cards"][0]["title"] in second_worldview["prompt_snapshot"]["previous_cards_summary"]
    assert second_worldview["cards"][0]["core_rule"]
    replacement_worldview = assert_success(
        client.post(
            f"/api/projects/{project_id}/creation/sessions/{session_id}/worldviews",
            json={"count": 1, "manual_input": "完全换一批世界观", "replace_existing": True},
        )
    )
    assert len(replacement_worldview["cards"]) == 1
    assert replacement_worldview["session"]["state"]["worldview_candidates_count"] == 1
    assert replacement_worldview["session"]["state"]["selected_worldview_id"] == replacement_worldview["cards"][0]["id"]
    assert replacement_worldview["session"]["state"]["protagonist_candidates_count"] == 0
    assert replacement_worldview["session"]["state"]["title_candidates_count"] == 0
    assert replacement_worldview["session"]["state"]["has_project_seed"] is False
    assert replacement_worldview["prompt_snapshot"]["previous_cards_summary"] == "无上一批候选。"
    selected_worldview = replacement_worldview["cards"][0]

    protagonist_payload = assert_success(
        client.post(
            f"/api/projects/{project_id}/creation/sessions/{session_id}/protagonists",
            json={"count": 1, "selected_worldview": selected_worldview},
        )
    )
    assert len(protagonist_payload["cards"]) == 1
    assert protagonist_payload["session"]["state"]["selected_worldview_id"] == selected_worldview["id"]
    selected_protagonist = protagonist_payload["cards"][0]

    market_payload = assert_success(
        client.post(
            f"/api/projects/{project_id}/creation/sessions/{session_id}/market-position",
            json={"count": 1, "selected_protagonist": selected_protagonist},
        )
    )
    assert len(market_payload["title_candidates"]) == 1
    assert market_payload["market_position_candidates"] == []
    assert market_payload["prompt_snapshot"]["prompt_id"] == "creation_title_packaging"
    selected_title = market_payload["title_candidates"][0]
    assert "core_selling_point" in selected_title
    assert "reader_expectation" in selected_title
    assert market_payload["session"]["state"]["market_position_source"] == "title_packaging"

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
    unrelated_edge_id = add_unrelated_graph_edge(project_id)

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
    assert committed["project"]["target_words"] == 1200000
    assert committed["project"]["planned_volume_count"] == 10
    assert committed["project"]["planned_chapter_count"] == 400
    assert committed["project"]["chapters_per_volume"] == 40
    assert committed["project"]["chapter_word_target"] == 3000
    assert committed["project"]["chapter_word_min"] == 2400
    assert committed["project"]["chapter_word_max"] == 3600
    assert committed["story_bible"]["main_conflict"]
    assert committed["version"]["agent_name"] == "canon_curator"
    assert committed["session"]["status"] == "committed"
    state_after_commit = assert_success(client.get(f"/api/projects/{project_id}/state"))["state"]
    character_names = [character["name"] for character in state_after_commit["characters"]]
    assert selected_protagonist["name"] in character_names
    assert "待定主角" not in character_names
    assert len([name for name in character_names if name == selected_protagonist["name"]]) == 1

    profile = assert_success(client.get(f"/api/projects/{project_id}/creation/profile"))
    assert profile["project"]["title"] == selected_title["title"]
    assert profile["story_bible"]["main_conflict"]
    assert profile["creation_session"]["id"] == session_id
    assert profile["creation_session"]["status"] == "committed"
    creation_profile = profile["creation_profile"]
    assert creation_profile["basic_info"]["genre"] == "都市"
    assert creation_profile["basic_info"]["target_words"] == 1200000
    assert creation_profile["selected_worldview"]["title"] == selected_worldview["title"]
    assert creation_profile["selected_protagonist"]["name"] == selected_protagonist["name"]
    assert creation_profile["selected_title"]["title"] == selected_title["title"]
    assert creation_profile["market_position"]["source"] == "title_packaging"
    assert creation_profile["project_seed"]["selected_title"]["title"] == selected_title["title"]
    assert creation_profile["core_conflict_system"]["core_conflict"]
    assert creation_profile["novel_constitution"]["core_narrative_engine"]
    assert creation_profile["constitution_review"]["status"] == "passed_with_notes"
    assert creation_profile["canon_candidates"]["story_bible_candidate"]["main_conflict"]
    assert creation_profile["confirmed_canon"]["core_conflict_system"]["core_conflict"]

    db = SessionLocal()
    try:
        unrelated_versions = (
            db.query(models.CanonVersion)
            .filter(
                models.CanonVersion.project_id == project_id,
                models.CanonVersion.ref_type == "graph_edge",
                models.CanonVersion.ref_id == unrelated_edge_id,
            )
            .all()
        )
        creation_edge_versions = (
            db.query(models.CanonVersion)
            .join(models.GraphEdge, models.GraphEdge.id == models.CanonVersion.ref_id)
            .filter(
                models.CanonVersion.project_id == project_id,
                models.CanonVersion.ref_type == "graph_edge",
                models.GraphEdge.edge_type.in_(["creation_star_related", "driven_by"]),
            )
            .all()
        )
    finally:
        db.close()
    assert unrelated_versions == []
    assert creation_edge_versions


def test_creation_star_draw_calls_llm_client(monkeypatch) -> None:
    class FakeLLMClient:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str | None, str, dict]] = []

        def generate(self, system_prompt: str, user_prompt: str, model: str | None = None):
            payload = json.loads(user_prompt)
            self.calls.append((payload["agent_name"], model, system_prompt, payload["context"]))
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
                                "conflict_engine_seed": "只提供冲突发动机种子，不生成核心矛盾系统。",
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

    assert fake_llm.calls[0][0] == "creation_worldview_draw"
    assert fake_llm.calls[0][1] == "unit-star-model"
    assert "长篇小说世界观抽卡 Agent" in fake_llm.calls[0][2]
    assert "请帮我设计一部长篇小说的核心矛盾系统" not in fake_llm.calls[0][2]
    assert "生成一份“长篇小说宪法”" not in fake_llm.calls[0][2]
    assert fake_llm.calls[0][3]["prompt_snapshot"]["prompt_id"] == "creation_worldview_draw"
    assert payload["cards"][0]["title"] == "远程 API 世界观"
    assert payload["cards"][0]["conflict_engine_seed"] == "只提供冲突发动机种子，不生成核心矛盾系统。"
    assert payload["job"]["current_agent"] == "creation_worldview_draw"
    runs = assert_success(client.get(f"/api/jobs/{payload['job']['id']}/agent-runs"))["agent_runs"]
    assert runs[0]["agent_name"] == "creation_worldview_draw"
    assert runs[0]["output_payload"]["_llm"]["used_remote_model"] is True
    assert runs[0]["output_payload"]["_llm"]["provider"] == "fake-provider"


def test_creation_session_worldview_uses_dedicated_prompt(monkeypatch) -> None:
    class FakeLLMClient:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        def generate(self, system_prompt: str, user_prompt: str, model: str | None = None):
            payload = json.loads(user_prompt)
            self.calls.append({"system_prompt": system_prompt, "payload": payload, "model": model})
            return SimpleNamespace(
                content=json.dumps(
                    {
                        "step": "worldview",
                        "cards": [
                            {
                                "id": "session_world_1",
                                "title": "榜单回应世界",
                                "description": "榜单会把所有资源分配变成公开惩罚。",
                                "tags": ["榜单", "规则"],
                                "core_world_rule": "所有资格都由可审计榜单即时改写。",
                                "social_pressure": "普通人被排名绑定亲密关系和上升通道。",
                                "conflict_engine_seed": "主角发现榜单规则被某个阶层持续喂养，越纠错越会暴露自己。",
                                "protagonist_entry": "主角从被错误降档的候选者切入。",
                                "long_form_potential": "每卷揭开一层榜单权力来源。",
                                "reader_hooks": ["纠错爽点", "榜单破防"],
                                "selling_point": "用榜单压迫包装长线升级。",
                                "risk": "需要避免榜单机制只停留在说明。",
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                provider="fake-provider",
                model=model or "fake-worldview-model",
                used_remote_model=True,
            )

    reset_database()
    fake_llm = FakeLLMClient()
    monkeypatch.setattr(studio_service_module, "llm_client", fake_llm)
    client = TestClient(app)
    project_id = create_project(client)
    session_id = assert_success(
        client.post(
            f"/api/projects/{project_id}/creation/sessions",
            json={"basic_info": {"genre": "都市", "target_reader": "喜欢规则流的读者", "initial_idea": "榜单会回应主角批注。"}},
        )
    )["session"]["id"]

    payload = assert_success(
        client.post(
            f"/api/projects/{project_id}/creation/sessions/{session_id}/worldviews",
            json={"count": 1, "model": "unit-worldview-model"},
        )
    )

    assert fake_llm.calls[0]["payload"]["agent_name"] == "creation_worldview_draw"
    assert fake_llm.calls[0]["model"] == "unit-worldview-model"
    assert "长篇小说世界观抽卡 Agent" in fake_llm.calls[0]["system_prompt"]
    assert "请帮我设计一部长篇小说的核心矛盾系统" not in fake_llm.calls[0]["system_prompt"]
    assert "生成一份“长篇小说宪法”" not in fake_llm.calls[0]["system_prompt"]
    assert fake_llm.calls[0]["payload"]["context"]["prompt_snapshot"]["prompt_id"] == "creation_worldview_draw"
    assert fake_llm.calls[0]["payload"]["context"]["prompt_snapshot"]["runtime_strategy"]["selected"] == "dedicated_worldview_prompt"
    assert payload["cards"][0]["core_rule"] == "所有资格都由可审计榜单即时改写。"
    assert payload["cards"][0]["conflict_engine_seed"].startswith("主角发现榜单规则")
    assert payload["job"]["current_agent"] == "creation_worldview_draw"


def test_creation_star_protagonist_draw_calls_dedicated_llm_client(monkeypatch) -> None:
    class FakeLLMClient:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str | None, str, dict]] = []

        def generate(self, system_prompt: str, user_prompt: str, model: str | None = None):
            payload = json.loads(user_prompt)
            self.calls.append((payload["agent_name"], model, system_prompt, payload["context"]))
            return SimpleNamespace(
                content=json.dumps(
                    {
                        "step": "protagonist",
                        "cards": [
                            {
                                "id": "remote_protagonist_1",
                                "name": "闻照夜",
                                "title": "被榜单误删的人",
                                "identity": "被规则榜单降档的候选者",
                                "opening_situation": "开局被取消资格，只能用违规申诉进入世界裂缝。",
                                "world_rule_connection": "他能看见榜单每次改写背后的资源流向。",
                                "long_term_desire": "夺回解释自己命运的权利。",
                                "immediate_goal": "查清榜单为何删除他的资格。",
                                "inner_wound": "害怕自己只是规则错误的副产品。",
                                "ability": "能把榜单异常转成短暂战术优势。",
                                "ability_cost": "每次纠错都会暴露一个亲近者的隐私。",
                                "weakness": "不愿让别人分担代价。",
                                "secret": "他的名字曾出现在旧榜单的隐藏冠军位。",
                                "growth_arc": "从被榜单定义，到重新定义榜单。",
                                "relationship_hooks": ["与榜单维护者之女互相利用", "被导师当成申诉样本"],
                                "conflict_seed": "主角每次纠错都会让榜单维护阶层更主动地清除他。",
                                "reader_satisfaction": "爽点来自用规则漏洞反打规则。",
                                "long_form_potential": "资格、名誉、亲密关系和城市权限都能逐卷升级。",
                                "writing_risk": "需要避免主角只像设定工具人。",
                                "revision_hint": "可以强化他的私人欲望，而不是只写反制度。",
                                "tags": ["规则流", "底层逆袭"],
                                "source": "agent",
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                provider="fake-provider",
                model=model or "fake-protagonist-model",
                used_remote_model=True,
            )

    reset_database()
    fake_llm = FakeLLMClient()
    monkeypatch.setattr(studio_service_module, "llm_client", fake_llm)
    client = TestClient(app)
    project_id = create_project(client)
    worldview = {
        "id": "world_1",
        "title": "榜单回应世界",
        "core_rule": "所有资格都由可审计榜单即时改写。",
        "social_pressure": "普通人被排名绑定亲密关系和上升通道。",
        "power_or_resource_system": "资格榜单、申诉积分和城市权限。",
        "protagonist_entry": "主角从被错误降档的候选者切入。",
        "conflict_engine_seed": "榜单规则被维护阶层持续喂养。",
        "reader_hooks": ["纠错爽点", "规则反噬"],
    }

    payload = assert_success(
        client.post(
            f"/api/projects/{project_id}/creation-star/draw",
            json={
                "step": "protagonist",
                "basic_info": {"genre": "都市", "target_reader": "喜欢规则流的读者", "initial_idea": "榜单会回应主角批注。"},
                "selected_worldview": worldview,
                "count": 3,
                "model": "unit-protagonist-model",
            },
        )
    )

    assert fake_llm.calls[0][0] == "creation_protagonist_draw"
    assert fake_llm.calls[0][1] == "unit-protagonist-model"
    assert "长篇小说主角人设抽卡 Agent" in fake_llm.calls[0][2]
    assert "请帮我设计一部长篇小说的核心矛盾系统" not in fake_llm.calls[0][2]
    assert "生成一份“长篇小说宪法”" not in fake_llm.calls[0][2]
    assert fake_llm.calls[0][3]["prompt_snapshot"]["prompt_id"] == "creation_protagonist_draw"
    assert payload["cards"][0]["world_rule_connection"] == "他能看见榜单每次改写背后的资源流向。"
    assert payload["cards"][0]["conflict_seed"].startswith("主角每次纠错")
    assert payload["cards"][0]["long_term_goal"] == "夺回解释自己命运的权利。"
    assert payload["job"]["current_agent"] == "creation_protagonist_draw"


def test_creation_session_protagonist_uses_dedicated_prompt(monkeypatch) -> None:
    class FakeLLMClient:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        def generate(self, system_prompt: str, user_prompt: str, model: str | None = None):
            payload = json.loads(user_prompt)
            self.calls.append({"system_prompt": system_prompt, "payload": payload, "model": model})
            return SimpleNamespace(
                content=json.dumps(
                    {
                        "step": "protagonist",
                        "cards": [
                            {
                                "id": "session_protagonist_1",
                                "name": "顾燃",
                                "title": "申诉榜单的失格者",
                                "identity": "被榜单标记为失格的贫民区候选者",
                                "opening_situation": "开局为了保住家人保障名额，被迫挑战榜单漏洞。",
                                "world_rule_connection": "他的失败记录会触发榜单隐藏审计。",
                                "long_term_desire": "让被榜单吞掉的人重新拥有名字。",
                                "immediate_goal": "拿回家人的保障资格。",
                                "inner_wound": "一直认为自己拖累了家人。",
                                "ability": "能从失败记录反推出规则漏洞。",
                                "ability_cost": "每次推演都会损失一段真实记忆。",
                                "weakness": "容易把自责当成行动燃料。",
                                "secret": "他是旧榜单清洗计划的幸存样本。",
                                "growth_arc": "从替家人申诉，到替无名者改写榜单。",
                                "relationship_hooks": ["妹妹的保障名额被当成筹码", "旧榜单调查员想利用他"],
                                "conflict_seed": "他越证明榜单错误，榜单越要证明他不存在。",
                                "reader_satisfaction": "失败记录反杀权威的反差爽点。",
                                "long_form_potential": "每卷升级一个榜单层级和一段记忆真相。",
                                "writing_risk": "记忆代价要和剧情选择绑定。",
                                "revision_hint": "可把家人线改成师徒线或同伴线。",
                                "tags": ["规则流", "申诉", "成长"],
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                provider="fake-provider",
                model=model or "fake-protagonist-model",
                used_remote_model=True,
            )

    reset_database()
    fake_llm = FakeLLMClient()
    monkeypatch.setattr(studio_service_module, "llm_client", fake_llm)
    client = TestClient(app)
    project_id = create_project(client)
    session_id = assert_success(
        client.post(
            f"/api/projects/{project_id}/creation/sessions",
            json={"basic_info": {"genre": "都市", "target_reader": "喜欢规则流的读者", "initial_idea": "榜单会回应主角批注。"}},
        )
    )["session"]["id"]
    worldview = {
        "id": "world_1",
        "title": "榜单回应世界",
        "core_rule": "所有资格都由可审计榜单即时改写。",
        "social_pressure": "普通人被排名绑定亲密关系和上升通道。",
        "power_or_resource_system": "资格榜单、申诉积分和城市权限。",
        "protagonist_entry": "主角从被错误降档的候选者切入。",
        "conflict_engine_seed": "榜单规则被维护阶层持续喂养。",
        "reader_hooks": ["纠错爽点", "规则反噬"],
    }
    patch_creation_session_state(session_id, {"selected_worldview": worldview, "worldview_candidates": [worldview]})

    payload = assert_success(
        client.post(
            f"/api/projects/{project_id}/creation/sessions/{session_id}/protagonists",
            json={"count": 1, "model": "unit-protagonist-model"},
        )
    )

    assert fake_llm.calls[0]["payload"]["agent_name"] == "creation_protagonist_draw"
    assert fake_llm.calls[0]["model"] == "unit-protagonist-model"
    assert "长篇小说主角人设抽卡 Agent" in fake_llm.calls[0]["system_prompt"]
    assert "请帮我设计一部长篇小说的核心矛盾系统" not in fake_llm.calls[0]["system_prompt"]
    assert "生成一份“长篇小说宪法”" not in fake_llm.calls[0]["system_prompt"]
    snapshot = fake_llm.calls[0]["payload"]["context"]["prompt_snapshot"]
    assert snapshot["prompt_id"] == "creation_protagonist_draw"
    assert snapshot["runtime_strategy"]["selected"] == "dedicated_protagonist_prompt"
    assert "榜单回应世界" in snapshot["context_summary"]
    assert payload["cards"][0]["world_rule_connection"] == "他的失败记录会触发榜单隐藏审计。"
    assert payload["cards"][0]["ability_cost"] == "每次推演都会损失一段真实记忆。"
    assert payload["job"]["current_agent"] == "creation_protagonist_draw"


def test_creation_session_title_uses_dedicated_packaging_prompt(monkeypatch) -> None:
    class FakeLLMClient:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        def generate(self, system_prompt: str, user_prompt: str, model: str | None = None):
            payload = json.loads(user_prompt)
            self.calls.append({"system_prompt": system_prompt, "payload": payload, "model": model})
            return SimpleNamespace(
                content=json.dumps(
                    {
                        "step": "title",
                        "cards": [
                            {
                                "id": "title_packaging_1",
                                "title": "榜单误删后我让全城重排",
                                "subtitle": "规则流高武开局包装",
                                "description": "用一句强钩子书名直接承诺榜单压迫、主角反打和长线升级。",
                                "platform_style": "强钩子口语化",
                                "one_sentence_ad": "被榜单删名的少年，用失败记录逼全城规则重排。",
                                "core_selling_point": "规则压迫 + 申诉反杀 + 高武升级。",
                                "selling_point": "主角每次纠错都会让旧榜单破防。",
                                "reader_expectation": "前三章看见冤屈、反打和规则漏洞。",
                                "worldview_hook": "榜单即时改写所有资格。",
                                "protagonist_hook": "主角能从失败记录反推漏洞。",
                                "risk": "标题信息量偏高，需按平台长度压缩。",
                                "revision_hint": "可弱化高武词，强化榜单和误删钩子。",
                                "tags": ["规则流", "高武", "强钩子"],
                                "source": "agent",
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                provider="fake-provider",
                model=model or "fake-title-model",
                used_remote_model=True,
            )

    reset_database()
    fake_llm = FakeLLMClient()
    monkeypatch.setattr(studio_service_module, "llm_client", fake_llm)
    client = TestClient(app)
    project_id = create_project(client)
    session_id = assert_success(
        client.post(
            f"/api/projects/{project_id}/creation/sessions",
            json={"basic_info": {"genre": "都市", "target_reader": "喜欢规则流的读者", "initial_idea": "榜单会回应主角批注。"}},
        )
    )["session"]["id"]
    worldview = {
        "id": "world_1",
        "title": "榜单回应世界",
        "core_rule": "所有资格都由可审计榜单即时改写。",
        "social_pressure": "普通人被排名绑定亲密关系和上升通道。",
        "power_or_resource_system": "资格榜单、申诉积分和城市权限。",
        "protagonist_entry": "主角从被错误降档的候选者切入。",
        "conflict_engine_seed": "榜单规则被维护阶层持续喂养。",
        "reader_hooks": ["纠错爽点", "规则反噬"],
    }
    protagonist = {
        "id": "protagonist_1",
        "name": "顾燃",
        "identity": "被榜单标记为失格的贫民区候选者",
        "long_term_goal": "让被榜单吞掉的人重新拥有名字。",
        "world_rule_connection": "他的失败记录会触发榜单隐藏审计。",
        "conflict_seed": "他越证明榜单错误，榜单越要证明他不存在。",
    }
    patch_creation_session_state(
        session_id,
        {
            "selected_worldview": worldview,
            "selected_protagonist": protagonist,
            "worldview_candidates": [worldview],
            "protagonist_candidates": [protagonist],
        },
    )

    payload = assert_success(
        client.post(
            f"/api/projects/{project_id}/creation/sessions/{session_id}/market-position",
            json={"count": 1, "model": "unit-title-model"},
        )
    )

    assert fake_llm.calls[0]["payload"]["agent_name"] == "creation_title_packaging"
    assert fake_llm.calls[0]["model"] == "unit-title-model"
    assert "长篇小说书名与包装抽卡 Agent" in fake_llm.calls[0]["system_prompt"]
    assert "请帮我设计一部长篇小说的核心矛盾系统" not in fake_llm.calls[0]["system_prompt"]
    assert "生成一份“长篇小说宪法”" not in fake_llm.calls[0]["system_prompt"]
    snapshot = fake_llm.calls[0]["payload"]["context"]["prompt_snapshot"]
    assert snapshot["prompt_id"] == "creation_title_packaging"
    assert snapshot["runtime_strategy"]["selected"] == "dedicated_title_packaging_prompt"
    assert snapshot["output_schema"]["cards"][0]["core_selling_point"]
    assert "榜单回应世界" in snapshot["context_summary"]
    assert payload["title_candidates"][0]["title"] == "榜单误删后我让全城重排"
    assert payload["title_candidates"][0]["core_selling_point"] == "规则压迫 + 申诉反杀 + 高武升级。"
    assert payload["cards"] == payload["title_candidates"]
    assert payload["_llm"]["used_remote_model"] is True
    assert payload["market_position_candidates"] == []
    assert payload["session"]["state"]["market_position_source"] == "title_packaging"
    assert payload["session"]["state"]["title_candidates_count"] == 1
    assert "market_position" not in payload["session"]["state"]
    assert payload["job"]["current_agent"] == "creation_title_packaging"


def test_creation_session_core_and_constitution_read_expanded_seed_context(monkeypatch) -> None:
    class FakeLLMClient:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        def generate(self, system_prompt: str, user_prompt: str, model: str | None = None):
            payload = json.loads(user_prompt)
            self.calls.append({"system_prompt": system_prompt, "payload": payload, "model": model})
            if payload["task"].startswith("根据创作 Star 已确认的立项种子生成核心矛盾系统"):
                content = {
                    "protagonist_desire": "让被榜单吞掉的人重新拥有名字。",
                    "world_resistance": "榜单规则被维护阶层持续喂养。",
                    "core_conflict": "顾燃想让被榜单吞掉的人重新拥有名字，但榜单维护阶层必须证明他不存在。",
                    "external_resistance": "城市权限和申诉积分被旧榜单控制。",
                    "internal_resistance": "顾燃害怕自己也会复制榜单逻辑。",
                    "relationship_resistance": "妹妹的保障名额被当成筹码。",
                    "institutional_resistance": "榜单、学校和财团共享资格解释权。",
                    "typical_cost": "每次纠错都会失去一部分身份信用。",
                    "long_form_engine": "每卷揭开一层榜单背后的资源分配规则。",
                    "possible_endpoint": "顾燃重写榜单，但必须承担新规则的审判。",
                    "theme_question": "普通人能否夺回被制度删除的名字。",
                }
            else:
                content = {
                    "basic_positioning": {"genre": "都市", "target_reader_experience": "喜欢规则流的读者"},
                    "core_narrative_engine": {"core_conflict": "顾燃与榜单维护阶层持续冲突。"},
                    "protagonist_arc": {"surface_goal": "让被榜单吞掉的人重新拥有名字。"},
                    "world_rules": {"primary_logic": "榜单即时改写所有资格。"},
                    "character_functions": {"protagonist": "顾燃"},
                    "theme_pressure": {"core_question": "普通人能否夺回被制度删除的名字。"},
                    "cost_mechanism": ["纠错必须失去身份信用"],
                    "forbidden_directions": ["不能无代价改写榜单"],
                    "long_form_sustainability": "榜单、财团、城市权限可逐层展开。",
                }
            return SimpleNamespace(
                content=json.dumps(content, ensure_ascii=False),
                provider="fake-provider",
                model=model or "fake-core-model",
                used_remote_model=True,
            )

    reset_database()
    fake_llm = FakeLLMClient()
    monkeypatch.setattr(studio_service_module, "llm_client", fake_llm)
    client = TestClient(app)
    project_id = create_project(client)
    session_id = assert_success(
        client.post(
            f"/api/projects/{project_id}/creation/sessions",
            json={"basic_info": {"genre": "都市", "target_reader": "喜欢规则流的读者", "initial_idea": "榜单会回应主角批注。"}},
        )
    )["session"]["id"]
    worldview = {
        "id": "world_1",
        "title": "榜单回应世界",
        "core_world_rule": "所有资格都由可审计榜单即时改写。",
        "social_pressure": "普通人被排名绑定亲密关系和上升通道。",
        "power_or_resource_system": "资格榜单、申诉积分和城市权限。",
        "protagonist_entry": "主角从被错误降档的候选者切入。",
        "conflict_engine_seed": "榜单规则被维护阶层持续喂养。",
        "reader_hooks": ["纠错爽点", "规则反噬"],
    }
    protagonist = {
        "id": "protagonist_1",
        "name": "顾燃",
        "identity": "被榜单标记为失格的贫民区候选者",
        "long_term_desire": "让被榜单吞掉的人重新拥有名字。",
        "ability_cost": "每次纠错都会失去身份信用。",
        "relationship_hooks": ["妹妹的保障名额被当成筹码"],
        "conflict_seed": "他越证明榜单错误，榜单越要证明他不存在。",
    }
    title = {
        "id": "title_1",
        "title": "榜单误删后我让全城重排",
        "core_selling_point": "规则压迫 + 申诉反杀 + 高武升级。",
        "reader_expectation": "前三章看见冤屈、反打和规则漏洞。",
    }
    market_position = {
        "target_reader": "喜欢规则流的读者",
        "platform_fit": "男频强钩子",
        "core_selling_point": "规则压迫 + 申诉反杀 + 高武升级。",
        "reader_expectation": "前三章看见冤屈、反打和规则漏洞。",
    }
    patch_creation_session_state(
        session_id,
        {
            "project_seed": {
                "basic_info": {"genre": "都市", "target_reader": "喜欢规则流的读者"},
                "selected_worldview": worldview,
                "selected_protagonist": protagonist,
                "selected_title": title,
                "market_position": market_position,
            }
        },
    )

    assert_success(client.post(f"/api/projects/{project_id}/creation/sessions/{session_id}/core-conflict", json={"model": "unit-core-model"}))
    assert_success(client.post(f"/api/projects/{project_id}/creation/sessions/{session_id}/constitution", json={"model": "unit-constitution-model"}))

    core_call = fake_llm.calls[0]
    constitution_call = fake_llm.calls[1]
    assert core_call["model"] == "unit-core-model"
    assert "project_seed" in core_call["system_prompt"]
    assert "selected_worldview" in core_call["system_prompt"]
    assert "题材类型：【填写" not in core_call["system_prompt"]
    core_context = core_call["payload"]["context"]
    assert core_context["selected_worldview"]["conflict_engine_seed"] == "榜单规则被维护阶层持续喂养。"
    assert core_context["selected_protagonist"]["ability_cost"] == "每次纠错都会失去身份信用。"
    assert core_context["selected_title"]["core_selling_point"] == "规则压迫 + 申诉反杀 + 高武升级。"
    assert core_context["market_position"]["reader_expectation"] == "前三章看见冤屈、反打和规则漏洞。"

    assert constitution_call["model"] == "unit-constitution-model"
    assert "core_conflict_system" in constitution_call["system_prompt"]
    assert "basic_positioning" in constitution_call["system_prompt"]
    assert "【粘贴核心矛盾系统】" not in constitution_call["system_prompt"]
    constitution_context = constitution_call["payload"]["context"]
    assert constitution_context["selected_worldview"]["title"] == "榜单回应世界"
    assert constitution_context["selected_protagonist"]["name"] == "顾燃"
    assert constitution_context["selected_title"]["title"] == "榜单误删后我让全城重排"
    assert constitution_context["market_position"]["platform_fit"] == "男频强钩子"
    assert constitution_context["core_conflict_system"]["core_conflict"].startswith("顾燃想")


def test_creation_basic_suggestions_call_llm_client(monkeypatch) -> None:
    class FakeLLMClient:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str | None, dict]] = []

        def generate(self, system_prompt: str, user_prompt: str, model: str | None = None):
            payload = json.loads(user_prompt)
            self.calls.append((payload["agent_name"], model, payload["context"]))
            return SimpleNamespace(
                content=json.dumps(
                    {
                        "suggestions": [
                            {
                                "id": "idea_remote_1",
                                "target": "initial_idea",
                                "title": "旧案开局",
                                "content": "主角在武考前夜收到一份被官方抹除的旧案卷宗。",
                                "tags": ["旧案", "开局钩子"],
                                "reason": "能把主角入口、世界压迫和主线谜团合并在同一个事件里。",
                            },
                            {
                                "id": "constraint_remote_1",
                                "target": "manual_input",
                                "title": "避开外挂碾压",
                                "content": "刷新世界观时避免纯外挂碾压，所有爽点必须绑定制度漏洞和代价。",
                                "tags": ["约束", "代价机制"],
                                "reason": "帮助后续抽卡持续生成可升级的规则压力。",
                            },
                        ]
                    },
                    ensure_ascii=False,
                ),
                provider="fake-provider",
                model=model or "fake-suggestion-model",
                used_remote_model=True,
            )

    reset_database()
    fake_llm = FakeLLMClient()
    monkeypatch.setattr(studio_service_module, "llm_client", fake_llm)
    client = TestClient(app)
    project_id = create_project(client)

    payload = assert_success(
        client.post(
            f"/api/projects/{project_id}/creation/basic-suggestions",
            json={
                "basic_info": {
                    "channel": "男频",
                    "genre": "都市",
                    "tags": ["学院流"],
                    "target_reader": "喜欢高武升级和旧案悬疑的读者",
                    "initial_idea": "宗门变成教育集团。",
                },
                "manual_input": "想保留现代都市质感",
                "previous_suggestions": [{"title": "上一批建议"}],
                "count": 4,
                "model": "unit-basic-suggestion-model",
            },
        )
    )

    assert fake_llm.calls[0][0] == "creation_basic_suggestions"
    assert fake_llm.calls[0][1] == "unit-basic-suggestion-model"
    assert fake_llm.calls[0][2]["manual_input"] == "想保留现代都市质感"
    assert fake_llm.calls[0][2]["previous_suggestions"][0]["title"] == "上一批建议"
    assert payload["suggestions"][0]["target"] == "initial_idea"
    assert payload["suggestions"][1]["target"] == "manual_input"
    assert payload["prompt_snapshot"]["agent_name"] == "creation_basic_suggestions"
    assert payload["llm"]["used_remote_model"] is True

    refreshed = assert_success(
        client.post(
            f"/api/projects/{project_id}/creation/basic-suggestions",
            json={
                "basic_info": {
                    "channel": "男频",
                    "genre": "都市",
                    "tags": ["学院流"],
                    "target_reader": "喜欢高武升级和旧案悬疑的读者",
                    "initial_idea": "宗门变成教育集团。",
                },
                "manual_input": "想保留现代都市质感",
                "previous_suggestions": payload["suggestions"],
                "count": 4,
                "model": "unit-basic-suggestion-model",
            },
        )
    )
    previous_keys = {(item["target"], item["title"], item["content"]) for item in payload["suggestions"]}
    refreshed_keys = {(item["target"], item["title"], item["content"]) for item in refreshed["suggestions"]}
    assert not previous_keys.intersection(refreshed_keys)


def test_creation_basic_suggestions_do_not_use_hidden_project_premise(monkeypatch) -> None:
    class FakeLLMClient:
        def __init__(self) -> None:
            self.context: dict = {}

        def generate(self, system_prompt: str, user_prompt: str, model: str | None = None):
            payload = json.loads(user_prompt)
            self.context = payload["context"]
            return SimpleNamespace(
                content=json.dumps(
                    {
                        "suggestions": [
                            {
                                "id": "idea_visible_1",
                                "target": "initial_idea",
                                "title": "可见表单脑洞",
                                "content": "围绕当前页面已填字段生成，不继承旧项目 premise。",
                                "tags": ["可见输入"],
                                "reason": "避免隐藏项目资料污染创作 Star 基本信息页。",
                            },
                            {
                                "id": "constraint_visible_1",
                                "target": "manual_input",
                                "title": "可见约束",
                                "content": "只参考额外约束输入框。",
                                "tags": ["约束"],
                                "reason": "保持刷新建议可解释。",
                            },
                        ]
                    },
                    ensure_ascii=False,
                ),
                provider="fake-provider",
                model=model or "fake-suggestion-model",
                used_remote_model=True,
            )

    reset_database()
    fake_llm = FakeLLMClient()
    monkeypatch.setattr(studio_service_module, "llm_client", fake_llm)
    client = TestClient(app)
    project_id = assert_success(
        client.post(
            "/api/projects",
            json={
                "title": "旧项目",
                "genre": "悬疑",
                "target_reader": "喜欢编辑器怪谈的读者",
                "premise": "一名编辑发现自己修改的小说会改变现实。",
                "style_guide": "冷峻。",
                "language": "zh-CN",
                "planned_chapter_count": 60,
                "chapter_word_target": 2200,
            },
        )
    )["project"]["id"]

    assert_success(
        client.post(
            f"/api/projects/{project_id}/creation/basic-suggestions",
            json={
                "basic_info": {
                    "channel": "男频",
                    "genre": "玄幻",
                    "target_words": 1000000,
                    "style": "热血爽快",
                },
                "manual_input": "",
                "count": 4,
            },
        )
    )

    assert fake_llm.context["basic_info"]["initial_idea"] == ""
    assert fake_llm.context["basic_info"]["target_reader"] == ""
    assert "premise" not in fake_llm.context["project"]
    assert "initial_idea" not in fake_llm.context["project"]
