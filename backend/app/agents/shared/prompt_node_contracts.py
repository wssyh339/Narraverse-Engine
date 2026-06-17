from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from app.schemas import prompt_nodes as schemas


@dataclass(frozen=True)
class PromptNodeContract:
    prompt_id: str
    node_subtype: str
    required_inputs: tuple[str, ...]
    optional_inputs: tuple[str, ...]
    produces: tuple[str, ...]
    input_schema: type[BaseModel]
    output_schema: type[BaseModel]
    description: str

    def input_json_schema(self) -> dict[str, Any]:
        return self.input_schema.model_json_schema()

    def output_json_schema(self) -> dict[str, Any]:
        return self.output_schema.model_json_schema()


def _contract(
    prompt_id: str,
    required_inputs: tuple[str, ...],
    produces: tuple[str, ...],
    input_schema: type[BaseModel],
    output_schema: type[BaseModel],
    description: str,
    optional_inputs: tuple[str, ...] = (),
) -> PromptNodeContract:
    return PromptNodeContract(
        prompt_id=prompt_id,
        node_subtype="prompt_agent",
        required_inputs=required_inputs,
        optional_inputs=optional_inputs,
        produces=produces,
        input_schema=input_schema,
        output_schema=output_schema,
        description=description,
    )


PROMPT_NODE_CONTRACTS: dict[str, PromptNodeContract] = {
    "general_control": _contract(
        "general_control",
        ("task", "context"),
        ("normalized_task", "control_rules_applied"),
        schemas.GeneralControlInput,
        schemas.GeneralControlOutput,
        "总控节点：结合上下文、任务和期望输出 schema，约束后续提示词任务的执行边界。",
        ("expected_output_schema",),
    ),
    "creation_worldview_draw": _contract(
        "creation_worldview_draw",
        ("basic_info",),
        ("worldview_candidates", "conflict_engine_seed"),
        schemas.CreationWorldviewDrawInput,
        schemas.CreationWorldviewDrawOutput,
        "创作 Star 世界观抽卡节点：只生成候选世界观和冲突发动机种子，不生成核心矛盾系统或小说宪法。",
        ("manual_input", "previous_cards_summary", "count"),
    ),
    "creation_protagonist_draw": _contract(
        "creation_protagonist_draw",
        ("basic_info", "selected_worldview"),
        ("protagonist_candidates", "conflict_seed"),
        schemas.CreationProtagonistDrawInput,
        schemas.CreationProtagonistDrawOutput,
        "创作 Star 主角人设抽卡节点：只生成候选主角和主角侧 conflict_seed，不生成核心矛盾系统或小说宪法。",
        ("manual_input", "previous_cards_summary", "count"),
    ),
    "creation_title_packaging": _contract(
        "creation_title_packaging",
        ("basic_info", "selected_worldview", "selected_protagonist"),
        ("title_candidates", "market_position"),
        schemas.CreationTitlePackagingInput,
        schemas.CreationTitlePackagingOutput,
        "创作 Star 书名与包装抽卡节点：只生成标题、广告句、核心卖点、读者期待、平台风格和风险提示。",
        ("manual_input", "count"),
    ),
    "core_conflict_system": _contract(
        "core_conflict_system",
        ("project_seed", "canon_context", "market_position"),
        ("core_conflict_system",),
        schemas.CoreConflictSystemInput,
        schemas.CoreConflictSystemOutput,
        "从立项种子生成多个核心矛盾引擎，并推荐最适合长篇展开的方案。",
    ),
    "novel_constitution": _contract(
        "novel_constitution",
        ("project_seed", "core_conflict_system", "canon_context"),
        ("novel_constitution",),
        schemas.NovelConstitutionInput,
        schemas.NovelConstitutionOutput,
        "把已确认种子与核心矛盾收敛为小说宪法、不可破坏约束和候选正典。",
    ),
    "constitution_stress_test": _contract(
        "constitution_stress_test",
        ("novel_constitution", "core_conflict_system", "canon_context"),
        ("constitution_review",),
        schemas.ConstitutionStressTestInput,
        schemas.ConstitutionStressTestOutput,
        "以编辑视角压力测试小说宪法，给出 passed/needs_revision/blocked 等质量门状态。",
    ),
    "macro_outline": _contract(
        "macro_outline",
        ("novel_constitution", "core_conflict_system", "target_length", "canon_context"),
        ("macro_outline",),
        schemas.MacroOutlineInput,
        schemas.MacroOutlineOutput,
        "生成全书 5-8 阶段宏观大纲、压力递进曲线和未解决问题。",
    ),
    "ending_backcast": _contract(
        "ending_backcast",
        ("novel_constitution", "macro_outline", "desired_ending"),
        ("ending_backcast",),
        schemas.EndingBackcastInput,
        schemas.EndingBackcastOutput,
        "从结局命题反推必然因果链、前文铺垫和结局风险。",
    ),
    "volume_outline": _contract(
        "volume_outline",
        ("novel_constitution", "macro_outline", "ending_backcast", "volume_index"),
        ("volume_outline",),
        schemas.VolumeOutlineInput,
        schemas.VolumeOutlineOutput,
        "生成当前分卷标题、读者承诺、单元结构和出入卷状态。",
    ),
    "rolling_chapter_outline": _contract(
        "rolling_chapter_outline",
        ("novel_constitution", "volume_outline", "narrative_ledger", "completed_chapters"),
        ("rolling_chapter_outline",),
        schemas.RollingChapterOutlineInput,
        schemas.RollingChapterOutlineOutput,
        "基于当前卷和叙事账本生成未来滚动章纲。",
    ),
    "chapter_card": _contract(
        "chapter_card",
        (
            "novel_constitution",
            "volume_outline",
            "rolling_chapter_outline",
            "narrative_ledger",
            "previous_chapter_summary",
            "user_instruction",
        ),
        ("chapter_card",),
        schemas.ChapterCardInput,
        schemas.ChapterCardOutput,
        "生成单章章节卡，明确本章功能、冲突、转折、钩子和正典触点。",
    ),
    "scene_outline": _contract(
        "scene_outline",
        ("novel_constitution", "chapter_card", "narrative_ledger", "canon_context"),
        ("scene_outline",),
        schemas.SceneOutlineInput,
        schemas.SceneOutlineOutput,
        "把章节卡拆成场景细纲，并标注连续性和节奏注意事项。",
    ),
    "draft_generation": _contract(
        "draft_generation",
        ("novel_constitution", "chapter_card", "scene_outline", "narrative_ledger", "style_profile", "canon_context"),
        ("integrated_draft",),
        schemas.DraftGenerationInput,
        schemas.DraftGenerationOutput,
        "根据章节卡、场景细纲和正典上下文生成章节正文草稿。",
    ),
    "draft_self_check": _contract(
        "draft_self_check",
        ("integrated_draft", "chapter_card", "scene_outline", "novel_constitution", "narrative_ledger"),
        ("draft_self_check",),
        schemas.DraftSelfCheckInput,
        schemas.DraftSelfCheckOutput,
        "对正文进行逻辑、结构、节奏和承诺兑现自检。",
    ),
    "draft_rewrite": _contract(
        "draft_rewrite",
        ("integrated_draft", "draft_self_check", "chapter_card", "user_instruction", "style_profile"),
        ("rewritten_draft",),
        schemas.DraftRewriteInput,
        schemas.DraftRewriteOutput,
        "根据自检报告和用户要求改写正文，记录已执行和未解决问题。",
    ),
    "narrative_ledger_update": _contract(
        "narrative_ledger_update",
        ("final_chapter_text", "chapter_card", "narrative_ledger", "canon_context"),
        ("narrative_ledger", "candidate_canon_updates"),
        schemas.NarrativeLedgerUpdateInput,
        schemas.NarrativeLedgerUpdateOutput,
        "章后更新叙事账本，并产出候选正典和连续性问题。",
    ),
    "foreshadowing_management": _contract(
        "foreshadowing_management",
        ("narrative_ledger", "completed_chapters", "future_outline"),
        ("foreshadowing_updates",),
        schemas.ForeshadowingManagementInput,
        schemas.ForeshadowingManagementOutput,
        "管理伏笔新增、强化、回收、废弃和后续回收计划。",
    ),
    "character_arc_management": _contract(
        "character_arc_management",
        ("characters", "narrative_ledger", "completed_chapters"),
        ("character_arc_updates",),
        schemas.CharacterArcManagementInput,
        schemas.CharacterArcManagementOutput,
        "检查人物弧线推进、行为矛盾和下一步人物变化建议。",
    ),
    "relationship_network_management": _contract(
        "relationship_network_management",
        ("characters", "relationship_graph", "narrative_ledger"),
        ("relationship_network_updates",),
        schemas.RelationshipNetworkManagementInput,
        schemas.RelationshipNetworkManagementOutput,
        "维护人物关系网，标注关系变化、误解、依赖和新张力机会。",
    ),
    "world_rules_management": _contract(
        "world_rules_management",
        ("world_facts", "novel_constitution", "narrative_ledger"),
        ("world_rule_updates",),
        schemas.WorldRulesManagementInput,
        schemas.WorldRulesManagementOutput,
        "维护世界规则一致性，输出候选规则更新和矛盾问题。",
    ),
    "timeline_check": _contract(
        "timeline_check",
        ("timeline", "completed_chapters", "narrative_ledger"),
        ("timeline_check_report",),
        schemas.TimelineCheckInput,
        schemas.TimelineCheckOutput,
        "校验时间线、年龄、距离和因果顺序，给出修复建议。",
    ),
    "branch_plot_generation": _contract(
        "branch_plot_generation",
        ("novel_constitution", "current_story_state", "open_questions"),
        ("branch_plot_options",),
        schemas.BranchPlotGenerationInput,
        schemas.BranchPlotGenerationOutput,
        "生成多分支剧情候选，并标注推荐分支和合并机会。",
    ),
    "structure_editor_review": _contract(
        "structure_editor_review",
        ("macro_outline", "rolling_chapter_outline", "completed_chapters", "novel_constitution"),
        ("structure_review",),
        schemas.StructureEditorReviewInput,
        schemas.StructureEditorReviewOutput,
        "从结构编辑视角审查全书、章纲和已完成章节。",
    ),
    "ten_chapter_health_check": _contract(
        "ten_chapter_health_check",
        ("recent_chapters", "narrative_ledger", "novel_constitution"),
        ("health_check_report",),
        schemas.TenChapterHealthCheckInput,
        schemas.TenChapterHealthCheckOutput,
        "每十章检查结构健康、节奏、人物弧线和伏笔兑现。",
    ),
    "rolling_outline_revision": _contract(
        "rolling_outline_revision",
        ("rolling_chapter_outline", "health_check_report", "narrative_ledger", "user_instruction"),
        ("revised_rolling_chapter_outline",),
        schemas.RollingOutlineRevisionInput,
        schemas.RollingOutlineRevisionOutput,
        "根据体检报告和用户要求修订后续滚动章纲。",
    ),
    "context_compression": _contract(
        "context_compression",
        ("canon_context", "completed_chapters", "narrative_ledger", "compression_goal"),
        ("context_summary",),
        schemas.ContextCompressionInput,
        schemas.ContextCompressionOutput,
        "压缩长上下文，保留必须信息并记录延后加载内容。",
    ),
    "style_calibration": _contract(
        "style_calibration",
        ("style_samples", "target_reader", "genre", "current_draft"),
        ("style_profile",),
        schemas.StyleCalibrationInput,
        schemas.StyleCalibrationOutput,
        "从样本中抽取风格规则、禁忌和可复用改写示例。",
    ),
    "subplot_design": _contract(
        "subplot_design",
        ("novel_constitution", "main_plot_state", "characters"),
        ("subplot_options",),
        schemas.SubplotDesignInput,
        schemas.SubplotDesignOutput,
        "设计可与主线交汇的支线候选，避免支线游离。",
    ),
    "antagonist_design": _contract(
        "antagonist_design",
        ("novel_constitution", "core_conflict_system", "protagonist_profile"),
        ("antagonist_profile",),
        schemas.AntagonistDesignInput,
        schemas.AntagonistDesignOutput,
        "设计对立力量的自洽逻辑、施压方式和风险。",
    ),
    "climax_design": _contract(
        "climax_design",
        ("novel_constitution", "macro_outline", "crisis_candidates", "foreshadowing_list"),
        ("climax_design",),
        schemas.ClimaxDesignInput,
        schemas.ClimaxDesignOutput,
        "设计高潮候选，检查主题、人物弧光、伏笔和机械降神风险。",
    ),
    "next_chapter_state_change": _contract(
        "next_chapter_state_change",
        ("current_story_state", "rolling_chapter_outline", "narrative_ledger"),
        ("next_chapter_state_change_plan",),
        schemas.NextChapterStateChangeInput,
        schemas.NextChapterStateChangeOutput,
        "先定义下一章必须改变的状态，防止章节原地踏步。",
    ),
    "recommended_workflow_order": _contract(
        "recommended_workflow_order",
        ("project_stage", "available_artifacts", "user_goal"),
        ("recommended_workflow_order",),
        schemas.RecommendedWorkflowOrderInput,
        schemas.RecommendedWorkflowOrderOutput,
        "根据当前项目阶段和已有产物推荐最合理的提示词工作顺序。",
    ),
    "minimal_work_template": _contract(
        "minimal_work_template",
        ("novel_constitution", "current_chapter_goal", "narrative_ledger"),
        ("minimal_chapter_loop",),
        schemas.MinimalWorkTemplateInput,
        schemas.MinimalWorkTemplateOutput,
        "提供极简章节卡、场景细纲和账本更新提醒，用于快速单章闭环。",
    ),
    "single_round_generation_combo": _contract(
        "single_round_generation_combo",
        ("novel_constitution", "current_chapter_goal", "narrative_ledger", "canon_context", "style_profile"),
        ("single_round_generation_result",),
        schemas.SingleRoundGenerationComboInput,
        schemas.SingleRoundGenerationComboOutput,
        "单轮完成章节规划、正文生成、自检和账本更新的组合节点。",
    ),
}


def get_prompt_node_contract(prompt_id: str) -> PromptNodeContract:
    return PROMPT_NODE_CONTRACTS[prompt_id]


def list_prompt_node_contracts() -> list[PromptNodeContract]:
    return list(PROMPT_NODE_CONTRACTS.values())
