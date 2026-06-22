from __future__ import annotations

from fastapi import Depends, Query
from sqlalchemy.orm import Session

from app.api.v1.endpoints.studio import (
    archive_canon_items,
    approve_canon_proposal,
    create_character,
    create_canon_folder,
    create_entity,
    create_world_fact,
    delete_character,
    delete_entity,
    delete_world_fact,
    export_canon_package,
    generate_settings,
    get_canon_health,
    get_canon_impact,
    get_character,
    get_graph,
    get_subgraph,
    list_canon_proposals,
    list_canon_tree,
    list_canon_versions,
    list_characters,
    list_entities,
    list_world_facts,
    move_canon_node,
    reject_canon_proposal,
    rollback_canon_version,
    scan_canon_duplicates,
    set_canon_locks,
    update_character,
    update_entity,
    update_world_fact,
)
from app.core.responses import success_response
from app.db.session import get_db
from app.services.studio_service import studio_service


def get_canon_version_timeline(
    project_id: str,
    ref_type: str | None = Query(default=None),
    ref_id: str | None = Query(default=None),
    chapter_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    return success_response(
        studio_service.get_canon_version_timeline(
            db,
            project_id,
            ref_type=ref_type,
            ref_id=ref_id,
            chapter_id=chapter_id,
        )
    )
