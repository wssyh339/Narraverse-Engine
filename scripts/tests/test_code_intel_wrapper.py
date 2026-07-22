from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1]
ROOT = SCRIPTS_DIR.parent
WRAPPER = SCRIPTS_DIR / "code-intel.sh"


class CodeIntelWrapperTests(unittest.TestCase):
    def run_wrapper(
        self,
        *arguments: str,
        environment: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(WRAPPER), *arguments],
            cwd=str(ROOT),
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
            timeout=20,
            check=False,
        )

    def test_forbidden_cypher_fails_before_install_or_native_lookup(self) -> None:
        completed = self.run_wrapper(
            "query",
            "query_graph",
            '{"query":"SHOW DATABASES"}',
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("arguments failed validation", completed.stderr)
        self.assertNotIn("is not installed", completed.stderr)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks are required")
    def test_uninstall_rejects_version_symlink_without_touching_target(self) -> None:
        with tempfile.TemporaryDirectory(prefix="narraverse-uninstall-") as temporary:
            base = Path(temporary)
            data_home = base / "data"
            parent = data_home / "narraverse/code-intel/codebase-memory-mcp"
            parent.mkdir(parents=True)
            outside = base / "outside"
            outside.mkdir()
            sentinel = outside / "sentinel.txt"
            sentinel.write_text("keep\n", encoding="utf-8")
            os.symlink(outside, parent / "0.9.0")
            environment = os.environ.copy()
            environment["XDG_DATA_HOME"] = str(data_home)
            completed = self.run_wrapper("uninstall", environment=environment)
            self.assertNotEqual(completed.returncode, 0)
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep\n")
            self.assertTrue((parent / "0.9.0").is_symlink())

    def test_uninstall_recovers_a_partial_removal_tombstone(self) -> None:
        with tempfile.TemporaryDirectory(prefix="narraverse-tombstone-") as temporary:
            base = Path(temporary)
            data_home = base / "data"
            parent = data_home / "narraverse/code-intel/codebase-memory-mcp"
            tombstone = parent / (".removing.0.9.0." + "a" * 32)
            tombstone.mkdir(parents=True)
            (tombstone / "LICENSE").write_text("partial\n", encoding="utf-8")
            environment = os.environ.copy()
            environment["XDG_DATA_HOME"] = str(data_home)
            completed = self.run_wrapper("uninstall", environment=environment)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertFalse(tombstone.exists())
            self.assertIn("is not installed", completed.stdout)


if __name__ == "__main__":
    unittest.main()
