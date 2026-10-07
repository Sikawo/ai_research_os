#!/usr/bin/env python3
"""Validate the public repository tree, transfer manifest, and Git boundary."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path, PurePosixPath
from typing import Any


BASELINE_PATHS = {
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

GOVERNANCE_PATHS = {
    "shared_core/CORE_AI_CHAT_ACCESS_POLICY.md",
    "shared_core/CORE_AUTONOMOUS_DELIVERY_POLICY.md",
    "shared_core/CORE_COMMAND_POLICY.md",
    "shared_core/CORE_EXTERNAL_AI.md",
    "shared_core/CORE_PRINCIPLES.md",
    "shared_core/CORE_REVIEW_POLICY.md",
    "shared_core/CORE_WORKFLOW.md",
    "shared_core/README.md",
    "Docs/codex_autonomous_work_policy.md",
    "Docs/codex_team_workflow.md",
    "Docs/final_review_workflow.md",
    "Schemas/autonomous_delivery.schema.json",
    "Schemas/autonomous_review.schema.json",
    "Schemas/autonomous_task_scope.schema.json",
    "Scripts/autonomous_delivery.py",
    "Scripts/check_shared_core.py",
    "Scripts/finalize_completed_change.py",
    "Scripts/finish_change.py",
    "Scripts/handoff.py",
    "Scripts/import_change_spec.py",
    "Scripts/prepare_commit_after_review.py",
    "Scripts/run_safety_check.py",
    "Scripts/safe_codex_auto_push.py",
    "Scripts/start_change.py",
    "Templates/autonomous_delivery.example.json",
    "Templates/autonomous_review.example.json",
    "Templates/autonomous_task_scope.example.json",
    "Templates/change_spec_template.md",
    "Templates/expected_behavior_template.md",
    "Templates/user_profile_template.md",
    "tests/test_autonomous_delivery.py",
    "tests/test_check_shared_core.py",
    "tests/test_codex_autonomous_work_policy.py",
    "tests/test_final_review_workflow.py",
    "tests/test_finalize_completed_change.py",
    "tests/test_import_change_spec.py",
    "tests/test_prepare_commit_after_review.py",
    "tests/test_safe_codex_auto_push.py",
    "tests/test_start_change.py",
    "requirements-dev.txt",
}

EXPECTED_ORIGIN = "https://github.com/Sikawo/ai_research_os.git"
EXPECTED_ROOT_COMMIT = "89c16ee682ea8aec910e982130e236a281df924e"
EXPECTED_TRANSFER_COUNT = 169
EXPECTED_PORTED_COUNT = 40
MAX_FILE_BYTES = 200_000

FORBIDDEN_SUFFIXES = {
    ".bam", ".cram", ".czi", ".doc", ".docx", ".fcs", ".fastq",
    ".h5", ".hdf5", ".ipynb", ".key", ".lif", ".nd2", ".pdf",
    ".pem", ".tif", ".tiff", ".vcf", ".zip",
}

FORBIDDEN_CONTENT = {
    "local absolute path": re.compile(
        r"(?:/" + r"Users/|/" + r"home/|[A-Za-z]:\\\\" + r"Users\\\\)"
    ),
    "local file URL": re.compile("file:" + r"//", re.IGNORECASE),
    "private key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "GitHub token": re.compile(r"(?:ghp_|github_pat_)[A-Za-z0-9_]+"),
    "OpenAI-style secret": re.compile(r"\\bsk-[A-Za-z0-9_-]{16,}"),
    "Slack webhook": re.compile(r"https://hooks\\.slack\\.com/services/"),
    "Google resource binding": re.compile(
        r"https://(?:drive\\.google\\.com/drive/folders|docs\\.google\\.com/(?:spreadsheets|document)/d)/[A-Za-z0-9_-]{10,}"
    ),
}

ALLOWED_TRANSFER_MODES = {
    "exact_copy",
    "sanitized_copy",
    "refactor_public_api",
    "adapted_public_copy",
}


def git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=root, check=False, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
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


def load_manifest(root: Path) -> tuple[dict[str, Any] | None, list[str]]:
    path = root / "manifests" / "phase6a_transfer_allowlist.yaml"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, [f"invalid transfer manifest: {exc}"]
    if not isinstance(value, dict):
        return None, ["transfer manifest must be an object"]
    return value, []


def is_safe_relative_path(value: object) -> bool:
    if not isinstance(value, str) or not value or "\\" in value:
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and ".." not in path.parts and "." not in path.parts


def validate_manifest(manifest: dict[str, Any]) -> tuple[list[str], set[str], set[str]]:
    errors: list[str] = []
    if manifest.get("schema_version") != 1:
        errors.append("transfer manifest schema_version must be 1")
    if manifest.get("manifest_id") != "phase6a-transfer-allowlist":
        errors.append("unexpected transfer manifest id")
    if manifest.get("status") != "approved_for_offline_transfer":
        errors.append("transfer manifest is not approved for offline transfer")
    if manifest.get("deny_by_default") is not True:
        errors.append("transfer manifest must deny by default")
    if manifest.get("expected_transfer_count") != EXPECTED_TRANSFER_COUNT:
        errors.append(f"expected_transfer_count must be {EXPECTED_TRANSFER_COUNT}")

    rules = manifest.get("rules")
    required_rules = {
        "exact_paths_only": True,
        "synthetic_fixtures_only": True,
        "copy_git_history": False,
        "copy_private_values": False,
        "copy_runtime_state": False,
        "copy_connector_bindings": False,
        "copy_scheduled_tasks": False,
        "live_cutover": False,
    }
    if not isinstance(rules, dict):
        errors.append("transfer manifest rules must be an object")
    else:
        for name, expected in required_rules.items():
            if rules.get(name) is not expected:
                errors.append(f"transfer rule {name} must be {expected!r}")

    sources = manifest.get("sources")
    if not isinstance(sources, dict) or not sources:
        errors.append("transfer manifest sources must be a non-empty object")
        sources = {}
    transfers = manifest.get("transfers")
    if not isinstance(transfers, list):
        return errors + ["transfers must be a list"], set(), set()
    if len(transfers) != EXPECTED_TRANSFER_COUNT:
        errors.append(
            f"transfer manifest must contain {EXPECTED_TRANSFER_COUNT} entries; found {len(transfers)}"
        )

    source_keys: set[tuple[str, str]] = set()
    destinations: set[str] = set()
    ported: set[str] = set()
    for index, transfer in enumerate(transfers):
        label = f"transfer[{index}]"
        if not isinstance(transfer, dict):
            errors.append(f"{label} must be an object")
            continue
        source_id = transfer.get("source_id")
        source_path = transfer.get("source_path")
        destination_path = transfer.get("destination_path")
        source_commit = transfer.get("source_commit")
        if source_id not in sources:
            errors.append(f"{label} has unknown source_id")
        elif not isinstance(sources[source_id], dict) or source_commit != sources[source_id].get("commit"):
            errors.append(f"{label} source_commit does not match its source")
        if not is_safe_relative_path(source_path):
            errors.append(f"{label} has unsafe source_path")
        if not is_safe_relative_path(destination_path):
            errors.append(f"{label} has unsafe destination_path")
        if transfer.get("transfer_mode") not in ALLOWED_TRANSFER_MODES:
            errors.append(f"{label} has unsupported transfer_mode")
        if transfer.get("phase") not in {"6A.0", "6A.1"}:
            errors.append(f"{label} has unsupported phase")
        if transfer.get("status") not in {"planned", "ported_offline"}:
            errors.append(f"{label} has unsupported status")
        if isinstance(source_id, str) and isinstance(source_path, str):
            key = (source_id, source_path)
            if key in source_keys:
                errors.append(f"duplicate source path: {source_id}:{source_path}")
            source_keys.add(key)
        if isinstance(destination_path, str):
            if destination_path in destinations:
                errors.append(f"duplicate destination path: {destination_path}")
            destinations.add(destination_path)
            if transfer.get("status") == "ported_offline":
                ported.add(destination_path)

    if len(ported) != EXPECTED_PORTED_COUNT:
        errors.append(
            f"manifest must mark {EXPECTED_PORTED_COUNT} governance paths ported; found {len(ported)}"
        )
    if ported != GOVERNANCE_PATHS:
        errors.append("ported transfer paths do not match the Phase 6A.0 governance cohort")
    return errors, destinations, ported


def validate_tree(root: Path) -> list[str]:
    errors: list[str] = []
    files = repository_files(root)
    manifest, manifest_errors = load_manifest(root)
    errors.extend(manifest_errors)
    destinations: set[str] = set()
    ported: set[str] = set()
    if manifest is not None:
        manifest_result, destinations, ported = validate_manifest(manifest)
        errors.extend(manifest_result)

    required = BASELINE_PATHS | GOVERNANCE_PATHS
    missing = sorted(required - files)
    extra = sorted(files - (BASELINE_PATHS | destinations))
    missing_ported = sorted(ported - files)
    if missing:
        errors.append(f"missing required paths: {', '.join(missing)}")
    if extra:
        errors.append(f"paths outside public allowlist: {', '.join(extra)}")
    if missing_ported:
        errors.append(f"manifest marks missing paths as ported: {', '.join(missing_ported)}")

    for relative in sorted(files):
        path = root / relative
        if path.is_symlink():
            errors.append(f"symlink is not allowed: {relative}")
            continue
        lower = relative.casefold()
        if any(lower.endswith(suffix) for suffix in FORBIDDEN_SUFFIXES):
            errors.append(f"forbidden file type: {relative}")
        if path.stat().st_size > MAX_FILE_BYTES:
            errors.append(f"file exceeds review size limit: {relative}")
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            errors.append(f"non-text public file: {relative}")
            continue
        for label, pattern in FORBIDDEN_CONTENT.items():
            if pattern.search(content):
                errors.append(f"{label} marker found: {relative}")
    return errors


def validate_repository(root: Path, *, require_clean: bool) -> list[str]:
    errors: list[str] = []
    branch = git(root, "branch", "--show-current")
    branch_name = branch.stdout.strip()
    if branch.returncode or not (
        branch_name == "main" or branch_name.startswith("agent/") or branch_name.startswith("codex/")
    ):
        errors.append("branch must be main or use an approved feature prefix")
    origin = git(root, "remote", "get-url", "origin")
    if origin.returncode or origin.stdout.strip() != EXPECTED_ORIGIN:
        errors.append("origin does not match the public repository")
    roots = git(root, "rev-list", "--max-parents=0", "HEAD")
    root_commits = [line for line in roots.stdout.splitlines() if line]
    if roots.returncode or root_commits != [EXPECTED_ROOT_COMMIT]:
        errors.append("independent clean-history root commit changed")
    if require_clean:
        status = git(root, "status", "--porcelain")
        if status.returncode or status.stdout.strip():
            errors.append("working tree must be clean for repository-phase validation")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--phase",
        choices=("working-tree", "repository", "pre-commit", "post-commit"),
        default="working-tree",
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    errors = validate_tree(root)
    errors.extend(
        validate_repository(
            root,
            require_clean=args.phase in {"repository", "post-commit"},
        )
    )
    if errors:
        for error in errors:
            print(f"BLOCK: {error}")
        return 1
    print(f"PASS: public repository safety validation ({args.phase})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
