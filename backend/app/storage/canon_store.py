from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.schemas.canon import CanonEntity, CompletionStatus, EntityLevel


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _empty_store(project_id: str) -> dict[str, Any]:
    return {
        "project_id": project_id,
        "entities": {},
        "completion_tickets": [],
        "continuity_issues": [],
        "updated_at": utc_now(),
    }


class CanonStore:
    """Project-local canon database backed by JSON files.

    The store deliberately behaves like a tiny append-aware canon database rather
    than a text dump: callers upsert named entities, record versions, and ask for
    incomplete S/A entities before content is allowed into the formal outline.
    """

    def __init__(self, project_id: str, base_dir: Path | str = "outputs") -> None:
        self.project_id = project_id
        self.base_dir = Path(base_dir)
        self.project_dir = self.base_dir / project_id
        self.canon_path = self.project_dir / "canon_store.json"
        self.trace_path = self.project_dir / "trace_store.json"
        self.version_path = self.project_dir / "version_store.json"

    def _ensure_dir(self) -> None:
        self.project_dir.mkdir(parents=True, exist_ok=True)

    def load(self) -> dict[str, Any]:
        if not self.canon_path.exists():
            return _empty_store(self.project_id)
        return self._read_json(self.canon_path, _empty_store(self.project_id))

    def save(self, payload: dict[str, Any]) -> Path:
        self._ensure_dir()
        payload["updated_at"] = utc_now()
        self.canon_path.write_text(self._to_json(payload), encoding="utf-8")
        return self.canon_path

    def load_trace(self) -> dict[str, Any]:
        return self._read_json(self.trace_path, {"project_id": self.project_id, "events": []})

    def save_trace(self, events: list[dict[str, Any]]) -> Path:
        self._ensure_dir()
        self.trace_path.write_text(
            self._to_json({"project_id": self.project_id, "events": events, "updated_at": utc_now()}),
            encoding="utf-8",
        )
        return self.trace_path

    def load_versions(self) -> dict[str, Any]:
        return self._read_json(self.version_path, {"project_id": self.project_id, "versions": []})

    def save_versions(self, versions: dict[str, Any]) -> Path:
        self._ensure_dir()
        versions["updated_at"] = utc_now()
        self.version_path.write_text(self._to_json(versions), encoding="utf-8")
        return self.version_path

    def upsert_entity(self, entity: CanonEntity, actor: str = "CanonMergeNode") -> CanonEntity:
        payload = self.load()
        entities = payload.setdefault("entities", {})
        existing = entities.get(entity.key)
        next_entity = entity
        if existing:
            merged_payload = deepcopy(existing.get("payload", {}))
            merged_payload.update(entity.payload)
            next_entity = CanonEntity(
                **{
                    **existing,
                    **entity.model_dump(mode="json"),
                    "payload": merged_payload,
                    "version": int(existing.get("version", 1)) + 1,
                }
            )
        entities[next_entity.key] = next_entity.model_dump(mode="json")
        self.save(payload)
        self.record_version(next_entity.key, actor, next_entity.model_dump(mode="json"))
        return next_entity

    def get_entity(self, entity_key: str) -> CanonEntity | None:
        raw = self.load().get("entities", {}).get(entity_key)
        return CanonEntity(**raw) if raw else None

    def list_entities(self) -> list[CanonEntity]:
        return [CanonEntity(**raw) for raw in self.load().get("entities", {}).values()]

    def find_incomplete_entities(self) -> list[CanonEntity]:
        return [
            entity
            for entity in self.list_entities()
            if entity.level in {EntityLevel.S, EntityLevel.A}
            and (entity.completion_status != CompletionStatus.COMPLETE or not entity.continuity_checked)
        ]

    def mark_entity_complete(self, entity_key: str, actor: str = "ContinuityAgent") -> CanonEntity | None:
        entity = self.get_entity(entity_key)
        if entity is None:
            return None
        completed = entity.model_copy(update={"completion_status": CompletionStatus.COMPLETE, "continuity_checked": True})
        return self.upsert_entity(completed, actor=actor)

    def record_version(self, entity_key: str, actor: str, content: dict[str, Any]) -> None:
        versions = self.load_versions()
        versions.setdefault("versions", []).append(
            {
                "entity_key": entity_key,
                "actor": actor,
                "content": content,
                "created_at": utc_now(),
            }
        )
        self.save_versions(versions)

    def detect_conflict(self, entity: CanonEntity) -> list[dict[str, Any]]:
        existing = self.get_entity(entity.key)
        if existing is None:
            return []
        if existing.completion_status != CompletionStatus.COMPLETE:
            return []
        conflicts: list[dict[str, Any]] = []
        for key, value in entity.payload.items():
            existing_value = existing.payload.get(key)
            if key in existing.payload and existing_value not in ("", None) and existing_value not in ([], {}) and existing_value != value:
                conflicts.append(
                    {
                        "type": "payload_conflict",
                        "entity_key": entity.key,
                        "field": key,
                        "existing": existing.payload[key],
                        "incoming": value,
                    }
                )
        return conflicts

    @staticmethod
    def _to_json(payload: dict[str, Any]) -> str:
        import json

        return json.dumps(payload, ensure_ascii=False, indent=2)

    @staticmethod
    def _read_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
        if not path.exists():
            return default
        import json

        return json.loads(path.read_text(encoding="utf-8"))
