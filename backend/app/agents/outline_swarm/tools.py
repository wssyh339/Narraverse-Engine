from __future__ import annotations

from typing import Any

from app.agents.outline_swarm.state import OutlineSwarmState
from app.agents.shared.trace import append_trace


def upsert_canon_candidate(state: OutlineSwarmState, payload: dict[str, Any]) -> dict[str, Any]:
    candidate = {**payload, "source": "outline_swarm", "status": "candidate"}
    state.story_entities.append(candidate)
    append_trace(state.agent_trace, agent_name=state.active_agent, event_type="canon_candidate", message="写入候选正典", payload=candidate)
    return candidate


def create_character_candidate(state: OutlineSwarmState, payload: dict[str, Any]) -> dict[str, Any]:
    candidate = {
        **payload,
        "source": "outline_swarm",
        "status": "candidate",
        "activity_status": payload.get("activity_status") or "candidate",
    }
    state.character_candidates.append(candidate)
    append_trace(state.agent_trace, agent_name=state.active_agent, event_type="character_candidate", message="生成候选角色卡", payload=candidate)
    return candidate


def create_setting_candidate(state: OutlineSwarmState, payload: dict[str, Any]) -> dict[str, Any]:
    candidate = {
        **payload,
        "source": "outline_swarm",
        "status": "candidate",
        "activity_status": payload.get("activity_status") or "candidate",
    }
    state.setting_candidates.append(candidate)
    append_trace(state.agent_trace, agent_name=state.active_agent, event_type="setting_candidate", message="生成候选设定卡", payload=candidate)
    return candidate


def create_completion_ticket(state: OutlineSwarmState, payload: dict[str, Any]) -> dict[str, Any]:
    ticket = {**payload, "source": "outline_swarm", "status": "open"}
    state.completion_tickets.append(ticket)
    append_trace(state.agent_trace, agent_name=state.active_agent, event_type="completion_ticket", message="创建实体补全任务", payload=ticket)
    return ticket


def create_uncertainty_ticket(state: OutlineSwarmState, question: str) -> dict[str, Any]:
    ticket = {"question": question, "source": "outline_swarm", "status": "open"}
    state.uncertainty_tickets.append(ticket)
    append_trace(state.agent_trace, agent_name=state.active_agent, event_type="uncertainty_ticket", message=question, payload=ticket)
    return ticket


def record_outline_piece(state: OutlineSwarmState, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    if kind == "outline":
        state.outline.update(payload)
    elif kind == "volume":
        state.volume_outlines.append(payload)
    elif kind == "chapter":
        state.chapter_beats.append(payload)
    elif kind == "foreshadowing":
        state.foreshadowing_items.append(payload)
    else:
        raise ValueError(f"未知大纲片段类型：{kind}")
    append_trace(state.agent_trace, agent_name=state.active_agent, event_type="outline_piece", message=f"记录 {kind}", payload=payload)
    return payload
