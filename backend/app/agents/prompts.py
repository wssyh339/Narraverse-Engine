from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from app.agents.contracts import AgentSpec
from app.agents.shared.prompt_catalog import load_catalog_prompt


PROMPT_ROOT = Path(__file__).resolve().parents[1] / "prompts"

AGENT_SPEC_PROMPT_FILES: dict[str, str] = {'beat_control': 'agent_specs/beat_control.md',
 'canon_curator': 'agent_specs/canon_curator.md',
 'chapter_planner': 'agent_specs/chapter_planner.md',
 'character_tree': 'agent_specs/character_tree.md',
 'chief_architect': 'agent_specs/chief_architect.md',
 'creation_star': 'agent_specs/creation_star.md',
 'dialogue_writer': 'agent_specs/dialogue_writer.md',
 'editor_orchestrator': 'agent_specs/editor_orchestrator.md',
 'environment_writer': 'agent_specs/environment_writer.md',
 'fact_checker': 'agent_specs/fact_checker.md',
 'faction_conflict': 'agent_specs/faction_conflict.md',
 'foreshadowing_manager': 'agent_specs/foreshadowing_manager.md',
 'full_structure': 'agent_specs/full_structure.md',
 'genre_market_position': 'agent_specs/genre_market_position.md',
 'integrator': 'agent_specs/integrator.md',
 'logic_audit': 'agent_specs/logic_audit.md',
 'one_sentence_expansion': 'agent_specs/one_sentence_expansion.md',
 'plot_narrator': 'agent_specs/plot_narrator.md',
 'power_system': 'agent_specs/power_system.md',
 'protagonist_arc': 'agent_specs/protagonist_arc.md',
 'reviewer': 'agent_specs/reviewer.md',
 'style_unifier': 'agent_specs/style_unifier.md',
 'volume_outline': 'agent_specs/volume_outline.md',
 'world_bible': 'agent_specs/world_bible.md'}

AGENT_PROMPT_BINDINGS: dict[str, tuple[str, ...]] = {'beat_control': ('rolling_chapter_outline', 'chapter_card'),
 'canon_curator': ('narrative_ledger_update',
                   'foreshadowing_management',
                   'character_arc_management',
                   'relationship_network_management',
                   'world_rules_management',
                   'context_compression'),
 'chapter_planner': ('macro_outline',
                     'ending_backcast',
                     'volume_outline',
                     'rolling_chapter_outline',
                     'next_chapter_state_change',
                     'chapter_card',
                     'branch_plot_generation',
                     'rolling_outline_revision',
                     'subplot_design',
                     'climax_design'),
 'character_tree': ('character_arc_management', 'relationship_network_management'),
 'chief_architect': ('general_control',
                     'core_conflict_system',
                     'novel_constitution',
                     'constitution_stress_test',
                     'antagonist_design'),
 'creation_star': ('core_conflict_system', 'novel_constitution'),
 'dialogue_writer': ('draft_generation',),
 'editor_orchestrator': ('general_control', 'recommended_workflow_order'),
 'environment_writer': ('scene_outline', 'draft_generation'),
 'fact_checker': ('world_rules_management', 'timeline_check'),
 'faction_conflict': ('world_rules_management', 'relationship_network_management'),
 'foreshadowing_manager': ('foreshadowing_management',),
 'full_structure': ('macro_outline', 'ending_backcast'),
 'integrator': ('draft_generation', 'single_round_generation_combo'),
 'logic_audit': ('structure_editor_review', 'ten_chapter_health_check'),
 'one_sentence_expansion': ('core_conflict_system',),
 'plot_narrator': ('next_chapter_state_change', 'chapter_card', 'scene_outline', 'draft_generation'),
 'power_system': ('world_rules_management',),
 'protagonist_arc': ('character_arc_management',),
 'reviewer': ('draft_self_check', 'draft_rewrite', 'structure_editor_review', 'ten_chapter_health_check'),
 'style_unifier': ('style_calibration',),
 'volume_outline': ('volume_outline',),
 'world_bible': ('novel_constitution', 'world_rules_management')}


@lru_cache(maxsize=None)
def load_agent_spec_prompt(agent_name: str) -> str:
    try:
        relative_path = AGENT_SPEC_PROMPT_FILES[agent_name]
    except KeyError as exc:
        raise KeyError(f"Unknown agent prompt: {agent_name}") from exc
    return (PROMPT_ROOT / relative_path).read_text(encoding="utf-8").strip()


def _with_prompt_library(spec: AgentSpec) -> AgentSpec:
    prompt_ids = AGENT_PROMPT_BINDINGS.get(spec.name, ())
    if not prompt_ids:
        return spec
    prompt_blocks = "\n\n".join(
        f"### prompt_id={prompt_id}\n{load_catalog_prompt(prompt_id)}"
        for prompt_id in prompt_ids
    )
    prompt = (
        f"{spec.prompt}\n\n"
        "## 长篇小说生产提示词库绑定\n"
        "以下提示词来自 backend/app/prompts，必须结合 context、expected_output_schema 和当前 task 使用；"
        "不要机械复述提示词标题。\n\n"
        f"{prompt_blocks}"
    )
    return spec.model_copy(update={"prompt": prompt})


BASE_AGENT_SPECS: list[AgentSpec] = [
    AgentSpec(
        name='chief_architect',
        role='总策划 Agent',
        order=1,
        prompt=load_agent_spec_prompt('chief_architect'),
    ),
    AgentSpec(
        name='chapter_planner',
        role='章节规划 Agent',
        order=2,
        prompt=load_agent_spec_prompt('chapter_planner'),
    ),
    AgentSpec(
        name='plot_narrator',
        role='情节叙事 Agent',
        order=3,
        prompt=load_agent_spec_prompt('plot_narrator'),
    ),
    AgentSpec(
        name='dialogue_writer',
        role='人物对话 Agent',
        order=4,
        prompt=load_agent_spec_prompt('dialogue_writer'),
    ),
    AgentSpec(
        name='environment_writer',
        role='环境描写 Agent',
        order=5,
        prompt=load_agent_spec_prompt('environment_writer'),
    ),
    AgentSpec(
        name='reviewer',
        role='审核修改 Agent',
        order=6,
        prompt=load_agent_spec_prompt('reviewer'),
    ),
    AgentSpec(
        name='style_unifier',
        role='风格统一 Agent',
        order=7,
        prompt=load_agent_spec_prompt('style_unifier'),
    ),
    AgentSpec(
        name='fact_checker',
        role='事实核查 Agent',
        order=8,
        prompt=load_agent_spec_prompt('fact_checker'),
    ),
    AgentSpec(
        name='integrator',
        role='整合输出 Agent',
        order=9,
        prompt=load_agent_spec_prompt('integrator'),
    ),
    AgentSpec(
        name='canon_curator',
        role='设定整理 Agent',
        order=10,
        prompt=load_agent_spec_prompt('canon_curator'),
    ),
    AgentSpec(
        name='creation_star',
        role='创作 Star Agent',
        order=11,
        prompt=load_agent_spec_prompt('creation_star'),
    ),
]


OUTLINE_AGENT_SEQUENCE = ['editor_orchestrator',
 'one_sentence_expansion',
 'genre_market_position',
 'world_bible',
 'protagonist_arc',
 'character_tree',
 'faction_conflict',
 'power_system',
 'full_structure',
 'volume_outline',
 'beat_control',
 'foreshadowing_manager',
 'logic_audit']


OUTLINE_AGENT_SPECS: list[AgentSpec] = [
    AgentSpec(
        name='editor_orchestrator',
        role='总编统筹 Agent',
        order=20,
        prompt=load_agent_spec_prompt('editor_orchestrator'),
    ),
    AgentSpec(
        name='one_sentence_expansion',
        role='一句话故事扩展 Agent',
        order=21,
        prompt=load_agent_spec_prompt('one_sentence_expansion'),
    ),
    AgentSpec(
        name='genre_market_position',
        role='类型与卖点定位 Agent',
        order=22,
        prompt=load_agent_spec_prompt('genre_market_position'),
    ),
    AgentSpec(
        name='world_bible',
        role='世界观圣经 Agent',
        order=23,
        prompt=load_agent_spec_prompt('world_bible'),
    ),
    AgentSpec(
        name='protagonist_arc',
        role='主角欲望与成长 Agent',
        order=24,
        prompt=load_agent_spec_prompt('protagonist_arc'),
    ),
    AgentSpec(
        name='character_tree',
        role='人物树 Agent',
        order=25,
        prompt=load_agent_spec_prompt('character_tree'),
    ),
    AgentSpec(
        name='faction_conflict',
        role='势力与冲突 Agent',
        order=26,
        prompt=load_agent_spec_prompt('faction_conflict'),
    ),
    AgentSpec(
        name='power_system',
        role='金手指与升级体系 Agent',
        order=27,
        prompt=load_agent_spec_prompt('power_system'),
    ),
    AgentSpec(
        name='full_structure',
        role='全书结构 Agent',
        order=28,
        prompt=load_agent_spec_prompt('full_structure'),
    ),
    AgentSpec(
        name='volume_outline',
        role='卷级大纲 Agent',
        order=29,
        prompt=load_agent_spec_prompt('volume_outline'),
    ),
    AgentSpec(
        name='beat_control',
        role='章节节拍 Agent',
        order=30,
        prompt=load_agent_spec_prompt('beat_control'),
    ),
    AgentSpec(
        name='foreshadowing_manager',
        role='伏笔管理 Agent',
        order=31,
        prompt=load_agent_spec_prompt('foreshadowing_manager'),
    ),
    AgentSpec(
        name='logic_audit',
        role='逻辑审计与修订 Agent',
        order=32,
        prompt=load_agent_spec_prompt('logic_audit'),
    ),
]


DEFAULT_AGENT_SPECS = [_with_prompt_library(spec) for spec in [*BASE_AGENT_SPECS, *OUTLINE_AGENT_SPECS]]

AGENT_SPECS_BY_NAME = {spec.name: spec for spec in DEFAULT_AGENT_SPECS}
