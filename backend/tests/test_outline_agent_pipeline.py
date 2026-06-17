import os
import json
from types import SimpleNamespace

os.environ["DATABASE_URL"] = "sqlite:///./data/test_novel_agent.db"
os.environ["JOB_ARTIFACT_DIR"] = "backend/artifacts/test-runs"

from fastapi.testclient import TestClient

from app.db.session import Base, engine
from app.main import app
import app.services.studio_service as studio_service_module


OUTLINE_AGENT_NAMES = [
    "editor_orchestrator",
    "one_sentence_expansion",
    "genre_market_position",
    "world_bible",
    "protagonist_arc",
    "character_tree",
    "faction_conflict",
    "power_system",
    "full_structure",
    "volume_outline",
    "beat_control",
    "foreshadowing_manager",
    "logic_audit",
]

OUTLINE_SWARM_AGENT_NAMES = [
    "outline_swarm/StoryDirectorAgent",
    "outline_swarm/WhyInterrogatorAgent",
    "outline_swarm/WorldSettingAgent",
    "outline_swarm/CharacterArcAgent",
    "outline_swarm/ConflictAgent",
    "outline_swarm/CharacterGeneratorAgent",
    "outline_swarm/SettingGeneratorAgent",
    "outline_swarm/PlotArchitectAgent",
    "outline_swarm/BeatControllerAgent",
    "outline_swarm/ForeshadowingAgent",
    "outline_swarm/EntityExtractorAgent",
    "outline_swarm/ContinuityAgent",
]


def reset_database() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def assert_success(response) -> dict:
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["error"] is None
    return payload["data"]


def create_outline_project(client: TestClient) -> str:
    data = assert_success(
        client.post(
            "/api/projects",
            json={
                "title": "长篇推演测试",
                "genre": "都市高武",
                "target_reader": "喜欢升级、悬疑暗线和长期伏笔的读者",
                "premise": "被宗门财团退学的少年发现自己的批注会改写武道规则。",
                "style_guide": "热血、清晰、强钩子。",
                "language": "zh-CN",
                "planned_chapter_count": 500,
                "chapter_word_target": 2000,
            },
        )
    )
    return data["project"]["id"]


def test_outline_agents_and_workflow_are_registered() -> None:
    reset_database()
    client = TestClient(app)

    agents = assert_success(client.get("/api/agents"))["agents"]
    agents_by_name = {agent["name"]: agent for agent in agents}
    for name in OUTLINE_AGENT_NAMES:
        assert name in agents_by_name
    assert "长篇小说总编统筹 Agent" in agents_by_name["editor_orchestrator"]["prompt"]
    assert "伏笔账本" in agents_by_name["foreshadowing_manager"]["prompt"]
    assert "A级问题" in agents_by_name["logic_audit"]["prompt"]

    workflows = assert_success(client.get("/api/workflows"))["workflows"]
    outline_workflow = next(workflow for workflow in workflows if workflow["id"] == "outline_generation")
    node_agent_names = [node["agent_name"] for node in outline_workflow["nodes"] if node["type"] == "agent"]
    assert node_agent_names == OUTLINE_AGENT_NAMES
    assert outline_workflow["nodes"][0]["stage"] == "S1"
    assert outline_workflow["nodes"][-1]["stage"] == "S11"


def test_plan_chapters_runs_thirteen_outline_agents_and_returns_story_state() -> None:
    reset_database()
    client = TestClient(app)
    project_id = create_outline_project(client)

    planned = assert_success(
        client.post(
            f"/api/projects/{project_id}/chapters/plan",
            json={
                "volume_title": "第一卷：退学之后",
                "start_chapter_no": 1,
                "chapter_count": 5,
                "outline_requirement": "建立主角退学、批注改写规则、宗门财团追责和第一条伏笔。",
                "overwrite_existing": False,
                "idempotency_key": f"outline-pipeline:{project_id}:v1",
                "target_words": 1000000,
                "volume_count": 10,
                "chapters_per_volume": 50,
                "chapter_word_target": 2000,
            },
        )
    )

    outline_plan = planned["outline_plan"]
    assert outline_plan["story_state"]["current_stage"] == "S13_FINAL_OUTLINE"
    assert outline_plan["story_state"]["version"] == "outline-v1"
    assert len(outline_plan["推演状态机流程"]) == 14
    assert [item["agent_name"] for item in outline_plan["13Agent推演链"]] == OUTLINE_AGENT_NAMES
    for key in [
        "故事核心",
        "类型卖点定位",
        "世界圣经",
        "主角成长线",
        "人物树",
        "势力冲突表",
        "金手指升级体系",
        "全书10卷总纲",
        "逐卷50章大纲",
        "章节节拍表",
        "伏笔账本",
        "逻辑审计报告",
        "最终修订版纲要",
    ]:
        assert key in outline_plan
    assert len(outline_plan["全书10卷总纲"]["ten_volume_table"]) == 10
    assert len(outline_plan["逐卷50章大纲"]) == 10
    assert outline_plan["逻辑审计报告"]["passed"] is True
    assert len(planned["chapters"]) == 5

    runs = assert_success(client.get(f"/api/jobs/{planned['job']['id']}/agent-runs"))["agent_runs"]
    run_names = [run["agent_name"] for run in runs]
    assert run_names[: len(OUTLINE_AGENT_NAMES)] == OUTLINE_AGENT_NAMES
    assert run_names[-len(OUTLINE_SWARM_AGENT_NAMES) :] == OUTLINE_SWARM_AGENT_NAMES
    assert runs[len(OUTLINE_AGENT_NAMES) - 1]["output_payload"]["passed"] is True
    assert runs[-1]["output_payload"]["status"] in {"passed", "needs_user_review", "failed"}


def test_plan_chapters_calls_llm_client_for_each_outline_agent(monkeypatch) -> None:
    class FakeLLMClient:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str | None]] = []

        def generate(self, system_prompt: str, user_prompt: str, model: str | None = None):
            payload = json.loads(user_prompt)
            agent_name = payload["agent_name"]
            self.calls.append((agent_name, model))
            return SimpleNamespace(
                content=json.dumps({"remote_marker": agent_name, "passed": True, "issues": []}, ensure_ascii=False),
                provider="fake-provider",
                model=model or "fake-outline-model",
                used_remote_model=True,
            )

    reset_database()
    fake_llm = FakeLLMClient()
    monkeypatch.setattr(studio_service_module, "llm_client", fake_llm)
    client = TestClient(app)
    project_id = create_outline_project(client)

    planned = assert_success(
        client.post(
            f"/api/projects/{project_id}/chapters/plan",
            json={
                "volume_title": "第一卷：退学之后",
                "start_chapter_no": 1,
                "chapter_count": 2,
                "outline_requirement": "验证 13 Agent 都走真实 LLM Client。",
                "overwrite_existing": False,
                "idempotency_key": f"outline-llm:{project_id}:v1",
                "target_words": 1000000,
                "volume_count": 10,
                "chapters_per_volume": 50,
                "chapter_word_target": 2000,
                "model": "unit-outline-model",
            },
        )
    )

    assert [agent_name for agent_name, _ in fake_llm.calls] == OUTLINE_AGENT_NAMES
    assert all(model == "unit-outline-model" for _, model in fake_llm.calls)
    runs = assert_success(client.get(f"/api/jobs/{planned['job']['id']}/agent-runs"))["agent_runs"]
    legacy_runs = runs[: len(OUTLINE_AGENT_NAMES)]
    swarm_runs = runs[len(OUTLINE_AGENT_NAMES) :]
    for run in legacy_runs:
        assert run["output_payload"]["remote_marker"] == run["agent_name"]
        assert run["output_payload"]["_llm"]["used_remote_model"] is True
        assert run["output_payload"]["_llm"]["provider"] == "fake-provider"
    assert [run["agent_name"] for run in swarm_runs] == OUTLINE_SWARM_AGENT_NAMES
    for run in swarm_runs:
        assert run["output_payload"]["_llm"]["source"] in {"remote_api", "local_fallback"}


def test_outline_swarm_generates_character_and_setting_candidates() -> None:
    from app.agents.outline_swarm.service import run_outline_swarm

    result = run_outline_swarm(
        {
            "project_id": "project_outline_candidates",
            "generation_kind": "book_outline",
            "seed": {
                "title": "候选补全测试",
                "genre": "权谋玄幻",
                "target_reader": "期待压迫感、权谋感和成长感的读者",
                "premise": "被废黜的少主必须在王朝禁令下重建失落宗门。",
                "worldview": "王朝以血脉律令限制修行资源流动。",
                "outline_requirement": "需要生成总纲时补齐关键对手和制度设定。",
            },
            "volume_target": 2,
            "chapter_target": 8,
            "max_iterations": 14,
        }
    )

    assert [event["agent_name"] for event in result["agent_trace"] if event["event_type"] == "agent_step"][:7] == [
        "StoryDirectorAgent",
        "WhyInterrogatorAgent",
        "WorldSettingAgent",
        "CharacterArcAgent",
        "ConflictAgent",
        "CharacterGeneratorAgent",
        "SettingGeneratorAgent",
    ]
    assert result["character_candidates"]
    assert result["setting_candidates"]
    character = result["character_candidates"][0]
    setting = result["setting_candidates"][0]
    assert character["activity_status"] == "candidate"
    assert character["canon_write_suggestion"]["requires_user_approval"] is True
    assert character["first_needed_in"]["stage"] == "book_outline"
    assert setting["activity_status"] == "candidate"
    assert setting["canon_write_suggestion"]["requires_user_approval"] is True
    assert setting["first_needed_in"]["stage"] == "book_outline"
    assert any(event["event_type"] == "character_candidate" for event in result["agent_trace"])
    assert any(event["event_type"] == "setting_candidate" for event in result["agent_trace"])


def test_book_outline_topology_exposes_character_and_setting_candidates() -> None:
    reset_database()
    client = TestClient(app)
    project_id = create_outline_project(client)

    data = assert_success(
        client.post(
            f"/api/projects/{project_id}/outline/book/generate",
            json={
                "outline_requirement": "讨论全书总纲时，如果缺少阶段对手或世界规则，请生成候选角色和候选设定。",
                "target_words": 300000,
                "volume_count": 2,
                "chapters_per_volume": 8,
                "chapter_word_target": 2000,
                "use_topology_inference": True,
                "idempotency_key": f"book-outline-candidates:{project_id}:v1",
            },
        )
    )

    outline_plan = data["outline_plan"]
    swarm = outline_plan["outline_swarm"]
    topology = outline_plan["outline_topology"]
    assert swarm["character_candidates"]
    assert swarm["setting_candidates"]
    event_types = {event["event_type"] for event in topology["events"]}
    assert "character_candidate" in event_types
    assert "setting_candidate" in event_types
    artifact_types = [artifact["type"] for artifact in topology["artifacts"]]
    assert "character_candidate" in artifact_types
    assert "setting_candidate" in artifact_types
    node_labels = [node["label"] for node in topology["nodes"]]
    assert "大纲角色生成 Agent" in node_labels
    assert "大纲设定生成 Agent" in node_labels
