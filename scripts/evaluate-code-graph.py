#!/usr/bin/env python3
"""Evaluate real code-graph retrieval queries with hit@10 and MRR."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple


Runner = Callable[..., subprocess.CompletedProcess[str]]
EXPECTED_SCENARIO_IDS = frozenset(
    {
        "dual_api_prefix",
        "creation_star_lane",
        "outline_debate_lane",
        "chapter_writing_lane",
        "batch_generation",
        "canon_approval_boundary",
        "frontend_outline_workbench",
        "frontend_proposal_apply",
        "tooling_and_ci_context",
    }
)


class EvaluationError(RuntimeError):
    """Raised when the evaluation contract or tool response is invalid."""


def require_list(value: Any, label: str) -> List[Any]:
    if not isinstance(value, list):
        raise EvaluationError(f"{label} must be an array")
    return value


def load_retrieval_queries(evaluation_path: Path) -> List[Dict[str, str]]:
    try:
        evaluation = json.loads(evaluation_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvaluationError(f"invalid evaluation file: {exc}") from exc
    if evaluation.get("$schema") != "narraverse.ai-context-eval.v1":
        raise EvaluationError("unsupported evaluation schema")

    queries: List[Dict[str, str]] = []
    observed_scenario_ids: set[str] = set()
    for scenario_index, scenario in enumerate(
        require_list(evaluation.get("scenarios"), "scenarios")
    ):
        if not isinstance(scenario, dict):
            raise EvaluationError(f"scenario {scenario_index} must be an object")
        scenario_id = scenario.get("id")
        profile = scenario.get("profile")
        if not isinstance(scenario_id, str) or not scenario_id:
            raise EvaluationError(f"scenario {scenario_index} has an invalid id")
        if scenario_id in observed_scenario_ids:
            raise EvaluationError(f"duplicate evaluation scenario: {scenario_id}")
        observed_scenario_ids.add(scenario_id)
        if not isinstance(profile, str) or not profile:
            raise EvaluationError(f"scenario {scenario_id} has an invalid profile")
        scenario_queries = require_list(
            scenario.get("retrieval_queries", []),
            f"retrieval_queries in {scenario_id}",
        )
        if len(scenario_queries) != 1:
            raise EvaluationError(
                f"scenario {scenario_id} must define exactly one retrieval query"
            )
        for query_index, query in enumerate(scenario_queries):
            if not isinstance(query, dict):
                raise EvaluationError(
                    f"retrieval query {query_index} in {scenario_id} must be an object"
                )
            pattern = query.get("pattern")
            expected_path = query.get("expected_path")
            if not isinstance(pattern, str) or not pattern:
                raise EvaluationError(
                    f"retrieval query {query_index} in {scenario_id} has an invalid pattern"
                )
            if not isinstance(expected_path, str) or not expected_path:
                raise EvaluationError(
                    f"retrieval query {query_index} in {scenario_id} has an invalid expected_path"
                )
            queries.append(
                {
                    "scenario_id": scenario_id,
                    "profile": profile,
                    "pattern": pattern,
                    "expected_path": expected_path,
                }
            )
    if observed_scenario_ids != EXPECTED_SCENARIO_IDS:
        missing = sorted(EXPECTED_SCENARIO_IDS - observed_scenario_ids)
        unexpected = sorted(observed_scenario_ids - EXPECTED_SCENARIO_IDS)
        raise EvaluationError(
            f"evaluation scenario contract drifted; missing={missing}, unexpected={unexpected}"
        )
    if len(queries) != len(EXPECTED_SCENARIO_IDS):
        raise EvaluationError("evaluation query count drifted from the scenario contract")
    return queries


def search_code(
    repo_root: Path,
    code_intel: Path,
    pattern: str,
    runner: Runner = subprocess.run,
) -> Tuple[List[str], Optional[str]]:
    arguments = {
        "pattern": pattern,
        "limit": 10,
        "context": 0,
        "mode": "files",
    }
    command = [
        str(code_intel),
        "query",
        "search_code",
        json.dumps(arguments, ensure_ascii=False, separators=(",", ":")),
    ]
    try:
        completed = runner(
            command,
            cwd=str(repo_root),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
            timeout=180,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return [], "search_code timed out"
    except OSError as exc:
        return [], f"could not run search_code: {exc}"

    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        suffix = f": {detail[:2000]}" if detail else ""
        return [], f"search_code exited {completed.returncode}{suffix}"
    try:
        response = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        return [], f"search_code returned invalid JSON: {exc}"
    if not isinstance(response, dict):
        return [], "search_code response must be an object"

    files = response.get("files")
    if not isinstance(files, list) or any(not isinstance(path, str) for path in files):
        return [], "search_code response files must be an array of paths"
    return files[:10], None


def evaluate_queries(
    repo_root: Path,
    code_intel: Path,
    queries: Sequence[Mapping[str, str]],
    runner: Runner = subprocess.run,
) -> Dict[str, Any]:
    results: List[Dict[str, Any]] = []
    reciprocal_rank_total = 0.0
    hit_count = 0

    for query in queries:
        returned_files, error = search_code(
            repo_root,
            code_intel,
            query["pattern"],
            runner=runner,
        )
        expected_path = query["expected_path"]
        try:
            rank: Optional[int] = returned_files.index(expected_path) + 1
        except ValueError:
            rank = None
        hit = rank is not None
        if hit:
            hit_count += 1
            reciprocal_rank_total += 1.0 / rank
        results.append(
            {
                "scenario_id": query["scenario_id"],
                "profile": query["profile"],
                "pattern": query["pattern"],
                "expected_path": expected_path,
                "returned_files": returned_files,
                "rank": rank,
                "hit_at_10": hit,
                "error": error,
            }
        )

    query_count = len(results)
    if query_count == 0:
        raise EvaluationError("cannot evaluate an empty query set")
    return {
        "schema_version": 1,
        "query_count": query_count,
        "hit_count": hit_count,
        "miss_count": query_count - hit_count,
        "hit_at_10": hit_count / query_count,
        "mrr": reciprocal_rank_total / query_count,
        "results": results,
    }


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--json", action="store_true", dest="as_json")
    return parser.parse_args(argv)


def main(
    argv: Optional[Sequence[str]] = None,
    runner: Runner = subprocess.run,
) -> int:
    arguments = parse_args(argv)
    repo_root = Path(arguments.repo_root).expanduser().resolve()
    evaluation_path = repo_root / "scripts" / "ai-context-eval.json"
    code_intel = repo_root / "scripts" / "code-intel.sh"
    try:
        queries = load_retrieval_queries(evaluation_path)
        if not code_intel.is_file():
            raise EvaluationError(f"missing code-intel entry point: {code_intel}")
        summary = evaluate_queries(repo_root, code_intel, queries, runner=runner)
    except EvaluationError as exc:
        print(f"code-graph-eval: {exc}", file=sys.stderr)
        return 2

    if arguments.as_json:
        json.dump(summary, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        for result in summary["results"]:
            state = "PASS" if result["hit_at_10"] else "MISS"
            rank = result["rank"] if result["rank"] is not None else "-"
            print(
                f"{state} {result['scenario_id']} rank={rank} "
                f"expected={result['expected_path']}"
            )
            if result["error"]:
                print(f"  - {result['error']}")
        print(
            "Code graph retrieval: "
            f"hit@10={summary['hit_count']}/{summary['query_count']} "
            f"({summary['hit_at_10']:.3f}), MRR={summary['mrr']:.3f}"
        )
    return 1 if summary["miss_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
