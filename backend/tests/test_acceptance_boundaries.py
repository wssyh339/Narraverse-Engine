from fastapi.testclient import TestClient

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


def assert_error_envelope(payload: dict, code: str) -> None:
    assert payload["success"] is False
    assert payload["data"] is None
    assert payload["error"]["code"] == code
    assert isinstance(payload["error"]["message"], str)
    assert payload["error"]["message"]
    assert isinstance(payload["error"]["details"], dict)
    assert payload["request_id"].startswith("req_")
    assert payload["timestamp"].endswith("Z")


def create_project(client: TestClient, title: str = "验收项目") -> str:
    response = client.post(
        "/api/projects",
        json={
            "title": title,
            "genre": "悬疑科幻",
            "target_reader": "喜欢连续性和长期伏笔的读者",
            "premise": "调查员在失联空间站发现一封来自未来的报告。",
            "style_guide": "冷静、紧凑。",
            "language": "zh-CN",
            "planned_chapter_count": 10,
            "chapter_word_target": 1500,
        },
    )
    assert response.status_code == 200
    return response.json()["data"]["project"]["id"]


def test_validation_errors_use_unified_envelope() -> None:
    reset_database()
    client = TestClient(app)

    response = client.post("/api/projects", json={})

    assert response.status_code == 422
    assert_error_envelope(response.json(), "VALIDATION_ERROR")


def test_oversized_project_title_is_rejected_without_server_error() -> None:
    reset_database()
    client = TestClient(app)

    response = client.post(
        "/api/projects",
        json={
            "title": "超" * 5000,
            "genre": "科幻",
            "target_reader": "读者",
            "premise": "故事前提",
            "planned_chapter_count": 10,
            "chapter_word_target": 1500,
        },
    )

    assert response.status_code == 422
    assert_error_envelope(response.json(), "VALIDATION_ERROR")


def test_batch_generation_rejects_missing_confirmed_chapters_without_placeholders() -> None:
    reset_database()
    client = TestClient(app)
    project_id = create_project(client)

    response = client.post("/api/write/batch-generate", json={"project_id": project_id, "chapter_start": 1, "chapter_end": 3})

    assert response.status_code == 400
    assert_error_envelope(response.json(), "VALIDATION_ERROR")
    assert "请先确认章纲" in response.json()["error"]["message"]
    chapters = client.get(f"/api/projects/{project_id}/chapters").json()["data"]["chapters"]
    assert chapters == []


def test_repeated_batch_generation_creates_fresh_async_parent_jobs() -> None:
    reset_database()
    client = TestClient(app)
    project_id = create_project(client)
    client.post(f"/api/projects/{project_id}/chapters", json={"volume_no": 1, "title": "第1章：报告", "outline": "建立空间站谜团。"})
    client.post(f"/api/projects/{project_id}/chapters", json={"volume_no": 1, "title": "第2章：回声", "outline": "推进空间站谜团。"})

    first = client.post("/api/write/batch-generate", json={"project_id": project_id, "chapter_start": 1, "chapter_end": 2})
    second = client.post("/api/write/batch-generate", json={"project_id": project_id, "chapter_start": 1, "chapter_end": 2})

    assert first.status_code == 200
    assert second.status_code == 200
    assert_success_envelope(first.json())
    assert_success_envelope(second.json())
    assert first.json()["data"]["job"]["id"] != second.json()["data"]["job"]["id"]
    assert first.json()["data"]["job"]["job_type"] == "batch_generate"
    assert first.json()["data"]["job"]["status"] in {"queued", "running"}
    assert first.json()["data"]["job"]["progress"]["total_steps"] == 2
    assert first.json()["data"]["job"]["progress"]["completed_steps"] == 0
    assert first.json()["data"]["chapters"] == []
    assert second.json()["data"]["job"]["progress"]["total_steps"] == 2
    assert second.json()["data"]["job"]["progress"]["completed_steps"] == 0
    assert second.json()["data"]["chapters"] == []


def test_missing_api_key_uses_local_fallback_and_records_successful_job() -> None:
    reset_database()
    client = TestClient(app)
    project_id = create_project(client, "无 Key 验收")

    response = client.post(
        f"/api/projects/{project_id}/story-bible/generate",
        json={"initial_idea": "围绕空间站留下的未来报告扩建设定。"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert_success_envelope(payload)
    assert payload["data"]["job"]["status"] == "succeeded"
    assert payload["data"]["story_bible"]["world_setting"]


def test_job_websockets_return_connection_messages() -> None:
    reset_database()
    client = TestClient(app)

    with client.websocket_connect("/ws/progress") as websocket:
        message = websocket.receive_json()
        assert message["type"] == "connected"

    with client.websocket_connect("/ws/jobs/job_acceptance") as websocket:
        message = websocket.receive_json()
        assert message["type"] == "job"
        assert message["job_id"] == "job_acceptance"
