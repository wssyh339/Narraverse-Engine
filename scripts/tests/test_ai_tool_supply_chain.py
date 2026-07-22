from __future__ import annotations

import importlib.util
import json
import re
import unittest
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1]
ROOT = SCRIPTS_DIR.parent
VERIFIER_PATH = SCRIPTS_DIR / "verify-ai-tool-supply-chain.py"
SPEC = importlib.util.spec_from_file_location("ai_tool_supply_chain", VERIFIER_PATH)
if SPEC is None or SPEC.loader is None:  # pragma: no cover - import contract
    raise RuntimeError(f"could not load {VERIFIER_PATH}")
supply_chain = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(supply_chain)


class AiToolSupplyChainTests(unittest.TestCase):
    def test_repomix_package_and_transitive_lock_are_exact_and_closed(self) -> None:
        result = supply_chain.validate_runtime(SCRIPTS_DIR / "repomix-runtime")
        self.assertEqual(result["repomix_version"], "1.17.0")
        self.assertEqual(
            result["package_lock_sha256"],
            "0d2a6f6899f6c1bcef2c10d37f13b07fa06e8344bcb03b81dc18d5f7c023ab0b",
        )
        self.assertEqual(result["package_count"], 170)

        lock = json.loads(
            (SCRIPTS_DIR / "repomix-runtime/package-lock.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertFalse(
            any(
                entry.get("hasInstallScript") is True
                for entry in lock["packages"].values()
                if isinstance(entry, dict)
            )
        )

    def test_code_graph_release_assets_and_installed_files_are_pinned(self) -> None:
        wrapper = (SCRIPTS_DIR / "code-intel.sh").read_text(encoding="utf-8")
        expected = {
            "codebase-memory-mcp-darwin-arm64.tar.gz": "faa02f0404230c451a9812230394481948f80183801fa5bf67044b41c2f25ed4",
            "codebase-memory-mcp-darwin-amd64.tar.gz": "6af3d02a27f589901fa763d3971089337bc8c9838bbed5d0cf543ca9f1a9e543",
            "codebase-memory-mcp-linux-amd64-portable.tar.gz": "8459d5c9d1457f2c82de3de307ffc7641ecbba2dde893427be1e62eca8ef9b25",
            "codebase-memory-mcp-linux-arm64-portable.tar.gz": "b0a43fdaf534073c16707d72726b73b149d4c1212034b281ee8b7b2dac755107",
        }
        expected_binaries = {
            "d9fbdd7d8570a77b2fb32453e00bd52a02627281309cd56003a4eccfcfe878d6",
            "04ee3048810c19099502adc8bb83039423f02f2553d17677892a7f03b924e01f",
            "8d019ca9372e5e0d60650648f3740673db7f84d1e38fd14fa4b0e823ee7220dc",
            "5636efebea2afdcb4783014f8c8eb7d319c48b63e9ecdccbbf12911837a7cacd",
        }
        self.assertIn('CBM_VERSION="0.9.0"', wrapper)
        self.assertIn("releases/download/v${CBM_VERSION}", wrapper)
        for asset, digest in expected.items():
            self.assertIn(asset, wrapper)
            self.assertIn(digest, wrapper)
        for digest in expected_binaries | {
            "1f58f9911dc5e3bcb96de28bb28e7b6bb7eb323952d29569c5d7214a152146bb",
            "d02434a42fb7b5151cc3f7a3be4908136e8bbc12255f7ddc8c63c6923acfd611",
        }:
            self.assertIn(digest, wrapper)
        for marker in (
            "--proto '=https'",
            "--tlsv1.2",
            "LICENSE THIRD_PARTY_NOTICES.md",
            "installed-files.sha256",
            "verify_installed_files",
            "run_native",
            "--binary-sha256",
            "prepare_install_parent",
            "os.rename(",
            "release_runtime_lock",
            "handle_signal 143",
            "--watch-file \"${archive_path}=134217728\"",
            "--max-filesize 134217728",
        ):
            self.assertIn(marker, wrapper)
        self.assertNotIn("CODEBASE_MEMORY_MCP_BIN", wrapper)
        self.assertIsNone(re.search(r"command -v codebase-memory-mcp", wrapper))

    def test_repomix_build_uses_immutable_input_lock_and_clean_environment(self) -> None:
        build = (SCRIPTS_DIR / "build-ai-context.sh").read_text(encoding="utf-8")
        for marker in (
            "materialize-snapshot-input",
            "ci --ignore-scripts",
            "--clear-environment",
            "--watch-file",
            "publish-context-bundle",
            "copied_config_path",
            "runtime_lock_sha256",
            "runtime_package_sha256",
            "snapshot_sha256",
            "node_version",
            "npm_version",
        ):
            self.assertIn(marker, build)
        for forbidden in ("npm exec", "npm view", "npx repomix", "@latest"):
            self.assertNotIn(forbidden, build)
        config = json.loads((ROOT / "repomix.config.json").read_text(encoding="utf-8"))
        self.assertFalse(config["ignore"]["useGitignore"])
        self.assertFalse(config["ignore"]["useDotIgnore"])
        self.assertFalse(config["output"]["git"]["sortByChanges"])

    def test_github_actions_are_immutable_and_least_privilege(self) -> None:
        expected_shas = {
            "11bd71901bbe5b1630ceea73d27597364c9af683",
            "a26af69be951a213d495a4c3e4e4022e16d87065",
            "49933ea5288caeca8642d1e84afbd3f7d6820020",
            "fc06bc1257f339d1d5d8b3a19a8cae5388b55320",
        }
        workflows = list((ROOT / ".github/workflows").glob("*.yml"))
        reviewed = [
            path
            for path in workflows
            if path.name in {"ci.yml", "ai-context-full.yml"}
        ]
        self.assertEqual({path.name for path in reviewed}, {"ci.yml", "ai-context-full.yml"})
        observed: set[str] = set()
        for path in reviewed:
            text = path.read_text(encoding="utf-8")
            self.assertIn("permissions:\n  contents: read", text)
            self.assertNotRegex(text, r"uses:\s+[^\s]+@v[0-9]")
            observed.update(re.findall(r"uses:\s+[^@\s]+@([0-9a-f]{40})", text))
            for checkout_block in re.findall(
                r"uses:\s+actions/checkout@[\s\S]*?(?=\n\s*- name:|\Z)",
                text,
            ):
                self.assertIn("persist-credentials: false", checkout_block)
        self.assertEqual(observed, expected_shas)


if __name__ == "__main__":
    unittest.main()
