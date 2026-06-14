from __future__ import annotations

from app.agents.contracts import NovelStudioState
from app.agents.chapter_writing.workflow import agent_workflow


class ChapterWritingService:
    def run_initialization(self, state: NovelStudioState) -> NovelStudioState:
        return agent_workflow.run_initialization(state)

    def run_chapter_plan(self, state: NovelStudioState) -> NovelStudioState:
        return agent_workflow.run_chapter_plan(state)

    def run_chapter_draft(self, state: NovelStudioState) -> NovelStudioState:
        return agent_workflow.run_chapter_draft(state)


chapter_writing_service = ChapterWritingService()

__all__ = ["ChapterWritingService", "chapter_writing_service", "agent_workflow"]
