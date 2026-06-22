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
    list_prompt_workflows,
    load_catalog_prompt,
)
from app.agents.shared.prompt_node_contracts import get_prompt_node_contract
from app.services.studio_service import studio_service


def test_long_novel_catalog_covers_all_prompt_files() -> None:
    entries = list_long_novel_prompt_entries()

    assert len(entries) == 35
    assert LONG_NOVEL_PROMPT_IDS[0] == "general_control"
    assert LONG_NOVEL_PROMPT_IDS[-1] == "creation_title_packaging"
    assert entries[0].filename == "00_general_control_prompt.md"
    assert entries[-1].filename == "34_creation_title_packaging_prompt.md"


def test_catalog_loads_prompt_text_and_metadata() -> None:
    entry = get_prompt_entry("chapter_card")
    text = load_catalog_prompt("chapter_card")

    assert entry.index == 8
    assert entry.workflow == "chapter_production"
    assert entry.default_agent == "chapter_planner"
    assert text.startswith("# 8. 单章章节卡生成提示词")
    assert "本章核心功能" in text


def test_outline_prompt_assets_are_classified_as_debate_support_not_legacy_flow() -> None:
    for prompt_id in ["macro_outline", "ending_backcast", "volume_outline", "rolling_chapter_outline"]:
        entry = get_prompt_entry(prompt_id)
        assert entry.workflow == "outline_debate_support"


def test_agent_bindings_route_new_prompt_library_to_existing_agents() -> None:
    assert "novel_constitution" in AGENT_PROMPT_BINDINGS["chief_architect"]
    assert "chapter_card" in AGENT_PROMPT_BINDINGS["chapter_planner"]
    assert "scene_outline" in AGENT_PROMPT_BINDINGS["plot_narrator"]
    assert "draft_self_check" in AGENT_PROMPT_BINDINGS["reviewer"]
    assert "narrative_ledger_update" in AGENT_PROMPT_BINDINGS["canon_curator"]
    assert "core_conflict_system" not in AGENT_PROMPT_BINDINGS["creation_star"]
    assert "novel_constitution" not in AGENT_PROMPT_BINDINGS["creation_star"]


def test_worldview_draw_prompt_is_dedicated_to_conflict_engine_seed() -> None:
    entry = get_prompt_entry("creation_worldview_draw")
    text = load_catalog_prompt("creation_worldview_draw")

    assert entry.index == 32
    assert entry.workflow == "creation_star"
    assert entry.default_agent == "creation_star"
    assert "长篇小说世界观抽卡 Agent" in text
    assert "冲突发动机种子" in text
    assert "不要生成核心矛盾系统" in text
    assert "不要生成小说宪法" in text
    assert "核心矛盾系统如下" not in text
    assert "生成一份“长篇小说宪法”" not in text


def test_protagonist_draw_prompt_is_dedicated_to_character_cards() -> None:
    entry = get_prompt_entry("creation_protagonist_draw")
    text = load_catalog_prompt("creation_protagonist_draw")

    assert entry.index == 33
    assert entry.workflow == "creation_star"
    assert entry.default_agent == "creation_star"
    assert "长篇小说主角人设抽卡 Agent" in text
    assert "world_rule_connection" in text
    assert "conflict_seed" in text
    assert "ability_cost" in text
    assert "不要生成核心矛盾系统" in text
    assert "不要生成小说宪法" in text
    assert "核心矛盾系统如下" not in text
    assert "生成一份“长篇小说宪法”" not in text


def test_title_packaging_prompt_is_dedicated_to_title_and_selling_point_cards() -> None:
    entry = get_prompt_entry("creation_title_packaging")
    text = load_catalog_prompt("creation_title_packaging")
    workflow = next(item for item in list_prompt_workflows() if item["key"] == "creation_star")

    assert entry.index == 34
    assert entry.workflow == "creation_star"
    assert entry.default_agent == "creation_star"
    assert entry.filename == "34_creation_title_packaging_prompt.md"
    assert workflow["prompt_ids"] == [
        "creation_worldview_draw",
        "creation_protagonist_draw",
        "creation_title_packaging",
    ]
    assert "长篇小说书名与包装抽卡 Agent" in text
    assert "basic_info" in text
    assert "selected_worldview" in text
    assert "selected_protagonist" in text
    assert "core_selling_point" in text
    assert "reader_expectation" in text
    assert "platform_style" in text
    assert "one_sentence_ad" in text
    assert "不要生成世界观" in text
    assert "不要生成主角人设" in text
    assert "不要生成核心矛盾系统" in text
    assert "不要生成小说宪法" in text
    assert "只输出严格 JSON object" in text
    assert "核心矛盾系统如下" not in text
    assert "生成一份“长篇小说宪法”" not in text


def test_core_conflict_prompt_reads_creation_seed_fields() -> None:
    text = load_catalog_prompt("core_conflict_system")

    for marker in [
        "project_seed",
        "selected_worldview",
        "selected_protagonist",
        "selected_title",
        "market_position",
        "conflict_engine_seed",
        "long_term_desire",
        "ability_cost",
        "relationship_hooks",
        "core_selling_point",
        "reader_expectation",
        "protagonist_desire",
        "world_resistance",
        "core_conflict",
    ]:
        assert marker in text

    assert "不要生成小说宪法" in text
    assert "只输出严格 JSON object" in text
    assert "题材类型：【填写" not in text
    assert "请输出 5 套不同的核心矛盾系统" not in text


def test_novel_constitution_prompt_reads_seed_and_core_conflict_fields() -> None:
    text = load_catalog_prompt("novel_constitution")

    for marker in [
        "project_seed",
        "selected_worldview",
        "selected_protagonist",
        "selected_title",
        "market_position",
        "core_conflict_system",
        "basic_positioning",
        "core_narrative_engine",
        "protagonist_arc",
        "world_rules",
        "character_functions",
        "theme_pressure",
        "cost_mechanism",
        "forbidden_directions",
        "long_form_sustainability",
    ]:
        assert marker in text

    assert "只输出严格 JSON object" in text
    assert "【粘贴核心矛盾系统】" not in text
    assert "请按照以下结构输出：" not in text


def test_agent_spec_prompt_bodies_live_in_markdown_files() -> None:
    prompt_root = Path(__file__).resolve().parents[1] / "app" / "prompts"

    assert "creation_star" in AGENT_SPEC_PROMPT_FILES
    assert "editor_orchestrator" not in AGENT_SPEC_PROMPT_FILES
    for agent_name, relative_path in AGENT_SPEC_PROMPT_FILES.items():
        prompt_path = prompt_root / relative_path

        assert prompt_path.exists()
        prompt_text = prompt_path.read_text(encoding="utf-8").strip()
        assert load_agent_spec_prompt(agent_name) == prompt_text
        assert prompt_text in AGENT_SPECS_BY_NAME[agent_name].prompt
    remaining_files = {path.stem for path in (prompt_root / "agent_specs").glob("*.md")}
    assert remaining_files == set(AGENT_SPEC_PROMPT_FILES)


def test_agent_prompts_module_does_not_embed_long_prompt_bodies() -> None:
    source = (Path(__file__).resolve().parents[1] / "app" / "agents" / "prompts.py").read_text(encoding="utf-8")

    assert 'prompt="""' not in source
    assert "你是“长篇小说总编统筹 Agent”" not in source
    assert "你是专业网文立项与灵感抽卡 Agent" not in source


def test_studio_workflows_do_not_expose_legacy_outline_lanes() -> None:
    workflows = studio_service.list_workflows()["workflows"]
    keys = {item["key"] for item in workflows}

    assert {
        "conception",
        "chapter_production",
        "serial_maintenance",
        "special_design",
    }.issubset(keys)
    assert "outline_planning" not in keys
    assert "book_structure_lifecycle" not in keys
    assert "volume_rolling_lifecycle" not in keys
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


def test_prompt_lifecycle_workflows_exclude_legacy_outline_generation_lanes() -> None:
    workflows = list_prompt_lifecycle_workflows()
    keys = [workflow["key"] for workflow in workflows]

    assert keys == [
        "story_foundation_lifecycle",
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


def test_lifecycle_node_tags_are_unique_for_shortcut_nodes() -> None:
    workflows = list_prompt_lifecycle_workflows()

    for workflow in workflows:
        for node in workflow["nodes"]:
            assert node["tags"] == list(dict.fromkeys(node["tags"]))

    special_booster = next(
        item for item in workflows
        if item["key"] == "special_booster_lifecycle"
    )
    shortcut_nodes = [
        node
        for node in special_booster["nodes"]
        if node["id"] in {"minimal_work_template", "single_round_generation_combo"}
    ]

    assert shortcut_nodes
    assert all(node["tags"].count("shortcut") == 1 for node in shortcut_nodes)


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
