from __future__ import annotations

from functools import lru_cache
from pathlib import Path


PROMPT_DIR = Path(__file__).resolve().parents[1] / "prompts"


@lru_cache(maxsize=64)
def load_prompt(name: str) -> str:
    path = PROMPT_DIR / f"{name}.md"
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def list_prompts() -> dict[str, str]:
    if not PROMPT_DIR.exists():
        return {}
    return {path.stem: path.read_text(encoding="utf-8") for path in sorted(PROMPT_DIR.glob("*.md"))}
