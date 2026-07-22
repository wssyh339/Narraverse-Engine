from __future__ import annotations

import importlib.util
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from typing import Any, Sequence
from unittest import mock


SCRIPTS_DIR = Path(__file__).resolve().parents[1]
HELPER_PATH = SCRIPTS_DIR / "ai-context-inputs.py"
SPEC = importlib.util.spec_from_file_location("ai_context_inputs", HELPER_PATH)
if SPEC is None or SPEC.loader is None:  # pragma: no cover - import contract
    raise RuntimeError(f"could not load {HELPER_PATH}")
ai_inputs = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ai_inputs)


class AiContextInputsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="narraverse-inputs-")
        self.base = Path(self.temporary.name)
        self.repo = self.base / "repo"
        self.repo.mkdir()
        self.empty_global_config = self.base / "empty-gitconfig"
        self.empty_global_config.write_text("", encoding="utf-8")
        self.original_environment = os.environ.copy()
        os.environ.pop("GIT_INDEX_FILE", None)
        os.environ.update(
            {
                "GIT_CONFIG_GLOBAL": str(self.empty_global_config),
                "GIT_CONFIG_NOSYSTEM": "1",
                "HOME": str(self.base / "home"),
            }
        )
        self.git("init", "--quiet")
        self.git("config", "user.name", "Narraverse Test")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "commit.gpgsign", "false")
        self.git("config", "core.autocrlf", "false")
        self.write(".denyignore", "private/**\n")
        self.write(".gitignore", "ignored/**\n")
        self.write("tracked.txt", "committed\n")
        self.write("deleted.txt", "delete me\n")
        self.git("add", ".")
        self.git("commit", "--quiet", "-m", "initial")

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self.original_environment)
        self.temporary.cleanup()

    def git(
        self,
        *arguments: str,
        input_text: str | None = None,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(self.repo), *arguments],
            input=input_text,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
            check=check,
        )

    def write(self, relative: str, content: str) -> Path:
        path = self.repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def inventory(self, allowed: Sequence[str] = ()) -> dict[str, Any]:
        return ai_inputs.build_inventory(
            self.repo,
            self.repo / ".denyignore",
            list(allowed),
        )

    def publishable_context_build(
        self,
        context: Path,
        manifest: dict[str, Any],
        config_sha: str,
    ) -> tuple[Path, str]:
        build_dir = Path(tempfile.mkdtemp(prefix=".building.", dir=str(context)))
        ai_inputs.atomic_write_json(build_dir / "manifest.json", manifest)
        snapshot_path = build_dir / "repomix.xml"
        snapshot_path.write_text(
            "<files>"
            + "".join(
                f'<file path="{item["path"]}">content</file>'
                for item in manifest["files"]
            )
            + "</files>\n",
            encoding="utf-8",
        )
        snapshot_path.chmod(0o600)
        snapshot_sha = hashlib.sha256(snapshot_path.read_bytes()).hexdigest()
        package_sha = "b" * 64
        lock_sha = "c" * 64
        digest = hashlib.sha256()
        for label, value in (
            ("inventory", manifest["inventory_sha256"]),
            ("config", config_sha),
            ("snapshot", snapshot_sha),
            ("runtime_package", package_sha),
            ("runtime_lock", lock_sha),
            ("repomix", "1.17.0"),
            ("node", "v24.14.0"),
            ("npm", "11.5.1"),
        ):
            digest.update(label.encode("ascii") + b"\0" + value.encode("ascii") + b"\0")
        bundle_id = digest.hexdigest()
        ai_inputs.atomic_write_json(
            build_dir / "provenance.json",
            {
                "schema_version": 1,
                "bundle_id": bundle_id,
                "inventory_sha256": manifest["inventory_sha256"],
                "profile": manifest["profile"],
                "packed_file_count": len(manifest["files"]),
                "config_sha256": config_sha,
                "snapshot_sha256": snapshot_sha,
                "runtime_package_sha256": package_sha,
                "runtime_lock_sha256": lock_sha,
                "repomix_version": "1.17.0",
                "repomix_integrity": "sha512-test",
                "node_version": "v24.14.0",
                "npm_version": "11.5.1",
            },
        )
        return build_dir, bundle_id

    @staticmethod
    def file_map(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
        return {item["path"]: item for item in manifest["files"]}

    def test_inventory_uses_index_membership_and_current_worktree_content(self) -> None:
        self.write("tracked.txt", "working tree wins\n")
        self.write("staged new $ 文件.py", "staged version\n")
        self.git("add", "staged new $ 文件.py")
        self.write("staged new $ 文件.py", "latest worktree version\n")
        self.write("intent-only.py", "not really staged\n")
        self.git("add", "-N", "intent-only.py")
        (self.repo / "deleted.txt").unlink()
        self.write("staged-delete.txt", "gone\n")
        self.git("add", "staged-delete.txt")
        self.git("commit", "--quiet", "-m", "add staged deletion fixture")
        self.git("rm", "--quiet", "staged-delete.txt")

        manifest = self.inventory()
        files = self.file_map(manifest)
        self.assertIn("tracked.txt", files)
        self.assertIn("staged new $ 文件.py", files)
        expected_hash, _, _ = ai_inputs.hash_regular_file(
            self.repo / "staged new $ 文件.py"
        )
        self.assertEqual(files["staged new $ 文件.py"]["sha256"], expected_hash)
        self.assertEqual(files["staged new $ 文件.py"]["origin"], "tracked")
        self.assertNotIn("staged-delete.txt", files)
        self.assertNotIn("intent-only.py", files)
        self.assertIn(
            {"path": "intent-only.py", "reason": "intent_to_add"},
            manifest["skipped"],
        )
        self.assertIn(
            {"path": "deleted.txt", "reason": "deleted_from_worktree"},
            manifest["skipped"],
        )

    def test_untracked_defaults_to_deny_and_exact_allow_is_audited(self) -> None:
        self.write("draft/idea.py", "idea\n")
        self.assertNotIn("draft/idea.py", self.file_map(self.inventory()))

        manifest = self.inventory(["draft/idea.py", "draft/idea.py"])
        files = self.file_map(manifest)
        self.assertEqual(files["draft/idea.py"]["origin"], "explicit_untracked")
        self.assertEqual(manifest["explicit_untracked"], ["draft/idea.py"])

        for unsafe in ("../escape", "draft/*.py", "/absolute", "line\nbreak", "tab\tpath"):
            with self.subTest(unsafe=unsafe), self.assertRaises(ai_inputs.InventoryError):
                self.inventory([unsafe])
        with self.assertRaisesRegex(ai_inputs.InventoryError, "deny rules take precedence"):
            self.inventory([".git/config"])

    def test_git_and_custom_ignore_rules_override_explicit_allow(self) -> None:
        self.write("private/tracked.txt", "tracked secret\n")
        self.git("add", "-f", "private/tracked.txt")
        self.write("ignored/tracked.txt", "tracked ignored\n")
        self.git("add", "-f", "ignored/tracked.txt")
        self.git("commit", "--quiet", "-m", "tracked denied fixtures")
        self.write("private/local.txt", "local secret\n")
        self.write("ignored/local.txt", "ignored local\n")

        manifest = self.inventory()
        denied = {
            item["path"]
            for item in manifest["skipped"]
            if item["reason"] == "deny_rule"
        }
        self.assertTrue({"private/tracked.txt", "ignored/tracked.txt"} <= denied)
        for path in ("private/local.txt", "ignored/local.txt"):
            with self.subTest(path=path), self.assertRaisesRegex(
                ai_inputs.InventoryError,
                "deny rules take precedence",
            ):
                self.inventory([path])

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks are required")
    def test_symlink_gitlink_and_symlinked_parent_never_enter_inventory(self) -> None:
        outside = self.base / "outside"
        outside.mkdir()
        (outside / "secret.txt").write_text("outside\n", encoding="utf-8")
        os.symlink(outside / "secret.txt", self.repo / "tracked-link")
        self.git("add", "tracked-link")
        head = self.git("rev-parse", "HEAD").stdout.strip()
        self.git(
            "update-index",
            "--add",
            "--cacheinfo",
            f"160000,{head},vendor/submodule",
        )
        manifest = self.inventory()
        skipped = {(item["path"], item["reason"]) for item in manifest["skipped"]}
        self.assertIn(("tracked-link", "git_mode_120000"), skipped)
        self.assertIn(("vendor/submodule", "git_mode_160000"), skipped)

        os.symlink(outside / "secret.txt", self.repo / "untracked-link")
        with self.assertRaises(ai_inputs.InventoryError):
            self.inventory(["untracked-link"])

        self.write("real-parent/file.py", "inside\n")
        self.git("add", "real-parent/file.py")
        self.git("commit", "--quiet", "-m", "parent symlink fixture")
        shutil.rmtree(self.repo / "real-parent")
        os.symlink(outside, self.repo / "real-parent")
        with self.assertRaisesRegex(ai_inputs.InventoryError, "parent-directory symlink"):
            self.inventory()

    def test_unmerged_index_is_rejected(self) -> None:
        object_ids = []
        for content in ("base\n", "ours\n", "theirs\n"):
            object_ids.append(
                self.git("hash-object", "-w", "--stdin", input_text=content).stdout.strip()
            )
        index_info = "".join(
            f"100644 {object_id} {stage}\tconflict.py\n"
            for stage, object_id in enumerate(object_ids, start=1)
        )
        self.git("update-index", "--index-info", input_text=index_info)
        with self.assertRaisesRegex(ai_inputs.InventoryError, "unmerged Git paths"):
            self.inventory()

    def test_high_confidence_secret_in_normal_tracked_file_fails_before_copy(self) -> None:
        self.write(
            "backend/accidental.py",
            'TOKEN = "' + "sk-" + "proj-" + "abcdefghijklmnopqrstuvwxyz123456" + '"\n',
        )
        self.git("add", "backend/accidental.py")
        with self.assertRaisesRegex(ai_inputs.InventoryError, "high-confidence secret"):
            self.inventory()

    def test_secret_scan_and_hash_share_one_authenticated_open(self) -> None:
        self.write("draft/allowed.py", "allowed untracked bytes\n")
        original_open = ai_inputs.open_repository_file
        open_counts: dict[str, int] = {}

        def counting_open(root: Path, relative_path: str) -> int:
            open_counts[relative_path] = open_counts.get(relative_path, 0) + 1
            return original_open(root, relative_path)

        with mock.patch.object(
            ai_inputs,
            "open_repository_file",
            side_effect=counting_open,
        ):
            manifest = self.inventory(["draft/allowed.py"])

        files = self.file_map(manifest)
        self.assertIn("tracked.txt", files)
        self.assertIn("draft/allowed.py", files)
        self.assertEqual(open_counts["tracked.txt"], 1)
        self.assertEqual(open_counts["draft/allowed.py"], 1)

    def test_shadow_is_independent_read_only_verified_and_activation_is_atomic(self) -> None:
        manifest = self.inventory()
        cache = self.repo / ".codebase-memory"
        shadow = ai_inputs.create_shadow(self.repo, cache, manifest)
        self.assertEqual(shadow.parent.name, manifest["inventory_sha256"])
        source = self.repo / "tracked.txt"
        linked = shadow / "tracked.txt"
        self.assertNotEqual((source.stat().st_dev, source.stat().st_ino), (linked.stat().st_dev, linked.stat().st_ino))
        self.assertFalse(linked.is_symlink())
        self.assertEqual(stat.S_IMODE(linked.stat().st_mode), 0o400)
        self.assertEqual(stat.S_IMODE(shadow.stat().st_mode), 0o500)
        ai_inputs.verify_shadow(cache, shadow)

        ai_inputs.activate_shadow(cache, shadow)
        pointer = cache / "current-input.json"
        before = pointer.read_bytes()
        self.assertEqual(stat.S_IMODE(pointer.stat().st_mode), 0o600)
        self.assertEqual(ai_inputs.current_shadow(cache), shadow.resolve())
        with self.assertRaises(ai_inputs.InventoryError):
            ai_inputs.activate_shadow(cache, self.base / "outside-shadow")
        self.assertEqual(pointer.read_bytes(), before)

        generation_manifest = shadow.parent / "manifest.json"
        original_manifest = generation_manifest.read_bytes()
        tampered = json.loads(original_manifest)
        tampered["approved_file_count"] += 1
        generation_manifest.write_text(json.dumps(tampered), encoding="utf-8")
        with self.assertRaisesRegex(ai_inputs.InventoryError, "count is inconsistent"):
            ai_inputs.current_shadow(cache)
        self.assertEqual(pointer.read_bytes(), before)
        generation_manifest.write_bytes(original_manifest)
        generation_manifest.chmod(0o600)

        source.write_text("source changed after snapshot\n", encoding="utf-8")
        self.assertEqual(ai_inputs.current_shadow(cache), shadow.resolve())
        linked.chmod(0o600)
        linked.write_text("tampered shadow\n", encoding="utf-8")
        with self.assertRaisesRegex(ai_inputs.InventoryError, "differs from manifest"):
            ai_inputs.current_shadow(cache)

    def test_orphan_shadow_is_rebuilt_and_snapshot_must_exactly_match_manifest(self) -> None:
        manifest = self.inventory()
        cache = self.repo / ".codebase-memory"
        orphan = cache / "inputs" / manifest["inventory_sha256"]
        (orphan / "files").mkdir(parents=True)
        (orphan / "files" / "unexpected.txt").write_text("orphan\n", encoding="utf-8")

        shadow = ai_inputs.create_shadow(self.repo, cache, manifest)
        self.assertFalse((shadow / "unexpected.txt").exists())
        self.assertTrue(
            (orphan / "manifest.json").is_file()
        )

        manifest_path = cache / "manifest-for-snapshot.json"
        ai_inputs.atomic_write_json(manifest_path, manifest)
        snapshot = cache / "snapshot.xml"
        expected_paths = [item["path"] for item in manifest["files"]]
        snapshot.write_text(
            "<files>"
            + "".join(
                f'<file path="{path}">content</file>' for path in expected_paths
            )
            + "</files>\n",
            encoding="utf-8",
        )
        self.assertEqual(
            ai_inputs.validate_snapshot(manifest_path, snapshot),
            len(expected_paths),
        )
        snapshot.write_text(
            '<files><file path="untracked.txt">content</file></files>\n',
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ai_inputs.InventoryError, "differ from its manifest"):
            ai_inputs.validate_snapshot(manifest_path, snapshot)

        graph_result = cache / "graph-result.json"
        graph_result.write_text(
            json.dumps(
                {
                    "columns": ["f.file_path"],
                    "rows": [[expected_paths[0]]],
                    "total": 1,
                }
            ),
            encoding="utf-8",
        )
        self.assertEqual(
            ai_inputs.validate_graph_paths(manifest_path, graph_result),
            1,
        )
        graph_result.write_text(
            json.dumps(
                {
                    "columns": ["f.file_path"],
                    "rows": [["untracked.txt"]],
                    "total": 1,
                }
            ),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ai_inputs.InventoryError, "outside its manifest"):
            ai_inputs.validate_graph_paths(manifest_path, graph_result)

    def test_negated_custom_ignore_rule_fails_closed(self) -> None:
        self.write(".denyignore", "private/**\n!private/allowed.txt\n")
        with self.assertRaisesRegex(ai_inputs.InventoryError, "forbidden negation"):
            self.inventory()

    def test_hardlinked_source_and_unsafe_output_targets_fail_closed(self) -> None:
        os.link(self.repo / "tracked.txt", self.base / "external-hardlink")
        with self.assertRaisesRegex(ai_inputs.InventoryError, "multiple hard links"):
            self.inventory()

        (self.base / "external-hardlink").unlink()
        manifest = self.inventory()
        with self.assertRaisesRegex(ai_inputs.InventoryError, "repository .codebase-memory"):
            ai_inputs.create_shadow(self.repo, self.repo / "arbitrary-cache", manifest)

        protected = self.repo / "protected.txt"
        protected.write_text("do not overwrite\n", encoding="utf-8")
        completed = subprocess.run(
            [
                os.sys.executable,
                str(HELPER_PATH),
                "inventory",
                "--repo-root",
                str(self.repo),
                "--ignore-file",
                str(self.repo / ".denyignore"),
                "--manifest",
                str(protected),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
            check=False,
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(protected.read_text(encoding="utf-8"), "do not overwrite\n")

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks are required")
    def test_controlled_nested_symlinks_never_write_or_delete_outside_repo(self) -> None:
        manifest = self.inventory()
        cache = self.repo / ".codebase-memory"
        cache.mkdir()
        external_inputs = self.base / "external-inputs"
        external_inputs.mkdir()
        os.symlink(external_inputs, cache / "inputs")
        with self.assertRaisesRegex(ai_inputs.InventoryError, "real directory"):
            ai_inputs.create_shadow(self.repo, cache, manifest)
        self.assertEqual(list(external_inputs.iterdir()), [])

        (cache / "inputs").unlink()
        shadow = ai_inputs.create_shadow(self.repo, cache, manifest)
        ai_inputs.activate_shadow(cache, shadow)
        real_inputs = cache / "real-inputs"
        (cache / "inputs").rename(real_inputs)
        sentinel_generation = external_inputs / ("b" * 64)
        sentinel_generation.mkdir()
        sentinel = sentinel_generation / "sentinel.txt"
        sentinel.write_text("keep\n", encoding="utf-8")
        os.symlink(external_inputs, cache / "inputs")
        with self.assertRaisesRegex(ai_inputs.InventoryError, "real directory"):
            ai_inputs.cleanup_inactive_generations(cache)
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep\n")

        context = self.repo / ".ai-context"
        context.mkdir()
        external_snapshots = self.base / "external-snapshots"
        external_snapshots.mkdir()
        external_bundle = external_snapshots / ("c" * 64)
        external_bundle.mkdir()
        external_sentinel = external_bundle / "sentinel.txt"
        external_sentinel.write_text("keep\n", encoding="utf-8")
        os.symlink(external_snapshots, context / "snapshots")
        with self.assertRaisesRegex(ai_inputs.InventoryError, "real directory"):
            ai_inputs.prepare_context_layout(self.repo)
        self.assertEqual(external_sentinel.read_text(encoding="utf-8"), "keep\n")

    def test_materialized_snapshot_input_is_independent_read_only_and_verified(self) -> None:
        manifest = self.inventory()
        context = ai_inputs.prepare_context_layout(self.repo)
        build_dir = Path(tempfile.mkdtemp(prefix=".building.", dir=str(context)))
        manifest_path = build_dir / "manifest.json"
        ai_inputs.atomic_write_json(manifest_path, manifest)
        input_root = build_dir / "input-root"

        materialized = ai_inputs.materialize_snapshot_input(
            self.repo,
            manifest_path,
            input_root,
        )
        source = self.repo / "tracked.txt"
        copied = materialized / "tracked.txt"
        self.assertNotEqual(
            (source.stat().st_dev, source.stat().st_ino),
            (copied.stat().st_dev, copied.stat().st_ino),
        )
        self.assertEqual(stat.S_IMODE(copied.stat().st_mode), 0o400)
        self.assertEqual(stat.S_IMODE(materialized.stat().st_mode), 0o500)
        before = copied.read_bytes()
        source.write_text("changed after materialization\n", encoding="utf-8")
        self.assertEqual(copied.read_bytes(), before)
        ai_inputs.validate_shadow_contents(materialized, manifest)

        ai_inputs.remove_snapshot_input(self.repo, input_root)
        self.assertFalse(input_root.exists())

    def test_context_bundle_publication_authenticates_snapshot_and_activates_atomically(self) -> None:
        manifest = self.inventory()
        context = ai_inputs.prepare_context_layout(self.repo)
        build_dir = Path(tempfile.mkdtemp(prefix=".building.", dir=str(context)))
        manifest_path = build_dir / "manifest.json"
        ai_inputs.atomic_write_json(manifest_path, manifest)
        snapshot_path = build_dir / "repomix.xml"
        snapshot_path.write_text(
            "<files>"
            + "".join(
                f'<file path="{item["path"]}">content</file>'
                for item in manifest["files"]
            )
            + "</files>\n",
            encoding="utf-8",
        )
        snapshot_path.chmod(0o600)
        snapshot_sha = hashlib.sha256(snapshot_path.read_bytes()).hexdigest()
        config_sha = "a" * 64
        package_sha = "b" * 64
        lock_sha = "c" * 64
        digest = hashlib.sha256()
        for label, value in (
            ("inventory", manifest["inventory_sha256"]),
            ("config", config_sha),
            ("snapshot", snapshot_sha),
            ("runtime_package", package_sha),
            ("runtime_lock", lock_sha),
            ("repomix", "1.17.0"),
            ("node", "v24.14.0"),
            ("npm", "11.5.1"),
        ):
            digest.update(label.encode("ascii") + b"\0" + value.encode("ascii") + b"\0")
        bundle_id = digest.hexdigest()
        provenance = {
            "schema_version": 1,
            "bundle_id": bundle_id,
            "inventory_sha256": manifest["inventory_sha256"],
            "profile": manifest["profile"],
            "packed_file_count": len(manifest["files"]),
            "config_sha256": config_sha,
            "snapshot_sha256": snapshot_sha,
            "runtime_package_sha256": package_sha,
            "runtime_lock_sha256": lock_sha,
            "repomix_version": "1.17.0",
            "repomix_integrity": "sha512-test",
            "node_version": "v24.14.0",
            "npm_version": "11.5.1",
        }
        provenance_path = build_dir / "provenance.json"
        ai_inputs.atomic_write_json(provenance_path, provenance)

        bundle = ai_inputs.publish_context_bundle(
            self.repo,
            build_dir,
            bundle_id,
            len(manifest["files"]),
        )
        self.assertEqual(bundle, context / "snapshots" / bundle_id)
        self.assertFalse(build_dir.exists())
        current = json.loads((context / "current.json").read_text(encoding="utf-8"))
        self.assertEqual(current["bundle_id"], bundle_id)
        self.assertEqual(current["snapshot_sha256"], snapshot_sha)
        self.assertEqual((context / "repomix.xml").resolve(), bundle / "repomix.xml")
        self.assertEqual(
            (context / "repomix-input-manifest.json").resolve(),
            bundle / "manifest.json",
        )

        malformed = context / "snapshots" / ("f" * 64)
        malformed.mkdir(mode=0o700)
        (malformed / "unexpected.txt").write_text("keep current\n", encoding="utf-8")
        second_build = Path(tempfile.mkdtemp(prefix=".building.", dir=str(context)))
        shutil.copy2(bundle / "manifest.json", second_build / "manifest.json")
        shutil.copy2(bundle / "repomix.xml", second_build / "repomix.xml")
        (second_build / "manifest.json").chmod(0o600)
        (second_build / "repomix.xml").chmod(0o600)
        second_config_sha = "d" * 64
        second_digest = hashlib.sha256()
        for label, value in (
            ("inventory", manifest["inventory_sha256"]),
            ("config", second_config_sha),
            ("snapshot", snapshot_sha),
            ("runtime_package", package_sha),
            ("runtime_lock", lock_sha),
            ("repomix", "1.17.0"),
            ("node", "v24.14.0"),
            ("npm", "11.5.1"),
        ):
            second_digest.update(
                label.encode("ascii") + b"\0" + value.encode("ascii") + b"\0"
            )
        second_bundle_id = second_digest.hexdigest()
        second_provenance = dict(provenance)
        second_provenance.update(
            {"bundle_id": second_bundle_id, "config_sha256": second_config_sha}
        )
        ai_inputs.atomic_write_json(
            second_build / "provenance.json",
            second_provenance,
        )
        current_before = (context / "current.json").read_bytes()
        active_snapshot_before = (context / "repomix.xml").resolve()
        with self.assertRaisesRegex(ai_inputs.InventoryError, "retire"):
            ai_inputs.publish_context_bundle(
                self.repo,
                second_build,
                second_bundle_id,
                len(manifest["files"]),
            )
        self.assertEqual((context / "current.json").read_bytes(), current_before)
        self.assertEqual((context / "repomix.xml").resolve(), active_snapshot_before)

    def test_context_bundle_publication_serializes_two_processes(self) -> None:
        manifest = self.inventory()
        context = ai_inputs.prepare_context_layout(self.repo)
        first_build, first_id = self.publishable_context_build(
            context,
            manifest,
            "1" * 64,
        )
        second_build, second_id = self.publishable_context_build(
            context,
            manifest,
            "2" * 64,
        )
        markers = [context / ".publisher-one.ready", context / ".publisher-two.ready"]
        driver = "\n".join(
            (
                "import importlib.util, pathlib, sys",
                "spec = importlib.util.spec_from_file_location('publisher_helper', sys.argv[1])",
                "module = importlib.util.module_from_spec(spec)",
                "spec.loader.exec_module(module)",
                "pathlib.Path(sys.argv[6]).write_text('ready\\n', encoding='utf-8')",
                "module.publish_context_bundle(pathlib.Path(sys.argv[2]), pathlib.Path(sys.argv[3]), sys.argv[4], int(sys.argv[5]))",
            )
        )
        publication_token = ai_inputs.acquire_context_publication_lock(
            self.repo,
            os.getpid(),
        )
        released = False
        processes: list[subprocess.Popen[str]] = []
        try:
            for build_dir, bundle_id, marker in (
                (first_build, first_id, markers[0]),
                (second_build, second_id, markers[1]),
            ):
                processes.append(
                    subprocess.Popen(
                        [
                            sys.executable,
                            "-c",
                            driver,
                            str(HELPER_PATH),
                            str(self.repo),
                            str(build_dir),
                            bundle_id,
                            str(len(manifest["files"])),
                            str(marker),
                        ],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        encoding="utf-8",
                        env=os.environ.copy(),
                    )
                )
            deadline = time.monotonic() + 10.0
            while not all(marker.exists() for marker in markers):
                exited = [process.poll() for process in processes]
                if any(code is not None for code in exited):
                    self.fail(f"publisher exited before contending for the lock: {exited}")
                if time.monotonic() >= deadline:
                    self.fail("publishers did not reach the publication lock")
                time.sleep(0.02)
            time.sleep(0.1)
            self.assertFalse(
                (context / "current.json").exists(),
                "a publisher bypassed the held publication lock",
            )
            self.assertTrue(all(process.poll() is None for process in processes))
            ai_inputs.release_context_publication_lock(
                self.repo,
                publication_token,
            )
            released = True

            for process in processes:
                stdout, stderr = process.communicate(timeout=15)
                self.assertEqual(process.returncode, 0, f"{stdout}\n{stderr}")
        finally:
            if not released:
                ai_inputs.release_context_publication_lock(
                    self.repo,
                    publication_token,
                )
            for process in processes:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)

        current = json.loads((context / "current.json").read_text(encoding="utf-8"))
        active_id = current["bundle_id"]
        self.assertIn(active_id, {first_id, second_id})
        active_bundle = context / "snapshots" / active_id
        self.assertTrue(active_bundle.is_dir())
        self.assertEqual(
            (context / "repomix.xml").resolve(),
            active_bundle / "repomix.xml",
        )
        self.assertEqual(
            (context / "repomix-input-manifest.json").resolve(),
            active_bundle / "manifest.json",
        )
        self.assertEqual(
            (context / current["snapshot"]).resolve(),
            active_bundle / "repomix.xml",
        )
        self.assertEqual(
            (context / current["manifest"]).resolve(),
            active_bundle / "manifest.json",
        )
        self.assertTrue((context / current["provenance"]).is_file())
        self.assertTrue((context / "snapshots" / first_id).is_dir())
        self.assertTrue((context / "snapshots" / second_id).is_dir())

    def test_snapshot_size_limit_is_checked_before_decoding(self) -> None:
        manifest = self.inventory()
        cache = ai_inputs.prepare_cache_layout(
            self.repo,
            self.repo / ".codebase-memory",
        )
        manifest_path = cache / "manifest.json"
        ai_inputs.atomic_write_json(manifest_path, manifest)
        snapshot_path = cache / "snapshot.xml"
        snapshot_path.write_bytes(b"x" * 17)
        with mock.patch.object(ai_inputs, "MAX_SNAPSHOT_BYTES", 16):
            with self.assertRaisesRegex(ai_inputs.InventoryError, "oversized"):
                ai_inputs.validate_snapshot(manifest_path, snapshot_path)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks are required")
    def test_controlled_locks_reject_symlinks_and_require_owner_token(self) -> None:
        cache = ai_inputs.prepare_cache_layout(
            self.repo,
            self.repo / ".codebase-memory",
        )
        external = self.base / "external-lock"
        external.mkdir()
        sentinel = external / "owner.json"
        sentinel.write_text('{"pid":99999999,"token":"' + "a" * 64 + '"}\n')
        os.symlink(external, cache / ".index.lock")
        with self.assertRaisesRegex(ai_inputs.InventoryError, "not a real directory"):
            ai_inputs.acquire_controlled_lock(
                self.repo,
                cache,
                "index",
                os.getpid(),
            )
        self.assertTrue(sentinel.exists())

        (cache / ".index.lock").unlink()
        token = ai_inputs.acquire_controlled_lock(
            self.repo,
            cache,
            "index",
            os.getpid(),
        )
        with self.assertRaisesRegex(ai_inputs.InventoryError, "another process"):
            ai_inputs.release_controlled_lock(
                self.repo,
                cache,
                "index",
                "b" * 64,
            )
        self.assertTrue((cache / ".index.lock").is_dir())
        ai_inputs.release_controlled_lock(self.repo, cache, "index", token)
        self.assertFalse((cache / ".index.lock").exists())

        orphan = cache / ".index.lock"
        orphan.mkdir(mode=0o700)
        old = max(1, int(orphan.stat().st_mtime) - 10)
        os.utime(orphan, (old, old))
        recovered_token = ai_inputs.acquire_controlled_lock(
            self.repo,
            cache,
            "index",
            os.getpid(),
        )
        ai_inputs.release_controlled_lock(
            self.repo,
            cache,
            "index",
            recovered_token,
        )
        self.assertFalse(orphan.exists())

        interrupted = cache / ".index.lock"
        interrupted.mkdir(mode=0o700)
        pending_owner = interrupted / (".owner.pending." + "c" * 64)
        pending_owner.write_text('{"pid":', encoding="utf-8")
        pending_owner.chmod(0o600)
        old = max(1, int(interrupted.stat().st_mtime) - 10)
        os.utime(interrupted, (old, old))
        interrupted_token = ai_inputs.acquire_controlled_lock(
            self.repo,
            cache,
            "index",
            os.getpid(),
        )
        ai_inputs.release_controlled_lock(
            self.repo,
            cache,
            "index",
            interrupted_token,
        )
        self.assertFalse(interrupted.exists())

        released_token = ai_inputs.acquire_controlled_lock(
            self.repo,
            cache,
            "index",
            os.getpid(),
        )
        original_stat = ai_inputs.os.stat
        original_unlink = ai_inputs.os.unlink
        original_rmdir = ai_inputs.os.rmdir
        release_race_triggered = False

        def stat_then_owner_releases(path: Any, *args: Any, **kwargs: Any) -> os.stat_result:
            nonlocal release_race_triggered
            result = original_stat(path, *args, **kwargs)
            if (
                path == ".index.lock"
                and kwargs.get("dir_fd") is not None
                and not release_race_triggered
            ):
                original_unlink(cache / ".index.lock" / "owner.json")
                original_rmdir(cache / ".index.lock")
                release_race_triggered = True
            return result

        with mock.patch.object(
            ai_inputs.os,
            "stat",
            side_effect=stat_then_owner_releases,
        ):
            replacement_token = ai_inputs.acquire_controlled_lock(
                self.repo,
                cache,
                "index",
                os.getpid(),
            )
        self.assertTrue(release_race_triggered)
        self.assertNotEqual(released_token, replacement_token)
        ai_inputs.release_controlled_lock(
            self.repo,
            cache,
            "index",
            replacement_token,
        )

        stale = cache / ".index.lock"
        stale.mkdir(mode=0o700)
        (stale / "owner.json").write_text(
            json.dumps({"pid": 99_999_999, "token": "d" * 64}) + "\n",
            encoding="utf-8",
        )
        (stale / "owner.json").chmod(0o600)
        stale_race_triggered = False

        def unlink_after_other_waiter(path: Any, *args: Any, **kwargs: Any) -> None:
            nonlocal stale_race_triggered
            if (
                path == "owner.json"
                and kwargs.get("dir_fd") is not None
                and not stale_race_triggered
            ):
                original_unlink(path, *args, **kwargs)
                original_rmdir(stale)
                stale_race_triggered = True
            original_unlink(path, *args, **kwargs)

        with mock.patch.object(
            ai_inputs.os,
            "unlink",
            side_effect=unlink_after_other_waiter,
        ):
            stale_replacement_token = ai_inputs.acquire_controlled_lock(
                self.repo,
                cache,
                "index",
                os.getpid(),
            )
        self.assertTrue(stale_race_triggered)
        ai_inputs.release_controlled_lock(
            self.repo,
            cache,
            "index",
            stale_replacement_token,
        )

    @unittest.skipUnless(
        hasattr(os, "fchmod") and ai_inputs.current_user_id() is not None,
        "POSIX ownership and modes are required",
    )
    def test_controlled_layouts_enforce_owner_private_modes_and_fail_closed(self) -> None:
        cache = ai_inputs.prepare_cache_layout(
            self.repo,
            self.repo / ".codebase-memory",
        )
        inputs = cache / "inputs"
        cache.chmod(0o777)
        inputs.chmod(0o755)
        ai_inputs.controlled_cache_layout(cache, create=False)
        self.assertEqual(stat.S_IMODE(cache.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(inputs.stat().st_mode), 0o700)

        shadow = ai_inputs.create_shadow(self.repo, cache, self.inventory())
        generation = shadow.parent
        generation.chmod(0o775)
        shadow.chmod(0o755)
        ai_inputs.verify_shadow(cache, shadow)
        self.assertEqual(stat.S_IMODE(generation.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(shadow.stat().st_mode), 0o500)

        context = ai_inputs.prepare_context_layout(self.repo)
        snapshots = context / "snapshots"
        context.chmod(0o775)
        snapshots.chmod(0o755)
        ai_inputs.controlled_context_layout(self.repo, create=False)
        self.assertEqual(stat.S_IMODE(context.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(snapshots.stat().st_mode), 0o700)

        current_owner = ai_inputs.current_user_id()
        assert current_owner is not None
        with mock.patch.object(
            ai_inputs,
            "current_user_id",
            return_value=current_owner + 1,
        ), self.assertRaisesRegex(ai_inputs.InventoryError, "owned by the current user"):
            ai_inputs.controlled_cache_layout(cache, create=False)

        cache.chmod(0o777)
        with mock.patch.object(
            ai_inputs.os,
            "fchmod",
            side_effect=PermissionError("denied"),
        ), self.assertRaisesRegex(ai_inputs.InventoryError, "secure cache directory"):
            ai_inputs.controlled_cache_layout(cache, create=False)

    def test_named_profile_only_reduces_the_approved_inventory(self) -> None:
        self.write("backend/app.py", "backend\n")
        self.write("frontend/app.ts", "frontend\n")
        self.git("add", "backend/app.py", "frontend/app.ts")
        self.git("commit", "--quiet", "-m", "profile fixtures")
        profile_config = self.repo / "profiles.json"
        profile_config.write_text(
            json.dumps(
                {
                    "$schema": "narraverse.ai-context-profiles.v1",
                    "default": "backend",
                    "profiles": {
                        "backend": {
                            "include_paths": ["tracked.txt"],
                            "include_prefixes": ["backend/"],
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        manifest = ai_inputs.build_inventory(
            self.repo,
            self.repo / ".denyignore",
            [],
            profile_config,
            "backend",
        )
        self.assertEqual(manifest["profile"], "backend")
        self.assertTrue(ai_inputs.is_hex_digest(manifest["profile_config_sha256"], 64))
        self.assertEqual(
            set(self.file_map(manifest)),
            {"backend/app.py", "tracked.txt"},
        )
        self.assertIn(
            {"path": "frontend/app.ts", "reason": "profile_filter"},
            manifest["skipped"],
        )
        with self.assertRaisesRegex(ai_inputs.InventoryError, "unknown AI context profile"):
            ai_inputs.build_inventory(
                self.repo,
                self.repo / ".denyignore",
                [],
                profile_config,
                "missing",
            )


if __name__ == "__main__":
    unittest.main()
