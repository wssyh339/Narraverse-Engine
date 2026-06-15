from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from app.schemas.common import APIModel


class PromptRisk(APIModel):
    level: Literal["low", "medium", "high", "blocking"] = Field(description="风险等级。")
    issue: str = Field(description="风险或问题说明。")
    mitigation: str = Field(default="", description="建议的修正或规避方式。")


class PromptRecommendation(APIModel):
    priority: Literal["low", "medium", "high"] = Field(default="medium", description="建议优先级。")
    action: str = Field(description="建议采取的具体动作。")
    reason: str = Field(default="", description="建议原因。")


class PromptIssue(APIModel):
    severity: Literal["note", "minor", "major", "blocking"] = Field(default="note", description="问题严重程度。")
    summary: str = Field(description="问题摘要。")
    evidence: str = Field(default="", description="来自设定、正文或大纲的依据。")
    suggestion: str = Field(default="", description="修正建议。")


class StoryBeat(APIModel):
    title: str = Field(description="节拍标题。")
    purpose: str = Field(description="该节拍在长篇结构中的功能。")
    conflict: str = Field(default="", description="本节拍承载的冲突。")
    state_change: str = Field(default="", description="节拍结束时改变了什么。")


class ScenePlan(APIModel):
    scene_no: int = Field(ge=1, description="场景序号。")
    location: str = Field(default="", description="场景地点。")
    pov: str = Field(default="", description="视角人物。")
    goal: str = Field(description="场景目标。")
    obstacle: str = Field(default="", description="阻力。")
    turn: str = Field(default="", description="转折。")
    exit_hook: str = Field(default="", description="场景收束钩子。")


class CanonCandidate(APIModel):
    target: Literal["project", "story_bible", "characters", "entities", "world_facts", "graph"] = Field(description="候选正典目标区。")
    content: dict[str, Any] = Field(default_factory=dict, description="候选写入内容。")
    source_prompt_id: str = Field(description="候选来源提示词。")
    confidence: float = Field(default=0.7, ge=0, le=1, description="置信度。")
    reason: str = Field(default="", description="为何建议写入正典。")


class BranchOption(APIModel):
    option_id: str = Field(description="分支选项编号。")
    title: str = Field(description="分支标题。")
    premise: str = Field(description="分支前提。")
    long_form_value: str = Field(description="长篇连载价值。")
    cost: str = Field(default="", description="该分支带来的代价。")
    risks: list[PromptRisk] = Field(default_factory=list, description="分支风险。")


class GeneralControlInput(APIModel):
    task: str = Field(description="当前要执行的创作任务。")
    context: dict[str, Any] = Field(default_factory=dict, description="本轮可用上下文。")
    expected_output_schema: dict[str, Any] | None = Field(default=None, description="调用方期望的输出 schema。")


class GeneralControlOutput(APIModel):
    normalized_task: str = Field(description="整理后的任务目标。")
    control_rules_applied: list[str] = Field(default_factory=list, description="本轮必须遵守的总控规则。")
    missing_context: list[str] = Field(default_factory=list, description="缺失但会影响结果的上下文。")
    recommendations: list[PromptRecommendation] = Field(default_factory=list, description="下一步建议。")


class CreationWorldviewDrawInput(APIModel):
    basic_info: dict[str, Any] = Field(description="创作 Star 基本信息，包括频道、类型、标签、读者、风格和初始想法。")
    manual_input: str = Field(default="", description="作者本轮额外补充。")
    previous_cards_summary: str = Field(default="", description="上一批世界观候选摘要，用于刷新去重。")
    count: int = Field(default=1, ge=1, description="本轮需要生成的新增世界观卡数量。")


class CreationWorldviewDrawOutput(APIModel):
    cards: list[dict[str, Any]] = Field(min_length=1, description="世界观候选卡，只包含世界规则、主角入口和冲突发动机种子。")
    generation_notes: list[str] = Field(default_factory=list, description="本轮差异化或风险说明。")


class CreationProtagonistDrawInput(APIModel):
    basic_info: dict[str, Any] = Field(description="创作 Star 基本信息，包括频道、类型、标签、读者、风格和初始想法。")
    selected_worldview: dict[str, Any] = Field(description="作者已选世界观候选卡。")
    manual_input: str = Field(default="", description="作者本轮额外补充。")
    previous_cards_summary: str = Field(default="", description="上一批主角候选摘要，用于刷新去重。")
    count: int = Field(default=1, ge=1, description="本轮需要生成的新增主角卡数量。")


class CreationProtagonistDrawOutput(APIModel):
    cards: list[dict[str, Any]] = Field(min_length=1, description="主角候选卡，只包含人物身份、欲望、能力代价、关系钩子和主角侧 conflict_seed。")
    generation_notes: list[str] = Field(default_factory=list, description="本轮差异化或风险说明。")


class CoreConflictSystemInput(APIModel):
    project_seed: dict[str, Any] = Field(description="创作 Star 已确认的立项种子。")
    canon_context: dict[str, Any] = Field(default_factory=dict, description="当前正典上下文。")
    market_position: dict[str, Any] = Field(default_factory=dict, description="频道、类型、卖点与读者预期。")


class CoreConflictSystemOutput(APIModel):
    conflict_engines: list[dict[str, Any]] = Field(min_length=1, description="候选核心矛盾引擎。")
    recommended_engine: str = Field(description="推荐采用的核心矛盾引擎编号或标题。")
    theme_pressure: str = Field(description="核心矛盾承载的主题压力。")
    risks: list[PromptRisk] = Field(default_factory=list, description="核心矛盾风险。")


class NovelConstitutionInput(APIModel):
    project_seed: dict[str, Any] = Field(description="已确认的立项种子。")
    core_conflict_system: dict[str, Any] = Field(description="核心矛盾系统。")
    canon_context: dict[str, Any] = Field(default_factory=dict, description="正典上下文。")


class NovelConstitutionOutput(APIModel):
    constitution: dict[str, Any] = Field(description="小说宪法主体。")
    non_negotiables: list[str] = Field(default_factory=list, description="不可破坏的创作约束。")
    open_questions: list[str] = Field(default_factory=list, description="尚未解决但可继续推演的问题。")
    canon_candidates: list[CanonCandidate] = Field(default_factory=list, description="可进入正典预览的候选。")


class ConstitutionStressTestInput(APIModel):
    novel_constitution: dict[str, Any] = Field(description="待测试的小说宪法。")
    core_conflict_system: dict[str, Any] = Field(description="核心矛盾系统。")
    canon_context: dict[str, Any] = Field(default_factory=dict, description="正典上下文。")


class ConstitutionStressTestOutput(APIModel):
    status: Literal["passed", "passed_with_notes", "needs_revision", "blocked"] = Field(description="压力测试结论。")
    issues: list[PromptIssue] = Field(default_factory=list, description="结构、逻辑或市场风险。")
    revision_plan: list[PromptRecommendation] = Field(default_factory=list, description="修订计划。")


class MacroOutlineInput(APIModel):
    novel_constitution: dict[str, Any] = Field(description="小说宪法。")
    core_conflict_system: dict[str, Any] = Field(description="核心矛盾系统。")
    target_length: str = Field(default="", description="目标篇幅或卷数。")
    canon_context: dict[str, Any] = Field(default_factory=dict, description="正典上下文。")


class MacroOutlineOutput(APIModel):
    phases: list[StoryBeat] = Field(min_length=1, description="5-8 个全书阶段。")
    volume_strategy: str = Field(default="", description="分卷组织策略。")
    escalation_curve: list[str] = Field(default_factory=list, description="压力递进曲线。")
    unresolved_questions: list[str] = Field(default_factory=list, description="未解决问题。")


class EndingBackcastInput(APIModel):
    novel_constitution: dict[str, Any] = Field(description="小说宪法。")
    macro_outline: dict[str, Any] = Field(description="宏观大纲。")
    desired_ending: str = Field(default="", description="用户或系统期望的结局方向。")


class EndingBackcastOutput(APIModel):
    ending_claim: str = Field(description="结局命题。")
    inevitable_chain: list[StoryBeat] = Field(default_factory=list, description="从结局反推的必然因果链。")
    required_setups: list[str] = Field(default_factory=list, description="前文必须埋下的设置。")
    risks: list[PromptRisk] = Field(default_factory=list, description="结局反推风险。")


class VolumeOutlineInput(APIModel):
    novel_constitution: dict[str, Any] = Field(description="小说宪法。")
    macro_outline: dict[str, Any] = Field(description="宏观大纲。")
    ending_backcast: dict[str, Any] = Field(default_factory=dict, description="结局反推路径。")
    volume_index: int = Field(default=1, ge=1, description="当前分卷序号。")


class VolumeOutlineOutput(APIModel):
    volume_title: str = Field(description="分卷标题。")
    volume_promise: str = Field(description="本卷读者承诺。")
    units: list[StoryBeat] = Field(min_length=1, description="5-8 个分卷单元。")
    entry_state: str = Field(default="", description="本卷开始状态。")
    exit_state: str = Field(default="", description="本卷结束状态。")


class RollingChapterOutlineInput(APIModel):
    novel_constitution: dict[str, Any] = Field(description="小说宪法。")
    volume_outline: dict[str, Any] = Field(description="当前分卷大纲。")
    narrative_ledger: dict[str, Any] = Field(default_factory=dict, description="叙事账本。")
    completed_chapters: list[dict[str, Any]] = Field(default_factory=list, description="已完成章节摘要。")


class RollingChapterOutlineOutput(APIModel):
    chapters: list[dict[str, Any]] = Field(min_length=1, description="滚动章纲，通常覆盖未来 10-15 章。")
    dependency_notes: list[str] = Field(default_factory=list, description="章节依赖与伏笔说明。")
    risks: list[PromptRisk] = Field(default_factory=list, description="滚动章纲风险。")


class ChapterCardInput(APIModel):
    novel_constitution: dict[str, Any] = Field(description="小说宪法。")
    volume_outline: dict[str, Any] = Field(description="当前分卷大纲。")
    rolling_chapter_outline: list[dict[str, Any]] = Field(description="滚动章纲。")
    narrative_ledger: dict[str, Any] = Field(description="叙事账本。")
    previous_chapter_summary: str = Field(description="上一章摘要。")
    user_instruction: str = Field(default="", description="用户对本章的额外要求。")


class ChapterCardOutput(APIModel):
    chapter_title: str = Field(description="章节标题。")
    core_function: str = Field(description="本章核心功能：这一章必须在长篇结构中完成什么。")
    pov: str = Field(default="", description="视角人物。")
    conflict: str = Field(description="本章主要冲突。")
    turn_point: str = Field(default="", description="本章转折点。")
    hook: str = Field(default="", description="章末钩子。")
    canon_touches: list[str] = Field(default_factory=list, description="本章触及或可能更新的正典点。")


class SceneOutlineInput(APIModel):
    novel_constitution: dict[str, Any] = Field(description="小说宪法。")
    chapter_card: dict[str, Any] = Field(description="章节卡。")
    narrative_ledger: dict[str, Any] = Field(description="叙事账本。")
    canon_context: dict[str, Any] = Field(default_factory=dict, description="正典上下文。")


class SceneOutlineOutput(APIModel):
    scenes: list[ScenePlan] = Field(min_length=1, description="场景细纲。")
    continuity_notes: list[str] = Field(default_factory=list, description="连续性注意事项。")
    pacing_notes: list[str] = Field(default_factory=list, description="节奏注意事项。")


class DraftGenerationInput(APIModel):
    novel_constitution: dict[str, Any] = Field(description="小说宪法。")
    chapter_card: dict[str, Any] = Field(description="章节卡。")
    scene_outline: dict[str, Any] = Field(description="场景细纲。")
    narrative_ledger: dict[str, Any] = Field(description="叙事账本。")
    style_profile: dict[str, Any] = Field(default_factory=dict, description="风格校准档案。")
    canon_context: dict[str, Any] = Field(default_factory=dict, description="正典上下文。")


class DraftGenerationOutput(APIModel):
    integrated_draft: str = Field(description="生成的章节正文草稿。")
    chapter_summary: str = Field(default="", description="本章摘要。")
    state_changes: list[str] = Field(default_factory=list, description="本章改变了哪些人物、关系、世界或情节状态。")
    candidate_canon_updates: list[CanonCandidate] = Field(default_factory=list, description="候选正典更新。")


class DraftSelfCheckInput(APIModel):
    integrated_draft: str = Field(description="待自检正文。")
    chapter_card: dict[str, Any] = Field(description="章节卡。")
    scene_outline: dict[str, Any] = Field(description="场景细纲。")
    novel_constitution: dict[str, Any] = Field(description="小说宪法。")
    narrative_ledger: dict[str, Any] = Field(default_factory=dict, description="叙事账本。")


class DraftSelfCheckOutput(APIModel):
    pass_level: Literal["passed", "minor_revision", "major_revision", "blocked"] = Field(description="自检结论。")
    issues: list[PromptIssue] = Field(default_factory=list, description="正文问题。")
    keep: list[str] = Field(default_factory=list, description="建议保留的亮点。")
    rewrite_focus: list[str] = Field(default_factory=list, description="改写重点。")


class DraftRewriteInput(APIModel):
    integrated_draft: str = Field(description="原正文。")
    draft_self_check: dict[str, Any] = Field(description="自检报告。")
    chapter_card: dict[str, Any] = Field(description="章节卡。")
    user_instruction: str = Field(default="", description="用户改写要求。")
    style_profile: dict[str, Any] = Field(default_factory=dict, description="风格校准档案。")


class DraftRewriteOutput(APIModel):
    rewritten_draft: str = Field(description="改写后的正文。")
    applied_changes: list[str] = Field(default_factory=list, description="已执行的改写项。")
    remaining_issues: list[PromptIssue] = Field(default_factory=list, description="仍需处理的问题。")


class NarrativeLedgerUpdateInput(APIModel):
    final_chapter_text: str = Field(description="本章定稿或候选定稿文本。")
    chapter_card: dict[str, Any] = Field(description="章节卡。")
    narrative_ledger: dict[str, Any] = Field(description="旧叙事账本。")
    canon_context: dict[str, Any] = Field(default_factory=dict, description="正典上下文。")


class NarrativeLedgerUpdateOutput(APIModel):
    ledger_updates: dict[str, Any] = Field(description="叙事账本更新。")
    candidate_canon_updates: list[CanonCandidate] = Field(default_factory=list, description="候选正典更新。")
    continuity_issues: list[PromptIssue] = Field(default_factory=list, description="发现的连续性问题。")


class ForeshadowingManagementInput(APIModel):
    narrative_ledger: dict[str, Any] = Field(description="叙事账本。")
    completed_chapters: list[dict[str, Any]] = Field(description="已完成章节。")
    future_outline: list[dict[str, Any]] = Field(default_factory=list, description="后续章纲。")


class ForeshadowingManagementOutput(APIModel):
    foreshadowing_updates: list[dict[str, Any]] = Field(default_factory=list, description="伏笔新增、强化、回收或废弃建议。")
    payoff_plan: list[dict[str, Any]] = Field(default_factory=list, description="伏笔回收计划。")
    risks: list[PromptRisk] = Field(default_factory=list, description="伏笔风险。")


class CharacterArcManagementInput(APIModel):
    characters: list[dict[str, Any]] = Field(description="角色卡。")
    narrative_ledger: dict[str, Any] = Field(description="叙事账本。")
    completed_chapters: list[dict[str, Any]] = Field(default_factory=list, description="已完成章节。")


class CharacterArcManagementOutput(APIModel):
    arc_updates: list[dict[str, Any]] = Field(default_factory=list, description="人物弧线更新。")
    contradictions: list[PromptIssue] = Field(default_factory=list, description="人物行为或弧线矛盾。")
    recommendations: list[PromptRecommendation] = Field(default_factory=list, description="后续推进建议。")


class RelationshipNetworkManagementInput(APIModel):
    characters: list[dict[str, Any]] = Field(description="角色卡。")
    relationship_graph: dict[str, Any] = Field(default_factory=dict, description="人物关系图谱。")
    narrative_ledger: dict[str, Any] = Field(description="叙事账本。")


class RelationshipNetworkManagementOutput(APIModel):
    relationship_changes: list[dict[str, Any]] = Field(default_factory=list, description="关系变化。")
    tension_opportunities: list[str] = Field(default_factory=list, description="可继续强化的关系张力。")
    risks: list[PromptRisk] = Field(default_factory=list, description="关系线风险。")


class WorldRulesManagementInput(APIModel):
    world_facts: list[dict[str, Any]] = Field(description="世界观事实。")
    novel_constitution: dict[str, Any] = Field(description="小说宪法。")
    narrative_ledger: dict[str, Any] = Field(default_factory=dict, description="叙事账本。")


class WorldRulesManagementOutput(APIModel):
    rule_updates: list[CanonCandidate] = Field(default_factory=list, description="世界规则候选更新。")
    contradictions: list[PromptIssue] = Field(default_factory=list, description="世界规则矛盾。")
    value_notes: list[str] = Field(default_factory=list, description="世界规则对剧情的价值说明。")


class TimelineCheckInput(APIModel):
    timeline: list[dict[str, Any]] = Field(description="当前时间线。")
    completed_chapters: list[dict[str, Any]] = Field(description="已完成章节。")
    narrative_ledger: dict[str, Any] = Field(default_factory=dict, description="叙事账本。")


class TimelineCheckOutput(APIModel):
    timeline_updates: list[dict[str, Any]] = Field(default_factory=list, description="时间线更新。")
    issues: list[PromptIssue] = Field(default_factory=list, description="时间顺序、年龄、距离或因果问题。")
    repair_suggestions: list[PromptRecommendation] = Field(default_factory=list, description="修复建议。")


class BranchPlotGenerationInput(APIModel):
    novel_constitution: dict[str, Any] = Field(description="小说宪法。")
    current_story_state: dict[str, Any] = Field(description="当前故事状态。")
    open_questions: list[str] = Field(default_factory=list, description="待探索问题。")


class BranchPlotGenerationOutput(APIModel):
    options: list[BranchOption] = Field(min_length=1, description="分支剧情候选，通常为 A-E。")
    recommended_options: list[str] = Field(default_factory=list, description="推荐继续发展的分支编号。")
    merge_opportunities: list[str] = Field(default_factory=list, description="可合并分支。")


class StructureEditorReviewInput(APIModel):
    macro_outline: dict[str, Any] = Field(default_factory=dict, description="宏观大纲。")
    rolling_chapter_outline: list[dict[str, Any]] = Field(default_factory=list, description="滚动章纲。")
    completed_chapters: list[dict[str, Any]] = Field(default_factory=list, description="已完成章节。")
    novel_constitution: dict[str, Any] = Field(description="小说宪法。")


class StructureEditorReviewOutput(APIModel):
    structure_status: Literal["healthy", "watch", "needs_revision", "blocked"] = Field(description="结构审查结论。")
    issues: list[PromptIssue] = Field(default_factory=list, description="结构问题。")
    recommendations: list[PromptRecommendation] = Field(default_factory=list, description="修订建议。")


class TenChapterHealthCheckInput(APIModel):
    recent_chapters: list[dict[str, Any]] = Field(description="最近十章或一个检查窗口。")
    narrative_ledger: dict[str, Any] = Field(description="叙事账本。")
    novel_constitution: dict[str, Any] = Field(description="小说宪法。")


class TenChapterHealthCheckOutput(APIModel):
    health_score: int = Field(ge=0, le=100, description="结构健康分。")
    strengths: list[str] = Field(default_factory=list, description="表现良好的部分。")
    issues: list[PromptIssue] = Field(default_factory=list, description="结构、节奏、人物或伏笔问题。")
    next_window_plan: list[PromptRecommendation] = Field(default_factory=list, description="下一检查窗口建议。")


class RollingOutlineRevisionInput(APIModel):
    rolling_chapter_outline: list[dict[str, Any]] = Field(description="原滚动章纲。")
    health_check_report: dict[str, Any] = Field(description="结构体检或审查报告。")
    narrative_ledger: dict[str, Any] = Field(description="叙事账本。")
    user_instruction: str = Field(default="", description="用户修订要求。")


class RollingOutlineRevisionOutput(APIModel):
    revised_outline: list[dict[str, Any]] = Field(description="修订后的后续章纲。")
    revision_reasons: list[str] = Field(default_factory=list, description="修订原因。")
    preserved_promises: list[str] = Field(default_factory=list, description="仍保留的读者承诺。")


class ContextCompressionInput(APIModel):
    canon_context: dict[str, Any] = Field(description="原上下文包。")
    completed_chapters: list[dict[str, Any]] = Field(default_factory=list, description="已完成章节。")
    narrative_ledger: dict[str, Any] = Field(default_factory=dict, description="叙事账本。")
    compression_goal: str = Field(default="", description="压缩目标。")


class ContextCompressionOutput(APIModel):
    context_summary: str = Field(description="压缩后的上下文摘要。")
    must_keep: list[str] = Field(default_factory=list, description="必须保留的信息。")
    dropped_or_deferred: list[str] = Field(default_factory=list, description="删除或延后加载的信息。")


class StyleCalibrationInput(APIModel):
    style_samples: list[str] = Field(description="风格样本。")
    target_reader: str = Field(default="", description="目标读者。")
    genre: str = Field(default="", description="类型。")
    current_draft: str = Field(default="", description="可选当前正文样本。")


class StyleCalibrationOutput(APIModel):
    style_profile: dict[str, Any] = Field(description="风格校准档案。")
    do_rules: list[str] = Field(default_factory=list, description="应遵守的风格规则。")
    avoid_rules: list[str] = Field(default_factory=list, description="应避免的风格问题。")
    example_rewrites: list[dict[str, str]] = Field(default_factory=list, description="示例改写。")


class SubplotDesignInput(APIModel):
    novel_constitution: dict[str, Any] = Field(description="小说宪法。")
    main_plot_state: dict[str, Any] = Field(description="主线当前状态。")
    characters: list[dict[str, Any]] = Field(default_factory=list, description="可参与支线的人物。")


class SubplotDesignOutput(APIModel):
    subplots: list[BranchOption] = Field(min_length=1, description="支线候选。")
    integration_points: list[str] = Field(default_factory=list, description="支线与主线交汇点。")
    risks: list[PromptRisk] = Field(default_factory=list, description="支线风险。")


class AntagonistDesignInput(APIModel):
    novel_constitution: dict[str, Any] = Field(description="小说宪法。")
    core_conflict_system: dict[str, Any] = Field(description="核心矛盾系统。")
    protagonist_profile: dict[str, Any] = Field(default_factory=dict, description="主角设定。")


class AntagonistDesignOutput(APIModel):
    antagonist_profile: dict[str, Any] = Field(description="反派或对立力量设定。")
    pressure_methods: list[str] = Field(default_factory=list, description="反派施压方式。")
    moral_logic: str = Field(default="", description="对立方自洽逻辑。")
    risks: list[PromptRisk] = Field(default_factory=list, description="反派设计风险。")


class ClimaxDesignInput(APIModel):
    novel_constitution: dict[str, Any] = Field(description="小说宪法。")
    macro_outline: dict[str, Any] = Field(description="宏观大纲。")
    crisis_candidates: list[dict[str, Any]] = Field(default_factory=list, description="危机候选。")
    foreshadowing_list: list[dict[str, Any]] = Field(default_factory=list, description="伏笔列表。")


class ClimaxDesignOutput(APIModel):
    climax_candidates: list[dict[str, Any]] = Field(min_length=1, description="高潮候选。")
    recommended_climax: str = Field(description="推荐高潮方案。")
    payoff_map: list[dict[str, Any]] = Field(default_factory=list, description="伏笔回收映射。")
    risks: list[PromptRisk] = Field(default_factory=list, description="高潮风险。")


class NextChapterStateChangeInput(APIModel):
    current_story_state: dict[str, Any] = Field(description="当前故事状态。")
    rolling_chapter_outline: list[dict[str, Any]] = Field(default_factory=list, description="滚动章纲。")
    narrative_ledger: dict[str, Any] = Field(default_factory=dict, description="叙事账本。")


class NextChapterStateChangeOutput(APIModel):
    required_changes: list[str] = Field(min_length=1, description="下一章必须改变的状态。")
    optional_changes: list[str] = Field(default_factory=list, description="可选状态变化。")
    avoid_static_repetition: list[str] = Field(default_factory=list, description="避免原地踏步的提醒。")


class RecommendedWorkflowOrderInput(APIModel):
    project_stage: str = Field(description="当前项目阶段。")
    available_artifacts: dict[str, Any] = Field(default_factory=dict, description="当前已有产物。")
    user_goal: str = Field(default="", description="用户当前目标。")


class RecommendedWorkflowOrderOutput(APIModel):
    ordered_steps: list[dict[str, Any]] = Field(description="推荐执行顺序。")
    skip_rules: list[str] = Field(default_factory=list, description="可跳过或延后的环节。")
    next_best_action: str = Field(description="当前最推荐的下一步。")


class MinimalWorkTemplateInput(APIModel):
    novel_constitution: dict[str, Any] = Field(description="小说宪法。")
    current_chapter_goal: str = Field(description="当前章节目标。")
    narrative_ledger: dict[str, Any] = Field(default_factory=dict, description="叙事账本。")


class MinimalWorkTemplateOutput(APIModel):
    chapter_card: dict[str, Any] = Field(description="极简章节卡。")
    scene_outline: list[ScenePlan] = Field(default_factory=list, description="极简场景细纲。")
    ledger_update_hint: list[str] = Field(default_factory=list, description="章后账本更新提醒。")


class SingleRoundGenerationComboInput(APIModel):
    novel_constitution: dict[str, Any] = Field(description="小说宪法。")
    current_chapter_goal: str = Field(description="当前章节目标。")
    narrative_ledger: dict[str, Any] = Field(default_factory=dict, description="叙事账本。")
    canon_context: dict[str, Any] = Field(default_factory=dict, description="正典上下文。")
    style_profile: dict[str, Any] = Field(default_factory=dict, description="风格校准档案。")


class SingleRoundGenerationComboOutput(APIModel):
    chapter_card: dict[str, Any] = Field(description="本轮生成的章节卡。")
    scene_outline: list[ScenePlan] = Field(description="本轮生成的场景细纲。")
    integrated_draft: str = Field(description="本轮生成的正文。")
    ledger_updates: dict[str, Any] = Field(default_factory=dict, description="章后账本更新。")
    self_check: dict[str, Any] = Field(default_factory=dict, description="本轮自检结果。")
