from __future__ import annotations

import argparse
import json

from app.db.session import Base, SessionLocal, engine
from app.db import models
from app.schemas.project import CreateProjectRequest
from app.schemas.studio import BatchGenerateRequest, DraftChapterRequest, ExportRequest, QueryKnowledgeRequest
from app.services.project_service import project_service
from app.services.studio_service import studio_service


def _print(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _latest_project(db):
    return db.query(models.Project).order_by(models.Project.updated_at.desc()).first()


DEFAULT_CHAPTER_WORD_TARGET = 8000


def main() -> None:
    parser = argparse.ArgumentParser(description="叙界推演引擎 / Narraverse Engine CLI")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("resume")
    sub.add_parser("versions")
    sub.add_parser("config")
    sub.add_parser("character_map")
    q = sub.add_parser("query")
    q.add_argument("question", nargs="?", default="当前有哪些核心角色？")
    new = sub.add_parser("new")
    new.add_argument("--title", default="CLI 新项目")
    new.add_argument("--genre", default="奇幻")
    new.add_argument("--premise", default="一个普通人在旧秩序崩塌时发现自己与核心秘密有关。")
    gen = sub.add_parser("generate-chapter")
    gen.add_argument("--chapter-no", type=int, default=1)
    sub.add_parser("batch-generate")
    exp = sub.add_parser("export")
    exp.add_argument("--format", default="markdown")
    args = parser.parse_args()

    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        if args.command == "new":
            _print(
                project_service.create_project(
                    db,
                    CreateProjectRequest(
                        title=args.title,
                        genre=args.genre,
                        target_reader="CLI 用户",
                        premise=args.premise,
                        planned_chapter_count=30,
                        chapter_word_target=DEFAULT_CHAPTER_WORD_TARGET,
                    ),
                )
            )
            return

        project = _latest_project(db)
        if project is None:
            raise SystemExit("还没有项目，请先运行 python main.py new")

        if args.command == "resume":
            _print(project_service.get_state(db, project.id))
        elif args.command == "versions":
            _print(studio_service.list_versions(db))
        elif args.command == "config":
            _print(studio_service.list_agents(db))
        elif args.command == "character_map":
            _print(studio_service.get_graph(db, project.id))
        elif args.command == "query":
            _print(studio_service.query_knowledge(db, QueryKnowledgeRequest(project_id=project.id, question=args.question)))
        elif args.command == "generate-chapter":
            chapter = db.query(models.Chapter).filter_by(project_id=project.id, chapter_no=args.chapter_no).first()
            if chapter is None:
                raise SystemExit("章节不存在，请先在大纲议事中确认章纲，或通过工作台手动创建章节")
            _print(studio_service.draft_chapter(db, project.id, chapter.id, DraftChapterRequest(user_instruction="CLI 生成章节")))
        elif args.command == "batch-generate":
            _print(studio_service.batch_generate(db, BatchGenerateRequest(project_id=project.id, chapter_start=1, chapter_end=3)))
        elif args.command == "export":
            _print(studio_service.export(db, ExportRequest(project_id=project.id, format=args.format)))


if __name__ == "__main__":
    main()
