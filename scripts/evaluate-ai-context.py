#!/usr/bin/env python3
"""Run an offline, deterministic coverage evaluation for AI context profiles."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Set


def load_input_helper(script_dir: Path) -> Any:
    helper_path = script_dir / "ai-context-inputs.py"
    spec = importlib.util.spec_from_file_location("narraverse_ai_context_inputs", helper_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {helper_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def require_list(value: Any, label: str) -> List[Any]:
    if not isinstance(value, list):
        raise RuntimeError(f"{label} must be an array")
    return value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--json", action="store_true", dest="as_json")
    return parser.parse_args()


def main() -> None:
    arguments = parse_args()
    root = Path(arguments.repo_root).expanduser().resolve()
    script_dir = Path(__file__).resolve().parent
    helper = load_input_helper(script_dir)
    root = helper.ensure_repository(root)
    profile_config = script_dir / "ai-context-profiles.json"
    eval_path = script_dir / "ai-context-eval.json"
    try:
        evaluation = json.loads(eval_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"ai-context-eval: invalid evaluation file: {exc}") from exc
    if evaluation.get("$schema") != "narraverse.ai-context-eval.v1":
        raise SystemExit("ai-context-eval: unsupported evaluation schema")

    scenarios = require_list(evaluation.get("scenarios"), "scenarios")
    profiles = sorted(
        {
            item.get("profile")
            for item in scenarios
            if isinstance(item, dict) and isinstance(item.get("profile"), str)
        }
    )
    inventories: Dict[str, Mapping[str, Any]] = {}
    selected_paths: Dict[str, Set[str]] = {}
    for profile in profiles:
        manifest = helper.build_inventory(
            root,
            root / ".repomixignore",
            [],
            profile_config,
            profile,
        )
        inventories[profile] = manifest
        selected_paths[profile] = {item["path"] for item in manifest["files"]}

    failures: List[str] = []
    results: List[Dict[str, Any]] = []
    forbidden = require_list(evaluation.get("forbidden_paths", []), "forbidden_paths")
    for profile in profiles:
        leaked = sorted(set(forbidden).intersection(selected_paths[profile]))
        if leaked:
            failures.append(f"profile {profile} selected forbidden paths: {leaked}")

    seen_ids: Set[str] = set()
    for scenario in scenarios:
        if not isinstance(scenario, dict):
            raise SystemExit("ai-context-eval: scenario must be an object")
        scenario_id = scenario.get("id")
        profile = scenario.get("profile")
        if not isinstance(scenario_id, str) or not scenario_id or scenario_id in seen_ids:
            raise SystemExit(f"ai-context-eval: invalid or duplicate scenario id: {scenario_id}")
        seen_ids.add(scenario_id)
        if profile not in selected_paths:
            raise SystemExit(f"ai-context-eval: unknown profile in {scenario_id}: {profile}")
        scenario_failures: List[str] = []
        required_paths = require_list(scenario.get("required_paths", []), "required_paths")
        for raw_path in required_paths:
            if not isinstance(raw_path, str):
                raise SystemExit(f"ai-context-eval: invalid path in {scenario_id}")
            path = helper.validate_protocol_path(raw_path, "evaluation path")
            if path not in selected_paths[profile]:
                scenario_failures.append(f"profile {profile} omits {path}")
        for anchor in require_list(scenario.get("anchors", []), "anchors"):
            if not isinstance(anchor, dict) or not isinstance(anchor.get("path"), str):
                raise SystemExit(f"ai-context-eval: invalid anchor in {scenario_id}")
            path = helper.validate_protocol_path(anchor["path"], "anchor path")
            if path not in selected_paths[profile]:
                scenario_failures.append(f"anchor path is absent from {profile}: {path}")
                continue
            try:
                text = helper.read_repository_file(root, path).decode("utf-8")
            except (UnicodeDecodeError, helper.InventoryError) as exc:
                scenario_failures.append(f"could not read anchor path {path}: {exc}")
                continue
            for marker in require_list(anchor.get("contains", []), "anchor contains"):
                if not isinstance(marker, str) or marker not in text:
                    scenario_failures.append(f"missing anchor {marker!r} in {path}")
        retrieval_queries = require_list(
            scenario.get("retrieval_queries", []),
            "retrieval_queries",
        )
        if not retrieval_queries:
            scenario_failures.append("scenario defines no full-mode retrieval query")
        for query in retrieval_queries:
            if not isinstance(query, dict):
                raise SystemExit(f"ai-context-eval: invalid retrieval query in {scenario_id}")
            pattern = query.get("pattern")
            raw_expected_path = query.get("expected_path")
            if not isinstance(pattern, str) or not pattern or not isinstance(raw_expected_path, str):
                raise SystemExit(f"ai-context-eval: invalid retrieval query in {scenario_id}")
            expected_path = helper.validate_protocol_path(
                raw_expected_path,
                "retrieval expected path",
            )
            if expected_path not in selected_paths[profile]:
                scenario_failures.append(
                    f"retrieval path is absent from {profile}: {expected_path}"
                )
                continue
            try:
                source = helper.read_repository_file(root, expected_path).decode("utf-8")
            except (UnicodeDecodeError, helper.InventoryError) as exc:
                scenario_failures.append(
                    f"could not read retrieval path {expected_path}: {exc}"
                )
                continue
            if pattern not in source:
                scenario_failures.append(
                    f"retrieval pattern {pattern!r} is absent from {expected_path}"
                )
        passed = not scenario_failures
        results.append(
            {
                "id": scenario_id,
                "profile": profile,
                "passed": passed,
                "failures": scenario_failures,
            }
        )
        failures.extend(f"{scenario_id}: {message}" for message in scenario_failures)

    summary = {
        "schema_version": 1,
        "scenario_count": len(results),
        "passed": sum(1 for item in results if item["passed"]),
        "profiles": {
            name: {
                "approved_file_count": inventories[name]["approved_file_count"],
                "inventory_sha256": inventories[name]["inventory_sha256"],
            }
            for name in profiles
        },
        "results": results,
    }
    if arguments.as_json:
        json.dump(summary, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        for item in results:
            state = "PASS" if item["passed"] else "FAIL"
            print(f"{state} {item['id']} [{item['profile']}]")
            for message in item["failures"]:
                print(f"  - {message}")
        print(f"AI context profile evaluation: {summary['passed']}/{summary['scenario_count']} passed")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
