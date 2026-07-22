#!/usr/bin/env python3
"""Run the pinned codebase-memory binary with a clean environment and hard I/O caps."""

from __future__ import annotations

import argparse
import hashlib
import os
import stat
import sys
from pathlib import Path
from typing import Dict

from ai_tool_subprocess import run_bounded_process


MAX_INPUT_BYTES = 128 * 1024
MAX_STDOUT_BYTES = 32 * 1024 * 1024
MAX_STDERR_BYTES = 1024 * 1024
MAX_TIMEOUT_SECONDS = 1800


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", required=True)
    parser.add_argument("--binary-sha256", required=True)
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--cache-dir", required=True)
    parser.add_argument("--stdout-limit", required=True, type=int)
    parser.add_argument("--stderr-limit", required=True, type=int)
    parser.add_argument("--timeout", required=True, type=int)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    return parser.parse_args()


def safe_environment(repo_root: Path, cache_dir: Path) -> Dict[str, str]:
    runtime_home = cache_dir / ".runtime-home"
    if os.path.lexists(runtime_home):
        runtime_stat = runtime_home.lstat()
        if stat.S_ISLNK(runtime_stat.st_mode) or not stat.S_ISDIR(runtime_stat.st_mode):
            raise SystemExit("code-intel-native: runtime HOME is unsafe")
    else:
        runtime_home.mkdir(mode=0o700)
    runtime_home.chmod(0o700)
    allowed = {"PATH", "LANG", "LC_ALL", "LC_CTYPE", "TMPDIR", "SYSTEMROOT", "WINDIR", "PATHEXT"}
    environment = {
        name: value
        for name, value in os.environ.items()
        if name in allowed or name.startswith("LC_")
    }
    environment.update(
        {
            "CBM_ALLOWED_ROOT": str(repo_root),
            "CBM_CACHE_DIR": str(cache_dir),
            "CBM_LOG_LEVEL": "warn",
            "HOME": str(runtime_home),
            "USERPROFILE": str(runtime_home),
        }
    )
    return environment


def main() -> None:
    arguments = parse_args()
    command = list(arguments.command)
    if command[:1] == ["--"]:
        command = command[1:]
    if not command:
        raise SystemExit("code-intel-native: native command is required")
    if not 0 <= arguments.stdout_limit <= MAX_STDOUT_BYTES:
        raise SystemExit("code-intel-native: stdout limit is invalid")
    if not 0 <= arguments.stderr_limit <= MAX_STDERR_BYTES:
        raise SystemExit("code-intel-native: stderr limit is invalid")
    if not 1 <= arguments.timeout <= MAX_TIMEOUT_SECONDS:
        raise SystemExit("code-intel-native: timeout is invalid")

    binary = Path(arguments.binary).expanduser()
    expected_binary_sha = arguments.binary_sha256
    if len(expected_binary_sha) != 64 or any(
        character not in "0123456789abcdef" for character in expected_binary_sha
    ):
        raise SystemExit("code-intel-native: pinned binary digest is invalid")
    try:
        binary_stat = binary.lstat()
    except OSError as exc:
        raise SystemExit("code-intel-native: pinned binary is missing") from exc
    if (
        stat.S_ISLNK(binary_stat.st_mode)
        or not stat.S_ISREG(binary_stat.st_mode)
        or not os.access(binary, os.X_OK)
    ):
        raise SystemExit("code-intel-native: pinned binary must be a regular executable")
    binary_identity = (binary_stat.st_dev, binary_stat.st_ino)
    digest = hashlib.sha256()
    flags = os.O_RDONLY | (os.O_NOFOLLOW if hasattr(os, "O_NOFOLLOW") else 0)
    descriptor = os.open(str(binary), flags)
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != binary_identity:
            raise SystemExit("code-intel-native: pinned binary changed while opening")
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    finally:
        os.close(descriptor)
    if digest.hexdigest() != expected_binary_sha:
        raise SystemExit("code-intel-native: pinned binary integrity check failed")
    binary = binary.resolve()
    repo_root = Path(arguments.repo_root).expanduser().resolve()
    cache_dir = Path(arguments.cache_dir).expanduser().resolve()
    if cache_dir != repo_root / ".codebase-memory":
        raise SystemExit("code-intel-native: cache directory is outside the repository")

    input_bytes = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
    if len(input_bytes) > MAX_INPUT_BYTES:
        raise SystemExit("code-intel-native: native input exceeds the limit")
    try:
        result = run_bounded_process(
            [str(binary), *command],
            cwd=repo_root,
            environment=safe_environment(repo_root, cache_dir),
            input_bytes=input_bytes,
            timeout_seconds=arguments.timeout,
            stdout_limit=arguments.stdout_limit,
            stderr_limit=arguments.stderr_limit,
        )
    except OSError as exc:
        raise SystemExit("code-intel-native: native process could not start") from exc

    after = binary.lstat()
    if (after.st_dev, after.st_ino) != binary_identity:
        raise SystemExit("code-intel-native: pinned binary identity changed during execution")
    after_digest = hashlib.sha256(binary.read_bytes()).hexdigest()
    if after_digest != expected_binary_sha:
        raise SystemExit("code-intel-native: pinned binary changed during execution")

    if result.failure == "timeout":
        raise SystemExit("code-intel-native: native process timed out")
    if result.failure in {"stdout_limit", "stderr_limit"}:
        raise SystemExit("code-intel-native: native process exceeded its output limit")
    if result.failure is not None:
        raise SystemExit("code-intel-native: native process failed safely")
    sys.stdout.buffer.write(result.stdout)
    sys.stdout.buffer.flush()
    if result.stderr:
        sys.stderr.buffer.write(result.stderr)
        sys.stderr.buffer.flush()
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
