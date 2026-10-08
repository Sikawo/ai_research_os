#!/usr/bin/env python3
"""Create or verify the deterministic GatedSprint skill-package manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_NAME = "skill-package-manifest.json"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def included_files() -> list[Path]:
    files: list[Path] = []
    for path in PACKAGE_ROOT.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(PACKAGE_ROOT)
        if relative.as_posix() == MANIFEST_NAME:
            continue
        if "__pycache__" in relative.parts or path.suffix == ".pyc":
            continue
        files.append(relative)
    return sorted(files, key=lambda item: item.as_posix())


def workflow_version() -> str:
    skill_text = (PACKAGE_ROOT / "SKILL.md").read_text(encoding="utf-8")
    match = re.search(r'^\s*version:\s*["\']([^"\']+)["\']\s*$', skill_text, re.MULTILINE)
    if not match:
        raise ValueError("SKILL.md does not declare metadata.version")
    return match.group(1)


def build_manifest() -> dict[str, object]:
    file_records: list[dict[str, object]] = []
    hash_lines: list[str] = []
    for relative in included_files():
        data = (PACKAGE_ROOT / relative).read_bytes()
        digest = sha256_bytes(data)
        relative_text = relative.as_posix()
        file_records.append(
            {"path": relative_text, "sha256": digest, "bytes": len(data)}
        )
        hash_lines.append(f"{digest}  {relative_text}")

    package_hash = sha256_bytes(("\n".join(hash_lines) + "\n").encode("utf-8"))
    return {
        "schema_version": 1,
        "skill_name": "gated-sprint",
        "workflow_version": workflow_version(),
        "hash_algorithm": "sha256",
        "package_hash": package_hash,
        "file_count": len(file_records),
        "files": file_records,
    }


def write_manifest() -> int:
    manifest = build_manifest()
    path = PACKAGE_ROOT / MANIFEST_NAME
    path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"WROTE {path} package_hash={manifest['package_hash']}")
    return 0


def verify_manifest() -> int:
    path = PACKAGE_ROOT / MANIFEST_NAME
    if not path.is_file():
        print(f"ERROR missing manifest: {path}", file=sys.stderr)
        return 1
    try:
        recorded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR cannot read manifest: {exc}", file=sys.stderr)
        return 1
    current = build_manifest()
    if recorded != current:
        print("ERROR package manifest does not match current files", file=sys.stderr)
        print(
            f"recorded={recorded.get('package_hash')} current={current['package_hash']}",
            file=sys.stderr,
        )
        return 1
    print(
        "PASS skill package manifest "
        f"version={current['workflow_version']} "
        f"files={current['file_count']} hash={current['package_hash']}"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("write", "verify"))
    args = parser.parse_args()
    if args.command == "write":
        return write_manifest()
    return verify_manifest()


if __name__ == "__main__":
    raise SystemExit(main())
