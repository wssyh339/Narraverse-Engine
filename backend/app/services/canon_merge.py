from __future__ import annotations

from typing import Any

from pydantic import Field

from app.schemas.canon import CanonCompletionTicket, CanonEntity, ContinuityIssue
from app.schemas.common import APIModel
from app.services.entity_router import CanonCompletionRouter
from app.storage.canon_store import CanonStore


class CanonMergeResult(APIModel):
    merged_entities: list[CanonEntity] = Field(default_factory=list)
    completion_tickets: list[CanonCompletionTicket] = Field(default_factory=list)
    continuity_issues: list[ContinuityIssue] = Field(default_factory=list)
    merge_actions: list[dict[str, Any]] = Field(default_factory=list)


class CanonMergeNode:
    def __init__(self, router: CanonCompletionRouter | None = None) -> None:
        self.router = router or CanonCompletionRouter()

    def merge_entities(self, store: CanonStore, entities: list[CanonEntity]) -> CanonMergeResult:
        result = CanonMergeResult()
        payload = store.load()
        for entity in entities:
            entity = CanonEntity.model_validate(entity.__dict__)
            conflicts = store.detect_conflict(entity)
            if conflicts:
                issue = ContinuityIssue(
                    issue_id=f"ci_{abs(hash((entity.key, tuple(item['field'] for item in conflicts)))) % 10**12:012d}",
                    severity="blocking",
                    issue_type="canon_conflict",
                    location=entity.first_appearance or "CanonMergeNode",
                    message=f"实体「{entity.name}」的新设定与既有正典冲突。",
                    impact_scope="会导致后续大纲无法判断哪个版本为真。",
                    suggested_agent="ContinuityAgent",
                    repair_requirement="保留双方证据，交由对应 Agent 解释、修订或创建分支，不得直接覆盖。",
                )
                result.continuity_issues.append(issue)
                payload.setdefault("continuity_issues", []).append(issue.model_dump(mode="json"))
                result.merge_actions.append({"action": "conflict", "entity_key": entity.key, "conflicts": conflicts})
                continue

            merged = store.upsert_entity(entity, actor="CanonMergeNode")
            result.merged_entities.append(merged)
            ticket = self.router.ticket_for_entity(merged)
            if ticket:
                result.completion_tickets.append(ticket)
                payload = store.load()
                tickets = payload.setdefault("completion_tickets", [])
                if not any(item.get("ticket_id") == ticket.ticket_id for item in tickets):
                    tickets.append(ticket.model_dump(mode="json"))
                store.save(payload)
                result.merge_actions.append({"action": "need_completion", "entity_key": entity.key, "ticket_id": ticket.ticket_id})
            else:
                result.merge_actions.append({"action": "merged", "entity_key": entity.key})

        if result.continuity_issues:
            store.save(payload)
        return result
