from __future__ import annotations

import importlib.util
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1]
MODULE_PATH = SCRIPTS_DIR / "ai_tool_subprocess.py"
SPEC = importlib.util.spec_from_file_location("ai_tool_subprocess_test", MODULE_PATH)
if SPEC is None or SPEC.loader is None:  # pragma: no cover - import contract
    raise RuntimeError(f"could not load {MODULE_PATH}")
bounded = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = bounded
SPEC.loader.exec_module(bounded)


class BoundedSubprocessTests(unittest.TestCase):
    def assert_process_disappears(self, process_id: int) -> None:
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            completed = subprocess.run(
                ["ps", "-o", "stat=", "-p", str(process_id)],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                encoding="utf-8",
                check=False,
            )
            if not completed.stdout.strip():
                return
            time.sleep(0.05)
        self.fail(f"child process survived bounded invocation: {process_id}")

    @unittest.skipUnless(os.name == "posix" and hasattr(os, "fork"), "POSIX fork required")
    def test_timeout_kills_forked_pipe_holder_after_leader_exits(self) -> None:
        with tempfile.TemporaryDirectory(prefix="narraverse-process-group-") as temporary:
            root = Path(temporary)
            pid_path = root / "child.pid"
            script = (
                "import os,pathlib,sys,time\n"
                "pid=os.fork()\n"
                "if pid:\n"
                "    raise SystemExit(0)\n"
                "pathlib.Path(sys.argv[1]).write_text(str(os.getpid()))\n"
                "time.sleep(30)\n"
            )
            result = bounded.run_bounded_process(
                [sys.executable, "-c", script, str(pid_path)],
                cwd=root,
                environment=os.environ.copy(),
                input_bytes=b"",
                timeout_seconds=1,
                stdout_limit=4096,
                stderr_limit=4096,
            )
            self.assertEqual(result.failure, "timeout")
            child_pid = int(pid_path.read_text(encoding="utf-8"))
            self.assert_process_disappears(child_pid)

    @unittest.skipUnless(os.name == "posix" and hasattr(os, "fork"), "POSIX fork required")
    def test_successful_leader_cannot_leave_a_detached_pipe_closed_child(self) -> None:
        with tempfile.TemporaryDirectory(prefix="narraverse-process-group-") as temporary:
            root = Path(temporary)
            pid_path = root / "child.pid"
            script = (
                "import os,pathlib,sys,time\n"
                "pid=os.fork()\n"
                "if pid:\n"
                "    raise SystemExit(0)\n"
                "devnull=os.open(os.devnull, os.O_RDWR)\n"
                "for fd in (0,1,2): os.dup2(devnull, fd)\n"
                "pathlib.Path(sys.argv[1]).write_text(str(os.getpid()))\n"
                "time.sleep(30)\n"
            )
            result = bounded.run_bounded_process(
                [sys.executable, "-c", script, str(pid_path)],
                cwd=root,
                environment=os.environ.copy(),
                input_bytes=b"",
                timeout_seconds=5,
                stdout_limit=4096,
                stderr_limit=4096,
            )
            self.assertIsNone(result.failure)
            self.assertEqual(result.returncode, 0)
            child_pid = int(pid_path.read_text(encoding="utf-8"))
            self.assert_process_disappears(child_pid)

    def test_watched_file_limit_terminates_the_process_group(self) -> None:
        with tempfile.TemporaryDirectory(prefix="narraverse-watched-file-") as temporary:
            root = Path(temporary)
            snapshot_path = root / "snapshot.xml"
            pid_path = root / "child.pid"
            script = (
                "import pathlib,subprocess,sys,time\n"
                "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)'])\n"
                "pathlib.Path(sys.argv[1]).write_text(str(child.pid))\n"
                "pathlib.Path(sys.argv[2]).write_bytes(b'x' * 4097)\n"
                "time.sleep(30)\n"
            )
            result = bounded.run_bounded_process(
                [sys.executable, "-c", script, str(pid_path), str(snapshot_path)],
                cwd=root,
                environment=os.environ.copy(),
                input_bytes=b"",
                timeout_seconds=10,
                stdout_limit=4096,
                stderr_limit=4096,
                watched_files={snapshot_path: 4096},
            )
            self.assertEqual(result.failure, "watched_file_limit")
            child_pid = int(pid_path.read_text(encoding="utf-8"))
            self.assert_process_disappears(child_pid)

    @unittest.skipUnless(os.name == "posix", "POSIX signal semantics required")
    def test_sigterm_to_runner_terminates_native_process_group(self) -> None:
        with tempfile.TemporaryDirectory(prefix="narraverse-signal-") as temporary:
            root = Path(temporary)
            pid_path = root / "child.pid"
            driver_path = root / "driver.py"
            driver_path.write_text(
                "import importlib.util,os,pathlib,sys\n"
                f"spec=importlib.util.spec_from_file_location('bounded_signal', {str(MODULE_PATH)!r})\n"
                "module=importlib.util.module_from_spec(spec)\n"
                "sys.modules[spec.name]=module\n"
                "spec.loader.exec_module(module)\n"
                "root=pathlib.Path(sys.argv[1])\n"
                "pid_path=root/'child.pid'\n"
                "child_code='import os,pathlib,sys,time; pathlib.Path(sys.argv[1]).write_text(str(os.getpid())); time.sleep(30)'\n"
                "result=module.run_bounded_process([sys.executable,'-c',child_code,str(pid_path)], cwd=root, environment=os.environ.copy(), input_bytes=b'', timeout_seconds=60, stdout_limit=4096, stderr_limit=4096)\n"
                "raise SystemExit(0 if result.failure == 'signal' else 3)\n",
                encoding="utf-8",
            )
            runner = subprocess.Popen([sys.executable, str(driver_path), str(root)])
            deadline = time.monotonic() + 5
            while not pid_path.exists() and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertTrue(pid_path.exists())
            child_pid = int(pid_path.read_text(encoding="utf-8"))
            runner.send_signal(signal.SIGTERM)
            self.assertEqual(runner.wait(timeout=5), 0)
            self.assert_process_disappears(child_pid)


if __name__ == "__main__":
    unittest.main()
