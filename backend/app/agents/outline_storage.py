from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.agents.outline_models import StoryState


DEFAULT_STATE_PATH = Path("./workspace/story_state.json")
DEFAULT_EXPORT_DIR = Path("./workspace/exports")


def save_story_state(state: StoryState, path: str | Path = DEFAULT_STATE_PATH) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(state.model_dump(mode="json"), ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def load_story_state(path: str | Path = DEFAULT_STATE_PATH) -> StoryState:
    source = Path(path)
    return StoryState.model_validate(json.loads(source.read_text(encoding="utf-8")))


def append_revision_history(state: StoryState, entry: dict[str, Any]) -> StoryState:
    state.revision_history.append(entry)
    return state


def _markdown(title: str, payload: Any) -> str:
    body = json.dumps(payload, ensure_ascii=False, indent=2)
    return f"# {title}\n\n```json\n{body}\n```\n"


def save_markdown_exports(state: StoryState, export_dir: str | Path = DEFAULT_EXPORT_DIR) -> list[Path]:
    target = Path(export_dir)
    target.mkdir(parents=True, exist_ok=True)
    exports: list[tuple[str, str, Any]] = [
        ("01_故事核心.md", "故事核心", state.kernel.model_dump(mode="json")),
        ("02_类型卖点定位.md", "类型卖点定位", state.market_position),
        ("03_世界圣经.md", "世界圣经", state.world_bible.model_dump(mode="json")),
        ("04_主角成长线.md", "主角成长线", [item.model_dump(mode="json") for item in state.protagonist_arcs]),
        ("05_人物树.md", "人物树", [item.model_dump(mode="json") for item in state.characters]),
        ("06_势力冲突表.md", "势力冲突表", state.faction_conflicts),
        ("07_金手指升级体系.md", "金手指升级体系", state.power_progression),
        ("08_全书10卷总纲.md", "全书10卷总纲", state.full_structure),
        ("09_逐卷50章大纲.md", "逐卷50章大纲", [item.model_dump(mode="json") for item in state.volumes]),
        ("10_章节节拍表.md", "章节节拍表", [item.model_dump(mode="json") for item in state.beat_sheets]),
        ("11_伏笔账本.md", "伏笔账本", [item.model_dump(mode="json") for item in state.foreshadowing_ledger]),
        ("12_逻辑审计报告.md", "逻辑审计报告", [item.model_dump(mode="json") for item in state.audit_reports]),
        ("13_最终修订版纲要.md", "最终修订版纲要", state.model_dump(mode="json")),
    ]
    written: list[Path] = []
    for filename, title, payload in exports:
        path = target / filename
        path.write_text(_markdown(title, payload), encoding="utf-8")
        written.append(path)
    return written
