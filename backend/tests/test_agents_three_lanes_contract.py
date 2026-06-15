from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_agents_are_split_into_three_lanes() -> None:
    expected = {
        "backend/app/agents/shared/__init__.py",
        "backend/app/agents/shared/contracts.py",
        "backend/app/agents/shared/prompt_loader.py",
        "backend/app/agents/shared/trace.py",
        "backend/app/agents/shared/canon_context.py",
        "backend/app/agents/creation_star/__init__.py",
        "backend/app/agents/creation_star/state.py",
        "backend/app/agents/creation_star/workflow.py",
        "backend/app/agents/creation_star/service.py",
        "backend/app/agents/outline_swarm/__init__.py",
        "backend/app/agents/outline_swarm/state.py",
        "backend/app/agents/outline_swarm/tools.py",
        "backend/app/agents/outline_swarm/validators.py",
        "backend/app/agents/outline_swarm/swarm.py",
        "backend/app/agents/outline_swarm/service.py",
        "backend/app/agents/chapter_writing/__init__.py",
        "backend/app/agents/chapter_writing/state.py",
        "backend/app/agents/chapter_writing/workflow.py",
        "backend/app/agents/chapter_writing/service.py",
    }
    missing = [path for path in sorted(expected) if not (ROOT / path).exists()]
    assert missing == []


def test_langgraph_swarm_dependency_is_declared() -> None:
    backend_requirements = (ROOT / "backend/requirements.txt").read_text(encoding="utf-8")
    root_requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert "langgraph-swarm" in backend_requirements
    assert "langgraph-swarm" in root_requirements


def test_docs_describe_three_agent_lanes() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    for doc in [readme, agents]:
        assert "creation_star" in doc
        assert "outline_swarm" in doc
        assert "chapter_writing" in doc
        assert "langgraph-swarm" in doc
