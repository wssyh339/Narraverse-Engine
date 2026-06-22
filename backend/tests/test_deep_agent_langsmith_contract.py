import os

os.environ["DATABASE_URL"] = "sqlite:///./data/test_novel_agent.db"
os.environ["JOB_ARTIFACT_DIR"] = "backend/artifacts/test-runs"
os.environ["DEEP_AGENT_ENABLED"] = "false"
os.environ["DEEP_AGENT_ALLOW_WRITE"] = "false"
os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LANGSMITH_PRIVACY_MODE"] = "metadata_only"

from fastapi.testclient import TestClient

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


def create_project(client: TestClient) -> str:
    created = assert_success(
        client.post(
            "/api/projects",
            json={
                "title": "雾港来信",
                "genre": "悬疑",
                "target_reader": "喜欢旧案追凶和长期伏笔的读者",
                "premise": "记者收到一封来自十年前死者的信。",
                "style_guide": "冷峻、克制、快节奏。",
                "language": "zh-CN",
                "planned_chapter_count": 60,
                "chapter_word_target": 2200,
            },
        )
    )
    return created["project"]["id"]


def test_deep_agent_config_defaults_and_runtime_update_are_safe() -> None:
    reset_database()
    client = TestClient(app)

    config = assert_success(client.get("/api/deep-agent/config"))["config"]
    assert config["deep_agent"]["enabled"] is False
    assert config["deep_agent"]["mode"] == "advisor"
    assert config["deep_agent"]["allow_write"] is False
    assert config["deep_agent"]["tool_policy"] == "approval_required"
    assert config["langsmith"]["tracing"] is False
    assert config["langsmith"]["privacy_mode"] == "metadata_only"
    assert config["langsmith"]["prompt_sync"] == "manual"
    assert "api_key" not in str(config).lower()

    updated = assert_success(
        client.put(
            "/api/deep-agent/config",
            json={
                "deep_agent_enabled": True,
                "deep_agent_mode": "orchestrator",
                "deep_agent_allow_write": False,
                "langsmith_privacy_mode": "redacted",
                "langsmith_prompt_sync": "manual",
            },
        )
    )["config"]
    assert updated["deep_agent"]["enabled"] is True
    assert updated["deep_agent"]["mode"] == "orchestrator"
    assert updated["deep_agent"]["allow_write"] is False
    assert updated["langsmith"]["privacy_mode"] == "redacted"


def test_deep_agent_session_stream_creates_pending_approved_tool_call() -> None:
    reset_database()
    client = TestClient(app)
    project_id = create_project(client)

    session = assert_success(
        client.post(
            f"/api/projects/{project_id}/deep-agent/sessions",
            json={"objective": "检查大纲与正典风险，给出下一步行动。"},
        )
    )["session"]
    assert session["id"].startswith("dps_")
    assert session["mode"] == "advisor"
    assert session["status"] == "active"

    with client.stream(
        "POST",
        f"/api/projects/{project_id}/deep-agent/sessions/{session['id']}/chat/stream",
        json={"message": "请检查大纲、正典和下一章风险。"},
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        body = response.read().decode("utf-8")
    assert '"type":"meta"' in body
    assert '"type":"result"' in body
    assert '"type":"done"' in body

    refreshed = assert_success(client.get(f"/api/projects/{project_id}/deep-agent/sessions/{session['id']}"))["session"]
    assert refreshed["state"]["messages"][-1]["role"] == "assistant"
    tool_calls = refreshed["state"]["tool_calls"]
    assert tool_calls
    tool_call = tool_calls[-1]
    assert tool_call["tool_name"] in {"run_outline_debate", "read_canon_context", "create_candidate_canon_update"}
    assert tool_call["status"] == "pending_approval"
    assert tool_call["requires_approval"] is True

    approved = assert_success(client.post(f"/api/projects/{project_id}/deep-agent/tool-calls/{tool_call['id']}/approve"))["tool_call"]
    assert approved["status"] == "approved"
    assert approved["result"]["action"] == "approval_recorded"


def test_langsmith_status_eval_and_prompt_preview_do_not_leak_sensitive_text_by_default() -> None:
    reset_database()
    client = TestClient(app)
    project_id = create_project(client)

    status = assert_success(client.get("/api/langsmith/status"))["status"]
    assert status["configured"] is False
    assert status["tracing"] is False
    assert status["privacy_mode"] == "metadata_only"
    assert status["project"] == "novel-agent-local"
    assert "api_key" not in str(status).lower()

    eval_report = assert_success(client.post("/api/langsmith/evals/run", json={"project_id": project_id}))["eval_report"]
    assert eval_report["remote_submitted"] is False
    assert eval_report["privacy_mode"] == "metadata_only"
    assert eval_report["checks"]["placeholder_scan"]["status"] in {"passed", "warning"}
    assert "记者收到一封来自十年前死者的信" not in str(eval_report)

    push = assert_success(client.post("/api/langsmith/prompts/push", json={"agent_name": "chapter_planner"}))["prompt_sync"]
    assert push["remote_submitted"] is False
    assert push["privacy_mode"] == "metadata_only"
    assert push["status"] == "skipped"
