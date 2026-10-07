#!/usr/bin/env python3
"""
Run conservative repository safety checks before review or commit.

This script is read-only. It does not modify files, stage changes, commit,
push, delete, move, or rename anything.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType


IMPORTANT_PATHS = (
    "AI_INSTRUCTIONS.md",
    "CURRENT_STATUS.md",
    "NEXT_ACTIONS.md",
    "Career_Job_Agent_Framework",
    "Docs",
    "Templates",
    "Scripts",
    "config",
    "Experiments",
    "Indexes",
    "Papers",
    "Applications",
    "People",
)

EXCLUDED_SEARCH_PREFIXES = (
    "Career_Job_Agent_Framework/profiles/local",
    "Career_Job_Agent_Framework/private",
    "Career_Job_Agent_Framework/state",
    "Career_Job_Agent_Framework/outputs",
    "Career_Job_Agent_Framework/reports/private",
    "Career_Job_Agent_Framework/application_materials",
    "Career_Job_Agent_Framework/credentials",
    "Career_Job_Agent_Framework/tokens",
)

UNSAFE_MARKERS = (
    "/" + "Users/",
    "/" + "home/",
    "file:" + "//",
    "source" + "_url",
)

MAX_TEXT_FILE_BYTES = 1_000_000
MAX_PRIVACY_CONFIG_BYTES = 64_000


@dataclass(frozen=True)
class _PrivacyFinding:
    kind: str


class _StandalonePrivacyGuard:
    """Dependency-free public-tree guard used before Career core is ported."""

    DEFAULT_PATTERNS = {
        "private_key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
        "aws_access_key": re.compile(r"\\bAKIA[A-Z0-9]{16}\\b"),
        "github_token": re.compile(r"(?:ghp_|github_pat_)[A-Za-z0-9_]+"),
        "slack_token": re.compile(r"\\bxox[baprs]-[A-Za-z0-9-]+"),
        "assigned_secret": re.compile(
            r"(?i)\\b(?:api[_-]?key|secret|token|password)\\s*[:=]\\s*['\"][^'\"]{8,}"
        ),
        "mac_local_path": re.compile(r"/" + r"Users/|/" + r"home/"),
        "windows_local_path": re.compile(r"[A-Za-z]:\\\\" + r"Users\\\\"),
    }

    def __init__(
        self,
        *,
        include_defaults: bool,
        forbidden_literals: tuple[str, ...],
        forbidden_regexes: tuple[re.Pattern[str], ...],
    ) -> None:
        self.patterns = self.DEFAULT_PATTERNS if include_defaults else {}
        self.forbidden_literals = forbidden_literals
        self.forbidden_regexes = forbidden_regexes

    @classmethod
    def from_config(cls, config: dict[str, object]) -> "_StandalonePrivacyGuard":
        literals = config.get("forbidden_literals", [])
        regexes = config.get("forbidden_regexes", [])
        if not isinstance(literals, list) or not all(isinstance(x, str) for x in literals):
            raise ValueError("invalid privacy configuration")
        if not isinstance(regexes, list) or not all(isinstance(x, str) for x in regexes):
            raise ValueError("invalid privacy configuration")
        try:
            compiled = tuple(re.compile(value) for value in regexes)
        except re.error:
            raise ValueError("invalid privacy configuration") from None
        return cls(
            include_defaults=bool(config.get("include_default_secret_patterns", True)),
            forbidden_literals=tuple(literals),
            forbidden_regexes=compiled,
        )

    def scan_text(self, text: str) -> list[_PrivacyFinding]:
        findings = [
            _PrivacyFinding(kind)
            for kind, pattern in self.patterns.items()
            if pattern.search(text)
        ]
        if any(value in text for value in self.forbidden_literals):
            findings.append(_PrivacyFinding("forbidden_literal"))
        if any(pattern.search(text) for pattern in self.forbidden_regexes):
            findings.append(_PrivacyFinding("configured_regex"))
        return findings

    def scan_files(self, paths: list[Path], *, max_bytes: int) -> list[_PrivacyFinding]:
        findings: list[_PrivacyFinding] = []
        for path in paths:
            if path.is_symlink():
                findings.append(_PrivacyFinding("symlink"))
                continue
            try:
                if path.stat().st_size > max_bytes:
                    findings.append(_PrivacyFinding("oversize"))
                    continue
                raw = path.read_bytes()
            except OSError:
                findings.append(_PrivacyFinding("unreadable"))
                continue
            if bytes([0]) in raw:
                findings.append(_PrivacyFinding("binary"))
                continue
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                findings.append(_PrivacyFinding("binary"))
                continue
            findings.extend(self.scan_text(text))
        return findings

# These paths are never opened by the release privacy scan. The first group is
# expected local runtime state and is ignored unless it has accidentally become
# tracked (checked separately below). The second group is forbidden publication
# content and causes a blocking result based on path metadata alone.
PROTECTED_RELEASE_PREFIXES = (
    "exports",
    "ai_artifacts",
    "profiles/local",
    "private",
    "state",
    "outputs",
    "reports/private",
    "application_materials",
    "credentials",
    "tokens",
    "Papers",
    "Applications",
    "People",
    "Protocols",
    "Private",
    "raw_data",
    "RawData",
    "data/raw",
    "Data/raw",
)

PROTECTED_RELEASE_SUFFIXES = (
    ".pem",
    ".key",
    ".fcs",
    ".fastq",
    ".fastq.gz",
    ".bam",
    ".cram",
    ".vcf",
    ".vcf.gz",
    ".lif",
    ".czi",
    ".nd2",
    ".tif",
    ".tiff",
    ".h5",
    ".hdf5",
    ".zip",
    ".tar",
    ".tar.gz",
    ".ipynb",
    ".pdf",
    ".doc",
    ".docx",
)


class CheckResult:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, message: str) -> None:
        self.errors.append(message)

    def warning(self, message: str) -> None:
        self.warnings.append(message)


def print_section(title: str) -> None:
    print()
    print(f"== {title} ==")


def run_command(repo_root: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=repo_root,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def run_git(repo_root: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return run_command(repo_root, ["git", *args])


def find_repo_root(start: Path | None = None) -> Path | None:
    cur = (start or Path.cwd()).resolve()
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=cur,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        return None
    return Path(result.stdout.strip()).resolve()


def status_path(line: str) -> str:
    body = line[3:].strip()
    if " -> " in body:
        return body.split(" -> ", 1)[1].strip()
    return body


def print_command_output(result: subprocess.CompletedProcess[str]) -> None:
    output = "\n".join(part.rstrip() for part in (result.stdout, result.stderr) if part.strip())
    if output.strip():
        print(output)


def show_branch(repo_root: Path, results: CheckResult) -> None:
    print_section("Repository")
    branch = run_git(repo_root, ["branch", "--show-current"])
    if branch.returncode == 0 and branch.stdout.strip():
        print(f"Branch: {branch.stdout.strip()}")
        return

    head = run_git(repo_root, ["rev-parse", "--short", "HEAD"])
    if head.returncode == 0 and head.stdout.strip():
        print(f"Branch: detached at {head.stdout.strip()}")
    else:
        print("Branch: unknown")
        results.warning("Could not determine the current branch.")


def show_status(repo_root: Path, results: CheckResult) -> str:
    print_section("Git Status")
    status = run_git(repo_root, ["status", "--short"])
    if status.returncode != 0:
        print_command_output(status)
        results.error("Could not read git status.")
        return ""

    status_text = status.stdout.rstrip()
    if status_text:
        print(status_text)
    else:
        print("Working tree is clean.")
    return status.stdout


def warn_cleanup_items(repo_root: Path, status_text: str, results: CheckResult) -> None:
    print_section("Cleanup Warnings")
    warnings: list[str] = []
    status_lines = [line for line in status_text.splitlines() if line.strip()]

    exports_changes = [
        line for line in status_lines if status_path(line) == "exports" or status_path(line).startswith("exports/")
    ]
    if exports_changes:
        warnings.append("exports/ has modified or untracked files.")

    ds_store_status_paths = [status_path(line) for line in status_lines if status_path(line).endswith(".DS_Store")]
    ds_store_other_paths: list[str] = []
    other_files = run_git(repo_root, ["ls-files", "--others", "--exclude-standard"])
    if other_files.returncode == 0:
        ds_store_other_paths = [line.strip() for line in other_files.stdout.splitlines() if line.strip().endswith(".DS_Store")]

    if ds_store_status_paths or ds_store_other_paths:
        detail = sorted(set(ds_store_status_paths + ds_store_other_paths))
        warnings.append(".DS_Store is modified, deleted, or untracked: " + ", ".join(detail[:5]))
        if len(detail) > 5:
            warnings[-1] += f" (+{len(detail) - 5} more)"

    workspace_changes = [
        line for line in status_lines if status_path(line) == ".obsidian/workspace.json"
    ]
    if workspace_changes:
        warnings.append(".obsidian/workspace.json is modified or untracked.")

    if not warnings:
        print("No cleanup warnings found.")
        return

    for warning in warnings:
        print(f"WARN: {warning}")
        results.warning(warning)


def run_diff_check(repo_root: Path, results: CheckResult, cached: bool = False) -> None:
    label = "git diff --cached --check" if cached else "git diff --check"
    args = ["diff", "--cached", "--check"] if cached else ["diff", "--check"]
    print_section(label)
    diff_check = run_git(repo_root, args)
    if diff_check.returncode == 0:
        print("OK: no whitespace or conflict-marker problems found.")
        return

    print("FAIL: git reported whitespace or conflict-marker problems.")
    print_command_output(diff_check)
    results.error(f"{label} failed.")


CHANGED_FILE_GIT_SOURCES = (
    ["diff", "--name-only"],
    ["diff", "--cached", "--name-only"],
    ["diff", "--name-only", "@{upstream}...HEAD"],
    ["ls-files", "--others", "--exclude-standard"],
)


def changed_file_names(repo_root: Path) -> set[str]:
    names: set[str] = set()
    for args in CHANGED_FILE_GIT_SOURCES:
        result = run_git(repo_root, args)
        if result.returncode != 0:
            continue
        for line in result.stdout.splitlines():
            path_text = line.strip()
            if path_text:
                names.add(path_text)
    return names


def release_candidate_file_names(repo_root: Path) -> set[str]:
    """Return the complete pending/upstream release delta or fail closed."""

    names: set[str] = set()
    for args in CHANGED_FILE_GIT_SOURCES:
        result = run_git(repo_root, args)
        if result.returncode != 0:
            if args == ["diff", "--name-only", "@{upstream}...HEAD"]:
                upstream = run_git(repo_root, ["rev-parse", "--verify", "@{upstream}"])
                if upstream.returncode != 0:
                    # A new local branch can still be checked from its working
                    # tree/index. Once an upstream exists, its diff is mandatory.
                    continue
            raise RuntimeError("release candidate file inventory failed")
        for line in result.stdout.splitlines():
            path_text = line.strip()
            if path_text:
                names.add(path_text)
    return names


def tracked_file_names(repo_root: Path) -> set[str]:
    """Return tracked path metadata without opening any file contents."""

    result = run_git(repo_root, ["ls-files"])
    if result.returncode != 0:
        raise RuntimeError("tracked file inventory failed")
    return {line.strip() for line in result.stdout.splitlines() if line.strip()}


def changed_python_files(repo_root: Path) -> list[Path]:
    names = {
        path_text
        for path_text in changed_file_names(repo_root)
        if path_text.endswith(".py")
        and not is_private_runtime_path(path_text)
        and not is_protected_release_path(path_text)
    }

    paths: list[Path] = []
    for name in sorted(names):
        path = repo_root / name
        if path.is_file():
            paths.append(path)
    return paths


def run_py_compile(repo_root: Path, results: CheckResult) -> None:
    print_section("Python Syntax")
    paths = changed_python_files(repo_root)
    if not paths:
        print("No changed Python files found.")
        return

    failed = False
    with tempfile.TemporaryDirectory(prefix="repo-safety-pycache-") as pycache_dir:
        for path in paths:
            rel = path.relative_to(repo_root).as_posix()
            env = os.environ.copy()
            env["PYTHONPYCACHEPREFIX"] = pycache_dir
            result = subprocess.run(
                ["python3", "-m", "py_compile", str(path)],
                cwd=repo_root,
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
            )
            if result.returncode == 0:
                print(f"OK: {rel}")
                continue

            failed = True
            print(f"FAIL: {rel}")
            print_command_output(result)

    if failed:
        results.error("Python syntax check failed.")


def check_tracked_private_paths(repo_root: Path, results: CheckResult) -> None:
    """Reject tracked private runtime paths without opening their contents."""

    print_section("Career Job Agent Private Paths")
    tracked = run_git(repo_root, ["ls-files", "--", *EXCLUDED_SEARCH_PREFIXES])
    if tracked.returncode != 0:
        print_command_output(tracked)
        results.error("Could not inspect tracked Career Job Agent private paths.")
        return
    paths = [line.strip() for line in tracked.stdout.splitlines() if line.strip()]
    if not paths:
        print("OK: no Career Job Agent private runtime paths are tracked.")
        return
    print("FAIL: private Career Job Agent runtime paths are tracked.")
    for path in paths[:25]:
        print(f"  {path}")
    if len(paths) > 25:
        print(f"  ... {len(paths) - 25} more path(s)")
    results.error("Career Job Agent private runtime paths must not be tracked.")


def _is_path_within_prefixes(path_text: str, prefixes: tuple[str, ...]) -> bool:
    return any(
        path_text == prefix or path_text.startswith(f"{prefix}/")
        for prefix in prefixes
    )


def is_private_runtime_path(path_text: str) -> bool:
    """Return True for local runtime paths whose contents must not be opened."""

    return _is_path_within_prefixes(path_text, EXCLUDED_SEARCH_PREFIXES)


def is_protected_release_path(path_text: str) -> bool:
    """Identify forbidden publication paths without inspecting their contents."""

    if _is_path_within_prefixes(path_text, PROTECTED_RELEASE_PREFIXES):
        return True
    parts = tuple(part.casefold() for part in path_text.split("/") if part)
    if any(part in {"credentials", "secrets"} for part in parts):
        return True
    filename = parts[-1] if parts else ""
    if filename == ".env" or filename.startswith(".env."):
        return True
    lowered = path_text.casefold()
    return any(lowered.endswith(suffix) for suffix in PROTECTED_RELEASE_SUFFIXES)


def _valid_repo_relative_path(path_text: str) -> bool:
    if not path_text or path_text.startswith(("/", "\\")) or "\\" in path_text:
        return False
    return all(part not in {"", ".", ".."} for part in path_text.split("/"))


def _read_explicit_privacy_config(path_text: str) -> dict[str, object]:
    """Read only a caller-named JSON config and never echo its contents."""

    path = Path(path_text)
    if path.suffix.casefold() != ".json" or path.is_symlink() or not path.is_file():
        raise ValueError("invalid privacy configuration")
    if path.stat().st_size > MAX_PRIVACY_CONFIG_BYTES:
        raise ValueError("invalid privacy configuration")
    with path.open("rb") as handle:
        raw = handle.read(MAX_PRIVACY_CONFIG_BYTES + 1)
    if len(raw) > MAX_PRIVACY_CONFIG_BYTES or b"\x00" in raw:
        raise ValueError("invalid privacy configuration")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ValueError("invalid privacy configuration") from None
    if not isinstance(value, dict):
        raise ValueError("invalid privacy configuration")
    return value


def _build_release_privacy_guard(
    privacy_config_path: str | None,
    *,
    include_default_secret_patterns: bool = True,
):
    module_root = Path(__file__).resolve().parents[1]
    module_root_text = str(module_root)
    if module_root_text not in sys.path:
        sys.path.insert(0, module_root_text)

    config: dict[str, object] = {}
    if privacy_config_path:
        loaded = _read_explicit_privacy_config(privacy_config_path)
        if "privacy_guard" in loaded:
            nested = loaded["privacy_guard"]
            if not isinstance(nested, dict):
                raise ValueError("invalid privacy configuration")
            config = dict(nested)
        else:
            config = loaded

    # The changed-file secret scan cannot be weakened by an optional overlay.
    # The separate tracked-file personal-data scan deliberately uses only the
    # configured identifiers so historical synthetic path fixtures do not
    # become false positives.
    config["include_default_secret_patterns"] = include_default_secret_patterns
    try:
        from Career_Job_Agent_Framework.core.privacy import PrivacyGuard
    except ImportError:
        return _StandalonePrivacyGuard.from_config(config)
    return PrivacyGuard.from_config(config)


def _privacy_finding_label(kind: str) -> str:
    labels = {
        "private_key": "private-key material",
        "aws_access_key": "access-key shaped content",
        "github_token": "token-shaped content",
        "slack_token": "token-shaped content",
        "assigned_secret": "assigned-secret shaped content",
        "mac_local_path": "local absolute path",
        "windows_local_path": "local absolute path",
        "forbidden_literal": "configured forbidden literal",
        "configured_regex": "configured forbidden pattern",
        "symlink": "symbolic link",
        "oversize": "file exceeds the privacy scan limit",
        "binary": "binary or non-text file",
        "unreadable": "unreadable or non-UTF-8 file",
        "scan_error": "privacy scan could not complete",
    }
    return labels.get(kind, "privacy guard finding")


def run_public_release_privacy_check(
    repo_root: Path,
    results: CheckResult,
    *,
    privacy_config_path: str | None = None,
) -> None:
    """Scan release candidates and tracked public files without opening private paths."""

    print_section("Public Release Privacy and Secrets")
    try:
        guard = _build_release_privacy_guard(privacy_config_path)
        personal_guard = (
            _build_release_privacy_guard(
                privacy_config_path,
                include_default_secret_patterns=False,
            )
            if privacy_config_path
            else None
        )
    except (ImportError, OSError, ValueError):
        print("FAIL: privacy guard configuration could not be loaded safely.")
        results.error("Public release privacy/secret guard could not be initialized.")
        return

    try:
        names = sorted(release_candidate_file_names(repo_root))
        tracked_names = sorted(tracked_file_names(repo_root))
    except RuntimeError:
        print("FAIL: Git could not inventory the public release candidate safely.")
        results.error("Public release privacy/secret file inventory failed.")
        return
    config_relative: str | None = None
    if privacy_config_path:
        try:
            config_path = Path(privacy_config_path)
            if not config_path.is_absolute():
                config_path = Path.cwd() / config_path
            config_relative = config_path.resolve().relative_to(repo_root.resolve()).as_posix()
        except (OSError, ValueError):
            config_relative = None

    candidates: list[tuple[str, Path]] = []
    protected: set[str] = set()
    invalid_path_count = 0
    skipped_private_count = 0
    for path_text in names:
        if not _valid_repo_relative_path(path_text):
            invalid_path_count += 1
            continue
        if is_private_runtime_path(path_text):
            skipped_private_count += 1
            continue
        if is_protected_release_path(path_text) or path_text == config_relative:
            protected.add(path_text)
            continue
        path = repo_root / path_text
        # A deleted file is not release content. Broken links still exist as
        # links and are passed to PrivacyGuard so they fail closed.
        if not path.exists() and not path.is_symlink():
            continue
        candidates.append((path_text, path))

    tracked_candidates: list[tuple[str, Path]] = []
    for path_text in tracked_names:
        if not _valid_repo_relative_path(path_text):
            invalid_path_count += 1
            continue
        if is_private_runtime_path(path_text):
            continue
        if is_protected_release_path(path_text) or path_text == config_relative:
            protected.add(path_text)
            continue
        path = repo_root / path_text
        if path.exists() or path.is_symlink():
            tracked_candidates.append((path_text, path))

    found = False
    if protected:
        found = True
        protected_paths = sorted(protected)
        print("FAIL: protected publication path(s) are tracked or changed; contents were not opened.")
        for path_text in protected_paths[:25]:
            print(f"  {path_text}")
        if len(protected_paths) > 25:
            print(f"  ... {len(protected_paths) - 25} more path(s)")
    if invalid_path_count:
        found = True
        print(
            "FAIL: "
            f"{invalid_path_count} changed path(s) could not be classified safely; "
            "contents were not opened."
        )

    for path_text, path in candidates:
        try:
            findings = guard.scan_files([path], max_bytes=MAX_TEXT_FILE_BYTES)
        except Exception:
            # Never serialize an exception that could contain a configured
            # literal, expression, matched value, or local absolute path.
            found = True
            print(f"  {path_text}: {_privacy_finding_label('scan_error')}")
            continue
        if not findings:
            continue
        found = True
        kinds = sorted({str(item.kind) for item in findings})
        labels = ", ".join(_privacy_finding_label(kind) for kind in kinds)
        print(f"  {path_text}: {labels}")

    personal_matches = 0
    if personal_guard is not None:
        for path_text, path in tracked_candidates:
            # A configured identifier in a path is itself private. Do not echo
            # that path or open the file once path metadata already blocks it.
            if personal_guard.scan_text(path_text):
                found = True
                personal_matches += 1
                continue
            try:
                findings = personal_guard.scan_files(
                    [path], max_bytes=MAX_TEXT_FILE_BYTES
                )
            except Exception:
                found = True
                print(f"  {path_text}: {_privacy_finding_label('scan_error')}")
                continue
            if not findings:
                continue
            found = True
            kinds = sorted({str(item.kind) for item in findings})
            labels = ", ".join(_privacy_finding_label(kind) for kind in kinds)
            print(f"  {path_text}: {labels}")
        if personal_matches:
            print(
                "  "
                f"{personal_matches} tracked path(s) matched configured private "
                "identifiers; matching paths were not printed or opened."
            )

    if skipped_private_count:
        print(
            f"Skipped {skipped_private_count} local private runtime path(s) "
            "without opening them."
        )
    if found:
        results.error("Public release privacy/secret check failed.")
    elif candidates:
        message = f"OK: scanned {len(candidates)} changed public release file(s)"
        if personal_guard is not None:
            message += f" and {len(tracked_candidates)} tracked public file(s)"
        print(message + ".")
    else:
        print("OK: no changed public release files need privacy scanning.")


def is_probably_binary(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            chunk = handle.read(4096)
    except OSError:
        return True
    return b"\0" in chunk


def is_relevant_search_path(path_text: str) -> bool:
    if any(
        path_text == excluded or path_text.startswith(f"{excluded}/")
        for excluded in EXCLUDED_SEARCH_PREFIXES
    ):
        return False
    return any(
        path_text == important_path or path_text.startswith(f"{important_path}/")
        for important_path in IMPORTANT_PATHS
    )


def iter_all_search_files(repo_root: Path) -> list[Path]:
    files: list[Path] = []
    seen: set[Path] = set()
    for path_text in IMPORTANT_PATHS:
        path = repo_root / path_text
        if not path.exists():
            continue
        if path.is_file():
            candidates = [path]
        else:
            candidates = []
            for current_root, directories, filenames in os.walk(path, topdown=True):
                current = Path(current_root)
                directories[:] = [
                    name
                    for name in directories
                    if is_relevant_search_path(
                        (current / name).relative_to(repo_root).as_posix()
                    )
                ]
                candidates.extend(current / name for name in filenames)

        for candidate in candidates:
            relative = candidate.relative_to(repo_root).as_posix()
            if not is_relevant_search_path(relative):
                continue
            if candidate in seen:
                continue
            seen.add(candidate)
            files.append(candidate)
    return sorted(files)


def iter_changed_search_files(repo_root: Path) -> list[Path]:
    files: list[Path] = []
    seen: set[Path] = set()
    for path_text in sorted(changed_file_names(repo_root)):
        if not is_relevant_search_path(path_text):
            continue
        path = repo_root / path_text
        if not path.is_file():
            continue
        if path in seen:
            continue
        seen.add(path)
        files.append(path)
    return files


def is_allowed_marker_mention(path: str, line: str, marker: str) -> bool:
    stripped = line.strip()
    lower = stripped.lower()
    path_parts = path.split("/")
    in_scripts = bool(path_parts) and path_parts[0] == "Scripts"

    if not stripped:
        return True

    grep_terms = ("grep", "rg ", "ripgrep", "git grep", "findstr", "ack ")
    if any(term in lower for term in grep_terms):
        return True

    example_terms = ("example", "sample", "test fixture", "fixture", "dummy", "placeholder")
    safety_terms = ("safety-check", "safety check", "unsafe marker")
    if any(term in lower for term in example_terms) and any(term in lower for term in safety_terms):
        return True

    documentation_phrases = (
        "must not appear",
        "must not include",
        "must not contain",
        "should not appear",
        "should not include",
        "should not contain",
        "do not include",
        "do not contain",
        "forbidden marker",
        "forbidden markers",
        "blocked marker",
        "blocked markers",
        "unsafe marker",
        "unsafe markers",
        "remove unsafe marker",
        "strip unsafe marker",
        "redact unsafe marker",
    )
    if any(phrase in lower for phrase in documentation_phrases):
        return True

    # The reusable framework uses source_url as a typed verification field.
    # Local paths and file URLs on the same line remain independently blocked
    # by the other unsafe markers.
    if (
        marker == "source" + "_url"
        and path.startswith("Career_Job_Agent_Framework/")
        and path.endswith(".py")
    ):
        return True

    if marker == "source" + "_url" and in_scripts:
        url_field_terms = (
            "parse",
            "parses",
            "parser",
            "pop(",
            "remove",
            "removes",
            "strip",
            "strips",
            "delete",
            "deletes",
            "discard",
            "discards",
            "block",
            "blocks",
            "forbid",
            "forbidden",
            "disallow",
            "reject",
            "redact",
            "unsafe",
            "must not",
            "should not",
            "document",
            "documents",
            ".get(",
            "[",
            " in ",
            "field",
            "fields",
            "metadata",
        )
        if any(term in lower for term in url_field_terms):
            return True

    return False


def search_unsafe_markers(repo_root: Path, results: CheckResult, full_scan: bool = False) -> None:
    print_section("Unsafe Local/Path Markers")
    matches: list[tuple[str, int, str]] = []
    skipped_large = 0
    skipped_binary = 0
    files = iter_all_search_files(repo_root) if full_scan else iter_changed_search_files(repo_root)

    if full_scan:
        print("Mode: full scan of configured repository areas.")
    else:
        print("Mode: default scan of changed, staged, and untracked files only.")

    if not files:
        print("OK: no relevant changed files need unsafe marker scanning.")
        return

    for path in files:
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if size > MAX_TEXT_FILE_BYTES:
            skipped_large += 1
            continue
        if is_probably_binary(path):
            skipped_binary += 1
            continue

        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            skipped_binary += 1
            continue
        except OSError:
            continue

        rel = path.relative_to(repo_root).as_posix()
        for line_number, line in enumerate(text.splitlines(), start=1):
            for marker in UNSAFE_MARKERS:
                if marker in line and not is_allowed_marker_mention(rel, line, marker):
                    matches.append((rel, line_number, marker))

    if matches:
        print("FAIL: unsafe local/path markers found.")
        for rel, line_number, marker in matches[:25]:
            print(f"  {rel}:{line_number}: {marker}")
        if len(matches) > 25:
            print(f"  ... {len(matches) - 25} more matches")
        results.error("Unsafe local/path markers were found.")
    else:
        print("OK: no unsafe markers found in checked areas.")

    if skipped_large or skipped_binary:
        print(f"Skipped {skipped_large} large file(s) and {skipped_binary} binary/non-text file(s).")


def load_check_shared_core_module() -> ModuleType | None:
    script_path = Path(__file__).resolve().parent / "check_shared_core.py"
    if not script_path.is_file():
        return None
    module_name = "check_shared_core_wired"
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def run_shared_core_check(repo_root: Path, results: CheckResult) -> None:
    print_section("Shared Core")
    module = load_check_shared_core_module()
    if module is None:
        message = "Could not load Scripts/check_shared_core.py."
        print(f"WARN: {message}")
        results.warning(message)
        return

    report = module.check_shared_core(repo_root)
    for line in module.render_report(report):
        print(line)

    for error in report.errors:
        results.error(error)
    for warning in report.warnings:
        results.warning(warning)


def print_summary(results: CheckResult) -> int:
    print_section("Summary")
    if results.errors:
        print("FAIL")
        print("Blocking issues:")
        for error in results.errors:
            print(f"  - {error}")
        return 1

    if results.warnings:
        print("WARN")
        print("Cleanup warnings:")
        for warning in results.warnings:
            print(f"  - {warning}")
        return 0

    print("PASS")
    print("No blocking errors or cleanup warnings found.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run conservative repository safety checks.")
    parser.add_argument(
        "--full-scan",
        action="store_true",
        help="scan all configured repository areas for unsafe local/path markers",
    )
    parser.add_argument(
        "--privacy-config",
        metavar="PATH",
        help=(
            "explicit JSON file containing privacy_guard forbidden_literals "
            "and forbidden_regexes; values and matches are never printed"
        ),
    )
    args = parser.parse_args()

    results = CheckResult()
    repo_root = find_repo_root()

    if repo_root is None:
        print("FAIL: This command must be run inside a git repository.")
        return 1

    print("Repository safety check")
    print(f"Repo root: {repo_root}")

    show_branch(repo_root, results)
    status_text = show_status(repo_root, results)
    warn_cleanup_items(repo_root, status_text, results)
    check_tracked_private_paths(repo_root, results)
    run_public_release_privacy_check(
        repo_root,
        results,
        privacy_config_path=args.privacy_config,
    )
    if results.errors:
        return print_summary(results)
    run_diff_check(repo_root, results, cached=False)
    run_diff_check(repo_root, results, cached=True)
    run_py_compile(repo_root, results)
    search_unsafe_markers(repo_root, results, full_scan=args.full_scan)
    run_shared_core_check(repo_root, results)
    return print_summary(results)


if __name__ == "__main__":
    raise SystemExit(main())
