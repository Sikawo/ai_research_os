#!/usr/bin/env python3
"""Fail-closed dry-run checks for bounded autonomous delivery.

This helper only reads repository state and review evidence. It never stages,
commits, pushes, opens a pull request, merges, deletes, cleans, or rewrites Git
history.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO


READY = "READY"
BLOCK = "BLOCK"

POLICY_REQUIRED_FIELDS = {
    "schema_version",
    "repository",
    "origin_url",
    "github_repository",
    "enabled",
    "max_git_level",
    "base_branch",
    "allowed_branch_prefixes",
    "allowed_task_classes",
    "protected_content_mode",
    "blocked_path_patterns",
    "required_validation_commands",
    "policy_documents",
    "final_review_command",
    "draft_pr_allowed",
    "merge_allowed",
    "forbid_force_push",
    "forbid_branch_delete",
}

TASK_REQUIRED_FIELDS = {
    "schema_version",
    "task_id",
    "repository",
    "task_class",
    "change_class",
    "requested_git_level",
    "base_branch",
    "branch",
    "allowed_paths",
    "allowed_new_files",
    "review_required_paths",
    "forbidden_paths",
    "protected_content_mode",
    "validation_commands",
    "commit_message",
    "pr_title",
    "pr_body_file",
    "existing_draft_pr_number",
}

REVIEW_REQUIRED_FIELDS = {
    "schema_version",
    "task_id",
    "verdict",
    "reviewed_paths",
    "reviewed_snapshot_sha256",
    "final_review_packet_sha256",
    "reviewed_base_commit",
    "reviewed_head_commit",
    "pr_body_path",
    "pr_body_sha256",
}

POLICY_LIST_FIELDS = {
    "allowed_branch_prefixes",
    "allowed_task_classes",
    "blocked_path_patterns",
    "required_validation_commands",
    "policy_documents",
}

TASK_LIST_FIELDS = {
    "allowed_paths",
    "allowed_new_files",
    "review_required_paths",
    "forbidden_paths",
    "validation_commands",
}

ALLOWED_TASK_CLASSES = {"documentation", "source", "tests", "config", "workflow"}
ALLOWED_CHANGE_CLASSES = {"light", "medium", "heavy"}

CORE_BLOCKED_PATH_PATTERNS = [
    ".env",
    "**/.env",
    ".DS_Store",
    "**/.DS_Store",
    "exports/**",
    "ai_artifacts/**",
    "**/*.key",
    "**/*.pem",
    "credentials/**",
    "**/credentials/**",
    "secrets/**",
    "**/secrets/**",
]

REQUIRED_PR_BODY_HEADINGS = (
    "Summary",
    "Files",
    "Validation",
    "Review",
    "Risk",
    "Rollback",
)


@dataclass(frozen=True)
class DeliveryAssessment:
    phase: str
    decision: str
    repository: str
    branch: str
    base_branch: str
    changed_paths: list[str]
    review_required_paths: list[str]
    reasons: list[str]
    proposed_commands: list[str]


def is_allowed_read_only_git(args: list[str]) -> bool:
    if not args:
        return False
    command, rest = args[0], args[1:]
    if command == "branch":
        return rest == ["--show-current"]
    if command == "status":
        return rest == ["--porcelain=v1", "-z", "--untracked-files=all"]
    if command == "remote":
        return rest == ["get-url", "origin"]
    if command == "merge-base":
        return len(rest) == 2 and all(value and not value.startswith("-") for value in rest)
    if command == "rev-parse":
        return rest == ["HEAD"]
    if command == "rev-list":
        return (
            len(rest) == 2
            and rest[0] in {"--count", "--reverse"}
            and ".." in rest[1]
            and not rest[1].startswith("-")
        )
    if command == "diff":
        return (
            len(rest) == 3
            and rest[:2] in (["--name-only", "-z"], ["--name-status", "-z"])
            and ".." in rest[2]
            and not rest[2].startswith("-")
        )
    if command == "diff-tree":
        return (
            len(rest) == 6
            and rest[:5] == ["--root", "--no-commit-id", "--name-status", "-r", "-z"]
            and bool(re.fullmatch(r"[0-9a-f]{40}", rest[5]))
        )
    return False


def run_git(repo_root: Path, args: list[str], *, binary: bool = False) -> str | bytes:
    if not is_allowed_read_only_git(args):
        raise RuntimeError(f"refusing non-read-only git command: {' '.join(args)}")
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=False,
        text=not binary,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace") if binary else result.stderr
        stdout = result.stdout.decode("utf-8", errors="replace") if binary else result.stdout
        detail = stderr.strip() or stdout.strip()
        raise RuntimeError(f"git {' '.join(args)} failed: {detail}")
    if binary:
        return result.stdout
    return result.stdout.strip()


def find_repo_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=current,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        raise RuntimeError("run inside a Git repository or pass --repo-root")
    return Path(result.stdout.strip()).resolve()


def load_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise RuntimeError(f"could not read {label} {path}: {error}") from error
    except json.JSONDecodeError as error:
        raise RuntimeError(f"invalid JSON in {label} {path}: {error}") from error
    if not isinstance(value, dict):
        raise RuntimeError(f"{label} must be a JSON object")
    return value


def require_fields(data: dict[str, Any], required: set[str], label: str) -> None:
    missing = sorted(required - data.keys())
    if missing:
        raise RuntimeError(f"{label} missing required fields: {', '.join(missing)}")
    unexpected = sorted(data.keys() - required)
    if unexpected:
        raise RuntimeError(f"{label} has unsupported fields: {', '.join(unexpected)}")


def require_string(data: dict[str, Any], field: str, label: str) -> None:
    if not isinstance(data.get(field), str) or not data[field].strip():
        raise RuntimeError(f"{label}.{field} must be a non-empty string")


def require_string_list(data: dict[str, Any], field: str, label: str, *, nonempty: bool = False) -> None:
    value = data.get(field)
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise RuntimeError(f"{label}.{field} must be a list of non-empty strings")
    if nonempty and not value:
        raise RuntimeError(f"{label}.{field} must not be empty")
    if len(value) != len(set(value)):
        raise RuntimeError(f"{label}.{field} must not contain duplicates")


def validate_relative_pattern(value: str, label: str) -> None:
    normalized = value.replace("\\", "/")
    if normalized.startswith("/") or (len(normalized) >= 2 and normalized[1] == ":"):
        raise RuntimeError(f"{label} must be repository-relative: {value}")
    if ".." in Path(normalized).parts:
        raise RuntimeError(f"{label} must not traverse parent directories: {value}")


def validate_policy(data: dict[str, Any]) -> None:
    require_fields(data, POLICY_REQUIRED_FIELDS, "policy")
    for field in (
        "repository",
        "origin_url",
        "github_repository",
        "base_branch",
        "final_review_command",
    ):
        require_string(data, field, "policy")
    for field in POLICY_LIST_FIELDS:
        require_string_list(data, field, "policy", nonempty=True)
    if data["schema_version"] != 1:
        raise RuntimeError("policy.schema_version must be 1")
    if type(data["enabled"]) is not bool:
        raise RuntimeError("policy.enabled must be a boolean")
    if type(data["max_git_level"]) is not int or not 0 <= data["max_git_level"] <= 4:
        raise RuntimeError("policy.max_git_level must be an integer from 0 through 4")
    if data["protected_content_mode"] not in {"forbidden", "explicit_exact_scope"}:
        raise RuntimeError("policy.protected_content_mode is invalid")
    if not set(data["allowed_task_classes"]) <= ALLOWED_TASK_CLASSES:
        raise RuntimeError("policy.allowed_task_classes contains an unsupported value")
    if data["draft_pr_allowed"] is not True:
        raise RuntimeError("policy.draft_pr_allowed must remain true for this contract")
    if data["merge_allowed"] is not False:
        raise RuntimeError("policy.merge_allowed must remain false")
    if data["forbid_force_push"] is not True:
        raise RuntimeError("policy.forbid_force_push must remain true")
    if data["forbid_branch_delete"] is not True:
        raise RuntimeError("policy.forbid_branch_delete must remain true")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", data["github_repository"]):
        raise RuntimeError("policy.github_repository must use owner/repository form")
    for field in ("blocked_path_patterns", "policy_documents"):
        for value in data[field]:
            validate_relative_pattern(value, f"policy.{field}")


def validate_task(data: dict[str, Any]) -> None:
    require_fields(data, TASK_REQUIRED_FIELDS, "task")
    for field in (
        "task_id",
        "repository",
        "task_class",
        "change_class",
        "base_branch",
        "branch",
        "protected_content_mode",
        "commit_message",
        "pr_title",
        "pr_body_file",
    ):
        require_string(data, field, "task")
    for field in TASK_LIST_FIELDS:
        require_string_list(
            data,
            field,
            "task",
            nonempty=field in {"allowed_paths", "forbidden_paths", "validation_commands"},
        )
    if data["schema_version"] != 1:
        raise RuntimeError("task.schema_version must be 1")
    if type(data["requested_git_level"]) is not int or not 0 <= data["requested_git_level"] <= 4:
        raise RuntimeError("task.requested_git_level must be an integer from 0 through 4")
    if data["protected_content_mode"] not in {"none", "explicit_exact_scope"}:
        raise RuntimeError("task.protected_content_mode is invalid")
    if data["task_class"] not in ALLOWED_TASK_CLASSES:
        raise RuntimeError("task.task_class is invalid")
    if data["change_class"] not in ALLOWED_CHANGE_CLASSES:
        raise RuntimeError("task.change_class is invalid")
    pr_number = data["existing_draft_pr_number"]
    if pr_number is not None and (type(pr_number) is not int or pr_number < 1):
        raise RuntimeError("task.existing_draft_pr_number must be null or a positive integer")
    for field in ("allowed_paths", "allowed_new_files", "review_required_paths", "forbidden_paths"):
        for value in data[field]:
            validate_relative_pattern(value, f"task.{field}")
    validate_relative_pattern(data["pr_body_file"], "task.pr_body_file")


def validate_review(data: dict[str, Any]) -> None:
    require_fields(data, REVIEW_REQUIRED_FIELDS, "review")
    require_string(data, "task_id", "review")
    require_string_list(data, "reviewed_paths", "review", nonempty=True)
    if data["schema_version"] != 1:
        raise RuntimeError("review.schema_version must be 1")
    if data["verdict"] not in {"APPROVE", "REQUEST_CHANGES", "BLOCK"}:
        raise RuntimeError("review.verdict is invalid")
    for field in (
        "reviewed_snapshot_sha256",
        "final_review_packet_sha256",
        "pr_body_sha256",
    ):
        value = data.get(field)
        if (
            not isinstance(value, str)
            or len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)
        ):
            raise RuntimeError(f"review.{field} must be a lowercase SHA256")
    for field in ("reviewed_base_commit", "reviewed_head_commit"):
        value = data.get(field)
        if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{40}", value):
            raise RuntimeError(f"review.{field} must be a lowercase 40-character Git SHA")
    require_string(data, "pr_body_path", "review")
    validate_relative_pattern(data["pr_body_path"], "review.pr_body_path")
    for value in data["reviewed_paths"]:
        validate_relative_pattern(value, "review.reviewed_paths")


def normalize_path(value: str) -> str:
    normalized = value.replace("\\", "/")
    return normalized[2:] if normalized.startswith("./") else normalized


def path_matches(path: str, patterns: list[str]) -> bool:
    normalized = normalize_path(path)
    for pattern in patterns:
        candidate = normalize_path(pattern)
        variants = [candidate]
        if candidate.startswith("**/"):
            variants.append(candidate[3:])
        for variant in variants:
            if variant.endswith("/**"):
                prefix = variant[:-3].rstrip("/")
                if normalized == prefix or normalized.startswith(prefix + "/"):
                    return True
            if variant.endswith("/") and normalized.startswith(variant):
                return True
            if fnmatch.fnmatchcase(normalized, variant):
                return True
    return False


def porcelain_entries(repo_root: Path) -> dict[str, str]:
    output = run_git(
        repo_root,
        ["status", "--porcelain=v1", "-z", "--untracked-files=all"],
        binary=True,
    )
    assert isinstance(output, bytes)
    records = output.split(b"\0")
    entries: dict[str, str] = {}
    index = 0
    while index < len(records):
        record = records[index]
        if not record:
            index += 1
            continue
        text = record.decode("utf-8", errors="surrogateescape")
        if len(text) < 4:
            raise RuntimeError(f"unexpected git status record: {text!r}")
        status = text[:2]
        entries[normalize_path(text[3:])] = status
        index += 1
        if "R" in status or "C" in status:
            if index >= len(records) or not records[index]:
                raise RuntimeError("git status rename/copy record is incomplete")
            entries[normalize_path(records[index].decode("utf-8", errors="surrogateescape"))] = status
            index += 1
    return entries


def porcelain_paths(repo_root: Path) -> list[str]:
    return sorted(porcelain_entries(repo_root))


def staged_and_unstaged_paths(entries: dict[str, str]) -> tuple[list[str], list[str]]:
    staged: list[str] = []
    unstaged: list[str] = []
    for path, status in entries.items():
        if status == "??":
            unstaged.append(path)
            continue
        if status[0] not in {" ", "?"}:
            staged.append(path)
        if status[1] not in {" ", "?"}:
            unstaged.append(path)
    return sorted(set(staged)), sorted(set(unstaged))


def parse_name_status(output: bytes) -> dict[str, str]:
    records = output.split(b"\0")
    entries: dict[str, str] = {}
    index = 0
    while index < len(records):
        if not records[index]:
            index += 1
            continue
        status = records[index].decode("ascii", errors="strict")
        index += 1
        path_count = 2 if status.startswith(("R", "C")) else 1
        if index + path_count > len(records):
            raise RuntimeError("git name-status output is incomplete")
        paths = [
            normalize_path(records[index + offset].decode("utf-8", errors="surrogateescape"))
            for offset in range(path_count)
        ]
        index += path_count
        for path in paths:
            entries[path] = status
    return entries


def ref_exists(repo_root: Path, ref: str) -> bool:
    result = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", ref],
        cwd=repo_root,
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0


def merge_base_sha(repo_root: Path, base_branch: str) -> str:
    remote_ref = f"origin/{base_branch}"
    base_ref = remote_ref if ref_exists(repo_root, remote_ref) else base_branch
    merge_base = run_git(repo_root, ["merge-base", base_ref, "HEAD"])
    assert isinstance(merge_base, str)
    return merge_base


def branch_scope_entries(repo_root: Path, base_branch: str) -> dict[str, str]:
    merge_base = merge_base_sha(repo_root, base_branch)
    output = run_git(repo_root, ["diff", "--name-status", "-z", f"{merge_base}..HEAD"], binary=True)
    assert isinstance(output, bytes)
    return parse_name_status(output)


def branch_scope_paths(repo_root: Path, base_branch: str) -> list[str]:
    return sorted(branch_scope_entries(repo_root, base_branch))


def commits_ahead(repo_root: Path, base_branch: str) -> int:
    remote_ref = f"origin/{base_branch}"
    base_ref = remote_ref if ref_exists(repo_root, remote_ref) else base_branch
    output = run_git(repo_root, ["rev-list", "--count", f"{base_ref}..HEAD"])
    assert isinstance(output, str)
    return int(output)


def head_sha(repo_root: Path) -> str:
    output = run_git(repo_root, ["rev-parse", "HEAD"])
    assert isinstance(output, str)
    return output


def commits_between(repo_root: Path, start: str, end: str = "HEAD") -> list[str]:
    output = run_git(repo_root, ["rev-list", "--reverse", f"{start}..{end}"])
    assert isinstance(output, str)
    return output.splitlines() if output else []


def commit_range_entries(repo_root: Path, commits: list[str]) -> dict[str, str]:
    entries: dict[str, str] = {}
    for commit in commits:
        output = run_git(
            repo_root,
            ["diff-tree", "--root", "--no-commit-id", "--name-status", "-r", "-z", commit],
            binary=True,
        )
        assert isinstance(output, bytes)
        entries.update(parse_name_status(output))
    return entries


def file_sha256(path: Path) -> str:
    if path.is_symlink():
        raise RuntimeError(f"SHA256 input must not be a symlink: {path}")
    if not path.is_file():
        raise RuntimeError(f"file not found: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot_sha256(repo_root: Path, paths: list[str]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths):
        target = repo_root / path
        if target.is_symlink():
            raise RuntimeError(f"review snapshots do not follow symlinks: {path}")
        digest.update(path.encode("utf-8", errors="surrogateescape"))
        digest.update(b"\0")
        if not target.exists():
            digest.update(b"DELETED\0")
            continue
        if not target.is_file():
            raise RuntimeError(f"review snapshot path is not a normal file: {path}")
        digest.update(f"MODE:{target.stat().st_mode:o}\0".encode("ascii"))
        digest.update(target.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def markdown_section(text: str, heading: str) -> str:
    marker = f"## {heading}\n"
    start = text.find(marker)
    if start < 0:
        return ""
    start += len(marker)
    end = text.find("\n## ", start)
    return text[start:] if end < 0 else text[start:end]


def backtick_metadata(section: str, label: str) -> str | None:
    match = re.search(rf"^- {re.escape(label)}: `([^`]+)`$", section, flags=re.MULTILINE)
    return match.group(1) if match else None


def normalized_command(command: str) -> list[str]:
    parts = shlex.split(command)
    if parts and Path(parts[0]).name in {"python", "python3"}:
        parts[0] = "python3"
    return parts


def validate_pr_body(repo_root: Path, task: dict[str, Any]) -> Path:
    resolved_root = repo_root.resolve()
    lexical_path = resolved_root / task["pr_body_file"]
    if lexical_path.is_symlink():
        raise RuntimeError("task PR body file must not be a symlink")
    path = lexical_path.resolve()
    try:
        path.relative_to(resolved_root)
    except ValueError as error:
        raise RuntimeError("task PR body file resolves outside the repository") from error
    if not path.is_file():
        raise RuntimeError(f"task PR body file not found: {task['pr_body_file']}")
    text = path.read_text(encoding="utf-8")
    missing = [heading for heading in REQUIRED_PR_BODY_HEADINGS if f"## {heading}" not in text]
    if missing:
        raise RuntimeError("task PR body file lacks required headings: " + ", ".join(missing))
    return path


def inspect_existing_draft_pr(
    repo_root: Path, number: int, github_repository: str
) -> dict[str, Any]:
    result = subprocess.run(
        [
            "gh",
            "pr",
            "view",
            str(number),
            "--repo",
            github_repository,
            "--json",
            "number,isDraft,headRefName,baseRefName,url",
        ],
        cwd=repo_root,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "could not verify existing draft PR identity: "
            + (result.stderr.strip() or result.stdout.strip())
        )
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError("existing draft PR query returned invalid JSON") from error
    if not isinstance(value, dict):
        raise RuntimeError("existing draft PR query returned an invalid object")
    return value


def command_evidence_passes(section: str, command: str) -> bool:
    command_lines = re.findall(r"^Command: (.+)$", section, re.MULTILINE)
    if len(command_lines) != 1 or normalized_command(command_lines[0]) != normalized_command(command):
        return False
    exit_codes = re.findall(r"^Exit code: ([0-9]+)$", section, re.MULTILINE)
    if exit_codes:
        return all(code == "0" for code in exit_codes) and bool(re.search(r"\bPASS\b", section))
    return bool(re.search(r"^PASS: .*\b(?:exit|exited).*\bcode 0\b", section, re.MULTILINE))


def packet_passes_final_review(
    packet_path: Path,
    *,
    repo_root: Path,
    policy: dict[str, Any],
    task: dict[str, Any],
    changed_paths: list[str],
) -> tuple[bool, str]:
    if not packet_path.is_file():
        raise RuntimeError(f"final review packet not found: {packet_path}")
    packet_text = packet_path.read_text(encoding="utf-8")
    if not packet_text.startswith("# Final Review Packet\n"):
        return False, "packet title is missing"
    required_sections = (
        "Packet Metadata",
        "Git Branch",
        "Changed Files",
        "Human-Readable Summary",
        "Change Spec Identity",
        "Spec-Based Review Summary",
        "Repository Safety Validation Output",
        "Safety Check Output",
        "Pytest Output",
        "Relevant Diff",
    )
    if any(not markdown_section(packet_text, heading) for heading in required_sections):
        return False, "packet structure is incomplete"

    identity = markdown_section(packet_text, "Change Spec Identity")
    expected = {
        "Spec ID": task["task_id"],
        "Target repo": policy["repository"],
        "Expected branch": task["branch"],
        "Current branch": task["branch"],
    }
    for label, value in expected.items():
        if backtick_metadata(identity, label) != value:
            return False, f"packet {label} does not match task evidence"

    summary = markdown_section(packet_text, "Spec-Based Review Summary")
    required_statuses = (
        "- Safety check status: PASS",
        "- Python syntax status: PASS",
        "- Pytest status: PASS",
        "- Unsafe marker status: PASS",
    )
    if any(status not in summary for status in required_statuses):
        return False, "packet does not report all required PASS statuses"

    checklist = markdown_section(packet_text, "Expected Behavior / Review Checklist")
    candidate_match = re.search(
        r"^- Intended commit candidate paths: (.+)$", checklist, flags=re.MULTILINE
    )
    if not candidate_match:
        return False, "packet does not declare intended commit candidate paths"
    candidates = re.findall(r"`([^`]+)`", candidate_match.group(1))
    candidate_files = {path for path in candidates if not path.endswith("/")}
    if candidate_files != set(changed_paths):
        return False, "packet changed paths do not match current task paths"

    evidence_sections = [
        markdown_section(packet_text, "Repository Safety Validation Output"),
        markdown_section(packet_text, "Safety Check Output"),
        markdown_section(packet_text, "Python Syntax Check Output"),
        markdown_section(packet_text, "Pytest Output"),
    ]
    failed_commands = [
        command
        for command in task["validation_commands"]
        if not any(command_evidence_passes(section, command) for section in evidence_sections)
    ]
    if failed_commands:
        return False, "packet lacks successful output for required validation commands"
    return True, ""


def shell_join(parts: list[str]) -> str:
    return " ".join(shlex.quote(part) for part in parts)


def proposed_review_commands(
    staged_paths: list[str], unstaged_paths: list[str], task: dict[str, Any]
) -> list[str]:
    if unstaged_paths:
        return [shell_join(["git", "add", "--", *unstaged_paths])]
    if staged_paths:
        return [shell_join(["git", "commit", "-m", task["commit_message"]])]
    return []


def proposed_publish_commands(policy: dict[str, Any], task: dict[str, Any]) -> list[str]:
    branch = task["branch"]
    commands = [shell_join(["git", "push", "-u", "origin", branch])]
    common = ["--title", task["pr_title"], "--body-file", task["pr_body_file"]]
    if task["existing_draft_pr_number"] is None:
        commands.append(
            shell_join(
                [
                    "gh",
                    "pr",
                    "create",
                    "--repo",
                    policy["github_repository"],
                    "--draft",
                    "--base",
                    task["base_branch"],
                    "--head",
                    branch,
                    *common,
                ]
            )
        )
    else:
        commands.append(
            shell_join(
                [
                    "gh",
                    "pr",
                    "edit",
                    str(task["existing_draft_pr_number"]),
                    "--repo",
                    policy["github_repository"],
                    *common,
                ]
            )
        )
    return commands


def assess_delivery(
    repo_root: Path,
    policy: dict[str, Any],
    task: dict[str, Any],
    phase: str,
    final_review_packet: Path | None = None,
    review_record: dict[str, Any] | None = None,
) -> DeliveryAssessment:
    validate_policy(policy)
    validate_task(task)

    branch = run_git(repo_root, ["branch", "--show-current"])
    assert isinstance(branch, str)
    working_entries = porcelain_entries(repo_root)
    branch_entries = branch_scope_entries(repo_root, task["base_branch"])
    working_paths = sorted(working_entries)
    branch_paths = sorted(branch_entries)
    changed_paths = sorted(set(working_paths) | set(branch_paths))
    staged_paths, unstaged_paths = staged_and_unstaged_paths(working_entries)
    base_commit = merge_base_sha(repo_root, task["base_branch"])
    current_head = head_sha(repo_root)
    origin_url = run_git(repo_root, ["remote", "get-url", "origin"])
    assert isinstance(origin_url, str)
    reasons: list[str] = []

    if repo_root.name != policy["repository"]:
        reasons.append(
            f"repository directory {repo_root.name!r} does not match policy repository {policy['repository']!r}"
        )
    if task["repository"] != policy["repository"]:
        reasons.append("task repository does not match repository policy")
    if origin_url != policy["origin_url"]:
        reasons.append("origin URL does not match repository policy")
    if not policy["enabled"]:
        reasons.append("repository autonomous delivery is disabled")
    if task["base_branch"] != policy["base_branch"]:
        reasons.append("task base branch does not match repository policy")
    if branch != task["branch"]:
        reasons.append(f"current branch {branch!r} does not match task branch {task['branch']!r}")
    if branch == task["base_branch"]:
        reasons.append("current branch is the protected base branch")
    if not any(branch.startswith(prefix) for prefix in policy["allowed_branch_prefixes"]):
        reasons.append("current branch does not use an allowed branch prefix")
    if task["requested_git_level"] > policy["max_git_level"]:
        reasons.append("requested Git level exceeds repository maximum")
    if task["task_class"] not in policy["allowed_task_classes"]:
        reasons.append("task class is not allowed by repository policy")
    if (
        task["protected_content_mode"] == "explicit_exact_scope"
        and policy["protected_content_mode"] == "forbidden"
    ):
        reasons.append("task protected-content mode exceeds repository policy")

    missing_validations = sorted(
        set(policy["required_validation_commands"]) - set(task["validation_commands"])
    )
    if missing_validations:
        reasons.append("task omits required validation commands: " + ", ".join(missing_validations))

    missing_policy_docs = [
        path for path in policy["policy_documents"] if not (repo_root / path).is_file()
    ]
    if missing_policy_docs:
        reasons.append("repository is missing policy documents: " + ", ".join(missing_policy_docs))

    unclassified_paths = [
        path for path in changed_paths if not path_matches(path, task["allowed_paths"])
    ]
    if unclassified_paths:
        reasons.append("changed paths outside task scope: " + ", ".join(unclassified_paths))

    new_paths = sorted(
        {
            path
            for entries in (branch_entries, working_entries)
            for path, status in entries.items()
            if status == "??" or status.startswith("A")
        }
    )
    unapproved_new_paths = [
        path for path in new_paths if not path_matches(path, task["allowed_new_files"])
    ]
    if unapproved_new_paths:
        reasons.append(
            "new files outside allowed_new_files: " + ", ".join(unapproved_new_paths)
        )

    forbidden_patterns = (
        CORE_BLOCKED_PATH_PATTERNS
        + policy["blocked_path_patterns"]
        + task["forbidden_paths"]
    )
    forbidden_paths = [path for path in changed_paths if path_matches(path, forbidden_patterns)]
    if forbidden_paths:
        reasons.append("changed paths match forbidden patterns: " + ", ".join(forbidden_paths))

    review_required_paths = [
        path for path in changed_paths if path_matches(path, task["review_required_paths"])
    ]

    pr_body_valid = True
    if phase in {"review", "publish"}:
        if not changed_paths:
            reasons.append("task has no changed paths to review or publish")
        try:
            validate_pr_body(repo_root, task)
        except RuntimeError as error:
            pr_body_valid = False
            reasons.append(str(error))
        if path_matches(task["pr_body_file"], forbidden_patterns):
            reasons.append("task PR body file matches a blocked or forbidden path")
        if final_review_packet is None:
            reasons.append("final review packet was not provided")
        else:
            packet_ok, packet_reason = packet_passes_final_review(
                final_review_packet,
                repo_root=repo_root,
                policy=policy,
                task=task,
                changed_paths=changed_paths,
            )
            if not packet_ok:
                reasons.append("final review packet is invalid: " + packet_reason)
        if review_record is None:
            reasons.append("review evidence was not provided")
        else:
            validate_review(review_record)
            if review_record["task_id"] != task["task_id"]:
                reasons.append("review evidence task ID does not match task scope")
            if review_record["verdict"] != "APPROVE":
                reasons.append(f"review verdict is {review_record['verdict']}, not APPROVE")
            if review_record["reviewed_base_commit"] != base_commit:
                reasons.append("reviewed base commit does not match current merge base")
            if phase == "review" and review_record["reviewed_head_commit"] != current_head:
                reasons.append("reviewed HEAD commit does not match current HEAD")
            if sorted(review_record["reviewed_paths"]) != changed_paths:
                reasons.append("reviewed paths do not match current changed paths")
            if review_record["pr_body_path"] != task["pr_body_file"]:
                reasons.append("reviewed PR body path does not match task scope")
            pr_body_target = repo_root / task["pr_body_file"]
            if pr_body_valid and pr_body_target.is_file():
                if review_record["pr_body_sha256"] != file_sha256(pr_body_target):
                    reasons.append("reviewed PR body SHA256 does not match current content")
            if not unclassified_paths and not forbidden_paths:
                current_snapshot = snapshot_sha256(repo_root, changed_paths)
                if review_record["reviewed_snapshot_sha256"] != current_snapshot:
                    reasons.append("reviewed content snapshot does not match current content")
            if final_review_packet is not None and final_review_packet.is_file():
                if review_record["final_review_packet_sha256"] != file_sha256(final_review_packet):
                    reasons.append("review evidence does not match the final review packet")

    if phase == "review":
        if task["requested_git_level"] < 3:
            reasons.append("review commit gate requires requested Git Level 3 or 4")
        if not working_paths:
            reasons.append("review requires uncommitted working-tree changes")
        if staged_paths and unstaged_paths:
            reasons.append("review requires either entirely unstaged or entirely staged changes")

    if phase == "publish":
        if task["requested_git_level"] < 4:
            reasons.append("publish requires requested Git Level 4")
        if not policy["draft_pr_allowed"]:
            reasons.append("repository policy does not allow draft PR creation")
        if working_paths:
            reasons.append("working tree is not clean")
        if commits_ahead(repo_root, task["base_branch"]) < 1:
            reasons.append("feature branch has no commit beyond its base")
        if review_record is not None:
            if review_record["reviewed_head_commit"] != base_commit:
                reasons.append("publish requires review to start from the exact merge-base commit")
            publication_commits = commits_between(
                repo_root, review_record["reviewed_head_commit"], current_head
            )
            if len(publication_commits) != 1:
                reasons.append("publish requires exactly one commit after the reviewed HEAD")
            else:
                publication_entries = commit_range_entries(repo_root, publication_commits)
                publication_paths = sorted(publication_entries)
                if publication_paths != sorted(review_record["reviewed_paths"]):
                    reasons.append("publication commit paths do not match reviewed paths")
                historical_forbidden = [
                    path for path in publication_paths if path_matches(path, forbidden_patterns)
                ]
                if historical_forbidden:
                    reasons.append(
                        "publication history contains forbidden paths: "
                        + ", ".join(historical_forbidden)
                    )
        if task["existing_draft_pr_number"] is not None:
            try:
                existing_pr = inspect_existing_draft_pr(
                    repo_root,
                    task["existing_draft_pr_number"],
                    policy["github_repository"],
                )
            except RuntimeError as error:
                reasons.append(str(error))
            else:
                if existing_pr.get("number") != task["existing_draft_pr_number"]:
                    reasons.append("existing PR number does not match task scope")
                if existing_pr.get("isDraft") is not True:
                    reasons.append("existing PR is not draft")
                if existing_pr.get("headRefName") != task["branch"]:
                    reasons.append("existing PR head branch does not match task scope")
                if existing_pr.get("baseRefName") != task["base_branch"]:
                    reasons.append("existing PR base branch does not match task scope")

    proposed_commands: list[str] = []
    if not reasons:
        if phase == "review":
            proposed_commands = proposed_review_commands(staged_paths, unstaged_paths, task)
        elif phase == "publish":
            proposed_commands = proposed_publish_commands(policy, task)

    return DeliveryAssessment(
        phase=phase,
        decision=BLOCK if reasons else READY,
        repository=policy["repository"],
        branch=branch,
        base_branch=task["base_branch"],
        changed_paths=changed_paths,
        review_required_paths=review_required_paths,
        reasons=reasons,
        proposed_commands=proposed_commands,
    )


def print_assessment(assessment: DeliveryAssessment, out: TextIO = sys.stdout) -> None:
    print("Autonomous delivery dry-run", file=out)
    print(f"Phase: {assessment.phase}", file=out)
    print(f"Decision: {assessment.decision}", file=out)
    print(f"Repository: {assessment.repository}", file=out)
    print(f"Branch: {assessment.branch}", file=out)
    print(f"Base branch: {assessment.base_branch}", file=out)
    print(file=out)
    print("Changed paths:", file=out)
    for path in assessment.changed_paths:
        print(f"- {path}", file=out)
    if not assessment.changed_paths:
        print("- none", file=out)
    print(file=out)
    print("Review-required paths:", file=out)
    for path in assessment.review_required_paths:
        print(f"- {path}", file=out)
    if not assessment.review_required_paths:
        print("- none", file=out)
    print(file=out)
    print("Reasons:", file=out)
    for reason in assessment.reasons:
        print(f"- {reason}", file=out)
    if not assessment.reasons:
        print("- all dry-run gates passed", file=out)
    if assessment.proposed_commands:
        print(file=out)
        print("Proposed commands:", file=out)
        print("```bash", file=out)
        for command in assessment.proposed_commands:
            print(command, file=out)
        print("```", file=out)
    print(file=out)
    print("Dry-run only; no Git or GitHub write action was executed.", file=out)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Dry-run bounded autonomous delivery gates.")
    subparsers = parser.add_subparsers(dest="phase", required=True)
    for phase in ("preflight", "review", "publish"):
        subparser = subparsers.add_parser(phase)
        subparser.add_argument("--repo-root", type=Path, default=None)
        subparser.add_argument("--policy", type=Path, required=True)
        subparser.add_argument("--task-scope", type=Path, required=True)
        if phase in {"review", "publish"}:
            subparser.add_argument("--final-review-packet", type=Path, required=True)
            subparser.add_argument("--review-record", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None, out: TextIO = sys.stdout) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        repo_root = args.repo_root.resolve() if args.repo_root else find_repo_root()
        policy = load_json_object(args.policy.resolve(), "repository policy")
        task = load_json_object(args.task_scope.resolve(), "task scope")
        packet = getattr(args, "final_review_packet", None)
        review_record_path = getattr(args, "review_record", None)
        review_record = (
            load_json_object(review_record_path.resolve(), "review evidence")
            if review_record_path
            else None
        )
        assessment = assess_delivery(
            repo_root,
            policy,
            task,
            args.phase,
            final_review_packet=packet.resolve() if packet else None,
            review_record=review_record,
        )
    except RuntimeError as error:
        print("Autonomous delivery dry-run", file=out)
        print(f"Phase: {args.phase}", file=out)
        print(f"Decision: {BLOCK}", file=out)
        print(f"Reason: {error}", file=out)
        print(file=out)
        print("Dry-run only; no Git or GitHub write action was executed.", file=out)
        return 1
    print_assessment(assessment, out=out)
    return 0 if assessment.decision == READY else 1


if __name__ == "__main__":
    raise SystemExit(main())
