#!/usr/bin/env python3
"""Validate public CLI query arguments with the exact MCP read-only policy."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def load_proxy() -> object:
    path = Path(__file__).resolve().with_name("code-intel-mcp-proxy.py")
    spec = importlib.util.spec_from_file_location("narraverse_code_intel_proxy", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> None:
    if len(sys.argv) != 4:
        raise SystemExit("usage: code-intel-validate.py TOOL PROJECT JSON_OBJECT")
    tool, project, raw = sys.argv[1:]
    proxy = load_proxy()
    if tool not in proxy.ALLOWED_TOOLS:
        raise SystemExit("tool is not in the read-only allowlist")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"query payload is not valid JSON: {exc}") from exc
    try:
        validated = proxy.validate_arguments(tool, payload, Path(project).resolve())
    except proxy.InvalidParams as exc:
        raise SystemExit(f"query payload violates the read-only policy: {exc}") from exc
    print(json.dumps(validated, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
