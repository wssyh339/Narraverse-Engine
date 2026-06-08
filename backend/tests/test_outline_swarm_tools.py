from __future__ import annotations

from app.agents.outline_swarm.state import OutlineSwarmState
from app.agents.outline_swarm.tools import (
    create_completion_ticket,
    create_uncertainty_ticket,
    record_outline_piece,
    upsert_canon_candidate,
)


def test_tools_write_to_state_not_database() -> None:
    state = OutlineSwarmState(project_id="prj_test")
    upsert_canon_candidate(state, {"name": "候选城市", "entity_type": "location", "confidence": 0.72})
    create_completion_ticket(state, {"entity_name": "候选城市", "entity_level": "A"})
    create_uncertainty_ticket(state, "为什么主角必须进入候选城市？")
    record_outline_piece(state, "volume", {"volume_no": 1, "title": "第一卷"})
    assert state.story_entities[0]["name"] == "候选城市"
    assert state.completion_tickets[0]["entity_name"] == "候选城市"
    assert state.uncertainty_tickets[0]["question"] == "为什么主角必须进入候选城市？"
    assert state.volume_outlines[0]["title"] == "第一卷"
