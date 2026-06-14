from pathlib import Path

from app.agents.prompts import AGENT_SPECS_BY_NAME


def test_outline_agent_prompts_keep_full_fixed_details() -> None:
    editor_prompt = AGENT_SPECS_BY_NAME["editor_orchestrator"].prompt
    one_sentence_prompt = AGENT_SPECS_BY_NAME["one_sentence_expansion"].prompt
    world_prompt = AGENT_SPECS_BY_NAME["world_bible"].prompt
    volume_prompt = AGENT_SPECS_BY_NAME["volume_outline"].prompt
    beat_prompt = AGENT_SPECS_BY_NAME["beat_control"].prompt
    logic_prompt = AGENT_SPECS_BY_NAME["logic_audit"].prompt

    assert "你的核心目标" in editor_prompt
    assert "current_judgment" in editor_prompt
    assert "禁止直接生成大段正文" in editor_prompt
    assert "suitability_score" in one_sentence_prompt
    assert "weaknesses_to_fix" in one_sentence_prompt
    assert "loss_of_control_risk" in world_prompt
    assert "forbidden_changes" in world_prompt
    assert "不能套用固定五段模板" in volume_prompt
    assert "rhythm_model" in volume_prompt
    assert "major_events" in volume_prompt
    assert "chapter_function_table" in beat_prompt
    assert "special_audits" in logic_prompt
    assert "A级问题 = 0" in logic_prompt

    for name in [
        "editor_orchestrator",
        "one_sentence_expansion",
        "genre_market_position",
        "world_bible",
        "protagonist_arc",
        "character_tree",
        "faction_conflict",
        "power_system",
        "full_structure",
        "volume_outline",
        "beat_control",
        "foreshadowing_manager",
        "logic_audit",
    ]:
        assert len(AGENT_SPECS_BY_NAME[name].prompt) > 500


def test_outline_models_gate_router_workflow_and_exports(tmp_path: Path) -> None:
    from app.agents.outline_models import ForeshadowingItem, ProjectConfig, StoryState, VolumeOutline
    from app.agents.outline_workflow import GateValidator, NovelWorkflow, RevisionRouter

    config = ProjectConfig(
        project_name="长篇推演测试",
        genre="都市脑洞",
        tone="搞笑腹黑",
        must_keep_elements=["主角反常识破局"],
        forbidden_elements=["机械降神"],
    )
    state = StoryState(config=config, raw_worldview="规则会惩罚正常人。")
    assert state.config.target_words == 1000000
    assert state.current_stage == "S0"

    volume = VolumeOutline(
        volume=1,
        title="第一卷：异常开局",
        chapter_range="1-50",
        core_map="规则医院",
        main_plot="主角发现正常行为会被惩罚。",
        hidden_plot="医院只是更大规则系统的入口。",
        foreshadowing_plot="错误病历在本卷埋设、误导并于卷末回收。",
        protagonist_upgrade={"ability": "识别规则漏洞"},
        phases=[
            {"phase": index + 1, "major_events": [f"事件{item}" for item in range(5)]}
            for index in range(5)
        ],
        final_hook="主角收到来自下一层规则的账单。",
        change_summary={"protagonist": "从被动求生到主动试探。"},
        risks=[],
    )
    foreshadowing = ForeshadowingItem(
        id="F001",
        name="错误病历",
        first_appearance="第1章",
        surface_meaning="医生写错了名字。",
        true_meaning="名字是规则身份锁。",
        related_characters=["林缺"],
        related_factions=["规则医院"],
        importance="high",
        progress_nodes=["第10章"],
        misdirection_nodes=["第20章"],
        payoff_node="第50章",
        payoff_method="用错误身份反杀规则。",
        status="planted",
    )
    assert volume.phases[0]["major_events"]
    assert foreshadowing.id == "F001"

    gate = GateValidator()
    assert gate.validate_single_volume(volume)["passed"] is True
    assert RevisionRouter().route_issue("金手指万能导致战力膨胀太快") == "PowerSystemAgent"

    workflow = NovelWorkflow(config=config, raw_worldview=state.raw_worldview, one_sentence_story="林缺用反常识操作让怪谈规则破防。")
    final_state = workflow.run_full_pipeline()
    assert final_state.current_stage == "S13"
    assert len(final_state.volumes) == 10
    assert all(len(item.phases) == 5 for item in final_state.volumes)
    assert final_state.audit_reports[-1].passed is True

    exported = workflow.export_final_outline(tmp_path)
    assert (tmp_path / "01_故事核心.md").exists()
    assert (tmp_path / "13_最终修订版纲要.md").exists()
    assert len(exported) >= 13
