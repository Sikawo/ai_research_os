#!/usr/bin/env python3
"""
Prepare a human-controlled commit after FINAL_REVIEW_PACKET.md approval.

This helper is intentionally conservative. It may remove generated local
exports after guard checks pass, but it never stages, commits, pushes, pulls,
fetches, switches branches, creates pull requests, or uploads anything.
"""

from __future__ import annotations

import argparse
import re
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TextIO


FINAL_REVIEW_PACKET_NAME = "FINAL_REVIEW_PACKET.md"
FINAL_REVIEW_ROOT = Path("exports") / "final_review"
EXPORTS_ROOT = Path("exports")
ACTIVE_SPEC_PATH = Path("exports") / "active_change" / "CHANGE_SPEC.md"
KNOWN_GENERATED_EXPORT_DIRS = {
    "active_change",
    "archived_change_specs",
    "case_review",
    "change_start",
    "daily_status",
    "daily_status_review",
    "doc_sync_context",
    "doc_sync_review",
    "final_review",
    "review_context",
}
KNOWN_GENERATED_EXPORT_SUFFIXES = {
    ".md",
    ".json",
    ".txt",
}
@dataclass
class CommandResult:
    command: list[str]
    returncode: int
    stdout: str = ""
    stderr: str = ""

    def combined_output(self) -> str:
        parts = [part.rstrip() for part in (self.stdout, self.stderr) if part.strip()]
        return "\n".join(parts)


@dataclass
class PacketExpectation:
    packet_path: Path
    expected_paths: list[str]
    source: str
    content: str


@dataclass
class CleanupResult:
    removed: bool = False
    skipped: bool = False
    blocked: bool = False
    messages: list[str] = field(default_factory=list)


@dataclass
class ChangedPath:
    path: str
    status: str

    @property
    def is_export(self) -> bool:
        return self.path == "exports" or self.path.startswith("exports/")

    @property
    def is_tracked_change(self) -> bool:
        return self.status != "??"


def run_command(repo_root: Path, command: list[str]) -> CommandResult:
    result = subprocess.run(
        command,
        cwd=repo_root,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return CommandResult(
        command=command,
        returncode=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
    )


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


def repo_relative_path(repo_root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def normalize_repo_path(path_text: str) -> str:
    path = path_text.strip().strip("`").strip()
    path = path.rstrip(".")
    return path.replace("\\", "/")


def is_safe_repo_relative_path(path_text: str) -> bool:
    if not path_text:
        return False
    path = Path(path_text)
    if path.is_absolute():
        return False
    return ".." not in path.parts


def parse_backtick_paths(text: str) -> list[str]:
    paths: list[str] = []
    seen: set[str] = set()
    for raw_path in re.findall(r"`([^`]+)`", text):
        path = normalize_repo_path(raw_path)
        if path == "no repository files":
            continue
        if not is_safe_repo_relative_path(path):
            continue
        if path not in seen:
            paths.append(path)
            seen.add(path)
    return paths


def parse_intended_commit_paths(packet_text: str) -> tuple[list[str], str]:
    for line in packet_text.splitlines():
        if "Intended commit candidate paths:" not in line:
            continue
        paths = parse_backtick_paths(line)
        if paths:
            return paths, "Intended commit candidate paths"

        _, value = line.split("Intended commit candidate paths:", 1)
        fallback_paths = [
            normalize_repo_path(part)
            for part in value.split(",")
            if is_safe_repo_relative_path(normalize_repo_path(part))
        ]
        if fallback_paths and fallback_paths != ["no repository files"]:
            return fallback_paths, "Intended commit candidate paths"

    changed_paths = parse_changed_files_section(packet_text)
    if changed_paths:
        return changed_paths, "Changed Files fallback"
    return [], "not found"


def parse_changed_files_section(packet_text: str) -> list[str]:
    lines = packet_text.splitlines()
    in_section = False
    in_block = False
    paths: list[str] = []
    seen: set[str] = set()

    for line in lines:
        if line.startswith("## "):
            if in_section:
                break
            in_section = line.strip() == "## Changed Files"
            continue
        if not in_section:
            continue
        if line.startswith("```"):
            in_block = not in_block
            continue
        if not in_block:
            continue

        stripped = line.strip()
        if not stripped or stripped == "(none)":
            continue

        match = re.match(r"^\S+\s+(.+?)(?:\s+\[|$)", stripped)
        if not match:
            continue
        path = normalize_repo_path(match.group(1))
        if not is_safe_repo_relative_path(path):
            continue
        if path not in seen:
            paths.append(path)
            seen.add(path)
    return paths


def find_latest_packet(repo_root: Path) -> Path:
    candidates = [
        path
        for path in (repo_root / FINAL_REVIEW_ROOT).glob(f"*/{FINAL_REVIEW_PACKET_NAME}")
        if path.is_file()
    ]
    if not candidates:
        raise RuntimeError(
            f"No {FINAL_REVIEW_PACKET_NAME} found under {FINAL_REVIEW_ROOT.as_posix()}/*/."
        )
    return max(candidates, key=lambda path: path.stat().st_mtime)


def read_packet(repo_root: Path, packet_arg: Path | None) -> PacketExpectation:
    packet_path = packet_arg.expanduser() if packet_arg is not None else find_latest_packet(repo_root)
    if not packet_path.is_absolute():
        packet_path = repo_root / packet_path
    packet_path = packet_path.resolve()
    try:
        content = packet_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise RuntimeError(f"Could not read final review packet {packet_path}: {error}") from error

    expected_paths, source = parse_intended_commit_paths(content)
    return PacketExpectation(
        packet_path=packet_path,
        expected_paths=expected_paths,
        source=source,
        content=content,
    )


def status_path(line: str) -> str:
    body = line[3:].strip()
    if " -> " in body:
        return body.split(" -> ", 1)[1].strip()
    return body


def parse_git_status(status_text: str) -> list[ChangedPath]:
    changed: list[ChangedPath] = []
    for line in status_text.splitlines():
        if not line.strip():
            continue
        path = status_path(line)
        if path:
            changed.append(ChangedPath(path=path, status=line[:2]))
    return changed


def relative_export_paths(exports_root: Path) -> list[str]:
    if not exports_root.exists():
        return []
    paths: list[str] = []
    for path in exports_root.rglob("*"):
        try:
            rel = path.relative_to(exports_root).as_posix()
        except ValueError:
            continue
        if rel:
            paths.append(rel)
    return sorted(paths)


def is_generated_export_path(rel_path: str) -> bool:
    parts = Path(rel_path).parts
    if not parts:
        return True
    if parts[0] in KNOWN_GENERATED_EXPORT_DIRS:
        return True
    if len(parts) == 1 and Path(parts[0]).suffix in KNOWN_GENERATED_EXPORT_SUFFIXES:
        return True
    if parts[-1] == ".DS_Store":
        return True
    return False


def cleanup_exports(
    repo_root: Path,
    packet: PacketExpectation,
    status_before_cleanup: str,
    *,
    no_clean: bool,
    runner=run_command,
) -> CleanupResult:
    result = CleanupResult()
    exports_root = repo_root / EXPORTS_ROOT

    if no_clean:
        result.skipped = True
        result.messages.append("SKIP: --no-clean was provided; generated exports were not removed.")
        return result

    if not exports_root.exists():
        result.skipped = True
        result.messages.append("SKIP: exports/ does not exist.")
        return result

    if any(path == "exports" or path.startswith("exports/") for path in packet.expected_paths):
        result.blocked = True
        result.messages.append("BLOCK: exports/ is listed as an intended commit candidate path.")
        return result

    tracked_exports = runner(repo_root, ["git", "ls-files", "exports"])
    if tracked_exports.returncode != 0:
        result.blocked = True
        result.messages.append("BLOCK: could not verify tracked files under exports/.")
        details = tracked_exports.combined_output()
        if details:
            result.messages.append(details)
        return result

    tracked_paths = [line.strip() for line in tracked_exports.stdout.splitlines() if line.strip()]
    if tracked_paths:
        result.blocked = True
        result.messages.append("BLOCK: tracked files exist under exports/; cleanup refused.")
        result.messages.extend(f"  - {path}" for path in tracked_paths[:20])
        if len(tracked_paths) > 20:
            result.messages.append(f"  - ... {len(tracked_paths) - 20} more")
        return result

    export_tracked_changes = [
        item for item in parse_git_status(status_before_cleanup) if item.is_export and item.is_tracked_change
    ]
    if export_tracked_changes:
        result.blocked = True
        result.messages.append("BLOCK: tracked git status changes exist under exports/; cleanup refused.")
        result.messages.extend(f"  - {item.status} {item.path}" for item in export_tracked_changes)
        return result

    export_paths = relative_export_paths(exports_root)
    suspicious_paths = [path for path in export_paths if not is_generated_export_path(path)]
    if suspicious_paths:
        result.blocked = True
        result.messages.append(
            "BLOCK: exports/ contains paths that do not look like known generated review/output content."
        )
        result.messages.extend(f"  - exports/{path}" for path in suspicious_paths[:20])
        if len(suspicious_paths) > 20:
            result.messages.append(f"  - ... {len(suspicious_paths) - 20} more")
        return result

    try:
        if exports_root.is_symlink() or not exports_root.is_dir():
            result.blocked = True
            result.messages.append("BLOCK: exports/ is not a normal directory.")
            return result
        shutil.rmtree(exports_root)
    except OSError as error:
        result.blocked = True
        result.messages.append(f"BLOCK: could not remove generated exports/: {error}")
        return result

    result.removed = True
    result.messages.append("PASS: removed generated exports/ after safety guards passed.")
    return result


def run_required_checks(repo_root: Path, runner=run_command) -> list[CommandResult]:
    checks = [
        ["git", "diff", "--check"],
        ["git", "diff", "--cached", "--check"],
        ["python3", "Scripts/run_safety_check.py"],
    ]
    return [runner(repo_root, command) for command in checks]


def analyze_changed_paths(changed: list[ChangedPath], expected_paths: list[str]) -> tuple[list[str], list[str], list[str]]:
    changed_paths = {item.path for item in changed}
    expected = set(expected_paths)
    non_export_changed = {path for path in changed_paths if not (path == "exports" or path.startswith("exports/"))}

    unexpected = sorted(path for path in non_export_changed if path not in expected)
    missing = sorted(path for path in expected if path not in changed_paths)
    export_changes = sorted(path for path in changed_paths if path == "exports" or path.startswith("exports/"))
    return unexpected, missing, export_changes


def quote_command(command: list[str]) -> str:
    return " ".join(shlex.quote(part) for part in command)


def suggested_commands(paths: list[str], commit_message: str) -> list[str]:
    if not paths:
        return []
    return [
        quote_command(["git", "add", "--", *paths]),
        quote_command(["git", "commit", "-m", commit_message]),
        quote_command(["git", "push", "origin", "main"]),
    ]


def print_command_result(result: CommandResult, out: TextIO) -> None:
    print(f"$ {quote_command(result.command)}", file=out)
    if result.returncode == 0:
        print("PASS", file=out)
    else:
        print(f"FAIL: exited with code {result.returncode}", file=out)
    output = result.combined_output()
    if output:
        print(output, file=out)


def print_section(title: str, out: TextIO) -> None:
    print(file=out)
    print(f"== {title} ==", file=out)


def print_post_commit_finalize_guidance(repo_root: Path, cleanup: CleanupResult, out: TextIO) -> None:
    active_spec_path = repo_root / ACTIVE_SPEC_PATH
    if active_spec_path.is_file():
        print(file=out)
        print("# After human commit and push, clear the completed active spec once the tree is clean:", file=out)
        print("python3 Scripts/finalize_completed_change.py --archive-active-spec", file=out)
        return

    if cleanup.removed:
        print(file=out)
        print(
            "# Generated exports were already cleaned during prepare; "
            "exports/active_change/CHANGE_SPEC.md may no longer exist to finalize.",
            file=out,
        )


def prepare_commit_after_review(
    repo_root: Path,
    *,
    packet_path: Path | None = None,
    no_clean: bool = False,
    commit_message: str = "Commit approved final review changes",
    runner=run_command,
    out: TextIO = sys.stdout,
) -> int:
    packet = read_packet(repo_root, packet_path)

    print("Post-final-review commit preparation", file=out)
    print(f"Repo root: {repo_root}", file=out)
    print(f"Final review packet: {repo_relative_path(repo_root, packet.packet_path)}", file=out)
    print(f"Expected path source: {packet.source}", file=out)
    if packet.source == "Changed Files fallback":
        print("WARN: intended commit line was unavailable; using Changed Files fallback.", file=out)
    elif packet.source == "not found":
        print("BLOCK: no expected commit paths could be parsed from the packet.", file=out)
    print("Expected commit candidate paths:", file=out)
    if packet.expected_paths:
        for path in packet.expected_paths:
            print(f"  - {path}", file=out)
    else:
        print("  - (none)", file=out)

    status_before = runner(repo_root, ["git", "status", "--short"])
    if status_before.returncode != 0:
        print("FAIL: could not read git status before cleanup.", file=out)
        print(status_before.combined_output(), file=out)
        return 1

    print_section("Generated Export Cleanup", out)
    cleanup = cleanup_exports(
        repo_root,
        packet,
        status_before.stdout,
        no_clean=no_clean,
        runner=runner,
    )
    for message in cleanup.messages:
        print(message, file=out)

    status_after = runner(repo_root, ["git", "status", "--short"])
    if status_after.returncode != 0:
        print("FAIL: could not read git status after cleanup.", file=out)
        print(status_after.combined_output(), file=out)
        return 1

    changed = parse_git_status(status_after.stdout)
    unexpected, missing, export_changes = analyze_changed_paths(changed, packet.expected_paths)

    print_section("Changed Files Check", out)
    if not changed:
        print("PASS: working tree is clean; there is nothing to commit.", file=out)
    elif unexpected:
        print("BLOCK: unexpected non-export changed files remain.", file=out)
        for path in unexpected:
            print(f"  - {path}", file=out)
    else:
        print("PASS: only expected non-export files remain changed.", file=out)

    if missing:
        print("WARN: expected files are not currently changed.", file=out)
        for path in missing:
            print(f"  - {path}", file=out)
    if export_changes:
        print("WARN: exports/ still appears in git status.", file=out)
        for path in export_changes:
            print(f"  - {path}", file=out)

    print_section("Required Checks", out)
    check_results = run_required_checks(repo_root, runner=runner)
    checks_pass = True
    for check in check_results:
        print_command_result(check, out)
        if check.returncode != 0:
            checks_pass = False

    ready_to_commit = (
        packet.source != "not found"
        and not cleanup.blocked
        and checks_pass
        and bool(changed)
        and not unexpected
        and not export_changes
    )

    print_section("Human-Controlled Git Commands", out)
    if ready_to_commit:
        changed_expected_paths = sorted(item.path for item in changed if not item.is_export)
        print("PASS: ready for a human-controlled commit if ChatGPT has approved the packet.", file=out)
        for command in suggested_commands(changed_expected_paths, commit_message):
            print(command, file=out)
        print_post_commit_finalize_guidance(repo_root, cleanup, out)
    elif not changed:
        print("No suggested commit commands because the working tree is clean.", file=out)
    else:
        print("No suggested commit commands because attention is needed first.", file=out)

    if ready_to_commit or (not changed and not cleanup.blocked):
        return 0
    return 1


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare a human-controlled commit after FINAL_REVIEW_PACKET.md approval."
    )
    parser.add_argument(
        "--packet",
        type=Path,
        help="path to a specific FINAL_REVIEW_PACKET.md; defaults to newest exports/final_review/* packet",
    )
    parser.add_argument(
        "--no-clean",
        action="store_true",
        help="perform checks without removing generated exports/",
    )
    parser.add_argument(
        "--commit-message",
        default="Commit approved final review changes",
        help="commit message to print in the suggested human-controlled command",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        repo_root = find_repo_root()
        return prepare_commit_after_review(
            repo_root,
            packet_path=args.packet,
            no_clean=args.no_clean,
            commit_message=args.commit_message,
        )
    except RuntimeError as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
