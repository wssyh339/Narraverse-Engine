#!/usr/bin/env python3
"""Run a local AI tool with a minimal environment, timeout, and streaming caps."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Dict

from ai_tool_subprocess import run_bounded_process


MAX_INPUT_BYTES = 128 * 1024 * 1024
MAX_OUTPUT_BYTES = 32 * 1024 * 1024
MAX_TIMEOUT_SECONDS = 1800
MAX_WATCHED_FILE_BYTES = 1024 * 1024 * 1024


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cwd", required=True)
    parser.add_argument("--timeout", required=True, type=int)
    parser.add_argument("--stdout-limit", required=True, type=int)
    parser.add_argument("--stderr-limit", required=True, type=int)
    parser.add_argument("--clear-environment", action="store_true")
    parser.add_argument("--env", action="append", default=[])
    parser.add_argument("--watch-file", action="append", default=[])
    parser.add_argument("command", nargs=argparse.REMAINDER)
    return parser.parse_args()


def parse_assignments(values: list[str], label: str) -> Dict[str, str]:
    result: Dict[str, str] = {}
    for value in values:
        name, separator, assigned = value.partition("=")
        if not separator or not name or "\x00" in value:
            raise SystemExit(f"run-bounded-ai-tool: invalid {label}")
        result[name] = assigned
    return result


def main() -> None:
    arguments = parse_args()
    command = list(arguments.command)
    if command[:1] == ["--"]:
        command = command[1:]
    if not command:
        raise SystemExit("run-bounded-ai-tool: command is required")
    if not 1 <= arguments.timeout <= MAX_TIMEOUT_SECONDS:
        raise SystemExit("run-bounded-ai-tool: timeout is invalid")
    if not 0 <= arguments.stdout_limit <= MAX_OUTPUT_BYTES:
        raise SystemExit("run-bounded-ai-tool: stdout limit is invalid")
    if not 0 <= arguments.stderr_limit <= MAX_OUTPUT_BYTES:
        raise SystemExit("run-bounded-ai-tool: stderr limit is invalid")
    cwd = Path(arguments.cwd).expanduser().resolve()
    if not cwd.is_dir() or cwd.is_symlink():
        raise SystemExit("run-bounded-ai-tool: cwd is unsafe")
    environment = {} if arguments.clear_environment else os.environ.copy()
    environment.update(parse_assignments(arguments.env, "environment assignment"))
    watched: Dict[Path, int] = {}
    for raw in arguments.watch_file:
        path_value, separator, limit_value = raw.rpartition("=")
        if not separator:
            raise SystemExit("run-bounded-ai-tool: invalid watched file")
        try:
            limit = int(limit_value)
        except ValueError as exc:
            raise SystemExit("run-bounded-ai-tool: invalid watched file limit") from exc
        if not 0 <= limit <= MAX_WATCHED_FILE_BYTES:
            raise SystemExit("run-bounded-ai-tool: watched file limit is invalid")
        watched[Path(path_value).expanduser()] = limit
    input_bytes = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
    if len(input_bytes) > MAX_INPUT_BYTES:
        raise SystemExit("run-bounded-ai-tool: stdin exceeds the limit")
    try:
        result = run_bounded_process(
            command,
            cwd=cwd,
            environment=environment,
            input_bytes=input_bytes,
            timeout_seconds=arguments.timeout,
            stdout_limit=arguments.stdout_limit,
            stderr_limit=arguments.stderr_limit,
            watched_files=watched,
        )
    except OSError as exc:
        raise SystemExit("run-bounded-ai-tool: process could not start") from exc
    if result.failure is not None:
        raise SystemExit(f"run-bounded-ai-tool: process failed safely ({result.failure})")
    sys.stdout.buffer.write(result.stdout)
    sys.stdout.buffer.flush()
    if result.stderr:
        sys.stderr.buffer.write(result.stderr)
        sys.stderr.buffer.flush()
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
