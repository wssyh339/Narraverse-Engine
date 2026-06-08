from __future__ import annotations

from typing import Literal

from app.agents.outline_swarm.state import OutlineSwarmState
from app.schemas.common import APIModel


class OutlineSwarmStopResult(APIModel):
    should_stop: bool
    status: Literal["running", "passed", "failed", "needs_user_review"]
    reasons: list[str]


class OutlineSwarmStopValidator:
    def evaluate(self, state: OutlineSwarmState) -> OutlineSwarmStopResult:
        reasons: list[str] = []
        blocking = [issue for issue in state.continuity_issues if issue.get("severity") == "blocking"]
        if blocking:
            reasons.append("存在 blocking continuity issue")
        if state.incomplete_required_entities:
            reasons.append("存在未补全 S/A 级实体")
        if len(state.volume_outlines) < state.volume_target:
            reasons.append("卷纲数量未达标")
        if len(state.chapter_beats) < state.chapter_target:
            reasons.append("章纲/节拍数量未达标")
        if state.iteration_count >= state.max_iterations:
            return OutlineSwarmStopResult(should_stop=True, status="failed", reasons=["达到最大迭代次数", *reasons])
        if reasons:
            return OutlineSwarmStopResult(should_stop=False, status="running", reasons=reasons)
        return OutlineSwarmStopResult(should_stop=True, status="passed", reasons=["大纲 Swarm 停止条件已满足"])
