from __future__ import annotations

from app.agents.chapter_writing.workflow import AgentWorkflow
from app.agents.chapter_writing import workflow as _chapter_workflow

llm_client = _chapter_workflow.llm_client


class CompatAgentWorkflow:
    def _sync_compat_globals(self) -> None:
        _chapter_workflow.llm_client = llm_client

    def run_initialization(self, state):
        self._sync_compat_globals()
        return _chapter_workflow.agent_workflow.run_initialization(state)

    def run_chapter_draft(self, state):
        self._sync_compat_globals()
        return _chapter_workflow.agent_workflow.run_chapter_draft(state)


agent_workflow = CompatAgentWorkflow()

__all__ = ["AgentWorkflow", "agent_workflow"]
