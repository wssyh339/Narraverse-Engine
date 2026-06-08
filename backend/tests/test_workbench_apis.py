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


def create_project(client: TestClient) -> str:
    data = assert_success(
        client.post(
            "/api/projects",
            json={
                "title": "统一工作室验收",
                "genre": "悬疑",
                "target_reader": "长篇小说作者",
                "premise": "一名编辑发现自己修改的小说会改变现实。",
                "style_guide": "克制、清晰。",
                "language": "zh-CN",
                "planned_chapter_count": 20,
                "chapter_word_target": 1800,
            },
        )
    )
    return data["project"]["id"]


def test_workbench_directory_notes_proposals_and_backup_flow() -> None:
    reset_database()
    client = TestClient(app)
    project_id = create_project(client)

    default_volumes = assert_success(client.get(f"/api/projects/{project_id}/volumes"))["volumes"]
    assert len(default_volumes) == 1
    assert default_volumes[0]["volume_no"] == 1

    volume = assert_success(
        client.post(
            f"/api/projects/{project_id}/volumes",
            json={"title": "第二卷：被改写的现实", "outline": "主角发现修改规则。"},
        )
    )["volume"]
    assert volume["volume_no"] == 2

    chapter_one = assert_success(
        client.post(
            f"/api/projects/{project_id}/chapters",
            json={"volume_no": 1, "title": "编辑器里的血字", "outline": "发现第一条异常规则。"},
        )
    )["chapter"]
    chapter_two = assert_success(
        client.post(
            f"/api/projects/{project_id}/chapters",
            json={"volume_no": 1, "title": "被删除的人", "outline": "现实开始响应改写。"},
        )
    )["chapter"]

    reordered = assert_success(
        client.post(
            f"/api/projects/{project_id}/chapters/reorder",
            json={"chapter_ids": [chapter_two["id"], chapter_one["id"]]},
        )
    )["chapters"]
    assert [item["id"] for item in reordered] == [chapter_two["id"], chapter_one["id"]]

    assert_success(client.post(f"/api/projects/{project_id}/chapters/{chapter_two['id']}/trash"))
    active = assert_success(client.get(f"/api/projects/{project_id}/chapters"))["chapters"]
    assert chapter_two["id"] not in {item["id"] for item in active}
    trash = assert_success(client.get(f"/api/projects/{project_id}/chapters/trash"))["chapters"]
    assert {item["id"] for item in trash} == {chapter_two["id"]}
    assert_success(client.post(f"/api/projects/{project_id}/chapters/{chapter_two['id']}/restore"))

    note = assert_success(
        client.post(
            f"/api/projects/{project_id}/notes",
            json={"title": "第一卷灵感", "content": "让删除操作成为世界规则。", "note_type": "inspiration"},
        )
    )["note"]
    updated_note = assert_success(
        client.put(
            f"/api/projects/{project_id}/notes/{note['id']}",
            json={"content": "删除操作会让现实中的对应对象被遗忘。", "is_pinned": True},
        )
    )["note"]
    assert updated_note["is_pinned"] is True

    assert_success(
        client.put(
            f"/api/projects/{project_id}/chapters/{chapter_one['id']}",
            json={"final_text": "编辑器里出现了一行不属于她的血字。", "status": "drafted"},
        )
    )
    snapshot = assert_success(
        client.post(
            f"/api/projects/{project_id}/chapters/{chapter_one['id']}/snapshot",
            json={"user_note": "手动快照"},
        )
    )["version"]
    assert snapshot["user_note"] == "手动快照"

    proposal = assert_success(
        client.post(
            f"/api/projects/{project_id}/chapters/{chapter_one['id']}/proposals",
            json={"tool_name": "polish", "instruction": "增强悬疑感。"},
        )
    )["proposal"]
    assert proposal["status"] == "pending"
    assert proposal["original_content"] != proposal["proposed_content"]
    assert proposal["diff"]

    applied = assert_success(
        client.post(f"/api/projects/{project_id}/proposals/{proposal['id']}/apply")
    )["proposal"]
    assert applied["status"] == "applied"
    chapter_after = assert_success(
        client.get(f"/api/projects/{project_id}/chapters/{chapter_one['id']}")
    )["chapter"]
    assert chapter_after["final_text"] == proposal["proposed_content"]

    backup = assert_success(client.get(f"/api/projects/{project_id}/backup"))["backup"]
    assert backup["project"]["id"] == project_id
    assert backup["volumes"]
    assert backup["chapters"]
    assert backup["notes"]
    assert backup["editor_proposals"]

    assert_success(client.delete(f"/api/projects/{project_id}/notes/{note['id']}"))
    notes = assert_success(client.get(f"/api/projects/{project_id}/notes"))["notes"]
    assert notes == []


def test_batch_trash_chapters_moves_selected_outline_items_to_trash() -> None:
    reset_database()
    client = TestClient(app)
    project_id = create_project(client)

    chapters = [
        assert_success(
            client.post(
                f"/api/projects/{project_id}/chapters",
                json={"volume_no": 1, "title": f"第{index}章", "outline": f"第{index}章章纲"},
            )
        )["chapter"]
        for index in range(1, 4)
    ]

    result = assert_success(
        client.post(
            f"/api/projects/{project_id}/chapters/trash/batch",
            json={"chapter_ids": [chapters[0]["id"], chapters[2]["id"]]},
        )
    )
    assert result["deleted"] is True
    assert {item["id"] for item in result["chapters"]} == {chapters[0]["id"], chapters[2]["id"]}

    active = assert_success(client.get(f"/api/projects/{project_id}/chapters"))["chapters"]
    assert {item["id"] for item in active} == {chapters[1]["id"]}
    trash = assert_success(client.get(f"/api/projects/{project_id}/chapters/trash"))["chapters"]
    assert {item["id"] for item in trash} == {chapters[0]["id"], chapters[2]["id"]}
