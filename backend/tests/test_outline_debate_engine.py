import os
import json
import asyncio
from pathlib import Path
from types import SimpleNamespace

os.environ["DATABASE_URL"] = "sqlite:///./data/test_novel_agent.db"
os.environ["JOB_ARTIFACT_DIR"] = "backend/artifacts/test-runs"

from fastapi.testclient import TestClient
from dotenv import dotenv_values
import pytest

from app.db import models
from app.db.session import Base, engine, SessionLocal
from app.main import app
from app.schemas.outline import OutlineDebateRunRequest
from app.services import outline_debate_service as outline_debate_service_module


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


def create_project(client: TestClient) -> str:
    data = assert_success(
        client.post(
            "/api/projects",
            json={
                "title": "议事引擎测试",
                "genre": "权谋玄幻",
                "target_reader": "目标读者体验：压迫感、权谋感、成长感、宿命感",
                "premise": "被废黜的少主在血脉禁令下重建失落宗门。",
                "style_guide": "冷静、紧张、因果清晰。",
                "language": "zh-CN",
                "planned_chapter_count": 120,
                "chapter_word_target": 2200,
            },
        )
    )
    return data["project"]["id"]


def load_real_llm_env() -> str:
    env_path = Path(__file__).resolve().parents[2] / ".env"
    values = dotenv_values(env_path)
    provider_env = [
        ("openai", "OPENAI_API_KEY", "OPENAI_MODEL", "gpt-4.1-mini"),
        ("deepseek", "DEEPSEEK_API_KEY", "DEEPSEEK_MODEL", "deepseek-v4-flash"),
        ("qwen", "QWEN_API_KEY", "QWEN_MODEL", "qwen-plus"),
        ("qwen", "DASHSCOPE_API_KEY", "DASHSCOPE_MODEL", "qwen-plus"),
        ("openrouter", "OPENROUTER_API_KEY", "OPENROUTER_MODEL", "openrouter/auto"),
        ("siliconflow", "SILICONFLOW_API_KEY", "SILICONFLOW_MODEL", "Qwen/Qwen3-32B"),
        ("moonshot", "MOONSHOT_API_KEY", "MOONSHOT_MODEL", "kimi-k2-0711-preview"),
        ("zhipu", "ZHIPU_API_KEY", "ZHIPU_MODEL", "glm-4-plus"),
        ("generic", "LLM_API_KEY", "LLM_MODEL", "qwen-plus"),
    ]
    for _provider, key_name, model_name, _default_model in provider_env:
        value = values.get(key_name)
        if value and not os.getenv(key_name):
            os.environ[key_name] = str(value)
    for provider, key_name, model_name, default_model in provider_env:
        if os.getenv(key_name):
            model = os.getenv(model_name) or values.get(model_name) or default_model
            if values.get(f"{provider.upper()}_BASE_URL"):
                os.environ[f"{provider.upper()}_BASE_URL"] = str(values[f"{provider.upper()}_BASE_URL"])
            os.environ["LLM_PROVIDER"] = provider
            os.environ[model_name] = str(model)
            os.environ["LLM_REQUIRE_REMOTE"] = "true"
            return f"{provider}:{model}"
    pytest.skip("A non-empty supported LLM API key is required for the real LLM outline debate contract test")


def run_phase(client: TestClient, project_id: str, session_id: str, phase_path: str, requirement: str, **overrides) -> dict:
    payload = {
        "requirement": requirement,
        "use_topology_inference": True,
        "volume_count": 3,
        "chapters_per_volume": 8,
        "chapter_ranges": [{"volume_no": 1, "start_chapter_no": 1, "end_chapter_no": 3}],
        "local_preview": True,
    }
    payload.update(overrides)
    return assert_success(
        client.post(
            f"/api/projects/{project_id}/outline/debate/sessions/{session_id}/{phase_path}/run",
            json=payload,
        )
    )


class FakeDebateLLM:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def generate(self, system_prompt: str, user_prompt: str, model: str | None = None) -> SimpleNamespace:
        payload = json.loads(user_prompt)
        agent_name = payload["agent_name"]
        self.calls.append({"agent_name": agent_name, "model": model, "system_prompt": system_prompt})
        short_name = agent_name.rsplit("/", 1)[-1]
        response = {
            "stance": f"remote stance {short_name}",
            "message": f"remote turn {short_name}",
            "claims": [f"remote claim {short_name}"],
            "risks": [f"remote risk {short_name}"],
            "result_patch": {
                "book_outline": {
                    "title": "远程总纲标题",
                    "main_conflict": "远程讨论后的核心冲突",
                }
            },
        }
        if short_name == "CharacterGeneratorAgent":
            response["character_candidate"] = {
                "name": "远程候选角色",
                "role_type": "antagonist",
                "summary": "由真实 LLM 结构化输出的候选角色。",
            }
        if short_name == "SettingGeneratorAgent":
            response["setting_candidate"] = {
                "title": "远程候选设定",
                "ref_type": "world_fact",
                "content": "由真实 LLM 结构化输出的候选世界规则。",
            }
        return SimpleNamespace(
            content=json.dumps(response, ensure_ascii=False),
            provider="deepseek",
            model=model or "deepseek-v4-flash",
            used_remote_model=True,
        )


def test_outline_debate_real_path_rejects_unparseable_llm_output(monkeypatch) -> None:
    reset_database()

    class BrokenRemoteLLM:
        def generate(self, *_args, **_kwargs) -> SimpleNamespace:
            return SimpleNamespace(
                content="这不是 JSON，也不应被模板 fallback 吞掉。",
                provider="openai",
                model="contract-test",
                used_remote_model=True,
            )

    monkeypatch.setattr(outline_debate_service_module, "llm_client", BrokenRemoteLLM(), raising=False)
    client = TestClient(app)
    project_id = create_project(client)
    session_id = assert_success(
        client.post(
            f"/api/projects/{project_id}/outline/debate/sessions",
            json={"idempotency_key": f"outline-debate-no-fallback:{project_id}:v1", "brief": "验证真实路径不允许模板兜底。"},
        )
    )["session"]["id"]

    db = SessionLocal()
    try:
        with pytest.raises(RuntimeError, match="未解析为 JSON"):
            outline_debate_service_module.outline_debate_service.run_phase(
                db,
                project_id,
                session_id,
                "book",
                OutlineDebateRunRequest(requirement="真实模式必须失败，不能生成模板议事。"),
            )
    finally:
        db.close()


def test_outline_debate_real_llm_generates_non_template_turns() -> None:
    reset_database()
    model = load_real_llm_env()
    client = TestClient(app)
    project_id = create_project(client)
    session_id = assert_success(
        client.post(
            f"/api/projects/{project_id}/outline/debate/sessions",
            json={"idempotency_key": f"outline-debate-real-llm:{project_id}:v1", "brief": "真实 LLM 议事验收。", "model": model},
        )
    )["session"]["id"]

    book_run = assert_success(
        client.post(
            f"/api/projects/{project_id}/outline/debate/sessions/{session_id}/book/run",
            json={
                "requirement": "用真实 LLM 简短讨论总纲。每个角色只输出一到两句，但必须给出具体判断。",
                "use_topology_inference": True,
                "model": model,
            },
        )
    )["phase_run"]

    fixed_fragments = [
        "本轮只形成候选，不写入正式正典",
        "本轮要检查爽点、压迫、期待管理和平台可读性是否互相支撑",
        "结构建议围绕因果推进、阶段代价和钩子密度展开",
        "用户确认本阶段候选后由服务层入库",
        "检查危机、高潮、结果是否混淆",
    ]
    assert all(turn["_llm"]["used_remote_model"] is True for turn in book_run["turns"])
    assert all(turn["_llm"]["source"] == "remote_api" for turn in book_run["turns"])
    assert all(fragment not in turn["message"] for turn in book_run["turns"] for fragment in fixed_fragments)
    assert any("被废黜" in turn["message"] or "宗门" in turn["message"] or "血脉" in turn["message"] for turn in book_run["turns"])

    protocol = book_run["debate_protocol"]
    assert protocol["orchestrator"] == "OutlineDebateOrchestrator"
    assert protocol["agenda"]["phase"] == "book"
    assert protocol["agenda"]["open_questions"]
    assert "cross_review" in protocol["steps"]
    assert "synthesize_candidate_artifact" in protocol["steps"]

    state = book_run["deliberation_state"]
    assert state["source"] == "real_llm"
    assert state["turn_count"] == len(book_run["turns"])
    assert state["open_questions"]
    assert isinstance(state["agreements"], list)
    assert isinstance(state["conflicts"], list)
    assert isinstance(state["artifact_patches"], list)
    assert isinstance(state["blocked_items"], list)

    for turn in book_run["turns"]:
        skill_file = turn["agent_spec"].get("skill_file", "")
        assert skill_file
        assert turn["agent_spec"].get("skill_source") == "file"
        assert turn["agent_spec"].get("skill_file_exists") is True
        assert Path(__file__).resolve().parents[1].joinpath(skill_file).exists()
        assert isinstance(turn["objections"], list)
        assert isinstance(turn["proposed_decisions"], list)
        assert isinstance(turn["artifact_patch"], dict)
        assert isinstance(turn["uncertainties"], list)
        assert 0 <= turn["confidence"] <= 1

    assert book_run["result"]["synthesis_source"] == "debate_state"
    assert book_run["result"]["source_turn_ids"]
    assert book_run["result"]["_provenance"]["source"] == "debate_state"
    assert "主角的生存与上升欲望对抗既有秩序" not in book_run["result"]["book_outline"]["main_conflict"]


def test_outline_debate_agents_call_llm_and_preserve_remote_metadata(monkeypatch) -> None:
    reset_database()
    fake_llm = FakeDebateLLM()
    monkeypatch.setattr(outline_debate_service_module, "llm_client", fake_llm, raising=False)
    client = TestClient(app)
    project_id = create_project(client)
    session_id = assert_success(
        client.post(
            f"/api/projects/{project_id}/outline/debate/sessions",
            json={"idempotency_key": f"outline-debate-llm:{project_id}:v1", "brief": "验证真实 LLM 议事。", "model": "deepseek:deepseek-v4-flash"},
        )
    )["session"]["id"]

    book = assert_success(
        client.post(
            f"/api/projects/{project_id}/outline/debate/sessions/{session_id}/book/run",
            json={
                "requirement": "使用 Star 生成数据讨论总纲。",
                "use_topology_inference": True,
                "model": "deepseek:deepseek-v4-flash",
            },
        )
    )
    book_run = book["phase_run"]

    assert [call["agent_name"] for call in fake_llm.calls] == [agent[0] for agent in outline_debate_service_module.DEBATE_AGENTS]
    assert all(call["model"] == "deepseek:deepseek-v4-flash" for call in fake_llm.calls)
    assert all(turn["_llm"]["used_remote_model"] is True for turn in book_run["turns"])
    assert all(turn["_llm"]["source"] == "remote_api" for turn in book_run["turns"])
    assert book_run["turns"][0]["message"] == "remote turn StoryDirectorAgent"
    assert book_run["result"]["book_outline"]["title"] == "远程总纲标题"

    character_candidate = next(artifact for artifact in book_run["artifacts"] if artifact["type"] == "character_candidate")["payload"]
    setting_candidate = next(artifact for artifact in book_run["artifacts"] if artifact["type"] == "setting_candidate")["payload"]
    assert character_candidate["name"] == "远程候选角色"
    assert character_candidate["canon_write_suggestion"]["requires_user_approval"] is True
    assert setting_candidate["title"] == "远程候选设定"
    assert setting_candidate["canon_write_suggestion"]["requires_user_approval"] is True

    agent_nodes = [node for node in book_run["outline_topology"]["nodes"] if node["type"] == "agent"]
    assert all(node["payload"]["llm"]["used_remote_model"] is True for node in agent_nodes)


def test_outline_debate_exposes_agent_skill_specs_and_canon_context(monkeypatch) -> None:
    reset_database()

    class InspectingLLM:
        def __init__(self) -> None:
            self.contexts: list[dict] = []

        def generate(self, _system_prompt: str, user_prompt: str, model: str | None = None) -> SimpleNamespace:
            payload = json.loads(user_prompt)
            self.contexts.append(payload["context"])
            agent_name = payload["agent_name"]
            short_name = agent_name.rsplit("/", 1)[-1]
            return SimpleNamespace(
                content=json.dumps(
                    {
                        "stance": f"inspect {short_name}",
                        "message": f"inspect turn {short_name}",
                        "claims": [f"inspect claim {short_name}"],
                        "risks": [f"inspect risk {short_name}"],
                    },
                    ensure_ascii=False,
                ),
                provider="deepseek",
                model=model or "deepseek-v4-flash",
                used_remote_model=True,
            )

    fake_llm = InspectingLLM()
    monkeypatch.setattr(outline_debate_service_module, "llm_client", fake_llm, raising=False)
    client = TestClient(app)
    project_id = create_project(client)

    db = SessionLocal()
    try:
        db.add(models.Character(id="chr-existing", project_id=project_id, name="既有主角", role="protagonist", role_type="protagonist"))
        db.add(models.StoryEntity(id="ent-existing", project_id=project_id, entity_type="sect", name="失落宗门"))
        db.add(models.WorldFact(id="fact-existing", project_id=project_id, category="rule", title="血脉禁令", content="血脉禁令会限制继承权。"))
        db.add(models.GraphNode(id="node-existing", project_id=project_id, node_type="character", ref_id="chr-existing", label="既有主角"))
        db.add(models.ContinuityIssue(id="issue-existing", project_id=project_id, severity="warning", category="timeline", message="血脉禁令起源未确认。"))
        db.add(models.ForeshadowingItem(id="fs-existing", project_id=project_id, content="血脉禁令的例外条款", source="manual"))
        db.commit()
    finally:
        db.close()

    session_id = assert_success(
        client.post(
            f"/api/projects/{project_id}/outline/debate/sessions",
            json={"idempotency_key": f"outline-debate-specs:{project_id}:v1", "brief": "验证 Agent skill 规格。"},
        )
    )["session"]["id"]

    book_run = assert_success(
        client.post(
            f"/api/projects/{project_id}/outline/debate/sessions/{session_id}/book/run",
            json={
                "requirement": "只讨论总纲方向，不新增角色或设定。",
                "target_words": 1000000,
                "volume_count": 10,
                "chapters_per_volume": 40,
                "chapter_word_target": 2500,
                "chapter_word_min": 2200,
                "chapter_word_max": 2800,
            },
        )
    )["phase_run"]

    specs = book_run["agent_specs"]
    assert [spec["name"] for spec in specs] == [agent[0] for agent in outline_debate_service_module.DEBATE_AGENTS]
    story_director = next(spec for spec in specs if spec["name"].endswith("StoryDirectorAgent"))
    character_generator = next(spec for spec in specs if spec["name"].endswith("CharacterGeneratorAgent"))
    continuity_auditor = next(spec for spec in specs if spec["name"].endswith("ContinuityAuditorAgent"))
    assert "讨论主持 skill" in story_director["skills"]
    assert "get_canon_context" in story_director["allowed_read_tools"]
    assert "create_character_candidate" in character_generator["allowed_candidate_tools"]
    assert "createCharacter" in character_generator["forbidden_tools"]
    assert "continuity_checker" in continuity_auditor["validators"]

    assert all(turn["agent_spec"]["skills"] for turn in book_run["turns"])
    agent_nodes = [node for node in book_run["outline_topology"]["nodes"] if node["type"] == "agent"]
    assert all(node["payload"]["agent_spec"]["name"].startswith("outline_debate/") for node in agent_nodes)

    first_context = fake_llm.contexts[0]
    assert first_context["scale_plan"] == {
        "target_words": 1000000,
        "volume_count": 10,
        "chapter_count": 400,
        "chapters_per_volume": 40,
        "chapter_word_target": 2500,
        "chapter_word_min": 2200,
        "chapter_word_max": 2800,
    }
    canon_context = first_context["canon_context"]
    assert any(item["name"] == "既有主角" for item in canon_context["characters"])
    assert any(item["name"] == "失落宗门" for item in canon_context["entities"])
    assert any(item["title"] == "血脉禁令" for item in canon_context["world_facts"])
    assert any(item["label"] == "既有主角" for item in canon_context["graph"]["nodes"])
    assert any(item["message"] == "血脉禁令起源未确认。" for item in canon_context["unresolved_continuity_issues"])
    assert any(item["content"] == "血脉禁令的例外条款" for item in canon_context["foreshadowing_items"])
    assert first_context["agent_spec"]["name"] == "outline_debate/StoryDirectorAgent"


def test_outline_debate_only_generates_character_and_setting_artifacts_when_gap_exists() -> None:
    reset_database()
    client = TestClient(app)
    project_id = create_project(client)
    session_id = assert_success(
        client.post(
            f"/api/projects/{project_id}/outline/debate/sessions",
            json={"idempotency_key": f"outline-debate-gap-policy:{project_id}:v1", "brief": "验证候选缺口策略。"},
        )
    )["session"]["id"]

    no_gap_run = assert_success(
        client.post(
            f"/api/projects/{project_id}/outline/debate/sessions/{session_id}/book/run",
            json={"requirement": "只讨论已有主线的总纲方向，不新增角色或设定。", "local_preview": True},
        )
    )["phase_run"]
    no_gap_artifact_types = [artifact["type"] for artifact in no_gap_run["artifacts"]]
    assert no_gap_artifact_types == ["book_outline_candidate"]
    assert no_gap_run["candidate_policy"]["character_gap"]["required"] is False
    assert no_gap_run["candidate_policy"]["setting_gap"]["required"] is False

    gap_run = assert_success(
        client.post(
            f"/api/projects/{project_id}/outline/debate/sessions/{session_id}/book/run",
            json={"requirement": "总纲缺角色和设定支撑，请只生成候选角色与候选规则。", "local_preview": True},
        )
    )["phase_run"]
    gap_artifact_types = [artifact["type"] for artifact in gap_run["artifacts"]]
    assert "character_candidate" in gap_artifact_types
    assert "setting_candidate" in gap_artifact_types
    assert gap_run["candidate_policy"]["character_gap"]["required"] is True
    assert gap_run["candidate_policy"]["setting_gap"]["required"] is True


def test_outline_debate_records_phase_validation_reports() -> None:
    reset_database()
    client = TestClient(app)
    project_id = create_project(client)
    session_id = assert_success(
        client.post(
            f"/api/projects/{project_id}/outline/debate/sessions",
            json={"idempotency_key": f"outline-debate-validators:{project_id}:v1", "brief": "验证议事校验器。"},
        )
    )["session"]["id"]

    book_run = assert_success(
        client.post(
            f"/api/projects/{project_id}/outline/debate/sessions/{session_id}/book/run",
            json={"requirement": "讨论总纲 schema。", "local_preview": True},
        )
    )["phase_run"]
    book_checks = {check["validator"]: check for check in book_run["validation_report"]["checks"]}
    assert book_run["validation_report"]["status"] == "passed"
    assert book_checks["schema_validator"]["status"] == "passed"

    assert_success(client.post(f"/api/projects/{project_id}/outline/debate/sessions/{session_id}/book/confirm", json={}))
    volumes_run = assert_success(
        client.post(
            f"/api/projects/{project_id}/outline/debate/sessions/{session_id}/volumes/run",
            json={"requirement": "讨论卷纲节奏模型。", "volume_count": 2, "chapters_per_volume": 6, "local_preview": True},
        )
    )["phase_run"]
    volume_checks = {check["validator"]: check for check in volumes_run["validation_report"]["checks"]}
    assert volume_checks["rhythm_model_selector"]["status"] == "passed"
    assert volume_checks["schema_validator"]["status"] == "passed"

    assert_success(client.post(f"/api/projects/{project_id}/outline/debate/sessions/{session_id}/volumes/confirm", json={}))
    chapters_run = assert_success(
        client.post(
            f"/api/projects/{project_id}/outline/debate/sessions/{session_id}/chapters/run",
            json={
                "requirement": "讨论章纲危机、高潮、结果。",
                "chapter_ranges": [{"volume_no": 1, "start_chapter_no": 1, "end_chapter_no": 2}],
                "local_preview": True,
            },
        )
    )["phase_run"]
    chapter_checks = {check["validator"]: check for check in chapters_run["validation_report"]["checks"]}
    assert chapter_checks["crisis_climax_result_checker"]["status"] == "passed"
    assert chapter_checks["schema_validator"]["status"] == "passed"
    assert "continuity_checker" in chapter_checks


def test_outline_debate_confirms_volume_and_chapter_items_with_incremental_canon_updates() -> None:
    reset_database()
    client = TestClient(app)
    project_id = create_project(client)
    db = SessionLocal()
    try:
        initial_counts = {
            "characters": db.query(models.Character).filter(models.Character.project_id == project_id).count(),
            "entities": db.query(models.StoryEntity).filter(models.StoryEntity.project_id == project_id).count(),
            "world_facts": db.query(models.WorldFact).filter(models.WorldFact.project_id == project_id).count(),
            "volumes": db.query(models.Volume).filter(models.Volume.project_id == project_id).count(),
            "chapters": db.query(models.Chapter).filter(models.Chapter.project_id == project_id).count(),
        }
    finally:
        db.close()

    session_data = assert_success(
        client.post(
            f"/api/projects/{project_id}/outline/debate/sessions",
            json={"idempotency_key": f"outline-debate:{project_id}:v1", "brief": "重新讨论三阶段大纲。"},
        )
    )
    session_id = session_data["session"]["id"]
    assert session_data["session"]["phase_runs"] == {}

    error = assert_validation_error(
        client.post(
            f"/api/projects/{project_id}/outline/debate/sessions/{session_id}/volumes/run",
            json={"requirement": "尝试跳过总纲确认直接生成卷纲。"},
        )
    )
    assert "请先确认总纲候选" in error["message"]

    book = run_phase(client, project_id, session_id, "book", "先讨论全书总纲，缺角色和设定时只生成候选。")
    book_run = book["phase_run"]
    assert book_run["phase"] == "book"
    assert book_run["status"] == "succeeded"
    assert book_run["candidate_status"] == "pending_confirmation"
    assert book_run["result"]["candidate_status"] == "pending_confirmation"
    assert [turn["agent_name"] for turn in book_run["turns"]][:3] == [
        "outline_debate/StoryDirectorAgent",
        "outline_debate/MarketPositionAgent",
        "outline_debate/StructureDoctorAgent",
    ]
    artifact_types = [artifact["type"] for artifact in book_run["artifacts"]]
    assert "character_candidate" in artifact_types
    assert "setting_candidate" in artifact_types
    character_candidate = next(artifact for artifact in book_run["artifacts"] if artifact["type"] == "character_candidate")["payload"]
    setting_candidate = next(artifact for artifact in book_run["artifacts"] if artifact["type"] == "setting_candidate")["payload"]
    assert character_candidate["source"] == "outline_debate"
    assert character_candidate["status"] == "candidate"
    assert character_candidate["canon_write_suggestion"]["requires_user_approval"] is True
    assert setting_candidate["source"] == "outline_debate"
    assert setting_candidate["status"] == "candidate"
    assert setting_candidate["canon_write_suggestion"]["requires_user_approval"] is True
    assert book_run["outline_topology"]["mode"] == "topology"
    assert book_run["result"]["generation_kind"] == "outline_debate_book"

    db = SessionLocal()
    try:
        assert db.query(models.Character).filter(models.Character.project_id == project_id).count() == initial_counts["characters"]
        assert db.query(models.StoryEntity).filter(models.StoryEntity.project_id == project_id).count() == initial_counts["entities"]
        assert db.query(models.WorldFact).filter(models.WorldFact.project_id == project_id).count() == initial_counts["world_facts"]
    finally:
        db.close()

    error = assert_validation_error(
        client.post(
            f"/api/projects/{project_id}/outline/debate/sessions/{session_id}/volumes/run",
            json={"requirement": "总纲候选未确认前仍不得生成卷纲。"},
        )
    )
    assert "请先确认总纲候选" in error["message"]

    confirmed_book_data = assert_success(
        client.post(
            f"/api/projects/{project_id}/outline/debate/sessions/{session_id}/book/confirm",
            json={"notes": "总纲方向确认。"},
        )
    )
    confirmed_book = confirmed_book_data["phase_run"]
    assert confirmed_book["candidate_status"] == "confirmed"
    assert confirmed_book["confirmed_at"]
    assert len(confirmed_book["canon_materializations"]) == 2
    assert {item["ref_type"] for item in confirmed_book["canon_materializations"]} == {"character", "world_fact"}
    assert confirmed_book_data["book_commit"]["story_bible"]["main_conflict"] == confirmed_book["result"]["book_outline"]["main_conflict"]

    state_after_book_confirm = assert_success(client.get(f"/api/projects/{project_id}/state"))["state"]
    assert state_after_book_confirm["story_bible"]["main_conflict"] == confirmed_book["result"]["book_outline"]["main_conflict"]

    db = SessionLocal()
    try:
        created_character = (
            db.query(models.Character)
            .filter(models.Character.project_id == project_id, models.Character.name == character_candidate["name"], models.Character.source == "outline_debate")
            .one()
        )
        created_fact = db.query(models.WorldFact).filter(models.WorldFact.project_id == project_id, models.WorldFact.title == setting_candidate["title"]).one()
        assert db.query(models.Character).filter(models.Character.project_id == project_id).count() == initial_counts["characters"] + 1
        assert db.query(models.WorldFact).filter(models.WorldFact.project_id == project_id).count() == initial_counts["world_facts"] + 1
        assert created_character.source == "outline_debate"
        assert created_fact.title == setting_candidate["title"]
        assert db.query(models.StoryEntity).filter(models.StoryEntity.project_id == project_id).count() == initial_counts["entities"]
        assert db.query(models.CanonVersion).filter(models.CanonVersion.project_id == project_id, models.CanonVersion.ref_type == "character").count() == 1
        assert db.query(models.CanonVersion).filter(models.CanonVersion.project_id == project_id, models.CanonVersion.ref_type == "world_fact").count() == 1
    finally:
        db.close()

    assert_success(
        client.post(
            f"/api/projects/{project_id}/outline/debate/sessions/{session_id}/book/confirm",
            json={"notes": "重复确认不应重复物化角色或设定。"},
        )
    )
    db = SessionLocal()
    try:
        assert db.query(models.Character).filter(models.Character.project_id == project_id).count() == initial_counts["characters"] + 1
        assert db.query(models.WorldFact).filter(models.WorldFact.project_id == project_id).count() == initial_counts["world_facts"] + 1
        assert db.query(models.CanonVersion).filter(models.CanonVersion.project_id == project_id, models.CanonVersion.ref_type == "character").count() == 1
        assert db.query(models.CanonVersion).filter(models.CanonVersion.project_id == project_id, models.CanonVersion.ref_type == "world_fact").count() == 1
    finally:
        db.close()

    volumes = run_phase(
        client,
        project_id,
        session_id,
        "volumes",
        "逐卷讨论第1卷卷纲节奏，确认后写入本卷正典。",
        target_volume_no=1,
        volume_count=2,
        local_preview=True,
    )
    assert volumes["phase_run"]["phase"] == "volumes"
    assert volumes["phase_run"]["candidate_status"] == "pending_confirmation"
    assert [item["volume_no"] for item in volumes["phase_run"]["result"]["volume_outlines"]] == [1]
    assert volumes["phase_run"]["confirmation_items"][0]["item_key"] == "volume:1"

    error = assert_validation_error(
        client.post(
            f"/api/projects/{project_id}/outline/debate/sessions/{session_id}/chapters/run",
            json={"requirement": "尝试跳过本卷卷纲确认直接生成章纲。", "target_volume_no": 1, "target_chapter_no": 1},
        )
    )
    assert "请先确认第1卷卷纲候选" in error["message"]

    confirmed_volumes = assert_success(
        client.post(
            f"/api/projects/{project_id}/outline/debate/sessions/{session_id}/volumes/confirm",
            json={"item_key": "volume:1", "notes": "第1卷卷纲节奏确认。"},
        )
    )["phase_run"]
    assert confirmed_volumes["candidate_status"] == "partially_confirmed"
    assert confirmed_volumes["confirmation_items"][0]["candidate_status"] == "confirmed"

    db = SessionLocal()
    try:
        volumes_in_db = db.query(models.Volume).filter(models.Volume.project_id == project_id).order_by(models.Volume.volume_no.asc()).all()
        assert [volume.volume_no for volume in volumes_in_db] == [1]
        assert db.query(models.CanonVersion).filter(models.CanonVersion.project_id == project_id, models.CanonVersion.ref_type == "volume").count() == 1
        assert db.query(models.CanonNode).filter(models.CanonNode.project_id == project_id, models.CanonNode.ref_type == "volume").count() == 1
    finally:
        db.close()

    chapters = run_phase(
        client,
        project_id,
        session_id,
        "chapters",
        "逐章讨论第1章章纲，确认后写入本章正典。",
        target_volume_no=1,
        target_chapter_no=1,
        chapter_ranges=[{"volume_no": 1, "start_chapter_no": 1, "end_chapter_no": 1}],
        local_preview=True,
    )
    assert chapters["phase_run"]["phase"] == "chapters"
    assert chapters["phase_run"]["candidate_status"] == "pending_confirmation"
    assert [item["chapter_no"] for item in chapters["phase_run"]["result"]["chapter_outlines"]] == [1]
    assert chapters["phase_run"]["confirmation_items"][0]["item_key"] == "chapter:1"
    confirmed_chapters_data = assert_success(
        client.post(
            f"/api/projects/{project_id}/outline/debate/sessions/{session_id}/chapters/confirm",
            json={"item_key": "chapter:1", "notes": "第1章章纲候选确认。"},
        )
    )
    assert confirmed_chapters_data["phase_run"]["candidate_status"] == "confirmed"
    assert set(confirmed_chapters_data["session"]["confirmed_candidates"]) == {"book", "volumes", "chapters"}

    db = SessionLocal()
    try:
        chapters_in_db = db.query(models.Chapter).filter(models.Chapter.project_id == project_id).order_by(models.Chapter.chapter_no.asc()).all()
        assert [chapter.chapter_no for chapter in chapters_in_db] == [1]
        assert db.query(models.CanonVersion).filter(models.CanonVersion.project_id == project_id, models.CanonVersion.ref_type == "chapter").count() == 1
        assert db.query(models.CanonNode).filter(models.CanonNode.project_id == project_id, models.CanonNode.ref_type == "chapter").count() == 1
    finally:
        db.close()

    loaded = assert_success(client.get(f"/api/projects/{project_id}/outline/debate/sessions/{session_id}"))["session"]
    assert set(loaded["phase_runs"]) == {"book", "volumes", "chapters"}
    assert loaded["phase_runs"]["book"]["result"]["generation_kind"] == "outline_debate_book"
    assert loaded["phase_runs"]["volumes"]["result"]["generation_kind"] == "outline_debate_volumes"
    assert loaded["phase_runs"]["chapters"]["result"]["generation_kind"] == "outline_debate_chapters"
    assert loaded["phase_runs"]["chapters"]["candidate_status"] == "confirmed"

    db = SessionLocal()
    try:
        counts_before_refresh = {
            "characters": db.query(models.Character).filter(models.Character.project_id == project_id).count(),
            "entities": db.query(models.StoryEntity).filter(models.StoryEntity.project_id == project_id).count(),
            "world_facts": db.query(models.WorldFact).filter(models.WorldFact.project_id == project_id).count(),
            "volumes": db.query(models.Volume).filter(models.Volume.project_id == project_id).count(),
            "chapters": db.query(models.Chapter).filter(models.Chapter.project_id == project_id).count(),
        }
    finally:
        db.close()

    refreshed_book = run_phase(client, project_id, session_id, "book", "重新讨论总纲，旧卷纲和章纲候选应过期。")["session"]
    assert refreshed_book["phase_runs"]["book"]["candidate_status"] == "pending_confirmation"
    assert refreshed_book["phase_runs"]["volumes"]["candidate_status"] == "stale"
    assert refreshed_book["phase_runs"]["chapters"]["candidate_status"] == "stale"
    assert "volumes" not in refreshed_book["confirmed_candidates"]
    assert "chapters" not in refreshed_book["confirmed_candidates"]

    db = SessionLocal()
    try:
        assert db.query(models.Character).filter(models.Character.project_id == project_id).count() == counts_before_refresh["characters"]
        assert db.query(models.StoryEntity).filter(models.StoryEntity.project_id == project_id).count() == counts_before_refresh["entities"]
        assert db.query(models.WorldFact).filter(models.WorldFact.project_id == project_id).count() == counts_before_refresh["world_facts"]
        assert db.query(models.Volume).filter(models.Volume.project_id == project_id).count() == counts_before_refresh["volumes"]
        assert db.query(models.Chapter).filter(models.Chapter.project_id == project_id).count() == counts_before_refresh["chapters"]
    finally:
        db.close()


def test_confirmed_outline_debate_candidates_commit_to_formal_outline_without_duplicate_canon_side_effects() -> None:
    reset_database()
    client = TestClient(app)
    project_id = create_project(client)

    session_id = assert_success(
        client.post(
            f"/api/projects/{project_id}/outline/debate/sessions",
            json={"idempotency_key": f"outline-debate-commit:{project_id}:v1", "brief": "完整议事后写入正式大纲。"},
        )
    )["session"]["id"]

    run_phase(client, project_id, session_id, "book", "讨论全书总纲候选。")
    assert_success(client.post(f"/api/projects/{project_id}/outline/debate/sessions/{session_id}/book/confirm", json={}))

    for volume_no in (1, 2, 3):
        run_phase(
            client,
            project_id,
            session_id,
            "volumes",
            f"逐卷讨论第{volume_no}卷卷纲候选。",
            target_volume_no=volume_no,
            volume_count=3,
            local_preview=True,
        )
        assert_success(
            client.post(
                f"/api/projects/{project_id}/outline/debate/sessions/{session_id}/volumes/confirm",
                json={"item_key": f"volume:{volume_no}", "notes": f"第{volume_no}卷确认。"},
            )
        )

    premature = assert_validation_error(
        client.post(f"/api/projects/{project_id}/outline/debate/sessions/{session_id}/commit", json={"overwrite_existing_chapters": True})
    )
    assert "请先确认章纲候选" in premature["message"]

    for chapter_no in (1, 2, 3):
        run_phase(
            client,
            project_id,
            session_id,
            "chapters",
            f"逐章讨论第{chapter_no}章章纲候选。",
            target_volume_no=1,
            target_chapter_no=chapter_no,
            chapter_ranges=[{"volume_no": 1, "start_chapter_no": chapter_no, "end_chapter_no": chapter_no}],
            local_preview=True,
        )
        assert_success(
            client.post(
                f"/api/projects/{project_id}/outline/debate/sessions/{session_id}/chapters/confirm",
                json={"item_key": f"chapter:{chapter_no}", "notes": f"第{chapter_no}章确认。"},
            )
        )

    db = SessionLocal()
    try:
        before_counts = {
            "characters": db.query(models.Character).filter(models.Character.project_id == project_id).count(),
            "entities": db.query(models.StoryEntity).filter(models.StoryEntity.project_id == project_id).count(),
            "world_facts": db.query(models.WorldFact).filter(models.WorldFact.project_id == project_id).count(),
        }
    finally:
        db.close()

    committed = assert_success(
        client.post(f"/api/projects/{project_id}/outline/debate/sessions/{session_id}/commit", json={"overwrite_existing_chapters": True})
    )
    assert committed["session"]["status"] == "committed"
    assert committed["session"]["formal_commit"]["status"] == "committed"
    assert set(committed["session"]["confirmed_candidates"]) == {"book", "volumes", "chapters"}
    assert committed["book_commit"]["story_bible"]["main_conflict"] == committed["session"]["confirmed_candidates"]["book"]["book_outline"]["main_conflict"]
    assert [volume["volume_no"] for volume in committed["book_commit"]["volumes"]] == [1, 2, 3]
    assert [chapter["chapter_no"] for chapter in committed["chapter_commit"]["chapters"]] == [1, 2, 3]
    assert committed["session"]["formal_commit"]["incremental_canon_updates"]["volumes"] == 3
    assert committed["session"]["formal_commit"]["incremental_canon_updates"]["chapters"] == 3

    state = assert_success(client.get(f"/api/projects/{project_id}/state"))["state"]
    assert len(state["chapters"]) == 3
    assert state["story_bible"]["main_conflict"] == committed["session"]["confirmed_candidates"]["book"]["book_outline"]["main_conflict"]

    db = SessionLocal()
    try:
        assert db.query(models.Character).filter(models.Character.project_id == project_id).count() == before_counts["characters"]
        assert db.query(models.StoryEntity).filter(models.StoryEntity.project_id == project_id).count() == before_counts["entities"]
        assert db.query(models.WorldFact).filter(models.WorldFact.project_id == project_id).count() == before_counts["world_facts"]
    finally:
        db.close()


def test_outline_debate_stream_emits_real_phase_events() -> None:
    reset_database()
    client = TestClient(app)
    project_id = create_project(client)
    session_id = assert_success(
        client.post(
            f"/api/projects/{project_id}/outline/debate/sessions",
            json={"idempotency_key": f"outline-debate-stream:{project_id}:v1", "brief": "验证流式议事。"},
        )
    )["session"]["id"]

    with client.stream(
        "POST",
        f"/api/projects/{project_id}/outline/debate/sessions/{session_id}/book/stream",
        json={"requirement": "流式讨论总纲，并暴露真实 Agent 事件。", "use_topology_inference": True, "local_preview": True},
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        stream_text = "".join(response.iter_text())

    for event_name in ["meta", "turn", "decision", "artifact", "done"]:
        assert f"event: {event_name}" in stream_text
    assert "event: delta" in stream_text
    assert "display_text" in stream_text
    assert "关键主张" in stream_text
    assert "交接" in stream_text
    assert "@主持总策划" in stream_text
    assert "@类型卖点" in stream_text
    assert "outline_debate/CharacterGeneratorAgent" in stream_text
    assert "outline_debate/SettingGeneratorAgent" in stream_text

    loaded = assert_success(client.get(f"/api/projects/{project_id}/outline/debate/sessions/{session_id}"))["session"]
    assert loaded["phase_runs"]["book"]["status"] == "succeeded"
    assert loaded["phase_runs"]["book"]["turns"]
    first_turn = loaded["phase_runs"]["book"]["turns"][0]
    assert first_turn["display_text"].startswith("@主持总策划 发言")
    assert first_turn["handoff"]["display"] == "@主持总策划 → @类型卖点"
    assert first_turn["next_agent_name"] == "outline_debate/MarketPositionAgent"


def test_outline_debate_display_text_localizes_structured_keys() -> None:
    service = outline_debate_service_module.outline_debate_service
    turn = {
        "id": "turn-display-localized",
        "agent_name": "outline_debate/StructureDoctorAgent",
        "role": "结构医生 Agent",
        "stance": "压缩工程字段展示。",
        "message": "把候选包字段转成读者能读的中文。",
        "claims": [],
        "objections": [],
        "proposed_decisions": [],
        "artifact_patch": {
            "volume_outlines": [
                {
                    "phase_3": {
                        "name": "争霸天下",
                        "chapters": "131-200",
                        "stage_goal": "萧燃从先天中期突破到大宗师。",
                        "main_conflict": "多势力联盟联手剿灭。",
                        "boundary": "成为新垄断者还是分散权力。",
                        "cost": "核心盟友牺牲。",
                    }
                }
            ]
        },
        "result_patch": {},
        "character_candidate": {},
        "setting_candidate": {},
        "risks": [],
        "uncertainties": [],
        "decisions": [],
        "confidence": 0.8,
    }

    service._attach_turn_display(turn, "outline_debate/ContinuityAuditorAgent")
    display_text = turn["display_text"]

    for label in ["第三阶段", "名称", "章节", "阶段目标", "主线冲突", "阶段边界", "代价"]:
        assert label in display_text
    for english_key in ["phase_3", "stage_goal", "main_conflict", "boundary：", "cost："]:
        assert english_key not in display_text


def test_outline_debate_session_load_refreshes_legacy_display_text() -> None:
    service = outline_debate_service_module.outline_debate_service
    legacy_turn = {
        "id": "turn-legacy-display",
        "agent_name": "outline_debate/StructureDoctorAgent",
        "role": "结构医生 Agent",
        "display_text": "- phase_3：\n  - stage_goal：旧文本",
        "message": "旧会话展示文本需要重算。",
        "claims": [],
        "objections": [],
        "proposed_decisions": [],
        "artifact_patch": {"phase_3": {"stage_goal": "旧会话目标", "main_conflict": "旧会话冲突"}},
        "result_patch": {},
        "character_candidate": {},
        "setting_candidate": {},
        "risks": [],
        "uncertainties": [],
        "decisions": [],
        "confidence": 0.7,
    }
    job = SimpleNamespace(
        id="job-legacy-display",
        project_id="project-legacy-display",
        result_json=json.dumps(
            {
                "session": {
                    "id": "job-legacy-display",
                    "project_id": "project-legacy-display",
                    "phase_runs": {"book": {"turns": [legacy_turn]}},
                }
            },
            ensure_ascii=False,
        ),
    )

    loaded = service._session_from_job(job)
    display_text = loaded["phase_runs"]["book"]["turns"][0]["display_text"]

    assert "第三阶段" in display_text
    assert "阶段目标" in display_text
    assert "主线冲突" in display_text
    assert "phase_3" not in display_text
    assert "stage_goal" not in display_text


def test_outline_debate_stream_sends_meta_before_waiting_for_agent_generation(monkeypatch) -> None:
    reset_database()
    client = TestClient(app)
    project_id = create_project(client)
    session_id = assert_success(
        client.post(
            f"/api/projects/{project_id}/outline/debate/sessions",
            json={"idempotency_key": f"outline-debate-first-byte:{project_id}:v1", "brief": "验证首事件。"},
        )
    )["session"]["id"]

    class ExplodingLLM:
        def generate(self, *_args, **_kwargs):
            raise AssertionError("stream meta should be yielded before any LLM call")

    monkeypatch.setattr(outline_debate_service_module, "llm_client", ExplodingLLM(), raising=False)

    async def first_event() -> str:
        db = SessionLocal()
        stream = outline_debate_service_module.outline_debate_service.stream_phase(
            db,
            project_id,
            session_id,
            "book",
            OutlineDebateRunRequest(requirement="首事件不能等待完整议事。"),
        )
        try:
            return await stream.__anext__()
        finally:
            await stream.aclose()
            db.close()

    first = asyncio.run(first_event())
    assert "event: meta" in first
    assert "讨论总纲开始流式回放" in first


def test_outline_debate_local_preview_stream_completes_without_remote_llm(monkeypatch) -> None:
    reset_database()
    client = TestClient(app)
    project_id = create_project(client)
    session_id = assert_success(
        client.post(
            f"/api/projects/{project_id}/outline/debate/sessions",
            json={"idempotency_key": f"outline-debate-local-preview:{project_id}:v1", "brief": "验证快速本地推演。"},
        )
    )["session"]["id"]

    class ExplodingLLM:
        def generate(self, *_args, **_kwargs):
            raise AssertionError("local_preview should not call remote LLM")

    monkeypatch.setattr(outline_debate_service_module, "llm_client", ExplodingLLM(), raising=False)

    with client.stream(
        "POST",
        f"/api/projects/{project_id}/outline/debate/sessions/{session_id}/book/stream",
        json={"requirement": "快速本地推演总纲。", "local_preview": True},
    ) as response:
        assert response.status_code == 200
        stream_text = "".join(response.iter_text())

    assert "event: turn" in stream_text
    assert "event: artifact" in stream_text
    assert "event: done" in stream_text
    assert '"source":"local_fallback"' in stream_text


def test_outline_debate_join_mode_streams_one_turn_then_pauses() -> None:
    reset_database()
    client = TestClient(app)
    project_id = create_project(client)
    session_id = assert_success(
        client.post(
            f"/api/projects/{project_id}/outline/debate/sessions",
            json={"idempotency_key": f"outline-debate-round:{project_id}:v1", "brief": "验证回合制议事。"},
        )
    )["session"]["id"]

    with client.stream(
        "POST",
        f"/api/projects/{project_id}/outline/debate/sessions/{session_id}/book/stream",
        json={"requirement": "先让主持发言，然后等待用户意见。", "use_topology_inference": True, "join_discussion": True, "local_preview": True},
    ) as response:
        assert response.status_code == 200
        stream_text = "".join(response.iter_text())

    assert "event: meta" in stream_text
    assert "event: turn" in stream_text
    assert "event: delta" in stream_text
    assert "event: pause" in stream_text
    assert "event: done" not in stream_text
    assert "@主持总策划 → @类型卖点" in stream_text

    loaded = assert_success(client.get(f"/api/projects/{project_id}/outline/debate/sessions/{session_id}"))["session"]
    book_run = loaded["phase_runs"]["book"]
    assert loaded["status"] == "paused"
    assert book_run["status"] == "paused"
    assert len(book_run["turns"]) == 1
    assert book_run["turns"][0]["agent_name"] == "outline_debate/StoryDirectorAgent"
    assert book_run["next_agent_name"] == "outline_debate/MarketPositionAgent"


def test_outline_debate_user_message_can_target_next_agent_and_finish_phase() -> None:
    reset_database()
    client = TestClient(app)
    project_id = create_project(client)
    session_id = assert_success(
        client.post(
            f"/api/projects/{project_id}/outline/debate/sessions",
            json={"idempotency_key": f"outline-debate-mention:{project_id}:v1", "brief": "验证 @ 角色。"},
        )
    )["session"]["id"]

    with client.stream(
        "POST",
        f"/api/projects/{project_id}/outline/debate/sessions/{session_id}/book/stream",
        json={"requirement": "先开场。", "join_discussion": True, "local_preview": True},
    ) as response:
        assert response.status_code == 200
        _ = "".join(response.iter_text())

    message_data = assert_success(
        client.post(
            f"/api/projects/{project_id}/outline/debate/sessions/{session_id}/messages",
            json={
                "phase": "book",
                "message": "@结构医生 请先检查危机、高潮、结果有没有混淆。",
                "target_agent_name": "outline_debate/StructureDoctorAgent",
            },
        )
    )
    assert message_data["message"]["target_agent_name"] == "outline_debate/StructureDoctorAgent"
    assert "outline_debate/StructureDoctorAgent" in message_data["message"]["mentions"]

    with client.stream(
        "POST",
        f"/api/projects/{project_id}/outline/debate/sessions/{session_id}/book/stream",
        json={"requirement": "继续回应用户意见。", "join_discussion": True, "refresh_phase": False, "local_preview": True},
    ) as response:
        assert response.status_code == 200
        stream_text = "".join(response.iter_text())

    assert "outline_debate/StructureDoctorAgent" in stream_text
    assert "@结构医生 → @类型卖点" in stream_text
    loaded = assert_success(client.get(f"/api/projects/{project_id}/outline/debate/sessions/{session_id}"))["session"]
    book_run = loaded["phase_runs"]["book"]
    assert book_run["turns"][-1]["agent_name"] == "outline_debate/StructureDoctorAgent"
    assert book_run["turns"][-1]["handoff"]["display"] == "@结构医生 → @类型卖点"
    assert book_run["user_messages"][-1]["message"].startswith("@结构医生")

    with client.stream(
        "POST",
        f"/api/projects/{project_id}/outline/debate/sessions/{session_id}/book/stream",
        json={"requirement": "根据已有讨论形成阶段结论。", "join_discussion": True, "refresh_phase": False, "finish_phase": True, "local_preview": True},
    ) as response:
        assert response.status_code == 200
        done_text = "".join(response.iter_text())

    assert "event: decision" in done_text
    assert "event: artifact" in done_text
    assert "event: done" in done_text
    loaded = assert_success(client.get(f"/api/projects/{project_id}/outline/debate/sessions/{session_id}"))["session"]
    assert loaded["phase_runs"]["book"]["status"] == "succeeded"
    assert loaded["phase_runs"]["book"]["artifacts"]


def test_outline_debate_user_message_before_first_round_routes_target_agent() -> None:
    reset_database()
    client = TestClient(app)
    project_id = create_project(client)
    session_id = assert_success(
        client.post(
            f"/api/projects/{project_id}/outline/debate/sessions",
            json={"idempotency_key": f"outline-debate-pre-message:{project_id}:v1", "brief": "验证先插话再开始。"},
        )
    )["session"]["id"]

    message_data = assert_success(
        client.post(
            f"/api/projects/{project_id}/outline/debate/sessions/{session_id}/messages",
            json={
                "phase": "book",
                "message": "@结构医生 请先从结构风险开始，不要等主持开场。",
                "target_agent_name": "outline_debate/StructureDoctorAgent",
            },
        )
    )
    assert message_data["message"]["target_agent_name"] == "outline_debate/StructureDoctorAgent"

    with client.stream(
        "POST",
        f"/api/projects/{project_id}/outline/debate/sessions/{session_id}/book/stream",
        json={"requirement": "回应用户先插入的意见。", "join_discussion": True, "refresh_phase": False, "local_preview": True},
    ) as response:
        assert response.status_code == 200
        stream_text = "".join(response.iter_text())

    assert "outline_debate/StructureDoctorAgent" in stream_text
    loaded = assert_success(client.get(f"/api/projects/{project_id}/outline/debate/sessions/{session_id}"))["session"]
    book_run = loaded["phase_runs"]["book"]
    assert book_run["turns"][0]["agent_name"] == "outline_debate/StructureDoctorAgent"
    assert book_run["user_messages"][0]["handled_by_turn_id"] == book_run["turns"][0]["id"]
    assert loaded["messages"][0]["handled_by_turn_id"] == book_run["turns"][0]["id"]


def test_outline_debate_interrupt_marks_session_without_artifacts() -> None:
    reset_database()
    client = TestClient(app)
    project_id = create_project(client)
    session_id = assert_success(
        client.post(
            f"/api/projects/{project_id}/outline/debate/sessions",
            json={"idempotency_key": f"outline-debate-interrupt:{project_id}:v1", "brief": "验证打断。"},
        )
    )["session"]["id"]

    with client.stream(
        "POST",
        f"/api/projects/{project_id}/outline/debate/sessions/{session_id}/book/stream",
        json={"requirement": "先发言。", "join_discussion": True, "local_preview": True},
    ) as response:
        assert response.status_code == 200
        _ = "".join(response.iter_text())

    interrupted = assert_success(
        client.post(
            f"/api/projects/{project_id}/outline/debate/sessions/{session_id}/interrupt",
            json={"phase": "book", "reason": "用户要重写讨论目标。"},
        )
    )["session"]
    assert interrupted["status"] == "interrupted"
    assert interrupted["phase_runs"]["book"]["status"] == "interrupted"
    assert interrupted["phase_runs"]["book"]["artifacts"] == []
