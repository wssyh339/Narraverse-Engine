#!/usr/bin/env python3
"""Repository-scoped, read-only MCP facade for codebase-memory-mcp."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Set

from ai_tool_subprocess import run_bounded_process


PROXY_VERSION = "1.0.0"
SUPPORTED_PROTOCOL_VERSION = "2025-06-18"
MAX_REQUEST_BYTES = 64 * 1024
MAX_NATIVE_OUTPUT_BYTES = 256 * 1024
MAX_NATIVE_ERROR_BYTES = 32 * 1024
MAX_RESULT_BYTES = 256 * 1024
TOOL_TIMEOUT_SECONDS = 45
READ_ONLY_CYPHER_FORBIDDEN = {
    "ALTER",
    "CALL",
    "CONSTRAINT",
    "CREATE",
    "DELETE",
    "DENY",
    "DETACH",
    "DROP",
    "FOREACH",
    "GRANT",
    "INDEX",
    "LOAD",
    "MERGE",
    "PROFILE",
    "REMOVE",
    "RENAME",
    "REVOKE",
    "SET",
    "SHOW",
    "START",
    "STOP",
    "TERMINATE",
    "TRANSACTION",
    "USE",
}


def object_schema(
    properties: Mapping[str, Mapping[str, Any]],
    required: Iterable[str] = (),
) -> Dict[str, Any]:
    return {
        "type": "object",
        "properties": dict(properties),
        "required": list(required),
        "additionalProperties": False,
    }


READ_ONLY_ANNOTATIONS = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": False,
}
GENERIC_OUTPUT_SCHEMA = {"type": "object", "additionalProperties": True}
TOOL_DEFINITIONS: List[Dict[str, Any]] = [
    {
        "name": "search_graph",
        "title": "Search graph",
        "description": "Search repository-scoped graph symbols and relationships.",
        "inputSchema": object_schema(
            {
                "query": {"type": "string"},
                "name_pattern": {"type": "string"},
                "qn_pattern": {"type": "string"},
                "label": {"type": "string"},
                "file_pattern": {"type": "string"},
                "relationship": {"type": "string"},
                "semantic_query": {"type": "array", "items": {"type": "string"}},
                "include_connected": {"type": "boolean"},
                "exclude_entry_points": {"type": "boolean"},
                "min_degree": {"type": "integer"},
                "max_degree": {"type": "integer"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 200},
                "offset": {"type": "integer", "minimum": 0, "maximum": 10000},
            }
        ),
        "outputSchema": GENERIC_OUTPUT_SCHEMA,
        "annotations": READ_ONLY_ANNOTATIONS,
    },
    {
        "name": "query_graph",
        "title": "Query graph",
        "description": "Run a bounded read-only Cypher query against this repository.",
        "inputSchema": object_schema(
            {
                "query": {"type": "string"},
                "max_rows": {"type": "integer", "minimum": 1, "maximum": 500},
            },
            required=("query",),
        ),
        "outputSchema": GENERIC_OUTPUT_SCHEMA,
        "annotations": READ_ONLY_ANNOTATIONS,
    },
    {
        "name": "trace_path",
        "title": "Trace path",
        "description": "Trace bounded call, data-flow, or cross-service paths.",
        "inputSchema": object_schema(
            {
                "function_name": {"type": "string"},
                "depth": {"type": "integer", "minimum": 1, "maximum": 8},
                "direction": {
                    "type": "string",
                    "enum": ["inbound", "outbound", "both"],
                },
                "mode": {
                    "type": "string",
                    "enum": ["calls", "data_flow", "cross_service"],
                },
                "parameter_name": {"type": "string"},
                "edge_types": {"type": "array", "items": {"type": "string"}},
                "include_tests": {"type": "boolean"},
                "risk_labels": {"type": "boolean"},
            },
            required=("function_name",),
        ),
        "outputSchema": GENERIC_OUTPUT_SCHEMA,
        "annotations": READ_ONLY_ANNOTATIONS,
    },
    {
        "name": "get_code_snippet",
        "title": "Get code snippet",
        "description": "Read a bounded source snippet for an indexed symbol.",
        "inputSchema": object_schema(
            {
                "qualified_name": {"type": "string"},
                "include_neighbors": {"type": "boolean"},
            },
            required=("qualified_name",),
        ),
        "outputSchema": GENERIC_OUTPUT_SCHEMA,
        "annotations": READ_ONLY_ANNOTATIONS,
    },
    {
        "name": "get_graph_schema",
        "title": "Get graph schema",
        "description": "Read graph node and relationship types.",
        "inputSchema": object_schema({}),
        "outputSchema": GENERIC_OUTPUT_SCHEMA,
        "annotations": READ_ONLY_ANNOTATIONS,
    },
    {
        "name": "get_architecture",
        "title": "Get architecture",
        "description": "Read a bounded architecture summary for this repository.",
        "inputSchema": object_schema(
            {
                "aspects": {"type": "array", "items": {"type": "string"}},
                "path": {"type": "string"},
            }
        ),
        "outputSchema": GENERIC_OUTPUT_SCHEMA,
        "annotations": READ_ONLY_ANNOTATIONS,
    },
    {
        "name": "search_code",
        "title": "Search code",
        "description": "Run bounded graph-augmented text search in this repository.",
        "inputSchema": object_schema(
            {
                "pattern": {"type": "string"},
                "regex": {"type": "boolean"},
                "file_pattern": {"type": "string"},
                "path_filter": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                "context": {"type": "integer", "minimum": 0, "maximum": 20},
                "mode": {
                    "type": "string",
                    "enum": ["compact", "full", "files"],
                },
            },
            required=("pattern",),
        ),
        "outputSchema": GENERIC_OUTPUT_SCHEMA,
        "annotations": READ_ONLY_ANNOTATIONS,
    },
    {
        "name": "index_status",
        "title": "Index status",
        "description": "Read current repository index status.",
        "inputSchema": object_schema({}),
        "outputSchema": GENERIC_OUTPUT_SCHEMA,
        "annotations": READ_ONLY_ANNOTATIONS,
    },
]
TOOL_DEFINITION_BY_NAME = {item["name"]: item for item in TOOL_DEFINITIONS}
ALLOWED_TOOLS: Set[str] = set(TOOL_DEFINITION_BY_NAME)


class InvalidParams(ValueError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", required=True)
    parser.add_argument("--binary-sha256", required=True)
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--cache-dir", required=True)
    parser.add_argument("--input-helper", required=True)
    return parser.parse_args()


def safe_environment(repo_root: Path, cache_dir: Path) -> Dict[str, str]:
    allowed_names = {
        "PATH",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "TMPDIR",
        "SYSTEMROOT",
        "WINDIR",
        "PATHEXT",
    }
    environment = {
        key: value
        for key, value in os.environ.items()
        if key in allowed_names or key.startswith("LC_")
    }
    runtime_home = cache_dir / ".runtime-home"
    if runtime_home.is_symlink() or not runtime_home.is_dir():
        return {}
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


def expect_type(name: str, value: Any, expected: str) -> None:
    valid = False
    if expected == "string":
        valid = isinstance(value, str)
    elif expected == "boolean":
        valid = isinstance(value, bool)
    elif expected == "integer":
        valid = isinstance(value, int) and not isinstance(value, bool)
    elif expected == "array":
        valid = isinstance(value, list)
    if not valid:
        raise InvalidParams(f"{name} must be {expected}")


def validate_string(name: str, value: str, maximum: int = 4096) -> None:
    if not value.strip():
        raise InvalidParams(f"{name} must not be empty")
    if len(value) > maximum:
        raise InvalidParams(f"{name} exceeds {maximum} characters")


def validate_relative_path(value: str) -> None:
    validate_string("path", value, 512)
    candidate = PurePosixPath(value.replace("\\", "/"))
    if candidate.is_absolute() or ".." in candidate.parts:
        raise InvalidParams("path must stay relative to the repository")


def cypher_tokens(query: str) -> List[str]:
    masked: List[str] = []
    quote: Optional[str] = None
    escaped = False
    index = 0
    while index < len(query):
        character = query[index]
        following = query[index + 1] if index + 1 < len(query) else ""
        if quote is not None:
            masked.append(" ")
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                if quote in {"'", '"'} and following == quote:
                    masked.append(" ")
                    index += 1
                else:
                    quote = None
            index += 1
            continue
        if character in {"'", '"', "`"}:
            quote = character
            masked.append(" ")
            index += 1
            continue
        if character == ";" or (character == "/" and following in {"/", "*"}) or (
            character == "*" and following == "/"
        ):
            raise InvalidParams("query_graph rejects comments and multiple statements")
        masked.append(character)
        index += 1
    if quote is not None:
        raise InvalidParams("query_graph contains an unterminated string or identifier")
    return re.findall(r"[A-Za-z_]+", "".join(masked).upper())


def validate_arguments(tool: str, raw: Any, project_root: Path) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        raise InvalidParams("arguments must be a JSON object")
    schema = TOOL_DEFINITION_BY_NAME[tool]["inputSchema"]
    properties = schema["properties"]
    unknown = sorted(set(raw) - set(properties))
    if unknown:
        raise InvalidParams(f"unsupported arguments: {unknown}")
    missing = sorted(set(schema.get("required", [])) - set(raw))
    if missing:
        raise InvalidParams(f"missing required arguments: {missing}")

    arguments: Dict[str, Any] = dict(raw)
    for name, value in arguments.items():
        property_schema = properties[name]
        expected_type = property_schema.get("type")
        expect_type(name, value, expected_type)
        if expected_type == "string":
            validate_string(name, value)
        elif expected_type == "integer":
            minimum = property_schema.get("minimum")
            maximum = property_schema.get("maximum")
            if minimum is not None and value < minimum:
                raise InvalidParams(f"{name} must be >= {minimum}")
            if maximum is not None and value > maximum:
                raise InvalidParams(f"{name} must be <= {maximum}")
        elif expected_type == "array":
            if len(value) > 20:
                raise InvalidParams(f"{name} has too many items")
            for item in value:
                if not isinstance(item, str) or not item.strip() or len(item) > 256:
                    raise InvalidParams(f"{name} must contain short non-empty strings")
        choices = property_schema.get("enum")
        if choices is not None and value not in choices:
            raise InvalidParams(f"{name} must be one of {choices}")

    if tool == "query_graph":
        query = arguments["query"]
        validate_string("query", query, 4000)
        tokens = cypher_tokens(query)
        if not tokens:
            raise InvalidParams("query_graph requires a read-only query")
        first_clause = tokens[0]
        if first_clause not in {"MATCH", "OPTIONAL", "WITH", "UNWIND", "RETURN"}:
            raise InvalidParams("query_graph starts with an unsupported clause")
        if first_clause == "OPTIONAL" and (len(tokens) < 2 or tokens[1] != "MATCH"):
            raise InvalidParams("OPTIONAL must be followed by MATCH")
        forbidden_tokens = sorted(set(tokens).intersection(READ_ONLY_CYPHER_FORBIDDEN))
        if forbidden_tokens:
            raise InvalidParams("query_graph accepts read-only Cypher only")
        arguments.setdefault("max_rows", 200)
    elif tool == "get_architecture" and "path" in arguments:
        validate_relative_path(arguments["path"])
    elif tool == "search_graph" and "semantic_query" in arguments:
        if len(arguments["semantic_query"]) > 10:
            raise InvalidParams("semantic_query accepts at most 10 keywords")
    elif tool == "trace_path":
        arguments.setdefault("depth", 3)
    elif tool == "search_code":
        validate_string("pattern", arguments["pattern"], 1000)
        if "file_pattern" in arguments:
            validate_string("file_pattern", arguments["file_pattern"], 256)
        if "path_filter" in arguments:
            validate_string("path_filter", arguments["path_filter"], 512)
        arguments.setdefault("limit", 10)
        arguments.setdefault("context", 2)

    arguments["project"] = str(project_root)
    return arguments


def sanitize_paths(value: Any, repo_root: Path, project_root: Path) -> Any:
    if isinstance(value, str):
        return value.replace(str(project_root), ".").replace(str(repo_root), ".")
    if isinstance(value, list):
        return [sanitize_paths(item, repo_root, project_root) for item in value]
    if isinstance(value, dict):
        return {
            key: sanitize_paths(item, repo_root, project_root)
            for key, item in value.items()
        }
    return value


def input_integrity_ok(
    input_helper: Path,
    repo_root: Path,
    project_root: Path,
    cache_dir: Path,
) -> bool:
    try:
        completed = subprocess.run(
            [
                sys.executable,
                str(input_helper),
                "verify-shadow",
                "--cache-dir",
                str(cache_dir),
                "--shadow-path",
                str(project_root),
            ],
            cwd=str(repo_root),
            env=safe_environment(repo_root, cache_dir),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0


def binary_integrity_ok(
    binary: Path,
    expected_sha256: str,
    expected_identity: tuple[int, int],
) -> bool:
    try:
        before = binary.lstat()
        if (
            stat.S_ISLNK(before.st_mode)
            or not stat.S_ISREG(before.st_mode)
            or (before.st_dev, before.st_ino) != expected_identity
        ):
            return False
        digest = hashlib.sha256()
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(str(binary), flags)
        try:
            opened = os.fstat(descriptor)
            if (opened.st_dev, opened.st_ino) != expected_identity:
                return False
            while True:
                chunk = os.read(descriptor, 1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
        finally:
            os.close(descriptor)
        after = binary.lstat()
    except OSError:
        return False
    return (
        (after.st_dev, after.st_ino) == expected_identity
        and digest.hexdigest() == expected_sha256
    )


def tool_result(
    binary: Path,
    repo_root: Path,
    project_root: Path,
    cache_dir: Path,
    input_helper: Path,
    binary_sha256: str,
    binary_identity: tuple[int, int],
    tool: str,
    arguments: Mapping[str, Any],
) -> Dict[str, Any]:
    payload = json.dumps(
        arguments,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    if len(payload.encode("utf-8")) > MAX_REQUEST_BYTES:
        raise InvalidParams("tool arguments exceed the request limit")
    if not input_integrity_ok(
        input_helper,
        repo_root,
        project_root,
        cache_dir,
    ):
        return {
            "content": [{"type": "text", "text": "tracked input integrity check failed"}],
            "isError": True,
        }
    if not binary_integrity_ok(binary, binary_sha256, binary_identity):
        return {
            "content": [{"type": "text", "text": "native binary integrity check failed"}],
            "isError": True,
        }
    try:
        native_result = run_bounded_process(
            [str(binary), "cli", tool],
            cwd=repo_root,
            environment=safe_environment(repo_root, cache_dir),
            input_bytes=payload.encode("utf-8"),
            timeout_seconds=TOOL_TIMEOUT_SECONDS,
            stdout_limit=MAX_NATIVE_OUTPUT_BYTES,
            stderr_limit=MAX_NATIVE_ERROR_BYTES,
        )
    except OSError:
        return {
            "content": [{"type": "text", "text": "read-only tool could not start"}],
            "isError": True,
        }

    if not input_integrity_ok(
        input_helper,
        repo_root,
        project_root,
        cache_dir,
    ):
        return {
            "content": [{"type": "text", "text": "tracked input integrity check failed"}],
            "isError": True,
        }
    if not binary_integrity_ok(binary, binary_sha256, binary_identity):
        return {
            "content": [{"type": "text", "text": "native binary integrity check failed"}],
            "isError": True,
        }

    if native_result.failure == "timeout":
        return {
            "content": [{"type": "text", "text": "read-only tool timed out"}],
            "isError": True,
        }
    if native_result.failure in {"stdout_limit", "stderr_limit"}:
        return {
            "content": [
                {
                    "type": "text",
                    "text": (
                        "read-only tool response exceeded the native "
                        "output limit; narrow the query"
                    ),
                }
            ],
            "isError": True,
        }

    if native_result.failure is not None:
        return {
            "content": [{"type": "text", "text": "read-only tool failed safely"}],
            "isError": True,
        }

    stdout = native_result.stdout.decode("utf-8", errors="replace")
    stderr = native_result.stderr.decode("utf-8", errors="replace")
    return_code = native_result.returncode

    if return_code != 0:
        message = stderr.strip() or stdout.strip()
        message = str(sanitize_paths(message, repo_root, project_root))[:2000]
        return {
            "content": [{"type": "text", "text": message or "tool failed"}],
            "isError": True,
        }
    try:
        structured = json.loads(stdout)
    except json.JSONDecodeError:
        return {
            "content": [{"type": "text", "text": "tool returned invalid JSON"}],
            "isError": True,
        }
    structured = sanitize_paths(structured, repo_root, project_root)
    text = json.dumps(structured, ensure_ascii=False, separators=(",", ":"))
    result = {
        "content": [{"type": "text", "text": text}],
        "structuredContent": structured,
        "isError": False,
    }
    encoded_result = json.dumps(
        result,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    if len(encoded_result) > MAX_RESULT_BYTES:
        return {
            "content": [
                {
                    "type": "text",
                    "text": (
                        "read-only tool result exceeded the MCP response limit; "
                        "narrow the query"
                    ),
                }
            ],
            "isError": True,
        }
    return result


def response(identifier: Any, result: Any) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": identifier, "result": result}


def error(identifier: Any, code: int, message: str) -> Dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": identifier,
        "error": {"code": code, "message": message},
    }


def emit(message: Mapping[str, Any]) -> None:
    data = json.dumps(message, ensure_ascii=False, separators=(",", ":"))
    sys.stdout.write(data + "\n")
    sys.stdout.flush()


def serve(
    binary: Path,
    repo_root: Path,
    project_root: Path,
    cache_dir: Path,
    input_helper: Path,
    binary_sha256: str,
    binary_identity: tuple[int, int],
) -> None:
    while True:
        line = sys.stdin.buffer.readline(MAX_REQUEST_BYTES + 1)
        if not line:
            break
        if len(line) > MAX_REQUEST_BYTES:
            emit(error(None, -32600, "request exceeds size limit"))
            while line and not line.endswith(b"\n"):
                line = sys.stdin.buffer.readline(MAX_REQUEST_BYTES + 1)
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            emit(error(None, -32700, "parse error"))
            continue
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
            emit(error(message.get("id") if isinstance(message, dict) else None, -32600, "invalid request"))
            continue

        identifier = message.get("id")
        method = message.get("method")
        params = message.get("params", {})
        is_notification = "id" not in message

        if method == "initialize" and not is_notification:
            if not isinstance(params, dict) or not isinstance(
                params.get("protocolVersion"), str
            ):
                emit(error(identifier, -32602, "initialize params are invalid"))
                continue
            emit(
                response(
                    identifier,
                    {
                        "protocolVersion": SUPPORTED_PROTOCOL_VERSION,
                        "capabilities": {"tools": {"listChanged": False}},
                        "serverInfo": {
                            "name": "narraverse-code-intel-readonly",
                            "version": PROXY_VERSION,
                        },
                        "instructions": (
                            "Repository-scoped read-only code intelligence. "
                            "Project selection and write tools are not exposed."
                        ),
                    },
                )
            )
        elif method in {
            "notifications/initialized",
            "notifications/cancelled",
            "notifications/roots/list_changed",
        }:
            continue
        elif method == "ping" and not is_notification:
            emit(response(identifier, {}))
        elif method == "tools/list" and not is_notification:
            if params not in ({}, None) and (
                not isinstance(params, dict)
                or params.get("cursor") not in (None, "")
                or set(params) - {"cursor"}
            ):
                emit(error(identifier, -32602, "tools/list cursor is invalid"))
                continue
            emit(response(identifier, {"tools": TOOL_DEFINITIONS}))
        elif method == "tools/call" and not is_notification:
            if not isinstance(params, dict):
                emit(error(identifier, -32602, "params must be an object"))
                continue
            tool = params.get("name")
            if not isinstance(tool, str) or not tool or tool not in ALLOWED_TOOLS:
                emit(error(identifier, -32602, "tool is not exposed by the read-only proxy"))
                continue
            try:
                arguments = validate_arguments(
                    tool,
                    params.get("arguments", {}),
                    project_root,
                )
            except InvalidParams as exc:
                emit(error(identifier, -32602, str(exc)))
                continue
            emit(
                response(
                    identifier,
                    tool_result(
                        binary,
                        repo_root,
                        project_root,
                        cache_dir,
                        input_helper,
                        binary_sha256,
                        binary_identity,
                        tool,
                        arguments,
                    ),
                )
            )
        elif not is_notification:
            emit(error(identifier, -32601, "method not found"))


def main() -> None:
    arguments = parse_args()
    binary = Path(os.path.abspath(os.fspath(Path(arguments.binary).expanduser())))
    repo_root = Path(arguments.repo_root).expanduser().resolve()
    cache_raw = Path(os.path.abspath(os.fspath(Path(arguments.cache_dir).expanduser())))
    cache_dir = cache_raw.parent.resolve() / cache_raw.name
    project_raw = Path(os.path.abspath(os.fspath(Path(arguments.project_root).expanduser())))
    project_root = project_raw.parent.resolve() / project_raw.name
    input_helper = Path(os.path.abspath(os.fspath(Path(arguments.input_helper).expanduser())))
    binary_sha256 = arguments.binary_sha256
    if re.fullmatch(r"[0-9a-f]{64}", binary_sha256) is None:
        raise SystemExit("read-only proxy requires a pinned native binary digest")
    try:
        binary_mode = binary.lstat().st_mode
        helper_mode = input_helper.lstat().st_mode
        cache_mode = cache_dir.lstat().st_mode
        project_mode = project_root.lstat().st_mode
    except OSError as exc:
        raise SystemExit("read-only proxy requires complete controlled inputs") from exc
    if (
        stat.S_ISLNK(binary_mode)
        or not stat.S_ISREG(binary_mode)
        or not os.access(str(binary), os.X_OK)
    ):
        raise SystemExit("read-only proxy requires an executable native binary")
    binary_identity = (binary.lstat().st_dev, binary.lstat().st_ino)
    if not binary_integrity_ok(binary, binary_sha256, binary_identity):
        raise SystemExit("read-only proxy native binary differs from its repository pin")
    if stat.S_ISLNK(helper_mode) or not stat.S_ISREG(helper_mode):
        raise SystemExit("read-only proxy requires the tracked-input verifier")
    if not repo_root.is_dir() or not (repo_root / ".git").exists():
        raise SystemExit("read-only proxy requires the configured Git repository root")
    if (
        cache_dir != repo_root / ".codebase-memory"
        or stat.S_ISLNK(cache_mode)
        or not stat.S_ISDIR(cache_mode)
    ):
        raise SystemExit("cache directory is outside the repository boundary")
    os.umask(0o077)
    try:
        project_relative = project_root.relative_to(cache_dir / "inputs")
    except ValueError as exc:
        raise SystemExit("project root is outside the controlled input directory") from exc
    if (
        len(project_relative.parts) != 2
        or project_relative.parts[1] != "files"
        or not re.fullmatch(r"[0-9a-f]{64}", project_relative.parts[0])
        or stat.S_ISLNK(project_mode)
        or not stat.S_ISDIR(project_mode)
        or not (project_root.parent / "manifest.json").is_file()
    ):
        raise SystemExit("project root is not an authenticated input generation")
    serve(
        binary,
        repo_root,
        project_root,
        cache_dir,
        input_helper,
        binary_sha256,
        binary_identity,
    )


if __name__ == "__main__":
    main()
