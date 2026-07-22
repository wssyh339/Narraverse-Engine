from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_agents_are_split_into_active_lanes() -> None:
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
        "backend/app/api/v1/endpoints/outline_debate.py",
        "backend/app/services/outline_debate_service.py",
        "backend/app/agents/chapter_writing/__init__.py",
        "backend/app/agents/chapter_writing/state.py",
        "backend/app/agents/chapter_writing/workflow.py",
        "backend/app/agents/chapter_writing/service.py",
    }
    missing = [path for path in sorted(expected) if not (ROOT / path).exists()]
    assert missing == []


def test_legacy_outline_story_state_code_is_removed() -> None:
    deleted_paths = [
        "backend/app/agents/outline_llm_client.py",
        "backend/app/agents/outline_agents.py",
        "backend/app/agents/outline_models.py",
        "backend/app/agents/outline_storage.py",
        "backend/app/agents/outline_workflow.py",
    ]
    for path in deleted_paths:
        assert not (ROOT / path).exists(), f"{path} should stay deleted"


def test_langgraph_swarm_dependency_is_declared() -> None:
    backend_requirements = (ROOT / "backend/requirements.txt").read_text(encoding="utf-8")
    root_requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert "langgraph-swarm" in backend_requirements
    assert "langgraph-swarm" in root_requirements


def test_docs_describe_active_agent_lanes() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    root_agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    backend_agents = (ROOT / "backend/AGENTS.md").read_text(encoding="utf-8")
    assert "backend/AGENTS.md" in root_agents
    assert "GLOBAL-DISCOVERY-001" in root_agents
    assert "BACKEND-AGENT-LANES-001" in backend_agents
    for doc in [readme, backend_agents]:
        assert "creation_star" in doc
        assert "outline_debate" in doc
        assert "chapter_writing" in doc
        assert "outline_swarm" not in doc
    assert "返回初始化、章节规划" not in backend_agents
    assert "结构化故事状态、章节规划" not in backend_agents
    assert "历史源码" in backend_agents
    assert "对外稳定的正式 Agent 角色为 11 个" not in backend_agents


def test_active_readme_uses_outline_debate_not_legacy_swarm_labels() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "大纲议事" in readme
    assert "outline/debate/sessions" in readme
    assert "大纲 Swarm" not in readme
    assert "大纲 Swarm 线" not in readme
    assert "python main.py plan" not in readme


def test_active_architecture_doc_uses_outline_debate_not_legacy_swarm() -> None:
    architecture = (ROOT / "docs/architecture.md").read_text(encoding="utf-8")
    assert "outline_debate" in architecture
    assert "backend/app/services/outline_debate_service.py" in architecture
    assert "backend/app/agents/outline_swarm/" not in architecture
    assert "大纲 Swarm" not in architecture
