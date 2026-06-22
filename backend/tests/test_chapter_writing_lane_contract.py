from __future__ import annotations


def test_chapter_writing_lane_exports_agent_workflow() -> None:
    from app.agents.chapter_writing.workflow import agent_workflow

    assert hasattr(agent_workflow, "run_chapter_draft")
    assert not hasattr(agent_workflow, "run_chapter_plan")


def test_chapter_writing_lane_does_not_recommend_legacy_outline_planning() -> None:
    import inspect
    import app.agents.chapter_writing.workflow as chapter_workflow

    source = inspect.getsource(chapter_workflow)
    assert "outline_planning" not in source
    assert "outline_debate" in source
