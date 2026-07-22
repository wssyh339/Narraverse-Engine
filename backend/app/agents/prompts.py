from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from app.agents.contracts import AgentSpec
from app.agents.shared.prompt_catalog import load_catalog_prompt


PROMPT_ROOT = Path(__file__).resolve().parents[1] / "prompts"

AGENT_SPEC_PROMPT_FILES: dict[str, str] = {'canon_curator': 'agent_specs/canon_curator.md',
 'chapter_planner': 'agent_specs/chapter_planner.md',
 'chief_architect': 'agent_specs/chief_architect.md',
 'creation_star': 'agent_specs/creation_star.md',
 'dialogue_writer': 'agent_specs/dialogue_writer.md',
 'environment_writer': 'agent_specs/environment_writer.md',
 'fact_checker': 'agent_specs/fact_checker.md',
 'integrator': 'agent_specs/integrator.md',
 'plot_narrator': 'agent_specs/plot_narrator.md',
 'reviewer': 'agent_specs/reviewer.md',
 'style_unifier': 'agent_specs/style_unifier.md'}

AGENT_PROMPT_BINDINGS: dict[str, tuple[str, ...]] = {'canon_curator': ('narrative_ledger_update',
                   'foreshadowing_management',
                   'character_arc_management',
                   'relationship_network_management',
                   'world_rules_management',
                   'context_compression'),
 'chapter_planner': ('next_chapter_state_change',
                     'chapter_prep',
                     'chapter_card',
                     'branch_plot_generation',
                     'rolling_outline_revision',
                     'subplot_design',
                     'climax_design'),
 'chief_architect': ('general_control',
                     'core_conflict_system',
                     'novel_constitution',
                     'constitution_stress_test',
                     'antagonist_design'),
 'creation_star': (),
 'dialogue_writer': ('draft_generation',),
 'environment_writer': ('scene_outline', 'draft_generation'),
 'fact_checker': ('world_rules_management', 'timeline_check'),
 'integrator': ('draft_generation', 'single_round_generation_combo'),
 'plot_narrator': ('next_chapter_state_change',
                   'chapter_card',
                   'scene_outline',
                   'draft_generation'),
 'reviewer': ('draft_self_check',
              'draft_rewrite',
              'structure_editor_review',
              'ten_chapter_health_check'),
 'style_unifier': ('style_calibration',)}


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
        role='章节准备 AgentSpec',
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



DEFAULT_AGENT_SPECS = [_with_prompt_library(spec) for spec in BASE_AGENT_SPECS]

AGENT_SPECS_BY_NAME = {spec.name: spec for spec in DEFAULT_AGENT_SPECS}
