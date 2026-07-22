#!/usr/bin/env bash
set -euo pipefail
umask 077

readonly REPOMIX_VERSION="1.17.0"
readonly REPOMIX_INTEGRITY="sha512-W5vcI17Nuk7PvKhXWTyPZTtF3UnCQAoPBdYwgEFJHdYsOXNh829A6ZKzeY8d6/iAGKbom8lvZzuSnvgAbzdohw=="
readonly MAX_SNAPSHOT_BYTES=536870912

script_dir=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
readonly script_dir
repo_root=$(CDPATH= cd -- "${script_dir}/.." && pwd -P)
readonly repo_root
readonly config_path="${repo_root}/repomix.config.json"
readonly output_dir="${repo_root}/.ai-context"
readonly output_path="${output_dir}/repomix.xml"
readonly manifest_path="${output_dir}/repomix-input-manifest.json"
readonly current_path="${output_dir}/current.json"
readonly input_helper="${script_dir}/ai-context-inputs.py"
readonly input_ignore="${repo_root}/.repomixignore"
readonly profile_config="${script_dir}/ai-context-profiles.json"
readonly runtime_source="${script_dir}/repomix-runtime"
readonly runtime_verifier="${script_dir}/verify-ai-tool-supply-chain.py"
readonly bounded_runner="${script_dir}/run-bounded-ai-tool.py"

fail() {
  printf 'build-ai-context: %s\n' "$*" >&2
  exit 1
}

declare -a inventory_arguments=()
inventory_argument_count=0
profile_name=full
while (( $# > 0 )); do
  case "$1" in
    --allow-untracked)
      (( $# >= 2 )) || fail "--allow-untracked requires an exact repository-relative path"
      inventory_arguments+=(--allow-untracked "$2")
      inventory_argument_count=$((inventory_argument_count + 2))
      shift 2
      ;;
    --profile)
      (( $# >= 2 )) || fail "--profile requires a configured profile name"
      profile_name=$2
      shift 2
      ;;
    -h|--help)
      cat <<'EOF'
Usage: scripts/build-ai-context.sh [--profile NAME] [--allow-untracked PATH]...

By default only committed or staged-added Git paths are eligible. Their current
worktree bytes are packed. Untracked files require exact-path exceptions, and
deny rules always win. Profiles: full (default), backend, frontend, tooling.
EOF
      exit 0
      ;;
    *)
      fail "unsupported argument: $1"
      ;;
  esac
done
[[ -f "${config_path}" ]] || fail "missing ${config_path}"
[[ -f "${input_helper}" ]] || fail "missing ${input_helper}"
[[ -f "${input_ignore}" ]] || fail "missing ${input_ignore}"
[[ -f "${profile_config}" ]] || fail "missing ${profile_config}"
[[ -f "${runtime_source}/package.json" ]] || fail "missing Repomix runtime package.json"
[[ -f "${runtime_source}/package-lock.json" ]] || fail "missing Repomix runtime lockfile"
[[ -f "${runtime_verifier}" ]] || fail "missing Repomix supply-chain verifier"
[[ -f "${bounded_runner}" ]] || fail "missing bounded AI tool runner"

if command -v python3 >/dev/null 2>&1; then
  python_bin=python3
elif command -v python >/dev/null 2>&1; then
  python_bin=python
else
  fail "Python 3 is required for the tracked input manifest"
fi

shopt -s nullglob
legacy_repopack_files=(
  "${repo_root}"/repopack.config.*
  "${repo_root}"/repopack-output.*
)
shopt -u nullglob
if [[ -e "${repo_root}/.repopackignore" ]]; then
  legacy_repopack_files+=("${repo_root}/.repopackignore")
fi
if (( ${#legacy_repopack_files[@]} > 0 )); then
  fail "legacy repopack files must be reviewed and removed before packing: ${legacy_repopack_files[*]}"
fi

command -v node >/dev/null 2>&1 || fail "Node.js is required for the pinned Repomix runtime"
command -v npm >/dev/null 2>&1 || fail "npm is required to install the locked Repomix runtime"
node_bin=$(command -v node)
npm_bin=$(command -v npm)

"${python_bin}" "${input_helper}" prepare-context-layout \
  --repo-root "${repo_root}" >/dev/null || fail "AI context output layout is unsafe"
build_dir=$(mktemp -d "${output_dir}/.building.XXXXXX")
readonly build_dir
input_list="${build_dir}/input-paths.txt"
temporary_manifest="${build_dir}/manifest.json"
temporary_snapshot="${build_dir}/repomix.xml"
input_root="${build_dir}/input-root"
runtime_dir="${build_dir}/repomix-runtime"
runtime_home="${build_dir}/runtime-home"
runtime_tmp="${build_dir}/runtime-tmp"
runtime_cache="${build_dir}/npm-cache"
copied_config_path="${build_dir}/repomix.config.json"
cleanup() {
  if [[ -d "${build_dir}" ]]; then
    if [[ -e "${input_root}" && ! -L "${input_root}" ]]; then
      "${python_bin}" "${input_helper}" remove-snapshot-input \
        --repo-root "${repo_root}" --destination "${input_root}" >/dev/null || return 1
    fi
    "${python_bin}" - "${build_dir}" "${output_dir}" <<'PY'
import os
import pathlib
import shutil
import stat
import sys

target = pathlib.Path(os.path.abspath(sys.argv[1]))
output = pathlib.Path(os.path.abspath(sys.argv[2]))
if (
    not target.name.startswith(".building.")
    or target.parent != output
    or target.is_symlink()
    or output.is_symlink()
):
    raise SystemExit("refusing to clean an unsafe AI context build directory")
for current_root, directory_names, file_names in os.walk(target, topdown=False, followlinks=False):
    current = pathlib.Path(current_root)
    for name in file_names:
        item = current / name
        if item.is_symlink():
            item.unlink()
            continue
        item.chmod(0o600)
    for name in directory_names:
        item = current / name
        if item.is_symlink():
            item.unlink()
            continue
        item.chmod(0o700)
    current.chmod(0o700)
shutil.rmtree(target)
PY
  fi
}
trap cleanup EXIT

mkdir -p -- "${runtime_dir}" "${runtime_home}" "${runtime_tmp}" "${runtime_cache}"
chmod 0700 "${runtime_dir}" "${runtime_home}" "${runtime_tmp}" "${runtime_cache}"
"${python_bin}" - \
  "${runtime_source}/package.json" "${runtime_dir}/package.json" 1048576 \
  "${runtime_source}/package-lock.json" "${runtime_dir}/package-lock.json" 16777216 \
  "${config_path}" "${copied_config_path}" 1048576 <<'PY'
import os
import stat
import sys

arguments = sys.argv[1:]
if len(arguments) % 3:
    raise SystemExit("invalid safe-copy argument set")
for offset in range(0, len(arguments), 3):
    source, destination, raw_limit = arguments[offset : offset + 3]
    limit = int(raw_limit)
    source_flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    if hasattr(os, "O_NOFOLLOW"):
        source_flags |= os.O_NOFOLLOW
    source_descriptor = os.open(source, source_flags)
    try:
        before = os.fstat(source_descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
            raise SystemExit(f"unsafe or oversized pinned input: {source}")
        destination_descriptor = os.open(
            destination,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0),
            0o600,
        )
        try:
            while True:
                chunk = os.read(source_descriptor, 1024 * 1024)
                if not chunk:
                    break
                remaining = memoryview(chunk)
                while remaining:
                    written = os.write(destination_descriptor, remaining)
                    remaining = remaining[written:]
            os.fsync(destination_descriptor)
        finally:
            os.close(destination_descriptor)
        after = os.fstat(source_descriptor)
        if (
            before.st_dev != after.st_dev
            or before.st_ino != after.st_ino
            or before.st_size != after.st_size
            or before.st_mtime_ns != after.st_mtime_ns
        ):
            raise SystemExit(f"pinned input changed while it was copied: {source}")
    finally:
        os.close(source_descriptor)
PY

supply_chain_json=$("${python_bin}" "${runtime_verifier}" \
  --source-dir "${runtime_dir}" --json) || \
  fail "copied Repomix dependency lock failed offline validation"
runtime_lock_sha=$("${python_bin}" -c \
  'import json,sys; print(json.loads(sys.argv[1])["package_lock_sha256"])' \
  "${supply_chain_json}")
runtime_package_sha=$("${python_bin}" -c \
  'import json,sys; print(json.loads(sys.argv[1])["package_json_sha256"])' \
  "${supply_chain_json}")
runtime_path="$(dirname -- "${node_bin}"):$(dirname -- "${npm_bin}"):/usr/bin:/bin"
node_version=$("${python_bin}" "${bounded_runner}" \
  --cwd "${repo_root}" --timeout 15 --stdout-limit 4096 --stderr-limit 4096 \
  --clear-environment --env "PATH=${runtime_path}" --env LC_ALL=C --env TZ=UTC \
  -- "${node_bin}" --version </dev/null) || fail "could not read Node.js version safely"
npm_version=$("${python_bin}" "${bounded_runner}" \
  --cwd "${repo_root}" --timeout 15 --stdout-limit 4096 --stderr-limit 4096 \
  --clear-environment --env "PATH=${runtime_path}" --env LC_ALL=C --env TZ=UTC \
  -- "${npm_bin}" --version </dev/null) || fail "could not read npm version safely"

declare -a inventory_command=(
  "${python_bin}" "${input_helper}" inventory
  --repo-root "${repo_root}"
  --ignore-file "${input_ignore}"
  --format repomix-lines
  --manifest "${temporary_manifest}"
  --profile-config "${profile_config}"
  --profile "${profile_name}"
)
if (( inventory_argument_count > 0 )); then
  inventory_command+=("${inventory_arguments[@]}")
fi
"${inventory_command[@]}" >"${input_list}" || \
  fail "could not build the tracked input manifest"
[[ -s "${input_list}" ]] || fail "tracked input manifest approved no files"

"${python_bin}" "${input_helper}" materialize-snapshot-input \
  --repo-root "${repo_root}" \
  --manifest "${temporary_manifest}" \
  --destination "${input_root}" >/dev/null || \
  fail "could not materialize the immutable Repomix input"

"${python_bin}" "${bounded_runner}" \
  --cwd "${runtime_dir}" --timeout 600 \
  --stdout-limit 1048576 --stderr-limit 1048576 \
  --clear-environment \
  --env "PATH=${runtime_path}" \
  --env "HOME=${runtime_home}" \
  --env "TMPDIR=${runtime_tmp}" \
  --env LC_ALL=C --env TZ=UTC --env CI=1 --env NO_COLOR=1 \
  --env "npm_config_cache=${runtime_cache}" \
  --env "npm_config_userconfig=${runtime_home}/.npmrc" \
  --env "npm_config_globalconfig=${runtime_home}/global-npmrc" \
  --env npm_config_ignore_scripts=true \
  --env npm_config_audit=false \
  --env npm_config_fund=false \
  --env npm_config_update_notifier=false \
  -- "${npm_bin}" ci --ignore-scripts --no-audit --no-fund --omit=dev --silent \
  </dev/null || fail "could not install the locked Repomix dependency closure safely"

repomix_bin="${runtime_dir}/node_modules/repomix/bin/repomix.cjs"
"${python_bin}" - \
  "${runtime_dir}" "${REPOMIX_VERSION}" "${REPOMIX_INTEGRITY}" <<'PY'
import json
import pathlib
import stat
import sys

runtime, expected_version, expected_integrity = sys.argv[1:]
runtime = pathlib.Path(runtime)
package = runtime / "node_modules/repomix/package.json"
binary = runtime / "node_modules/repomix/bin/repomix.cjs"
license_path = runtime / "node_modules/repomix/LICENSE"
lock = json.loads((runtime / "package-lock.json").read_text(encoding="utf-8"))
if package.is_symlink() or binary.is_symlink() or license_path.is_symlink():
    raise SystemExit("Repomix runtime contains an unsafe symlink")
if not all(path.is_file() for path in (package, binary, license_path)):
    raise SystemExit("Repomix runtime is incomplete")
if json.loads(package.read_text(encoding="utf-8")).get("version") != expected_version:
    raise SystemExit("Repomix installed version differs from the lock")
entry = lock["packages"]["node_modules/repomix"]
if entry.get("version") != expected_version or entry.get("integrity") != expected_integrity:
    raise SystemExit("Repomix installed package metadata differs from the lock")
if not stat.S_ISREG(binary.lstat().st_mode):
    raise SystemExit("Repomix entry point is not a regular file")
PY

repomix_environment=(
  --env "PATH=${runtime_path}"
  --env "HOME=${runtime_home}"
  --env "TMPDIR=${runtime_tmp}"
  --env "XDG_CACHE_HOME=${runtime_cache}"
  --env "NODE_COMPILE_CACHE=${runtime_cache}/node-compile"
  --env LC_ALL=C
  --env TZ=UTC
  --env CI=1
  --env NO_COLOR=1
)
version_output=$("${python_bin}" "${bounded_runner}" \
  --cwd "${runtime_dir}" --timeout 15 \
  --stdout-limit 4096 --stderr-limit 4096 --clear-environment \
  "${repomix_environment[@]}" -- \
  "${node_bin}" "${repomix_bin}" --version </dev/null) || \
  fail "could not read the locked Repomix version safely"
[[ "${version_output}" == *"${REPOMIX_VERSION}"* ]] || \
  fail "expected Repomix ${REPOMIX_VERSION}, got: ${version_output}"

"${python_bin}" "${bounded_runner}" \
  --cwd "${input_root}" --timeout 600 \
  --stdout-limit 4194304 --stderr-limit 1048576 --clear-environment \
  --watch-file "${temporary_snapshot}=${MAX_SNAPSHOT_BYTES}" \
  "${repomix_environment[@]}" -- \
  "${node_bin}" "${repomix_bin}" \
  --stdin \
  --config "${copied_config_path}" \
  --output "${temporary_snapshot}" <"${input_list}" >/dev/null || \
  fail "Repomix failed safely while reading the immutable input generation"
[[ -f "${temporary_snapshot}" ]] || fail "Repomix did not create a snapshot"

packed_count=$("${python_bin}" "${input_helper}" validate-snapshot \
  --manifest "${temporary_manifest}" \
  --snapshot "${temporary_snapshot}") || \
  fail "Repomix output escaped its tracked input manifest"
chmod 0600 "${temporary_manifest}" "${temporary_snapshot}"

bundle_id=$("${python_bin}" - \
  "${temporary_manifest}" "${copied_config_path}" "${temporary_snapshot}" \
  "${REPOMIX_VERSION}" \
  "${runtime_package_sha}" "${runtime_lock_sha}" \
  "${node_version}" "${npm_version}" <<'PY'
import hashlib
import json
import pathlib
import sys

(
    manifest_path,
    config_path,
    snapshot_path,
    version,
    package_sha,
    lock_sha,
    node_version,
    npm_version,
) = sys.argv[1:]
manifest = json.loads(pathlib.Path(manifest_path).read_text(encoding="utf-8"))
digest = hashlib.sha256()
for label, value in (
    ("inventory", manifest["inventory_sha256"]),
    ("config", hashlib.sha256(pathlib.Path(config_path).read_bytes()).hexdigest()),
    ("snapshot", hashlib.sha256(pathlib.Path(snapshot_path).read_bytes()).hexdigest()),
    ("runtime_package", package_sha),
    ("runtime_lock", lock_sha),
    ("repomix", version),
    ("node", node_version),
    ("npm", npm_version),
):
    digest.update(label.encode("ascii") + b"\0" + value.encode("ascii") + b"\0")
print(digest.hexdigest())
PY
)
provenance_path="${build_dir}/provenance.json"
"${python_bin}" - \
  "${temporary_manifest}" "${copied_config_path}" "${temporary_snapshot}" \
  "${provenance_path}" \
  "${bundle_id}" "${REPOMIX_VERSION}" "${REPOMIX_INTEGRITY}" \
  "${runtime_package_sha}" "${runtime_lock_sha}" \
  "${node_version}" "${npm_version}" "${packed_count}" <<'PY'
import hashlib
import json
import os
import pathlib
import sys

(
    manifest_path,
    config_path,
    snapshot_path,
    provenance_path,
    bundle_id,
    repomix_version,
    repomix_integrity,
    package_sha,
    lock_sha,
    node_version,
    npm_version,
    packed_count,
) = sys.argv[1:]
manifest = json.loads(pathlib.Path(manifest_path).read_text(encoding="utf-8"))
payload = {
    "schema_version": 1,
    "bundle_id": bundle_id,
    "inventory_sha256": manifest["inventory_sha256"],
    "profile": manifest["profile"],
    "packed_file_count": int(packed_count),
    "config_sha256": hashlib.sha256(pathlib.Path(config_path).read_bytes()).hexdigest(),
    "snapshot_sha256": hashlib.sha256(pathlib.Path(snapshot_path).read_bytes()).hexdigest(),
    "runtime_package_sha256": package_sha,
    "runtime_lock_sha256": lock_sha,
    "repomix_version": repomix_version,
    "repomix_integrity": repomix_integrity,
    "node_version": node_version,
    "npm_version": npm_version,
}
path = pathlib.Path(provenance_path)
descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
    json.dump(payload, handle, sort_keys=True, separators=(",", ":"))
    handle.write("\n")
    handle.flush()
    os.fsync(handle.fileno())
PY

"${python_bin}" "${input_helper}" remove-snapshot-input \
  --repo-root "${repo_root}" --destination "${input_root}" >/dev/null || \
  fail "could not safely remove the transient immutable input"
"${python_bin}" - "${build_dir}" \
  runtime-home runtime-tmp npm-cache repomix-runtime <<'PY'
import pathlib
import shutil
import sys

build = pathlib.Path(sys.argv[1]).resolve()
for name in sys.argv[2:]:
    target = build / name
    if target.parent != build or target.is_symlink() or not target.is_dir():
        raise SystemExit(f"unsafe transient runtime directory: {target}")
    shutil.rmtree(target)
PY
unlink "${input_list}"
unlink "${copied_config_path}"
chmod 0600 "${provenance_path}"
bundle_dir=$("${python_bin}" "${input_helper}" publish-context-bundle \
  --repo-root "${repo_root}" \
  --build-dir "${build_dir}" \
  --bundle-id "${bundle_id}" \
  --packed-count "${packed_count}") || \
  fail "could not atomically publish and activate the AI context bundle"
[[ "${bundle_dir}" == "${output_dir}/snapshots/${bundle_id}" ]] || \
  fail "AI context publisher returned an unexpected bundle path"

trap - EXIT
cleanup
printf 'AI context snapshot: %s (%s files; bundle %s)\n' \
  "${output_path}" "${packed_count}" "${bundle_id}"
printf 'AI context manifest: %s\n' "${manifest_path}"
