from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN = ["龙骨能源", "最后真龙封印", "帝国能源署", "龙骨矿区", "最后龙裔矿工"]


def test_outline_swarm_does_not_hardcode_sample_story_content() -> None:
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / "backend/app/agents/outline_swarm").glob("**/*.py")
    )
    for forbidden in FORBIDDEN:
        assert forbidden not in source
