from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

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
                "title": "正典推演测试",
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


def test_entity_router_and_completion_ticket_generation() -> None:
    from app.schemas.canon import CanonEntity, EntityLevel, EntityType
    from app.services.entity_router import CanonCompletionRouter, requires_completion

    router = CanonCompletionRouter()
    character = CanonEntity(
        name="最后龙裔矿工",
        entity_type=EntityType.CHARACTER,
        level=EntityLevel.S,
        story_function="承担全书命运与主题选择。",
        first_appearance="SeedInterpreterNode",
        responsible_agent="EntityExtractorAgent",
        payload={"external_goal": "逃离矿区"},
    )
    ticket = router.ticket_for_entity(character)

    assert requires_completion(character.level) is True
    assert ticket is not None
    assert ticket.suggested_agent == "CharacterArcAgent"
    assert "inner_need" in ticket.missing_fields
    assert "arc_climax" in ticket.missing_fields

    item = CanonEntity(
        name="龙骨能源",
        entity_type=EntityType.ITEM,
        level=EntityLevel.A,
        story_function="决定帝国工业秩序与主线争夺。",
        first_appearance="SeedInterpreterNode",
        responsible_agent="EntityExtractorAgent",
        payload={},
    )
    item_ticket = router.ticket_for_entity(item)
    assert item_ticket is not None
    assert item_ticket.suggested_agent == "ItemLoreAgent"
    assert "limitation" in item_ticket.missing_fields


def test_canon_store_merge_and_continuity_gate(tmp_path: Path) -> None:
    from app.schemas.canon import CanonEntity, EntityLevel, EntityType
    from app.services.canon_merge import CanonMergeNode
    from app.services.validators import ContinuityAgentValidator
    from app.storage.canon_store import CanonStore

    store = CanonStore(project_id="canon_test", base_dir=tmp_path)
    incomplete_secret = CanonEntity(
        name="真龙封印",
        entity_type=EntityType.SECRET,
        level=EntityLevel.S,
        story_function="改变主角命运和最终高潮选择。",
        first_appearance="SeedInterpreterNode",
        responsible_agent="EntityExtractorAgent",
        payload={"truth": "主角体内封印着最后真龙"},
    )

    merge_result = CanonMergeNode().merge_entities(store, [incomplete_secret])
    assert merge_result.completion_tickets
    assert store.find_incomplete_entities()
    failed_report = ContinuityAgentValidator().validate_store(store)
    assert failed_report["passed"] is False
    assert "S / A 级实体缺档案" in failed_report["issues"][0]["message"]

    completed = incomplete_secret.model_copy(
        update={
            "completion_status": "complete",
            "continuity_checked": True,
            "payload": {
                "truth": "主角体内封印着最后真龙",
                "who_knows": ["帝国能源署"],
                "who_misunderstands": ["主角"],
                "who_hides_it": ["帝国能源署"],
                "why_hidden": "公开真相会摧毁龙骨能源合法性。",
                "cost_if_revealed": "矿区叛乱和帝国追杀同步爆发。",
                "false_explanation": "矿工只是能源病变患者。",
                "foreshadowing_clues": ["龙骨矿脉在主角靠近时共鸣"],
                "reveal_timing": "第一卷卷末",
                "impact_on_character": "迫使主角承认自己不是受害者那么简单。",
                "impact_on_world": "帝国能源神话开始崩塌。",
                "impact_on_conflict": "私人逃亡升级为制度追捕。",
                "impact_on_climax": "高潮选择必须决定真龙是否复苏。",
                "why_not_revealed_earlier": "帝国用矿难记录掩盖真相。",
                "if_removed_what_breaks": "主线命运压力和终局选择失效。",
            },
        }
    )
    CanonMergeNode().merge_entities(store, [completed])
    assert ContinuityAgentValidator().validate_store(store)["passed"] is True

    conflict = completed.model_copy(update={"payload": {**completed.payload, "truth": "真龙已死"}})
    conflicts = store.detect_conflict(conflict)
    assert conflicts
    assert conflicts[0]["type"] == "payload_conflict"


def test_canon_workflow_generates_final_outline_and_store(tmp_path: Path) -> None:
    from app.schemas.canon import CanonRunRequest, DramaNodeType
    from app.services.canon_service import run_canon_workflow

    result = run_canon_workflow(
        CanonRunRequest(
            project_id="sample_novel_001",
            worldview="帝国依靠龙骨能源维持工业文明。",
            one_sentence_story="一个低等矿工发现自己体内封印着最后一条真龙。",
            genre="奇幻 / 工业幻想",
            target_length="长篇，多卷结构",
            tone="沉重、史诗、成长",
        ),
        base_dir=tmp_path,
    )

    assert Path(result.final_outline_path).exists()
    assert Path(result.canon_store_path).exists()
    assert "故事核心种子" in result.final_outline
    assert "连续性审查报告" in result.final_outline
    assert result.continuity_report["passed"] is True
    assert {"EntityExtractorAgent", "ContinuityAgent", "ExportNode"}.issubset(set(result.agent_trace))
    node_types = {node.node_type for node in result.drama_nodes}
    assert {DramaNodeType.CRISIS, DramaNodeType.CLIMAX, DramaNodeType.RESOLUTION}.issubset(node_types)

    store = json.loads(Path(result.canon_store_path).read_text(encoding="utf-8"))
    important = [
        entity
        for entity in store["entities"].values()
        if entity["level"] in {"S", "A"}
    ]
    assert important
    assert all(entity["completion_status"] == "complete" for entity in important)
    assert all(entity["continuity_checked"] is True for entity in important)


def test_canon_studio_api_run_and_downloads() -> None:
    reset_database()
    client = TestClient(app)
    project_id = create_project(client)

    data = assert_success(
        client.post(
            f"/api/projects/{project_id}/canon-studio/run",
            json={
                "worldview": "帝国依靠龙骨能源维持工业文明。",
                "one_sentence_story": "一个低等矿工发现自己体内封印着最后一条真龙。",
                "genre": "奇幻 / 工业幻想",
                "target_length": "长篇，多卷结构",
                "tone": "沉重、史诗、成长",
            },
        )
    )

    assert data["continuity_report"]["passed"] is True
    assert "final_outline.md" in data["final_outline_path"]
    assert "canon_store.json" in data["canon_store_path"]

    store_data = assert_success(client.get(f"/api/projects/{project_id}/canon-studio/store"))
    assert store_data["store"]["entities"]

    outline_data = assert_success(client.get(f"/api/projects/{project_id}/canon-studio/final-outline"))
    assert "危机 / 高潮 / 结果链" in outline_data["markdown"]


def test_canon_cli_runs_sample_input(tmp_path: Path) -> None:
    sample = tmp_path / "sample_input.json"
    output = tmp_path / "final_outline.md"
    sample.write_text(
        json.dumps(
            {
                "project_id": "sample_novel_001",
                "worldview": "帝国依靠龙骨能源维持工业文明。",
                "one_sentence_story": "一个低等矿工发现自己体内封印着最后一条真龙。",
                "genre": "奇幻 / 工业幻想",
                "target_length": "长篇，多卷结构",
                "tone": "沉重、史诗、成长",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    repo_root = Path(__file__).resolve().parents[2]
    completed = subprocess.run(
        [sys.executable, str(repo_root / "main.py"), "canon-run", "--input", str(sample), "--output", str(output)],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert output.exists()
    assert (output.parent / "canon_store.json").exists()
    assert "final_outline.md" in completed.stdout
    assert "故事核心种子" in output.read_text(encoding="utf-8")
