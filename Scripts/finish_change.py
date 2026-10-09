#!/usr/bin/env python3
"""
Create a final human-supervised review packet before committing changes.

This script is intentionally conservative. It does not stage, commit, push,
delete, move, or rename files. It writes a timestamped Markdown packet under
exports/final_review/<timestamp>/ and refreshes HANDOFF.md.
"""

from __future__ import annotations

import ast
import argparse
import difflib
import hashlib
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


OUTPUT_ROOT_PARTS = ("exports", "final_review")
PACKET_NAME = "FINAL_REVIEW_PACKET.md"
HANDOFF_NAME = "HANDOFF.md"
CHANGE_START_ROOT_PARTS = ("exports", "change_start")
ACTIVE_CHANGE_SPEC_PATH_PARTS = ("exports", "active_change", "CHANGE_SPEC.md")
CHANGE_SPEC_NAME = "CHANGE_SPEC.md"
MAX_UNTRACKED_TEXT_BYTES = 200_000
MAX_DIFF_CHARS = 160_000
DEFAULT_PYTEST_TIMEOUT_SECONDS = 300
MAX_PYTEST_TIMEOUT_SECONDS = 3600
PYTEST_TIMEOUT_ENV = "AI_RESEARCH_OS_FINAL_REVIEW_PYTEST_TIMEOUT_SECONDS"
BROAD_CHANGE_FILE_THRESHOLD = 5

RAW_DATA_MARKERS = (
    "raw_data",
    "data/raw",
    "raw/",
    "RawData",
)

RAW_DATA_EXTENSIONS = (
    ".bam",
    ".bcl",
    ".czi",
    ".fast5",
    ".fastq",
    ".fcs",
    ".h5",
    ".hdf5",
    ".lif",
    ".nd2",
    ".sam",
    ".tif",
    ".tiff",
)

SECRET_OR_LOCAL_PATH_MARKERS = (
    ".env",
    ".pem",
    ".p12",
    ".key",
    "id_rsa",
    "credential",
    "credentials",
    "secret",
    "token",
    "private",
)

HIGH_RISK_PATH_MARKERS = (
    ".github/workflows",
    ".gitignore",
    "security",
    "config",
)

FAST_LANE_EXTENSIONS = (
    ".md",
    ".txt",
    ".rst",
)

SOURCE_EXTENSIONS = (
    ".py",
    ".sh",
    ".bash",
    ".zsh",
    ".yaml",
    ".yml",
    ".json",
    ".toml",
)

DANGEROUS_DIFF_MARKERS = (
    "git commit",
    "git push",
    "git add",
    "git rm",
    "git mv",
    "git reset",
    "git checkout",
    "git clean",
    "rm -rf",
    "shutil.rmtree",
    ".unlink(",
    "os.remove(",
    "os.rmdir(",
    ".rename(",
    ".replace(",
)

SPEC_METADATA_FIELDS = (
    "Spec ID",
    "Target repo",
    "Expected branch",
    "Task",
    "Created for / change class",
)

SPEC_METADATA_ALIASES = {
    "spec id": "Spec ID",
    "target repo": "Target repo",
    "target repository": "Target repo",
    "expected branch": "Expected branch",
    "task": "Task",
    "created for": "Created for / change class",
    "change class": "Created for / change class",
    "change type": "Created for / change class",
    "created for change class": "Created for / change class",
}

SPEC_FILE_SCOPE_HEADINGS = {
    "positive file list": "positive",
    "negative file list": "negative",
    "forbidden file list": "forbidden",
}

SPEC_SCOPE_NAMES = {
    "positive": "Positive file list",
    "negative": "Negative file list",
    "forbidden": "Forbidden file list",
}

ADVISORY_DECISIONS = (
    "AUTO-APPROVE CANDIDATE",
    "REVIEW REQUIRED",
    "BLOCK COMMIT",
    "REVERT OR EXPLAIN",
)


@dataclass
class ChangedFile:
    path: str
    status_codes: set[str] = field(default_factory=set)
    sources: set[str] = field(default_factory=set)


@dataclass
class CommandResult:
    label: str
    command: list[str]
    returncode: int
    stdout: str
    stderr: str

    def combined_output(self) -> str:
        parts = []
        if self.stdout.strip():
            parts.append(self.stdout.rstrip())
        if self.stderr.strip():
            parts.append(self.stderr.rstrip())
        return "\n".join(parts)


@dataclass
class ChangeSpec:
    source_path: Path
    content: str
    sha256: str
    metadata: dict[str, str]


@dataclass
class SpecFileScope:
    positive: list[str] = field(default_factory=list)
    negative: list[str] = field(default_factory=list)
    forbidden: list[str] = field(default_factory=list)
    missing_sections: list[str] = field(default_factory=list)


@dataclass
class SpecReviewFacts:
    file_scope: SpecFileScope
    missing_metadata: list[str]
    expected_branch: str | None
    branch_matches: bool
    intended_commit_paths: list[str]
    outside_positive_paths: list[str]
    negative_paths: list[str]
    forbidden_paths: list[str]
    generated_export_paths: list[str]
    staged_generated_export_paths: list[str]
    generated_exports_in_intended_commit: list[str]
    safety_status: str
    python_syntax_status: str
    pytest_status: str
    unsafe_marker_status: str
    broad_change_warning: str
    dangerous_executable_paths: list[str]
    deletion_or_rename_paths: list[str]
    suggested_decision: str
    decision_reasons: list[str]


def find_repo_root(start: Path | None = None) -> Path:
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
        raise RuntimeError("Run this script from inside a Git repository.")
    return Path(result.stdout.strip()).resolve()


def run_command(
    repo_root: Path,
    command: list[str],
    label: str,
    timeout: int | None = None,
    env: dict[str, str] | None = None,
) -> CommandResult:
    result = subprocess.run(
        command,
        cwd=repo_root,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        env=env,
    )
    return CommandResult(
        label=label,
        command=command,
        returncode=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
    )


def run_git(repo_root: Path, args: list[str], label: str) -> CommandResult:
    return run_command(repo_root, ["git", *args], label)


def require_success(result: CommandResult) -> str:
    if result.returncode == 0:
        return result.stdout
    command = " ".join(result.command)
    details = result.combined_output() or "(no output)"
    raise RuntimeError(f"{command} failed:\n{details}")


def status_path(line: str) -> str:
    body = line[3:].strip()
    if " -> " in body:
        return body.split(" -> ", 1)[1].strip()
    return body


def parse_status(status_text: str) -> dict[str, ChangedFile]:
    changed: dict[str, ChangedFile] = {}
    for line in status_text.splitlines():
        if not line.strip():
            continue
        path = status_path(line)
        if not path:
            continue
        entry = changed.setdefault(path, ChangedFile(path=path))
        entry.sources.add("git status")
        for code in line[:2]:
            if code.strip():
                entry.status_codes.add(code)
    return changed


def add_name_status(
    changed: dict[str, ChangedFile],
    name_status_text: str,
    source: str,
) -> None:
    for line in name_status_text.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        status = parts[0]
        path = parts[-1]
        if not path:
            continue
        entry = changed.setdefault(path, ChangedFile(path=path))
        entry.sources.add(source)
        entry.status_codes.add(status[:1])


def add_untracked(changed: dict[str, ChangedFile], untracked_text: str) -> None:
    for line in untracked_text.splitlines():
        path = line.strip()
        if not path:
            continue
        entry = changed.setdefault(path, ChangedFile(path=path))
        entry.sources.add("untracked")
        entry.status_codes.add("?")


def is_raw_data_path(path: str) -> bool:
    lower = path.lower()
    if any(marker.lower() in lower for marker in RAW_DATA_MARKERS):
        return True
    return lower.endswith(RAW_DATA_EXTENSIONS)


def is_probably_binary(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            chunk = handle.read(4096)
    except OSError:
        return True
    return b"\0" in chunk


def is_safe_text_path(repo_root: Path, path_text: str) -> bool:
    if is_raw_data_path(path_text):
        return False
    path = repo_root / path_text
    if not path.is_file():
        return False
    try:
        if path.stat().st_size > MAX_UNTRACKED_TEXT_BYTES:
            return False
    except OSError:
        return False
    return not is_probably_binary(path)


def changed_python_files(repo_root: Path, changed: dict[str, ChangedFile]) -> list[Path]:
    paths: list[Path] = []
    for path_text in sorted(changed):
        if not path_text.endswith(".py"):
            continue
        entry = changed[path_text]
        if "D" in entry.status_codes:
            continue
        if is_raw_data_path(path_text):
            continue
        path = repo_root / path_text
        if path.is_file():
            paths.append(path)
    return paths


def run_python_syntax_checks(repo_root: Path, paths: list[Path]) -> str:
    if not paths:
        return "No changed Python files found."

    lines: list[str] = []
    ok = True
    for path in paths:
        rel = path.relative_to(repo_root).as_posix()
        try:
            source = path.read_text(encoding="utf-8")
            ast.parse(source, filename=rel)
            compile(source, rel, "exec")
        except SyntaxError as error:
            ok = False
            lines.append(f"FAIL {rel}:{error.lineno}:{error.offset}: {error.msg}")
        except UnicodeDecodeError as error:
            ok = False
            lines.append(f"FAIL {rel}: could not read as UTF-8: {error}")
        except OSError as error:
            ok = False
            lines.append(f"FAIL {rel}: could not read file: {error}")
        else:
            lines.append(f"OK   {rel}")

    header = "PASS: Python syntax checks passed." if ok else "FAIL: Python syntax checks failed."
    return "\n".join([header, *lines])


def run_safety_check(repo_root: Path) -> CommandResult:
    script = repo_root / "Scripts" / "run_safety_check.py"
    if not script.is_file():
        return CommandResult(
            label="Safety check",
            command=["python3", "Scripts/run_safety_check.py"],
            returncode=127,
            stdout="Scripts/run_safety_check.py not found; safety check was not run.\n",
            stderr="",
        )
    return run_command(
        repo_root,
        ["python3", str(script.relative_to(repo_root))],
        "Safety check",
    )


def run_repository_safety_validation(repo_root: Path) -> CommandResult:
    script = repo_root / "Scripts" / "validate_repository_safety.py"
    command = [
        "python3",
        "Scripts/validate_repository_safety.py",
        "--phase",
        "working-tree",
    ]
    if not script.is_file():
        return CommandResult(
            label="Repository safety validation",
            command=command,
            returncode=127,
            stdout="Scripts/validate_repository_safety.py not found; validation was not run.\n",
            stderr="",
        )
    return run_command(
        repo_root,
        command,
        "Repository safety validation",
    )


def appears_to_have_tests(repo_root: Path) -> bool:
    config_names = ("pytest.ini", "tox.ini", "setup.cfg", "pyproject.toml")
    if any((repo_root / name).is_file() for name in config_names):
        return True

    tests_dir = repo_root / "tests"
    if tests_dir.is_dir():
        for child in tests_dir.rglob("*.py"):
            if child.name.startswith("test_") or child.name.endswith("_test.py"):
                return True

    for pattern in ("test_*.py", "*_test.py"):
        if any(repo_root.glob(pattern)):
            return True

    return False


def pytest_available(repo_root: Path) -> bool:
    if shutil.which("pytest"):
        return True
    result = run_command(repo_root, [sys.executable, "-m", "pytest", "--version"], "pytest probe")
    return result.returncode == 0


def resolve_pytest_timeout(
    environment: dict[str, str] | None = None,
) -> tuple[int | None, str | None]:
    """Resolve a positive pytest timeout without weakening fail-closed review."""

    source = os.environ if environment is None else environment
    raw_value = source.get(PYTEST_TIMEOUT_ENV)
    if raw_value is None:
        return DEFAULT_PYTEST_TIMEOUT_SECONDS, None

    try:
        timeout_seconds = int(raw_value)
    except ValueError:
        return None, (
            f"{PYTEST_TIMEOUT_ENV} must be an integer between 1 and "
            f"{MAX_PYTEST_TIMEOUT_SECONDS}"
        )
    if timeout_seconds <= 0 or timeout_seconds > MAX_PYTEST_TIMEOUT_SECONDS:
        return None, (
            f"{PYTEST_TIMEOUT_ENV} must be an integer between 1 and "
            f"{MAX_PYTEST_TIMEOUT_SECONDS}"
        )
    return timeout_seconds, None


def run_pytest_if_available(repo_root: Path) -> str:
    if not appears_to_have_tests(repo_root):
        return "Pytest was not run because this repository does not appear to have tests."

    if not pytest_available(repo_root):
        return "Pytest was not run because pytest does not appear to be available."

    timeout_seconds, timeout_error = resolve_pytest_timeout()
    if timeout_error is not None or timeout_seconds is None:
        return "FAIL: invalid pytest timeout configuration. " + str(timeout_error)

    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    with tempfile.TemporaryDirectory(prefix="finish-change-pycache-") as pycache_dir:
        env["PYTHONPYCACHEPREFIX"] = pycache_dir
        command = [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
        ]
        try:
            result = run_command(
                repo_root,
                command,
                "pytest",
                timeout=timeout_seconds,
                env=env,
            )
        except subprocess.TimeoutExpired as error:
            output_parts = []
            if error.stdout:
                output_parts.append(str(error.stdout).rstrip())
            if error.stderr:
                output_parts.append(str(error.stderr).rstrip())
            output = "\n".join(part for part in output_parts if part)
            return "\n".join(
                [
                    f"FAIL: pytest timed out after {timeout_seconds} seconds.",
                    "Command: " + " ".join(command),
                    output or "(no output before timeout)",
                ]
            )

    status = "PASS" if result.returncode == 0 else "FAIL"
    output = result.combined_output() or "(no output)"
    return "\n".join(
        [
            f"{status}: pytest exited with code {result.returncode}.",
            "Command: " + " ".join(command),
            output,
        ]
    )


def markdown_code_block(text: str, language: str = "") -> str:
    body = text.rstrip("\n") if text.strip() else "(none)"
    fence = f"```{language}".rstrip()
    return f"{fence}\n{body}\n```"


def normalize_metadata_label(label: str) -> str:
    text = label.strip().strip("`*_")
    text = re.sub(r"[*_`]+", "", text)
    text = re.sub(r"[^a-zA-Z0-9]+", " ", text)
    return " ".join(text.casefold().split())


def clean_metadata_value(value: str) -> str:
    text = value.strip().strip("`*_")
    return text.strip()


def parse_change_spec_metadata(spec_text: str) -> dict[str, str]:
    metadata: dict[str, str] = {}
    for line in spec_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped[:1] in {"-", "*", "+"}:
            stripped = stripped[1:].strip()
        if ":" not in stripped:
            continue

        label_text, value_text = stripped.split(":", 1)
        field = SPEC_METADATA_ALIASES.get(normalize_metadata_label(label_text))
        if field is None:
            continue

        value = clean_metadata_value(value_text)
        if not value:
            continue
        if field in metadata and metadata[field] != value:
            existing_parts = [part.strip() for part in metadata[field].split(" / ")]
            if value not in existing_parts:
                metadata[field] = f"{metadata[field]} / {value}"
        else:
            metadata[field] = value
    return metadata


def clean_scope_item(item: str) -> list[str]:
    backtick_paths = re.findall(r"`([^`]+)`", item)
    if backtick_paths:
        return [normalize_scope_path(path) for path in backtick_paths if normalize_scope_path(path)]

    text = item.strip().strip("`*_")
    text = re.sub(r"\s+#.*$", "", text).strip()
    text = text.rstrip(".;,")
    return [normalize_scope_path(text)] if text else []


def normalize_scope_path(path_text: str) -> str:
    text = path_text.strip().strip("`*_")
    text = text.replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    return text.rstrip(".;,")


def parse_change_spec_file_scope(spec_text: str) -> SpecFileScope:
    lists: dict[str, list[str]] = {"positive": [], "negative": [], "forbidden": []}
    seen_sections: set[str] = set()
    current: str | None = None

    for line in spec_text.splitlines():
        heading = re.match(r"^\s{0,3}#{1,6}\s+(.+?)\s*$", line)
        if heading:
            heading_label = normalize_metadata_label(heading.group(1))
            current = SPEC_FILE_SCOPE_HEADINGS.get(heading_label)
            if current is not None:
                seen_sections.add(current)
            continue

        if current is None:
            continue

        stripped = line.strip()
        if not stripped or stripped.startswith("```"):
            continue
        if stripped[:1] not in {"-", "*", "+"}:
            continue

        for item in clean_scope_item(stripped[1:].strip()):
            if item and item not in lists[current]:
                lists[current].append(item)

    missing = [
        SPEC_SCOPE_NAMES[key]
        for key in ("positive", "negative", "forbidden")
        if key not in seen_sections or not lists[key]
    ]
    return SpecFileScope(
        positive=lists["positive"],
        negative=lists["negative"],
        forbidden=lists["forbidden"],
        missing_sections=missing,
    )


def spec_metadata_value(change_spec: ChangeSpec, field: str) -> str:
    value = change_spec.metadata.get(field)
    return f"`{value}`" if value else "missing"


def format_change_spec_identity(change_spec: ChangeSpec, current_branch: str) -> str:
    expected_branch = change_spec.metadata.get("Expected branch")
    warning_lines = ["- Branch warning: none"]
    if expected_branch and expected_branch != current_branch:
        warning_lines = [
            (
                "- WARNING: expected branch "
                f"`{expected_branch}` does not match current branch `{current_branch}`."
            )
        ]

    missing = [field for field in SPEC_METADATA_FIELDS if field not in change_spec.metadata]
    missing_text = ", ".join(missing) if missing else "none"

    return "\n".join(
        [
            "## Change Spec Identity",
            "",
            f"- Spec source path: `{change_spec.source_path}`",
            f"- Spec ID: {spec_metadata_value(change_spec, 'Spec ID')}",
            f"- Spec SHA256: `{change_spec.sha256}`",
            f"- Target repo: {spec_metadata_value(change_spec, 'Target repo')}",
            f"- Expected branch: {spec_metadata_value(change_spec, 'Expected branch')}",
            f"- Current branch: `{current_branch}`",
            f"- Task: {spec_metadata_value(change_spec, 'Task')}",
            (
                "- Created for / change class: "
                f"{spec_metadata_value(change_spec, 'Created for / change class')}"
            ),
            f"- Missing metadata fields: {missing_text}",
            *warning_lines,
            "",
        ]
    )


def truncate_text(text: str, max_chars: int, label: str) -> str:
    if len(text) <= max_chars:
        return text
    omitted = len(text) - max_chars
    return text[:max_chars].rstrip() + f"\n\n[truncated {omitted} characters from {label}]"


def quote_paths(paths: list[str]) -> list[str]:
    return ["--", *paths]


def diffable_paths(changed: dict[str, ChangedFile]) -> list[str]:
    paths: list[str] = []
    for path_text in sorted(changed):
        if is_raw_data_path(path_text):
            continue
        paths.append(path_text)
    return paths


def git_diff_for_paths(repo_root: Path, paths: list[str], cached: bool = False) -> str:
    if not paths:
        return ""
    args = ["diff", "--no-ext-diff"]
    if cached:
        args.append("--cached")
    args.extend(quote_paths(paths))
    return require_success(run_git(repo_root, args, "git diff"))


def git_diff_stat_for_paths(repo_root: Path, paths: list[str], cached: bool = False) -> str:
    if not paths:
        return ""
    args = ["diff", "--stat", "--no-ext-diff"]
    if cached:
        args.append("--cached")
    args.extend(quote_paths(paths))
    return require_success(run_git(repo_root, args, "git diff stat"))


def untracked_text_diff(repo_root: Path, changed: dict[str, ChangedFile]) -> str:
    chunks: list[str] = []
    for path_text in sorted(changed):
        entry = changed[path_text]
        if "?" not in entry.status_codes:
            continue
        if not is_safe_text_path(repo_root, path_text):
            chunks.append(
                f"Untracked file skipped from content diff: {path_text} "
                "(raw data, binary, large, or unreadable file)."
            )
            continue
        path = repo_root / path_text
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            chunks.append(f"Untracked file skipped from content diff: {path_text} ({error})")
            continue
        new_lines = text.splitlines(keepends=True)
        diff = difflib.unified_diff(
            [],
            [line.rstrip("\n") for line in new_lines],
            fromfile="/dev/null",
            tofile=path_text,
            lineterm="",
        )
        chunks.append("\n".join(diff))
    return "\n\n".join(chunk.rstrip() for chunk in chunks if chunk.strip())


def added_diff_lines_for_path(diff_text: str, path_text: str) -> list[str]:
    lines: list[str] = []
    active = False
    for line in diff_text.splitlines():
        if line.startswith("diff --git "):
            active = f" a/{path_text} " in line or f" b/{path_text}" in line
            continue
        if line.startswith("+++ "):
            active = line == f"+++ {path_text}" or line == f"+++ b/{path_text}"
            continue
        if line.startswith("--- "):
            continue
        if active and line.startswith("+"):
            lines.append(line)
    return lines


def line_looks_like_dangerous_operation(line: str) -> bool:
    stripped = line[1:].strip() if line.startswith("+") else line.strip()
    if not stripped or stripped.startswith("#"):
        return False
    if stripped[0] in {'"', "'"}:
        return False

    lower = stripped.lower()
    return any(marker in lower for marker in DANGEROUS_DIFF_MARKERS)


def path_lane_reasons(path_text: str, entry: ChangedFile, diff_text: str) -> tuple[str, list[str]]:
    lower = path_text.lower()
    suffix = Path(path_text).suffix.lower()
    reasons: list[str] = []

    if is_raw_data_path(path_text):
        reasons.append("possible raw data path")
    if "D" in entry.status_codes:
        reasons.append("deleted file")
    if "R" in entry.status_codes:
        reasons.append("renamed file")
    if any(marker in lower for marker in SECRET_OR_LOCAL_PATH_MARKERS):
        reasons.append("secret, credential, or local-only path marker")
    if any(marker in lower for marker in HIGH_RISK_PATH_MARKERS):
        reasons.append("security, workflow, ignore, or config path")

    if reasons:
        return "high_risk_lane", reasons

    added_lines = added_diff_lines_for_path(diff_text, path_text)
    if any(line_looks_like_dangerous_operation(line) for line in added_lines):
        return "high_risk_lane", ["possible dangerous git or filesystem operation in diff"]

    if suffix in FAST_LANE_EXTENSIONS and not any(code in entry.status_codes for code in ("?", "A")):
        return "fast_lane", ["documentation/text-only tracked change"]

    if path_text.startswith("tests/") and suffix == ".py":
        return "fast_lane", ["test-only Python change"]

    if suffix in SOURCE_EXTENSIONS:
        return "review_lane", ["source, config, or structured data change"]

    return "review_lane", ["default conservative review"]


def global_high_risk_reasons(changed: dict[str, ChangedFile], relevant_diff: str) -> list[str]:
    reasons: list[str] = []
    if len(changed) > BROAD_CHANGE_FILE_THRESHOLD:
        reasons.append(
            f"broad change set with {len(changed)} changed files; require extra review before commit"
        )

    status_codes = {code for entry in changed.values() for code in entry.status_codes}
    if "D" in status_codes:
        reasons.append("one or more files are deleted")
    if "R" in status_codes:
        reasons.append("one or more files are renamed")

    if any(is_raw_data_path(path_text) for path_text in changed):
        reasons.append("one or more changed paths look like raw data or large instrument output")

    added_lines = [line for line in relevant_diff.splitlines() if line.startswith("+")]
    if any(line_looks_like_dangerous_operation(line) for line in added_lines):
        reasons.append(
            "diff contains added lines that look like git or filesystem operations; verify they are safe and intentional"
        )

    return reasons


def build_human_readable_summary(
    changed: dict[str, ChangedFile],
    lanes: dict[str, list[str]],
    safety_output: str,
    syntax_output: str,
    pytest_output: str,
) -> str:
    if not changed:
        return "No repository changes were detected."

    lane_counts = {
        lane_name: sum(1 for item in items if item != "- (none)")
        for lane_name, items in lanes.items()
    }
    changed_count = len(changed)
    changed_word = "file" if changed_count == 1 else "files"

    safety_status = "PASS" if "== Summary ==\nPASS" in safety_output or "Exit code: 0" in safety_output else "CHECK"
    syntax_status = "PASS" if syntax_output.startswith("PASS") or syntax_output == "No changed Python files found." else "CHECK"
    pytest_status = "not run"
    if pytest_output.startswith("PASS"):
        pytest_status = "PASS"
    elif pytest_output.startswith("FAIL"):
        pytest_status = "FAIL"

    return "\n".join(
        [
            f"This packet reviews {changed_count} changed {changed_word}.",
            f"Lane counts: fast={lane_counts['fast_lane']}, review={lane_counts['review_lane']}, high_risk={lane_counts['high_risk_lane']}.",
            f"Safety check: {safety_status}. Python syntax check: {syntax_status}. Pytest: {pytest_status}.",
            "Commit should include only the intended changed files, not generated exports.",
        ]
    )


def build_expected_behavior(changed: dict[str, ChangedFile]) -> str:
    intended_paths = intended_commit_candidate_paths(changed)
    if intended_paths:
        changed_paths = ", ".join(f"`{path}`" for path in intended_paths)
    else:
        changed_paths = "no repository files"

    return "\n".join(
        [
            "- Review should cover exactly the changed paths listed in this packet.",
            f"- Intended commit candidate paths: {changed_paths}.",
            "- Generated `exports/final_review/` packets should not be committed.",
            "- No raw data, large instrument outputs, local absolute paths, credentials, tokens, or secrets should be introduced.",
            "- The workflow script should not stage, commit, push, delete, move, rename, or modify repository files outside its documented output directory.",
            "- Any high-risk lane item should be resolved or explicitly accepted before commit.",
        ]
    )


def is_generated_export_path(path_text: str) -> bool:
    return path_text == "exports" or path_text.startswith("exports/")


def intended_commit_candidate_paths(changed: dict[str, ChangedFile]) -> list[str]:
    return sorted(path for path in changed if not is_generated_export_path(path))


def workflow_generated_artifact_paths(
    changed_before_refresh: dict[str, ChangedFile],
    changed_after_refresh: dict[str, ChangedFile],
    change_spec: ChangeSpec | None,
) -> set[str]:
    """Identify only HANDOFF changes created by this final-review invocation."""

    if HANDOFF_NAME not in changed_after_refresh:
        return set()
    if HANDOFF_NAME in changed_before_refresh:
        return set()

    if change_spec is not None:
        scope = parse_change_spec_file_scope(change_spec.content)
        if any(
            path_matches_scope_entry(HANDOFF_NAME, entry)
            for entry in scope.positive
        ):
            return set()

    return {HANDOFF_NAME}


def exclude_workflow_generated_artifacts(
    changed: dict[str, ChangedFile],
    workflow_artifacts: set[str],
) -> dict[str, ChangedFile]:
    return {
        path: entry for path, entry in changed.items() if path not in workflow_artifacts
    }


def format_workflow_generated_artifacts(paths: set[str]) -> str:
    if not paths:
        return "- (none)"
    return "\n".join(
        f"- `{path}`: generated after the pre-review snapshot; excluded from "
        "normal commit-candidate and scope calculations"
        for path in sorted(paths)
    )


def is_secret_or_local_path(path_text: str) -> bool:
    lower = path_text.lower()
    return any(marker.lower() in lower for marker in SECRET_OR_LOCAL_PATH_MARKERS)


def is_image_or_pdf_path(path_text: str) -> bool:
    suffix = Path(path_text).suffix.lower()
    return suffix in {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".pdf"}


def path_matches_scope_entry(path_text: str, scope_entry: str) -> bool:
    entry = normalize_scope_path(scope_entry)
    if not entry:
        return False

    lower_entry = entry.casefold()
    lower_path = path_text.casefold()

    if entry.endswith("/"):
        return lower_path.startswith(lower_entry)
    if lower_path == lower_entry:
        return True

    semantic_checks = {
        "raw data": is_raw_data_path(path_text),
        "experiment records": lower_path.startswith("experiments/"),
        "papers": "paper" in lower_path or lower_path.endswith(".pdf"),
        "images": is_image_or_pdf_path(path_text),
        "pdfs": lower_path.endswith(".pdf"),
        "notebooks": lower_path.endswith(".ipynb"),
        "generated exports": is_generated_export_path(path_text),
        "local workspace state files": "workspace" in lower_path,
    }
    if semantic_checks.get(lower_entry, False):
        return True

    if any(word in lower_entry for word in ("secret", "credential", "token", "private key")):
        return is_secret_or_local_path(path_text)

    return False


def paths_matching_scope(paths: list[str], scope_entries: list[str]) -> list[str]:
    return sorted(
        path
        for path in paths
        if any(path_matches_scope_entry(path, entry) for entry in scope_entries)
    )


def paths_outside_positive_scope(paths: list[str], positive_entries: list[str]) -> list[str]:
    if not positive_entries:
        return sorted(paths)
    return sorted(
        path
        for path in paths
        if not any(path_matches_scope_entry(path, entry) for entry in positive_entries)
    )


def status_from_command_output(output: str) -> str:
    if "Exit code: 0" not in output:
        return "FAIL"
    if "== Summary ==\nPASS" in output:
        return "PASS"
    if "== Summary ==\nWARN" in output:
        return "PASS WITH WARNINGS"
    return "PASS"


def unsafe_marker_status_from_output(output: str) -> str:
    if "Unsafe local/path markers were found" in output:
        return "FAIL"
    if "OK: no unsafe markers found" in output:
        return "PASS"
    return "UNKNOWN"


def python_syntax_status_from_output(output: str) -> str:
    if output == "No changed Python files found.":
        return "NOT APPLICABLE"
    if output.startswith("PASS"):
        return "PASS"
    if output.startswith("FAIL"):
        return "FAIL"
    return "CHECK"


def pytest_status_from_output(output: str) -> str:
    if output.startswith("PASS"):
        return "PASS"
    if output.startswith("FAIL"):
        return "FAIL"
    if "does not appear to have tests" in output:
        return "NOT APPLICABLE"
    if "pytest does not appear to be available" in output:
        return "NOT RUN"
    return "CHECK"


def dangerous_executable_paths(
    changed: dict[str, ChangedFile],
    relevant_diff: str,
) -> list[str]:
    executable_suffixes = {".py", ".sh", ".bash", ".zsh"}
    paths: list[str] = []
    for path_text in sorted(changed):
        if Path(path_text).suffix.lower() not in executable_suffixes:
            continue
        added_lines = added_diff_lines_for_path(relevant_diff, path_text)
        if any(line_looks_like_dangerous_operation(line) for line in added_lines):
            paths.append(path_text)
    return paths


def deletion_or_rename_paths(changed: dict[str, ChangedFile]) -> list[str]:
    return sorted(
        path
        for path, entry in changed.items()
        if "D" in entry.status_codes or "R" in entry.status_codes
    )


def choose_spec_review_decision(facts: SpecReviewFacts) -> tuple[str, list[str]]:
    block_reasons: list[str] = []
    revert_reasons: list[str] = []
    review_reasons: list[str] = []

    if facts.forbidden_paths:
        block_reasons.append("forbidden-list paths changed")
    if facts.staged_generated_export_paths or facts.generated_exports_in_intended_commit:
        block_reasons.append("generated exports are staged or listed as intended commit candidates")
    if facts.safety_status == "FAIL":
        block_reasons.append("safety check failed")
    if facts.python_syntax_status == "FAIL":
        block_reasons.append("Python syntax check failed")
    if facts.pytest_status == "FAIL":
        block_reasons.append("pytest failed")
    if facts.unsafe_marker_status == "FAIL":
        block_reasons.append("unsafe local/path/secret markers were detected")

    if facts.deletion_or_rename_paths:
        revert_reasons.append("deletions, moves, or renames appear in the change set")
    if facts.outside_positive_paths:
        revert_reasons.append("changed files appear outside the positive file list")

    if facts.expected_branch and not facts.branch_matches:
        review_reasons.append("expected branch does not match current branch")
    if facts.missing_metadata:
        review_reasons.append("required spec metadata is missing")
    if facts.file_scope.missing_sections:
        review_reasons.append("one or more spec file-scope lists are missing or empty")
    if facts.negative_paths:
        review_reasons.append("negative-list paths changed")
    if facts.safety_status == "PASS WITH WARNINGS":
        review_reasons.append("safety check passed with warnings")
    if facts.pytest_status in {"NOT RUN", "CHECK"}:
        review_reasons.append("pytest was not run or needs interpretation")
    if facts.python_syntax_status == "CHECK":
        review_reasons.append("Python syntax status needs interpretation")
    if facts.unsafe_marker_status == "UNKNOWN":
        review_reasons.append("unsafe marker status was not available")
    if facts.broad_change_warning != "none":
        review_reasons.append(facts.broad_change_warning)
    if facts.dangerous_executable_paths:
        review_reasons.append("dangerous Git/filesystem command text appears in executable files")
    if facts.generated_export_paths:
        review_reasons.append("generated exports are present and must stay out of the commit")

    if block_reasons:
        return "BLOCK COMMIT", block_reasons
    if revert_reasons:
        return "REVERT OR EXPLAIN", revert_reasons + review_reasons
    if review_reasons:
        return "REVIEW REQUIRED", review_reasons
    return "AUTO-APPROVE CANDIDATE", [
        "all conservative spec-based checks passed; ChatGPT/human review is still required"
    ]


def build_spec_review_facts(
    change_spec: ChangeSpec,
    branch: str,
    changed: dict[str, ChangedFile],
    safety_output: str,
    syntax_output: str,
    pytest_output: str,
    relevant_diff: str,
) -> SpecReviewFacts:
    file_scope = parse_change_spec_file_scope(change_spec.content)
    missing_metadata = [field for field in SPEC_METADATA_FIELDS if field not in change_spec.metadata]
    expected_branch = change_spec.metadata.get("Expected branch")
    branch_matches = expected_branch == branch if expected_branch else False

    intended_paths = intended_commit_candidate_paths(changed)
    generated_export_paths = sorted(path for path in changed if is_generated_export_path(path))
    staged_exports = sorted(
        path for path in generated_export_paths if "staged diff" in changed[path].sources
    )
    generated_exports_in_intended = [
        path for path in intended_paths if is_generated_export_path(path)
    ]

    outside_positive = paths_outside_positive_scope(intended_paths, file_scope.positive)
    negative_paths = paths_matching_scope(intended_paths, file_scope.negative)
    forbidden_paths = paths_matching_scope(intended_paths, file_scope.forbidden)

    non_export_count = len(intended_paths)
    broad_warning = (
        f"broad change warning: {non_export_count} intended commit candidate paths"
        if non_export_count > BROAD_CHANGE_FILE_THRESHOLD
        else "none"
    )

    facts = SpecReviewFacts(
        file_scope=file_scope,
        missing_metadata=missing_metadata,
        expected_branch=expected_branch,
        branch_matches=branch_matches,
        intended_commit_paths=intended_paths,
        outside_positive_paths=outside_positive,
        negative_paths=negative_paths,
        forbidden_paths=forbidden_paths,
        generated_export_paths=generated_export_paths,
        staged_generated_export_paths=staged_exports,
        generated_exports_in_intended_commit=generated_exports_in_intended,
        safety_status=status_from_command_output(safety_output),
        python_syntax_status=python_syntax_status_from_output(syntax_output),
        pytest_status=pytest_status_from_output(pytest_output),
        unsafe_marker_status=unsafe_marker_status_from_output(safety_output),
        broad_change_warning=broad_warning,
        dangerous_executable_paths=dangerous_executable_paths(changed, relevant_diff),
        deletion_or_rename_paths=deletion_or_rename_paths(changed),
        suggested_decision="REVIEW REQUIRED",
        decision_reasons=[],
    )
    decision, reasons = choose_spec_review_decision(facts)
    facts.suggested_decision = decision
    facts.decision_reasons = reasons
    return facts


def inline_path_list(paths: list[str]) -> str:
    return ", ".join(f"`{path}`" for path in paths) if paths else "none"


def format_scope_parse_status(scope: SpecFileScope) -> str:
    counts = (
        f"positive={len(scope.positive)}, "
        f"negative={len(scope.negative)}, "
        f"forbidden={len(scope.forbidden)}"
    )
    if not scope.missing_sections:
        return f"parsed ({counts})"
    return f"parsed with missing/empty sections ({counts}; missing: {', '.join(scope.missing_sections)})"


def format_spec_based_review_summary(facts: SpecReviewFacts, change_spec: ChangeSpec) -> str:
    branch_result = "match" if facts.branch_matches else "mismatch or unavailable"
    metadata_result = "present" if not facts.missing_metadata else "missing: " + ", ".join(facts.missing_metadata)
    export_status = (
        "changed exports: "
        + inline_path_list(facts.generated_export_paths)
        + "; staged exports: "
        + inline_path_list(facts.staged_generated_export_paths)
        + "; exports listed as intended commit candidates: "
        + inline_path_list(facts.generated_exports_in_intended_commit)
    )
    decision_lines = "\n".join(f"- {reason}" for reason in facts.decision_reasons)

    return "\n".join(
        [
            "## Spec-Based Review Summary",
            "",
            "This advisory summary narrows review attention; it is not permission to commit without ChatGPT/human review.",
            "",
            f"- Spec source path: `{change_spec.source_path}`",
            f"- Spec ID: {spec_metadata_value(change_spec, 'Spec ID')}",
            f"- Expected branch vs current branch result: {branch_result}",
            f"- Required metadata fields: {metadata_result}",
            f"- File-scope parsing: {format_scope_parse_status(facts.file_scope)}",
            f"- Intended commit candidate paths: {inline_path_list(facts.intended_commit_paths)}",
            f"- Changed files outside positive file list: {inline_path_list(facts.outside_positive_paths)}",
            f"- Changed files matching negative file list: {inline_path_list(facts.negative_paths)}",
            f"- Changed files matching forbidden file list: {inline_path_list(facts.forbidden_paths)}",
            f"- Generated `exports/` status: {export_status}",
            f"- Safety check status: {facts.safety_status}",
            f"- Python syntax status: {facts.python_syntax_status}",
            f"- Pytest status: {facts.pytest_status}",
            f"- Unsafe marker status: {facts.unsafe_marker_status}",
            f"- Broad-change warning: {facts.broad_change_warning}",
            f"- Dangerous executable-operation warning: {inline_path_list(facts.dangerous_executable_paths)}",
            f"- Deletion/rename warning: {inline_path_list(facts.deletion_or_rename_paths)}",
            f"- Suggested decision: `{facts.suggested_decision}`",
            "",
            "Decision labels: " + ", ".join(f"`{label}`" for label in ADVISORY_DECISIONS) + ".",
            "`AUTO-APPROVE CANDIDATE` still requires ChatGPT/human review before commit.",
            "",
            "Decision reasons:",
            decision_lines or "- none",
            "",
        ]
    )


def classify_changes(changed: dict[str, ChangedFile], relevant_diff: str) -> dict[str, list[str]]:
    lanes = {
        "fast_lane": [],
        "review_lane": [],
        "high_risk_lane": [],
    }
    for path_text in sorted(changed):
        lane, reasons = path_lane_reasons(path_text, changed[path_text], relevant_diff)
        status = "".join(sorted(changed[path_text].status_codes)) or "changed"
        lanes[lane].append(f"- `{path_text}` ({status}): {', '.join(reasons)}")

    for reason in global_high_risk_reasons(changed, relevant_diff):
        lanes["high_risk_lane"].append(f"- (overall): {reason}")

    for lane_name in lanes:
        if not lanes[lane_name]:
            lanes[lane_name].append("- (none)")
    return lanes


def format_changed_files(changed: dict[str, ChangedFile]) -> str:
    if not changed:
        return "(none)"
    lines = []
    for path_text in sorted(changed):
        entry = changed[path_text]
        status = "".join(sorted(entry.status_codes)) or "changed"
        sources = ", ".join(sorted(entry.sources))
        lines.append(f"{status:4} {path_text} [{sources}]")
    return "\n".join(lines)


def build_packet(
    generated_at: str,
    repo_root: Path,
    branch: str,
    status_text: str,
    changed: dict[str, ChangedFile],
    lanes: dict[str, list[str]],
    human_summary: str,
    expected_behavior: str,
    repository_safety_output: str,
    safety_output: str,
    syntax_output: str,
    pytest_output: str,
    recent_commits: str,
    diff_summary: str,
    relevant_diff: str,
    workflow_generated_artifacts: set[str] | None = None,
    original_change_spec: ChangeSpec | None = None,
    spec_based_review_summary: str | None = None,
) -> str:
    workflow_generated_artifacts = workflow_generated_artifacts or set()
    raw_skips = [path for path in sorted(changed) if is_raw_data_path(path)]
    raw_skip_text = "\n".join(f"- `{path}`" for path in raw_skips) if raw_skips else "- (none)"

    reviewer_instructions = [
        "# Final Review Packet",
        "",
        "## Reviewer Instructions For ChatGPT",
        "",
        "You are reviewing a conservative pre-commit packet for a human-supervised repository change.",
        "",
        "Priorities:",
        "- Decide whether the current change is safe to commit.",
        "- Flag accidental raw data, local path, credential, token, or secret exposure.",
        "- Flag dangerous Git or filesystem operations.",
        "- Flag missing tests, failed checks, risky deletions, unexpected generated files, and broad changes.",
    ]
    if original_change_spec is not None:
        reviewer_instructions.append(
            "- Compare the actual diff against the Original Change Spec's expected behavior and scope."
        )
    reviewer_instructions.extend(
        [
            "- Explain concerns plainly and recommend specific fixes before commit.",
            "- Do not suggest destructive cleanup commands unless the human explicitly asks for them.",
            "",
            "Explicit review questions:",
            "- Is this safe to commit?",
            "- Are there accidental raw data / local path / secret exposures?",
            "- Are there dangerous git or filesystem operations?",
        ]
    )
    if original_change_spec is not None:
        reviewer_instructions.extend(
            [
                "- Does the actual diff match the original expected behavior and stay within scope?",
            ]
        )

    original_change_spec_section: list[str] = []
    if original_change_spec is not None:
        spec_summary_section = [spec_based_review_summary, ""] if spec_based_review_summary else []
        original_change_spec_section = [
            format_change_spec_identity(original_change_spec, branch),
            *spec_summary_section,
            "## Original Change Spec",
            "",
            markdown_code_block(original_change_spec.content, "markdown"),
            "",
        ]

    return "\n".join(
        reviewer_instructions
        + [
            "",
            "## Packet Metadata",
            "",
            f"- Generated at: {generated_at}",
            f"- Repository: `{repo_root}`",
            (
                "- Output policy: this script writes `HANDOFF.md` and "
                f"`{('/'.join(OUTPUT_ROOT_PARTS))}/<timestamp>/{PACKET_NAME}`."
            ),
            "",
            "## Git Branch",
            "",
            markdown_code_block(branch),
            "",
            "## Git Status",
            "",
            markdown_code_block(status_text),
            "",
            "## Workflow-Generated Artifacts",
            "",
            format_workflow_generated_artifacts(workflow_generated_artifacts),
            "",
            "## Changed Files",
            "",
            markdown_code_block(format_changed_files(changed)),
            "",
            "## Human-Readable Summary",
            "",
            markdown_code_block(human_summary),
            "",
            "## Expected Behavior / Review Checklist",
            "",
            expected_behavior,
            "",
        ]
        + original_change_spec_section
        + [
            "## Lane Classification",
            "",
            "### fast_lane",
            "\n".join(lanes["fast_lane"]),
            "",
            "### review_lane",
            "\n".join(lanes["review_lane"]),
            "",
            "### high_risk_lane",
            "\n".join(lanes["high_risk_lane"]),
            "",
            "## Repository Safety Validation Output",
            "",
            markdown_code_block(repository_safety_output),
            "",
            "## Safety Check Output",
            "",
            markdown_code_block(safety_output),
            "",
            "## Python Syntax Check Output",
            "",
            markdown_code_block(syntax_output),
            "",
            "## Pytest Output",
            "",
            markdown_code_block(pytest_output),
            "",
            "## Recent Commits",
            "",
            markdown_code_block(recent_commits),
            "",
            "## Diff Summary",
            "",
            markdown_code_block(diff_summary),
            "",
            "## Raw Data Paths Skipped From Content Diff",
            "",
            raw_skip_text,
            "",
            "## Relevant Diff",
            "",
            markdown_code_block(relevant_diff, "diff"),
            "",
        ]
    )


def create_output_dir(repo_root: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = repo_root.joinpath(*OUTPUT_ROOT_PARTS, timestamp)
    output_dir.mkdir(parents=True, exist_ok=False)
    return output_dir


def write_packet(output_dir: Path, packet: str) -> Path:
    packet_path = output_dir / PACKET_NAME
    packet_path.write_text(packet.rstrip("\n") + "\n", encoding="utf-8")
    return packet_path


def refresh_handoff(repo_root: Path, packet_path: Path) -> None:
    handoff_path = Path(__file__).resolve().with_name("handoff.py")
    spec = importlib.util.spec_from_file_location("ai_research_os_handoff", handoff_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load Scripts/handoff.py.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.update_handoff(
        repo_root,
        event="Generated final review packet",
        packet_path=packet_path,
        safe_stopping_point="A final review packet has been generated for human review before commit.",
        next_action="Upload FINAL_REVIEW_PACKET.md to ChatGPT for review before any commit.",
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a final human-supervised review packet before committing changes."
    )
    spec_group = parser.add_mutually_exclusive_group()
    spec_group.add_argument(
        "--spec",
        type=Path,
        help="path to a CHANGE_SPEC.md file to include in the final review packet",
    )
    spec_group.add_argument(
        "--latest-spec",
        action="store_true",
        help="include the newest exports/change_start/*/CHANGE_SPEC.md file",
    )
    spec_group.add_argument(
        "--active-spec",
        action="store_true",
        help="include exports/active_change/CHANGE_SPEC.md in the final review packet",
    )
    return parser.parse_args(argv)


def find_latest_change_spec(repo_root: Path) -> Path:
    spec_root = repo_root.joinpath(*CHANGE_START_ROOT_PARTS)
    candidates = [path for path in spec_root.glob(f"*/{CHANGE_SPEC_NAME}") if path.is_file()]
    if not candidates:
        raise RuntimeError(
            f"--latest-spec was requested, but no {CHANGE_SPEC_NAME} exists under "
            f"{'/'.join(CHANGE_START_ROOT_PARTS)}/*/."
        )
    return max(candidates, key=lambda path: path.stat().st_mtime)


def read_change_spec(repo_root: Path, spec_path: Path) -> ChangeSpec:
    path = spec_path.expanduser()
    if not path.is_absolute():
        path = repo_root / path
    path = path.resolve()
    try:
        content_bytes = path.read_bytes()
        content = content_bytes.decode("utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise RuntimeError(f"Could not read change spec {path}: {error}") from error
    return ChangeSpec(
        source_path=path,
        content=content,
        sha256=hashlib.sha256(content_bytes).hexdigest(),
        metadata=parse_change_spec_metadata(content),
    )


def load_original_change_spec(repo_root: Path, args: argparse.Namespace) -> ChangeSpec | None:
    if args.active_spec:
        return read_change_spec(repo_root, repo_root.joinpath(*ACTIVE_CHANGE_SPEC_PATH_PARTS))
    if args.latest_spec:
        return read_change_spec(repo_root, find_latest_change_spec(repo_root))
    if args.spec is not None:
        return read_change_spec(repo_root, args.spec)
    return None


def redact_local_paths(text: str, repo_root: Path | None = None, home: Path | None = None) -> str:
    replacements = (
        (repo_root.resolve() if repo_root is not None else find_repo_root(), "<REPO_ROOT>"),
        (home.resolve() if home is not None else Path.home().resolve(), "<HOME>"),
    )
    redacted = text
    for path, placeholder in replacements:
        path_text = str(path)
        if path_text:
            redacted = redacted.replace(path_text, placeholder)
    return redacted


def reveal_packet_in_finder(packet_path: Path) -> None:
    if sys.platform != "darwin":
        return

    # Convenience feature for local macOS use.
    result = subprocess.run(["open", "-R", str(packet_path)], check=False)
    if result.returncode != 0:
        print("Warning: could not reveal review packet in Finder.", file=sys.stderr)


def main() -> int:
    try:
        args = parse_args()
        repo_root = find_repo_root()
        original_change_spec = load_original_change_spec(repo_root, args)
        output_dir = create_output_dir(repo_root)
        packet_path = output_dir / PACKET_NAME
        pre_refresh_status_text = require_success(
            run_git(repo_root, ["status", "--short"], "pre-refresh status")
        )
        changed_before_refresh = parse_status(pre_refresh_status_text)
        try:
            refresh_handoff(repo_root, packet_path)
        except Exception as error:
            print(f"Warning: could not update HANDOFF.md: {error}", file=sys.stderr)

        branch = require_success(run_git(repo_root, ["branch", "--show-current"], "branch")).strip()
        if not branch:
            head = require_success(run_git(repo_root, ["rev-parse", "--short", "HEAD"], "head")).strip()
            branch = f"detached at {head}"

        status_text = require_success(run_git(repo_root, ["status", "--short"], "status"))
        changed = parse_status(status_text)

        unstaged_name_status = require_success(run_git(repo_root, ["diff", "--name-status"], "unstaged names"))
        staged_name_status = require_success(
            run_git(repo_root, ["diff", "--cached", "--name-status"], "staged names")
        )
        untracked = require_success(
            run_git(repo_root, ["ls-files", "--others", "--exclude-standard"], "untracked")
        )
        add_name_status(changed, unstaged_name_status, "unstaged diff")
        add_name_status(changed, staged_name_status, "staged diff")
        add_untracked(changed, untracked)
        workflow_artifacts = workflow_generated_artifact_paths(
            changed_before_refresh,
            changed,
            original_change_spec,
        )
        review_changed = exclude_workflow_generated_artifacts(
            changed,
            workflow_artifacts,
        )

        recent_commits = require_success(
            run_git(repo_root, ["log", "-5", "--oneline", "--decorate"], "recent commits")
        )

        safe_paths = diffable_paths(review_changed)
        unstaged_diff = git_diff_for_paths(repo_root, safe_paths, cached=False)
        staged_diff = git_diff_for_paths(repo_root, safe_paths, cached=True)
        unstaged_stat = git_diff_stat_for_paths(repo_root, safe_paths, cached=False)
        staged_stat = git_diff_stat_for_paths(repo_root, safe_paths, cached=True)
        new_file_diff = untracked_text_diff(repo_root, changed)

        diff_summary = "\n\n".join(
            part
            for part in (
                "Unstaged diff stat:\n" + (unstaged_stat.rstrip() or "(none)"),
                "Staged diff stat:\n" + (staged_stat.rstrip() or "(none)"),
            )
            if part.strip()
        )
        relevant_diff = "\n\n".join(
            part
            for part in (
                "Unstaged diff:\n" + (unstaged_diff.rstrip() or "(none)"),
                "Staged diff:\n" + (staged_diff.rstrip() or "(none)"),
                "Untracked text file diff:\n" + (new_file_diff.rstrip() or "(none)"),
            )
            if part.strip()
        )
        relevant_diff = truncate_text(relevant_diff, MAX_DIFF_CHARS, "relevant diff")

        repository_safety_result = run_repository_safety_validation(repo_root)
        repository_safety_output = "\n".join(
            [
                f"Command: {' '.join(repository_safety_result.command)}",
                f"Exit code: {repository_safety_result.returncode}",
                repository_safety_result.combined_output() or "(no output)",
            ]
        )

        safety_result = run_safety_check(repo_root)
        safety_output = "\n".join(
            [
                f"Command: {' '.join(safety_result.command)}",
                f"Exit code: {safety_result.returncode}",
                safety_result.combined_output() or "(no output)",
            ]
        )

        syntax_output = run_python_syntax_checks(
            repo_root,
            changed_python_files(repo_root, review_changed),
        )
        pytest_output = run_pytest_if_available(repo_root)
        lanes = classify_changes(review_changed, relevant_diff)
        spec_based_review_summary = None
        if original_change_spec is not None:
            spec_facts = build_spec_review_facts(
                original_change_spec,
                branch,
                review_changed,
                safety_output,
                syntax_output,
                pytest_output,
                relevant_diff,
            )
            spec_based_review_summary = format_spec_based_review_summary(
                spec_facts,
                original_change_spec,
            )

        packet = build_packet(
            generated_at=datetime.now().isoformat(timespec="seconds"),
            repo_root=repo_root,
            branch=branch,
            status_text=status_text,
            changed=review_changed,
            lanes=lanes,
            human_summary=build_human_readable_summary(review_changed, lanes, safety_output, syntax_output, pytest_output),
            expected_behavior=build_expected_behavior(review_changed),
            repository_safety_output=repository_safety_output,
            safety_output=safety_output,
            syntax_output=syntax_output,
            pytest_output=pytest_output,
            recent_commits=recent_commits,
            diff_summary=diff_summary,
            relevant_diff=relevant_diff,
            workflow_generated_artifacts=workflow_artifacts,
            original_change_spec=original_change_spec,
            spec_based_review_summary=spec_based_review_summary,
        )
        packet = redact_local_paths(packet, repo_root=repo_root)

        packet_path = write_packet(output_dir, packet)
        reveal_packet_in_finder(packet_path)
    except RuntimeError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    except FileExistsError as error:
        print(f"Error: output directory already exists: {error.filename}", file=sys.stderr)
        return 1

    print(packet_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
