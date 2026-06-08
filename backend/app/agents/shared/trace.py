from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.schemas.common import APIModel


class AgentTraceEvent(APIModel):
    timestamp: str
    agent_name: str
    event_type: str
    message: str
    payload: dict[str, Any] = {}


def append_trace(
    events: list[AgentTraceEvent],
    *,
    agent_name: str,
    event_type: str,
    message: str,
    payload: dict[str, Any] | None = None,
) -> AgentTraceEvent:
    event = AgentTraceEvent(
        timestamp=datetime.now(UTC).isoformat(),
        agent_name=agent_name,
        event_type=event_type,
        message=message,
        payload=payload or {},
    )
    events.append(event)
    return event
