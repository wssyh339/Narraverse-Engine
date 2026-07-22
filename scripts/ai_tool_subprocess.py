#!/usr/bin/env python3
"""Bounded subprocess primitives shared by optional local AI development tools."""

from __future__ import annotations

import os
import selectors
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional, Sequence


@dataclass(frozen=True)
class BoundedProcessResult:
    returncode: int
    stdout: bytes
    stderr: bytes
    failure: Optional[str]


def stop_process_group(process: subprocess.Popen[bytes]) -> None:
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        elif process.poll() is None:  # pragma: no cover - Windows fallback
            process.kill()
    except (ProcessLookupError, PermissionError):
        pass


def run_bounded_process(
    command: Sequence[str],
    *,
    cwd: Path,
    environment: Mapping[str, str],
    input_bytes: bytes,
    timeout_seconds: int,
    stdout_limit: int,
    stderr_limit: int,
    watched_files: Optional[Mapping[Path, int]] = None,
) -> BoundedProcessResult:
    """Run a child with streaming byte caps and whole-process-group termination."""
    if timeout_seconds <= 0 or stdout_limit < 0 or stderr_limit < 0:
        raise ValueError("bounded subprocess limits must be positive")
    process = subprocess.Popen(
        list(command),
        cwd=str(cwd),
        env=dict(environment),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=(os.name == "posix"),
    )
    if process.stdin is None or process.stdout is None or process.stderr is None:
        stop_process_group(process)
        process.wait()
        raise OSError("could not create bounded subprocess pipes")

    selector = selectors.DefaultSelector()
    for stream in (process.stdin, process.stdout, process.stderr):
        os.set_blocking(stream.fileno(), False)
    if input_bytes:
        selector.register(process.stdin, selectors.EVENT_WRITE, "stdin")
    else:
        process.stdin.close()
    selector.register(process.stdout, selectors.EVENT_READ, "stdout")
    selector.register(process.stderr, selectors.EVENT_READ, "stderr")

    pending = memoryview(input_bytes)
    stdout_chunks: list[bytes] = []
    stderr_chunks: list[bytes] = []
    stdout_size = 0
    stderr_size = 0
    failure: Optional[str] = None
    watched = dict(watched_files or {})
    interrupted_signal: Optional[int] = None
    previous_signal_handlers: dict[int, object] = {}

    def handle_signal(signum: int, _frame: object) -> None:
        nonlocal interrupted_signal
        interrupted_signal = signum
        stop_process_group(process)

    if threading.current_thread() is threading.main_thread():
        for signum in (signal.SIGINT, signal.SIGTERM):
            previous_signal_handlers[signum] = signal.getsignal(signum)
            signal.signal(signum, handle_signal)

    def watched_failure() -> Optional[str]:
        for raw_path, limit in watched.items():
            path = Path(raw_path)
            if limit < 0:
                return "watched_file_limit"
            if not os.path.lexists(str(path)):
                continue
            try:
                path_stat = path.lstat()
            except OSError:
                return "watched_file_unsafe"
            if not os.path.isfile(path) or os.path.islink(path):
                return "watched_file_unsafe"
            if path_stat.st_size > limit:
                return "watched_file_limit"
        return None

    deadline = time.monotonic() + timeout_seconds
    try:
        while selector.get_map():
            if interrupted_signal is not None:
                failure = "signal"
                break
            failure = watched_failure()
            if failure is not None:
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                failure = "timeout"
                break
            events = selector.select(min(remaining, 0.1))
            if not events and process.poll() is not None:
                events = [
                    (key, selectors.EVENT_READ)
                    for key in list(selector.get_map().values())
                    if key.data in {"stdout", "stderr"}
                ]
            for key, _mask in events:
                stream = key.fileobj
                label = key.data
                if label == "stdin":
                    try:
                        written = os.write(stream.fileno(), pending[:65536])
                    except (BrokenPipeError, OSError):
                        pending = pending[len(pending) :]
                    else:
                        pending = pending[written:]
                    if not pending:
                        selector.unregister(stream)
                        stream.close()
                    continue
                try:
                    chunk = os.read(stream.fileno(), 65536)
                except BlockingIOError:
                    continue
                except OSError:
                    failure = "io_error"
                    break
                if not chunk:
                    selector.unregister(stream)
                    stream.close()
                    continue
                if label == "stdout":
                    stdout_size += len(chunk)
                    if stdout_size > stdout_limit:
                        failure = "stdout_limit"
                        break
                    stdout_chunks.append(chunk)
                else:
                    stderr_size += len(chunk)
                    if stderr_size > stderr_limit:
                        failure = "stderr_limit"
                        break
                    stderr_chunks.append(chunk)
            if failure is not None:
                break
        if interrupted_signal is not None:
            failure = failure or "signal"
        failure = failure or watched_failure()
    finally:
        if failure is not None:
            stop_process_group(process)
        for key in list(selector.get_map().values()):
            try:
                selector.unregister(key.fileobj)
            except (KeyError, ValueError):
                pass
            try:
                key.fileobj.close()
            except OSError:
                pass
        selector.close()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            failure = failure or "timeout"
            stop_process_group(process)
            process.wait()
        # A successful leader may have daemonized descendants after closing its
        # pipes. Terminate the original process group after reaping the leader so
        # every bounded invocation leaves no same-group background process.
        stop_process_group(process)
        for signum, previous in previous_signal_handlers.items():
            signal.signal(signum, previous)
    return BoundedProcessResult(
        returncode=int(process.returncode),
        stdout=b"".join(stdout_chunks),
        stderr=b"".join(stderr_chunks),
        failure=failure,
    )
