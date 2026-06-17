from datetime import datetime, timezone
from typing import Any

from app.core.json import loads
from app.db import models


def isoformat(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def serialize_project(project: models.Project) -> dict[str, Any]:
    return {
        "id": project.id,
        "title": project.title,
        "genre": project.genre,
        "target_reader": project.target_reader,
        "premise": project.premise,
        "style_guide": project.style_guide,
        "language": project.language,
        "planned_chapter_count": project.planned_chapter_count,
        "planned_volume_count": project.planned_volume_count,
        "chapters_per_volume": project.chapters_per_volume,
        "chapter_word_target": project.chapter_word_target,
        "chapter_word_min": project.chapter_word_min,
        "chapter_word_max": project.chapter_word_max,
        "target_words": project.target_words,
        "current_volume": project.current_volume,
        "current_chapter": project.current_chapter,
        "cover_image": project.cover_image,
        "initial_idea": project.initial_idea,
        "status": project.status,
        "created_at": isoformat(project.created_at),
        "updated_at": isoformat(project.updated_at),
    }


def serialize_story_bible(story_bible: models.StoryBible, include_style_guide: bool = True) -> dict[str, Any]:
    payload = {
        "id": story_bible.id,
        "project_id": story_bible.project_id,
        "version": story_bible.version,
        "world_setting": story_bible.world_setting,
        "main_conflict": story_bible.main_conflict,
        "themes": loads(story_bible.themes_json, []),
        "narrative_pov": story_bible.narrative_pov,
        "forbidden_elements": loads(story_bible.forbidden_elements_json, []),
        "continuity_rules": loads(story_bible.continuity_rules_json, []),
        "created_at": isoformat(story_bible.created_at),
        "updated_at": isoformat(story_bible.updated_at),
    }
    if include_style_guide:
        payload["style_guide"] = story_bible.style_guide
    return payload


def serialize_creation_session(session: models.CreationSession) -> dict[str, Any]:
    return {
        "id": session.id,
        "project_id": session.project_id,
        "status": session.status,
        "current_step": session.current_step,
        "basic_info": loads(session.basic_info_json, {}),
        "state": loads(session.state_json, {}),
        "created_at": isoformat(session.created_at),
        "updated_at": isoformat(session.updated_at),
    }


def serialize_job(job: models.GenerationJob) -> dict[str, Any]:
    return {
        "id": job.id,
        "project_id": job.project_id,
        "chapter_id": job.chapter_id,
        "job_type": job.job_type,
        "status": job.status,
        "idempotency_key": job.idempotency_key,
        "model": job.model,
        "progress": loads(job.progress_json, {}),
        "current_agent": job.current_agent,
        "result": loads(job.result_json, None) if job.result_json else None,
        "langsmith_run_id": getattr(job, "langsmith_run_id", ""),
        "langsmith_url": getattr(job, "langsmith_url", ""),
        "trace_mode": getattr(job, "trace_mode", "local"),
        "error": {"message": job.error_message} if job.error_message else None,
        "created_at": isoformat(job.created_at),
        "started_at": isoformat(job.started_at),
        "finished_at": isoformat(job.finished_at),
    }


def serialize_chapter(chapter: models.Chapter) -> dict[str, Any]:
    return {
        "id": chapter.id,
        "project_id": chapter.project_id,
        "volume_no": chapter.volume_no,
        "chapter_no": chapter.chapter_no,
        "title": chapter.title,
        "outline": chapter.outline,
        "pov_character": chapter.pov_character,
        "core_event": chapter.core_event,
        "conflict": chapter.conflict,
        "turn_point": chapter.turn_point,
        "emotional_beats": loads(chapter.emotional_beats_json, []),
        "plot_purpose": chapter.plot_purpose,
        "cliffhanger": chapter.cliffhanger,
        "crisis": chapter.crisis,
        "climax": chapter.climax,
        "outcome": chapter.outcome,
        "chapter_hook": chapter.chapter_hook,
        "foreshadowing_plants": loads(chapter.foreshadowing_plants_json, []),
        "foreshadowing_payoffs": loads(chapter.foreshadowing_payoffs_json, []),
        "canon_updates": loads(chapter.canon_updates_json, []),
        "continuity_risks": loads(chapter.continuity_risks_json, []),
        "draft_text": chapter.draft_text,
        "final_text": chapter.final_text,
        "summary": chapter.summary,
        "revision_notes": chapter.revision_notes,
        "status": chapter.status,
        "word_target": chapter.word_target,
        "word_count": chapter.word_count,
        "sort_order": chapter.sort_order,
        "is_locked": bool(chapter.is_locked),
        "deleted_at": isoformat(chapter.deleted_at),
        "created_at": isoformat(chapter.created_at),
        "updated_at": isoformat(chapter.updated_at),
    }


def serialize_volume(volume: models.Volume) -> dict[str, Any]:
    return {
        "id": volume.id,
        "project_id": volume.project_id,
        "volume_no": volume.volume_no,
        "title": volume.title,
        "outline": volume.outline,
        "status": volume.status,
        "sort_order": volume.sort_order,
        "created_at": isoformat(volume.created_at),
        "updated_at": isoformat(volume.updated_at),
    }


def serialize_note(note: models.Note) -> dict[str, Any]:
    return {
        "id": note.id,
        "project_id": note.project_id,
        "parent_id": note.parent_id,
        "note_type": note.note_type,
        "title": note.title,
        "content": note.content,
        "sort_order": note.sort_order,
        "is_pinned": bool(note.is_pinned),
        "created_at": isoformat(note.created_at),
        "updated_at": isoformat(note.updated_at),
    }


def serialize_editor_proposal(proposal: models.EditorProposal) -> dict[str, Any]:
    return {
        "id": proposal.id,
        "project_id": proposal.project_id,
        "chapter_id": proposal.chapter_id,
        "tool_name": proposal.tool_name,
        "instruction": proposal.instruction,
        "original_content": proposal.original_content,
        "proposed_content": proposal.proposed_content,
        "diff": loads(proposal.diff_json, []),
        "status": proposal.status,
        "created_at": isoformat(proposal.created_at),
        "applied_at": isoformat(proposal.applied_at),
    }


def serialize_character(character: models.Character) -> dict[str, Any]:
    return {
        "id": character.id,
        "project_id": character.project_id,
        "name": character.name,
        "aliases": loads(character.aliases_json, []),
        "role": character.role,
        "role_type": character.role_type,
        "importance_level": character.importance_level,
        "importance_score": character.importance_score,
        "summary": character.summary or character.profile,
        "appearance": character.appearance,
        "personality": character.personality,
        "profile": character.profile,
        "goals": loads(character.goals_json, []),
        "motivations": loads(character.motivations_json, []) or ([character.motivation] if character.motivation else []),
        "secrets": loads(character.secrets_json, []),
        "abilities": loads(character.abilities_json, []),
        "weaknesses": loads(character.weaknesses_json, []),
        "character_arc": character.character_arc or character.arc,
        "current_status": character.current_status,
        "first_appearance_chapter_id": character.first_appearance_chapter_id,
        "last_seen_chapter_id": character.last_seen_chapter_id,
        "related_entity_ids": loads(character.related_entity_ids_json, []),
        "related_character_ids": loads(character.related_character_ids_json, []),
        "updated_reason": character.updated_reason,
        "relations": loads(character.relations_json, []),
        "status": character.status,
        "source": character.source,
        "created_at": isoformat(character.created_at),
        "updated_at": isoformat(character.updated_at),
    }


def serialize_story_entity(entity: models.StoryEntity) -> dict[str, Any]:
    return {
        "id": entity.id,
        "project_id": entity.project_id,
        "entity_type": entity.entity_type,
        "name": entity.name,
        "importance_level": entity.importance_level,
        "importance_score": entity.importance_score,
        "description": entity.description,
        "current_status": entity.current_status,
        "first_appearance_chapter_id": entity.first_appearance_chapter_id,
        "last_seen_chapter_id": entity.last_seen_chapter_id,
        "source": entity.source,
        "created_at": isoformat(entity.created_at),
        "updated_at": isoformat(entity.updated_at),
    }


def serialize_world_fact(fact: models.WorldFact) -> dict[str, Any]:
    return {
        "id": fact.id,
        "project_id": fact.project_id,
        "category": fact.category,
        "title": fact.title,
        "content": fact.content,
        "importance_level": fact.importance_level,
        "importance_score": fact.importance_score,
        "confidence": fact.confidence,
        "source_chapter_id": fact.source_chapter_id,
        "related_entity_ids": loads(fact.related_entity_ids_json, []),
        "created_at": isoformat(fact.created_at),
        "updated_at": isoformat(fact.updated_at),
    }


def serialize_graph_node(node: models.GraphNode) -> dict[str, Any]:
    return {
        "id": node.id,
        "project_id": node.project_id,
        "node_type": node.node_type,
        "ref_id": node.ref_id,
        "label": node.label,
        "importance_level": node.importance_level,
        "importance_score": node.importance_score,
        "metadata": loads(node.metadata_json, {}),
        "created_at": isoformat(node.created_at),
        "updated_at": isoformat(node.updated_at),
    }


def serialize_graph_edge(edge: models.GraphEdge) -> dict[str, Any]:
    return {
        "id": edge.id,
        "project_id": edge.project_id,
        "source_node_id": edge.source_node_id,
        "target_node_id": edge.target_node_id,
        "edge_type": edge.edge_type,
        "label": edge.label,
        "importance_score": edge.importance_score,
        "confidence": edge.confidence,
        "evidence": edge.evidence,
        "source_chapter_id": edge.source_chapter_id,
        "metadata": loads(edge.metadata_json, {}),
        "created_at": isoformat(edge.created_at),
        "updated_at": isoformat(edge.updated_at),
    }


def serialize_canon_node(node: models.CanonNode, content: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = {
        "id": node.id,
        "project_id": node.project_id,
        "parent_id": node.parent_id,
        "node_type": node.node_type,
        "ref_type": node.ref_type,
        "ref_id": node.ref_id,
        "title": node.title,
        "sort_order": node.sort_order,
        "status": node.status,
        "importance_level": node.importance_level,
        "activity_status": node.activity_status,
        "metadata": loads(node.metadata_json, {}),
        "created_at": isoformat(node.created_at),
        "updated_at": isoformat(node.updated_at),
    }
    if content is not None:
        payload["content"] = content
    return payload


def serialize_canon_version(version: models.CanonVersion) -> dict[str, Any]:
    return {
        "id": version.id,
        "project_id": version.project_id,
        "ref_type": version.ref_type,
        "ref_id": version.ref_id,
        "version_no": version.version_no,
        "content": loads(version.content_json, {}),
        "source_chapter_id": version.source_chapter_id,
        "source_job_id": version.source_job_id,
        "source_agent": version.source_agent,
        "change_reason": version.change_reason,
        "confidence": version.confidence,
        "created_at": isoformat(version.created_at),
    }


def serialize_canon_proposal(proposal: models.CanonChangeProposal) -> dict[str, Any]:
    return {
        "id": proposal.id,
        "project_id": proposal.project_id,
        "target_type": proposal.target_type,
        "target_id": proposal.target_id,
        "operation": proposal.operation,
        "before": loads(proposal.before_json, {}),
        "after": loads(proposal.after_json, {}),
        "source_chapter_id": proposal.source_chapter_id,
        "source_job_id": proposal.source_job_id,
        "source_agent": proposal.source_agent,
        "approval_status": proposal.approval_status,
        "confidence": proposal.confidence,
        "reason": proposal.reason,
        "created_at": isoformat(proposal.created_at),
        "decided_at": isoformat(proposal.decided_at),
    }


def serialize_agent_run(run: models.AgentRun) -> dict[str, Any]:
    return {
        "id": run.id,
        "job_id": run.job_id,
        "project_id": run.project_id,
        "chapter_id": run.chapter_id,
        "agent_name": run.agent_name,
        "agent_role": run.agent_role,
        "status": run.status,
        "input_payload": loads(run.input_payload_json, {}),
        "output_payload": loads(run.output_payload_json, {}),
        "error_message": run.error_message,
        "langsmith_run_id": getattr(run, "langsmith_run_id", ""),
        "langsmith_url": getattr(run, "langsmith_url", ""),
        "trace_mode": getattr(run, "trace_mode", "local"),
        "started_at": isoformat(run.started_at),
        "finished_at": isoformat(run.finished_at),
        "created_at": isoformat(run.created_at),
    }


def serialize_deep_agent_tool_call(tool_call: models.DeepAgentToolCall) -> dict[str, Any]:
    return {
        "id": tool_call.id,
        "session_id": tool_call.session_id,
        "project_id": tool_call.project_id,
        "tool_name": tool_call.tool_name,
        "status": tool_call.status,
        "risk_level": tool_call.risk_level,
        "requires_approval": bool(tool_call.requires_approval),
        "arguments": loads(tool_call.arguments_json, {}),
        "result": loads(tool_call.result_json, {}),
        "created_at": isoformat(tool_call.created_at),
        "approved_at": isoformat(tool_call.approved_at),
        "rejected_at": isoformat(tool_call.rejected_at),
        "executed_at": isoformat(tool_call.executed_at),
    }


def serialize_deep_agent_session(session: models.DeepAgentSession, tool_calls: list[models.DeepAgentToolCall] | None = None) -> dict[str, Any]:
    state = loads(session.state_json, {})
    if tool_calls is not None:
        state = {**state, "tool_calls": [serialize_deep_agent_tool_call(tool_call) for tool_call in tool_calls]}
    return {
        "id": session.id,
        "project_id": session.project_id,
        "mode": session.mode,
        "status": session.status,
        "objective": session.objective,
        "privacy_mode": session.privacy_mode,
        "summary": session.summary,
        "state": state,
        "created_at": isoformat(session.created_at),
        "updated_at": isoformat(session.updated_at),
    }


def serialize_langsmith_trace_link(link: models.LangSmithTraceLink) -> dict[str, Any]:
    return {
        "id": link.id,
        "project_id": link.project_id,
        "job_id": link.job_id,
        "agent_run_id": link.agent_run_id,
        "session_id": link.session_id,
        "trace_mode": link.trace_mode,
        "langsmith_run_id": link.langsmith_run_id,
        "langsmith_url": link.langsmith_url,
        "payload_policy": link.payload_policy,
        "metadata": loads(link.metadata_json, {}),
        "created_at": isoformat(link.created_at),
    }


def serialize_continuity_issue(issue: models.ContinuityIssue) -> dict[str, Any]:
    return {
        "id": issue.id,
        "project_id": issue.project_id,
        "chapter_id": issue.chapter_id,
        "severity": issue.severity,
        "category": issue.category,
        "message": issue.message,
        "suggestion": issue.suggestion,
        "related_chapter_id": issue.related_chapter_id,
        "status": issue.status,
        "evidence": issue.evidence,
        "created_at": isoformat(issue.created_at),
        "updated_at": isoformat(issue.updated_at),
    }


def serialize_foreshadowing_item(item: models.ForeshadowingItem) -> dict[str, Any]:
    return {
        "id": item.id,
        "project_id": item.project_id,
        "chapter_id": item.chapter_id,
        "content": item.content,
        "planted_chapter_id": item.planted_chapter_id,
        "planned_payoff_chapter_id": item.planned_payoff_chapter_id,
        "actual_payoff_chapter_id": item.actual_payoff_chapter_id,
        "planned_payoff": item.planned_payoff,
        "payoff_status": item.payoff_status,
        "importance_level": item.importance_level,
        "importance_score": item.importance_score,
        "related_character_ids": loads(item.related_character_ids_json, []),
        "related_entity_ids": loads(item.related_entity_ids_json, []),
        "source": item.source,
        "created_at": isoformat(item.created_at),
        "updated_at": isoformat(item.updated_at),
    }


def serialize_version_snapshot(version: models.VersionSnapshot) -> dict[str, Any]:
    return {
        "id": version.id,
        "project_id": version.project_id,
        "chapter_id": version.chapter_id,
        "job_id": version.job_id,
        "agent_name": version.agent_name,
        "content_type": version.content_type,
        "content": version.content,
        "metadata": loads(version.metadata_json, {}),
        "user_note": version.user_note,
        "branch_name": version.branch_name,
        "created_at": isoformat(version.created_at),
    }


def serialize_prompt_template(template: models.PromptTemplate) -> dict[str, Any]:
    return {
        "id": template.id,
        "agent_name": template.agent_name,
        "template_name": template.template_name,
        "prompt": template.prompt,
        "is_active": bool(template.is_active),
        "metadata": loads(template.metadata_json, {}),
        "created_at": isoformat(template.created_at),
        "updated_at": isoformat(template.updated_at),
    }


def serialize_generation_output(output: models.GenerationOutput) -> dict[str, Any]:
    return {
        "id": output.id,
        "project_id": output.project_id,
        "chapter_id": output.chapter_id,
        "job_id": output.job_id,
        "output_type": output.output_type,
        "title": output.title,
        "content": output.content,
        "summary": output.summary,
        "metadata": loads(output.metadata_json, {}),
        "created_at": isoformat(output.created_at),
        "updated_at": isoformat(output.updated_at),
    }


def serialize_export_job(job: models.ExportJob) -> dict[str, Any]:
    return {
        "id": job.id,
        "project_id": job.project_id,
        "format": job.export_format,
        "status": job.status,
        "options": loads(job.options_json, {}),
        "output_path": job.output_path,
        "error_message": job.error_message,
        "created_at": isoformat(job.created_at),
        "finished_at": isoformat(job.finished_at),
    }
