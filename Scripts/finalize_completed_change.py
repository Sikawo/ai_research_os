#!/usr/bin/env python3
"""
Archive and clear a completed active CHANGE_SPEC.md after human Git actions.

This helper is intentionally narrow. It never stages, commits, pushes, pulls,
fetches, switches branches, creates pull requests, uploads content, or broadly
cleans exports/. It removes only exports/active_change/CHANGE_SPEC.md after all
guards pass, then removes exports/active_change/ only if it is empty.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TextIO


ACTIVE_SPEC_REL = Path("exports") / "active_change" / "CHANGE_SPEC.md"
ACTIVE_DIR_REL = Path("exports") / "active_change"
ARCHIVE_ROOT_REL = Path("exports") / "archived_change_specs"
FINAL_REVIEW_ROOT_REL = Path("exports") / "final_review"
FINAL_REVIEW_PACKET_NAME = "FINAL_REVIEW_PACKET.md"
METADATA_FIELDS = (
    "Spec ID",
    "Target repo",
    "Task",
    "Created for / change class",
)
METADATA_PATTERN = re.compile(r"^- (?P<key>[^:]+):\s*(?P<value>.+?)\s*$")
SAFE_NAME_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")
FORBIDDEN_GIT_COMMANDS = {
    ("git", "add"),
    ("git", "commit"),
    ("git", "push"),
    ("git", "pull"),
    ("git", "fetch"),
    ("git", "switch"),
    ("git", "checkout"),
    ("git", "reset"),
    ("git", "clean"),
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


def run_command(repo_root: Path, command: list[str]) -> CommandResult:
    if tuple(command[:2]) in FORBIDDEN_GIT_COMMANDS:
        raise RuntimeError(f"Forbidden command attempted: {' '.join(command)}")

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


def is_relative_to(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def display_path(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def git_output(repo_root: Path, command: list[str], runner=run_command) -> str:
    result = runner(repo_root, command)
    if result.returncode != 0:
        details = result.combined_output()
        raise RuntimeError(f"{' '.join(command)} failed: {details or '(no output)'}")
    return result.stdout


def parse_metadata(spec_text: str) -> dict[str, str]:
    metadata: dict[str, str] = {}
    in_metadata = False

    for line in spec_text.splitlines():
        if line.strip() == "## Metadata":
            in_metadata = True
            continue
        if in_metadata and line.startswith("## "):
            break
        if not in_metadata:
            continue

        match = METADATA_PATTERN.match(line.strip())
        if match is None:
            continue

        key = match.group("key").strip()
        value = match.group("value").strip().strip("`")
        if key in METADATA_FIELDS:
            metadata[key] = value

    return metadata


def safe_name(value: str | None) -> str:
    raw = (value or "unknown_spec").strip().strip("`") or "unknown_spec"
    cleaned = SAFE_NAME_PATTERN.sub("_", raw).strip("._-")
    return (cleaned or "unknown_spec")[:80]


def require_path_inside_repo(path: Path, repo_root: Path, label: str) -> None:
    if not is_relative_to(path.resolve(), repo_root.resolve()):
        raise RuntimeError(f"{label} resolves outside the repository: {display_path(path, repo_root)}")


def require_normal_dir(path: Path, repo_root: Path, label: str, *, must_exist: bool) -> None:
    if not path.exists():
        if must_exist:
            raise RuntimeError(f"{label} does not exist: {display_path(path, repo_root)}")
        return
    if path.is_symlink() or not path.is_dir():
        raise RuntimeError(f"{label} is not a normal directory: {display_path(path, repo_root)}")
    require_path_inside_repo(path, repo_root, label)


def require_normal_file(path: Path, repo_root: Path, label: str) -> None:
    if not path.exists():
        raise RuntimeError(f"{label} does not exist: {display_path(path, repo_root)}")
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(f"{label} is not a normal file: {display_path(path, repo_root)}")
    require_path_inside_repo(path, repo_root, label)


def read_active_spec(repo_root: Path) -> tuple[Path, str, dict[str, str]]:
    exports_dir = repo_root / "exports"
    active_dir = repo_root / ACTIVE_DIR_REL
    active_path = repo_root / ACTIVE_SPEC_REL
    require_normal_dir(exports_dir, repo_root, "exports/", must_exist=True)
    require_normal_dir(active_dir, repo_root, "exports/active_change/", must_exist=True)
    require_normal_file(active_path, repo_root, "active CHANGE_SPEC.md")

    try:
        spec_text = active_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise RuntimeError(f"Could not read active spec: {error}") from error
    return active_path, spec_text, parse_metadata(spec_text)


def require_clean_status(repo_root: Path, runner=run_command) -> None:
    status = git_output(repo_root, ["git", "status", "--short"], runner=runner)
    if status.strip():
        raise RuntimeError(
            "Refusing to finalize active spec because git status --short is not clean:\n"
            + status.rstrip()
        )


def require_active_spec_untracked(repo_root: Path, runner=run_command) -> None:
    result = runner(
        repo_root,
        ["git", "ls-files", "--error-unmatch", "--", ACTIVE_SPEC_REL.as_posix()],
    )
    if result.returncode == 0:
        raise RuntimeError("Refusing to finalize because exports/active_change/CHANGE_SPEC.md is tracked by Git.")
    if result.returncode != 1:
        details = result.combined_output()
        raise RuntimeError(f"Could not verify active spec tracking status: {details or '(no output)'}")


def current_branch(repo_root: Path, runner=run_command) -> str:
    branch = git_output(repo_root, ["git", "branch", "--show-current"], runner=runner).strip()
    if branch:
        return branch
    head = git_output(repo_root, ["git", "rev-parse", "--short", "HEAD"], runner=runner).strip()
    return f"detached at {head}"


def latest_head_short(repo_root: Path, runner=run_command) -> str:
    return git_output(repo_root, ["git", "rev-parse", "--short", "HEAD"], runner=runner).strip()


def latest_final_review_packet(repo_root: Path) -> Path | None:
    final_review_root = repo_root / FINAL_REVIEW_ROOT_REL
    if not final_review_root.exists():
        return None
    require_normal_dir(final_review_root, repo_root, "exports/final_review/", must_exist=True)

    candidates = [
        path
        for path in final_review_root.glob(f"*/{FINAL_REVIEW_PACKET_NAME}")
        if path.exists()
    ]
    if not candidates:
        return None
    for candidate in candidates:
        require_normal_file(candidate, repo_root, "final review packet")
    latest = max(candidates, key=lambda path: path.stat().st_mtime)
    return latest


def create_archive_dir(repo_root: Path, timestamp: str, spec_id: str, head_short: str) -> Path:
    archive_root = repo_root / ARCHIVE_ROOT_REL
    require_normal_dir(repo_root / "exports", repo_root, "exports/", must_exist=True)
    require_normal_dir(archive_root, repo_root, "exports/archived_change_specs/", must_exist=False)
    archive_root.mkdir(parents=True, exist_ok=True)

    archive_dir = archive_root / f"{timestamp}_{safe_name(spec_id)}_{safe_name(head_short)}"
    require_path_inside_repo(archive_dir.parent, repo_root, "archive parent")
    archive_dir.mkdir(parents=False, exist_ok=False)
    return archive_dir


def write_manifest(
    archive_dir: Path,
    repo_root: Path,
    *,
    timestamp: str,
    branch: str,
    head_short: str,
    active_path: Path,
    metadata: dict[str, str],
    final_review_packet: Path | None,
) -> Path:
    final_review_text = (
        display_path(final_review_packet, repo_root) if final_review_packet is not None else "(none found)"
    )
    lines = [
        "# Archived Change Spec Manifest",
        "",
        f"- Archive timestamp: `{timestamp}`",
        f"- Branch: `{branch}`",
        f"- Latest commit short SHA: `{head_short}`",
        f"- Active spec source path: `{display_path(active_path, repo_root)}`",
        f"- Final review packet source path: `{final_review_text}`",
        "- Generated archive note: this archive is generated local content under `exports/` and must not be committed.",
        "",
        "## Parsed Active Spec Metadata",
        "",
    ]
    for field in METADATA_FIELDS:
        lines.append(f"- {field}: `{metadata.get(field, '(not found)')}`")

    manifest_path = archive_dir / "MANIFEST.md"
    manifest_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return manifest_path


def remove_active_spec_only(active_path: Path, repo_root: Path) -> bool:
    active_dir = repo_root / ACTIVE_DIR_REL
    require_normal_file(active_path, repo_root, "active CHANGE_SPEC.md")
    active_path.unlink()

    removed_active_dir = False
    if active_dir.exists():
        require_normal_dir(active_dir, repo_root, "exports/active_change/", must_exist=True)
        if not any(active_dir.iterdir()):
            active_dir.rmdir()
            removed_active_dir = True
    return removed_active_dir


def finalize_completed_change(
    repo_root: Path,
    *,
    archive_active_spec: bool,
    runner=run_command,
    timestamp: str | None = None,
    out: TextIO = sys.stdout,
) -> int:
    if not archive_active_spec:
        print("FAIL: pass --archive-active-spec to finalize a completed active spec.", file=out)
        return 1

    try:
        active_path, spec_text, metadata = read_active_spec(repo_root)
        require_clean_status(repo_root, runner=runner)
        require_active_spec_untracked(repo_root, runner=runner)
        branch = current_branch(repo_root, runner=runner)
        head_short = latest_head_short(repo_root, runner=runner)
        final_review_packet = latest_final_review_packet(repo_root)
        archive_timestamp = timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_dir = create_archive_dir(
            repo_root,
            archive_timestamp,
            metadata.get("Spec ID", "unknown_spec"),
            head_short,
        )

        archived_spec_path = archive_dir / "CHANGE_SPEC.md"
        archived_spec_path.write_text(spec_text, encoding="utf-8")
        archived_final_review_path: Path | None = None
        if final_review_packet is not None:
            archived_final_review_path = archive_dir / FINAL_REVIEW_PACKET_NAME
            shutil.copy2(final_review_packet, archived_final_review_path)

        manifest_path = write_manifest(
            archive_dir,
            repo_root,
            timestamp=archive_timestamp,
            branch=branch,
            head_short=head_short,
            active_path=active_path,
            metadata=metadata,
            final_review_packet=final_review_packet,
        )
        removed_active_dir = remove_active_spec_only(active_path, repo_root)
    except (OSError, RuntimeError) as error:
        print(f"FAIL: {error}", file=out)
        return 1

    print("Archived completed active CHANGE_SPEC.md.", file=out)
    print(f"Archive directory: {display_path(archive_dir, repo_root)}", file=out)
    print(f"Archived spec: {display_path(archived_spec_path, repo_root)}", file=out)
    if archived_final_review_path is not None:
        print(f"Archived final review packet: {display_path(archived_final_review_path, repo_root)}", file=out)
    else:
        print("Archived final review packet: (none found)", file=out)
    print(f"Manifest: {display_path(manifest_path, repo_root)}", file=out)
    print(f"Removed active spec: {ACTIVE_SPEC_REL.as_posix()}", file=out)
    if removed_active_dir:
        print(f"Removed empty active spec directory: {ACTIVE_DIR_REL.as_posix()}", file=out)
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Archive and clear a completed active CHANGE_SPEC.md after human Git actions."
    )
    parser.add_argument(
        "--archive-active-spec",
        action="store_true",
        required=True,
        help="archive exports/active_change/CHANGE_SPEC.md and then remove that active copy",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        repo_root = find_repo_root()
    except RuntimeError as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    return finalize_completed_change(repo_root, archive_active_spec=args.archive_active_spec)


if __name__ == "__main__":
    raise SystemExit(main())
