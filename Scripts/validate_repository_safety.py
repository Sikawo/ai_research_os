#!/usr/bin/env python3
"""Validate the public repository tree, transfer manifest, and Git boundary."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path, PurePosixPath
from typing import Any, Mapping


BASELINE_PATHS = {
    ".github/dependabot.yml",
    ".github/workflows/codeql.yml",
    ".gitattributes",
    ".gitignore",
    "AGENTS.md",
    "AI_SAFE.md",
    "HANDOFF.md",
    "LICENSE",
    "README.md",
    "REPO_PROFILE.md",
    "Scripts/validate_repository_safety.py",
    "config/autonomous_delivery.json",
    "manifests/phase6a_transfer_allowlist.yaml",
    "tests/test_repository_safety.py",
    "tests/test_workflow_security.py",
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
EXPECTED_GITHUB_REPOSITORY = "Sikawo/ai_research_os"
EXPECTED_ROOT_COMMIT = "89c16ee682ea8aec910e982130e236a281df924e"
EXPECTED_TRANSFER_COUNT = 171
EXPECTED_PORTED_COUNT = 40
PHASE12_MANIFEST_PATH = "manifests/phase12_review_tools_allowlist.yaml"
PHASE12_MANIFEST_ID = "phase12a-gated-sprint-public-plugin"
PHASE12_SOURCE_COMMIT = "d1fc6462fcc5dbdafb527d4ee318d12f84b65a1f"
PHASE12_TARGET_BASE = "e09dd53414d6c1bab9c70e8294808e51af3c70ba"
PHASE12_EXPECTED_TRANSFER_COUNT = 89
PHASE12_EXPECTED_TARGET_COUNT = 97
PHASE12_EXPECTED_INTEGRATION_PATHS = {
    ".agents/plugins/marketplace.json",
    ".github/workflows/gated-sprint-tests.yml",
    "README.md",
    "Scripts/validate_repository_safety.py",
    PHASE12_MANIFEST_PATH,
    "plugins/gated-sprint/.codex-plugin/plugin.json",
    "tests/test_phase12_review_tools.py",
    "tests/test_repository_safety.py",
}
PHASE12B_MANIFEST_PATH = "manifests/phase12b_review_tools_allowlist.yaml"
PHASE12B_MANIFEST_ID = "phase12b-review-tools-public-plugin"
PHASE12B_SOURCE_COMMIT = "d1fc6462fcc5dbdafb527d4ee318d12f84b65a1f"
PHASE12B_TARGET_BASE = "2b807abdfe7a841c489d4c0309f50252cc117ed1"
PHASE12B_EXPECTED_TRANSFER_COUNT = 102
PHASE12B_EXPECTED_TARGET_COUNT = 110
PHASE12B_CLASSIFICATION_SHA256 = (
    "5e74c36142b32876b1fdc1c7030ae05f4b700d7e32aebc200294acab68d90a7d"
)
PHASE12B_EXPECTED_INTEGRATION_PATHS = {
    ".agents/plugins/marketplace.json",
    ".github/workflows/review-tools-tests.yml",
    "README.md",
    "Scripts/validate_repository_safety.py",
    PHASE12B_MANIFEST_PATH,
    "plugins/review-tools/.codex-plugin/plugin.json",
    "tests/test_phase12b_review_tools.py",
    "tests/test_repository_safety.py",
}
PHASE13_MANIFEST_PATH = "manifests/phase13_research_workflows_allowlist.yaml"
PHASE13_MANIFEST_ID = "phase13-research-workflows-public-plugin"
PHASE13_SOURCE_COMMIT = "d1fc6462fcc5dbdafb527d4ee318d12f84b65a1f"
PHASE13_TARGET_BASE = "d53d0a5c33d31115a8913b8bce050cec1a7e37a1"
PHASE13_EXPECTED_TRANSFER_COUNT = 65
PHASE13_EXPECTED_TARGET_COUNT = 74
PHASE13_CLASSIFICATION_SHA256 = (
    "9bde33d0153d3ae91fd345eb1bb77421f782fcc61b71194d1aa81f441e1bd0b6"
)
PHASE13_EXPECTED_INTEGRATION_PATHS = {
    ".agents/plugins/marketplace.json",
    ".github/workflows/research-workflows-tests.yml",
    "README.md",
    "Scripts/validate_repository_safety.py",
    PHASE13_MANIFEST_PATH,
    "plugins/research-workflows/.codex-plugin/plugin.json",
    "plugins/research-workflows/skills/evidence-mode/SKILL.md",
    "tests/test_phase13_research_workflows.py",
    "tests/test_repository_safety.py",
}
PHASE11_MANIFEST_PATH = "manifests/phase11_academic_pi_allowlist.yaml"
PHASE11_MANIFEST_ID = "phase11-academic-pi-production-contract"
PHASE11_EXPECTED_TARGET_COUNT = 19
PHASE11_EXPECTED_TARGET_PATHS = {
    "Career_Job_Agent_Framework/deployments/academic_pi/README.md",
    "Career_Job_Agent_Framework/deployments/academic_pi/cli.py",
    "Career_Job_Agent_Framework/deployments/academic_pi/config/report_defaults.yaml",
    "Career_Job_Agent_Framework/deployments/academic_pi/contracts/daily_run.md",
    "Career_Job_Agent_Framework/deployments/academic_pi/contracts/runtime.md",
    "Career_Job_Agent_Framework/deployments/academic_pi/docs/GMAIL_ALERTS.md",
    "Career_Job_Agent_Framework/deployments/academic_pi/prompts/daily_scan.md",
    "Career_Job_Agent_Framework/deployments/academic_pi/reports.py",
    "Career_Job_Agent_Framework/deployments/academic_pi/service.py",
    "HANDOFF.md",
    "Scripts/validate_repository_safety.py",
    PHASE11_MANIFEST_PATH,
    "tests/test_academic_pi_daily_contract.py",
    "tests/test_academic_pi_job_agent.py",
    "tests/test_academic_pi_production_upgrade.py",
    "tests/test_academic_pi_rss.py",
    "tests/test_academic_pi_service_correctness.py",
    "tests/test_academic_pi_service_hardening.py",
    "tests/test_repository_safety.py",
}
PHASE11A_MANIFEST_PATH = "manifests/phase11a_academic_multisource_allowlist.yaml"
PHASE11A_MANIFEST_ID = "phase11a-academic-multisource-offline-design"
PHASE11A_EXPECTED_TARGET_PATHS = {
    "Career_Job_Agent_Framework/deployments/academic_pi/README.md",
    "Career_Job_Agent_Framework/deployments/academic_pi/config/platform_adapters.yaml",
    "Career_Job_Agent_Framework/deployments/academic_pi/docs/MULTISOURCE_EXPANSION.md",
    "Career_Job_Agent_Framework/deployments/academic_pi/docs/SOURCES.md",
    "Career_Job_Agent_Framework/deployments/academic_pi/schemas/institution_source_registry.schema.json",
    "Career_Job_Agent_Framework/deployments/academic_pi/schemas/source_health.schema.json",
    "Career_Job_Agent_Framework/deployments/academic_pi/source_registry.py",
    "Career_Job_Agent_Framework/deployments/academic_pi/templates/institution_source_registry.example.yaml",
    "Scripts/validate_repository_safety.py",
    PHASE11A_MANIFEST_PATH,
    "tests/test_academic_pi_source_registry.py",
    "tests/test_repository_safety.py",
}
PHASE11A_EXPECTED_TARGET_COUNT = len(PHASE11A_EXPECTED_TARGET_PATHS)
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

PHASE12_ALLOWED_TRANSFER_MODES = ALLOWED_TRANSFER_MODES | {
    "regenerated_manifest",
}


def git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=root, check=False, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )


def effective_branch_name(git_branch: str, environment: Mapping[str, str]) -> str:
    """Return the checked-out branch or the immutable GitHub PR head branch."""

    branch_name = git_branch.strip()
    if branch_name or environment.get("GITHUB_ACTIONS") != "true":
        return branch_name
    if environment.get("GITHUB_EVENT_NAME") == "pull_request":
        return environment.get("GITHUB_HEAD_REF", "").strip()
    return ""


def is_approved_branch_name(
    branch_name: str,
    environment: Mapping[str, str],
) -> bool:
    """Return whether the branch is allowed in the current trusted context."""

    if (
        branch_name == "main"
        or branch_name.startswith("agent/")
        or branch_name.startswith("codex/")
    ):
        return True
    if not branch_name.startswith("dependabot/"):
        return False
    return (
        environment.get("GITHUB_ACTIONS") == "true"
        and environment.get("GITHUB_EVENT_NAME") == "pull_request"
        and environment.get("GITHUB_REPOSITORY") == EXPECTED_GITHUB_REPOSITORY
        and environment.get("GITHUB_ACTOR") == "dependabot[bot]"
        and environment.get("GITHUB_HEAD_REF", "").strip() == branch_name
    )


def normalize_origin_url(value: str) -> str:
    """Normalize the optional .git suffix used by GitHub checkout remotes."""

    normalized = value.strip().rstrip("/")
    if normalized.endswith(".git"):
        normalized = normalized[:-4]
    return normalized


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
    return load_json_manifest(
        root,
        "manifests/phase6a_transfer_allowlist.yaml",
        "Phase 6A transfer manifest",
    )


def load_phase12_manifest(root: Path) -> tuple[dict[str, Any] | None, list[str]]:
    return load_json_manifest(root, PHASE12_MANIFEST_PATH, "Phase 12A transfer manifest")


def load_phase12b_manifest(root: Path) -> tuple[dict[str, Any] | None, list[str]]:
    return load_json_manifest(root, PHASE12B_MANIFEST_PATH, "Phase 12B transfer manifest")


def load_phase13_manifest(root: Path) -> tuple[dict[str, Any] | None, list[str]]:
    return load_json_manifest(root, PHASE13_MANIFEST_PATH, "Phase 13 transfer manifest")


def load_phase11_manifest(root: Path) -> tuple[dict[str, Any] | None, list[str]]:
    return load_json_manifest(root, PHASE11_MANIFEST_PATH, "Phase 11 allowlist manifest")


def load_phase11a_manifest(root: Path) -> tuple[dict[str, Any] | None, list[str]]:
    return load_json_manifest(root, PHASE11A_MANIFEST_PATH, "Phase 11A allowlist manifest")


def phase12b_classification_sha256(
    transfers: list[Any], excluded_source_paths: set[str]
) -> str:
    """Return the canonical digest for the reviewed Phase 12B classification."""
    lines = []
    for transfer in transfers:
        if not isinstance(transfer, dict):
            lines.append(f"invalid\t{type(transfer).__name__}")
            continue
        lines.append(
            f"{transfer.get('transfer_mode')}\t{transfer.get('source_path')}\t"
            f"{transfer.get('destination_path')}"
        )
    lines.extend(f"excluded\t{path}" for path in excluded_source_paths)
    payload = "\n".join(sorted(lines)) + "\n"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_json_manifest(
    root: Path,
    relative_path: str,
    label: str,
) -> tuple[dict[str, Any] | None, list[str]]:
    path = root / relative_path
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, [f"invalid {label}: {exc}"]
    if not isinstance(value, dict):
        return None, [f"{label} must be an object"]
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


def validate_phase12_manifest(
    manifest: dict[str, Any],
) -> tuple[list[str], set[str], set[str]]:
    errors: list[str] = []
    if manifest.get("schema_version") != 1:
        errors.append("Phase 12A manifest schema_version must be 1")
    if manifest.get("manifest_id") != PHASE12_MANIFEST_ID:
        errors.append("unexpected Phase 12A manifest id")
    if manifest.get("status") != "ported_offline":
        errors.append("Phase 12A manifest must be ported_offline")
    if manifest.get("deny_by_default") is not True:
        errors.append("Phase 12A manifest must deny by default")
    if manifest.get("license") != "Apache-2.0":
        errors.append("Phase 12A manifest license must be Apache-2.0")
    if manifest.get("expected_transfer_count") != PHASE12_EXPECTED_TRANSFER_COUNT:
        errors.append(
            f"Phase 12A expected_transfer_count must be {PHASE12_EXPECTED_TRANSFER_COUNT}"
        )
    if manifest.get("expected_target_path_count") != PHASE12_EXPECTED_TARGET_COUNT:
        errors.append(
            f"Phase 12A expected_target_path_count must be {PHASE12_EXPECTED_TARGET_COUNT}"
        )

    target = manifest.get("target")
    if not isinstance(target, dict) or target.get("repository") != "Sikawo/ai_research_os":
        errors.append("Phase 12A target repository is invalid")
    elif target.get("base_commit") != PHASE12_TARGET_BASE:
        errors.append("Phase 12A target base commit is invalid")

    sources = manifest.get("sources")
    source = sources.get("gated_sprint_v2_reviewed_package") if isinstance(sources, dict) else None
    if not isinstance(source, dict):
        errors.append("Phase 12A reviewed source is missing")
        sources = {}
    else:
        if source.get("repository") != "Sikawo/personal_research_brain":
            errors.append("Phase 12A source repository is invalid")
        if source.get("commit") != PHASE12_SOURCE_COMMIT:
            errors.append("Phase 12A source commit is invalid")
        if source.get("package_root") != "Application_Review_OS/gated_sprint/v2":
            errors.append("Phase 12A package root is invalid")

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
    rules = manifest.get("rules")
    if not isinstance(rules, dict):
        errors.append("Phase 12A rules must be an object")
    else:
        for name, expected in required_rules.items():
            if rules.get(name) is not expected:
                errors.append(f"Phase 12A rule {name} must be {expected!r}")

    integration_value = manifest.get("integration_paths")
    integration_paths = (
        set(integration_value)
        if isinstance(integration_value, list)
        and all(is_safe_relative_path(value) for value in integration_value)
        else set()
    )
    if integration_paths != PHASE12_EXPECTED_INTEGRATION_PATHS:
        errors.append("Phase 12A integration paths do not match the reviewed scope")

    allowed_value = manifest.get("allowed_target_paths")
    allowed_targets = (
        set(allowed_value)
        if isinstance(allowed_value, list)
        and all(is_safe_relative_path(value) for value in allowed_value)
        else set()
    )
    if len(allowed_targets) != PHASE12_EXPECTED_TARGET_COUNT:
        errors.append(
            f"Phase 12A must allow {PHASE12_EXPECTED_TARGET_COUNT} exact target paths; "
            f"found {len(allowed_targets)}"
        )

    transfers = manifest.get("transfers")
    if not isinstance(transfers, list):
        return errors + ["Phase 12A transfers must be a list"], allowed_targets, set()
    if len(transfers) != PHASE12_EXPECTED_TRANSFER_COUNT:
        errors.append(
            f"Phase 12A manifest must contain {PHASE12_EXPECTED_TRANSFER_COUNT} transfers; "
            f"found {len(transfers)}"
        )

    source_paths: set[str] = set()
    destinations: set[str] = set()
    mode_counts: dict[str, int] = {}
    for index, transfer in enumerate(transfers):
        label = f"Phase 12A transfer[{index}]"
        if not isinstance(transfer, dict):
            errors.append(f"{label} must be an object")
            continue
        source_path = transfer.get("source_path")
        destination_path = transfer.get("destination_path")
        mode = transfer.get("transfer_mode")
        if transfer.get("source_id") != "gated_sprint_v2_reviewed_package":
            errors.append(f"{label} has unknown source_id")
        if transfer.get("source_commit") != PHASE12_SOURCE_COMMIT:
            errors.append(f"{label} source_commit is invalid")
        if not is_safe_relative_path(source_path) or not str(source_path).startswith(
            "Application_Review_OS/gated_sprint/v2/"
        ):
            errors.append(f"{label} has unsafe source_path")
        if not is_safe_relative_path(destination_path) or not str(destination_path).startswith(
            "plugins/gated-sprint/skills/gated-sprint/"
        ):
            errors.append(f"{label} has unsafe destination_path")
        if mode not in PHASE12_ALLOWED_TRANSFER_MODES:
            errors.append(f"{label} has unsupported transfer_mode")
        if transfer.get("phase") != "12A":
            errors.append(f"{label} has unsupported phase")
        if transfer.get("status") != "ported_offline":
            errors.append(f"{label} must be ported_offline")
        if isinstance(source_path, str):
            if source_path in source_paths:
                errors.append(f"duplicate Phase 12A source path: {source_path}")
            source_paths.add(source_path)
        if isinstance(destination_path, str):
            if destination_path in destinations:
                errors.append(f"duplicate Phase 12A destination path: {destination_path}")
            destinations.add(destination_path)
        if isinstance(mode, str):
            mode_counts[mode] = mode_counts.get(mode, 0) + 1

    expected_modes = {
        "exact_copy": 85,
        "adapted_public_copy": 3,
        "regenerated_manifest": 1,
    }
    if mode_counts != expected_modes:
        errors.append(f"Phase 12A transfer modes must be {expected_modes!r}")
    if allowed_targets != destinations | integration_paths:
        errors.append("Phase 12A allowed targets must equal transfers plus integration paths")
    return errors, allowed_targets, destinations


def validate_phase12b_manifest(
    manifest: dict[str, Any],
) -> tuple[list[str], set[str], set[str]]:
    errors: list[str] = []
    if manifest.get("schema_version") != 1:
        errors.append("Phase 12B manifest schema_version must be 1")
    if manifest.get("manifest_id") != PHASE12B_MANIFEST_ID:
        errors.append("unexpected Phase 12B manifest id")
    if manifest.get("status") != "ported_offline":
        errors.append("Phase 12B manifest must be ported_offline")
    if manifest.get("deny_by_default") is not True:
        errors.append("Phase 12B manifest must deny by default")
    if manifest.get("license") != "Apache-2.0":
        errors.append("Phase 12B manifest license must be Apache-2.0")
    if manifest.get("expected_transfer_count") != PHASE12B_EXPECTED_TRANSFER_COUNT:
        errors.append(
            f"Phase 12B expected_transfer_count must be {PHASE12B_EXPECTED_TRANSFER_COUNT}"
        )
    if manifest.get("expected_target_path_count") != PHASE12B_EXPECTED_TARGET_COUNT:
        errors.append(
            f"Phase 12B expected_target_path_count must be {PHASE12B_EXPECTED_TARGET_COUNT}"
        )
    if manifest.get("classification_sha256") != PHASE12B_CLASSIFICATION_SHA256:
        errors.append("Phase 12B classification_sha256 does not match the reviewed inventory")

    target = manifest.get("target")
    if not isinstance(target, dict) or target.get("repository") != "Sikawo/ai_research_os":
        errors.append("Phase 12B target repository is invalid")
    elif target.get("base_commit") != PHASE12B_TARGET_BASE:
        errors.append("Phase 12B target base commit is invalid")

    sources = manifest.get("sources")
    source = (
        sources.get("phase12b_review_tools_classified")
        if isinstance(sources, dict)
        else None
    )
    if not isinstance(source, dict):
        errors.append("Phase 12B classified source is missing")
    else:
        expected_source = {
            "repository": "Sikawo/personal_research_brain",
            "commit": PHASE12B_SOURCE_COMMIT,
            "candidate_count": 113,
            "exact_copy_count": 16,
            "adapted_public_copy_count": 86,
            "excluded_count": 11,
        }
        for name, expected in expected_source.items():
            if source.get(name) != expected:
                errors.append(f"Phase 12B source {name} must be {expected!r}")

    required_rules = {
        "exact_paths_only": True,
        "synthetic_fixtures_only": True,
        "copy_git_history": False,
        "copy_private_values": False,
        "copy_runtime_state": False,
        "copy_connector_bindings": False,
        "copy_scheduled_tasks": False,
        "live_cutover": False,
        "sprint_authority_owner": "plugins/gated-sprint/skills/gated-sprint",
    }
    rules = manifest.get("rules")
    if not isinstance(rules, dict):
        errors.append("Phase 12B rules must be an object")
    else:
        for name, expected in required_rules.items():
            if rules.get(name) != expected:
                errors.append(f"Phase 12B rule {name} must be {expected!r}")

    integration_value = manifest.get("integration_paths")
    integration_paths = (
        set(integration_value)
        if isinstance(integration_value, list)
        and all(is_safe_relative_path(value) for value in integration_value)
        else set()
    )
    if integration_paths != PHASE12B_EXPECTED_INTEGRATION_PATHS:
        errors.append("Phase 12B integration paths do not match the reviewed scope")

    allowed_value = manifest.get("allowed_target_paths")
    allowed_targets = (
        set(allowed_value)
        if isinstance(allowed_value, list)
        and all(is_safe_relative_path(value) for value in allowed_value)
        else set()
    )
    if len(allowed_targets) != PHASE12B_EXPECTED_TARGET_COUNT:
        errors.append(
            f"Phase 12B must allow {PHASE12B_EXPECTED_TARGET_COUNT} exact target paths; "
            f"found {len(allowed_targets)}"
        )

    excluded_value = manifest.get("excluded_source_paths")
    excluded = (
        set(excluded_value)
        if isinstance(excluded_value, list)
        and all(is_safe_relative_path(value) for value in excluded_value)
        else set()
    )
    if len(excluded) != 11:
        errors.append("Phase 12B must record exactly 11 excluded source paths")

    transfers = manifest.get("transfers")
    if not isinstance(transfers, list):
        return errors + ["Phase 12B transfers must be a list"], allowed_targets, set()
    if len(transfers) != PHASE12B_EXPECTED_TRANSFER_COUNT:
        errors.append(
            f"Phase 12B manifest must contain {PHASE12B_EXPECTED_TRANSFER_COUNT} transfers; "
            f"found {len(transfers)}"
        )

    source_paths: set[str] = set()
    destinations: set[str] = set()
    mode_counts: dict[str, int] = {}
    for index, transfer in enumerate(transfers):
        label = f"Phase 12B transfer[{index}]"
        if not isinstance(transfer, dict):
            errors.append(f"{label} must be an object")
            continue
        source_path = transfer.get("source_path")
        destination_path = transfer.get("destination_path")
        mode = transfer.get("transfer_mode")
        if transfer.get("source_id") != "phase12b_review_tools_classified":
            errors.append(f"{label} has unknown source_id")
        if transfer.get("source_commit") != PHASE12B_SOURCE_COMMIT:
            errors.append(f"{label} source_commit is invalid")
        if not is_safe_relative_path(source_path):
            errors.append(f"{label} has unsafe source_path")
        if not is_safe_relative_path(destination_path) or not str(destination_path).startswith(
            "plugins/review-tools/skills/"
        ):
            errors.append(f"{label} has unsafe destination_path")
        if mode not in {"exact_copy", "adapted_public_copy"}:
            errors.append(f"{label} has unsupported transfer_mode")
        if transfer.get("phase") != "12B":
            errors.append(f"{label} has unsupported phase")
        if transfer.get("status") != "ported_offline":
            errors.append(f"{label} must be ported_offline")
        if isinstance(source_path, str):
            if source_path in source_paths:
                errors.append(f"duplicate Phase 12B source path: {source_path}")
            if source_path in excluded:
                errors.append(f"excluded Phase 12B source was transferred: {source_path}")
            source_paths.add(source_path)
        if isinstance(destination_path, str):
            if destination_path in destinations:
                errors.append(f"duplicate Phase 12B destination path: {destination_path}")
            destinations.add(destination_path)
        if isinstance(mode, str):
            mode_counts[mode] = mode_counts.get(mode, 0) + 1

    expected_modes = {"exact_copy": 16, "adapted_public_copy": 86}
    if mode_counts != expected_modes:
        errors.append(f"Phase 12B transfer modes must be {expected_modes!r}")
    classification_digest = phase12b_classification_sha256(transfers, excluded)
    if classification_digest != PHASE12B_CLASSIFICATION_SHA256:
        errors.append("Phase 12B source classification does not match the reviewed inventory")
    if allowed_targets != destinations | integration_paths:
        errors.append("Phase 12B allowed targets must equal transfers plus integration paths")
    return errors, allowed_targets, destinations


def validate_phase13_manifest(
    manifest: dict[str, Any],
) -> tuple[list[str], set[str], set[str]]:
    errors: list[str] = []
    if manifest.get("schema_version") != 1:
        errors.append("Phase 13 manifest schema_version must be 1")
    if manifest.get("manifest_id") != PHASE13_MANIFEST_ID:
        errors.append("unexpected Phase 13 manifest id")
    if manifest.get("status") != "ported_offline":
        errors.append("Phase 13 manifest must be ported_offline")
    if manifest.get("deny_by_default") is not True:
        errors.append("Phase 13 manifest must deny by default")
    if manifest.get("license") != "Apache-2.0":
        errors.append("Phase 13 manifest license must be Apache-2.0")
    if manifest.get("expected_transfer_count") != PHASE13_EXPECTED_TRANSFER_COUNT:
        errors.append(
            f"Phase 13 expected_transfer_count must be {PHASE13_EXPECTED_TRANSFER_COUNT}"
        )
    if manifest.get("expected_target_path_count") != PHASE13_EXPECTED_TARGET_COUNT:
        errors.append(
            f"Phase 13 expected_target_path_count must be {PHASE13_EXPECTED_TARGET_COUNT}"
        )
    if manifest.get("classification_sha256") != PHASE13_CLASSIFICATION_SHA256:
        errors.append("Phase 13 classification_sha256 does not match the reviewed inventory")

    target = manifest.get("target")
    if not isinstance(target, dict) or target.get("repository") != "Sikawo/ai_research_os":
        errors.append("Phase 13 target repository is invalid")
    elif target.get("base_commit") != PHASE13_TARGET_BASE:
        errors.append("Phase 13 target base commit is invalid")

    sources = manifest.get("sources")
    source = (
        sources.get("phase13_research_workflows_classified")
        if isinstance(sources, dict)
        else None
    )
    if not isinstance(source, dict):
        errors.append("Phase 13 classified source is missing")
    else:
        expected_source = {
            "repository": "Sikawo/personal_research_brain",
            "commit": PHASE13_SOURCE_COMMIT,
            "candidate_count": 70,
            "exact_copy_count": 9,
            "adapted_public_copy_count": 56,
            "excluded_count": 5,
        }
        for name, expected in expected_source.items():
            if source.get(name) != expected:
                errors.append(f"Phase 13 source {name} must be {expected!r}")

    required_rules = {
        "exact_paths_only": True,
        "synthetic_fixtures_only": True,
        "offline_first": True,
        "dry_run_by_default": True,
        "external_network_in_tests": False,
        "automatic_pdf_access": False,
        "automatic_purchase": False,
        "copy_git_history": False,
        "copy_private_values": False,
        "copy_runtime_state": False,
        "copy_connector_bindings": False,
        "copy_scheduled_tasks": False,
        "live_cutover": False,
    }
    rules = manifest.get("rules")
    if not isinstance(rules, dict):
        errors.append("Phase 13 rules must be an object")
    else:
        for name, expected in required_rules.items():
            if rules.get(name) != expected:
                errors.append(f"Phase 13 rule {name} must be {expected!r}")

    integration_value = manifest.get("integration_paths")
    integration_paths = (
        set(integration_value)
        if isinstance(integration_value, list)
        and all(is_safe_relative_path(value) for value in integration_value)
        else set()
    )
    if integration_paths != PHASE13_EXPECTED_INTEGRATION_PATHS:
        errors.append("Phase 13 integration paths do not match the reviewed scope")

    allowed_value = manifest.get("allowed_target_paths")
    allowed_targets = (
        set(allowed_value)
        if isinstance(allowed_value, list)
        and all(is_safe_relative_path(value) for value in allowed_value)
        else set()
    )
    if len(allowed_targets) != PHASE13_EXPECTED_TARGET_COUNT:
        errors.append(
            f"Phase 13 must allow {PHASE13_EXPECTED_TARGET_COUNT} exact target paths; "
            f"found {len(allowed_targets)}"
        )

    excluded_value = manifest.get("excluded_source_paths")
    excluded = (
        set(excluded_value)
        if isinstance(excluded_value, list)
        and all(is_safe_relative_path(value) for value in excluded_value)
        else set()
    )
    if len(excluded) != 5:
        errors.append("Phase 13 must record exactly 5 excluded source paths")

    transfers = manifest.get("transfers")
    if not isinstance(transfers, list):
        return errors + ["Phase 13 transfers must be a list"], allowed_targets, set()
    if len(transfers) != PHASE13_EXPECTED_TRANSFER_COUNT:
        errors.append(
            f"Phase 13 manifest must contain {PHASE13_EXPECTED_TRANSFER_COUNT} transfers; "
            f"found {len(transfers)}"
        )

    source_paths: set[str] = set()
    destinations: set[str] = set()
    mode_counts: dict[str, int] = {}
    for index, transfer in enumerate(transfers):
        label = f"Phase 13 transfer[{index}]"
        if not isinstance(transfer, dict):
            errors.append(f"{label} must be an object")
            continue
        source_path = transfer.get("source_path")
        destination_path = transfer.get("destination_path")
        mode = transfer.get("transfer_mode")
        if transfer.get("source_id") != "phase13_research_workflows_classified":
            errors.append(f"{label} has unknown source_id")
        if transfer.get("source_commit") != PHASE13_SOURCE_COMMIT:
            errors.append(f"{label} source_commit is invalid")
        if not is_safe_relative_path(source_path):
            errors.append(f"{label} has unsafe source_path")
        if not is_safe_relative_path(destination_path) or not str(destination_path).startswith(
            "plugins/research-workflows/skills/"
        ):
            errors.append(f"{label} has unsafe destination_path")
        if mode not in {"exact_copy", "adapted_public_copy"}:
            errors.append(f"{label} has unsupported transfer_mode")
        if transfer.get("phase") != "13":
            errors.append(f"{label} has unsupported phase")
        if transfer.get("status") != "ported_offline":
            errors.append(f"{label} must be ported_offline")
        if isinstance(source_path, str):
            if source_path in source_paths:
                errors.append(f"duplicate Phase 13 source path: {source_path}")
            if source_path in excluded:
                errors.append(f"excluded Phase 13 source was transferred: {source_path}")
            source_paths.add(source_path)
        if isinstance(destination_path, str):
            if destination_path in destinations:
                errors.append(f"duplicate Phase 13 destination path: {destination_path}")
            destinations.add(destination_path)
        if isinstance(mode, str):
            mode_counts[mode] = mode_counts.get(mode, 0) + 1

    expected_modes = {"exact_copy": 9, "adapted_public_copy": 56}
    if mode_counts != expected_modes:
        errors.append(f"Phase 13 transfer modes must be {expected_modes!r}")
    classification_digest = phase12b_classification_sha256(transfers, excluded)
    if classification_digest != PHASE13_CLASSIFICATION_SHA256:
        errors.append("Phase 13 source classification does not match the reviewed inventory")
    if allowed_targets != destinations | integration_paths:
        errors.append("Phase 13 allowed targets must equal transfers plus integration paths")
    return errors, allowed_targets, destinations


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

    phase12_manifest, phase12_load_errors = load_phase12_manifest(root)
    errors.extend(phase12_load_errors)
    phase12_allowed: set[str] = set()
    phase12_ported: set[str] = set()
    if phase12_manifest is not None:
        phase12_errors, phase12_allowed, phase12_ported = validate_phase12_manifest(
            phase12_manifest
        )
        errors.extend(phase12_errors)

        source = phase12_manifest.get("sources", {}).get(
            "gated_sprint_v2_reviewed_package", {}
        )
        package_manifest_path = (
            root
            / "plugins"
            / "gated-sprint"
            / "skills"
            / "gated-sprint"
            / "skill-package-manifest.json"
        )
        try:
            package_manifest = json.loads(package_manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"invalid GatedSprint package manifest: {exc}")
        else:
            if not isinstance(source, dict) or source.get(
                "destination_package_hash"
            ) != package_manifest.get("package_hash"):
                errors.append("GatedSprint destination package hash does not match Phase 12A")
            if package_manifest.get("file_count") != 88:
                errors.append("GatedSprint package manifest must contain 88 files")

    phase12b_manifest, phase12b_load_errors = load_phase12b_manifest(root)
    errors.extend(phase12b_load_errors)
    phase12b_allowed: set[str] = set()
    phase12b_ported: set[str] = set()
    if phase12b_manifest is not None:
        phase12b_errors, phase12b_allowed, phase12b_ported = validate_phase12b_manifest(
            phase12b_manifest
        )
        errors.extend(phase12b_errors)

    phase13_manifest, phase13_load_errors = load_phase13_manifest(root)
    errors.extend(phase13_load_errors)
    phase13_allowed: set[str] = set()
    phase13_ported: set[str] = set()
    if phase13_manifest is not None:
        phase13_errors, phase13_allowed, phase13_ported = validate_phase13_manifest(
            phase13_manifest
        )
        errors.extend(phase13_errors)

    phase11_manifest, phase11_load_errors = load_phase11_manifest(root)
    errors.extend(phase11_load_errors)
    phase11_allowed: set[str] = set()
    if phase11_manifest is not None:
        phase11_errors, phase11_allowed = validate_phase11_manifest(
            phase11_manifest
        )
        errors.extend(phase11_errors)

    phase11a_manifest, phase11a_load_errors = load_phase11a_manifest(root)
    errors.extend(phase11a_load_errors)
    phase11a_allowed: set[str] = set()
    if phase11a_manifest is not None:
        phase11a_errors, phase11a_allowed = validate_phase11a_manifest(
            phase11a_manifest
        )
        errors.extend(phase11a_errors)

    required = (
        BASELINE_PATHS
        | GOVERNANCE_PATHS
        | phase12_allowed
        | phase12b_allowed
        | phase13_allowed
        | phase11_allowed
        | phase11a_allowed
    )
    missing = sorted(required - files)
    extra = sorted(
        files
        - (
            BASELINE_PATHS
            | destinations
            | phase12_allowed
            | phase12b_allowed
            | phase13_allowed
            | phase11_allowed
            | phase11a_allowed
        )
    )
    missing_ported = sorted(
        (ported | phase12_ported | phase12b_ported | phase13_ported) - files
    )
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


def validate_phase11_manifest(
    manifest: dict[str, Any],
) -> tuple[list[str], set[str]]:
    """Validate the deny-by-default native Phase 11 development boundary."""

    errors: list[str] = []
    if manifest.get("schema_version") != 1:
        errors.append("Phase 11 manifest schema_version must be 1")
    if manifest.get("manifest_id") != PHASE11_MANIFEST_ID:
        errors.append("unexpected Phase 11 manifest id")
    if manifest.get("status") != "approved_for_offline_development":
        errors.append("Phase 11 manifest must be approved_for_offline_development")
    if manifest.get("deny_by_default") is not True:
        errors.append("Phase 11 manifest must deny by default")
    if manifest.get("license") != "Apache-2.0":
        errors.append("Phase 11 manifest license must be Apache-2.0")
    if manifest.get("expected_target_path_count") != PHASE11_EXPECTED_TARGET_COUNT:
        errors.append(
            f"Phase 11 expected_target_path_count must be {PHASE11_EXPECTED_TARGET_COUNT}"
        )

    rules = manifest.get("rules")
    expected_rules = {
        "exact_paths_only": True,
        "synthetic_tests_only": True,
        "private_values": False,
        "resource_bindings": False,
        "runtime_changes": False,
        "scheduled_task_changes": False,
        "live_cutover": False,
    }
    if not isinstance(rules, dict):
        errors.append("Phase 11 manifest rules must be an object")
    else:
        for name, expected in expected_rules.items():
            if rules.get(name) is not expected:
                errors.append(f"Phase 11 rule {name} must be {expected!r}")

    raw_paths = manifest.get("allowed_target_paths")
    if not isinstance(raw_paths, list):
        return errors + ["Phase 11 allowed_target_paths must be a list"], set()
    allowed = {str(path) for path in raw_paths if isinstance(path, str)}
    if len(allowed) != len(raw_paths):
        errors.append("Phase 11 allowed_target_paths must be unique strings")
    if any(not is_safe_relative_path(path) for path in allowed):
        errors.append("Phase 11 allowed_target_paths contains an unsafe path")
    if allowed != PHASE11_EXPECTED_TARGET_PATHS:
        errors.append("Phase 11 allowed targets do not match the reviewed scope")
    return errors, allowed


def validate_phase11a_manifest(
    manifest: dict[str, Any],
) -> tuple[list[str], set[str]]:
    """Validate the deny-by-default Phase 11A offline design boundary."""

    errors: list[str] = []
    if manifest.get("schema_version") != 1:
        errors.append("Phase 11A manifest schema_version must be 1")
    if manifest.get("manifest_id") != PHASE11A_MANIFEST_ID:
        errors.append("unexpected Phase 11A manifest id")
    if manifest.get("status") != "approved_for_offline_development":
        errors.append("Phase 11A manifest must be approved_for_offline_development")
    if manifest.get("deny_by_default") is not True:
        errors.append("Phase 11A manifest must deny by default")
    if manifest.get("license") != "Apache-2.0":
        errors.append("Phase 11A manifest license must be Apache-2.0")
    if manifest.get("expected_target_path_count") != PHASE11A_EXPECTED_TARGET_COUNT:
        errors.append(
            f"Phase 11A expected_target_path_count must be {PHASE11A_EXPECTED_TARGET_COUNT}"
        )

    expected_rules = {
        "exact_paths_only": True,
        "synthetic_tests_only": True,
        "private_values": False,
        "resource_bindings": False,
        "network_fetches": False,
        "gmail_reads": False,
        "runtime_changes": False,
        "scheduled_task_changes": False,
        "live_cutover": False,
    }
    rules = manifest.get("rules")
    if not isinstance(rules, dict):
        errors.append("Phase 11A manifest rules must be an object")
    else:
        for name, expected in expected_rules.items():
            if rules.get(name) is not expected:
                errors.append(f"Phase 11A rule {name} must be {expected!r}")

    raw_paths = manifest.get("allowed_target_paths")
    if not isinstance(raw_paths, list):
        return errors + ["Phase 11A allowed_target_paths must be a list"], set()
    allowed = {str(path) for path in raw_paths if isinstance(path, str)}
    if len(allowed) != len(raw_paths):
        errors.append("Phase 11A allowed_target_paths must be unique strings")
    if any(not is_safe_relative_path(path) for path in allowed):
        errors.append("Phase 11A allowed_target_paths contains an unsafe path")
    if allowed != PHASE11A_EXPECTED_TARGET_PATHS:
        errors.append("Phase 11A allowed targets do not match the reviewed scope")
    return errors, allowed


def validate_repository(
    root: Path,
    *,
    require_clean: bool,
    environment: Mapping[str, str] | None = None,
) -> list[str]:
    errors: list[str] = []
    environment = os.environ if environment is None else environment
    branch = git(root, "branch", "--show-current")
    branch_name = effective_branch_name(branch.stdout, environment)
    if branch.returncode or not is_approved_branch_name(branch_name, environment):
        errors.append("branch must be main or use an approved trusted prefix")
    origin = git(root, "remote", "get-url", "origin")
    if origin.returncode or normalize_origin_url(origin.stdout) != normalize_origin_url(EXPECTED_ORIGIN):
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
