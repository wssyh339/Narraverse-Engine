from __future__ import annotations

from app.agents.shared.canon_context import CanonContext
from app.agents.shared.trace import AgentTraceEvent, append_trace


def test_canon_context_defaults_are_safe() -> None:
    context = CanonContext(project_id="prj_test")
    assert context.project_id == "prj_test"
    assert context.characters == []
    assert context.world_facts == []
    assert context.story_entities == []
    assert context.previous_summaries == []


def test_append_trace_adds_agent_event() -> None:
    events: list[AgentTraceEvent] = []
    append_trace(events, agent_name="StoryDirectorAgent", event_type="handoff", message="start")
    assert len(events) == 1
    assert events[0].agent_name == "StoryDirectorAgent"
    assert events[0].event_type == "handoff"
    assert events[0].message == "start"
