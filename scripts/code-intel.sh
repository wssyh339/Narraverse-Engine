#!/usr/bin/env bash
set -euo pipefail
umask 077

readonly CBM_VERSION="0.9.0"
readonly CBM_RELEASE_BASE="https://github.com/DeusData/codebase-memory-mcp/releases/download/v${CBM_VERSION}"
readonly CBM_LICENSE_SHA256="1f58f9911dc5e3bcb96de28bb28e7b6bb7eb323952d29569c5d7214a152146bb"
readonly CBM_NOTICES_SHA256="d02434a42fb7b5151cc3f7a3be4908136e8bbc12255f7ddc8c63c6923acfd611"

script_dir=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
readonly script_dir
repo_root=$(CDPATH= cd -- "${script_dir}/.." && pwd -P)
readonly repo_root
readonly cache_dir="${repo_root}/.codebase-memory"
readonly input_helper="${script_dir}/ai-context-inputs.py"
readonly input_ignore="${repo_root}/.cbmignore"

if [[ -n "${XDG_DATA_HOME:-}" ]]; then
  tool_data_home="${XDG_DATA_HOME}"
else
  : "${HOME:?HOME must be set when XDG_DATA_HOME is not set}"
  tool_data_home="${HOME}/.local/share"
fi
readonly install_dir="${tool_data_home}/narraverse/code-intel/codebase-memory-mcp/${CBM_VERSION}"
readonly install_parent="${tool_data_home}/narraverse/code-intel/codebase-memory-mcp"
readonly installed_binary="${install_dir}/codebase-memory-mcp"
readonly installed_files_manifest="${install_dir}/installed-files.sha256"
readonly native_runner="${script_dir}/code-intel-native.py"
readonly bounded_runner="${script_dir}/run-bounded-ai-tool.py"

readonly -a readonly_tools=(
  search_graph
  query_graph
  trace_path
  get_code_snippet
  get_graph_schema
  get_architecture
  search_code
  index_status
)

index_lock_token=""
runtime_lock_token=""
install_temp_dir=""
install_stage_dir=""

usage() {
  cat <<'EOF'
Usage:
  scripts/code-intel.sh install
  scripts/code-intel.sh index [--allow-untracked PATH]...
  scripts/code-intel.sh refresh [--allow-untracked PATH]...
  scripts/code-intel.sh rebuild [--allow-untracked PATH]...
  scripts/code-intel.sh status
  scripts/code-intel.sh mcp
  scripts/code-intel.sh query <read-only-tool> [JSON-object]
  scripts/code-intel.sh uninstall

Index creation and refresh are available only through the explicit index and
refresh/rebuild subcommands. Inputs default to committed or staged-added Git
paths with current-worktree content. Untracked files require exact-path flags.
The MCP and query entry points expose read-only tools.
EOF
}

fail() {
  printf 'code-intel: %s\n' "$*" >&2
  exit 1
}

acquire_index_lock() {
  local python_bin
  python_bin=$(find_python)
  index_lock_token=$("${python_bin}" "${input_helper}" acquire-lock \
    --repo-root "${repo_root}" \
    --cache-dir "${cache_dir}" \
    --kind index \
    --pid "$$") || fail "could not acquire the controlled code graph lock"
}

release_index_lock() {
  local python_bin
  [[ -n "${index_lock_token:-}" ]] || return 0
  python_bin=$(find_python)
  if ! "${python_bin}" "${input_helper}" release-lock \
    --repo-root "${repo_root}" \
    --cache-dir "${cache_dir}" \
    --kind index \
    --token "${index_lock_token}"; then
    printf 'code-intel: warning: could not safely release the controlled code graph lock\n' >&2
    return 1
  fi
  index_lock_token=""
}

release_runtime_lock() {
  local python_bin
  [[ -n "${runtime_lock_token:-}" ]] || return 0
  python_bin=$(find_python)
  if ! "${python_bin}" "${input_helper}" release-lock \
    --repo-root "${repo_root}" \
    --cache-dir "${cache_dir}" \
    --kind runtime \
    --token "${runtime_lock_token}"; then
    printf 'code-intel: warning: could not safely release the controlled runtime lock\n' >&2
    return 1
  fi
  runtime_lock_token=""
}

cleanup_install_artifacts() {
  local python_bin
  [[ -n "${install_temp_dir:-}" || -n "${install_stage_dir:-}" ]] || return 0
  python_bin=$(find_python)
  "${python_bin}" - "${install_temp_dir:-}" "${install_stage_dir:-}" \
    "${install_parent}" <<'PY'
import os
import pathlib
import shutil
import sys

temporary_value, staging_value, parent_value = sys.argv[1:]
if temporary_value:
    temporary = pathlib.Path(os.path.abspath(temporary_value))
    allowed_temp_parent = pathlib.Path(os.path.abspath(os.environ.get("TMPDIR", "/tmp")))
    if temporary.parent != allowed_temp_parent or not temporary.name.startswith("narraverse-code-intel."):
        raise SystemExit("refusing to clean an unsafe download directory")
    if os.path.lexists(str(temporary)):
        if temporary.is_symlink() or not temporary.is_dir():
            raise SystemExit("download cleanup target is unsafe")
        shutil.rmtree(temporary)
if staging_value:
    staging = pathlib.Path(os.path.abspath(staging_value))
    parent = pathlib.Path(os.path.abspath(parent_value))
    if staging.parent != parent or not staging.name.startswith(".install."):
        raise SystemExit("refusing to clean an unsafe install staging directory")
    if os.path.lexists(str(staging)):
        if staging.is_symlink() or not staging.is_dir():
            raise SystemExit("install staging cleanup target is unsafe")
        shutil.rmtree(staging)
PY
  install_temp_dir=""
  install_stage_dir=""
}

cleanup_controlled_state() {
  local status=0
  release_runtime_lock || status=1
  release_index_lock || status=1
  cleanup_install_artifacts || status=1
  return "${status}"
}

handle_signal() {
  local exit_code=$1
  trap - EXIT INT TERM
  cleanup_controlled_state || true
  exit "${exit_code}"
}

find_python() {
  if command -v python3 >/dev/null 2>&1; then
    printf '%s\n' python3
  elif command -v python >/dev/null 2>&1; then
    printf '%s\n' python
  else
    fail "Python 3 is required for safe JSON argument handling"
  fi
}

run_native() {
  local binary=$1 stdout_limit=$2 stderr_limit=$3 timeout_seconds=$4 python_bin
  local _asset _archive_sha expected_binary_sha
  shift 4
  python_bin=$(find_python)
  IFS=$'\t' read -r _asset _archive_sha expected_binary_sha < <(platform_asset)
  "${python_bin}" "${native_runner}" \
    --binary "${binary}" \
    --binary-sha256 "${expected_binary_sha}" \
    --repo-root "${repo_root}" \
    --cache-dir "${cache_dir}" \
    --stdout-limit "${stdout_limit}" \
    --stderr-limit "${stderr_limit}" \
    --timeout "${timeout_seconds}" \
    -- "$@"
}

sha256_file() {
  local target=$1
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum -- "${target}" | awk '{print $1}'
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 -- "${target}" | awk '{print $1}'
  else
    fail "sha256sum or shasum is required"
  fi
}

platform_asset() {
  local os arch
  os=$(uname -s)
  arch=$(uname -m)
  case "${os}/${arch}" in
    Darwin/arm64)
      printf '%s\t%s\t%s\n' \
        "codebase-memory-mcp-darwin-arm64.tar.gz" \
        "faa02f0404230c451a9812230394481948f80183801fa5bf67044b41c2f25ed4" \
        "d9fbdd7d8570a77b2fb32453e00bd52a02627281309cd56003a4eccfcfe878d6"
      ;;
    Darwin/x86_64)
      printf '%s\t%s\t%s\n' \
        "codebase-memory-mcp-darwin-amd64.tar.gz" \
        "6af3d02a27f589901fa763d3971089337bc8c9838bbed5d0cf543ca9f1a9e543" \
        "04ee3048810c19099502adc8bb83039423f02f2553d17677892a7f03b924e01f"
      ;;
    Linux/x86_64|Linux/amd64)
      printf '%s\t%s\t%s\n' \
        "codebase-memory-mcp-linux-amd64-portable.tar.gz" \
        "8459d5c9d1457f2c82de3de307ffc7641ecbba2dde893427be1e62eca8ef9b25" \
        "8d019ca9372e5e0d60650648f3740673db7f84d1e38fd14fa4b0e823ee7220dc"
      ;;
    Linux/aarch64|Linux/arm64)
      printf '%s\t%s\t%s\n' \
        "codebase-memory-mcp-linux-arm64-portable.tar.gz" \
        "b0a43fdaf534073c16707d72726b73b149d4c1212034b281ee8b7b2dac755107" \
        "5636efebea2afdcb4783014f8c8eb7d319c48b63e9ecdccbbf12911837a7cacd"
      ;;
    *)
      fail "unsupported platform ${os}/${arch}; use the documented manual install path"
      ;;
  esac
}

prepare_install_parent() {
  local create_mode=${1:-existing} python_bin
  python_bin=$(find_python)
  "${python_bin}" - "${tool_data_home}" "${create_mode}" <<'PY'
import os
import pathlib
import stat
import sys

base_value, create_mode = sys.argv[1:]
if create_mode not in {"create", "existing"}:
    raise SystemExit("invalid controlled install parent mode")
base = pathlib.Path(base_value).expanduser()
if create_mode == "create":
    base.mkdir(mode=0o700, parents=True, exist_ok=True)
try:
    base = base.resolve(strict=True)
except OSError as exc:
    raise SystemExit("controlled tool data directory is missing") from exc
base_stat = base.lstat()
owner = os.geteuid() if hasattr(os, "geteuid") else os.getuid()
if (
    stat.S_ISLNK(base_stat.st_mode)
    or not stat.S_ISDIR(base_stat.st_mode)
    or base_stat.st_uid != owner
    or stat.S_IMODE(base_stat.st_mode) & 0o022
):
    raise SystemExit("tool data directory ownership or mode is unsafe")
flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0)
if hasattr(os, "O_NOFOLLOW"):
    flags |= os.O_NOFOLLOW
descriptor = os.open(base, flags)
current = base
try:
    for name in ("narraverse", "code-intel", "codebase-memory-mcp"):
        try:
            entry = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
        except FileNotFoundError:
            if create_mode != "create":
                raise SystemExit("controlled install parent is missing")
            os.mkdir(name, 0o700, dir_fd=descriptor)
            entry = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
        if (
            not stat.S_ISDIR(entry.st_mode)
            or entry.st_uid != owner
            or stat.S_IMODE(entry.st_mode) & 0o022
        ):
            raise SystemExit("controlled install parent ownership or mode is unsafe")
        child = os.open(name, flags, dir_fd=descriptor)
        opened = os.fstat(child)
        if (opened.st_dev, opened.st_ino) != (entry.st_dev, entry.st_ino):
            os.close(child)
            raise SystemExit("controlled install parent changed while opening")
        os.fchmod(child, 0o700)
        os.close(descriptor)
        descriptor = child
        current = current / name
finally:
    os.close(descriptor)
print(current)
PY
}

cleanup_install_tombstones() {
  local controlled_parent=$1 python_bin
  python_bin=$(find_python)
  "${python_bin}" - "${controlled_parent}" "${CBM_VERSION}" <<'PY'
import os
import pathlib
import re
import stat
import sys

parent_value, version = sys.argv[1:]
parent = pathlib.Path(parent_value)
flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0)
if hasattr(os, "O_NOFOLLOW"):
    flags |= os.O_NOFOLLOW
pattern = re.compile(rf"\.removing\.{re.escape(version)}\.[0-9a-f]{{32}}")
expected = {
    "codebase-memory-mcp",
    "LICENSE",
    "THIRD_PARTY_NOTICES.md",
    "archive.sha256",
    "installed-files.sha256",
}
parent_descriptor = os.open(parent, flags)
try:
    for name in sorted(os.listdir(parent_descriptor)):
        if not pattern.fullmatch(name):
            continue
        tombstone_descriptor = os.open(name, flags, dir_fd=parent_descriptor)
        try:
            entries = set(os.listdir(tombstone_descriptor))
            if not entries.issubset(expected):
                raise SystemExit("install removal tombstone contains unexpected entries")
            for file_name in sorted(entries):
                item = os.stat(
                    file_name,
                    dir_fd=tombstone_descriptor,
                    follow_symlinks=False,
                )
                if not stat.S_ISREG(item.st_mode):
                    raise SystemExit("install removal tombstone contains an unsafe entry")
                os.unlink(file_name, dir_fd=tombstone_descriptor)
        finally:
            os.close(tombstone_descriptor)
        os.rmdir(name, dir_fd=parent_descriptor)
    os.fsync(parent_descriptor)
finally:
    os.close(parent_descriptor)
PY
}

verify_installed_files() {
  local target_dir=${1:-${install_dir}} target_manifest
  local asset archive_sha binary_sha python_bin
  target_manifest="${target_dir}/installed-files.sha256"
  [[ -d "${target_dir}" && ! -L "${target_dir}" ]] || \
    fail "controlled codebase-memory install is missing or unsafe; run scripts/code-intel.sh install"
  [[ -f "${target_manifest}" && ! -L "${target_manifest}" ]] || \
    fail "installed file manifest is missing or unsafe; reinstall codebase-memory-mcp"
  IFS=$'\t' read -r asset archive_sha binary_sha < <(platform_asset)
  python_bin=$(find_python)
  "${python_bin}" - \
    "${target_dir}" "${target_manifest}" \
    "${binary_sha}" "${CBM_LICENSE_SHA256}" "${CBM_NOTICES_SHA256}" \
    "${archive_sha}" "${asset}" <<'PY' || \
    fail "controlled installed files failed repository-pin verification"
import hashlib
import os
import pathlib
import stat
import sys

(
    install_dir,
    manifest_path,
    binary_sha,
    license_sha,
    notices_sha,
    archive_sha,
    asset,
) = sys.argv[1:]
install = pathlib.Path(install_dir)
manifest = pathlib.Path(manifest_path)
owner = os.geteuid() if hasattr(os, "geteuid") else os.getuid()
install_stat = install.lstat()
if (
    stat.S_ISLNK(install_stat.st_mode)
    or not stat.S_ISDIR(install_stat.st_mode)
    or install_stat.st_uid != owner
    or stat.S_IMODE(install_stat.st_mode) & 0o022
):
    raise SystemExit("controlled install directory ownership or mode is unsafe")
expected = {
    "codebase-memory-mcp": binary_sha,
    "LICENSE": license_sha,
    "THIRD_PARTY_NOTICES.md": notices_sha,
}
expected_names = set(expected) | {"archive.sha256", "installed-files.sha256"}
if {item.name for item in install.iterdir()} != expected_names:
    raise SystemExit("controlled install contains an unexpected file set")
actual_lines = []
for name, digest in expected.items():
    path = install / name
    path_stat = path.lstat()
    if (
        stat.S_ISLNK(path_stat.st_mode)
        or not stat.S_ISREG(path_stat.st_mode)
        or path_stat.st_uid != owner
        or stat.S_IMODE(path_stat.st_mode) & 0o022
    ):
        raise SystemExit(f"installed file ownership or mode is unsafe: {name}")
    if name == "codebase-memory-mcp" and not stat.S_IMODE(path_stat.st_mode) & 0o100:
        raise SystemExit("installed binary is not owner-executable")
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != digest:
        raise SystemExit(f"installed file differs from repository pin: {name}")
    actual_lines.append(f"{digest}  {name}")
manifest_stat = manifest.lstat()
if (
    stat.S_ISLNK(manifest_stat.st_mode)
    or not stat.S_ISREG(manifest_stat.st_mode)
    or manifest_stat.st_uid != owner
    or stat.S_IMODE(manifest_stat.st_mode) & 0o077
):
    raise SystemExit("installed file manifest ownership or mode is unsafe")
if manifest.read_text(encoding="utf-8").splitlines() != actual_lines:
    raise SystemExit("installed file manifest differs from repository pins")
archive = install / "archive.sha256"
archive_stat = archive.lstat()
if (
    stat.S_ISLNK(archive_stat.st_mode)
    or not stat.S_ISREG(archive_stat.st_mode)
    or archive_stat.st_uid != owner
    or stat.S_IMODE(archive_stat.st_mode) & 0o022
):
    raise SystemExit("installed archive record ownership or mode is unsafe")
if archive.read_text(encoding="utf-8") != f"{archive_sha}  {asset}\n":
    raise SystemExit("installed archive record differs from repository pins")
PY
}

resolve_binary() {
  local candidate version_output
  candidate=${installed_binary}
  [[ -x "${candidate}" && ! -L "${candidate}" ]] || \
    fail "codebase-memory-mcp ${CBM_VERSION} is not installed; run scripts/code-intel.sh install"
  verify_installed_files
  version_output=$(run_native "${candidate}" 4096 4096 15 --version </dev/null 2>&1) || \
    fail "could not read codebase-memory-mcp version"
  [[ "${version_output}" == "codebase-memory-mcp ${CBM_VERSION}" ]] ||
    fail "expected codebase-memory-mcp ${CBM_VERSION}, got: ${version_output}"
  printf '%s\n' "${candidate}"
}

configure_runtime() {
  local binary=$1
  local python_bin config_exit_code=0 watch_exit_code=0
  [[ -d "${cache_dir}" && ! -L "${cache_dir}" ]] || \
    fail "code graph cache layout is unsafe"
  python_bin=$(find_python)
  runtime_lock_token=$("${python_bin}" "${input_helper}" acquire-lock \
    --repo-root "${repo_root}" \
    --cache-dir "${cache_dir}" \
    --kind runtime \
    --pid "$$") || fail "could not acquire the controlled runtime lock"

  if run_native "${binary}" 65536 65536 30 \
    config set auto_index false </dev/null >/dev/null; then
    :
  else
    config_exit_code=$?
  fi
  if run_native "${binary}" 65536 65536 30 \
    config set auto_watch false </dev/null >/dev/null; then
    :
  else
    watch_exit_code=$?
    if (( config_exit_code == 0 )); then
      config_exit_code=${watch_exit_code}
    fi
  fi

  release_runtime_lock || fail "could not safely release the controlled runtime lock"
  (( config_exit_code == 0 )) || fail "failed to persist safe runtime configuration"
}

repo_path_payload() {
  local project_root=$1 python_bin
  python_bin=$(find_python)
  "${python_bin}" -c \
    'import json, sys; print(json.dumps({"repo_path": sys.argv[1]}, ensure_ascii=False))' \
    "${project_root}"
}

query_payload() {
  local tool=$1 project_root=$2 raw_payload=$3 python_bin
  python_bin=$(find_python)
  "${python_bin}" "${script_dir}/code-intel-validate.py" \
    "${tool}" "${project_root}" "${raw_payload}"
}

is_readonly_tool() {
  local requested=$1 allowed
  for allowed in "${readonly_tools[@]}"; do
    [[ "${requested}" == "${allowed}" ]] && return 0
  done
  return 1
}

cleanup_inactive_projects() {
  local binary=$1 active_project=$2 python_bin projects_file stale_file stale_project payload
  local cleanup_failed=false
  python_bin=$(find_python)
  projects_file=$(mktemp "${cache_dir}/.projects.XXXXXX")
  stale_file=$(mktemp "${cache_dir}/.stale-projects.XXXXXX")
  chmod 0600 "${projects_file}" "${stale_file}"
  if ! printf '{}\n' | run_native "${binary}" 4194304 262144 60 \
      cli list_projects >"${projects_file}"; then
    unlink "${projects_file}"
    unlink "${stale_file}"
    printf 'code-intel: warning: could not list stale generated projects\n' >&2
    return 0
  fi
  "${python_bin}" - \
    "${projects_file}" "${repo_root}" "${cache_dir}" "${active_project}" \
    >"${stale_file}" <<'PY'
import json
import pathlib
import re
import sys

result_path, repo_value, cache_value, active_value = sys.argv[1:]
payload = json.loads(pathlib.Path(result_path).read_text(encoding="utf-8"))
repo = pathlib.Path(repo_value).resolve()
inputs = pathlib.Path(cache_value).resolve() / "inputs"
active = pathlib.Path(active_value).resolve()
for item in payload.get("projects", []):
    raw = item.get("root_path")
    if not isinstance(raw, str) or any(character in raw for character in "\r\n\0"):
        continue
    candidate = pathlib.Path(raw).resolve()
    stale = candidate == repo
    if not stale:
        try:
            relative = candidate.relative_to(inputs)
        except ValueError:
            continue
        stale = (
            len(relative.parts) == 2
            and re.fullmatch(r"[0-9a-f]{64}", relative.parts[0]) is not None
            and relative.parts[1] == "files"
            and candidate != active
        )
    if stale:
        print(candidate)
PY
  while IFS= read -r stale_project; do
    [[ -n "${stale_project}" ]] || continue
    payload=$("${python_bin}" -c \
      'import json,sys; print(json.dumps({"project":sys.argv[1]}, ensure_ascii=False))' \
      "${stale_project}")
    if ! printf '%s\n' "${payload}" | run_native \
      "${binary}" 1048576 262144 60 cli delete_project >/dev/null; then
      cleanup_failed=true
      printf 'code-intel: warning: could not delete stale project %s\n' \
        "${stale_project}" >&2
    fi
  done <"${stale_file}"
  unlink "${projects_file}"
  unlink "${stale_file}"
  if [[ "${cleanup_failed}" == false ]]; then
    "${python_bin}" "${input_helper}" cleanup-generations \
      --cache-dir "${cache_dir}" >/dev/null || \
      printf 'code-intel: warning: could not clean inactive input generations\n' >&2
  fi
}

install_tool() {
  command -v curl >/dev/null 2>&1 || fail "curl is required for the pinned HTTPS download"
  command -v tar >/dev/null 2>&1 || fail "tar is required to extract the verified release"
  [[ -f "${bounded_runner}" ]] || fail "bounded AI tool runner is missing"

  local asset expected expected_binary actual archive_path extract_dir version_output
  local controlled_parent controlled_target runtime_home python_bin curl_bin
  local binary_hash license_hash notices_hash
  IFS=$'\t' read -r asset expected expected_binary < <(platform_asset)
  python_bin=$(find_python)
  curl_bin=$(command -v curl)
  controlled_parent=$(prepare_install_parent create) || \
    fail "could not prepare the controlled install parent"
  cleanup_install_tombstones "${controlled_parent}" || \
    fail "could not recover an interrupted prior uninstall"
  controlled_target="${controlled_parent}/${CBM_VERSION}"
  if [[ -e "${controlled_target}" || -L "${controlled_target}" ]]; then
    verify_installed_files "${controlled_target}"
    printf 'codebase-memory-mcp %s is already installed at %s\n' \
      "${CBM_VERSION}" "${controlled_target}"
    return 0
  fi

  install_temp_dir=$(mktemp -d "${TMPDIR:-/tmp}/narraverse-code-intel.XXXXXX")
  archive_path="${install_temp_dir}/${asset}"
  extract_dir="${install_temp_dir}/extract"
  runtime_home="${install_temp_dir}/runtime-home"
  mkdir -p -- "${extract_dir}"
  mkdir -m 0700 -- "${runtime_home}"

  "${python_bin}" "${bounded_runner}" \
    --cwd "${install_temp_dir}" --timeout 300 \
    --stdout-limit 4096 --stderr-limit 262144 --clear-environment \
    --watch-file "${archive_path}=134217728" \
    --env "PATH=$(dirname -- "${curl_bin}"):/usr/bin:/bin" \
    --env "HOME=${runtime_home}" --env LC_ALL=C --env TZ=UTC -- \
    "${curl_bin}" --disable --proto '=https' --tlsv1.2 \
    --connect-timeout 15 --max-time 300 --max-filesize 134217728 \
    --speed-limit 1024 --speed-time 30 \
    --fail --silent --show-error --location \
    --output "${archive_path}" "${CBM_RELEASE_BASE}/${asset}" </dev/null || \
    fail "pinned release download failed safely"
  actual=$(sha256_file "${archive_path}")
  [[ "${actual}" == "${expected}" ]] || fail "SHA-256 mismatch for ${asset}"

  tar -xzf "${archive_path}" -C "${extract_dir}" \
    codebase-memory-mcp LICENSE THIRD_PARTY_NOTICES.md
  [[ -f "${extract_dir}/LICENSE" && -f "${extract_dir}/THIRD_PARTY_NOTICES.md" ]] ||
    fail "release archive did not contain required license notices"
  [[ "$(sha256_file "${extract_dir}/codebase-memory-mcp")" == "${expected_binary}" ]] || \
    fail "extracted binary differs from the reviewed platform pin"
  [[ "$(sha256_file "${extract_dir}/LICENSE")" == "${CBM_LICENSE_SHA256}" ]] || \
    fail "extracted LICENSE differs from the reviewed pin"
  [[ "$(sha256_file "${extract_dir}/THIRD_PARTY_NOTICES.md")" == "${CBM_NOTICES_SHA256}" ]] || \
    fail "extracted third-party notices differ from the reviewed pin"

  install_stage_dir=$(mktemp -d "${controlled_parent}/.install.${CBM_VERSION}.XXXXXX")
  chmod 0700 "${install_stage_dir}"
  install -m 0700 "${extract_dir}/codebase-memory-mcp" \
    "${install_stage_dir}/codebase-memory-mcp"
  install -m 0600 "${extract_dir}/LICENSE" "${install_stage_dir}/LICENSE"
  install -m 0600 "${extract_dir}/THIRD_PARTY_NOTICES.md" \
    "${install_stage_dir}/THIRD_PARTY_NOTICES.md"
  printf '%s  %s\n' "${expected}" "${asset}" >"${install_stage_dir}/archive.sha256"
  chmod 0600 "${install_stage_dir}/archive.sha256"

  binary_hash=$(sha256_file "${install_stage_dir}/codebase-memory-mcp")
  license_hash=$(sha256_file "${install_stage_dir}/LICENSE")
  notices_hash=$(sha256_file "${install_stage_dir}/THIRD_PARTY_NOTICES.md")
  {
    printf '%s  codebase-memory-mcp\n' "${binary_hash}"
    printf '%s  LICENSE\n' "${license_hash}"
    printf '%s  THIRD_PARTY_NOTICES.md\n' "${notices_hash}"
  } >"${install_stage_dir}/installed-files.sha256"
  chmod 0600 "${install_stage_dir}/installed-files.sha256"

  verify_installed_files "${install_stage_dir}"
  version_output=$("${python_bin}" "${bounded_runner}" \
    --cwd "${install_stage_dir}" --timeout 15 \
    --stdout-limit 4096 --stderr-limit 4096 --clear-environment \
    --env PATH=/usr/bin:/bin --env "HOME=${runtime_home}" --env LC_ALL=C --env TZ=UTC \
    -- "${install_stage_dir}/codebase-memory-mcp" --version </dev/null) || \
    fail "installed binary failed its bounded version check"
  [[ "${version_output}" == "codebase-memory-mcp ${CBM_VERSION}" ]] ||
    fail "installed binary failed its version check"
  verify_installed_files "${install_stage_dir}"

  "${python_bin}" - "${controlled_parent}" "${install_stage_dir}" \
    "${CBM_VERSION}" <<'PY' || fail "could not atomically publish the verified install"
import os
import pathlib
import stat
import sys

parent_value, staging_value, version = sys.argv[1:]
parent = pathlib.Path(parent_value)
staging = pathlib.Path(staging_value)
if staging.parent != parent or not staging.name.startswith(f".install.{version}."):
    raise SystemExit("install staging path is outside the controlled parent")
flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0)
if hasattr(os, "O_NOFOLLOW"):
    flags |= os.O_NOFOLLOW
parent_descriptor = os.open(parent, flags)
try:
    parent_stat = os.fstat(parent_descriptor)
    lexical_stat = parent.lstat()
    if (parent_stat.st_dev, parent_stat.st_ino) != (lexical_stat.st_dev, lexical_stat.st_ino):
        raise SystemExit("controlled install parent changed before publication")
    staging_stat = os.stat(staging.name, dir_fd=parent_descriptor, follow_symlinks=False)
    if not stat.S_ISDIR(staging_stat.st_mode):
        raise SystemExit("install staging entry is unsafe")
    try:
        os.stat(version, dir_fd=parent_descriptor, follow_symlinks=False)
    except FileNotFoundError:
        pass
    else:
        raise SystemExit("controlled install destination already exists")
    os.rename(
        staging.name,
        version,
        src_dir_fd=parent_descriptor,
        dst_dir_fd=parent_descriptor,
    )
    os.fsync(parent_descriptor)
finally:
    os.close(parent_descriptor)
PY
  install_stage_dir=""
  verify_installed_files "${controlled_target}"
  cleanup_install_artifacts || fail "could not clean verified install artifacts"
  printf 'Installed codebase-memory-mcp %s at %s\n' \
    "${CBM_VERSION}" "${controlled_target}/codebase-memory-mcp"
}

uninstall_tool() {
  local controlled_parent controlled_target python_bin
  if [[ ! -e "${install_parent}" && ! -L "${install_parent}" ]]; then
    printf 'codebase-memory-mcp %s is not installed at %s\n' "${CBM_VERSION}" "${install_dir}"
    return 0
  fi
  python_bin=$(find_python)
  controlled_parent=$(prepare_install_parent existing) || \
    fail "controlled install parent is missing or unsafe"
  cleanup_install_tombstones "${controlled_parent}" || \
    fail "could not recover an interrupted prior uninstall"
  controlled_target="${controlled_parent}/${CBM_VERSION}"
  if [[ ! -e "${controlled_target}" && ! -L "${controlled_target}" ]]; then
    printf 'codebase-memory-mcp %s is not installed at %s\n' \
      "${CBM_VERSION}" "${controlled_target}"
    return 0
  fi
  verify_installed_files "${controlled_target}"
  "${python_bin}" - "${controlled_parent}" "${CBM_VERSION}" <<'PY' || \
    fail "could not safely remove the verified install"
import os
import pathlib
import secrets
import stat
import sys

parent_value, version = sys.argv[1:]
parent = pathlib.Path(parent_value)
flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0)
if hasattr(os, "O_NOFOLLOW"):
    flags |= os.O_NOFOLLOW
parent_descriptor = os.open(parent, flags)
try:
    entry = os.stat(version, dir_fd=parent_descriptor, follow_symlinks=False)
    if not stat.S_ISDIR(entry.st_mode):
        raise SystemExit("controlled install target is unsafe")
    target_descriptor = os.open(version, flags, dir_fd=parent_descriptor)
    tombstone = f".removing.{version}.{secrets.token_hex(16)}"
    try:
        opened = os.fstat(target_descriptor)
        if (opened.st_dev, opened.st_ino) != (entry.st_dev, entry.st_ino):
            raise SystemExit("controlled install target changed while opening")
        expected = {
            "codebase-memory-mcp",
            "LICENSE",
            "THIRD_PARTY_NOTICES.md",
            "archive.sha256",
            "installed-files.sha256",
        }
        if set(os.listdir(target_descriptor)) != expected:
            raise SystemExit("controlled install target contains unexpected entries")
        current = os.stat(version, dir_fd=parent_descriptor, follow_symlinks=False)
        if (current.st_dev, current.st_ino) != (entry.st_dev, entry.st_ino):
            raise SystemExit("controlled install target changed before quarantine")
        os.rename(
            version,
            tombstone,
            src_dir_fd=parent_descriptor,
            dst_dir_fd=parent_descriptor,
        )
        os.fsync(parent_descriptor)
        for name in sorted(expected):
            item = os.stat(name, dir_fd=target_descriptor, follow_symlinks=False)
            if not stat.S_ISREG(item.st_mode):
                raise SystemExit("controlled install target contains an unsafe entry")
            os.unlink(name, dir_fd=target_descriptor)
    finally:
        os.close(target_descriptor)
    os.rmdir(tombstone, dir_fd=parent_descriptor)
    os.fsync(parent_descriptor)
finally:
    os.close(parent_descriptor)
PY
  printf 'Uninstalled codebase-memory-mcp %s; index cache remains at %s\n' \
    "${CBM_VERSION}" "${cache_dir}"
}

run_index() {
  local mode=$1
  shift
  local binary payload project_root python_bin graph_payload graph_result graph_count
  local -a inventory_arguments=()
  local inventory_argument_count=0
  acquire_index_lock
  while (( $# > 0 )); do
    case "$1" in
      --allow-untracked)
        (( $# >= 2 )) || fail "--allow-untracked requires an exact repository-relative path"
        inventory_arguments+=(--allow-untracked "$2")
        inventory_argument_count=$((inventory_argument_count + 2))
        shift 2
        ;;
      *)
        fail "unsupported index argument: $1"
        ;;
    esac
  done
  [[ -f "${input_helper}" ]] || fail "missing tracked-input helper: ${input_helper}"
  [[ -f "${input_ignore}" ]] || fail "missing input deny rules: ${input_ignore}"
  python_bin=$(find_python)
  local -a inventory_command=(
    "${python_bin}" "${input_helper}" prepare-shadow
    --repo-root "${repo_root}"
    --ignore-file "${input_ignore}"
    --cache-dir "${cache_dir}"
  )
  if (( inventory_argument_count > 0 )); then
    inventory_command+=("${inventory_arguments[@]}")
  fi
  project_root=$("${inventory_command[@]}") || \
    fail "could not prepare the tracked input generation"
  binary=$(resolve_binary)
  configure_runtime "${binary}"
  "${python_bin}" "${input_helper}" verify-shadow \
    --cache-dir "${cache_dir}" --shadow-path "${project_root}" >/dev/null || \
    fail "tracked input integrity check failed before native indexing"
  payload=$(repo_path_payload "${project_root}")
  printf '%s code graph from tracked input %s\n' "${mode}" "${project_root}" >&2
  if ! printf '%s\n' "${payload}" | run_native \
    "${binary}" 4194304 1048576 1800 cli index_repository; then
    fail "native indexing failed; the previous active input remains unchanged"
  fi
  "${python_bin}" "${input_helper}" verify-shadow \
    --cache-dir "${cache_dir}" \
    --shadow-path "${project_root}" >/dev/null || \
    fail "tracked input changed during indexing; the previous input remains active"
  graph_result=$(mktemp "${cache_dir}/.graph-paths.XXXXXX")
  chmod 0600 "${graph_result}"
  graph_payload=$("${python_bin}" -c \
    'import json,sys; print(json.dumps({"query":"MATCH (f:File) RETURN f.file_path","max_rows":20000,"project":sys.argv[1]},separators=(",",":")))' \
    "${project_root}")
  if ! printf '%s\n' "${graph_payload}" | run_native \
    "${binary}" 16777216 1048576 120 cli query_graph >"${graph_result}"; then
    unlink "${graph_result}"
    fail "could not verify indexed graph paths; the previous input remains active"
  fi
  if ! graph_count=$("${python_bin}" "${input_helper}" validate-graph-paths \
    --manifest "${project_root}/../manifest.json" \
    --graph-result "${graph_result}"); then
    unlink "${graph_result}"
    fail "indexed graph escaped or truncated its manifest; the previous input remains active"
  fi
  unlink "${graph_result}"
  "${python_bin}" "${input_helper}" activate-shadow \
    --cache-dir "${cache_dir}" \
    --shadow-path "${project_root}" || \
    fail "could not atomically activate the indexed input"
  cleanup_inactive_projects "${binary}" "${project_root}"
  release_index_lock || fail "could not safely release the controlled code graph lock"
  printf 'Active code graph input: %s (%s indexed files)\n' \
    "${project_root}" "${graph_count}"
}

run_query() {
  local tool=$1 raw_payload=${2:-\{\}} binary payload project_root python_bin result_file
  is_readonly_tool "${tool}" || fail "tool is not in the read-only allowlist: ${tool}"
  python_bin=$(find_python)
  payload=$(query_payload "${tool}" "${repo_root}" "${raw_payload}") || \
    fail "read-only query arguments failed validation"
  project_root=$("${python_bin}" "${input_helper}" current-shadow \
    --cache-dir "${cache_dir}") || fail "no valid active tracked input; run scripts/code-intel.sh index"
  binary=$(resolve_binary)
  configure_runtime "${binary}"
  "${python_bin}" "${input_helper}" verify-shadow \
    --cache-dir "${cache_dir}" --shadow-path "${project_root}" >/dev/null || \
    fail "tracked input integrity check failed before the native query"
  payload=$(query_payload "${tool}" "${project_root}" "${raw_payload}") || \
    fail "read-only query arguments failed active-generation binding"
  result_file=$(mktemp "${cache_dir}/.query-result.XXXXXX")
  chmod 0600 "${result_file}"
  if ! printf '%s\n' "${payload}" | run_native \
    "${binary}" 4194304 262144 120 cli "${tool}" >"${result_file}"; then
    unlink "${result_file}"
    fail "native read-only query failed"
  fi
  if ! "${python_bin}" "${input_helper}" verify-shadow \
    --cache-dir "${cache_dir}" \
    --shadow-path "${project_root}" >/dev/null; then
    unlink "${result_file}"
    fail "tracked input integrity check failed after the native query"
  fi
  cat "${result_file}"
  unlink "${result_file}"
}

trap 'cleanup_controlled_state || true' EXIT
trap 'handle_signal 130' INT
trap 'handle_signal 143' TERM

command_name=${1:-}
case "${command_name}" in
  install)
    [[ $# -eq 1 ]] || fail "install does not accept additional arguments"
    install_tool
    ;;
  index)
    run_index "Indexing" "${@:2}"
    ;;
  refresh)
    run_index "Refreshing" "${@:2}"
    ;;
  rebuild)
    run_index "Rebuilding" "${@:2}"
    ;;
  status)
    [[ $# -eq 1 ]] || fail "status does not accept additional arguments"
    run_query index_status '{}'
    ;;
  mcp)
    [[ $# -eq 1 ]] || fail "mcp does not accept additional arguments"
    python_bin=$(find_python)
    project_root=$("${python_bin}" "${input_helper}" current-shadow \
      --cache-dir "${cache_dir}") || fail "no valid active tracked input; run scripts/code-intel.sh index"
    binary=$(resolve_binary)
    IFS=$'\t' read -r _asset _archive_sha binary_sha < <(platform_asset)
    configure_runtime "${binary}"
    exec "${python_bin}" "${script_dir}/code-intel-mcp-proxy.py" \
      --binary "${binary}" \
      --binary-sha256 "${binary_sha}" \
      --repo-root "${repo_root}" \
      --project-root "${project_root}" \
      --cache-dir "${cache_dir}" \
      --input-helper "${input_helper}"
    ;;
  query)
    [[ $# -ge 2 && $# -le 3 ]] || fail "query requires a tool and optional JSON object"
    run_query "$2" "${3:-\{\}}"
    ;;
  uninstall)
    [[ $# -eq 1 ]] || fail "uninstall does not accept additional arguments"
    uninstall_tool
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
