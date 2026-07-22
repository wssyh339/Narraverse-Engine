from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Any


SCRIPTS_DIR = Path(__file__).resolve().parents[1]
EVALUATOR_PATH = SCRIPTS_DIR / "evaluate-code-graph.py"
SPEC = importlib.util.spec_from_file_location("evaluate_code_graph", EVALUATOR_PATH)
if SPEC is None or SPEC.loader is None:  # pragma: no cover - import contract
    raise RuntimeError(f"could not load {EVALUATOR_PATH}")
evaluator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(evaluator)


class CodeGraphEvaluationTests(unittest.TestCase):
    def test_evaluation_uses_files_top_ten_and_computes_metrics(self) -> None:
        repo_root = Path("/tmp/evaluation-repo")
        code_intel = repo_root / "scripts" / "code-intel.sh"
        calls: list[tuple[list[str], dict[str, Any]]] = []

        def fake_runner(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            payload = json.loads(command[3])
            calls.append((command, kwargs))
            if payload["pattern"] == "rank-two":
                files = ["other.py", "expected.py"]
            else:
                files = [f"result-{index}.py" for index in range(10)] + ["late.py"]
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps({"files": files}),
                stderr="",
            )

        summary = evaluator.evaluate_queries(
            repo_root,
            code_intel,
            [
                {
                    "scenario_id": "hit",
                    "profile": "backend",
                    "pattern": "rank-two",
                    "expected_path": "expected.py",
                },
                {
                    "scenario_id": "miss",
                    "profile": "frontend",
                    "pattern": "outside-top-ten",
                    "expected_path": "late.py",
                },
            ],
            runner=fake_runner,
        )

        self.assertEqual(summary["hit_count"], 1)
        self.assertEqual(summary["miss_count"], 1)
        self.assertEqual(summary["hit_at_10"], 0.5)
        self.assertEqual(summary["mrr"], 0.25)
        self.assertEqual(summary["results"][0]["rank"], 2)
        self.assertIsNone(summary["results"][1]["rank"])
        self.assertEqual(len(summary["results"][1]["returned_files"]), 10)
        self.assertEqual(len(calls), 2)
        for command, kwargs in calls:
            self.assertEqual(command[:3], [str(code_intel), "query", "search_code"])
            self.assertEqual(
                json.loads(command[3]),
                {"pattern": json.loads(command[3])["pattern"], "limit": 10, "context": 0, "mode": "files"},
            )
            self.assertEqual(kwargs["cwd"], str(repo_root))
            self.assertFalse(kwargs["check"])

    def test_main_returns_nonzero_when_any_query_misses(self) -> None:
        with tempfile.TemporaryDirectory(prefix="narraverse-graph-eval-") as temporary:
            repo_root = Path(temporary)
            scripts_dir = repo_root / "scripts"
            scripts_dir.mkdir()
            (scripts_dir / "code-intel.sh").write_text("#!/bin/sh\n", encoding="utf-8")
            (scripts_dir / "ai-context-eval.json").write_text(
                json.dumps(
                    {
                        "$schema": "narraverse.ai-context-eval.v1",
                        "scenarios": [
                            {
                                "id": scenario_id,
                                "profile": "backend",
                                "retrieval_queries": [
                                    {
                                        "pattern": f"needle-{scenario_id}",
                                        "expected_path": f"expected-{scenario_id}.py",
                                    }
                                ],
                            }
                            for scenario_id in sorted(
                                evaluator.EXPECTED_SCENARIO_IDS
                            )
                        ],
                    }
                ),
                encoding="utf-8",
            )

            def fake_runner(
                command: list[str], **kwargs: Any
            ) -> subprocess.CompletedProcess[str]:
                return subprocess.CompletedProcess(
                    command,
                    0,
                    stdout=json.dumps({"files": ["other.py"]}),
                    stderr="",
                )

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                exit_code = evaluator.main(
                    ["--repo-root", str(repo_root), "--json"],
                    runner=fake_runner,
                )

        report = json.loads(output.getvalue())
        self.assertEqual(exit_code, 1)
        self.assertEqual(report["miss_count"], 9)
        self.assertEqual(report["hit_at_10"], 0.0)

    def test_scenario_contract_rejects_deleted_or_renamed_cases(self) -> None:
        with tempfile.TemporaryDirectory(prefix="narraverse-graph-contract-") as temporary:
            path = Path(temporary) / "eval.json"
            path.write_text(
                json.dumps(
                    {
                        "$schema": "narraverse.ai-context-eval.v1",
                        "scenarios": [
                            {
                                "id": "dual_api_prefix",
                                "profile": "backend",
                                "retrieval_queries": [
                                    {"pattern": "needle", "expected_path": "file.py"}
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(evaluator.EvaluationError, "contract drifted"):
                evaluator.load_retrieval_queries(path)


if __name__ == "__main__":
    unittest.main()
