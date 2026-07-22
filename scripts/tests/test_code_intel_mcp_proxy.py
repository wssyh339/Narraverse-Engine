from __future__ import annotations

import json
import hashlib
import os
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path
from typing import Any, Optional


SCRIPTS_DIR = Path(__file__).resolve().parents[1]
PROXY = SCRIPTS_DIR / "code-intel-mcp-proxy.py"
EXPECTED_TOOLS = {
    "search_graph",
    "query_graph",
    "trace_path",
    "get_code_snippet",
    "get_graph_schema",
    "get_architecture",
    "search_code",
    "index_status",
}
FORBIDDEN_TOOLS = {
    "detect_changes",
    "index_repository",
    "list_projects",
    "delete_project",
    "manage_adr",
    "ingest_traces",
    "unknown_tool",
}


class ReadOnlyMcpProxyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="narraverse-mcp-proxy-")
        self.root = Path(self.temp_dir.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        (self.repo / ".git").mkdir()
        self.cache = self.repo / ".codebase-memory"
        self.project = self.cache / "inputs" / ("a" * 64) / "files"
        self.project.mkdir(parents=True)
        (self.project.parent / "manifest.json").write_text("{}\n", encoding="utf-8")
        self.fake_binary = self.root / "fake-codebase-memory"
        self.fake_binary.write_text(
            textwrap.dedent(
                """
                #!/usr/bin/env python3
                import json
                import os
                import pathlib
                import sys
                import time

                tool = sys.argv[2]
                arguments = json.load(sys.stdin)
                log = pathlib.Path.cwd() / "native-calls.jsonl"
                with log.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps({"tool": tool, "arguments": arguments}) + "\\n")
                (pathlib.Path(__file__).resolve().parent / "native-ran").write_text("yes\\n")
                if arguments.get("pattern") == "huge":
                    print(json.dumps({"payload": "x" * 600000}))
                elif arguments.get("pattern") == "streamhuge":
                    for _ in range(20):
                        sys.stdout.write("x" * 65536)
                        sys.stdout.flush()
                        time.sleep(0.02)
                    time.sleep(5)
                elif arguments.get("pattern") == "replacebinary":
                    pathlib.Path(__file__).write_text(
                        "#!/usr/bin/env python3\\nprint('{}')\\n",
                        encoding="utf-8",
                    )
                    print(json.dumps({"replaced": True}))
                elif arguments.get("pattern") == "wirehuge":
                    print(json.dumps({"payload": "x" * 140000}))
                else:
                    print(json.dumps({
                        "tool": tool,
                        "arguments": arguments,
                        "has_test_secret": "NARRAVERSE_PROXY_TEST_SECRET" in os.environ,
                    }))
                """
            ).lstrip(),
            encoding="utf-8",
        )
        self.fake_binary.chmod(0o755)
        self.fake_helper = self.root / "fake-input-helper"
        self.fake_helper.write_text(
            textwrap.dedent(
                """
                #!/usr/bin/env python3
                import pathlib
                import sys

                root = pathlib.Path(__file__).resolve().parent
                if (root / "fail-integrity").exists():
                    raise SystemExit(1)
                if (root / "fail-after-native").exists() and (root / "native-ran").exists():
                    raise SystemExit(1)
                """
            ).lstrip(),
            encoding="utf-8",
        )
        self.fake_helper.chmod(0o755)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    @staticmethod
    def request(identifier: int, method: str, params: Any = None) -> dict[str, Any]:
        message: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": identifier,
            "method": method,
        }
        if params is not None:
            message["params"] = params
        return message

    def run_proxy(
        self,
        messages: list[Any],
        extra_lines: Optional[list[str]] = None,
    ) -> list[dict[str, Any]]:
        lines = [
            json.dumps(message, ensure_ascii=False, separators=(",", ":"))
            for message in messages
        ]
        lines.extend(extra_lines or [])
        environment = os.environ.copy()
        environment["NARRAVERSE_PROXY_TEST_SECRET"] = "must-not-reach-native"
        completed = subprocess.run(
            [
                sys.executable,
                str(PROXY),
                "--binary",
                str(self.fake_binary),
                "--binary-sha256",
                hashlib.sha256(self.fake_binary.read_bytes()).hexdigest(),
                "--repo-root",
                str(self.repo),
                "--project-root",
                str(self.project),
                "--cache-dir",
                str(self.cache),
                "--input-helper",
                str(self.fake_helper),
            ],
            input="\n".join(lines) + "\n",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
            env=environment,
            timeout=15,
            check=True,
        )
        return [json.loads(line) for line in completed.stdout.splitlines()]

    def test_tools_list_exposes_exact_read_only_set(self) -> None:
        responses = self.run_proxy(
            [
                self.request(
                    1,
                    "initialize",
                    {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {},
                        "clientInfo": {"name": "test", "version": "1"},
                    },
                ),
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                self.request(2, "tools/list"),
            ]
        )
        self.assertEqual([item["id"] for item in responses], [1, 2])
        self.assertEqual(responses[0]["result"]["protocolVersion"], "2025-06-18")
        tools = responses[1]["result"]["tools"]
        self.assertEqual({item["name"] for item in tools}, EXPECTED_TOOLS)
        self.assertNotIn("nextCursor", responses[1]["result"])
        for tool in tools:
            self.assertTrue(tool["annotations"]["readOnlyHint"])
            self.assertFalse(tool["annotations"]["destructiveHint"])
            self.assertNotIn("project", tool["inputSchema"]["properties"])

    def test_forbidden_tools_are_rejected_before_native_execution(self) -> None:
        messages = [
            self.request(
                index,
                "tools/call",
                {"name": tool, "arguments": {}},
            )
            for index, tool in enumerate(sorted(FORBIDDEN_TOOLS), start=1)
        ]
        responses = self.run_proxy(messages)
        self.assertEqual(len(responses), len(FORBIDDEN_TOOLS))
        self.assertTrue(all(item["error"]["code"] == -32602 for item in responses))
        self.assertFalse((self.repo / "native-calls.jsonl").exists())

    def test_allowed_call_injects_repo_and_strips_sensitive_environment(self) -> None:
        responses = self.run_proxy(
            [
                self.request(
                    1,
                    "tools/call",
                    {"name": "index_status", "arguments": {}},
                )
            ]
        )
        result = responses[0]["result"]
        self.assertFalse(result["isError"])
        structured = result["structuredContent"]
        self.assertEqual(structured["tool"], "index_status")
        self.assertEqual(structured["arguments"]["project"], ".")
        self.assertFalse(structured["has_test_secret"])

        native_call = json.loads(
            (self.repo / "native-calls.jsonl").read_text(encoding="utf-8")
        )
        self.assertEqual(native_call["arguments"]["project"], str(self.project.resolve()))

    def test_cross_repo_and_write_queries_fail_closed(self) -> None:
        responses = self.run_proxy(
            [
                self.request(
                    1,
                    "tools/call",
                    {
                        "name": "index_status",
                        "arguments": {"project": "/another/repository"},
                    },
                ),
                self.request(
                    2,
                    "tools/call",
                    {
                        "name": "query_graph",
                        "arguments": {
                            "query": "MATCH (n) DELETE n RETURN n",
                        },
                    },
                ),
                self.request(
                    3,
                    "tools/call",
                    {
                        "name": "get_architecture",
                        "arguments": {"path": "../private"},
                    },
                ),
            ]
        )
        self.assertEqual([item["error"]["code"] for item in responses], [-32602] * 3)
        self.assertFalse((self.repo / "native-calls.jsonl").exists())

    def test_malformed_tool_name_and_cursor_fail_closed(self) -> None:
        responses = self.run_proxy(
            [
                self.request(
                    1,
                    "tools/call",
                    {"name": [], "arguments": {}},
                ),
                self.request(2, "tools/list", {"cursor": "8"}),
                self.request(3, "ping"),
            ]
        )
        self.assertEqual(responses[0]["error"]["code"], -32602)
        self.assertEqual(responses[1]["error"]["code"], -32602)
        self.assertEqual(responses[2]["result"], {})
        self.assertFalse((self.repo / "native-calls.jsonl").exists())

    def test_read_query_is_bounded_and_large_response_is_rejected(self) -> None:
        responses = self.run_proxy(
            [
                self.request(
                    1,
                    "tools/call",
                    {
                        "name": "query_graph",
                        "arguments": {"query": "MATCH (n) RETURN n"},
                    },
                ),
                self.request(
                    2,
                    "tools/call",
                    {
                        "name": "search_code",
                        "arguments": {"pattern": "huge"},
                    },
                ),
                self.request(
                    3,
                    "tools/call",
                    {
                        "name": "search_code",
                        "arguments": {"pattern": "wirehuge"},
                    },
                ),
            ]
        )
        first = responses[0]["result"]["structuredContent"]
        self.assertEqual(first["arguments"]["max_rows"], 200)
        self.assertEqual(first["arguments"]["project"], ".")
        self.assertTrue(responses[1]["result"]["isError"])
        self.assertIn("exceeded", responses[1]["result"]["content"][0]["text"])
        self.assertTrue(responses[2]["result"]["isError"])
        self.assertIn("MCP response", responses[2]["result"]["content"][0]["text"])

    def test_streaming_native_overflow_is_terminated_before_child_sleep(self) -> None:
        started = time.monotonic()
        responses = self.run_proxy(
            [
                self.request(
                    1,
                    "tools/call",
                    {
                        "name": "search_code",
                        "arguments": {"pattern": "streamhuge"},
                    },
                )
            ]
        )
        elapsed = time.monotonic() - started
        self.assertLess(elapsed, 3.0)
        self.assertTrue(responses[0]["result"]["isError"])
        self.assertIn("native output limit", responses[0]["result"]["content"][0]["text"])

    def test_binary_replacement_hides_result_and_blocks_later_calls(self) -> None:
        responses = self.run_proxy(
            [
                self.request(
                    1,
                    "tools/call",
                    {
                        "name": "search_code",
                        "arguments": {"pattern": "replacebinary"},
                    },
                ),
                self.request(
                    2,
                    "tools/call",
                    {"name": "index_status", "arguments": {}},
                ),
            ]
        )
        for response in responses:
            self.assertTrue(response["result"]["isError"])
            self.assertIn("binary integrity", response["result"]["content"][0]["text"])
        calls = (self.repo / "native-calls.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(calls), 1)

    def test_cypher_keywords_inside_strings_do_not_trigger_write_filter(self) -> None:
        responses = self.run_proxy(
            [
                self.request(
                    1,
                    "tools/call",
                    {
                        "name": "query_graph",
                        "arguments": {
                            "query": "MATCH (n) WHERE n.label = 'DELETE' RETURN n",
                        },
                    },
                ),
                self.request(
                    2,
                    "tools/call",
                    {
                        "name": "query_graph",
                        "arguments": {"query": "MATCH (n) // bypass\nRETURN n"},
                    },
                ),
            ]
        )
        self.assertFalse(responses[0]["result"]["isError"])
        self.assertEqual(responses[1]["error"]["code"], -32602)

    def test_invalid_json_and_unknown_method_return_json_rpc_errors(self) -> None:
        responses = self.run_proxy(
            [self.request(9, "resources/list")],
            extra_lines=["not-json"],
        )
        self.assertEqual(responses[0]["error"]["code"], -32601)
        self.assertEqual(responses[1]["error"]["code"], -32700)

    def test_pre_call_input_integrity_failure_prevents_native_execution(self) -> None:
        (self.root / "fail-integrity").write_text("fail\n", encoding="utf-8")
        responses = self.run_proxy(
            [
                self.request(
                    1,
                    "tools/call",
                    {"name": "index_status", "arguments": {}},
                )
            ]
        )
        result = responses[0]["result"]
        self.assertTrue(result["isError"])
        self.assertIn("integrity", result["content"][0]["text"])
        self.assertFalse((self.repo / "native-calls.jsonl").exists())

    def test_post_call_input_integrity_failure_hides_native_result(self) -> None:
        (self.root / "fail-after-native").write_text("fail later\n", encoding="utf-8")
        responses = self.run_proxy(
            [
                self.request(
                    1,
                    "tools/call",
                    {"name": "index_status", "arguments": {}},
                )
            ]
        )
        result = responses[0]["result"]
        self.assertTrue(result["isError"])
        self.assertIn("integrity", result["content"][0]["text"])
        self.assertTrue((self.repo / "native-calls.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
