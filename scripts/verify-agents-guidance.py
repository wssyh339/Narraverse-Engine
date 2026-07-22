#!/usr/bin/env python3
"""Validate the repository's layered AGENTS.md instruction contract."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_FILES = {
    Path("AGENTS.md"),
    Path("backend/AGENTS.md"),
    Path("frontend/AGENTS.md"),
    Path("scripts/AGENTS.md"),
    Path("docs/AGENTS.md"),
}
PROBES = {
    Path("."): (Path("AGENTS.md"),),
    Path("backend/app/agents/chapter_writing"): (
        Path("AGENTS.md"),
        Path("backend/AGENTS.md"),
    ),
    Path("frontend/src/pages"): (
        Path("AGENTS.md"),
        Path("frontend/AGENTS.md"),
    ),
    Path("scripts"): (
        Path("AGENTS.md"),
        Path("scripts/AGENTS.md"),
    ),
    Path("docs/adr"): (
        Path("AGENTS.md"),
        Path("docs/AGENTS.md"),
    ),
}
EXPECTED_PREFIXES = {
    Path("AGENTS.md"): "GLOBAL-",
    Path("backend/AGENTS.md"): "BACKEND-",
    Path("frontend/AGENTS.md"): "FRONTEND-",
    Path("scripts/AGENTS.md"): ("OPS-", "TOOLING-"),
    Path("docs/AGENTS.md"): "DOCS-",
}
IGNORED_DIR_NAMES = {
    ".git",
    ".codebase-memory",
    ".ai-context",
    ".pytest_cache",
    "__pycache__",
    "node_modules",
    "dist",
    "data",
    "artifacts",
    "output",
    "outputs",
    "logs",
}
IGNORED_RELATIVE_PREFIXES = (
    "docs/archive/",
    "docs/superpowers/",
    "docs/test-reports/",
)
ROOT_BUDGET_BYTES = 12 * 1024
CHAIN_BUDGET_BYTES = 28 * 1024
CONFIGURED_CAP_BYTES = 64 * 1024
RULE_ID_RE = re.compile(
    r"^##\s+([A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*-\d{3})[：:]",
    re.MULTILINE,
)


def fail(message: str) -> "None":
    raise SystemExit(f"verify-agents-guidance: {message}")


def active_guidance_files() -> set[Path]:
    found: set[Path] = set()
    for current, dirs, files in os.walk(ROOT):
        current_path = Path(current)
        relative_dir = current_path.relative_to(ROOT)
        relative_text = relative_dir.as_posix()
        if relative_text != "." and any(
            f"{relative_text}/".startswith(prefix)
            for prefix in IGNORED_RELATIVE_PREFIXES
        ):
            dirs[:] = []
            continue
        dirs[:] = sorted(name for name in dirs if name not in IGNORED_DIR_NAMES)
        for name in files:
            if name not in {"AGENTS.md", "AGENTS.override.md"}:
                continue
            found.add((current_path / name).relative_to(ROOT))
    return found


def ancestors_from_root(directory: Path) -> list[Path]:
    resolved = (ROOT / directory).resolve()
    try:
        relative = resolved.relative_to(ROOT)
    except ValueError:
        fail(f"probe escapes repository: {directory}")
    paths = [ROOT]
    current = ROOT
    for part in relative.parts:
        current = current / part
        paths.append(current)
    return paths


def discover(directory: Path) -> tuple[Path, ...]:
    chain: list[Path] = []
    for current in ancestors_from_root(directory):
        for name in ("AGENTS.override.md", "AGENTS.md"):
            candidate = current / name
            if candidate.is_file() and candidate.stat().st_size > 0:
                chain.append(candidate.relative_to(ROOT))
                break
    return tuple(chain)


def parse_top_level_config() -> tuple[int, str]:
    config_path = ROOT / ".codex/config.toml"
    text = config_path.read_text(encoding="utf-8")
    top_level = text.split("\n[", 1)[0]
    max_match = re.search(
        r"(?m)^project_doc_max_bytes\s*=\s*(\d+)\s*$",
        top_level,
    )
    fallback_match = re.search(
        r"(?m)^project_doc_fallback_filenames\s*=\s*(\[[^\n]*\])\s*$",
        top_level,
    )
    if max_match is None:
        fail(".codex/config.toml is missing top-level project_doc_max_bytes")
    if fallback_match is None:
        fail(".codex/config.toml is missing project_doc_fallback_filenames")
    return int(max_match.group(1)), fallback_match.group(1).replace(" ", "")


def validate() -> None:
    actual = active_guidance_files()
    overrides = sorted(path for path in actual if path.name == "AGENTS.override.md")
    if overrides:
        fail(f"AGENTS.override.md is not allowed: {overrides}")
    if actual != EXPECTED_FILES:
        missing = sorted(EXPECTED_FILES - actual)
        extra = sorted(actual - EXPECTED_FILES)
        fail(f"guidance file set drifted; missing={missing}, extra={extra}")

    root_bytes = (ROOT / "AGENTS.md").stat().st_size
    if root_bytes > ROOT_BUDGET_BYTES:
        fail(
            f"root AGENTS.md is {root_bytes} bytes; budget is {ROOT_BUDGET_BYTES}"
        )

    root_text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    for scoped in sorted(EXPECTED_FILES - {Path("AGENTS.md")}):
        if scoped.as_posix() not in root_text:
            fail(f"root routing table does not mention {scoped}")

    for probe, expected in PROBES.items():
        if not (ROOT / probe).is_dir():
            fail(f"probe directory does not exist: {probe}")
        actual_chain = discover(probe)
        if actual_chain != expected:
            fail(
                f"discovery mismatch for {probe}: "
                f"expected={expected}, actual={actual_chain}"
            )
        chain_bytes = sum((ROOT / item).stat().st_size for item in actual_chain)
        chain_bytes += 2 * max(0, len(actual_chain) - 1)
        if chain_bytes > CHAIN_BUDGET_BYTES:
            fail(
                f"instruction chain for {probe} is {chain_bytes} bytes; "
                f"portable budget is {CHAIN_BUDGET_BYTES}"
            )

    owners: dict[str, Path] = {}
    for relative in sorted(EXPECTED_FILES):
        text = (ROOT / relative).read_text(encoding="utf-8")
        ids = RULE_ID_RE.findall(text)
        if not ids:
            fail(f"{relative} has no stable rule IDs")
        expected_prefixes = EXPECTED_PREFIXES[relative]
        if isinstance(expected_prefixes, str):
            expected_prefixes = (expected_prefixes,)
        if not any(rule_id.startswith(expected_prefixes) for rule_id in ids):
            fail(f"{relative} has no rule ID owned by {expected_prefixes}")
        for rule_id in ids:
            previous = owners.get(rule_id)
            if previous is not None:
                fail(f"duplicate rule ID {rule_id}: {previous} and {relative}")
            owners[rule_id] = relative

    configured_cap, fallbacks = parse_top_level_config()
    if configured_cap != CONFIGURED_CAP_BYTES:
        fail(
            "project_doc_max_bytes must be 65536; "
            f"found {configured_cap}"
        )
    if fallbacks != "[]":
        fail("project_doc_fallback_filenames must be an explicit empty list")

    print(
        "Layered AGENTS guidance: OK "
        f"({len(EXPECTED_FILES)} files, {len(owners)} rule IDs, "
        f"largest portable chain <= {CHAIN_BUDGET_BYTES} bytes)"
    )


def validate_runtime() -> None:
    codex = shutil.which("codex")
    if codex is None:
        fail("--runtime requires codex on PATH")

    prefix = "# AGENTS.md instructions for "
    opening = "\n\n<INSTRUCTIONS>\n"
    closing = "\n</INSTRUCTIONS>"
    for probe, expected_paths in PROBES.items():
        cwd = (ROOT / probe).resolve()
        completed = subprocess.run(
            [codex, "debug", "prompt-input", "AGENTS_RUNTIME_PROBE"],
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
            errors="strict",
            timeout=30,
            check=False,
        )
        if completed.returncode != 0:
            fail(
                f"codex runtime probe failed for {probe}: "
                f"{completed.stderr.strip()}"
            )
        try:
            items = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            fail(f"codex runtime probe returned invalid JSON for {probe}: {exc}")
        if not isinstance(items, list):
            fail(f"codex runtime probe did not return a JSON array for {probe}")

        matches: list[str] = []
        for item in items:
            content = item.get("content", []) if isinstance(item, dict) else []
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict) or block.get("type") != "input_text":
                    continue
                value = block.get("text")
                if isinstance(value, str) and value.startswith(prefix):
                    matches.append(value)
        if len(matches) != 1:
            fail(
                f"expected one project instruction message for {probe}; "
                f"found {len(matches)}"
            )

        header, separator, tail = matches[0].partition(opening)
        if not separator or not tail.endswith(closing):
            fail(f"unexpected Codex instruction wrapper for {probe}")
        loaded_cwd = Path(header[len(prefix) :]).resolve()
        if loaded_cwd != cwd:
            fail(f"Codex runtime cwd mismatch: {loaded_cwd} != {cwd}")
        actual = tail[: -len(closing)]
        expected = "\n\n".join(
            (ROOT / relative).read_bytes().decode("utf-8")
            for relative in expected_paths
        )
        if actual != expected:
            fail(f"runtime instruction chain differs or was truncated for {probe}")
        print(
            f"Codex runtime chain {probe}: OK "
            f"({len(actual.encode('utf-8'))} bytes)"
        )


if __name__ == "__main__":
    if sys.argv[1:] not in ([], ["--runtime"]):
        fail("usage: python3 scripts/verify-agents-guidance.py [--runtime]")
    validate()
    if sys.argv[1:] == ["--runtime"]:
        validate_runtime()
