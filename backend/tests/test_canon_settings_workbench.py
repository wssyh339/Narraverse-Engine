import os

os.environ["DATABASE_URL"] = "sqlite:///./data/test_novel_agent.db"
os.environ["JOB_ARTIFACT_DIR"] = "backend/artifacts/test-runs"

from fastapi.testclient import TestClient

from app.db.session import Base, engine
from app.main import app


def reset_database() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def assert_success(payload: dict) -> dict:
    assert payload["success"] is True
    assert payload["error"] is None
    return payload["data"]


def create_project(client: TestClient) -> str:
    payload = assert_success(
        client.post(
            "/api/v1/projects",
            json={
                "title": "血脉王朝",
                "genre": "都市玄幻",
                "target_reader": "喜欢复仇、权谋和长期伏笔的读者",
                "premise": "低血统主角逐步瓦解血脉垄断。",
                "style_guide": "冷静、压迫、技术性爽感。",
                "language": "zh-CN",
                "planned_chapter_count": 120,
                "chapter_word_target": 3000,
            },
        ).json()
    )
    return payload["project"]["id"]


def test_canon_settings_tree_versions_proposals_health_and_rollback() -> None:
    reset_database()
    client = TestClient(app)
    project_id = create_project(client)
    chapter = assert_success(
        client.post(
            f"/api/v1/projects/{project_id}/chapters",
            json={"volume_no": 1, "title": "第一章：血检", "outline": "陆沉被血脉评级压制。", "word_target": 3000},
        ).json()
    )["chapter"]

    character = assert_success(
        client.post(
            f"/api/v1/projects/{project_id}/characters",
            json={
                "name": "陆沉",
                "role_type": "protagonist",
                "importance_level": "core",
                "importance_score": 96,
                "summary": "低血统复仇者。",
                "current_status": "active",
                "source_chapter_id": chapter["id"],
                "updated_reason": "第1章登场。",
            },
        ).json()
    )["character"]

    tree = assert_success(client.get(f"/api/v1/projects/{project_id}/settings/tree").json())
    assert tree["health"]["official_count"] >= 1
    assert tree["health"]["versioned_count"] >= 1
    assert any(node["title"] == "人物" and node["node_type"] == "folder" for node in tree["nodes"])
    character_node = next(node for node in tree["nodes"] if node["ref_type"] == "character" and node["ref_id"] == character["id"])
    assert character_node["title"] == "陆沉"
    assert character_node["importance_level"] == "core"
    assert character_node["activity_status"] == "active"

    versions = assert_success(client.get(f"/api/v1/projects/{project_id}/settings/characters/{character['id']}/versions").json())["versions"]
    assert len(versions) == 1
    assert versions[0]["version_no"] == 1
    assert versions[0]["source_chapter_id"] == chapter["id"]
    assert versions[0]["content"]["summary"] == "低血统复仇者。"

    updated = assert_success(
        client.put(
            f"/api/v1/projects/{project_id}/characters/{character['id']}",
            json={
                "summary": "低血统复仇者，已经掌握血检漏洞。",
                "current_status": "active",
                "source_chapter_id": chapter["id"],
                "updated_reason": "第1章结尾发现血检漏洞。",
            },
        ).json()
    )["character"]
    assert "血检漏洞" in updated["summary"]

    versions = assert_success(client.get(f"/api/v1/projects/{project_id}/settings/characters/{character['id']}/versions").json())["versions"]
    assert [item["version_no"] for item in versions] == [1, 2]
    assert versions[-1]["change_reason"] == "第1章结尾发现血检漏洞。"

    rollback = assert_success(
        client.post(
            f"/api/v1/projects/{project_id}/settings/characters/{character['id']}/versions/{versions[0]['id']}/rollback",
            json={"user_note": "恢复为初登场状态"},
        ).json()
    )
    assert rollback["rolled_back"] is True
    assert rollback["character"]["summary"] == "低血统复仇者。"
    assert rollback["version"]["version_no"] == 3

    generated = assert_success(
        client.post(
            f"/api/v1/projects/{project_id}/settings/generate",
            json={"target": "world_facts", "instruction": "生成血脉等级制度规则", "count": 1, "preview_only": True},
        ).json()
    )
    assert generated["preview_only"] is True
    assert generated["proposals"], "preview_only generation should create reviewable canon proposals"

    proposal_id = generated["proposals"][0]["id"]
    approved = assert_success(client.post(f"/api/v1/projects/{project_id}/settings/proposals/{proposal_id}/approve").json())
    assert approved["proposal"]["approval_status"] == "approved"
    assert approved["applied_ref"]["ref_type"] == "world_fact"

    health = assert_success(client.get(f"/api/v1/projects/{project_id}/settings/health").json())["health"]
    assert health["official_count"] >= 2
    assert health["pending_proposal_count"] == 0
    assert "characters" in health["by_type"]

    folder = assert_success(
        client.post(
            f"/api/v1/projects/{project_id}/settings/folders",
            json={"title": "第一卷核心人物", "parent_id": "folder:characters", "sort_order": 1},
        ).json()
    )["node"]
    moved = assert_success(
        client.patch(
            f"/api/v1/projects/{project_id}/settings/nodes/{character_node['id']}/move",
            json={"parent_id": folder["id"], "sort_order": 1},
        ).json()
    )["node"]
    assert moved["metadata"]["custom_folder_id"] == folder["id"]

    locked = assert_success(
        client.put(
            f"/api/v1/projects/{project_id}/settings/characters/{character['id']}/locks",
            json={"locked_fields": ["summary", "secrets"], "reason": "核心身份不可静默覆盖"},
        ).json()
    )["node"]
    assert "summary" in locked["metadata"]["locked_fields"]

    blocked = client.put(
        f"/api/v1/projects/{project_id}/characters/{character['id']}",
        json={"summary": "Agent 试图覆盖核心身份。", "source_agent": "canon_curator", "updated_reason": "章后自动提取"},
    )
    assert blocked.status_code == 409
    pending = assert_success(client.get(f"/api/v1/projects/{project_id}/settings/proposals?status=pending").json())["proposals"]
    update_proposal = next(item for item in pending if item["operation"] == "update" and item["target_id"] == character["id"])
    approved_update = assert_success(
        client.post(
            f"/api/v1/projects/{project_id}/settings/proposals/{update_proposal['id']}/approve",
            json={"user_note": "用户确认覆盖锁定摘要"},
        ).json()
    )
    assert approved_update["applied_ref"]["item"]["summary"] == "Agent 试图覆盖核心身份。"

    duplicate = assert_success(
        client.post(
            f"/api/v1/projects/{project_id}/characters",
            json={"name": "陆 沉", "role_type": "supporting", "importance_level": "major", "summary": "疑似重复角色。"},
        ).json()
    )["character"]
    duplicate_scan = assert_success(
        client.post(
            f"/api/v1/projects/{project_id}/settings/duplicates/scan",
            json={"ref_types": ["character"], "threshold": 0.55, "create_proposals": True},
        ).json()
    )
    assert duplicate_scan["candidates"]
    merge_proposal = next(item for item in duplicate_scan["proposals"] if item["operation"] == "merge")
    merged = assert_success(
        client.post(
            f"/api/v1/projects/{project_id}/settings/proposals/{merge_proposal['id']}/approve",
            json={"user_note": "确认合并重复人物"},
        ).json()
    )
    assert merged["applied_ref"]["source_ref"]["ref_id"] in {character["id"], duplicate["id"]}

    impact = assert_success(client.get(f"/api/v1/projects/{project_id}/settings/characters/{character['id']}/impact").json())
    assert impact["summary"]["version_count"] >= 1
    assert any(item["title"] == "第一章：血检" for item in impact["chapters"])

    markdown_export = assert_success(client.get(f"/api/v1/projects/{project_id}/settings/export?format=markdown").json())
    assert markdown_export["filename"].endswith(".md")
    assert "正典包" in markdown_export["content"]
    json_export = assert_success(client.get(f"/api/v1/projects/{project_id}/settings/export?format=json").json())
    assert json_export["package"]["health"]["official_count"] >= 1
