from __future__ import annotations

from app.agents.outline_swarm.state import OutlineSwarmState
from app.agents.outline_swarm.validators import OutlineSwarmStopValidator


def test_outline_swarm_state_has_safe_defaults() -> None:
    state = OutlineSwarmState(project_id="prj_test")
    assert state.active_agent == "StoryDirectorAgent"
    assert state.iteration_count == 0
    assert state.max_iterations == 18
    assert state.status == "running"
    assert state.volume_outlines == []


def test_stop_validator_passes_when_requirements_met() -> None:
    state = OutlineSwarmState(
        project_id="prj_test",
        volume_target=1,
        chapter_target=2,
        volume_outlines=[{"volume_no": 1}],
        chapter_beats=[{"chapter_no": 1}, {"chapter_no": 2}],
        continuity_issues=[],
        incomplete_required_entities=[],
    )
    result = OutlineSwarmStopValidator().evaluate(state)
    assert result.should_stop is True
    assert result.status == "passed"


def test_stop_validator_loops_when_blocking_issues_exist() -> None:
    state = OutlineSwarmState(
        project_id="prj_test",
        continuity_issues=[{"severity": "blocking", "message": "S级实体缺档案"}],
    )
    result = OutlineSwarmStopValidator().evaluate(state)
    assert result.should_stop is False
    assert result.status == "running"
