from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from app.agents.prompts import (
    AGENT_PROMPT_BINDINGS,
    AGENT_SPEC_PROMPT_FILES,
    AGENT_SPECS_BY_NAME,
    load_agent_spec_prompt,
)
from app.agents.shared.prompt_catalog import (
    LONG_NOVEL_PROMPT_IDS,
    get_prompt_entry,
    list_long_novel_prompt_entries,
    load_catalog_prompt,
)
from app.agents.shared.prompt_node_contracts import get_prompt_node_contract
from app.services.studio_service import studio_service


def test_long_novel_catalog_covers_all_32_prompt_files() -> None:
    entries = list_long_novel_prompt_entries()

    assert len(entries) == 32
    assert LONG_NOVEL_PROMPT_IDS[0] == "general_control"
    assert LONG_NOVEL_PROMPT_IDS[-1] == "single_round_generation_combo"
    assert entries[0].filename == "00_general_control_prompt.md"
    assert entries[-1].filename == "31_single_round_generation_combo_prompt.md"


def test_catalog_loads_prompt_text_and_metadata() -> None:
    entry = get_prompt_entry("chapter_card")
    text = load_catalog_prompt("chapter_card")

    assert entry.index == 8
    assert entry.workflow == "chapter_production"
    assert entry.default_agent == "chapter_planner"
    assert text.startswith("# 8. 单章章节卡生成提示词")
    assert "本章核心功能" in text


def test_agent_bindings_route_new_prompt_library_to_existing_agents() -> None:
    assert "novel_constitution" in AGENT_PROMPT_BINDINGS["chief_architect"]
    assert "chapter_card" in AGENT_PROMPT_BINDINGS["chapter_planner"]
    assert "scene_outline" in AGENT_PROMPT_BINDINGS["plot_narrator"]
    assert "draft_self_check" in AGENT_PROMPT_BINDINGS["reviewer"]
    assert "narrative_ledger_update" in AGENT_PROMPT_BINDINGS["canon_curator"]


def test_agent_spec_prompt_bodies_live_in_markdown_files() -> None:
    prompt_root = Path(__file__).resolve().parents[1] / "app" / "prompts"

    assert "creation_star" in AGENT_SPEC_PROMPT_FILES
    assert "editor_orchestrator" in AGENT_SPEC_PROMPT_FILES
    for agent_name, relative_path in AGENT_SPEC_PROMPT_FILES.items():
        prompt_path = prompt_root / relative_path

        assert prompt_path.exists()
        prompt_text = prompt_path.read_text(encoding="utf-8").strip()
        assert load_agent_spec_prompt(agent_name) == prompt_text
        assert prompt_text in AGENT_SPECS_BY_NAME[agent_name].prompt


def test_agent_prompts_module_does_not_embed_long_prompt_bodies() -> None:
    source = (Path(__file__).resolve().parents[1] / "app" / "agents" / "prompts.py").read_text(encoding="utf-8")

    assert 'prompt="""' not in source
    assert "你是“长篇小说总编统筹 Agent”" not in source
    assert "你是专业网文立项与灵感抽卡 Agent" not in source


def test_studio_workflows_expose_five_long_novel_lanes() -> None:
    workflows = studio_service.list_workflows()["workflows"]
    keys = {item["key"] for item in workflows}

    assert {
        "conception",
        "outline_planning",
        "chapter_production",
        "serial_maintenance",
        "special_design",
    }.issubset(keys)
    chapter = next(item for item in workflows if item["key"] == "chapter_production")
    assert chapter["prompt_ids"][:3] == ["chapter_card", "scene_outline", "draft_generation"]
    assert chapter["agents"][:2] == ["chapter_planner", "plot_narrator"]


def test_all_long_novel_prompts_have_prompt_agent_node_contracts() -> None:
    for prompt_id in LONG_NOVEL_PROMPT_IDS:
        contract = get_prompt_node_contract(prompt_id)

        assert contract.prompt_id == prompt_id
        assert contract.node_subtype == "prompt_agent"
        assert contract.required_inputs
        assert contract.produces
        assert contract.input_schema.model_json_schema()["type"] == "object"
        assert contract.output_schema.model_json_schema()["type"] == "object"


def test_prompt_workflow_nodes_expose_specific_io_and_schema() -> None:
    workflows = studio_service.list_workflows()["workflows"]
    chapter = next(item for item in workflows if item["key"] == "chapter_production")
    chapter_card = next(node for node in chapter["nodes"] if node["id"] == "chapter_card")
    draft_generation = next(node for node in chapter["nodes"] if node["id"] == "draft_generation")

    assert chapter_card["node_subtype"] == "prompt_agent"
    assert chapter_card["inputs"] == [
        "novel_constitution",
        "volume_outline",
        "rolling_chapter_outline",
        "narrative_ledger",
        "previous_chapter_summary",
        "user_instruction",
    ]
    assert chapter_card["outputs"] == ["chapter_card"]
    assert chapter_card["input_schema"]["title"] == "ChapterCardInput"
    assert chapter_card["output_schema"]["title"] == "ChapterCardOutput"
    assert "本章核心功能" in chapter_card["output_schema"]["properties"]["core_function"]["description"]

    assert draft_generation["node_subtype"] == "prompt_agent"
    assert draft_generation["inputs"] == [
        "novel_constitution",
        "chapter_card",
        "scene_outline",
        "narrative_ledger",
        "style_profile",
        "canon_context",
    ]
    assert draft_generation["outputs"] == ["integrated_draft"]
    assert draft_generation["output_schema"]["title"] == "DraftGenerationOutput"


def test_list_agents_exposes_prompt_binding_metadata() -> None:
    class EmptyQuery:
        def filter(self, *_args: object, **_kwargs: object) -> "EmptyQuery":
            return self

        def all(self) -> list[object]:
            return []

    fake_db = SimpleNamespace(query=lambda _model: EmptyQuery())
    agents = studio_service.list_agents(fake_db)["agents"]
    planner = next(agent for agent in agents if agent["name"] == "chapter_planner")

    assert planner["prompt_ids"][:3] == ["macro_outline", "ending_backcast", "volume_outline"]
    assert planner["prompt_titles"]["chapter_card"] == "单章章节卡生成"


from app.agents.shared.prompt_catalog import list_prompt_lifecycle_workflows


def test_prompt_lifecycle_workflows_expose_six_story_lanes() -> None:
    workflows = list_prompt_lifecycle_workflows()
    keys = [workflow["key"] for workflow in workflows]

    assert keys == [
        "story_foundation_lifecycle",
        "book_structure_lifecycle",
        "volume_rolling_lifecycle",
        "chapter_closed_loop_lifecycle",
        "serial_maintenance_lifecycle",
        "special_booster_lifecycle",
    ]
    assert all(workflow["workflow_kind"] == "prompt_lifecycle" for workflow in workflows)


def test_chapter_closed_loop_keeps_shortcuts_out_of_formal_chain() -> None:
    workflow = next(
        item for item in list_prompt_lifecycle_workflows()
        if item["key"] == "chapter_closed_loop_lifecycle"
    )
    node_ids = [node["id"] for node in workflow["nodes"]]

    assert node_ids == [
        "next_chapter_state_change",
        "chapter_card",
        "scene_outline",
        "draft_generation",
        "draft_self_check",
        "draft_rewrite",
        "narrative_ledger_update",
    ]
    assert "minimal_work_template" not in node_ids
    assert "single_round_generation_combo" not in node_ids

    edge_labels = {edge["label"] for edge in workflow["edges"]}
    assert {"passed", "needs_revision / blocked", "更新叙事账本"}.issubset(edge_labels)


def test_special_booster_contains_shortcut_prompt_agents() -> None:
    workflow = next(
        item for item in list_prompt_lifecycle_workflows()
        if item["key"] == "special_booster_lifecycle"
    )
    node_ids = {node["id"] for node in workflow["nodes"]}

    assert {"minimal_work_template", "single_round_generation_combo"}.issubset(node_ids)
    shortcut_nodes = [node for node in workflow["nodes"] if node["id"] in {"minimal_work_template", "single_round_generation_combo"}]
    assert all(node["node_subtype"] == "prompt_agent" for node in shortcut_nodes)
    assert all("shortcut" in node["tags"] for node in shortcut_nodes)


def test_lifecycle_prompt_nodes_reuse_prompt_agent_schemas() -> None:
    workflows = list_prompt_lifecycle_workflows()
    prompt_nodes = [
        node
        for workflow in workflows
        for node in workflow["nodes"]
        if node["type"] == "prompt"
    ]

    assert prompt_nodes
    assert all(node["node_subtype"] == "prompt_agent" for node in prompt_nodes)
    assert all(node["input_schema"]["type"] == "object" for node in prompt_nodes)
    assert all(node["output_schema"]["type"] == "object" for node in prompt_nodes)
