from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.agents.outline_models import ProjectConfig, StoryKernel, StoryState
from app.agents.outline_storage import DEFAULT_EXPORT_DIR, DEFAULT_STATE_PATH, load_story_state, save_markdown_exports, save_story_state
from app.agents.outline_workflow import NovelWorkflow
from app.db.session import Base, SessionLocal, engine
from app.db import models
from app.schemas.chapter import PlanChaptersRequest
from app.schemas.project import CreateProjectRequest
from app.schemas.studio import BatchGenerateRequest, DraftChapterRequest, ExportRequest, QueryKnowledgeRequest
from app.services.canon_service import run_canon_from_file
from app.services.project_service import project_service
from app.services.studio_service import studio_service


def _print(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _latest_project(db):
    return db.query(models.Project).order_by(models.Project.updated_at.desc()).first()


def _outline_workflow_from_state(state: StoryState) -> NovelWorkflow:
    workflow = NovelWorkflow(
        config=state.config,
        raw_worldview=state.raw_worldview,
        one_sentence_story=state.kernel.one_sentence_story,
    )
    workflow.state = state
    return workflow


def main() -> None:
    parser = argparse.ArgumentParser(description="长篇小说撰写 Agent Studio CLI")
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init")
    init.add_argument("--name", default="长篇推演项目")
    init.add_argument("--genre", default="都市脑洞")
    init.add_argument("--tone", default="搞笑腹黑")
    init.add_argument("--target-words", type=int, default=1000000)
    init.add_argument("--target-volumes", type=int, default=10)
    init.add_argument("--chapters-per-volume", type=int, default=50)
    init.add_argument("--words-per-chapter", type=int, default=2000)
    set_input = sub.add_parser("set-input")
    set_input.add_argument("--worldview", default="")
    set_input.add_argument("--story", required=True)
    sub.add_parser("run-full")
    run_stage = sub.add_parser("run-stage")
    run_stage.add_argument("stage")
    run_volume = sub.add_parser("run-volume")
    run_volume.add_argument("volume_number", type=int)
    sub.add_parser("audit")
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
    plan = sub.add_parser("plan")
    plan.add_argument("--count", type=int, default=3)
    gen = sub.add_parser("generate-chapter")
    gen.add_argument("--chapter-no", type=int, default=1)
    sub.add_parser("batch-generate")
    exp = sub.add_parser("export")
    exp.add_argument("--format", default="markdown")
    exp.add_argument("--outline", action="store_true")
    exp.add_argument("--out-dir", default=str(DEFAULT_EXPORT_DIR))
    canon_run = sub.add_parser("canon-run")
    canon_run.add_argument("--input", required=True)
    canon_run.add_argument("--output", required=True)
    args = parser.parse_args()

    if args.command == "canon-run":
        result = run_canon_from_file(Path(args.input), Path(args.output))
        _print(
            {
                "final_outline.md": result.final_outline_path,
                "canon_store.json": result.canon_store_path,
                "trace_store.json": result.trace_store_path,
                "continuity_report": result.continuity_report,
            }
        )
        return

    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        if args.command == "init":
            state = StoryState(
                config=ProjectConfig(
                    project_name=args.name,
                    genre=args.genre,
                    tone=args.tone,
                    target_words=args.target_words,
                    target_volumes=args.target_volumes,
                    chapters_per_volume=args.chapters_per_volume,
                    words_per_chapter=args.words_per_chapter,
                )
            )
            path = save_story_state(state, DEFAULT_STATE_PATH)
            _print({"story_state_path": str(path), "state": state.model_dump(mode="json")})
            return

        if args.command == "set-input":
            state = load_story_state(DEFAULT_STATE_PATH)
            worldview_path = Path(args.worldview) if args.worldview else None
            state.raw_worldview = worldview_path.read_text(encoding="utf-8") if worldview_path and worldview_path.exists() else args.worldview
            state.kernel = StoryKernel(one_sentence_story=args.story)
            path = save_story_state(state, DEFAULT_STATE_PATH)
            _print({"story_state_path": str(path), "state": state.model_dump(mode="json")})
            return

        if args.command == "run-full":
            workflow = _outline_workflow_from_state(load_story_state(DEFAULT_STATE_PATH))
            state = workflow.run_full_pipeline()
            path = save_story_state(state, DEFAULT_STATE_PATH)
            _print({"story_state_path": str(path), "current_stage": state.current_stage, "volumes": len(state.volumes)})
            return

        if args.command == "run-stage":
            workflow = _outline_workflow_from_state(load_story_state(DEFAULT_STATE_PATH))
            state = workflow.run_until_stage(args.stage)
            path = save_story_state(state, DEFAULT_STATE_PATH)
            _print({"story_state_path": str(path), "current_stage": state.current_stage})
            return

        if args.command == "run-volume":
            workflow = _outline_workflow_from_state(load_story_state(DEFAULT_STATE_PATH))
            volume = workflow.run_volume(args.volume_number)
            path = save_story_state(workflow.state, DEFAULT_STATE_PATH)
            _print({"story_state_path": str(path), "volume": volume.model_dump(mode="json")})
            return

        if args.command == "audit":
            workflow = _outline_workflow_from_state(load_story_state(DEFAULT_STATE_PATH))
            report = workflow.audit_current_state()
            path = save_story_state(workflow.state, DEFAULT_STATE_PATH)
            _print({"story_state_path": str(path), "audit_report": report.model_dump(mode="json")})
            return

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
                        chapter_word_target=2500,
                    ),
                )
            )
            return

        project = _latest_project(db)
        if args.command == "export" and (args.outline or project is None) and DEFAULT_STATE_PATH.exists():
            state = load_story_state(DEFAULT_STATE_PATH)
            exported = save_markdown_exports(state, args.out_dir)
            _print({"exported": [str(path) for path in exported]})
            return
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
        elif args.command == "plan":
            _print(
                studio_service.plan_chapters(
                    db,
                    project.id,
                    PlanChaptersRequest(
                        volume_title="CLI 自动规划",
                        start_chapter_no=1,
                        chapter_count=args.count,
                        outline_requirement="按当前故事圣经规划可写章节。",
                        overwrite_existing=True,
                        idempotency_key=f"cli-plan:{project.id}:{args.count}",
                    ),
                )
            )
        elif args.command == "generate-chapter":
            chapter = db.query(models.Chapter).filter_by(project_id=project.id, chapter_no=args.chapter_no).first()
            if chapter is None:
                raise SystemExit("章节不存在，请先运行 python main.py plan")
            _print(studio_service.draft_chapter(db, project.id, chapter.id, DraftChapterRequest(user_instruction="CLI 生成章节")))
        elif args.command == "batch-generate":
            _print(studio_service.batch_generate(db, BatchGenerateRequest(project_id=project.id, chapter_start=1, chapter_end=3)))
        elif args.command == "export":
            _print(studio_service.export(db, ExportRequest(project_id=project.id, format=args.format)))


if __name__ == "__main__":
    main()
