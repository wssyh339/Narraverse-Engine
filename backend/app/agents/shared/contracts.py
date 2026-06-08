from __future__ import annotations

from app.schemas.common import APIModel


class AgentLaneResult(APIModel):
    lane: str
    status: str
