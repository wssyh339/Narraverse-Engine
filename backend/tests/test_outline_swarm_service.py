from __future__ import annotations

from app.agents.outline_swarm.service import run_outline_swarm
from app.agents.outline_swarm.swarm import OUTLINE_SWARM_AGENT_NAMES, build_outline_swarm


def test_run_outline_swarm_returns_structured_result_without_api_key() -> None:
    result = run_outline_swarm(
        {
            "project_id": "prj_test",
            "seed": {"genre": "都市脑洞", "premise": "一个普通人发现城市规则正在重写现实。"},
            "volume_target": 1,
            "chapter_target": 2,
        }
    )
    assert result["project_id"] == "prj_test"
    assert result["status"] in {"passed", "needs_user_review", "failed"}
    assert result["outline"]
    assert result["volume_outlines"]
    assert result["chapter_beats"]
    assert result["agent_trace"]


def test_outline_swarm_builds_langgraph_swarm() -> None:
    graph = build_outline_swarm()
    app = graph.compile()
    result = app.invoke({"project_id": "prj_test", "seed": {}, "active_agent": "StoryDirectorAgent"})
    assert result["active_agent"] == "WhyInterrogatorAgent"
    assert result["iteration_count"] == 1


def test_run_outline_swarm_visits_expected_agents() -> None:
    result = run_outline_swarm(
        {
            "project_id": "prj_test",
            "seed": {"genre": "工业幻想", "premise": "一个工匠发现城市的动力源正在说谎。"},
            "volume_target": 2,
            "chapter_target": 4,
        }
    )
    visited = {event["agent_name"] for event in result["agent_trace"]}
    for agent_name in OUTLINE_SWARM_AGENT_NAMES:
        assert agent_name in visited
    assert result["status"] == "passed"
