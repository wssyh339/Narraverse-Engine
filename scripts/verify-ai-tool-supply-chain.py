#!/usr/bin/env python3
"""Offline validation for the pinned Repomix dependency closure."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any, Dict


REPOMIX_VERSION = "1.17.0"
REPOMIX_INTEGRITY = "sha512-W5vcI17Nuk7PvKhXWTyPZTtF3UnCQAoPBdYwgEFJHdYsOXNh829A6ZKzeY8d6/iAGKbom8lvZzuSnvgAbzdohw=="
REPOMIX_RESOLVED = "https://registry.npmjs.org/repomix/-/repomix-1.17.0.tgz"
REVIEWED_LOCK_SHA256 = "0d2a6f6899f6c1bcef2c10d37f13b07fa06e8344bcb03b81dc18d5f7c023ab0b"
REVIEWED_PACKAGE_COUNT = 170
REGISTRY_PREFIX = "https://registry.npmjs.org/"
EXACT_VERSION = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?$")


class SupplyChainError(RuntimeError):
    pass


def read_json(path: Path) -> Dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SupplyChainError(f"invalid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise SupplyChainError(f"expected JSON object: {path}")
    return payload


def validate_integrity(value: Any, package_path: str) -> None:
    if not isinstance(value, str) or not value.startswith("sha512-"):
        raise SupplyChainError(f"missing SHA-512 integrity: {package_path}")
    try:
        decoded = base64.b64decode(value.removeprefix("sha512-"), validate=True)
    except (ValueError, base64.binascii.Error) as exc:
        raise SupplyChainError(f"invalid SHA-512 integrity: {package_path}") from exc
    if len(decoded) != 64:
        raise SupplyChainError(f"wrong SHA-512 integrity length: {package_path}")


def validate_runtime(source_dir: Path) -> Dict[str, Any]:
    source_dir = source_dir.expanduser().resolve()
    package_path = source_dir / "package.json"
    lock_path = source_dir / "package-lock.json"
    package = read_json(package_path)
    lock = read_json(lock_path)
    lock_sha = hashlib.sha256(lock_path.read_bytes()).hexdigest()
    if lock_sha != REVIEWED_LOCK_SHA256:
        raise SupplyChainError("Repomix transitive lock differs from the reviewed closure")
    if package.get("private") is not True or package.get("license") != "UNLICENSED":
        raise SupplyChainError("Repomix runtime must be private and unpublishable")
    if package.get("dependencies") != {"repomix": REPOMIX_VERSION}:
        raise SupplyChainError("Repomix package dependency is not exact")
    if package.get("scripts") or package.get("devDependencies"):
        raise SupplyChainError("Repomix runtime must not define scripts or dev dependencies")
    if lock.get("lockfileVersion") != 3:
        raise SupplyChainError("Repomix package-lock must use lockfileVersion 3")
    packages = lock.get("packages")
    if not isinstance(packages, dict) or not packages:
        raise SupplyChainError("Repomix package-lock packages map is missing")
    if len(packages) - 1 != REVIEWED_PACKAGE_COUNT:
        raise SupplyChainError("Repomix reviewed package count has drifted")
    root = packages.get("")
    if not isinstance(root, dict) or root.get("dependencies") != {"repomix": REPOMIX_VERSION}:
        raise SupplyChainError("Repomix lock root dependency is not exact")
    repomix = packages.get("node_modules/repomix")
    if not isinstance(repomix, dict):
        raise SupplyChainError("Repomix lock entry is missing")
    if (
        repomix.get("version") != REPOMIX_VERSION
        or repomix.get("resolved") != REPOMIX_RESOLVED
        or repomix.get("integrity") != REPOMIX_INTEGRITY
        or repomix.get("license") != "MIT"
        or repomix.get("bin", {}).get("repomix") != "bin/repomix.cjs"
    ):
        raise SupplyChainError("Repomix lock entry differs from the reviewed package")

    for package_key, entry in packages.items():
        if package_key == "":
            continue
        if not isinstance(package_key, str) or not isinstance(entry, dict):
            raise SupplyChainError("Repomix lock contains an invalid package entry")
        key = PurePosixPath(package_key)
        if key.is_absolute() or ".." in key.parts or not package_key.startswith("node_modules/"):
            raise SupplyChainError(f"package path escapes node_modules: {package_key}")
        version = entry.get("version")
        resolved = entry.get("resolved")
        if not isinstance(version, str) or EXACT_VERSION.fullmatch(version) is None:
            raise SupplyChainError(f"package version is not exact: {package_key}")
        if not isinstance(resolved, str) or not resolved.startswith(REGISTRY_PREFIX):
            raise SupplyChainError(f"package does not resolve through registry HTTPS: {package_key}")
        if entry.get("link") is True or entry.get("hasInstallScript") is True:
            raise SupplyChainError(f"linked or install-script package is forbidden: {package_key}")
        validate_integrity(entry.get("integrity"), package_key)

    package_sha = hashlib.sha256(package_path.read_bytes()).hexdigest()
    return {
        "schema_version": 1,
        "repomix_version": REPOMIX_VERSION,
        "repomix_integrity": REPOMIX_INTEGRITY,
        "package_count": len(packages) - 1,
        "package_json_sha256": package_sha,
        "package_lock_sha256": lock_sha,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-dir",
        default=str(Path(__file__).resolve().parent / "repomix-runtime"),
    )
    parser.add_argument("--json", action="store_true")
    arguments = parser.parse_args()
    try:
        result = validate_runtime(Path(arguments.source_dir))
    except SupplyChainError as exc:
        raise SystemExit(f"verify-ai-tool-supply-chain: {exc}") from exc
    if arguments.json:
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    else:
        print(
            "Pinned Repomix closure: OK "
            f"({result['package_count']} packages; lock {result['package_lock_sha256']})"
        )


if __name__ == "__main__":
    main()
