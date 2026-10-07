#!/usr/bin/env python3
"""Validate the clean-history public repository scaffold."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path


APPROVED_BOOTSTRAP_PATHS = {
    ".gitattributes",
    ".gitignore",
    "AGENTS.md",
    "AI_SAFE.md",
    "LICENSE",
    "README.md",
    "REPO_PROFILE.md",
    "Scripts/validate_repository_safety.py",
    "config/autonomous_delivery.json",
    "manifests/phase6a_transfer_allowlist.yaml",
    "tests/test_repository_safety.py",
}

MAX_FILE_BYTES = 200_000
EXPECTED_ORIGIN = "https://github.com/Sikawo/ai_research_os.git"

FORBIDDEN_SUFFIXES = {
    ".czi", ".ipynb", ".key", ".lif", ".nd2", ".pdf", ".pem",
    ".tif", ".tiff", ".zip",
}

FORBIDDEN_CONTENT = {
    "local absolute path": re.compile(
        r"(?:/" + r"Users/|/" + r"home/|[A-Za-z]:\\\\" + r"Users\\\\)"
    ),
    "private key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "GitHub token": re.compile(
        r"(?:gh" + r"p_|github_" + r"pat_)[A-Za-z0-9_]+"
    ),
    "OpenAI-style secret": re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"),
}


def git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def repository_files(root: Path) -> set[str]:
    candidates = git(root, "ls-files", "--cached", "--others", "--exclude-standard")
    if candidates.returncode == 0:
        return {line for line in candidates.stdout.splitlines() if line}

    files: set[str] = set()
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if relative.parts and relative.parts[0] == ".git":
            continue
        if path.is_file() or path.is_symlink():
            files.add(relative.as_posix())
    return files


def validate_tree(root: Path) -> list[str]:
    errors: list[str] = []
    files = repository_files(root)

    missing = sorted(APPROVED_BOOTSTRAP_PATHS - files)
    extra = sorted(files - APPROVED_BOOTSTRAP_PATHS)
    if missing:
        errors.append(f"missing approved bootstrap paths: {', '.join(missing)}")
    if extra:
        errors.append(f"paths outside bootstrap allowlist: {', '.join(extra)}")

    for relative in sorted(files):
        path = root / relative
        if path.is_symlink():
            errors.append(f"symlink is not allowed: {relative}")
            continue
        if path.suffix.lower() in FORBIDDEN_SUFFIXES:
            errors.append(f"forbidden file type: {relative}")
        if path.stat().st_size > MAX_FILE_BYTES:
            errors.append(f"file exceeds review size limit: {relative}")
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            errors.append(f"non-text bootstrap file: {relative}")
            continue
        for label, pattern in FORBIDDEN_CONTENT.items():
            if pattern.search(content):
                errors.append(f"{label} marker found: {relative}")

    manifest_path = root / "config" / "autonomous_delivery.json"
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            errors.append(f"invalid autonomous-delivery manifest: {exc}")
        else:
            if manifest.get("enabled") is not False:
                errors.append("autonomous delivery must remain disabled")
            if manifest.get("max_git_level") != 0:
                errors.append("bootstrap autonomous-delivery ceiling must be 0")
            if manifest.get("origin_url") != EXPECTED_ORIGIN:
                errors.append("manifest origin does not match the public repository")

    allowlist_path = root / "manifests" / "phase6a_transfer_allowlist.yaml"
    if allowlist_path.is_file():
        allowlist = allowlist_path.read_text(encoding="utf-8")
        if "status: empty" not in allowlist or "transfers: []" not in allowlist:
            errors.append("Phase 6A transfer allowlist must remain empty")
        if "deny_by_default: true" not in allowlist:
            errors.append("Phase 6A transfer allowlist must deny by default")

    return errors


def validate_post_commit(root: Path) -> list[str]:
    errors: list[str] = []
    branch = git(root, "branch", "--show-current")
    if branch.returncode or branch.stdout.strip() != "main":
        errors.append("root commit must be on main")

    origin = git(root, "remote", "get-url", "origin")
    if origin.returncode or origin.stdout.strip() != EXPECTED_ORIGIN:
        errors.append("origin does not match the public repository")

    count = git(root, "rev-list", "--count", "HEAD")
    if count.returncode or count.stdout.strip() != "1":
        errors.append("history must contain exactly one commit")

    roots = git(root, "rev-list", "--max-parents=0", "HEAD")
    root_commits = [line for line in roots.stdout.splitlines() if line]
    if roots.returncode or len(root_commits) != 1:
        errors.append("history must contain exactly one root commit")

    tracked = git(root, "ls-tree", "-r", "--name-only", "HEAD")
    tracked_paths = {line for line in tracked.stdout.splitlines() if line}
    if tracked.returncode or tracked_paths != APPROVED_BOOTSTRAP_PATHS:
        errors.append("root commit paths do not match the bootstrap allowlist")

    status = git(root, "status", "--porcelain")
    if status.returncode or status.stdout.strip():
        errors.append("working tree must be clean after the root commit")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--phase",
        choices=("pre-commit", "post-commit"),
        default="pre-commit",
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]

    errors = validate_tree(root)
    if args.phase == "post-commit":
        errors.extend(validate_post_commit(root))

    if errors:
        for error in errors:
            print(f"BLOCK: {error}")
        return 1

    print(f"PASS: public scaffold safety validation ({args.phase})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
