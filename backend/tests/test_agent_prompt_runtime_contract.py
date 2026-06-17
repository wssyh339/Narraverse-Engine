import os
import re
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite:///./data/test_novel_agent.db"
os.environ["JOB_ARTIFACT_DIR"] = "backend/artifacts/test-runs"

from fastapi.testclient import TestClient

from app.agents.llm_io import call_agent_json, render_prompt_placeholders
from app.core.config import LLMProviderResolver, get_settings
from app.db.session import Base, engine
from app.main import app


def reset_database() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def assert_success(response):
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["error"] is None
    return payload["data"]


def test_agent_prompt_can_be_customized_and_restored_to_default() -> None:
    reset_database()
    client = TestClient(app)

    original = assert_success(client.get("/api/agents/full_structure"))["agent"]
    assert original["is_custom"] is False
    assert original["prompt"] == original["default_prompt"]

    custom_prompt = "自定义全书结构 Agent：只输出 JSON。"
    updated = assert_success(client.put("/api/agents/full_structure/prompt", json={"prompt": custom_prompt}))["agent"]
    assert updated["is_custom"] is True
    assert updated["prompt"] == custom_prompt
    assert updated["default_prompt"] == original["default_prompt"]

    restored = assert_success(client.post("/api/agents/full_structure/prompt/restore"))["agent"]
    assert restored["is_custom"] is False
    assert restored["prompt"] == original["default_prompt"]


def test_llm_model_catalog_and_workflow_agent_model_config_are_exposed(monkeypatch) -> None:
    reset_database()
    monkeypatch.setenv("LLM_PROVIDER", "qwen")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("QWEN_API_KEY", raising=False)
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    client = TestClient(app)

    catalog = assert_success(client.get("/api/llm/models"))
    providers = {item["id"] for item in catalog["providers"]}
    model_ids = {item["id"] for item in catalog["models"]}

    assert {"openai", "qwen", "deepseek", "openai_compatible"}.issubset(providers)
    assert {"gpt-4.1-mini", "qwen-plus", "deepseek-v4-flash", "deepseek-v4-pro"}.issubset(model_ids)
    assert catalog["default_model"]
    assert catalog["configured"] is False
    assert catalog["default_provider_configured"] is False
    assert catalog["configuration_warning"]
    assert "LLM 未配置" in catalog["configuration_warning"]
    qwen_provider = next(item for item in catalog["providers"] if item["id"] == "qwen")
    assert qwen_provider["configured"] is False
    assert qwen_provider["active"] is True

    saved = assert_success(
        client.put(
            "/api/agent-model-configs",
            json={
                "workflow_id": "chapter_draft",
                "agent_name": "reviewer",
                "model": "deepseek-v4-pro",
            },
        )
    )["config"]
    assert saved["workflow_id"] == "chapter_draft"
    assert saved["agent_name"] == "reviewer"
    assert saved["model"] == "deepseek-v4-pro"
    assert saved["provider"] == "deepseek"

    configs = assert_success(client.get("/api/agent-model-configs"))["configs"]
    assert any(item["workflow_id"] == "chapter_draft" and item["agent_name"] == "reviewer" for item in configs)

    workflows = assert_success(client.get("/api/workflows"))["workflows"]
    chapter_workflow = next(workflow for workflow in workflows if workflow["id"] == "chapter_draft")
    reviewer_node = next(node for node in chapter_workflow["nodes"] if node["agent_name"] == "reviewer")
    assert reviewer_node["model"] == "deepseek-v4-pro"
    assert reviewer_node["provider"] == "deepseek"

    agents = assert_success(client.get("/api/agents"))["agents"]
    reviewer = next(agent for agent in agents if agent["name"] == "reviewer")
    assert reviewer["model_configs"]["chapter_draft"]["model"] == "deepseek-v4-pro"


def test_agent_model_config_supplies_runtime_default_when_request_has_no_model() -> None:
    reset_database()
    client = TestClient(app)
    assert_success(
        client.put(
            "/api/agent-model-configs",
            json={
                "workflow_id": "creation_star_session",
                "agent_name": "creation_star",
                "model": "qwen-max",
            },
        )
    )

    captured = {}

    class FakeLLM:
        def generate(self, system_prompt: str, user_prompt: str, model: str | None = None):
            captured["model"] = model
            return type(
                "Result",
                (),
                {
                    "content": '{"cards":[{"title":"模型配置生效","description":"ok"}]}',
                    "provider": "fake",
                    "model": model or "fake",
                    "used_remote_model": True,
                },
            )()

    from app.services import studio_service as studio_module

    original_llm = studio_module.llm_client
    studio_module.llm_client = FakeLLM()
    try:
        project = assert_success(
            client.post(
                "/api/projects",
                json={
                    "title": "模型测试",
                    "genre": "都市",
                    "target_reader": "网文读者",
                    "premise": "一个作者测试模型配置。",
                    "style_guide": "",
                    "language": "zh-CN",
                    "planned_chapter_count": 30,
                    "chapter_word_target": 2000,
                },
            )
        )["project"]
        payload = {
            "step": "worldview",
            "basic_info": {"genre": "都市", "initial_idea": "模型配置测试"},
            "count": 1,
        }
        assert_success(client.post(f"/api/projects/{project['id']}/creation-star/draw", json=payload))
    finally:
        studio_module.llm_client = original_llm

    assert captured["model"] == "qwen-max"


def test_agent_model_config_rejects_unknown_workflow() -> None:
    reset_database()
    client = TestClient(app)

    response = client.put(
        "/api/agent-model-configs",
        json={
            "workflow_id": "unknown_workflow",
            "agent_name": "reviewer",
            "model": "deepseek-v4-pro",
        },
    )

    assert response.status_code == 404


def test_llm_provider_resolver_infers_provider_from_catalog_models() -> None:
    resolver = LLMProviderResolver(get_settings())

    assert resolver.resolve("openrouter/auto").provider == "openrouter"
    assert resolver.resolve("Qwen/Qwen3-32B").provider == "siliconflow"
    assert resolver.resolve("kimi-k2-0711-preview").provider == "moonshot"
    assert resolver.resolve("glm-4-plus").provider == "zhipu"
    assert resolver.resolve("qwen2.5:7b").provider == "ollama"
    prefixed = resolver.resolve("openrouter:custom/model-name")
    assert prefixed.provider == "openrouter"
    assert prefixed.model == "custom/model-name"


def test_workflows_api_exposes_prompt_lifecycle_views_and_keeps_legacy_prompt_lanes() -> None:
    reset_database()
    client = TestClient(app)

    workflows = assert_success(client.get("/api/workflows"))["workflows"]
    by_key = {workflow["key"]: workflow for workflow in workflows}

    assert "chapter_closed_loop_lifecycle" in by_key
    assert "special_booster_lifecycle" in by_key
    assert "chapter_production" in by_key
    first_lifecycle_index = next(index for index, workflow in enumerate(workflows) if workflow.get("workflow_kind") == "prompt_lifecycle")
    first_prompt_library_index = next(index for index, workflow in enumerate(workflows) if workflow.get("workflow_kind") == "prompt_library")
    assert first_lifecycle_index < first_prompt_library_index

    lifecycle = by_key["chapter_closed_loop_lifecycle"]
    assert lifecycle["workflow_kind"] == "prompt_lifecycle"
    assert lifecycle["runtime_status"] == "applied_via_prompt_binding"
    assert lifecycle["trigger_policy"] == "on_chapter_generation"

    node_ids = [node["id"] for node in lifecycle["nodes"]]
    assert node_ids[:4] == ["next_chapter_state_change", "chapter_card", "scene_outline", "draft_generation"]
    assert "minimal_work_template" not in node_ids
    assert all(node["node_subtype"] == "prompt_agent" for node in lifecycle["nodes"] if node["type"] == "prompt")

    legacy = by_key["chapter_production"]
    assert legacy["workflow_kind"] == "prompt_library"
    assert legacy["runtime_status"] == "applied_via_prompt_binding"


def test_call_agent_json_replaces_template_input_placeholders_before_llm_call() -> None:
    captured = {}

    class FakeLLM:
        def generate(self, system_prompt: str, user_prompt: str, model: str | None = None):
            captured["system_prompt"] = system_prompt
            captured["user_prompt"] = user_prompt
            return type("Result", (), {"content": '{"ok": true}', "provider": "fake", "model": model or "fake", "used_remote_model": True})()

    call_agent_json(
        llm_client=FakeLLM(),
        agent_name="full_structure",
        role="全书结构 Agent",
        system_prompt="小说宪法：【粘贴小说宪法】\n当前卷：【填写，例如第一卷：底层觉醒】\n正文长度：【填写字数】",
        task="生成大纲",
        context={
            "project": {"title": "雾港来信", "genre": "悬疑", "chapter_word_target": 2200},
            "story_bible": {"main_conflict": "记者追查十年前旧案", "themes": ["记忆", "真相"]},
            "volumes": [{"title": "第一卷：旧信"}],
            "request": {"chapter_word_target": 2200},
        },
        fallback={"ok": False},
        model="unit-model",
    )

    system_prompt = captured["system_prompt"]
    assert "【粘贴小说宪法】" not in system_prompt
    assert "【填写，例如第一卷：底层觉醒】" not in system_prompt
    assert "【填写字数】" not in system_prompt
    assert "记者追查十年前旧案" in system_prompt
    assert "第一卷：旧信" in system_prompt
    assert "2200" in system_prompt


def test_call_agent_json_marks_invalid_critical_agent_output_schema() -> None:
    class FakeLLM:
        def generate(self, system_prompt: str, user_prompt: str, model: str | None = None):
            return type(
                "Result",
                (),
                {
                    "content": '{"unexpected": true}',
                    "provider": "fake",
                    "model": model or "fake",
                    "used_remote_model": True,
                },
            )()

    payload, meta = call_agent_json(
        llm_client=FakeLLM(),
        agent_name="volume_outline",
        role="卷纲设计 Agent",
        system_prompt="输出卷纲 JSON。",
        task="生成分卷卷纲。",
        context={"project": {"title": "雾港来信"}},
        fallback={},
        model="unit-model",
    )

    assert meta["parsed"] is True
    assert meta["schema_valid"] is False
    assert any("volume_outlines" in warning for warning in meta["validation_warnings"])
    assert payload["_quality_gate"]["schema_valid"] is False
    assert payload["_quality_gate"]["severity"] == "warning"


def test_all_prompt_library_square_bracket_inputs_are_rendered_at_runtime() -> None:
    prompt_dir = Path(__file__).resolve().parents[1] / "app" / "prompts"
    context = {
        "project": {
            "title": "雾港来信",
            "genre": "悬疑",
            "target_reader": "喜欢旧案追凶和长期伏笔的读者",
            "premise": "记者收到来自十年前失踪者的信。",
            "style_guide": "冷峻、克制、快节奏",
            "chapter_word_target": 2200,
        },
        "request": {
            "instruction": "让主角第一次意识到码头账本并非证据，而是诱饵。",
            "chapter_word_target": 2200,
            "max_words": 2200,
        },
        "story_bible": {
            "world_setting": "雾港由码头家族、地方报社和旧警署共同维持脆弱秩序。",
            "main_conflict": "记者追查十年前旧案，同时被迫面对家族参与掩盖真相。",
            "themes": ["记忆", "真相", "代价"],
            "narrative_pov": "third_person_limited",
            "forbidden_elements": ["机械降神"],
        },
        "novel_constitution": {"不可背叛的承诺": "每条线索都必须付出代价。"},
        "core_conflict_system": {"主矛盾": "真相公开会摧毁主角仅存的亲情。"},
        "macro_outline": {"三幕": ["来信", "追查", "公开"]},
        "book_outline": {"卷一": "旧信引出码头账本。"},
        "volume_outline": {"title": "第一卷：旧信", "goal": "找到旧案第一名幸存者。"},
        "volumes": [{"title": "第一卷：旧信", "outline": "旧信与码头账本"}],
        "rolling_chapter_outline": [{"chapter_no": 7, "event": "主角发现账本缺页。"}],
        "chapter_beats": [{"beat": "发现账本缺页"}],
        "chapter_card": {"chapter_no": 7, "one_sentence": "主角在旧码头被迫交出第一份证据。"},
        "scene_outline": {"scenes": ["雨夜码头", "旧报社地下室"]},
        "narrative_ledger": {"debts": ["欠下线人承诺"], "open_threads": ["账本缺页"]},
        "foreshadowing_ledger": [{"content": "缺页上有主角父亲签名", "status": "planted"}],
        "foreshadowing_items": [{"content": "雾灯闪三次代表警署内应"}],
        "characters": [{"name": "林澈", "state": "怀疑父亲参与旧案"}],
        "protagonist": {"name": "林澈", "identity": "地方记者"},
        "relationship_network": {"林澈-父亲": "信任崩裂"},
        "graph": {"nodes": ["林澈", "旧警署"], "edges": ["隐瞒"]},
        "world_rules": ["雾港旧警署档案不得公开调阅。"],
        "world_facts": [{"fact": "码头家族控制夜航许可"}],
        "timeline": [{"time": "十年前", "event": "旧案发生"}],
        "chapter_summary": "主角拿到账本，却发现关键页被撕走。",
        "previous_chapter_summary": "线人把账本藏进旧报社排字机。",
        "completed_chapters": [{"chapter_no": 6, "summary": "旧报社失火。", "ending": "雾灯闪了三次。"}],
        "summaries": ["第六章：旧报社失火。"],
        "previous_chapter_ending": "雾灯闪了三次，码头开始停电。",
        "cliffhanger": "父亲的签名出现在缺页边缘。",
        "chapter_text": "雨水把码头灯影拖得很长。",
        "draft_text": "林澈握着账本，第一次觉得真相有重量。",
        "source_text": "旧稿正文",
        "integrated_draft": "整合草稿正文",
        "final_chapter_text": "终稿正文",
        "review_notes": "需要强化选择和代价。",
        "health_check_report": "结构健康，但反派压力不足。",
        "structure_review": "第二幕推进偏慢。",
        "logic_audit": "线索来源需补明。",
        "style_sample": "样章文本",
        "sample_text": "短句、冷调、少解释。",
        "ending": "主角公开真相，但失去父亲最后的信任。",
        "ending_direction": "公开真相与私人代价并存。",
    }

    leftovers: dict[str, list[str]] = {}
    for path in sorted(prompt_dir.glob("*.md")):
        rendered = render_prompt_placeholders(path.read_text(encoding="utf-8"), context)
        matches = re.findall(r"【[^】]+】", rendered)
        if matches:
            leftovers[path.name] = matches

    assert leftovers == {}


def test_workflow_definitions_expose_runtime_application_status() -> None:
    reset_database()
    client = TestClient(app)

    workflows = assert_success(client.get("/api/workflows"))["workflows"]
    assert workflows
    for workflow in workflows:
        assert workflow["runtime_status"] in {"active_runtime", "applied_via_prompt_binding"}
        assert workflow["runtime_note"]
        assert workflow["entrypoints"]

    outline = next(workflow for workflow in workflows if workflow["id"] == "outline_generation")
    assert outline["runtime_status"] == "active_runtime"
    assert "/api/projects/{project_id}/chapters/plan" in outline["entrypoints"]

    prompt_lane = next(workflow for workflow in workflows if workflow["id"] == "outline_planning")
    assert prompt_lane["runtime_status"] == "applied_via_prompt_binding"
    assert "AgentSpec" in prompt_lane["runtime_note"]


def test_creation_star_session_workflow_is_registered_for_visualization() -> None:
    reset_database()
    client = TestClient(app)

    workflows = assert_success(client.get("/api/workflows"))["workflows"]
    workflow = next(workflow for workflow in workflows if workflow["id"] == "creation_star_session")

    assert workflow["label"] == "创作 Star 立项流程"
    assert workflow["runtime_status"] == "active_runtime"
    assert "/api/projects/{project_id}/creation/sessions" in workflow["entrypoints"]
    assert "/api/projects/{project_id}/creation/sessions/{session_id}/commit" in workflow["entrypoints"]

    node_ids = [node["id"] for node in workflow["nodes"]]
    assert node_ids == [
        "basic_info",
        "worldview_cards",
        "protagonist_cards",
        "market_position",
        "project_seed",
        "core_constitution",
        "constitution_review",
        "canon_preview",
        "commit_creation",
    ]

    agent_by_node = {node["id"]: node["agent_name"] for node in workflow["nodes"]}
    assert agent_by_node["worldview_cards"] == "creation_worldview_draw"
    assert agent_by_node["protagonist_cards"] == "creation_protagonist_draw"
    assert agent_by_node["market_position"] == "creation_title_packaging"
    assert agent_by_node["core_constitution"] == "chief_architect"
    assert agent_by_node["constitution_review"] == "reviewer"
    assert agent_by_node["canon_preview"] == "canon_curator"

    edge_labels = {(edge["source"], edge["target"]): edge["label"] for edge in workflow["edges"]}
    assert edge_labels[("basic_info", "worldview_cards")] == "创建会话"
    assert edge_labels[("core_constitution", "constitution_review")] == "压力测试"
    assert edge_labels[("constitution_review", "canon_preview")] == "passed / passed_with_notes"
    assert edge_labels[("canon_preview", "commit_creation")] == "审批六项后提交"
