from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from app.db.session import Base, engine
from app.main import app


ROOT = Path(__file__).resolve().parents[2]


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
                "title": "旧正典流程删除测试",
                "genre": "工业奇幻",
                "target_reader": "喜欢长线伏笔和制度压迫的长篇读者",
                "premise": "一个低等矿工发现体内封印着最后一条真龙。",
                "style_guide": "沉重、史诗、成长。",
                "language": "zh-CN",
                "planned_chapter_count": 120,
                "chapter_word_target": 2500,
            },
        )
    )
    return data["project"]["id"]


def test_legacy_local_canon_workflow_modules_are_removed() -> None:
    deleted_paths = [
        "backend/app/agents/canon_workflow.py",
        "backend/app/services/canon_service.py",
        "backend/app/services/canon_merge.py",
        "backend/app/services/entity_router.py",
        "backend/app/services/validators.py",
        "backend/app/storage/canon_store.py",
        "backend/app/schemas/canon.py",
    ]
    for path in deleted_paths:
        assert not (ROOT / path).exists(), f"{path} should stay deleted"


def test_canon_studio_api_routes_are_removed_from_public_api() -> None:
    reset_database()
    client = TestClient(app)
    project_id = create_project(client)

    response = client.post(
        f"/api/projects/{project_id}/canon-studio/run",
        json={
            "worldview": "帝国依靠龙骨能源维持工业文明。",
            "one_sentence_story": "一个低等矿工发现自己体内封印着最后一条真龙。",
            "genre": "奇幻 / 工业幻想",
            "target_length": "长篇，多卷结构",
            "tone": "沉重、史诗、成长",
        },
    )
    assert response.status_code in {404, 405}

    for path in ["store", "final-outline"]:
        response = client.get(f"/api/projects/{project_id}/canon-studio/{path}")
        assert response.status_code in {404, 405}


def test_cli_no_longer_exposes_legacy_canon_run_command() -> None:
    completed = subprocess.run(
        [sys.executable, str(ROOT / "main.py"), "canon-run"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode != 0
    assert "invalid choice" in completed.stderr
