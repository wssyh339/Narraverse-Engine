from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.ids import generate_id
from app.core.json import dumps, loads
from app.db import models
from app.schemas.project import CreateProjectRequest
from app.schemas.studio import UpdateProjectRequest
from app.schemas.story_bible import UpdateStoryBibleRequest
from app.services.serializers import serialize_project, serialize_story_bible


def _not_found(message: str) -> HTTPException:
    return HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": message})


class ProjectService:
    def create_project(self, db: Session, request: CreateProjectRequest) -> dict:
        target_words = request.target_words or request.planned_chapter_count * request.chapter_word_target
        project = models.Project(
            id=generate_id("prj"),
            title=request.title,
            genre=request.genre,
            target_reader=request.target_reader,
            premise=request.premise,
            style_guide=request.style_guide,
            language=request.language,
            planned_chapter_count=request.planned_chapter_count,
            chapter_word_target=request.chapter_word_target,
            target_words=target_words,
            current_volume=request.current_volume,
            current_chapter=request.current_chapter,
            cover_image=request.cover_image,
            initial_idea=request.initial_idea or request.premise,
            status="draft",
        )
        story_bible = models.StoryBible(
            id=generate_id("bib"),
            project_id=project.id,
            version=1,
            world_setting="",
            main_conflict="",
            themes_json=dumps([]),
            style_guide=request.style_guide,
            narrative_pov="third_person_limited",
            forbidden_elements_json=dumps([]),
            continuity_rules_json=dumps([]),
        )
        db.add(project)
        db.flush()
        db.add(story_bible)
        db.add(models.Volume(id=generate_id("vol"), project_id=project.id, volume_no=1, title="第一卷", sort_order=1))
        self._seed_project_canon(db, project)
        db.commit()
        db.refresh(project)
        db.refresh(story_bible)
        return {
            "project": serialize_project(project),
            "story_bible": serialize_story_bible(story_bible, include_style_guide=False),
        }

    def list_projects(self, db: Session) -> dict:
        projects = db.query(models.Project).order_by(models.Project.updated_at.desc()).all()
        return {
            "projects": [serialize_project(project) for project in projects],
            "stats": {
                "project_count": len(projects),
                "active_count": len([project for project in projects if project.status != "archived"]),
                "target_words": sum(project.target_words or project.planned_chapter_count * project.chapter_word_target for project in projects),
            },
        }

    def get_project(self, db: Session, project_id: str) -> dict:
        project = db.get(models.Project, project_id)
        if project is None:
            raise _not_found("项目不存在")
        story_bible = db.query(models.StoryBible).filter(models.StoryBible.project_id == project_id).first()
        chapters = (
            db.query(models.Chapter)
            .filter(models.Chapter.project_id == project_id)
            .order_by(models.Chapter.chapter_no.asc())
            .all()
        )
        return {
            "project": serialize_project(project),
            "story_bible": serialize_story_bible(story_bible) if story_bible else None,
            "chapter_count": len(chapters),
            "completed_chapter_count": len([chapter for chapter in chapters if chapter.status in {"completed", "drafted"}]),
        }

    def update_project(self, db: Session, project_id: str, request: UpdateProjectRequest) -> dict:
        project = db.get(models.Project, project_id)
        if project is None:
            raise _not_found("项目不存在")
        updates = request.model_dump(exclude_unset=True)
        for field, value in updates.items():
            if value is not None and hasattr(project, field):
                setattr(project, field, value)
        if "planned_chapter_count" in updates or "chapter_word_target" in updates:
            project.target_words = project.planned_chapter_count * project.chapter_word_target
        db.commit()
        db.refresh(project)
        return {"project": serialize_project(project)}

    def delete_project(self, db: Session, project_id: str) -> dict:
        project = db.get(models.Project, project_id)
        if project is None:
            raise _not_found("项目不存在")
        job_ids = [row.id for row in db.query(models.GenerationJob.id).filter(models.GenerationJob.project_id == project_id).all()]
        run_ids = [row.id for row in db.query(models.AgentRun.id).filter(models.AgentRun.project_id == project_id).all()]
        report_ids = [row.id for row in db.query(models.QualityReport.id).filter(models.QualityReport.project_id == project_id).all()]
        if run_ids:
            db.query(models.AgentMessage).filter(models.AgentMessage.agent_run_id.in_(run_ids)).delete(synchronize_session=False)
        if report_ids:
            db.query(models.QualityIssue).filter(models.QualityIssue.report_id.in_(report_ids)).delete(synchronize_session=False)
        if job_ids:
            db.query(models.ModelCall).filter(models.ModelCall.job_id.in_(job_ids)).delete(synchronize_session=False)
            db.query(models.JobArtifact).filter(models.JobArtifact.job_id.in_(job_ids)).delete(synchronize_session=False)
        for model in [
            models.UserFeedback,
            models.ExportJob,
            models.EditorProposal,
            models.VersionSnapshot,
            models.StyleProfile,
            models.Note,
            models.Volume,
            models.ForeshadowingItem,
            models.GraphEdge,
            models.GraphNode,
            models.ContinuityIssue,
            models.WorldFact,
            models.StoryEntity,
            models.GenerationOutput,
            models.AgentRun,
            models.GenerationJob,
            models.StoryStateSnapshot,
            models.QualityReport,
            models.ContextPackage,
            models.ChapterIntent,
            models.EventLog,
            models.MemoryChunk,
            models.Chapter,
            models.Character,
            models.StoryBible,
        ]:
            db.query(model).filter(model.project_id == project_id).delete(synchronize_session=False)
        serialized = serialize_project(project)
        db.delete(project)
        db.commit()
        return {"project": serialized, "project_id": project_id, "deleted": True}

    def duplicate_project(self, db: Session, project_id: str) -> dict:
        project = db.get(models.Project, project_id)
        if project is None:
            raise _not_found("项目不存在")
        story_bible = db.query(models.StoryBible).filter(models.StoryBible.project_id == project_id).first()
        clone = models.Project(
            id=generate_id("prj"),
            title=f"{project.title} 副本",
            genre=project.genre,
            target_reader=project.target_reader,
            premise=project.premise,
            style_guide=project.style_guide,
            language=project.language,
            planned_chapter_count=project.planned_chapter_count,
            chapter_word_target=project.chapter_word_target,
            target_words=project.target_words,
            initial_idea=project.initial_idea,
            status="draft",
        )
        db.add(clone)
        db.flush()
        db.add(
            models.StoryBible(
                id=generate_id("bib"),
                project_id=clone.id,
                version=story_bible.version if story_bible else 1,
                world_setting=story_bible.world_setting if story_bible else "",
                main_conflict=story_bible.main_conflict if story_bible else "",
                themes_json=story_bible.themes_json if story_bible else dumps([]),
                style_guide=story_bible.style_guide if story_bible else project.style_guide,
                narrative_pov=story_bible.narrative_pov if story_bible else "third_person_limited",
                forbidden_elements_json=story_bible.forbidden_elements_json if story_bible else dumps([]),
                continuity_rules_json=story_bible.continuity_rules_json if story_bible else dumps([]),
            )
        )
        db.commit()
        db.refresh(clone)
        return self.get_project(db, clone.id)

    def update_story_bible(self, db: Session, project_id: str, request: UpdateStoryBibleRequest) -> dict:
        story_bible = db.query(models.StoryBible).filter(models.StoryBible.project_id == project_id).first()
        if story_bible is None:
            raise _not_found("项目或故事圣经不存在")

        story_bible.version += 1
        story_bible.world_setting = request.world_setting
        story_bible.main_conflict = request.main_conflict
        story_bible.themes_json = dumps(request.themes)
        story_bible.style_guide = request.style_guide
        story_bible.narrative_pov = request.narrative_pov
        story_bible.forbidden_elements_json = dumps(request.forbidden_elements)
        story_bible.continuity_rules_json = dumps(request.continuity_rules)
        db.commit()
        db.refresh(story_bible)
        return {"story_bible": serialize_story_bible(story_bible, include_style_guide=True)}

    def get_story_bible(self, db: Session, project_id: str) -> dict:
        story_bible = db.query(models.StoryBible).filter(models.StoryBible.project_id == project_id).first()
        if story_bible is None:
            raise _not_found("项目或故事圣经不存在")
        return {"story_bible": serialize_story_bible(story_bible)}

    def get_state(self, db: Session, project_id: str) -> dict:
        from app.services.serializers import (
            serialize_chapter,
            serialize_character,
            serialize_continuity_issue,
            serialize_foreshadowing_item,
            serialize_graph_edge,
            serialize_graph_node,
            serialize_story_entity,
            serialize_world_fact,
        )

        project = db.get(models.Project, project_id)
        if project is None:
            raise _not_found("项目不存在")
        story_bible = db.query(models.StoryBible).filter(models.StoryBible.project_id == project_id).first()
        return {
            "state": {
                "project": serialize_project(project),
                "story_bible": serialize_story_bible(story_bible) if story_bible else None,
                "characters": [serialize_character(item) for item in db.query(models.Character).filter(models.Character.project_id == project_id).all()],
                "chapters": [
                    serialize_chapter(item)
                    for item in db.query(models.Chapter)
                    .filter(models.Chapter.project_id == project_id, models.Chapter.deleted_at.is_(None))
                    .order_by(models.Chapter.sort_order.asc(), models.Chapter.chapter_no.asc())
                    .all()
                ],
                "story_entities": [serialize_story_entity(item) for item in db.query(models.StoryEntity).filter(models.StoryEntity.project_id == project_id).all()],
                "world_facts": [serialize_world_fact(item) for item in db.query(models.WorldFact).filter(models.WorldFact.project_id == project_id).all()],
                "graph": {
                    "nodes": [serialize_graph_node(item) for item in db.query(models.GraphNode).filter(models.GraphNode.project_id == project_id).all()],
                    "edges": [serialize_graph_edge(item) for item in db.query(models.GraphEdge).filter(models.GraphEdge.project_id == project_id).all()],
                },
                "continuity_issues": [serialize_continuity_issue(item) for item in db.query(models.ContinuityIssue).filter(models.ContinuityIssue.project_id == project_id).all()],
                "foreshadowing_items": [
                    serialize_foreshadowing_item(item)
                    for item in db.query(models.ForeshadowingItem)
                    .filter(models.ForeshadowingItem.project_id == project_id)
                    .order_by(models.ForeshadowingItem.importance_score.desc())
                    .all()
                ],
            }
        }

    def put_state(self, db: Session, project_id: str, payload: dict) -> dict:
        project = db.get(models.Project, project_id)
        if project is None:
            raise _not_found("项目不存在")
        if "project" in payload and isinstance(payload["project"], dict):
            self.update_project(db, project_id, UpdateProjectRequest(**payload["project"]))
        if "story_bible" in payload and isinstance(payload["story_bible"], dict):
            self.update_story_bible(db, project_id, UpdateStoryBibleRequest(**payload["story_bible"]))
        return self.get_state(db, project_id)

    def _seed_project_canon(self, db: Session, project: models.Project) -> None:
        protagonist = models.Character(
            id=generate_id("chr"),
            project_id=project.id,
            name="待定主角",
            role="主角",
            role_type="protagonist",
            importance_level="core",
            importance_score=95,
            summary=f"围绕「{project.premise}」展开成长的核心人物。",
            profile=f"目标读者：{project.target_reader}",
            goals_json=dumps(["寻找主线答案", "完成个人成长"]),
            motivations_json=dumps(["被初始事件推入冲突"]),
            character_arc="从被动卷入到主动选择承担代价。",
            updated_reason="项目创建时自动初始化核心角色卡。",
            source="project_seed",
        )
        entity = models.StoryEntity(
            id=generate_id("ent"),
            project_id=project.id,
            entity_type="concept",
            name=project.genre,
            importance_level="major",
            importance_score=70,
            description=f"项目题材与叙事承诺：{project.genre}",
            source="project_seed",
        )
        fact = models.WorldFact(
            id=generate_id("wld"),
            project_id=project.id,
            category="culture",
            title="创作前提",
            content=project.premise,
            importance_level="core",
            importance_score=90,
            confidence=1.0,
        )
        db.add_all([protagonist, entity, fact])
        char_node = models.GraphNode(
            id=generate_id("gnd"),
            project_id=project.id,
            node_type="character",
            ref_id=protagonist.id,
            label=protagonist.name,
            importance_level=protagonist.importance_level,
            importance_score=protagonist.importance_score,
        )
        entity_node = models.GraphNode(
            id=generate_id("gnd"),
            project_id=project.id,
            node_type="entity",
            ref_id=entity.id,
            label=entity.name,
            importance_level=entity.importance_level,
            importance_score=entity.importance_score,
        )
        fact_node = models.GraphNode(
            id=generate_id("gnd"),
            project_id=project.id,
            node_type="world_fact",
            ref_id=fact.id,
            label=fact.title,
            importance_level=fact.importance_level,
            importance_score=fact.importance_score,
        )
        db.add_all([char_node, entity_node, fact_node])
        db.flush()
        db.add_all(
            [
                models.GraphEdge(
                    id=generate_id("ged"),
                    project_id=project.id,
                    source_node_id=char_node.id,
                    target_node_id=fact_node.id,
                    edge_type="driven_by",
                    label="被创作前提驱动",
                    importance_score=85,
                    confidence=1.0,
                    evidence=project.premise,
                ),
                models.GraphEdge(
                    id=generate_id("ged"),
                    project_id=project.id,
                    source_node_id=fact_node.id,
                    target_node_id=entity_node.id,
                    edge_type="defines",
                    label="定义题材承诺",
                    importance_score=70,
                    confidence=1.0,
                    evidence=project.genre,
                ),
            ]
        )


project_service = ProjectService()
