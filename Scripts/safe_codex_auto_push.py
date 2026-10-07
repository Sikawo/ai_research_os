#!/usr/bin/env python3
"""Dry-run readiness check for autonomous codex-auto branch pushes.

This helper is intentionally dry-run only. It never runs ``git push``.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO


READY = "READY"
BLOCK = "BLOCK"

BLOCKED_PATH_SEGMENTS = {
    ".env",
    "ai_artifacts",
    "applications",
    "credentials",
    "exports",
    "meeting_notes",
    "papers",
    "raw",
    "secrets",
}

BLOCKED_SUFFIXES = (
    ".czi",
    ".env",
    ".h5",
    ".hdf5",
    ".ipynb",
    ".jpeg",
    ".jpg",
    ".lif",
    ".nd2",
    ".ome.tif",
    ".pem",
    ".png",
    ".tif",
    ".tiff",
)

REQUIRED_PACKET_MARKERS = (
    "Safety check: PASS",
    "Pytest: PASS",
)

APPROVAL_PACKET_MARKERS = (
    "Suggested decision: `AUTO-APPROVE CANDIDATE`",
    "Reviewer verdict: `APPROVE`",
    "Reviewer verdict: APPROVE",
)


@dataclass(frozen=True)
class PushReadiness:
    decision: str
    branch: str
    commit: str
    push_command: str
    reasons: list[str]
    changed_files: list[str]


def run_git(repo_root: Path, args: list[str]) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"git {' '.join(args)} failed: {detail}")
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
        raise RuntimeError("Run this helper from inside a Git repository or pass --repo-root.")
    return Path(result.stdout.strip()).resolve()


def split_path_segments(path: str) -> set[str]:
    return {part.lower() for part in Path(path).parts}


def path_is_blocked(path: str) -> bool:
    lower = path.lower()
    if lower.endswith(BLOCKED_SUFFIXES):
        return True
    return bool(split_path_segments(path) & BLOCKED_PATH_SEGMENTS)


def read_packet(packet_path: Path) -> str:
    if not packet_path.is_file():
        raise RuntimeError(f"final review packet not found: {packet_path}")
    return packet_path.read_text(encoding="utf-8")


def packet_approves_push(packet_text: str) -> bool:
    review_text = packet_text.split("\n## Relevant Diff", 1)[0]
    has_required = all(marker in review_text for marker in REQUIRED_PACKET_MARKERS)
    has_approval = any(marker in review_text for marker in APPROVAL_PACKET_MARKERS)
    return has_required and has_approval


def branch_changed_files(repo_root: Path) -> list[str]:
    try:
        base = run_git(repo_root, ["merge-base", "origin/main", "HEAD"])
    except RuntimeError:
        return [
            line
            for line in run_git(repo_root, ["diff-tree", "--root", "--no-commit-id", "--name-only", "-r", "HEAD"]).splitlines()
            if line
        ]
    return [line for line in run_git(repo_root, ["diff", "--name-only", f"{base}..HEAD"]).splitlines() if line]


def inspect_push_readiness(repo_root: Path, final_review_packet: Path | None = None) -> PushReadiness:
    branch = run_git(repo_root, ["branch", "--show-current"])
    commit = run_git(repo_root, ["rev-parse", "--short", "HEAD"])
    status = run_git(repo_root, ["status", "--short"])
    changed_files = branch_changed_files(repo_root)
    push_command = f"git push -u origin {branch}"

    reasons: list[str] = []
    if not branch.startswith("codex-auto/"):
        reasons.append("current branch is not codex-auto/*")
    if status:
        reasons.append("working tree is not clean")
    try:
        run_git(repo_root, ["remote", "get-url", "origin"])
    except RuntimeError:
        reasons.append("origin remote is not configured")
    if not changed_files:
        reasons.append("branch has no changed files to push")

    blocked_files = [path for path in changed_files if path_is_blocked(path)]
    if blocked_files:
        reasons.append("branch changes include blocked protected/generated paths: " + ", ".join(blocked_files))

    if final_review_packet is None:
        reasons.append("final review packet was not provided")
    else:
        packet_text = read_packet(final_review_packet)
        if not packet_approves_push(packet_text):
            reasons.append("final review packet does not show safety pass and reviewer approval")

    decision = BLOCK if reasons else READY
    return PushReadiness(
        decision=decision,
        branch=branch,
        commit=commit,
        push_command=push_command,
        reasons=reasons,
        changed_files=changed_files,
    )


def print_readiness(readiness: PushReadiness, out: TextIO = sys.stdout) -> None:
    print("Safe codex-auto push dry-run", file=out)
    print(f"Decision: {readiness.decision}", file=out)
    print(f"Branch: {readiness.branch}", file=out)
    print(f"Commit: {readiness.commit}", file=out)
    print(file=out)
    print("Changed files in branch scope:", file=out)
    if readiness.changed_files:
        for path in readiness.changed_files:
            print(f"- {path}", file=out)
    else:
        print("- none", file=out)
    print(file=out)
    if readiness.reasons:
        print("Reasons:", file=out)
        for reason in readiness.reasons:
            print(f"- {reason}", file=out)
    else:
        print("Reasons:", file=out)
        print("- all dry-run safety checks passed", file=out)
        print(file=out)
        print("Suggested command for an approved push wrapper:", file=out)
        print("```bash", file=out)
        print(readiness.push_command, file=out)
        print("```", file=out)
    print(file=out)
    print("This helper is dry-run only; it did not run git push.", file=out)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Dry-run readiness check for pushing an autonomous codex-auto branch.",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Repository root to inspect. Defaults to the current Git repository.",
    )
    parser.add_argument(
        "--final-review-packet",
        type=Path,
        default=None,
        help="Final review packet proving safety pass and reviewer approval.",
    )
    return parser


def main(argv: list[str] | None = None, out: TextIO = sys.stdout) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    repo_root = args.repo_root.resolve() if args.repo_root else find_repo_root()
    packet_path = args.final_review_packet.resolve() if args.final_review_packet else None
    readiness = inspect_push_readiness(repo_root, final_review_packet=packet_path)
    print_readiness(readiness, out=out)
    return 0 if readiness.decision == READY else 1


if __name__ == "__main__":
    raise SystemExit(main())
