from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.agents.shared.prompt_node_contracts import get_prompt_node_contract


PROMPT_DIR = Path(__file__).resolve().parents[2] / "prompts"


@dataclass(frozen=True)
class PromptCatalogEntry:
    prompt_id: str
    index: int
    title: str
    filename: str
    workflow: str
    default_agent: str


@dataclass(frozen=True)
class PromptWorkflowDefinition:
    key: str
    label: str
    description: str
    prompt_ids: tuple[str, ...]


@dataclass(frozen=True)
class PromptLifecycleWorkflowDefinition:
    key: str
    label: str
    description: str
    prompt_ids: tuple[str, ...]
    edges: tuple[dict[str, str], ...]
    trigger_policy: str = "manual"
    tags: tuple[str, ...] = ()


LONG_NOVEL_PROMPT_ENTRIES: tuple[PromptCatalogEntry, ...] = (
    PromptCatalogEntry("general_control", 0, "通用总控提示词", "00_general_control_prompt.md", "conception", "chief_architect"),
    PromptCatalogEntry("core_conflict_system", 1, "生成核心矛盾系统", "01_core_conflict_system_prompt.md", "conception", "chief_architect"),
    PromptCatalogEntry("novel_constitution", 2, "生成小说宪法", "02_novel_constitution_prompt.md", "conception", "chief_architect"),
    PromptCatalogEntry("constitution_stress_test", 3, "小说宪法压力测试", "03_constitution_stress_test_prompt.md", "conception", "reviewer"),
    PromptCatalogEntry("macro_outline", 4, "生成全书宏观大纲", "04_macro_outline_prompt.md", "outline_debate_support", "chapter_planner"),
    PromptCatalogEntry("ending_backcast", 5, "从结局反推路径", "05_ending_backcast_prompt.md", "outline_debate_support", "chapter_planner"),
    PromptCatalogEntry("volume_outline", 6, "生成分卷大纲", "06_volume_outline_prompt.md", "outline_debate_support", "chapter_planner"),
    PromptCatalogEntry("rolling_chapter_outline", 7, "生成当前卷滚动章节大纲", "07_rolling_chapter_outline_prompt.md", "outline_debate_support", "chapter_planner"),
    PromptCatalogEntry("chapter_card", 8, "单章章节卡生成", "08_chapter_card_prompt.md", "chapter_production", "chapter_planner"),
    PromptCatalogEntry("scene_outline", 9, "场景细纲生成", "09_scene_outline_prompt.md", "chapter_production", "plot_narrator"),
    PromptCatalogEntry("draft_generation", 10, "正文生成", "10_draft_generation_prompt.md", "chapter_production", "integrator"),
    PromptCatalogEntry("draft_self_check", 11, "正文自检", "11_draft_self_check_prompt.md", "chapter_production", "reviewer"),
    PromptCatalogEntry("draft_rewrite", 12, "正文改写", "12_draft_rewrite_prompt.md", "chapter_production", "reviewer"),
    PromptCatalogEntry("narrative_ledger_update", 13, "章后叙事账本更新", "13_narrative_ledger_update_prompt.md", "chapter_production", "canon_curator"),
    PromptCatalogEntry("foreshadowing_management", 14, "伏笔管理", "14_foreshadowing_management_prompt.md", "serial_maintenance", "canon_curator"),
    PromptCatalogEntry("character_arc_management", 15, "人物弧线管理", "15_character_arc_management_prompt.md", "serial_maintenance", "canon_curator"),
    PromptCatalogEntry("relationship_network_management", 16, "关系网管理", "16_relationship_network_management_prompt.md", "serial_maintenance", "canon_curator"),
    PromptCatalogEntry("world_rules_management", 17, "世界规则管理", "17_world_rules_management_prompt.md", "serial_maintenance", "fact_checker"),
    PromptCatalogEntry("timeline_check", 18, "时间线校验", "18_timeline_check_prompt.md", "serial_maintenance", "fact_checker"),
    PromptCatalogEntry("branch_plot_generation", 19, "多分支剧情生成", "19_branch_plot_generation_prompt.md", "serial_maintenance", "chapter_planner"),
    PromptCatalogEntry("structure_editor_review", 20, "结构编辑审查", "20_structure_editor_review_prompt.md", "serial_maintenance", "reviewer"),
    PromptCatalogEntry("ten_chapter_health_check", 21, "每 10 章结构体检", "21_ten_chapter_health_check_prompt.md", "serial_maintenance", "reviewer"),
    PromptCatalogEntry("rolling_outline_revision", 22, "滚动修正后续大纲", "22_rolling_outline_revision_prompt.md", "serial_maintenance", "chapter_planner"),
    PromptCatalogEntry("context_compression", 23, "上下文压缩", "23_context_compression_prompt.md", "serial_maintenance", "canon_curator"),
    PromptCatalogEntry("style_calibration", 24, "风格校准", "24_style_calibration_prompt.md", "serial_maintenance", "style_unifier"),
    PromptCatalogEntry("subplot_design", 25, "支线设计", "25_subplot_design_prompt.md", "special_design", "chapter_planner"),
    PromptCatalogEntry("antagonist_design", 26, "反派设计", "26_antagonist_design_prompt.md", "special_design", "chief_architect"),
    PromptCatalogEntry("climax_design", 27, "高潮设计", "27_climax_design_prompt.md", "special_design", "chapter_planner"),
    PromptCatalogEntry("next_chapter_state_change", 28, "下一章改变什么", "28_next_chapter_state_change_prompt.md", "chapter_production", "chapter_planner"),
    PromptCatalogEntry("recommended_workflow_order", 29, "最推荐的实际使用顺序", "29_recommended_workflow_order.md", "serial_maintenance", "chief_architect"),
    PromptCatalogEntry("minimal_work_template", 30, "极简工作模板", "30_minimal_work_template.md", "chapter_production", "chapter_planner"),
    PromptCatalogEntry("single_round_generation_combo", 31, "单轮生成组合提示词", "31_single_round_generation_combo_prompt.md", "chapter_production", "integrator"),
    PromptCatalogEntry("creation_worldview_draw", 32, "创作 Star 世界观抽卡", "32_creation_worldview_draw_prompt.md", "creation_star", "creation_star"),
    PromptCatalogEntry("creation_protagonist_draw", 33, "创作 Star 主角人设抽卡", "33_creation_protagonist_draw_prompt.md", "creation_star", "creation_star"),
    PromptCatalogEntry("creation_title_packaging", 34, "创作 Star 书名与包装抽卡", "34_creation_title_packaging_prompt.md", "creation_star", "creation_star"),
)

LONG_NOVEL_PROMPT_IDS: tuple[str, ...] = tuple(entry.prompt_id for entry in LONG_NOVEL_PROMPT_ENTRIES)

_ENTRY_BY_ID = {entry.prompt_id: entry for entry in LONG_NOVEL_PROMPT_ENTRIES}

PROMPT_WORKFLOWS: tuple[PromptWorkflowDefinition, ...] = (
    PromptWorkflowDefinition(
        key="creation_star",
        label="创作 Star 抽卡",
        description="世界观、主角、书名与包装抽卡只生成候选卡片与后续种子；核心矛盾和小说宪法在用户选定后进入后续流程。",
        prompt_ids=("creation_worldview_draw", "creation_protagonist_draw", "creation_title_packaging"),
    ),
    PromptWorkflowDefinition(
        key="conception",
        label="立项与小说宪法",
        description="从核心矛盾系统生成小说宪法，并进行压力测试。",
        prompt_ids=("general_control", "core_conflict_system", "novel_constitution", "constitution_stress_test"),
    ),
    PromptWorkflowDefinition(
        key="chapter_production",
        label="单章生产闭环",
        description="从章节卡、场景细纲、正文、自检、改写到章后叙事账本更新。",
        prompt_ids=(
            "chapter_card",
            "scene_outline",
            "draft_generation",
            "draft_self_check",
            "draft_rewrite",
            "narrative_ledger_update",
            "next_chapter_state_change",
            "minimal_work_template",
            "single_round_generation_combo",
        ),
    ),
    PromptWorkflowDefinition(
        key="serial_maintenance",
        label="连载维护与体检",
        description="维护伏笔、人物弧线、关系网、世界规则、时间线、结构健康和上下文压缩。",
        prompt_ids=(
            "foreshadowing_management",
            "character_arc_management",
            "relationship_network_management",
            "world_rules_management",
            "timeline_check",
            "branch_plot_generation",
            "structure_editor_review",
            "ten_chapter_health_check",
            "rolling_outline_revision",
            "context_compression",
            "style_calibration",
            "recommended_workflow_order",
        ),
    ),
    PromptWorkflowDefinition(
        key="special_design",
        label="专项增强",
        description="为支线、反派和高潮设计提供专项结构提示词。",
        prompt_ids=("subplot_design", "antagonist_design", "climax_design"),
    ),
)

PROMPT_LIFECYCLE_WORKFLOWS: tuple[PromptLifecycleWorkflowDefinition, ...] = (
    PromptLifecycleWorkflowDefinition(
        key="story_foundation_lifecycle",
        label="立项与宪法",
        description="从创作 Star 已确认种子生成核心矛盾、小说宪法、压力测试和正典候选。",
        prompt_ids=("core_conflict_system", "novel_constitution", "constitution_stress_test"),
        edges=(
            {"source": "core_conflict_system", "target": "novel_constitution", "label": "生成小说宪法"},
            {"source": "novel_constitution", "target": "constitution_stress_test", "label": "压力测试"},
            {"source": "constitution_stress_test", "target": "core_conflict_system", "label": "needs_revision / blocked"},
        ),
        tags=("foundation", "quality_gate"),
    ),
    PromptLifecycleWorkflowDefinition(
        key="chapter_closed_loop_lifecycle",
        label="单章生产闭环",
        description="从下一章状态变化到章节卡、场景细纲、正文、自检、改写和叙事账本更新。",
        prompt_ids=(
            "next_chapter_state_change",
            "chapter_card",
            "scene_outline",
            "draft_generation",
            "draft_self_check",
            "draft_rewrite",
            "narrative_ledger_update",
        ),
        edges=(
            {"source": "next_chapter_state_change", "target": "chapter_card", "label": "确定本章改变什么"},
            {"source": "chapter_card", "target": "scene_outline", "label": "拆成场景细纲"},
            {"source": "scene_outline", "target": "draft_generation", "label": "生成正文"},
            {"source": "draft_generation", "target": "draft_self_check", "label": "正文自检"},
            {"source": "draft_self_check", "target": "draft_rewrite", "label": "needs_revision / blocked"},
            {"source": "draft_self_check", "target": "narrative_ledger_update", "label": "passed"},
            {"source": "draft_rewrite", "target": "narrative_ledger_update", "label": "更新叙事账本"},
        ),
        trigger_policy="on_chapter_generation",
        tags=("chapter", "quality_gate", "revision_loop"),
    ),
    PromptLifecycleWorkflowDefinition(
        key="serial_maintenance_lifecycle",
        label="连载维护与体检",
        description="并行检查伏笔、人物、关系、世界规则、时间线、风格，并汇总结构体检结果。",
        prompt_ids=(
            "foreshadowing_management",
            "character_arc_management",
            "relationship_network_management",
            "world_rules_management",
            "timeline_check",
            "style_calibration",
            "structure_editor_review",
            "ten_chapter_health_check",
            "rolling_outline_revision",
        ),
        edges=(
            {"source": "foreshadowing_management", "target": "structure_editor_review", "label": "parallel_check"},
            {"source": "character_arc_management", "target": "structure_editor_review", "label": "parallel_check"},
            {"source": "relationship_network_management", "target": "structure_editor_review", "label": "parallel_check"},
            {"source": "world_rules_management", "target": "ten_chapter_health_check", "label": "parallel_check"},
            {"source": "timeline_check", "target": "ten_chapter_health_check", "label": "parallel_check"},
            {"source": "style_calibration", "target": "ten_chapter_health_check", "label": "parallel_check"},
            {"source": "structure_editor_review", "target": "rolling_outline_revision", "label": "revise_outline"},
            {"source": "ten_chapter_health_check", "target": "rolling_outline_revision", "label": "revise_outline"},
        ),
        trigger_policy="every_10_chapters_or_manual",
        tags=("maintenance", "parallel_check"),
    ),
    PromptLifecycleWorkflowDefinition(
        key="special_booster_lifecycle",
        label="专项增强",
        description="按需调用分支、支线、反派、高潮、工作流推荐和快捷写作模式。",
        prompt_ids=(
            "branch_plot_generation",
            "subplot_design",
            "antagonist_design",
            "climax_design",
            "recommended_workflow_order",
            "minimal_work_template",
            "single_round_generation_combo",
        ),
        edges=(
            {"source": "branch_plot_generation", "target": "subplot_design", "label": "扩展支线"},
            {"source": "subplot_design", "target": "antagonist_design", "label": "强化对立压力"},
            {"source": "antagonist_design", "target": "climax_design", "label": "强化高潮"},
            {"source": "recommended_workflow_order", "target": "minimal_work_template", "label": "shortcut"},
            {"source": "minimal_work_template", "target": "single_round_generation_combo", "label": "shortcut"},
        ),
        trigger_policy="manual",
        tags=("booster", "shortcut"),
    ),
)


def list_long_novel_prompt_entries() -> list[PromptCatalogEntry]:
    return list(LONG_NOVEL_PROMPT_ENTRIES)


def get_prompt_entry(prompt_id: str) -> PromptCatalogEntry:
    return _ENTRY_BY_ID[prompt_id]


@lru_cache(maxsize=64)
def load_catalog_prompt(prompt_id: str) -> str:
    entry = get_prompt_entry(prompt_id)
    return (PROMPT_DIR / entry.filename).read_text(encoding="utf-8")


def list_prompt_workflows() -> list[dict[str, object]]:
    workflows: list[dict[str, object]] = []
    for workflow in PROMPT_WORKFLOWS:
        entries = [get_prompt_entry(prompt_id) for prompt_id in workflow.prompt_ids]
        agents = list(dict.fromkeys(entry.default_agent for entry in entries))
        workflows.append(
            {
                "id": workflow.key,
                "key": workflow.key,
                "label": workflow.label,
                "description": workflow.description,
                "workflow_kind": "prompt_library",
                "trigger_policy": "manual",
                "tags": ["prompt_library"],
                "prompt_ids": list(workflow.prompt_ids),
                "prompts": [_prompt_summary(entry) for entry in entries],
                "agents": agents,
                "nodes": [
                    _prompt_workflow_node(entry, position)
                    for position, entry in enumerate(entries)
                ],
                "edges": [
                    {"source": left.prompt_id, "target": right.prompt_id, "label": "下一阶段"}
                    for left, right in zip(entries, entries[1:])
                ],
            }
        )
    return workflows


def list_prompt_lifecycle_workflows() -> list[dict[str, object]]:
    workflows: list[dict[str, object]] = []
    for workflow in PROMPT_LIFECYCLE_WORKFLOWS:
        entries = [get_prompt_entry(prompt_id) for prompt_id in workflow.prompt_ids]
        agents = list(dict.fromkeys(entry.default_agent for entry in entries))
        workflows.append(
            {
                "id": workflow.key,
                "key": workflow.key,
                "label": workflow.label,
                "description": workflow.description,
                "workflow_kind": "prompt_lifecycle",
                "trigger_policy": workflow.trigger_policy,
                "tags": list(workflow.tags),
                "prompt_ids": list(workflow.prompt_ids),
                "prompts": [_prompt_summary(entry) for entry in entries],
                "agents": agents,
                "nodes": [
                    _prompt_workflow_node(
                        entry,
                        position,
                        workflow_tags=workflow.tags,
                    )
                    for position, entry in enumerate(entries)
                ],
                "edges": [dict(edge) for edge in workflow.edges],
            }
        )
    return workflows


def _prompt_summary(entry: PromptCatalogEntry) -> dict[str, object]:
    return {
        "id": entry.prompt_id,
        "index": entry.index,
        "title": entry.title,
        "filename": entry.filename,
        "default_agent": entry.default_agent,
    }


def _prompt_workflow_node(
    entry: PromptCatalogEntry,
    position: int,
    workflow_tags: tuple[str, ...] = (),
) -> dict[str, object]:
    contract = get_prompt_node_contract(entry.prompt_id)
    node_tags = list(workflow_tags)
    if entry.prompt_id in {"minimal_work_template", "single_round_generation_combo"}:
        node_tags.append("shortcut")
    return {
        "id": entry.prompt_id,
        "label": entry.title,
        "type": "prompt",
        "node_subtype": contract.node_subtype,
        "agent_name": entry.default_agent,
        "description": contract.description,
        "inputs": list(contract.required_inputs),
        "outputs": list(contract.produces),
        "required_inputs": list(contract.required_inputs),
        "optional_inputs": list(contract.optional_inputs),
        "produces": list(contract.produces),
        "input_schema": contract.input_json_schema(),
        "output_schema": contract.output_json_schema(),
        "editable": True,
        "layer": position + 1,
        "prompt_id": entry.prompt_id,
        "prompt_filename": entry.filename,
        "tags": list(dict.fromkeys(node_tags)),
    }
