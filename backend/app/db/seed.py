from app.core.ids import generate_id
from app.core.json import dumps
from app.db import models
from app.db.session import Base, SessionLocal, engine


SEED_PROJECTS = [
    {
        "title": "星海遗民",
        "genre": "科幻",
        "target_reader": "喜欢群像、文明冲突和长期伏笔的中文网文读者",
        "premise": "一名失忆舰长在废弃星门中醒来，发现自己可能是旧帝国覆灭的关键责任人。",
        "style_guide": "第三人称有限视角，节奏偏紧。",
        "planned_chapter_count": 80,
        "chapter_word_target": 3000,
    },
    {
        "title": "雾港来信",
        "genre": "悬疑",
        "target_reader": "喜欢慢热调查和人物秘密的读者",
        "premise": "记者收到一封来自十年前死者的信。",
        "style_guide": "冷静、克制，避免过度煽情。",
        "planned_chapter_count": 40,
        "chapter_word_target": 2500,
    },
    {
        "title": "山河旧誓",
        "genre": "历史",
        "target_reader": "喜欢权谋和群像的读者",
        "premise": "失势女官重回朝堂，调查旧案。",
        "style_guide": "古雅但不堆砌。",
        "planned_chapter_count": 60,
        "chapter_word_target": 2800,
    },
]


def seed_database() -> int:
    Base.metadata.create_all(bind=engine)
    created = 0
    with SessionLocal() as db:
        for item in SEED_PROJECTS:
            exists = db.query(models.Project).filter(models.Project.title == item["title"]).first()
            if exists:
                continue
            project = models.Project(
                id=generate_id("prj"),
                title=item["title"],
                genre=item["genre"],
                target_reader=item["target_reader"],
                premise=item["premise"],
                style_guide=item["style_guide"],
                language="zh-CN",
                planned_chapter_count=item["planned_chapter_count"],
                chapter_word_target=item["chapter_word_target"],
                status="draft",
            )
            db.add(project)
            db.add(
                models.StoryBible(
                    id=generate_id("bib"),
                    project_id=project.id,
                    version=1,
                    world_setting="",
                    main_conflict="",
                    themes_json=dumps([]),
                    style_guide=item["style_guide"],
                    narrative_pov="third_person_limited",
                    forbidden_elements_json=dumps([]),
                    continuity_rules_json=dumps([]),
                )
            )
            created += 1
        db.commit()
    return created


if __name__ == "__main__":
    count = seed_database()
    print(f"seeded_projects={count}")
