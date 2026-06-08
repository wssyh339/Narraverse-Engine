from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_api_router_is_split_by_domain() -> None:
    router = read("backend/app/api/v1/router.py")
    endpoint_dir = ROOT / "backend/app/api/v1/endpoints"
    expected_modules = [
        "agents.py",
        "canon.py",
        "exporting.py",
        "foreshadowing.py",
        "knowledge.py",
        "project_studio.py",
        "tools.py",
        "versions.py",
        "websockets.py",
        "writing.py",
    ]

    for module_name in expected_modules:
        assert (endpoint_dir / module_name).exists(), f"missing endpoint module: {module_name}"
        assert module_name.removesuffix(".py") in router

    assert " studio" not in router


def test_large_studio_facade_is_documented_as_legacy_compatibility() -> None:
    legacy_studio = ROOT / "backend/app/api/v1/endpoints/studio.py"
    assert legacy_studio.exists()
    source = legacy_studio.read_text(encoding="utf-8")
    assert "legacy compatibility" in source
