import json

from fastapi.testclient import TestClient

from app.db.session import Base, engine
from app.main import app


def reset_database() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def assert_success(response) -> dict:
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["error"] is None
    return payload["data"]


def create_project_and_chapter(client: TestClient) -> tuple[str, str]:
    project = assert_success(
        client.post(
            "/api/projects",
            json={
                "title": "流式章节助手测试",
                "genre": "悬疑",
                "target_reader": "长篇小说作者",
                "premise": "一名作者发现自己的编辑器会保留每次改写的影子。",
                "style_guide": "克制、清晰，保留悬念。",
                "language": "zh-CN",
                "planned_chapter_count": 20,
                "chapter_word_target": 1800,
            },
        )
    )["project"]
    chapter = assert_success(
        client.post(
            f"/api/projects/{project['id']}/chapters",
            json={
                "volume_no": 1,
                "title": "白屏里的第二行字",
                "outline": "主角第一次发现编辑器会回应她。",
            },
        )
    )["chapter"]
    assert_success(
        client.put(
            f"/api/projects/{project['id']}/chapters/{chapter['id']}",
            json={"final_text": "屏幕亮着。她看见第二行字慢慢浮出来。", "status": "drafted"},
        )
    )
    return project["id"], chapter["id"]


def parse_sse_data(body: str) -> list[dict]:
    events: list[dict] = []
    for line in body.splitlines():
        if line.startswith("data: "):
            events.append(json.loads(line.removeprefix("data: ")))
    return events


def test_chapter_chat_stream_returns_meta_delta_result_and_done(monkeypatch) -> None:
    reset_database()
    monkeypatch.setenv("LLM_PROVIDER", "local-test")
    monkeypatch.setenv("LLM_API_KEY", "")
    client = TestClient(app)
    project_id, chapter_id = create_project_and_chapter(client)

    response = client.post(
        f"/api/projects/{project_id}/chapters/{chapter_id}/chat/stream",
        json={
            "mode": "polish",
            "instruction": "加强诡异感，但不要改事件。",
            "selected_text": "她看见第二行字慢慢浮出来。",
            "chapter_text": "屏幕亮着。她看见第二行字慢慢浮出来。",
            "selection_start": 5,
            "selection_end": 19,
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: meta" in response.text
    assert "event: delta" in response.text
    assert "event: result" in response.text
    assert "event: done" in response.text

    events = parse_sse_data(response.text)
    event_types = [event["type"] for event in events]
    assert event_types[0] == "meta"
    assert "delta" in event_types
    assert event_types[-2:] == ["result", "done"]
    result = next(event for event in events if event["type"] == "result")
    assert result["replacement"]
    assert result["used_remote_model"] is False
    assert result["selection"] == {"start": 5, "end": 19, "has_selection": True}
    assert "加强诡异感" in result["reasoning"]
