from __future__ import annotations


def test_chapter_writing_lane_exports_agent_workflow() -> None:
    from app.agents.chapter_writing.workflow import agent_workflow

    assert hasattr(agent_workflow, "run_chapter_draft")
    assert hasattr(agent_workflow, "run_chapter_plan")
