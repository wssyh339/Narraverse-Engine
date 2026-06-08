import os
from pathlib import Path
import json
from types import SimpleNamespace

os.environ["DATABASE_URL"] = "sqlite:///./data/test_novel_agent.db"
os.environ["JOB_ARTIFACT_DIR"] = "backend/artifacts/test-runs"

from fastapi.testclient import TestClient

from app.agents.contracts import NovelStudioState
from app.agents.workflow import agent_workflow
import app.agents.workflow as workflow_module
import app.services.studio_service as studio_service_module
from app.db.session import Base, engine
from app.main import app


def reset_database() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def assert_success_envelope(payload: dict) -> None:
    assert payload["success"] is True
    assert payload["error"] is None
    assert isinstance(payload["data"], dict)
    assert payload["request_id"].startswith("req_")
    assert payload["timestamp"].endswith("Z")


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


def test_plan_chapters_creates_job_and_chapter_placeholders() -> None:
    reset_database()
    client = TestClient(app)
    created = client.post(
        "/api/v1/projects",
        json={
            "title": "山河旧誓",
            "genre": "历史",
            "target_reader": "喜欢权谋和群像的读者",
            "premise": "失势女官重回朝堂，调查旧案。",
            "style_guide": "古雅但不堆砌。",
            "language": "zh-CN",
            "planned_chapter_count": 60,
            "chapter_word_target": 2800,
        },
    ).json()
    project_id = created["data"]["project"]["id"]

    response = client.post(
        f"/api/v1/projects/{project_id}/chapters/plan",
        json={
            "volume_title": "第一卷：寒灯",
            "start_chapter_no": 1,
            "chapter_count": 3,
            "outline_requirement": "建立主角回朝、旧案线索和第一位政敌。",
            "overwrite_existing": False,
            "idempotency_key": f"plan:{project_id}:volume-1:chapters-1-3:v1",
            "target_words": 1000000,
            "volume_count": 10,
            "chapters_per_volume": 50,
            "chapter_word_target": 2000,
            "model": "qwen-plus",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert_success_envelope(payload)
    job = payload["data"]["job"]
    assert job["id"].startswith("job_")
    assert job["project_id"] == project_id
    assert job["chapter_id"] is None
    assert job["job_type"] == "plan_chapters"
    assert job["status"] == "succeeded"
    assert job["progress"]["current_step"] == "completed"
    assert job["progress"]["total_steps"] == 23
    assert job["progress"]["completed_steps"] == 23
    assert len(payload["data"]["chapters"]) == 3
    outline_plan = payload["data"]["outline_plan"]
    assert outline_plan["parameters"]["target_words"] == 1000000
    assert outline_plan["parameters"]["volume_count"] == 10
    assert outline_plan["parameters"]["chapters_per_volume"] == 50
    assert outline_plan["parameters"]["chapter_word_target"] == 2000
    assert "世界圣经" in outline_plan
    assert "10卷单元总表" in outline_plan
    assert len(outline_plan["10卷单元总表"]) == 10
    assert outline_plan["10卷单元总表"][0]["卷名"]
    assert outline_plan["10卷单元总表"][0]["50章高密度剧情流水线执行协议"]
    assert "全卷逻辑审计" in outline_plan["10卷单元总表"][0]
    assert "outline_swarm" in outline_plan
    assert outline_plan["outline_swarm"]["status"] in {"passed", "needs_user_review", "failed"}
    assert outline_plan["outline_swarm"]["agent_trace"]
    assert outline_plan["outline_swarm"]["agent_llm_results"]
    assert outline_plan["outline_swarm"]["agent_trace"][0]["agent_name"] == "StoryDirectorAgent"
    assert job["result"]["outline_plan"]["structured_prompt"]["role"] == "顶级长篇网文总编 + 爽文结构设计师"
    assert job["result"]["chapters"][0]["status"] == "planned"
    assert job["error"] is None

    volumes = client.get(f"/api/projects/{project_id}/volumes").json()["data"]["volumes"]
    assert len(volumes) >= 10
    assert "本卷主角提升目标" in volumes[0]["outline"]

    job_response = client.get(f"/api/v1/jobs/{job['id']}")
    assert job_response.status_code == 200
    job_payload = job_response.json()
    assert_success_envelope(job_payload)
    assert job_payload["data"]["job"]["id"] == job["id"]
    assert job_payload["data"]["job"]["status"] == "succeeded"

    runs_response = client.get(f"/api/v1/jobs/{job['id']}/agent-runs")
    assert runs_response.status_code == 200
    runs_payload = runs_response.json()
    assert_success_envelope(runs_payload)
    run_names = [item["agent_name"] for item in runs_payload["data"]["agent_runs"]]
    assert len(run_names) == 23
    assert run_names[0] == "editor_orchestrator"
    assert run_names[12] == "logic_audit"
    assert run_names[13] == "outline_swarm/StoryDirectorAgent"
    assert run_names[-1] == "outline_swarm/ContinuityAgent"


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
    planned = client.post(
        f"/api/projects/{project_id}/chapters/plan",
        json={
            "volume_title": "第一卷",
            "start_chapter_no": 1,
            "chapter_count": 1,
            "outline_requirement": "开篇建立秘密。",
            "overwrite_existing": False,
            "idempotency_key": f"plan:{project_id}:1",
        },
    ).json()
    chapter_id = planned["data"]["chapters"][0]["id"]

    draft = client.post(
        f"/api/projects/{project_id}/chapters/{chapter_id}/draft",
        json={"user_instruction": "写得紧张一点"},
    )
    assert draft.status_code == 200
    draft_payload = draft.json()
    assert_success_envelope(draft_payload)
    assert draft_payload["data"]["job"]["status"] == "succeeded"
    assert draft_payload["data"]["chapter"]["final_text"]

    runs = client.get(f"/api/jobs/{draft_payload['data']['job']['id']}/agent-runs").json()
    agent_names = [item["agent_name"] for item in runs["data"]["agent_runs"]]
    assert len(agent_names) == 10
    assert "canon_context" in agent_names
    assert "quality_gate" in agent_names

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

    assert result.integrated_draft
    assert result.quality_gate["status"] == "passed"
    assert result.final_chapter_text
    assert result.candidate_canon_updates["world_fact_updates"]
    assert "林昭" in result.plot_draft
    assert "契约禁律" in result.plot_draft


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
                    "chapters": [
                        {
                            "chapter_no": 1,
                            "volume_no": 1,
                            "title": "LLM 第一章",
                            "outline": "LLM 章纲",
                            "pov_character": "林昭",
                            "core_event": "LLM 事件",
                            "conflict": "LLM 冲突",
                            "turn_point": "LLM 转折",
                            "emotional_beats": ["目标", "阻碍"],
                            "plot_purpose": "LLM 功能",
                            "cliffhanger": "LLM 钩子",
                            "word_target": 2000,
                        }
                    ]
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
    planned = agent_workflow.run_chapter_plan(initialized.model_copy(update={"target_chapters": 1, "current_chapter": 1}))
    drafted = agent_workflow.run_chapter_draft(
        planned.model_copy(update={"current_chapter_outline": planned.completed_chapters[0], "canon_context": state.canon_context})
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
    assert drafted.final_chapter_text == "LLM终稿"
    assert drafted.agent_llm_results["plot_narrator"]["used_remote_model"] is True
    assert drafted.agent_llm_results["plot_narrator"]["provider"] == "fake-provider"


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
    assert {"initialization", "chapter_planning", "chapter_draft", "batch_generation"}.issubset(workflow_keys)
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
    planned = client.post(
        f"/api/projects/{project_id}/chapters/plan",
        json={
            "volume_title": "第一卷",
            "start_chapter_no": 1,
            "chapter_count": 2,
            "outline_requirement": "建立钥匙和梦境线索。",
            "overwrite_existing": False,
            "idempotency_key": f"foreshadow-plan:{project_id}",
        },
    ).json()
    chapter_id = planned["data"]["chapters"][0]["id"]
    payoff_chapter_id = planned["data"]["chapters"][1]["id"]

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
