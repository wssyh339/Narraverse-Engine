from __future__ import annotations

import inspect
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_chapter_writing_lane_owns_workflow_implementation() -> None:
    import app.agents.chapter_writing.workflow as chapter_workflow

    source = inspect.getsource(chapter_workflow)
    assert "class AgentWorkflow" in source
    assert "from app.agents.workflow import" not in source
    assert hasattr(chapter_workflow.agent_workflow, "run_chapter_draft")
    assert hasattr(chapter_workflow.agent_workflow, "run_chapter_plan")


def test_legacy_workflow_is_compatibility_wrapper() -> None:
    source = (ROOT / "backend/app/agents/workflow.py").read_text(encoding="utf-8")
    assert "from app.agents.chapter_writing.workflow import" in source
    assert "class AgentWorkflow" not in source


def test_creation_star_lane_exposes_agent_service() -> None:
    import app.agents.creation_star.service as creation_star_service

    assert hasattr(creation_star_service, "creation_star_agent_service")
    service = creation_star_service.creation_star_agent_service
    assert hasattr(service, "draw")
    assert hasattr(service, "commit")
    assert hasattr(service, "options")


def test_studio_service_delegates_to_agent_lanes() -> None:
    source = (ROOT / "backend/app/services/studio_service.py").read_text(encoding="utf-8")
    assert "from app.agents.workflow import agent_workflow" not in source
    assert "from app.agents.chapter_writing.service import chapter_writing_service" in source
    assert "from app.agents.creation_star.service import creation_star_agent_service" in source
    assert "creation_star_agent_service.draw" in source
    assert "creation_star_agent_service.commit" in source
    assert "chapter_writing_service.run_initialization" in source
    assert "chapter_writing_service.run_chapter_plan" in source
    assert "chapter_writing_service.run_chapter_draft" in source
