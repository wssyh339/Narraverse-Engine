#!/usr/bin/env python3
"""Build a deny-filtered, Git-tracked input inventory for AI context tools."""

from __future__ import annotations

import argparse
import html
import hashlib
import json
import os
import re
import secrets
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unicodedata
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple


MANIFEST_SCHEMA_VERSION = 1
GLOB_META = set("*?[]{}!")
REGULAR_GIT_MODES = {"100644", "100755"}
NON_REGULAR_GIT_MODES = {"120000", "160000"}
MAX_FILE_COUNT = 20_000
MAX_FILE_BYTES = 1024 * 1024
MAX_TOTAL_BYTES = 100 * 1024 * 1024
MAX_SNAPSHOT_BYTES = 512 * 1024 * 1024
CONTROLLED_LOCKS = {"index": ".index.lock", "runtime": ".runtime-config.lock"}
CONTEXT_PUBLICATION_LOCK = ".publication.lock"
LOCK_ACQUIRE_TIMEOUT_SECONDS = 600.0
SECRET_PATTERNS = {
    "OpenAI-like API key": re.compile(rb"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"),
    "GitHub token": re.compile(
        rb"\b(?:github_pat_[A-Za-z0-9_]{20,}|gh[pousr]_[A-Za-z0-9]{36,})\b"
    ),
    "AWS access key": re.compile(rb"\bAKIA[0-9A-Z]{16}\b"),
    "private-key header": re.compile(
        rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
    ),
}
HARD_DENY_TOP_LEVEL = {
    ".ai-context",
    ".codebase-memory",
    ".git",
    ".logs",
    "backups",
    "data",
    "exports",
    "logs",
    "output",
    "outputs",
    "test-artifacts",
}
HARD_DENY_PREFIXES = {
    "backend/artifacts",
    "backend/data",
    "docs/archive",
    "docs/superpowers",
    "docs/test-reports",
    "frontend/dist",
    "frontend/node_modules",
}
HARD_DENY_SUFFIXES = {
    ".7z",
    ".backup",
    ".bak",
    ".db",
    ".db-shm",
    ".db-wal",
    ".docx",
    ".epub",
    ".key",
    ".p12",
    ".pdf",
    ".pem",
    ".pfx",
    ".sqlite",
    ".sqlite3",
    ".tar",
    ".tgz",
    ".zip",
}


class InventoryError(RuntimeError):
    pass


def is_hex_digest(value: Any, length: int) -> bool:
    return (
        isinstance(value, str)
        and len(value) == length
        and all(character in "0123456789abcdef" for character in value)
    )


def compute_inventory_sha(
    files: Sequence[Mapping[str, Any]],
    ignore_sha256: str,
    ignore_file: str,
    profile: str,
    profile_config_sha256: Optional[str],
) -> str:
    payload = {
        "files": list(files),
        "ignore_sha256": ignore_sha256,
        "ignore_file": ignore_file,
        "profile": profile,
        "profile_config_sha256": profile_config_sha256,
    }
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def run_git(root: Path, arguments: Sequence[str], check: bool = True) -> bytes:
    environment = os.environ.copy()
    environment["GIT_LITERAL_PATHSPECS"] = "1"
    environment["GIT_OPTIONAL_LOCKS"] = "0"
    completed = subprocess.run(
        ["git", "-C", str(root), *arguments],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=environment,
        check=False,
    )
    if check and completed.returncode != 0:
        message = completed.stderr.decode("utf-8", errors="replace").strip()
        raise InventoryError(f"git {' '.join(arguments)} failed: {message}")
    return completed.stdout


def split_nul(data: bytes) -> List[str]:
    values: List[str] = []
    for raw in data.split(b"\0"):
        if not raw:
            continue
        value = os.fsdecode(raw)
        try:
            value.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise InventoryError("non-UTF-8 repository paths are not supported") from exc
        values.append(value)
    return values


def ensure_repository(root: Path) -> Path:
    root = root.expanduser().resolve()
    if not root.is_dir():
        raise InventoryError(f"repository root does not exist: {root}")
    discovered = Path(
        os.fsdecode(run_git(root, ["rev-parse", "--show-toplevel"])).strip()
    ).resolve()
    if discovered != root:
        raise InventoryError(f"expected Git root {root}, discovered {discovered}")
    return root


def ensure_under(path: Path, parent: Path, label: str) -> Path:
    resolved = path.expanduser().resolve()
    try:
        resolved.relative_to(parent)
    except ValueError as exc:
        raise InventoryError(f"{label} escapes the repository: {path}") from exc
    return resolved


def lexical_absolute(path: Path) -> Path:
    """Normalize a path without resolving its final symlink target."""
    return Path(os.path.abspath(os.fspath(path.expanduser())))


def directory_open_flags() -> int:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    return flags


def current_user_id() -> Optional[int]:
    if hasattr(os, "geteuid"):
        return int(os.geteuid())
    if hasattr(os, "getuid"):
        return int(os.getuid())
    return None


def secure_directory_descriptor(
    descriptor: int,
    label: str,
    *,
    expected_mode: Optional[int] = None,
) -> os.stat_result:
    """Require current-user ownership and remove all group/other access."""
    opened = os.fstat(descriptor)
    if not stat.S_ISDIR(opened.st_mode):
        raise InventoryError(f"{label} must be a real directory")
    owner = current_user_id()
    if owner is not None and opened.st_uid != owner:
        raise InventoryError(f"{label} must be owned by the current user")
    if expected_mode is not None and expected_mode & ~0o700:
        raise InventoryError(f"{label} requested an unsafe directory mode")
    current_mode = stat.S_IMODE(opened.st_mode)
    desired_mode = (
        expected_mode if expected_mode is not None else current_mode & 0o700
    )
    if current_mode != desired_mode:
        try:
            os.fchmod(descriptor, desired_mode)
        except (AttributeError, OSError) as exc:
            raise InventoryError(f"could not secure {label} permissions") from exc
        opened = os.fstat(descriptor)
    actual_mode = stat.S_IMODE(opened.st_mode)
    if owner is not None and opened.st_uid != owner:
        raise InventoryError(f"{label} ownership changed while securing it")
    if actual_mode != desired_mode:
        raise InventoryError(f"{label} has an unexpected directory mode")
    return opened


def open_real_directory(
    path: Path,
    label: str,
    *,
    owner_private: bool = False,
    expected_mode: Optional[int] = None,
) -> Tuple[Path, int, os.stat_result]:
    """Open and authenticate a directory without following its final component."""
    path = lexical_absolute(path)
    path = path.parent.resolve() / path.name
    try:
        path_stat = path.lstat()
    except OSError as exc:
        raise InventoryError(f"{label} is missing: {path}") from exc
    if stat.S_ISLNK(path_stat.st_mode) or not stat.S_ISDIR(path_stat.st_mode):
        raise InventoryError(f"{label} must be a real directory: {path}")
    try:
        descriptor = os.open(str(path), directory_open_flags())
    except OSError as exc:
        raise InventoryError(f"could not safely open {label}: {path}") from exc
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISDIR(opened.st_mode)
            or (opened.st_dev, opened.st_ino) != (path_stat.st_dev, path_stat.st_ino)
        ):
            raise InventoryError(f"{label} changed while opening: {path}")
        if owner_private:
            opened = secure_directory_descriptor(
                descriptor,
                label,
                expected_mode=expected_mode,
            )
        current = path.lstat()
        if (
            stat.S_ISLNK(current.st_mode)
            or (current.st_dev, current.st_ino) != (opened.st_dev, opened.st_ino)
        ):
            raise InventoryError(f"{label} changed while validating: {path}")
    except BaseException:
        os.close(descriptor)
        raise
    return path, descriptor, opened


def require_real_directory(
    path: Path,
    label: str,
    *,
    owner_private: bool = False,
    expected_mode: Optional[int] = None,
) -> Path:
    """Require an authenticated real directory and optionally secure its mode."""
    path, descriptor, _opened = open_real_directory(
        path,
        label,
        owner_private=owner_private,
        expected_mode=expected_mode,
    )
    os.close(descriptor)
    return path


def ensure_direct_child_directory(
    parent: Path,
    name: str,
    label: str,
    *,
    create: bool,
    mode: Optional[int] = None,
    parent_owner_private: bool = False,
) -> Path:
    """Create or validate one controlled directory component without following it."""
    if not name or name in {".", ".."} or "/" in name or "\\" in name:
        raise InventoryError(f"{label} has an invalid directory name")
    parent, parent_descriptor, _parent_stat = open_real_directory(
        parent,
        f"{label} parent",
        owner_private=parent_owner_private,
    )
    child = parent / name
    try:
        try:
            child_stat = os.stat(
                name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            if not create:
                raise InventoryError(f"{label} is missing: {child}")
            try:
                os.mkdir(
                    name,
                    mode if mode is not None else 0o700,
                    dir_fd=parent_descriptor,
                )
            except FileExistsError:
                pass
            except OSError as exc:
                raise InventoryError(f"could not create {label}: {child}") from exc
            child_stat = os.stat(
                name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
        if stat.S_ISLNK(child_stat.st_mode) or not stat.S_ISDIR(child_stat.st_mode):
            raise InventoryError(f"{label} must be a real directory: {child}")
        try:
            child_descriptor = os.open(
                name,
                directory_open_flags(),
                dir_fd=parent_descriptor,
            )
        except OSError as exc:
            raise InventoryError(f"could not safely open {label}: {child}") from exc
        try:
            opened = os.fstat(child_descriptor)
            if (opened.st_dev, opened.st_ino) != (
                child_stat.st_dev,
                child_stat.st_ino,
            ):
                raise InventoryError(f"{label} changed while opening: {child}")
            opened = secure_directory_descriptor(
                child_descriptor,
                label,
                expected_mode=mode,
            )
            current = os.stat(
                name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
            if (
                stat.S_ISLNK(current.st_mode)
                or (current.st_dev, current.st_ino)
                != (opened.st_dev, opened.st_ino)
            ):
                raise InventoryError(f"{label} changed while validating: {child}")
        finally:
            os.close(child_descriptor)
    finally:
        os.close(parent_descriptor)
    return child


def controlled_cache_layout(
    cache_dir: Path,
    *,
    root: Optional[Path] = None,
    create: bool,
) -> Tuple[Path, Path]:
    """Validate the exact .codebase-memory/inputs managed-directory chain."""
    cache_dir = lexical_absolute(cache_dir)
    cache_dir = cache_dir.parent.resolve() / cache_dir.name
    if root is not None:
        root = ensure_repository(root)
        expected_cache = root / ".codebase-memory"
        if cache_dir != expected_cache:
            raise InventoryError("cache directory must be the repository .codebase-memory")
        cache_dir = ensure_direct_child_directory(
            root,
            ".codebase-memory",
            "cache directory",
            create=create,
            mode=0o700,
        )
    else:
        if cache_dir.name != ".codebase-memory":
            raise InventoryError("cache directory must be named .codebase-memory")
        repository_root = ensure_repository(cache_dir.parent)
        if cache_dir != repository_root / ".codebase-memory":
            raise InventoryError("cache directory is not attached to its Git repository root")
        cache_dir = ensure_direct_child_directory(
            repository_root,
            ".codebase-memory",
            "cache directory",
            create=False,
            mode=0o700,
        )
    inputs_dir = ensure_direct_child_directory(
        cache_dir,
        "inputs",
        "controlled inputs directory",
        create=create,
        mode=0o700,
        parent_owner_private=True,
    )
    return cache_dir, inputs_dir


def controlled_context_layout(root: Path, *, create: bool) -> Tuple[Path, Path]:
    """Validate the exact .ai-context/snapshots managed-directory chain."""
    root = ensure_repository(root)
    context_dir = ensure_direct_child_directory(
        root,
        ".ai-context",
        "AI context directory",
        create=create,
        mode=0o700,
    )
    snapshots_dir = ensure_direct_child_directory(
        context_dir,
        "snapshots",
        "AI context snapshots directory",
        create=create,
        mode=0o700,
        parent_owner_private=True,
    )
    return context_dir, snapshots_dir


def validate_protocol_path(value: str, label: str) -> str:
    if not value or value != value.strip():
        raise InventoryError(f"{label} must not be empty or padded with whitespace")
    if any(unicodedata.category(character) == "Cc" for character in value):
        raise InventoryError(f"{label} contains a control character")
    if value.startswith("#") or "\\" in value:
        raise InventoryError(f"{label} is incompatible with the input protocol")
    if any(character in GLOB_META for character in value):
        raise InventoryError(f"{label} must be an exact path without glob syntax")
    candidate = PurePosixPath(value)
    if candidate.is_absolute() or not candidate.parts:
        raise InventoryError(f"{label} must be repository-relative")
    if any(part in {"", ".", ".."} for part in candidate.parts):
        raise InventoryError(f"{label} contains an unsafe path component")
    return candidate.as_posix()


def is_hard_denied(path: str) -> bool:
    folded = PurePosixPath(path).as_posix().casefold()
    parts = PurePosixPath(folded).parts
    if not parts:
        return True
    if parts[0] in HARD_DENY_TOP_LEVEL:
        return True
    if any(folded == prefix or folded.startswith(prefix + "/") for prefix in HARD_DENY_PREFIXES):
        return True
    name = parts[-1]
    if name == ".env" or name.startswith(".env."):
        return True
    if name.startswith("credentials") and name.endswith(".json"):
        return True
    if name.startswith("secrets."):
        return True
    return any(name.endswith(suffix) for suffix in HARD_DENY_SUFFIXES)


def validate_ignore_file(root: Path, ignore_file: Path) -> Path:
    ignore_file = ensure_under(ignore_file, root, "ignore file")
    relative = ignore_file.relative_to(root).as_posix()
    repository_source(root, relative)
    if ignore_file.is_symlink() or not ignore_file.is_file():
        raise InventoryError(f"ignore file does not exist: {ignore_file}")
    return ignore_file


def validate_ignore_bytes(name: str, content: bytes) -> None:
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise InventoryError(f"{name} is not UTF-8") from exc
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("!"):
            raise InventoryError(
                f"{name}:{line_number} uses a forbidden negation rule"
            )


def repository_source(root: Path, relative_path: str) -> Path:
    """Return a source path only when every parent stays a real directory."""
    candidate = root
    parts = PurePosixPath(relative_path).parts
    for part in parts[:-1]:
        candidate = candidate / part
        try:
            component_stat = candidate.lstat()
        except FileNotFoundError:
            return root / relative_path
        if stat.S_ISLNK(component_stat.st_mode):
            raise InventoryError(
                f"tracked path crosses a parent-directory symlink: {relative_path}"
            )
        if not stat.S_ISDIR(component_stat.st_mode):
            raise InventoryError(
                f"tracked path parent is not a directory: {relative_path}"
            )
    return root / relative_path


def open_repository_file(root: Path, relative_path: str) -> int:
    """Open a repository file without following any path-component symlink."""
    if os.open not in os.supports_dir_fd or not hasattr(os, "O_NOFOLLOW"):
        raise InventoryError(
            "this platform cannot provide symlink-safe repository reads"
        )
    parts = PurePosixPath(relative_path).parts
    directory_flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        directory_flags |= os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        directory_flags |= os.O_NOFOLLOW
    current_descriptor = os.open(str(root), directory_flags)
    try:
        for part in parts[:-1]:
            next_descriptor = os.open(
                part,
                directory_flags,
                dir_fd=current_descriptor,
            )
            os.close(current_descriptor)
            current_descriptor = next_descriptor
        file_flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            file_flags |= os.O_NOFOLLOW
        descriptor = os.open(parts[-1], file_flags, dir_fd=current_descriptor)
    except OSError as exc:
        raise InventoryError(
            f"could not safely open repository input {relative_path}: {exc}"
        ) from exc
    finally:
        os.close(current_descriptor)
    opened_stat = os.fstat(descriptor)
    if not stat.S_ISREG(opened_stat.st_mode):
        os.close(descriptor)
        raise InventoryError(f"repository input is not a regular file: {relative_path}")
    if opened_stat.st_nlink > 1:
        os.close(descriptor)
        raise InventoryError(
            f"repository input has multiple hard links and is rejected: {relative_path}"
        )
    if opened_stat.st_size > MAX_FILE_BYTES:
        os.close(descriptor)
        raise InventoryError(
            f"repository input exceeds {MAX_FILE_BYTES} bytes: {relative_path}"
        )
    return descriptor


def inspect_repository_file(root: Path, relative_path: str) -> Tuple[str, int, int]:
    """Hash and secret-scan exactly the bytes read through one authenticated fd."""
    descriptor = open_repository_file(root, relative_path)
    try:
        opened_stat = os.fstat(descriptor)
        digest = hashlib.sha256()
        chunks: List[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            chunks.append(chunk)
            total += len(chunk)
        completed_stat = os.fstat(descriptor)
        initial_identity = (
            opened_stat.st_dev,
            opened_stat.st_ino,
            opened_stat.st_size,
            stat.S_IMODE(opened_stat.st_mode),
            getattr(opened_stat, "st_mtime_ns", None),
            getattr(opened_stat, "st_ctime_ns", None),
        )
        completed_identity = (
            completed_stat.st_dev,
            completed_stat.st_ino,
            completed_stat.st_size,
            stat.S_IMODE(completed_stat.st_mode),
            getattr(completed_stat, "st_mtime_ns", None),
            getattr(completed_stat, "st_ctime_ns", None),
        )
        if initial_identity != completed_identity or total != opened_stat.st_size:
            raise InventoryError(f"repository input changed while reading: {relative_path}")
        content = b"".join(chunks)
        matches = [
            name for name, pattern in SECRET_PATTERNS.items() if pattern.search(content)
        ]
        if matches:
            raise InventoryError(
                f"high-confidence secret detected in {relative_path}: "
                f"{', '.join(matches)}"
            )
        return (
            digest.hexdigest(),
            total,
            stat.S_IMODE(completed_stat.st_mode),
        )
    finally:
        os.close(descriptor)


def read_repository_file(root: Path, relative_path: str) -> bytes:
    descriptor = open_repository_file(root, relative_path)
    chunks: List[bytes] = []
    try:
        while True:
            chunk = os.read(descriptor, 64 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
    finally:
        os.close(descriptor)
    return b"".join(chunks)


def tracked_entries(root: Path) -> Tuple[Dict[str, Dict[str, str]], List[str]]:
    output = run_git(root, ["ls-files", "--stage", "-z"])
    entries: Dict[str, Dict[str, str]] = {}
    conflicts: List[str] = []
    for raw_record in output.split(b"\0"):
        if not raw_record:
            continue
        try:
            metadata, raw_path = raw_record.split(b"\t", 1)
            mode_bytes, object_id_bytes, stage_bytes = metadata.split(b" ", 2)
        except ValueError as exc:
            raise InventoryError("could not parse git ls-files --stage output") from exc
        path = validate_protocol_path(os.fsdecode(raw_path), "tracked path")
        mode = mode_bytes.decode("ascii")
        object_id = object_id_bytes.decode("ascii")
        stage = stage_bytes.decode("ascii")
        if stage != "0":
            conflicts.append(path)
            continue
        if path in entries:
            raise InventoryError(f"duplicate tracked path: {path}")
        entries[path] = {"mode": mode, "index_oid": object_id}
    return entries, sorted(set(conflicts))


def committed_or_staged_added_paths(root: Path) -> Set[str]:
    committed: Set[str] = set()
    head_check = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--verify", "HEAD"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"},
        check=False,
    )
    if head_check.returncode == 0:
        committed.update(split_nul(run_git(root, ["ls-tree", "-r", "--name-only", "-z", "HEAD"])))
    staged_added = split_nul(
        run_git(
            root,
            ["diff", "--cached", "--name-only", "--diff-filter=A", "-z"],
        )
    )
    return committed.union(staged_added)


def ignored_tracked_paths(root: Path, ignore_file: Path) -> Set[str]:
    custom = split_nul(
        run_git(
            root,
            [
                "ls-files",
                "-c",
                "-i",
                "-z",
                f"--exclude-from={ignore_file}",
            ],
        )
    )
    standard = split_nul(
        run_git(root, ["ls-files", "-c", "-i", "-z", "--exclude-standard"])
    )
    return set(custom).union(standard)


def is_ignored_untracked(root: Path, ignore_file: Path, path: str) -> bool:
    environment = os.environ.copy()
    environment["GIT_OPTIONAL_LOCKS"] = "0"
    standard = subprocess.run(
        ["git", "-C", str(root), "check-ignore", "--no-index", "--stdin", "-z"],
        input=path.encode("utf-8") + b"\0",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=environment,
        check=False,
    )
    if standard.returncode == 0:
        return True
    if standard.returncode != 1:
        raise InventoryError(f"git check-ignore failed for {path}")
    custom = run_git(
        root,
        [
            "ls-files",
            "--others",
            "-i",
            "-z",
            f"--exclude-from={ignore_file}",
            "--",
            path,
        ],
    )
    return bool(custom)


def ensure_exact_untracked(root: Path, path: str) -> None:
    listed = split_nul(run_git(root, ["ls-files", "--others", "-z", "--", path]))
    if listed != [path]:
        raise InventoryError(f"allowed path is not an exact top-level untracked file: {path}")


def hash_regular_file(path: Path) -> Tuple[str, int, int]:
    file_stat = path.lstat()
    if path.is_symlink() or not stat.S_ISREG(file_stat.st_mode):
        raise InventoryError(f"input is not a regular non-symlink file: {path}")
    digest = hashlib.sha256()
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(str(path), flags)
    try:
        opened_stat = os.fstat(descriptor)
        if not stat.S_ISREG(opened_stat.st_mode):
            raise InventoryError(f"input changed type while reading: {path}")
        if (
            opened_stat.st_dev != file_stat.st_dev
            or opened_stat.st_ino != file_stat.st_ino
        ):
            raise InventoryError(f"input changed identity while opening: {path}")
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
    finally:
        os.close(descriptor)
    return digest.hexdigest(), opened_stat.st_size, stat.S_IMODE(opened_stat.st_mode)


def git_head(root: Path) -> Optional[str]:
    completed = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if completed.returncode != 0:
        return None
    return completed.stdout.decode("ascii", errors="strict").strip()


def build_inventory(
    root: Path,
    ignore_file: Path,
    allow_untracked: Sequence[str],
    profile_config: Optional[Path] = None,
    profile_name: Optional[str] = None,
) -> Dict[str, Any]:
    root = ensure_repository(root)
    ignore_file = validate_ignore_file(root, ignore_file)
    ignore_relative = ignore_file.relative_to(root).as_posix()
    ignore_bytes = read_repository_file(root, ignore_relative)
    validate_ignore_bytes(ignore_file.name, ignore_bytes)
    ignore_digest = hashlib.sha256(ignore_bytes).hexdigest()
    tracked, conflicts = tracked_entries(root)
    if conflicts:
        raise InventoryError(f"unmerged Git paths are not allowed: {conflicts}")
    eligible_index_paths = committed_or_staged_added_paths(root)
    skipped: List[Dict[str, str]] = []
    files: List[Dict[str, Any]] = []

    descriptor, immutable_ignore_name = tempfile.mkstemp(
        prefix="narraverse-ai-ignore-",
    )
    immutable_ignore = Path(immutable_ignore_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(ignore_bytes)
            handle.flush()
            os.fsync(handle.fileno())
        ignored = ignored_tracked_paths(root, immutable_ignore)

        for path in sorted(tracked):
            metadata = tracked[path]
            mode = metadata["mode"]
            if path not in eligible_index_paths:
                skipped.append({"path": path, "reason": "intent_to_add"})
                continue
            if is_hard_denied(path) or path in ignored:
                skipped.append({"path": path, "reason": "deny_rule"})
                continue
            if mode in NON_REGULAR_GIT_MODES:
                skipped.append({"path": path, "reason": f"git_mode_{mode}"})
                continue
            if mode not in REGULAR_GIT_MODES:
                raise InventoryError(f"unsupported Git mode {mode} for {path}")
            source = repository_source(root, path)
            if not os.path.lexists(str(source)):
                skipped.append({"path": path, "reason": "deleted_from_worktree"})
                continue
            digest, size, file_mode = inspect_repository_file(root, path)
            files.append(
                {
                    "path": path,
                    "origin": "tracked",
                    "index_oid": metadata["index_oid"],
                    "sha256": digest,
                    "size": size,
                    "mode": file_mode,
                    "shadow_mode": 0o500 if file_mode & 0o111 else 0o400,
                }
            )

        approved_paths = {item["path"] for item in files}
        explicit_untracked: List[str] = []
        for raw_path in allow_untracked:
            path = validate_protocol_path(raw_path, "allowed untracked path")
            if is_hard_denied(path):
                raise InventoryError(f"deny rules take precedence over explicit allow: {path}")
            if path in tracked:
                if path not in approved_paths:
                    raise InventoryError(
                        f"tracked path is denied and cannot be allowed: {path}"
                    )
                continue
            if path in approved_paths:
                continue
            ensure_exact_untracked(root, path)
            if is_ignored_untracked(root, immutable_ignore, path):
                raise InventoryError(
                    f"deny rules take precedence over explicit allow: {path}"
                )
            repository_source(root, path)
            digest, size, file_mode = inspect_repository_file(root, path)
            files.append(
                {
                    "path": path,
                    "origin": "explicit_untracked",
                    "index_oid": None,
                    "sha256": digest,
                    "size": size,
                    "mode": file_mode,
                    "shadow_mode": 0o500 if file_mode & 0o111 else 0o400,
                }
            )
            approved_paths.add(path)
            explicit_untracked.append(path)
    finally:
        try:
            immutable_ignore.unlink()
        except FileNotFoundError:
            pass

    selected_profile = profile_name or "full"
    profile_config_sha: Optional[str] = None
    if profile_config is not None:
        profile_config = ensure_under(profile_config, root, "profile config")
        profile_relative = profile_config.relative_to(root).as_posix()
        profile_bytes = read_repository_file(root, profile_relative)
        profile_config_sha = hashlib.sha256(profile_bytes).hexdigest()
        try:
            profile_payload = json.loads(profile_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise InventoryError("AI context profile config is invalid") from exc
        if profile_payload.get("$schema") != "narraverse.ai-context-profiles.v1":
            raise InventoryError("AI context profile schema is unsupported")
        profiles = profile_payload.get("profiles")
        if not isinstance(profiles, dict):
            raise InventoryError("AI context profiles must be an object")
        selected_profile = profile_name or profile_payload.get("default")
        if not isinstance(selected_profile, str) or selected_profile not in profiles:
            raise InventoryError(f"unknown AI context profile: {selected_profile}")
        selected = profiles[selected_profile]
        if not isinstance(selected, dict):
            raise InventoryError(f"AI context profile is invalid: {selected_profile}")
        include_paths = selected.get("include_paths", [])
        include_prefixes = selected.get("include_prefixes", [])
        if not isinstance(include_paths, list) or not isinstance(include_prefixes, list):
            raise InventoryError(f"AI context profile selectors are invalid: {selected_profile}")
        exact_paths: Set[str] = set()
        for value in include_paths:
            if not isinstance(value, str):
                raise InventoryError(f"AI context profile path is invalid: {selected_profile}")
            exact_paths.add(validate_protocol_path(value, "profile include path"))
        prefixes: List[str] = []
        for value in include_prefixes:
            if value == "":
                prefixes.append("")
                continue
            if not isinstance(value, str) or not value.endswith("/"):
                raise InventoryError(f"AI context profile prefix is invalid: {selected_profile}")
            validated_prefix = validate_protocol_path(
                value[:-1],
                "profile include prefix",
            )
            prefixes.append(validated_prefix + "/")
        if not exact_paths and not prefixes:
            raise InventoryError(f"AI context profile selects no paths: {selected_profile}")
        selected_files = [
            item
            for item in files
            if item["path"] in exact_paths
            or any(item["path"].startswith(prefix) for prefix in prefixes)
        ]
        selected_paths = {item["path"] for item in selected_files}
        filtered_explicit = sorted(set(explicit_untracked) - selected_paths)
        if filtered_explicit:
            raise InventoryError(
                "explicit untracked paths are outside the selected profile: "
                f"{filtered_explicit}"
            )
        for item in files:
            if item["path"] not in selected_paths:
                skipped.append({"path": item["path"], "reason": "profile_filter"})
        files = selected_files
    elif profile_name not in (None, "full"):
        raise InventoryError("named profiles require --profile-config")

    files.sort(key=lambda item: item["path"])
    if len(files) > MAX_FILE_COUNT:
        raise InventoryError(f"inventory exceeds {MAX_FILE_COUNT} files")
    total_bytes = sum(int(item["size"]) for item in files)
    if total_bytes > MAX_TOTAL_BYTES:
        raise InventoryError(f"inventory exceeds {MAX_TOTAL_BYTES} bytes")
    inventory_sha = compute_inventory_sha(
        files,
        ignore_digest,
        ignore_relative,
        selected_profile,
        profile_config_sha,
    )
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "inventory_sha256": inventory_sha,
        "git_head": git_head(root),
        "membership_source": "git_index_committed_or_staged_added",
        "content_source": "current_worktree",
        "profile": selected_profile,
        "profile_config_sha256": profile_config_sha,
        "ignore_file": ignore_relative,
        "ignore_sha256": ignore_digest,
        "tracked_path_count": len(tracked),
        "approved_file_count": len(files),
        "approved_total_bytes": total_bytes,
        "limits": {
            "max_file_count": MAX_FILE_COUNT,
            "max_file_bytes": MAX_FILE_BYTES,
            "max_total_bytes": MAX_TOTAL_BYTES,
        },
        "explicit_untracked": sorted(explicit_untracked),
        "skipped": skipped,
        "files": files,
    }


def atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    parent = require_real_directory(
        path.parent,
        "atomic JSON parent directory",
        owner_private=True,
    )
    path = parent / path.name
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        dir=str(parent),
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(
                payload,
                handle,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(str(temporary), str(path))
    finally:
        if temporary.exists():
            temporary.unlink()


def load_manifest(path: Path) -> Dict[str, Any]:
    try:
        path_stat = path.lstat()
    except OSError as exc:
        raise InventoryError(f"manifest is missing: {path}") from exc
    if stat.S_ISLNK(path_stat.st_mode) or not stat.S_ISREG(path_stat.st_mode):
        raise InventoryError(f"manifest must be a regular non-symlink file: {path}")
    if path_stat.st_size > 10 * 1024 * 1024:
        raise InventoryError(f"manifest exceeds the size limit: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise InventoryError(f"manifest is invalid: {path}") from exc
    if not isinstance(payload, dict):
        raise InventoryError(f"manifest must be a JSON object: {path}")
    if payload.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise InventoryError(f"unsupported manifest schema: {path}")
    inventory_sha = payload.get("inventory_sha256")
    if not is_hex_digest(inventory_sha, 64):
        raise InventoryError(f"manifest inventory hash is invalid: {path}")
    files = payload.get("files")
    if not isinstance(files, list):
        raise InventoryError(f"manifest file list is invalid: {path}")
    if len(files) > MAX_FILE_COUNT:
        raise InventoryError(f"manifest file list exceeds the limit: {path}")
    approved_paths: Set[str] = set()
    total_bytes = 0
    for item in files:
        if not isinstance(item, dict):
            raise InventoryError(f"manifest contains a non-object file entry: {path}")
        item_path = validate_protocol_path(str(item.get("path", "")), "manifest path")
        if item_path in approved_paths or is_hard_denied(item_path):
            raise InventoryError(f"manifest contains an invalid path: {item_path}")
        approved_paths.add(item_path)
        origin = item.get("origin")
        if origin not in {"tracked", "explicit_untracked"}:
            raise InventoryError(f"manifest origin is invalid: {item_path}")
        index_oid = item.get("index_oid")
        if origin == "tracked":
            if not (
                is_hex_digest(index_oid, 40)
                or is_hex_digest(index_oid, 64)
            ):
                raise InventoryError(f"manifest index object is invalid: {item_path}")
        elif index_oid is not None:
            raise InventoryError(f"untracked manifest entry has an index object: {item_path}")
        if not is_hex_digest(item.get("sha256"), 64):
            raise InventoryError(f"manifest content hash is invalid: {item_path}")
        size = item.get("size")
        mode = item.get("mode")
        shadow_mode = item.get("shadow_mode")
        if not isinstance(size, int) or isinstance(size, bool) or not 0 <= size <= MAX_FILE_BYTES:
            raise InventoryError(f"manifest size is invalid: {item_path}")
        if not isinstance(mode, int) or isinstance(mode, bool) or not 0 <= mode <= 0o777:
            raise InventoryError(f"manifest mode is invalid: {item_path}")
        expected_shadow_mode = 0o500 if mode & 0o111 else 0o400
        if shadow_mode != expected_shadow_mode:
            raise InventoryError(f"manifest shadow mode is invalid: {item_path}")
        total_bytes += size
    if total_bytes > MAX_TOTAL_BYTES:
        raise InventoryError(f"manifest total size exceeds the limit: {path}")
    ignore_file = payload.get("ignore_file")
    ignore_sha = payload.get("ignore_sha256")
    if not isinstance(ignore_file, str):
        raise InventoryError(f"manifest ignore file is invalid: {path}")
    validate_protocol_path(ignore_file, "manifest ignore file")
    if not is_hex_digest(ignore_sha, 64):
        raise InventoryError(f"manifest ignore hash is invalid: {path}")
    profile = payload.get("profile")
    profile_config_sha = payload.get("profile_config_sha256")
    if not isinstance(profile, str) or not profile or len(profile) > 64:
        raise InventoryError(f"manifest profile is invalid: {path}")
    if profile_config_sha is not None and not is_hex_digest(profile_config_sha, 64):
        raise InventoryError(f"manifest profile config hash is invalid: {path}")
    expected_inventory_sha = compute_inventory_sha(
        files,
        ignore_sha,
        ignore_file,
        profile,
        profile_config_sha,
    )
    if inventory_sha != expected_inventory_sha:
        raise InventoryError(f"manifest inventory hash does not authenticate its contents: {path}")
    if payload.get("approved_file_count") != len(files):
        raise InventoryError(f"manifest approved count is inconsistent: {path}")
    if payload.get("approved_total_bytes") != total_bytes:
        raise InventoryError(f"manifest byte count is inconsistent: {path}")
    return payload


def validate_shadow_contents(
    shadow_path: Path,
    manifest: Mapping[str, Any],
) -> None:
    shadow_path = require_real_directory(
        shadow_path,
        "shadow directory",
        owner_private=True,
        expected_mode=0o500,
    )

    expected: Dict[str, Mapping[str, Any]] = {}
    for raw_item in manifest["files"]:
        if not isinstance(raw_item, dict):
            raise InventoryError("shadow manifest contains an invalid file entry")
        path = validate_protocol_path(str(raw_item.get("path", "")), "manifest path")
        if path in expected:
            raise InventoryError(f"shadow manifest contains a duplicate path: {path}")
        expected[path] = raw_item

    actual: Set[str] = set()
    for current_root, directory_names, file_names in os.walk(
        str(shadow_path),
        topdown=True,
        followlinks=False,
    ):
        current = Path(current_root)
        if current != shadow_path:
            require_real_directory(
                current,
                "nested shadow directory",
                owner_private=True,
                expected_mode=0o500,
            )
        for directory_name in list(directory_names):
            directory = current / directory_name
            if directory.is_symlink():
                raise InventoryError(f"shadow contains a directory symlink: {directory}")
        for file_name in file_names:
            file_path = current / file_name
            relative = file_path.relative_to(shadow_path).as_posix()
            relative = validate_protocol_path(relative, "shadow path")
            if file_path.is_symlink() or not stat.S_ISREG(file_path.lstat().st_mode):
                raise InventoryError(f"shadow contains a non-regular file: {relative}")
            actual.add(relative)

    expected_paths = set(expected)
    if actual != expected_paths:
        missing = sorted(expected_paths - actual)[:10]
        extra = sorted(actual - expected_paths)[:10]
        raise InventoryError(
            f"shadow file set differs from manifest; missing={missing}, extra={extra}"
        )
    for path in sorted(expected):
        item = expected[path]
        digest, size, file_mode = hash_regular_file(shadow_path / path)
        if digest != item.get("sha256") or size != item.get("size"):
            raise InventoryError(f"shadow content differs from manifest: {path}")
        if file_mode != item.get("shadow_mode"):
            raise InventoryError(f"shadow mode differs from manifest: {path}")


def copy_repository_file(
    root: Path,
    relative_path: str,
    destination: Path,
    item: Mapping[str, Any],
) -> None:
    source_descriptor = open_repository_file(root, relative_path)
    destination_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        destination_flags |= os.O_NOFOLLOW
    try:
        destination_descriptor = os.open(str(destination), destination_flags, 0o600)
    except OSError:
        os.close(source_descriptor)
        raise
    digest = hashlib.sha256()
    total = 0
    try:
        while True:
            chunk = os.read(source_descriptor, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            total += len(chunk)
            view = memoryview(chunk)
            while view:
                written = os.write(destination_descriptor, view)
                if written <= 0:
                    raise InventoryError(f"could not copy repository input: {relative_path}")
                view = view[written:]
        os.fsync(destination_descriptor)
        os.fchmod(destination_descriptor, int(item["shadow_mode"]))
    finally:
        os.close(source_descriptor)
        os.close(destination_descriptor)
    if digest.hexdigest() != item["sha256"] or total != item["size"]:
        raise InventoryError(f"input changed while copying: {relative_path}")


def remove_shadow_tree(path: Path) -> None:
    path = require_real_directory(
        path,
        "shadow removal directory",
        owner_private=True,
    )
    for current_root, directory_names, file_names in os.walk(
        str(path),
        topdown=False,
        followlinks=False,
    ):
        current = Path(current_root)
        for file_name in file_names:
            if (current / file_name).is_symlink():
                raise InventoryError(f"refusing to remove a shadow containing symlinks: {path}")
            try:
                (current / file_name).chmod(0o600)
            except OSError:
                pass
        for directory_name in directory_names:
            if (current / directory_name).is_symlink():
                raise InventoryError(f"refusing to remove a shadow containing symlinks: {path}")
            try:
                (current / directory_name).chmod(0o700)
            except OSError:
                pass
        try:
            current.chmod(0o700)
        except OSError:
            pass
    shutil.rmtree(path)


def shadow_manifest_path(cache_dir: Path, shadow_path: Path) -> Path:
    cache_dir, inputs_dir = controlled_cache_layout(cache_dir, create=False)
    shadow_path = require_real_directory(
        shadow_path,
        "shadow directory",
        owner_private=True,
        expected_mode=0o500,
    )
    try:
        relative = shadow_path.relative_to(inputs_dir)
    except ValueError as exc:
        raise InventoryError("shadow path is outside the controlled input directory") from exc
    if (
        len(relative.parts) != 2
        or relative.parts[1] != "files"
        or not is_hex_digest(relative.parts[0], 64)
    ):
        raise InventoryError("shadow path is not a complete inventory directory")
    generation = ensure_direct_child_directory(
        inputs_dir,
        relative.parts[0],
        "input generation",
        create=False,
        mode=0o700,
        parent_owner_private=True,
    )
    expected_shadow = ensure_direct_child_directory(
        generation,
        "files",
        "input generation files",
        create=False,
        mode=0o500,
        parent_owner_private=True,
    )
    if shadow_path != expected_shadow:
        raise InventoryError("shadow path is not the controlled input directory")
    return generation / "manifest.json"


def verify_shadow(cache_dir: Path, shadow_path: Path) -> Dict[str, Any]:
    manifest_path = shadow_manifest_path(cache_dir, shadow_path)
    manifest = load_manifest(manifest_path)
    expected_name = manifest["inventory_sha256"]
    shadow_path = lexical_absolute(shadow_path)
    if shadow_path.parent.name != expected_name:
        raise InventoryError("shadow directory name does not match its manifest")
    validate_shadow_contents(shadow_path, manifest)
    return manifest


def create_shadow(
    root: Path,
    cache_dir: Path,
    manifest: Mapping[str, Any],
) -> Path:
    root = ensure_repository(root)
    cache_dir, inputs_dir = controlled_cache_layout(
        cache_dir,
        root=root,
        create=True,
    )
    inventory_sha = str(manifest["inventory_sha256"])
    if not is_hex_digest(inventory_sha, 64):
        raise InventoryError("inventory hash is invalid")
    final_generation = inputs_dir / inventory_sha
    final_shadow = final_generation / "files"
    if final_generation.is_symlink():
        raise InventoryError(f"shadow target must not be a symlink: {final_generation}")
    if final_generation.is_dir():
        try:
            existing = verify_shadow(cache_dir, final_shadow)
            if existing["inventory_sha256"] != inventory_sha:
                raise InventoryError("existing shadow has a different manifest")
        except InventoryError:
            remove_shadow_tree(final_generation)
        else:
            return final_shadow
    if final_generation.exists():
        raise InventoryError(f"shadow target is not a directory: {final_generation}")

    temporary_generation = Path(
        tempfile.mkdtemp(prefix=".building-", dir=str(inputs_dir))
    )
    temporary_shadow = temporary_generation / "files"
    try:
        temporary_generation.chmod(0o700)
        temporary_shadow.mkdir(mode=0o700)
        for item in manifest["files"]:
            relative = Path(item["path"])
            destination = temporary_shadow / relative
            destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            copy_repository_file(root, item["path"], destination, item)
            linked_hash, linked_size, linked_mode = hash_regular_file(destination)
            if linked_hash != item["sha256"] or linked_size != item["size"]:
                raise InventoryError(f"input changed while copying: {item['path']}")
            if linked_mode != item["shadow_mode"]:
                raise InventoryError(f"shadow mode is unsafe: {item['path']}")
        for current_root, directory_names, _file_names in os.walk(
            str(temporary_shadow),
            topdown=False,
            followlinks=False,
        ):
            for directory_name in directory_names:
                (Path(current_root) / directory_name).chmod(0o500)
            Path(current_root).chmod(0o500)
        validate_shadow_contents(temporary_shadow, manifest)
        atomic_write_json(temporary_generation / "manifest.json", manifest)
        os.rename(str(temporary_generation), str(final_generation))
    except FileExistsError:
        existing = verify_shadow(cache_dir, final_shadow)
        if existing["inventory_sha256"] != inventory_sha:
            raise InventoryError("concurrent shadow publication was inconsistent")
    finally:
        if temporary_generation.exists():
            remove_shadow_tree(temporary_generation)
    return final_shadow


def activate_shadow(cache_dir: Path, shadow_path: Path) -> None:
    cache_dir, _inputs_dir = controlled_cache_layout(cache_dir, create=False)
    shadow_path = lexical_absolute(shadow_path)
    manifest = verify_shadow(cache_dir, shadow_path)
    atomic_write_json(
        cache_dir / "current-input.json",
        {
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "inventory_sha256": manifest["inventory_sha256"],
        },
    )


def current_shadow(cache_dir: Path) -> Path:
    cache_dir, inputs_dir = controlled_cache_layout(cache_dir, create=False)
    pointer = cache_dir / "current-input.json"
    if pointer.is_symlink() or not pointer.is_file():
        raise InventoryError("no active tracked input; run code-intel.sh index")
    try:
        payload = json.loads(pointer.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise InventoryError("active input pointer is invalid") from exc
    pointer_hash = payload.get("inventory_sha256")
    if not is_hex_digest(pointer_hash, 64):
        raise InventoryError("active input pointer hash is invalid")
    generation = ensure_direct_child_directory(
        inputs_dir,
        pointer_hash,
        "active input generation",
        create=False,
        mode=0o700,
        parent_owner_private=True,
    )
    shadow = ensure_direct_child_directory(
        generation,
        "files",
        "active tracked input directory",
        create=False,
        mode=0o500,
        parent_owner_private=True,
    )
    verify_shadow(cache_dir, shadow)
    return shadow


def current_manifest(cache_dir: Path) -> Path:
    shadow = current_shadow(cache_dir)
    return shadow_manifest_path(cache_dir, shadow)


def cleanup_inactive_generations(cache_dir: Path) -> int:
    cache_dir, inputs_dir = controlled_cache_layout(cache_dir, create=False)
    active_shadow = current_shadow(cache_dir)
    active_hash = active_shadow.parent.name
    removed = 0
    for candidate in sorted(inputs_dir.iterdir(), key=lambda item: item.name):
        if candidate.name == active_hash:
            continue
        if candidate.is_symlink() or not candidate.is_dir():
            raise InventoryError(f"unexpected entry in controlled inputs: {candidate}")
        if not (
            is_hex_digest(candidate.name, 64)
            or candidate.name.startswith(".building-")
        ):
            raise InventoryError(f"unexpected input generation name: {candidate.name}")
        remove_shadow_tree(candidate)
        removed += 1
    return removed


def prepare_context_layout(root: Path) -> Path:
    context_dir, _snapshots_dir = controlled_context_layout(root, create=True)
    return context_dir


def prepare_cache_layout(root: Path, cache_dir: Path) -> Path:
    cache_dir, _inputs_dir = controlled_cache_layout(
        cache_dir,
        root=root,
        create=True,
    )
    return cache_dir


def read_lock_owner(lock_descriptor: int) -> Dict[str, Any]:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open("owner.json", flags, dir_fd=lock_descriptor)
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or opened.st_size > 4096:
            raise InventoryError("controlled lock owner is not a small regular file")
        chunks: List[bytes] = []
        while True:
            chunk = os.read(descriptor, 4096)
            if not chunk:
                break
            chunks.append(chunk)
    finally:
        os.close(descriptor)
    try:
        payload = json.loads(b"".join(chunks).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InventoryError("controlled lock owner is invalid") from exc
    if not isinstance(payload, dict):
        raise InventoryError("controlled lock owner is invalid")
    process_id = payload.get("pid")
    token = payload.get("token")
    if (
        not isinstance(process_id, int)
        or isinstance(process_id, bool)
        or process_id <= 0
        or not is_hex_digest(token, 64)
    ):
        raise InventoryError("controlled lock owner fields are invalid")
    return payload


def process_is_alive(process_id: int) -> bool:
    try:
        os.kill(process_id, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def acquire_private_directory_lock(
    parent_dir: Path,
    lock_name: str,
    process_id: int,
) -> str:
    """Acquire a crash-recoverable owner-private directory lock."""
    if (
        not lock_name.startswith(".")
        or not lock_name.endswith(".lock")
        or "/" in lock_name
        or "\\" in lock_name
    ):
        raise InventoryError("controlled lock name is invalid")
    if process_id <= 0:
        raise InventoryError("controlled lock process id is invalid")
    parent_dir = require_real_directory(
        parent_dir,
        "controlled lock parent directory",
        owner_private=True,
        expected_mode=0o700,
    )
    parent_descriptor = os.open(str(parent_dir), directory_open_flags())
    deadline = time.monotonic() + LOCK_ACQUIRE_TIMEOUT_SECONDS
    try:
        while time.monotonic() < deadline:
            token = secrets.token_hex(32)
            try:
                os.mkdir(lock_name, 0o700, dir_fd=parent_descriptor)
            except FileExistsError:
                try:
                    entry = os.stat(
                        lock_name,
                        dir_fd=parent_descriptor,
                        follow_symlinks=False,
                    )
                    if stat.S_ISLNK(entry.st_mode) or not stat.S_ISDIR(entry.st_mode):
                        raise InventoryError("controlled lock path is not a real directory")
                    lock_descriptor = os.open(
                        lock_name,
                        directory_open_flags(),
                        dir_fd=parent_descriptor,
                    )
                    remove_orphan = False
                    try:
                        opened = os.fstat(lock_descriptor)
                        if (opened.st_dev, opened.st_ino) != (entry.st_dev, entry.st_ino):
                            raise InventoryError("controlled lock changed while opening")
                        secure_directory_descriptor(
                            lock_descriptor,
                            "controlled lock directory",
                            expected_mode=0o700,
                        )
                        try:
                            owner = read_lock_owner(lock_descriptor)
                        except FileNotFoundError:
                            age_seconds = max(0.0, time.time() - entry.st_mtime)
                            if age_seconds < 5.0:
                                time.sleep(0.05)
                                continue
                            entries = os.listdir(lock_descriptor)
                            if entries:
                                if (
                                    len(entries) != 1
                                    or re.fullmatch(
                                        r"\.owner\.pending\.[0-9a-f]{64}",
                                        entries[0],
                                    )
                                    is None
                                ):
                                    raise InventoryError(
                                        "orphaned controlled lock contains unexpected entries"
                                    )
                                pending_entry = os.stat(
                                    entries[0],
                                    dir_fd=lock_descriptor,
                                    follow_symlinks=False,
                                )
                                owner_id = current_user_id()
                                if (
                                    not stat.S_ISREG(pending_entry.st_mode)
                                    or pending_entry.st_size > 4096
                                    or stat.S_IMODE(pending_entry.st_mode) != 0o600
                                    or (
                                        owner_id is not None
                                        and pending_entry.st_uid != owner_id
                                    )
                                ):
                                    raise InventoryError(
                                        "orphaned controlled lock pending owner is unsafe"
                                    )
                                os.unlink(entries[0], dir_fd=lock_descriptor)
                            remove_orphan = True
                        else:
                            if process_is_alive(int(owner["pid"])):
                                time.sleep(0.05)
                                continue
                        current = os.stat(
                            lock_name,
                            dir_fd=parent_descriptor,
                            follow_symlinks=False,
                        )
                        if (current.st_dev, current.st_ino) != (
                            opened.st_dev,
                            opened.st_ino,
                        ):
                            raise InventoryError(
                                "controlled lock changed before stale cleanup"
                            )
                        if not remove_orphan:
                            os.unlink("owner.json", dir_fd=lock_descriptor)
                    finally:
                        os.close(lock_descriptor)
                    os.rmdir(lock_name, dir_fd=parent_descriptor)
                except FileNotFoundError:
                    # A live owner may release between any two observations, or
                    # another waiter may win stale cleanup. Both are normal races.
                    continue
                continue
            entry = os.stat(
                lock_name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
            lock_descriptor = os.open(
                lock_name,
                directory_open_flags(),
                dir_fd=parent_descriptor,
            )
            try:
                opened = os.fstat(lock_descriptor)
                if (opened.st_dev, opened.st_ino) != (entry.st_dev, entry.st_ino):
                    raise InventoryError("controlled lock changed while opening")
                secure_directory_descriptor(
                    lock_descriptor,
                    "controlled lock directory",
                    expected_mode=0o700,
                )
                pending_owner = f".owner.pending.{token}"
                owner_descriptor = os.open(
                    pending_owner,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL
                    | (os.O_NOFOLLOW if hasattr(os, "O_NOFOLLOW") else 0),
                    0o600,
                    dir_fd=lock_descriptor,
                )
                try:
                    content = json.dumps(
                        {"pid": process_id, "token": token},
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode("utf-8") + b"\n"
                    remaining = memoryview(content)
                    while remaining:
                        written = os.write(owner_descriptor, remaining)
                        remaining = remaining[written:]
                    os.fsync(owner_descriptor)
                finally:
                    os.close(owner_descriptor)
                os.replace(
                    pending_owner,
                    "owner.json",
                    src_dir_fd=lock_descriptor,
                    dst_dir_fd=lock_descriptor,
                )
                os.fsync(lock_descriptor)
                os.fsync(parent_descriptor)
            except BaseException:
                for candidate in (f".owner.pending.{token}", "owner.json"):
                    try:
                        candidate_entry = os.stat(
                            candidate,
                            dir_fd=lock_descriptor,
                            follow_symlinks=False,
                        )
                        if stat.S_ISREG(candidate_entry.st_mode):
                            os.unlink(candidate, dir_fd=lock_descriptor)
                    except FileNotFoundError:
                        pass
                os.close(lock_descriptor)
                try:
                    os.rmdir(lock_name, dir_fd=parent_descriptor)
                except OSError:
                    pass
                raise
            os.close(lock_descriptor)
            return token
    finally:
        os.close(parent_descriptor)
    raise InventoryError("timed out waiting for the controlled lock")


def release_private_directory_lock(
    parent_dir: Path,
    lock_name: str,
    token: str,
) -> None:
    if (
        not lock_name.startswith(".")
        or not lock_name.endswith(".lock")
        or "/" in lock_name
        or "\\" in lock_name
        or not is_hex_digest(token, 64)
    ):
        raise InventoryError("controlled lock release token is invalid")
    parent_dir = require_real_directory(
        parent_dir,
        "controlled lock parent directory",
        owner_private=True,
        expected_mode=0o700,
    )
    parent_descriptor = os.open(str(parent_dir), directory_open_flags())
    try:
        entry = os.stat(lock_name, dir_fd=parent_descriptor, follow_symlinks=False)
        if stat.S_ISLNK(entry.st_mode) or not stat.S_ISDIR(entry.st_mode):
            raise InventoryError("controlled lock path is not a real directory")
        lock_descriptor = os.open(
            lock_name,
            directory_open_flags(),
            dir_fd=parent_descriptor,
        )
        try:
            opened = os.fstat(lock_descriptor)
            if (opened.st_dev, opened.st_ino) != (entry.st_dev, entry.st_ino):
                raise InventoryError("controlled lock changed while releasing")
            secure_directory_descriptor(
                lock_descriptor,
                "controlled lock directory",
                expected_mode=0o700,
            )
            owner = read_lock_owner(lock_descriptor)
            if owner["token"] != token:
                raise InventoryError("controlled lock is owned by another process")
            current = os.stat(lock_name, dir_fd=parent_descriptor, follow_symlinks=False)
            if (current.st_dev, current.st_ino) != (opened.st_dev, opened.st_ino):
                raise InventoryError("controlled lock changed before release")
            os.unlink("owner.json", dir_fd=lock_descriptor)
            os.fsync(lock_descriptor)
        finally:
            os.close(lock_descriptor)
        os.rmdir(lock_name, dir_fd=parent_descriptor)
        os.fsync(parent_descriptor)
    except FileNotFoundError as exc:
        raise InventoryError("controlled lock is missing") from exc
    finally:
        os.close(parent_descriptor)


def acquire_controlled_lock(
    root: Path,
    cache_dir: Path,
    lock_kind: str,
    process_id: int,
) -> str:
    if lock_kind not in CONTROLLED_LOCKS:
        raise InventoryError("unknown controlled lock kind")
    cache_dir, _inputs_dir = controlled_cache_layout(
        cache_dir,
        root=root,
        create=True,
    )
    return acquire_private_directory_lock(
        cache_dir,
        CONTROLLED_LOCKS[lock_kind],
        process_id,
    )


def release_controlled_lock(
    root: Path,
    cache_dir: Path,
    lock_kind: str,
    token: str,
) -> None:
    if lock_kind not in CONTROLLED_LOCKS:
        raise InventoryError("unknown controlled lock kind")
    cache_dir, _inputs_dir = controlled_cache_layout(
        cache_dir,
        root=root,
        create=False,
    )
    release_private_directory_lock(
        cache_dir,
        CONTROLLED_LOCKS[lock_kind],
        token,
    )


def acquire_context_publication_lock(root: Path, process_id: int) -> str:
    context_dir, _snapshots_dir = controlled_context_layout(root, create=False)
    return acquire_private_directory_lock(
        context_dir,
        CONTEXT_PUBLICATION_LOCK,
        process_id,
    )


def release_context_publication_lock(root: Path, token: str) -> None:
    context_dir, _snapshots_dir = controlled_context_layout(root, create=False)
    release_private_directory_lock(
        context_dir,
        CONTEXT_PUBLICATION_LOCK,
        token,
    )


def controlled_snapshot_build(
    root: Path,
    destination: Path,
) -> Tuple[Path, Path, Path]:
    context_dir, _snapshots_dir = controlled_context_layout(root, create=False)
    destination = lexical_absolute(destination)
    destination = destination.parent.resolve() / destination.name
    try:
        relative_destination = destination.relative_to(context_dir)
    except ValueError as exc:
        raise InventoryError("snapshot input escapes the AI context directory") from exc
    if (
        len(relative_destination.parts) != 2
        or not relative_destination.parts[0].startswith(".building.")
        or relative_destination.parts[1] != "input-root"
    ):
        raise InventoryError("snapshot input must be an isolated build directory")
    build_dir = ensure_direct_child_directory(
        context_dir,
        relative_destination.parts[0],
        "snapshot build directory",
        create=False,
        mode=0o700,
        parent_owner_private=True,
    )
    expected_destination = build_dir / "input-root"
    if destination != expected_destination:
        raise InventoryError("snapshot input path is not the controlled build input")
    return context_dir, build_dir, expected_destination


def materialize_snapshot_input(
    root: Path,
    manifest_path: Path,
    destination: Path,
) -> Path:
    root = ensure_repository(root)
    _context_dir, build_dir, destination = controlled_snapshot_build(root, destination)
    manifest_path = lexical_absolute(manifest_path)
    if manifest_path.parent != build_dir:
        raise InventoryError("snapshot manifest must be inside the same build directory")
    if os.path.lexists(str(destination)):
        raise InventoryError("snapshot input destination already exists")
    manifest = load_manifest(manifest_path)
    destination.mkdir(parents=False, mode=0o700)
    try:
        for item in manifest["files"]:
            relative = Path(item["path"])
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            copy_repository_file(root, item["path"], target, item)
        for current_root, directory_names, _file_names in os.walk(
            str(destination),
            topdown=False,
            followlinks=False,
        ):
            for directory_name in directory_names:
                (Path(current_root) / directory_name).chmod(0o500)
            Path(current_root).chmod(0o500)
        validate_shadow_contents(destination, manifest)
    except BaseException:
        if destination.exists():
            remove_shadow_tree(destination)
        raise
    return destination


def remove_snapshot_input(root: Path, destination: Path) -> None:
    _context_dir, _build_dir, destination = controlled_snapshot_build(root, destination)
    if not os.path.lexists(str(destination)):
        return
    require_real_directory(
        destination,
        "snapshot input directory",
        owner_private=True,
        expected_mode=0o500,
    )
    remove_shadow_tree(destination)


def validate_snapshot(manifest_path: Path, snapshot_path: Path) -> int:
    manifest = load_manifest(manifest_path.expanduser().resolve())
    snapshot_path = lexical_absolute(snapshot_path)
    try:
        path_stat = snapshot_path.lstat()
    except OSError as exc:
        raise InventoryError(f"snapshot is missing: {snapshot_path}") from exc
    if (
        stat.S_ISLNK(path_stat.st_mode)
        or not stat.S_ISREG(path_stat.st_mode)
        or path_stat.st_size > MAX_SNAPSHOT_BYTES
    ):
        raise InventoryError(f"snapshot is unsafe or oversized: {snapshot_path}")
    flags = os.O_RDONLY | (os.O_NOFOLLOW if hasattr(os, "O_NOFOLLOW") else 0)
    descriptor = os.open(str(snapshot_path), flags)
    try:
        opened = os.fstat(descriptor)
        if (
            (opened.st_dev, opened.st_ino) != (path_stat.st_dev, path_stat.st_ino)
            or not stat.S_ISREG(opened.st_mode)
            or opened.st_size > MAX_SNAPSHOT_BYTES
        ):
            raise InventoryError(f"snapshot changed while opening: {snapshot_path}")
        chunks: List[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_SNAPSHOT_BYTES:
                raise InventoryError(f"snapshot exceeds the size limit: {snapshot_path}")
            chunks.append(chunk)
        completed = os.fstat(descriptor)
        if (
            (completed.st_dev, completed.st_ino, completed.st_size, completed.st_mtime_ns)
            != (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns)
            or total != opened.st_size
        ):
            raise InventoryError(f"snapshot changed while reading: {snapshot_path}")
        text = b"".join(chunks).decode("utf-8")
    except (UnicodeDecodeError, OSError) as exc:
        raise InventoryError(f"snapshot is not readable UTF-8: {snapshot_path}") from exc
    finally:
        os.close(descriptor)

    packed_paths = [
        html.unescape(value)
        for value in re.findall(r'<file\s+path="([^"]+)"', text)
    ]
    if not packed_paths:
        raise InventoryError("snapshot contains no recognizable file entries")
    if len(packed_paths) != len(set(packed_paths)):
        raise InventoryError("snapshot contains duplicate file paths")
    approved = {str(item["path"]) for item in manifest["files"]}
    unexpected = sorted(set(packed_paths) - approved)
    missing = sorted(approved - set(packed_paths))
    if unexpected or missing:
        raise InventoryError(
            "snapshot paths differ from its manifest; "
            f"missing={missing[:10]}, unexpected={unexpected[:10]}"
        )
    return len(packed_paths)


def publish_context_bundle(
    root: Path,
    build_dir: Path,
    bundle_id: str,
    packed_count: int,
) -> Path:
    """Serialize and publish one complete AI-context bundle."""
    token = acquire_context_publication_lock(root, os.getpid())
    try:
        return _publish_context_bundle_locked(
            root,
            build_dir,
            bundle_id,
            packed_count,
        )
    finally:
        release_context_publication_lock(root, token)


def _publish_context_bundle_locked(
    root: Path,
    build_dir: Path,
    bundle_id: str,
    packed_count: int,
) -> Path:
    """Atomically publish, validate, activate, and retain a context bundle."""
    if not is_hex_digest(bundle_id, 64) or packed_count <= 0:
        raise InventoryError("snapshot publication metadata is invalid")
    context_dir, snapshots_dir = controlled_context_layout(root, create=False)
    build_dir = lexical_absolute(build_dir)
    if (
        build_dir.parent != context_dir
        or not build_dir.name.startswith(".building.")
    ):
        raise InventoryError("snapshot build directory is outside the controlled layout")

    context_descriptor = os.open(str(context_dir), directory_open_flags())
    snapshots_descriptor = -1
    published = False
    try:
        context_opened = os.fstat(context_descriptor)
        context_current = context_dir.lstat()
        if (context_opened.st_dev, context_opened.st_ino) != (
            context_current.st_dev,
            context_current.st_ino,
        ):
            raise InventoryError("AI context directory changed before publication")
        snapshots_entry = os.stat(
            "snapshots", dir_fd=context_descriptor, follow_symlinks=False
        )
        if not stat.S_ISDIR(snapshots_entry.st_mode):
            raise InventoryError("AI context snapshots entry is unsafe")
        snapshots_descriptor = os.open(
            "snapshots", directory_open_flags(), dir_fd=context_descriptor
        )
        snapshots_opened = secure_directory_descriptor(
            snapshots_descriptor,
            "AI context snapshots directory",
            expected_mode=0o700,
        )
        if (snapshots_opened.st_dev, snapshots_opened.st_ino) != (
            snapshots_entry.st_dev,
            snapshots_entry.st_ino,
        ):
            raise InventoryError("AI context snapshots directory changed while opening")

        build_entry = os.stat(
            build_dir.name,
            dir_fd=context_descriptor,
            follow_symlinks=False,
        )
        if not stat.S_ISDIR(build_entry.st_mode):
            raise InventoryError("snapshot build entry is unsafe")
        build_descriptor = os.open(
            build_dir.name,
            directory_open_flags(),
            dir_fd=context_descriptor,
        )
        try:
            build_opened = secure_directory_descriptor(
                build_descriptor,
                "snapshot build directory",
                expected_mode=0o700,
            )
            if (build_opened.st_dev, build_opened.st_ino) != (
                build_entry.st_dev,
                build_entry.st_ino,
            ):
                raise InventoryError("snapshot build directory changed while opening")
            if set(os.listdir(build_descriptor)) != {
                "manifest.json",
                "provenance.json",
                "repomix.xml",
            }:
                raise InventoryError("snapshot build contains an unexpected file set")
        finally:
            os.close(build_descriptor)

        try:
            existing = os.stat(
                bundle_id,
                dir_fd=snapshots_descriptor,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            os.rename(
                build_dir.name,
                bundle_id,
                src_dir_fd=context_descriptor,
                dst_dir_fd=snapshots_descriptor,
            )
            os.fsync(snapshots_descriptor)
            published = True
        else:
            if not stat.S_ISDIR(existing.st_mode):
                raise InventoryError("existing snapshot bundle is unsafe")
    finally:
        if snapshots_descriptor >= 0:
            os.close(snapshots_descriptor)
        os.close(context_descriptor)

    bundle = snapshots_dir / bundle_id
    try:
        bundle = require_real_directory(
            bundle,
            "snapshot bundle",
            owner_private=True,
            expected_mode=0o700,
        )
        if {item.name for item in bundle.iterdir()} != {
            "manifest.json",
            "provenance.json",
            "repomix.xml",
        }:
            raise InventoryError("snapshot bundle contains an unexpected file set")
        for name in ("manifest.json", "provenance.json", "repomix.xml"):
            item = bundle / name
            item_stat = item.lstat()
            owner = current_user_id()
            if (
                stat.S_ISLNK(item_stat.st_mode)
                or not stat.S_ISREG(item_stat.st_mode)
                or (owner is not None and item_stat.st_uid != owner)
                or stat.S_IMODE(item_stat.st_mode) != 0o600
            ):
                raise InventoryError(f"snapshot bundle entry is unsafe: {name}")
        manifest = load_manifest(bundle / "manifest.json")
        actual_packed_count = validate_snapshot(
            bundle / "manifest.json", bundle / "repomix.xml"
        )
        if actual_packed_count != packed_count:
            raise InventoryError("snapshot packed count differs during publication")
        try:
            provenance = json.loads(
                (bundle / "provenance.json").read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError) as exc:
            raise InventoryError("snapshot provenance is invalid") from exc
        if not isinstance(provenance, dict):
            raise InventoryError("snapshot provenance is not an object")
        snapshot_sha = hashlib.sha256((bundle / "repomix.xml").read_bytes()).hexdigest()
        expected_simple = {
            "schema_version": 1,
            "bundle_id": bundle_id,
            "inventory_sha256": manifest["inventory_sha256"],
            "profile": manifest["profile"],
            "packed_file_count": packed_count,
            "snapshot_sha256": snapshot_sha,
        }
        for key, value in expected_simple.items():
            if provenance.get(key) != value:
                raise InventoryError(f"snapshot provenance mismatch: {key}")
        digest_fields = (
            "config_sha256",
            "runtime_package_sha256",
            "runtime_lock_sha256",
            "snapshot_sha256",
        )
        if any(not is_hex_digest(provenance.get(key), 64) for key in digest_fields):
            raise InventoryError("snapshot provenance contains an invalid digest")
        version_fields = ("repomix_version", "node_version", "npm_version")
        if any(
            not isinstance(provenance.get(key), str) or not provenance.get(key)
            for key in version_fields
        ):
            raise InventoryError("snapshot provenance contains an invalid version")
        recomputed = hashlib.sha256()
        for label, value in (
            ("inventory", manifest["inventory_sha256"]),
            ("config", provenance["config_sha256"]),
            ("snapshot", snapshot_sha),
            ("runtime_package", provenance["runtime_package_sha256"]),
            ("runtime_lock", provenance["runtime_lock_sha256"]),
            ("repomix", provenance["repomix_version"]),
            ("node", provenance["node_version"]),
            ("npm", provenance["npm_version"]),
        ):
            recomputed.update(label.encode("ascii") + b"\0" + value.encode("ascii") + b"\0")
        if recomputed.hexdigest() != bundle_id:
            raise InventoryError("snapshot bundle id does not authenticate its contents")
    except BaseException:
        if published:
            # Leave a newly published but unactivated bundle for forensic inspection;
            # retention on the next successful build can remove it safely.
            pass
        raise

    context_descriptor = os.open(str(context_dir), directory_open_flags())
    snapshots_descriptor = os.open(
        "snapshots", directory_open_flags(), dir_fd=context_descriptor
    )
    try:
        active_entry = os.stat(
            bundle_id, dir_fd=snapshots_descriptor, follow_symlinks=False
        )
        if not stat.S_ISDIR(active_entry.st_mode):
            raise InventoryError("active snapshot bundle changed before activation")

        previous_bundle_id: Optional[str] = None
        try:
            pointer_entry = os.stat(
                "current.json",
                dir_fd=context_descriptor,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            pass
        else:
            if not stat.S_ISREG(pointer_entry.st_mode) or pointer_entry.st_size > 65536:
                raise InventoryError("existing AI context pointer is unsafe")
            pointer_descriptor = os.open(
                "current.json",
                os.O_RDONLY | (os.O_NOFOLLOW if hasattr(os, "O_NOFOLLOW") else 0),
                dir_fd=context_descriptor,
            )
            try:
                pointer_opened = os.fstat(pointer_descriptor)
                if (pointer_opened.st_dev, pointer_opened.st_ino) != (
                    pointer_entry.st_dev,
                    pointer_entry.st_ino,
                ):
                    raise InventoryError("AI context pointer changed while opening")
                pointer_bytes = os.read(pointer_descriptor, 65537)
            finally:
                os.close(pointer_descriptor)
            try:
                pointer_payload = json.loads(pointer_bytes.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise InventoryError("existing AI context pointer is invalid") from exc
            previous_value = pointer_payload.get("bundle_id")
            if not is_hex_digest(previous_value, 64):
                raise InventoryError("existing AI context pointer bundle id is invalid")
            previous_bundle_id = previous_value

        expected_files = {"manifest.json", "provenance.json", "repomix.xml"}

        def remove_quarantined_bundle(name: str) -> None:
            candidate_descriptor = os.open(
                name, directory_open_flags(), dir_fd=snapshots_descriptor
            )
            try:
                entries = set(os.listdir(candidate_descriptor))
                if not entries.issubset(expected_files):
                    raise InventoryError(
                        "snapshot removal quarantine contains unexpected entries"
                    )
                for file_name in sorted(entries):
                    item = os.stat(
                        file_name,
                        dir_fd=candidate_descriptor,
                        follow_symlinks=False,
                    )
                    if not stat.S_ISREG(item.st_mode):
                        raise InventoryError(
                            "snapshot removal quarantine contains an unsafe entry"
                        )
                    os.unlink(file_name, dir_fd=candidate_descriptor)
            finally:
                os.close(candidate_descriptor)
            os.rmdir(name, dir_fd=snapshots_descriptor)

        quarantine_pattern = re.compile(r"\.removing\.[0-9a-f]{64}\.[0-9a-f]{32}")
        for name in sorted(os.listdir(snapshots_descriptor)):
            if quarantine_pattern.fullmatch(name):
                remove_quarantined_bundle(name)

        candidates: List[Tuple[int, str]] = []
        for name in os.listdir(snapshots_descriptor):
            if not is_hex_digest(name, 64):
                continue
            entry = os.stat(name, dir_fd=snapshots_descriptor, follow_symlinks=False)
            if not stat.S_ISDIR(entry.st_mode):
                raise InventoryError("snapshot retention found an unsafe bundle")
            candidates.append((entry.st_mtime_ns, name))
        candidates.sort(reverse=True)
        keep = {bundle_id}
        if previous_bundle_id is not None:
            try:
                previous_entry = os.stat(
                    previous_bundle_id,
                    dir_fd=snapshots_descriptor,
                    follow_symlinks=False,
                )
            except FileNotFoundError as exc:
                raise InventoryError(
                    "existing AI context pointer references a missing bundle"
                ) from exc
            if not stat.S_ISDIR(previous_entry.st_mode):
                raise InventoryError(
                    "existing AI context pointer references an unsafe bundle"
                )
            keep.add(previous_bundle_id)
        for _mtime, name in candidates:
            if len(keep) >= 2:
                break
            keep.add(name)
        quarantined: List[str] = []
        for _mtime, name in candidates:
            if name in keep:
                continue
            candidate_descriptor = os.open(
                name, directory_open_flags(), dir_fd=snapshots_descriptor
            )
            try:
                if set(os.listdir(candidate_descriptor)) != expected_files:
                    raise InventoryError("refusing to retire an unexpected snapshot bundle")
                for file_name in sorted(expected_files):
                    item = os.stat(
                        file_name,
                        dir_fd=candidate_descriptor,
                        follow_symlinks=False,
                    )
                    if not stat.S_ISREG(item.st_mode):
                        raise InventoryError("snapshot retention found an unsafe entry")
            finally:
                os.close(candidate_descriptor)
            quarantine_name = f".removing.{name}.{secrets.token_hex(16)}"
            os.rename(
                name,
                quarantine_name,
                src_dir_fd=snapshots_descriptor,
                dst_dir_fd=snapshots_descriptor,
            )
            quarantined.append(quarantine_name)
        os.fsync(snapshots_descriptor)
        for name in quarantined:
            remove_quarantined_bundle(name)
        os.fsync(snapshots_descriptor)

        links = {
            "repomix.xml": PurePosixPath("snapshots", bundle_id, "repomix.xml"),
            "repomix-input-manifest.json": PurePosixPath(
                "snapshots", bundle_id, "manifest.json"
            ),
        }
        for name, target in links.items():
            temporary_name = f".{name}.{secrets.token_hex(16)}"
            os.symlink(str(target), temporary_name, dir_fd=context_descriptor)
            try:
                os.replace(
                    temporary_name,
                    name,
                    src_dir_fd=context_descriptor,
                    dst_dir_fd=context_descriptor,
                )
            finally:
                try:
                    os.unlink(temporary_name, dir_fd=context_descriptor)
                except FileNotFoundError:
                    pass
        provenance_link = PurePosixPath("snapshots", bundle_id, "provenance.json")
        current_payload = {
            "schema_version": 1,
            "bundle_id": bundle_id,
            "manifest": str(links["repomix-input-manifest.json"]),
            "packed_file_count": packed_count,
            "profile": manifest["profile"],
            "provenance": str(provenance_link),
            "repomix_version": provenance["repomix_version"],
            "runtime_lock_sha256": provenance["runtime_lock_sha256"],
            "node_version": provenance["node_version"],
            "npm_version": provenance["npm_version"],
            "snapshot": str(links["repomix.xml"]),
            "snapshot_sha256": snapshot_sha,
        }
        temporary_name = f".current.{secrets.token_hex(16)}"
        descriptor = os.open(
            temporary_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL
            | (os.O_NOFOLLOW if hasattr(os, "O_NOFOLLOW") else 0),
            0o600,
            dir_fd=context_descriptor,
        )
        try:
            content = json.dumps(
                current_payload,
                ensure_ascii=False,
                sort_keys=True,
            ).encode("utf-8") + b"\n"
            remaining = memoryview(content)
            while remaining:
                written = os.write(descriptor, remaining)
                remaining = remaining[written:]
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        try:
            os.replace(
                temporary_name,
                "current.json",
                src_dir_fd=context_descriptor,
                dst_dir_fd=context_descriptor,
            )
            os.fsync(context_descriptor)
        finally:
            try:
                os.unlink(temporary_name, dir_fd=context_descriptor)
            except FileNotFoundError:
                pass

    finally:
        os.close(snapshots_descriptor)
        os.close(context_descriptor)
    return bundle


def validate_graph_paths(manifest_path: Path, graph_result_path: Path) -> int:
    manifest = load_manifest(manifest_path.expanduser().resolve())
    graph_result_path = graph_result_path.expanduser().resolve()
    try:
        result = json.loads(graph_result_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise InventoryError("graph path query returned invalid JSON") from exc
    if result.get("columns") != ["f.file_path"] or not isinstance(result.get("rows"), list):
        raise InventoryError("graph path query returned an unexpected schema")
    paths: List[str] = []
    for row in result["rows"]:
        if not isinstance(row, list) or len(row) != 1 or not isinstance(row[0], str):
            raise InventoryError("graph path query returned an invalid row")
        paths.append(validate_protocol_path(row[0], "graph file path"))
    if not paths or len(paths) != len(set(paths)):
        raise InventoryError("graph path query is empty or contains duplicates")
    if result.get("total") != len(paths):
        raise InventoryError("graph path query was truncated")
    approved = {str(item["path"]) for item in manifest["files"]}
    unexpected = sorted(set(paths) - approved)
    if unexpected:
        raise InventoryError(f"graph contains paths outside its manifest: {unexpected[:10]}")
    return len(paths)


def add_inventory_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--ignore-file", required=True)
    parser.add_argument(
        "--allow-untracked",
        action="append",
        default=[],
        metavar="PATH",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    inventory_parser = subparsers.add_parser("inventory")
    add_inventory_arguments(inventory_parser)
    inventory_parser.add_argument(
        "--format",
        choices=("repomix-lines", "json"),
        default="json",
    )
    inventory_parser.add_argument("--manifest")
    inventory_parser.add_argument("--profile-config")
    inventory_parser.add_argument("--profile")

    shadow_parser = subparsers.add_parser("prepare-shadow")
    add_inventory_arguments(shadow_parser)
    shadow_parser.add_argument("--cache-dir", required=True)

    activate_parser = subparsers.add_parser("activate-shadow")
    activate_parser.add_argument("--cache-dir", required=True)
    activate_parser.add_argument("--shadow-path", required=True)

    current_parser = subparsers.add_parser("current-shadow")
    current_parser.add_argument("--cache-dir", required=True)

    current_manifest_parser = subparsers.add_parser("current-manifest")
    current_manifest_parser.add_argument("--cache-dir", required=True)

    verify_parser = subparsers.add_parser("verify-shadow")
    verify_parser.add_argument("--cache-dir", required=True)
    verify_parser.add_argument("--shadow-path", required=True)

    snapshot_parser = subparsers.add_parser("validate-snapshot")
    snapshot_parser.add_argument("--manifest", required=True)
    snapshot_parser.add_argument("--snapshot", required=True)

    graph_parser = subparsers.add_parser("validate-graph-paths")
    graph_parser.add_argument("--manifest", required=True)
    graph_parser.add_argument("--graph-result", required=True)

    cleanup_parser = subparsers.add_parser("cleanup-generations")
    cleanup_parser.add_argument("--cache-dir", required=True)

    materialize_parser = subparsers.add_parser("materialize-snapshot-input")
    materialize_parser.add_argument("--repo-root", required=True)
    materialize_parser.add_argument("--manifest", required=True)
    materialize_parser.add_argument("--destination", required=True)

    context_layout_parser = subparsers.add_parser("prepare-context-layout")
    context_layout_parser.add_argument("--repo-root", required=True)

    publish_context_parser = subparsers.add_parser("publish-context-bundle")
    publish_context_parser.add_argument("--repo-root", required=True)
    publish_context_parser.add_argument("--build-dir", required=True)
    publish_context_parser.add_argument("--bundle-id", required=True)
    publish_context_parser.add_argument("--packed-count", required=True, type=int)

    cache_layout_parser = subparsers.add_parser("prepare-cache-layout")
    cache_layout_parser.add_argument("--repo-root", required=True)
    cache_layout_parser.add_argument("--cache-dir", required=True)

    remove_snapshot_parser = subparsers.add_parser("remove-snapshot-input")
    remove_snapshot_parser.add_argument("--repo-root", required=True)
    remove_snapshot_parser.add_argument("--destination", required=True)

    acquire_lock_parser = subparsers.add_parser("acquire-lock")
    acquire_lock_parser.add_argument("--repo-root", required=True)
    acquire_lock_parser.add_argument("--cache-dir", required=True)
    acquire_lock_parser.add_argument("--kind", choices=sorted(CONTROLLED_LOCKS), required=True)
    acquire_lock_parser.add_argument("--pid", type=int, required=True)

    release_lock_parser = subparsers.add_parser("release-lock")
    release_lock_parser.add_argument("--repo-root", required=True)
    release_lock_parser.add_argument("--cache-dir", required=True)
    release_lock_parser.add_argument("--kind", choices=sorted(CONTROLLED_LOCKS), required=True)
    release_lock_parser.add_argument("--token", required=True)
    return parser.parse_args()


def main() -> None:
    arguments = parse_args()
    try:
        if arguments.command in {"inventory", "prepare-shadow"}:
            root = Path(arguments.repo_root)
            manifest = build_inventory(
                root,
                Path(arguments.ignore_file),
                arguments.allow_untracked,
                Path(arguments.profile_config)
                if arguments.command == "inventory" and arguments.profile_config
                else None,
                arguments.profile if arguments.command == "inventory" else None,
            )
            if arguments.command == "inventory":
                if arguments.manifest:
                    repository_root = ensure_repository(root)
                    output_root, _snapshots = controlled_context_layout(
                        repository_root,
                        create=False,
                    )
                    manifest_path = lexical_absolute(Path(arguments.manifest))
                    try:
                        relative_manifest = manifest_path.relative_to(output_root)
                    except ValueError as exc:
                        raise InventoryError("manifest path escapes .ai-context") from exc
                    if (
                        len(relative_manifest.parts) != 2
                        or not relative_manifest.parts[0].startswith(".building.")
                        or relative_manifest.parts[1] != "manifest.json"
                    ):
                        raise InventoryError("manifest path must be inside an isolated build directory")
                    ensure_direct_child_directory(
                        output_root,
                        relative_manifest.parts[0],
                        "snapshot build directory",
                        create=False,
                        mode=0o700,
                        parent_owner_private=True,
                    )
                    atomic_write_json(manifest_path, manifest)
                if arguments.format == "repomix-lines":
                    for item in manifest["files"]:
                        print(item["path"])
                else:
                    json.dump(manifest, sys.stdout, ensure_ascii=False, sort_keys=True)
                    sys.stdout.write("\n")
            else:
                root = ensure_repository(root)
                shadow = create_shadow(root, Path(arguments.cache_dir), manifest)
                print(shadow)
        elif arguments.command == "activate-shadow":
            activate_shadow(
                Path(arguments.cache_dir),
                Path(arguments.shadow_path),
            )
        elif arguments.command == "current-shadow":
            print(current_shadow(Path(arguments.cache_dir)))
        elif arguments.command == "current-manifest":
            print(current_manifest(Path(arguments.cache_dir)))
        elif arguments.command == "verify-shadow":
            manifest = verify_shadow(
                Path(arguments.cache_dir),
                Path(arguments.shadow_path),
            )
            print(manifest["inventory_sha256"])
        elif arguments.command == "validate-snapshot":
            count = validate_snapshot(
                Path(arguments.manifest),
                Path(arguments.snapshot),
            )
            print(count)
        elif arguments.command == "validate-graph-paths":
            count = validate_graph_paths(
                Path(arguments.manifest),
                Path(arguments.graph_result),
            )
            print(count)
        elif arguments.command == "cleanup-generations":
            print(cleanup_inactive_generations(Path(arguments.cache_dir)))
        elif arguments.command == "materialize-snapshot-input":
            print(
                materialize_snapshot_input(
                    Path(arguments.repo_root),
                    Path(arguments.manifest),
                    Path(arguments.destination),
                )
            )
        elif arguments.command == "prepare-context-layout":
            print(prepare_context_layout(Path(arguments.repo_root)))
        elif arguments.command == "publish-context-bundle":
            print(
                publish_context_bundle(
                    Path(arguments.repo_root),
                    Path(arguments.build_dir),
                    arguments.bundle_id,
                    arguments.packed_count,
                )
            )
        elif arguments.command == "prepare-cache-layout":
            print(
                prepare_cache_layout(
                    Path(arguments.repo_root),
                    Path(arguments.cache_dir),
                )
            )
        elif arguments.command == "remove-snapshot-input":
            remove_snapshot_input(
                Path(arguments.repo_root),
                Path(arguments.destination),
            )
        elif arguments.command == "acquire-lock":
            print(
                acquire_controlled_lock(
                    Path(arguments.repo_root),
                    Path(arguments.cache_dir),
                    arguments.kind,
                    arguments.pid,
                )
            )
        elif arguments.command == "release-lock":
            release_controlled_lock(
                Path(arguments.repo_root),
                Path(arguments.cache_dir),
                arguments.kind,
                arguments.token,
            )
    except InventoryError as exc:
        raise SystemExit(f"ai-context-inputs: {exc}") from exc


if __name__ == "__main__":
    os.umask(0o077)
    main()
