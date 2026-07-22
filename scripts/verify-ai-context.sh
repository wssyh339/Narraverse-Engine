#!/usr/bin/env bash
set -euo pipefail

script_dir=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
readonly script_dir
repo_root=$(CDPATH= cd -- "${script_dir}/.." && pwd -P)
readonly repo_root

mode=${1:---full}
[[ $# -le 1 ]] || {
  printf 'Usage: scripts/verify-ai-context.sh [--static|--full]\n' >&2
  exit 2
}
case "${mode}" in
  --static|--full) ;;
  *)
    printf 'Usage: scripts/verify-ai-context.sh [--static|--full]\n' >&2
    exit 2
    ;;
esac

if command -v python3 >/dev/null 2>&1; then
  python_bin=python3
elif command -v python >/dev/null 2>&1; then
  python_bin=python
else
  printf 'verify-ai-context: Python 3 is required\n' >&2
  exit 1
fi

"${python_bin}" "${repo_root}/scripts/verify-agents-guidance.py"

"${python_bin}" - "${repo_root}" <<'PY'
import json
import pathlib
import re
import sys

root = pathlib.Path(sys.argv[1])
expected_tools = {
    "search_graph",
    "query_graph",
    "trace_path",
    "get_code_snippet",
    "get_graph_schema",
    "get_architecture",
    "search_code",
    "index_status",
}
forbidden_tools = {
    "detect_changes",
    "index_repository",
    "list_projects",
    "delete_project",
    "manage_adr",
    "ingest_traces",
}

codex_text = (root / ".codex/config.toml").read_text(encoding="utf-8")
try:
    import tomllib
except ModuleNotFoundError:
    try:
        import tomli as tomllib
    except ModuleNotFoundError:
        tomllib = None

if tomllib is not None:
    codex = tomllib.loads(codex_text)
    server = codex["mcp_servers"]["codebase_memory"]
    tools = server.get("enabled_tools", [])
    command = server.get("command")
    args = server.get("args")
else:
    section_match = re.search(
        r"(?ms)^\[mcp_servers\.codebase_memory\]\s*(.*?)(?=^\[|\Z)", codex_text
    )
    if section_match is None:
        raise SystemExit("missing [mcp_servers.codebase_memory] TOML section")
    section = section_match.group(1)
    tools_match = re.search(r"(?ms)^enabled_tools\s*=\s*\[(.*?)\]", section)
    if tools_match is None:
        raise SystemExit("missing enabled_tools in Codex MCP config")
    tools = re.findall(r'"([A-Za-z0-9_]+)"', tools_match.group(1))
    command_match = re.search(r'(?m)^command\s*=\s*"([^"]+)"\s*$', section)
    args_match = re.search(r'(?m)^args\s*=\s*\[\s*"([^"]+)"\s*\]\s*$', section)
    command = command_match.group(1) if command_match else None
    args = [args_match.group(1)] if args_match else None

if set(tools) != expected_tools or len(tools) != len(expected_tools):
    raise SystemExit("Codex MCP enabled_tools does not exactly match the eight-tool allowlist")
if forbidden_tools.intersection(tools):
    raise SystemExit("Codex MCP exposes a forbidden tool")
if command != "./scripts/code-intel.sh" or args != ["mcp"]:
    raise SystemExit("Codex MCP must start through scripts/code-intel.sh mcp")

config = json.loads((root / "repomix.config.json").read_text(encoding="utf-8"))
if config.get("$schema") != "https://repomix.com/schemas/1.17.0/schema.json":
    raise SystemExit("Repomix schema is not pinned to 1.17.0")
if config.get("input", {}).get("processors") != []:
    raise SystemExit("Repomix input.processors must be an explicit empty array")
if config.get("include") != []:
    raise SystemExit("Repomix include must stay empty so stdin is the only positive selector")
if config.get("output", {}).get("filePath") != ".ai-context/repomix.xml":
    raise SystemExit("Repomix output must stay under .ai-context")
if config.get("output", {}).get("parsableStyle") is not True:
    raise SystemExit("Repomix parsableStyle must be enabled")
if config.get("ignore", {}).get("useGitignore") is not False:
    raise SystemExit("Repomix Git ignore discovery must be disabled for immutable inputs")
if config.get("ignore", {}).get("useDotIgnore") is not False:
    raise SystemExit("Repomix dot-ignore discovery must be disabled for immutable inputs")
if config.get("ignore", {}).get("useDefaultPatterns") is not False:
    raise SystemExit("Repomix default patterns must be disabled to preserve manifest completeness")
if config.get("output", {}).get("git", {}).get("includeDiffs") is not False:
    raise SystemExit("Repomix git diffs must be disabled")
if config.get("output", {}).get("git", {}).get("includeLogs") is not False:
    raise SystemExit("Repomix git logs must be disabled")
if config.get("output", {}).get("git", {}).get("sortByChanges") is not False:
    raise SystemExit("Repomix Git-history sorting must be disabled for immutable inputs")
if config.get("security", {}).get("enableSecurityCheck") is not True:
    raise SystemExit("Repomix security check must be enabled")

required_markers = {
    ".env",
    "data/",
    "backend/data/",
    "backend/artifacts/",
    "backups/",
    "exports/",
    "output/",
    "outputs/",
    "logs/",
    ".logs/",
    "test-artifacts/",
    "frontend/node_modules/",
    "frontend/dist/",
    ".git/",
    ".codebase-memory/",
    ".ai-context/",
    "docs/test-reports/",
    "docs/archive/",
    "docs/superpowers/",
    "*.pdf",
}
effective_ignore_rules = {}
for ignore_name in (".cbmignore", ".repomixignore"):
    text = (root / ignore_name).read_text(encoding="utf-8")
    rules = [line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")]
    negated = [line for line in rules if line.startswith("!")]
    if negated:
        raise SystemExit(f"{ignore_name} contains forbidden negation rules: {negated}")
    effective_ignore_rules[ignore_name] = rules
    missing = sorted(marker for marker in required_markers if marker not in text)
    if missing:
        raise SystemExit(f"{ignore_name} is missing required exclusions: {missing}")
if effective_ignore_rules[".cbmignore"] != effective_ignore_rules[".repomixignore"]:
    raise SystemExit(".cbmignore and .repomixignore effective rules have drifted")

wrapper = (root / "scripts/code-intel.sh").read_text(encoding="utf-8")
proxy_path = root / "scripts/code-intel-mcp-proxy.py"
input_helper_path = root / "scripts/ai-context-inputs.py"
profile_path = root / "scripts/ai-context-profiles.json"
evaluation_path = root / "scripts/ai-context-eval.json"
graph_evaluator_path = root / "scripts/evaluate-code-graph.py"
bounded_runner_path = root / "scripts/run-bounded-ai-tool.py"
if not proxy_path.is_file():
    raise SystemExit("missing server-side read-only MCP proxy")
if not input_helper_path.is_file():
    raise SystemExit("missing tracked-input manifest helper")
if not profile_path.is_file() or not evaluation_path.is_file() or not graph_evaluator_path.is_file():
    raise SystemExit("missing AI context profiles or offline evaluation cases")
if not bounded_runner_path.is_file():
    raise SystemExit("missing bounded AI tool runner")
proxy = proxy_path.read_text(encoding="utf-8")
input_helper = input_helper_path.read_text(encoding="utf-8")
if 'CBM_VERSION="0.9.0"' not in wrapper:
    raise SystemExit("codebase-memory-mcp version is not pinned to 0.9.0")
if "auto_index false" not in wrapper or "auto_watch false" not in wrapper:
    raise SystemExit("automatic indexing and watcher must both be disabled")
if not re.search(r"[0-9a-f]{64}", wrapper):
    raise SystemExit("codebase-memory-mcp archive checksums are missing")
if "code-intel-mcp-proxy.py" not in wrapper:
    raise SystemExit("MCP entry point must execute the server-side read-only proxy")
if "prepare-shadow" not in wrapper or "current-shadow" not in wrapper:
    raise SystemExit("code graph wrapper must use tracked input generations")
if "--project-root" not in wrapper or "--project-root" not in proxy:
    raise SystemExit("read-only proxy must bind native calls to the active generation")
if "--binary-sha256" not in wrapper or "--binary-sha256" not in proxy:
    raise SystemExit("native code graph calls must carry a repository-pinned binary digest")
if '"name": "detect_changes"' in proxy:
    raise SystemExit("read-only MCP proxy must not publish detect_changes")
if "membership_source" not in input_helper or "current_worktree" not in input_helper:
    raise SystemExit("tracked membership/current-worktree semantics are not recorded")
if "copy_repository_file" not in input_helper or "os.link(" in input_helper:
    raise SystemExit("code graph inputs must be independent copies, never hard links")
if "validate_graph_paths" not in input_helper or "validate_snapshot" not in input_helper:
    raise SystemExit("manifest output validation is missing")
if "publish_context_bundle" not in input_helper or "snapshot_sha256" not in input_helper:
    raise SystemExit("content-authenticated atomic snapshot publication is missing")
for marker in (
    "CONTEXT_PUBLICATION_LOCK",
    "acquire_context_publication_lock",
    "release_context_publication_lock",
    ".owner.pending.",
):
    if marker not in input_helper:
        raise SystemExit(f"crash-recoverable serialized publication is missing: {marker}")
build_wrapper = (root / "scripts/build-ai-context.sh").read_text(encoding="utf-8")
for forbidden in ("npm exec", "npm view", "npx repomix", "@latest"):
    if forbidden in build_wrapper:
        raise SystemExit(f"Repomix build uses forbidden floating resolution: {forbidden}")
if "materialize-snapshot-input" not in build_wrapper or "ci --ignore-scripts" not in build_wrapper:
    raise SystemExit("Repomix build must use immutable inputs and its locked closure")
for marker in (
    "run-bounded-ai-tool.py",
    "--clear-environment",
    "--watch-file",
    "copied_config_path",
    "publish-context-bundle",
    "snapshot_sha256",
):
    if marker not in build_wrapper:
        raise SystemExit(f"Repomix bounded publication contract is missing: {marker}")

profiles = json.loads(profile_path.read_text(encoding="utf-8"))
if profiles.get("$schema") != "narraverse.ai-context-profiles.v1":
    raise SystemExit("AI context profile schema is invalid")
if profiles.get("default") != "full":
    raise SystemExit("full must remain the default AI context profile")
if set(profiles.get("profiles", {})) != {"full", "backend", "frontend", "tooling"}:
    raise SystemExit("AI context profile set has drifted")

root_guidance = (root / "AGENTS.md").read_text(encoding="utf-8")
if (
    "DeepWiki Open 仍明确为“暂不启用”" not in root_guidance
    or "不得克隆、安装、运行或生成 Wiki 缓存" not in root_guidance
):
    raise SystemExit("DeepWiki must remain explicitly disabled")

print("Static AI context configuration: OK")
PY

"${python_bin}" "${repo_root}/scripts/verify-ai-tool-supply-chain.py" >/dev/null
printf 'Pinned AI tool supply chain: OK\n'

if ! "${python_bin}" -m unittest discover \
  -s "${repo_root}/scripts/tests" \
  -p 'test_*.py' >/dev/null 2>&1; then
  "${python_bin}" -m unittest discover \
    -s "${repo_root}/scripts/tests" \
    -p 'test_*.py' -v
  exit 1
fi
printf 'Tracked-input and read-only MCP contracts: OK\n'

if ! "${python_bin}" "${repo_root}/scripts/evaluate-ai-context.py" >/dev/null 2>&1; then
  "${python_bin}" "${repo_root}/scripts/evaluate-ai-context.py"
  exit 1
fi
printf 'Offline AI context profile evaluation: OK\n'

for generated_path in .codebase-memory/.verify-ignore .ai-context/.verify-ignore; do
  git -C "${repo_root}" check-ignore --quiet --no-index -- "${generated_path}" || {
    printf 'verify-ai-context: %s is not ignored by Git\n' "${generated_path}" >&2
    exit 1
  }
done
printf 'Generated data ignore rules: OK\n'

for sensitive_candidate in \
  '.env.local' \
  'backups/.verify-ignore' \
  'exports/.verify-ignore' \
  'local.verify.db' \
  'local.verify.sqlite3'
do
  git -C "${repo_root}" check-ignore --quiet --no-index -- "${sensitive_candidate}" || {
    printf 'verify-ai-context: sensitive local path is not ignored by Git: %s\n' \
      "${sensitive_candidate}" >&2
    exit 1
  }
done
if git -C "${repo_root}" check-ignore --quiet --no-index -- '.env.example'; then
  printf 'verify-ai-context: the versioned .env.example template must remain visible to Git\n' >&2
  exit 1
fi
printf 'Sensitive local data ignore rules: OK\n'

for generated_dir in .codebase-memory .ai-context; do
  if [[ -n "$(git -C "${repo_root}" ls-files -- "${generated_dir}")" ]]; then
    printf 'verify-ai-context: %s contains tracked files\n' "${generated_dir}" >&2
    exit 1
  fi
done
printf 'Generated data tracking boundary: OK\n'

if [[ "${mode}" == "--static" ]]; then
  exit 0
fi

if ! "${repo_root}/scripts/build-ai-context.sh" >/dev/null 2>&1; then
  "${repo_root}/scripts/build-ai-context.sh"
  exit 1
fi
if ! "${repo_root}/scripts/code-intel.sh" rebuild >/dev/null 2>&1; then
  "${repo_root}/scripts/code-intel.sh" rebuild
  exit 1
fi
printf 'Fresh tracked-only snapshot and code graph rebuild: OK\n'

"${repo_root}/scripts/code-intel.sh" status >/dev/null
"${repo_root}/scripts/code-intel.sh" query get_graph_schema '{}' >/dev/null
"${repo_root}/scripts/code-intel.sh" query get_architecture '{}' >/dev/null
printf 'Pinned code graph and baseline read-only queries: OK\n'

if ! "${python_bin}" "${repo_root}/scripts/evaluate-code-graph.py" \
    --repo-root "${repo_root}" >/dev/null 2>&1; then
  "${python_bin}" "${repo_root}/scripts/evaluate-code-graph.py" \
    --repo-root "${repo_root}"
  exit 1
fi
printf 'Real code graph retrieval evaluation (9-scenario hit@10): OK\n'

"${python_bin}" - "${repo_root}" <<'PY'
import json
import pathlib
import subprocess
import sys

root = pathlib.Path(sys.argv[1])
messages = [
    {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "narraverse-verifier", "version": "1"},
        },
    },
    {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
    {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {"name": "index_status", "arguments": {}},
    },
    {
        "jsonrpc": "2.0",
        "id": 4,
        "method": "tools/call",
        "params": {"name": "detect_changes", "arguments": {}},
    },
    {
        "jsonrpc": "2.0",
        "id": 5,
        "method": "tools/call",
        "params": {
            "name": "query_graph",
            "arguments": {"query": "MATCH (n) DELETE n RETURN n"},
        },
    },
]
completed = subprocess.run(
    [str(root / "scripts/code-intel.sh"), "mcp"],
    input="".join(
        json.dumps(message, separators=(",", ":")) + "\n"
        for message in messages
    ),
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    encoding="utf-8",
    timeout=20,
    check=True,
)
responses = {}
for line in completed.stdout.splitlines():
    item = json.loads(line)
    if "id" in item:
        responses[item["id"]] = item
expected = {
    "search_graph",
    "query_graph",
    "trace_path",
    "get_code_snippet",
    "get_graph_schema",
    "get_architecture",
    "search_code",
    "index_status",
}
listed = responses[2]["result"]
if {tool["name"] for tool in listed["tools"]} != expected:
    raise SystemExit("server-side MCP proxy did not expose the exact eight-tool set")
if "nextCursor" in listed:
    raise SystemExit("server-side MCP proxy unexpectedly paginated its fixed tool set")
if responses[3]["result"].get("isError") is not False:
    raise SystemExit("server-side MCP proxy could not call index_status")
for identifier in (4, 5):
    if responses[identifier].get("error", {}).get("code") != -32602:
        raise SystemExit("server-side MCP proxy did not reject a forbidden call")
print("Server-side read-only MCP handshake: OK")
PY

for forbidden_graph_path in \
  '.env' \
  'data/' \
  'backend/data/' \
  'backend/artifacts/' \
  'backups/' \
  'exports/' \
  'output/' \
  'outputs/' \
  'logs/' \
  '.logs/' \
  'test-artifacts/' \
  'frontend/node_modules/' \
  'frontend/dist/' \
  '.git/' \
  '.codebase-memory/' \
  '.ai-context/' \
  'docs/archive/' \
  'docs/superpowers/' \
  'docs/test-reports/'
do
  graph_result=$(
    "${repo_root}/scripts/code-intel.sh" query query_graph \
      "{\"query\":\"MATCH (f:File) WHERE f.file_path CONTAINS \\\"${forbidden_graph_path}\\\" RETURN f.file_path LIMIT 1\"}"
  )
  graph_total=$(printf '%s' "${graph_result}" | "${python_bin}" -c \
    'import json, sys; print(int(json.load(sys.stdin).get("total", 0)))')
  if (( graph_total != 0 )); then
    printf 'verify-ai-context: sensitive path entered the code graph: %s\n' \
      "${forbidden_graph_path}" >&2
    exit 1
  fi
done
printf 'Code graph sensitive-path exclusions: OK\n'

graph_manifest=$("${python_bin}" "${repo_root}/scripts/ai-context-inputs.py" \
  current-manifest --cache-dir "${repo_root}/.codebase-memory")
graph_manifest_count=$("${python_bin}" -c \
  'import json,sys; print(len(json.load(open(sys.argv[1],encoding="utf-8"))["files"]))' \
  "${graph_manifest}")
printf 'Code graph manifest subset enforced by fresh rebuild: OK (%s approved files)\n' \
  "${graph_manifest_count}"

active_bundle_id=$("${python_bin}" -c \
  'import json,re,sys; value=json.load(open(sys.argv[1],encoding="utf-8")).get("bundle_id"); print(value) if isinstance(value,str) and re.fullmatch(r"[0-9a-f]{64}",value) else sys.exit(1)' \
  "${repo_root}/.ai-context/current.json") || {
  printf 'verify-ai-context: active AI context pointer is invalid\n' >&2
  exit 1
}
snapshot="${repo_root}/.ai-context/snapshots/${active_bundle_id}/repomix.xml"
snapshot_manifest="${repo_root}/.ai-context/snapshots/${active_bundle_id}/manifest.json"
[[ -f "${snapshot}" ]] || {
  printf 'verify-ai-context: missing %s; run scripts/build-ai-context.sh first\n' "${snapshot}" >&2
  exit 1
}
snapshot_count=$("${python_bin}" "${repo_root}/scripts/ai-context-inputs.py" \
  validate-snapshot \
  --manifest "${snapshot_manifest}" \
  --snapshot "${snapshot}")
printf 'Repomix manifest equality: OK (%s files)\n' "${snapshot_count}"

"${python_bin}" - "${snapshot}" <<'PY'
import pathlib
import re
import sys

path = pathlib.Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
packed_paths = re.findall(r'<file\s+path="([^"]+)"', text)
if not packed_paths:
    raise SystemExit("Repomix snapshot contains no recognizable file entries")

forbidden_prefixes = (
    ".git/",
    ".codebase-memory/",
    ".ai-context/",
    "data/",
    "backend/data/",
    "backend/artifacts/",
    "backups/",
    "exports/",
    "output/",
    "outputs/",
    "logs/",
    ".logs/",
    "test-artifacts/",
    "frontend/node_modules/",
    "frontend/dist/",
    "docs/archive/",
    "docs/superpowers/",
    "docs/test-reports/",
)
forbidden_names = {".env"}
leaks = [
    item
    for item in packed_paths
    if item in forbidden_names
    or item.startswith(forbidden_prefixes)
    or pathlib.PurePosixPath(item).name.startswith(".env.")
    or pathlib.PurePosixPath(item).suffix
    in {
        ".db",
        ".sqlite",
        ".sqlite3",
        ".pem",
        ".key",
        ".p12",
        ".pfx",
        ".backup",
        ".bak",
        ".epub",
        ".docx",
        ".pdf",
        ".zip",
        ".tar",
        ".tgz",
        ".gz",
        ".7z",
    }
]
if leaks:
    raise SystemExit(f"sensitive paths entered the Repomix snapshot: {leaks[:10]}")

secret_patterns = {
    "OpenAI-like API key": r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b",
    "GitHub token": r"\b(?:github_pat_[A-Za-z0-9_]{20,}|gh[pousr]_[A-Za-z0-9]{36,})\b",
    "AWS access key": r"\bAKIA[0-9A-Z]{16}\b",
    "private-key header": r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
}
secret_hits = [name for name, pattern in secret_patterns.items() if re.search(pattern, text)]
if secret_hits:
    raise SystemExit(f"possible secrets entered the Repomix snapshot: {secret_hits}")

print(f"Repomix exclusions: OK ({len(packed_paths)} files, {path.stat().st_size} bytes)")
PY

"${python_bin}" - "${repo_root}" <<'PY'
import json
import hashlib
import pathlib
import re
import stat
import sys

root = pathlib.Path(sys.argv[1]).resolve()
context = root / ".ai-context"
context_pointer = json.loads((context / "current.json").read_text(encoding="utf-8"))
bundle_id = context_pointer.get("bundle_id")
if not isinstance(bundle_id, str) or re.fullmatch(r"[0-9a-f]{64}", bundle_id) is None:
    raise SystemExit("AI context pointer has an invalid bundle id")
bundle = context / "snapshots" / bundle_id
provenance = json.loads((bundle / "provenance.json").read_text(encoding="utf-8"))
lock_sha = hashlib.sha256(
    (root / "scripts/repomix-runtime/package-lock.json").read_bytes()
).hexdigest()
snapshot_sha = hashlib.sha256((bundle / "repomix.xml").read_bytes()).hexdigest()
config_sha = hashlib.sha256((root / "repomix.config.json").read_bytes()).hexdigest()
if (
    context_pointer.get("profile") != "full"
    or context_pointer.get("runtime_lock_sha256") != lock_sha
    or provenance.get("runtime_lock_sha256") != lock_sha
    or provenance.get("bundle_id") != bundle_id
    or provenance.get("repomix_version") != "1.17.0"
    or provenance.get("snapshot_sha256") != snapshot_sha
    or context_pointer.get("snapshot_sha256") != snapshot_sha
    or provenance.get("config_sha256") != config_sha
    or context_pointer.get("provenance") != f"snapshots/{bundle_id}/provenance.json"
):
    raise SystemExit("AI context pointer/provenance differs from the pinned full build")

graph_cache = root / ".codebase-memory"
graph_pointer = json.loads((graph_cache / "current-input.json").read_text(encoding="utf-8"))
inventory_sha = graph_pointer.get("inventory_sha256")
if not isinstance(inventory_sha, str) or re.fullmatch(r"[0-9a-f]{64}", inventory_sha) is None:
    raise SystemExit("code graph pointer has an invalid inventory hash")
generation = graph_cache / "inputs" / inventory_sha
shadow = generation / "files"

expected_modes = {
    context: 0o700,
    context / "snapshots": 0o700,
    bundle: 0o700,
    bundle / "manifest.json": 0o600,
    bundle / "provenance.json": 0o600,
    bundle / "repomix.xml": 0o600,
    context / "current.json": 0o600,
    graph_cache: 0o700,
    graph_cache / "inputs": 0o700,
    generation: 0o700,
    generation / "manifest.json": 0o600,
    graph_cache / "current-input.json": 0o600,
}
for path, expected in expected_modes.items():
    if path.is_symlink():
        raise SystemExit(f"generated-data control path is a symlink: {path}")
    actual = stat.S_IMODE(path.stat().st_mode)
    if actual != expected:
        raise SystemExit(f"unsafe generated-data mode {oct(actual)} for {path}")
for directory in [shadow, *[item for item in shadow.rglob("*") if item.is_dir()]]:
    directory_mode = stat.S_IMODE(directory.stat().st_mode)
    if directory_mode != 0o500:
        raise SystemExit(f"shadow directory is not immutable owner-private: {directory}")

snapshot_bundles = [
    item
    for item in (context / "snapshots").iterdir()
    if item.is_dir() and not item.is_symlink() and re.fullmatch(r"[0-9a-f]{64}", item.name)
]
input_generations = [
    item
    for item in (graph_cache / "inputs").iterdir()
    if item.is_dir() and not item.is_symlink() and re.fullmatch(r"[0-9a-f]{64}", item.name)
]
if len(snapshot_bundles) > 2:
    raise SystemExit("snapshot retention exceeded two bundles")
if [item.name for item in input_generations] != [inventory_sha]:
    raise SystemExit("inactive code graph input generations were not cleaned")
for forbidden in (root / ".deepwiki", root / ".deepwiki-cache"):
    if forbidden.exists():
        raise SystemExit(f"DeepWiki remains disabled but generated data exists: {forbidden}")
print("Generated-data pointers, permissions, retention, and DeepWiki boundary: OK")
PY

printf 'AI context verification: OK\n'
