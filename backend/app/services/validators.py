from __future__ import annotations

from typing import Any

from app.schemas.canon import DramaNodeType, NovelState
from app.storage.canon_store import CanonStore


class ContinuityAgentValidator:
    def validate_store(self, store: CanonStore) -> dict[str, Any]:
        issues: list[dict[str, Any]] = []
        for entity in store.find_incomplete_entities():
            issues.append(
                {
                    "severity": "blocking",
                    "type": "entity_completion",
                    "entity_key": entity.key,
                    "message": f"S / A 级实体缺档案：{entity.name}",
                    "suggested_agent": "ContinuityAgent",
                    "repair_requirement": "先补全实体字段并通过连续性检查，再进入正式大纲。",
                }
            )
        return {
            "passed": len(issues) == 0,
            "score": 1.0 if not issues else 0.35,
            "issues": issues,
        }

    def validate_state(self, state: NovelState, store: CanonStore) -> dict[str, Any]:
        report = self.validate_store(store)
        node_types = {node.node_type for node in state.drama_nodes}
        for required in [DramaNodeType.CRISIS, DramaNodeType.CLIMAX, DramaNodeType.RESOLUTION]:
            if required not in node_types:
                report["issues"].append(
                    {
                        "severity": "blocking",
                        "type": "drama_node_missing",
                        "message": f"缺少 {required.value} 节点，危机/高潮/结果链不完整。",
                        "suggested_agent": "CrisisClimaxAgent",
                        "repair_requirement": "严格区分危机、高潮和结果。",
                    }
                )
        for node in state.drama_nodes:
            if not node.story_function or not node.why_chain:
                report["issues"].append(
                    {
                        "severity": "warning",
                        "type": "drama_function_missing",
                        "message": f"DramaNode「{node.title}」缺少戏剧功能或 Why Chain。",
                        "suggested_agent": "WhyInterrogatorAgent",
                        "repair_requirement": "说明改变了什么、增加了什么压力、如何逼近危机高潮。",
                    }
                )
        report["passed"] = not any(issue["severity"] == "blocking" for issue in report["issues"])
        report["score"] = 1.0 if report["passed"] and not report["issues"] else (0.72 if report["passed"] else 0.35)
        return report
