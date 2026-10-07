#!/usr/bin/env python3
"""
Refresh the tracked repository handoff snapshot.

This helper is intentionally small and human-controlled. It reads local Git
context and writes only HANDOFF.md. It does not stage, commit, push, delete,
move, rename, switch branches, create pull requests, upload, or call external
services.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path


HANDOFF_NAME = "HANDOFF.md"
CHANGE_START_ROOT_PARTS = ("exports", "change_start")
FINAL_REVIEW_ROOT_PARTS = ("exports", "final_review")
CHANGE_SPEC_PACKET_NAME = "CHANGE_SPEC_PACKET.md"
CHANGE_SPEC_NAME = "CHANGE_SPEC.md"
FINAL_REVIEW_PACKET_NAME = "FINAL_REVIEW_PACKET.md"


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


def run_git(repo_root: Path, args: list[str]) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode == 0:
        return result.stdout
    details = "\n".join(part.rstrip() for part in (result.stdout, result.stderr) if part.strip())
    raise RuntimeError(f"git {' '.join(args)} failed:\n{details or '(no output)'}")


def current_branch(repo_root: Path) -> str:
    branch = run_git(repo_root, ["branch", "--show-current"]).strip()
    if branch:
        return branch
    head = run_git(repo_root, ["rev-parse", "--short", "HEAD"]).strip()
    return f"detached at {head}"


def relative_path(repo_root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root).as_posix()
    except ValueError:
        return str(path)


def latest_existing_path(repo_root: Path, root_parts: tuple[str, ...], name: str) -> str:
    root = repo_root.joinpath(*root_parts)
    candidates = [path for path in root.glob(f"*/{name}") if path.is_file()]
    if not candidates:
        return "(none found)"
    latest = max(candidates, key=lambda path: path.stat().st_mtime)
    return relative_path(repo_root, latest)


def markdown_code_block(text: str) -> str:
    body = text.rstrip("\n") if text.strip() else "(none)"
    return f"```text\n{body}\n```"


def normalized_status(repo_root: Path) -> str:
    status = run_git(repo_root, ["status", "--short"])
    return status.rstrip("\n") if status.strip() else "Working tree clean."


def build_handoff_content(
    *,
    updated_at: str,
    event: str,
    branch: str,
    status_text: str,
    latest_change_spec_packet: str,
    latest_change_spec: str,
    latest_final_review_packet: str,
    current_packet: str | None,
    safe_stopping_point: str,
    next_action: str,
    notes: list[str],
) -> str:
    packet_lines = [
        f"- Latest change-spec packet: `{latest_change_spec_packet}`",
        f"- Latest imported change spec: `{latest_change_spec}`",
        f"- Latest final review packet: `{latest_final_review_packet}`",
    ]
    if current_packet:
        packet_lines.append(f"- Current event packet: `{current_packet}`")

    note_lines = [f"- {note}" for note in notes if note.strip()]
    if not note_lines:
        note_lines = ["- (none)"]

    return "\n".join(
        [
            "# HANDOFF",
            "",
            "This is the current resumable-work snapshot for `ai_research_os`.",
            "",
            "## Current Snapshot",
            "",
            f"- Updated at: `{updated_at}`",
            f"- Event: {event}",
            f"- Current branch: `{branch}`",
            "",
            "## Git Status Summary",
            "",
            markdown_code_block(status_text),
            "",
            "## Latest Relevant Packets",
            "",
            *packet_lines,
            "",
            "## Safe Stopping Point",
            "",
            safe_stopping_point,
            "",
            "## Next Recommended Action",
            "",
            next_action,
            "",
            "## Notes",
            "",
            *note_lines,
            "",
            "## Human-Controlled Guardrails",
            "",
            "- Do not stage, commit, push, switch branches, clean generated files, open pull requests, or upload anything unless the user explicitly asks.",
            "- Generated `exports/` files are context packets only and should not be committed.",
            "- Update `HANDOFF.md` before stopping work or handing work back to the user.",
            "",
        ]
    )


def update_handoff(
    repo_root: Path,
    *,
    event: str = "Manual HANDOFF refresh",
    packet_path: Path | None = None,
    safe_stopping_point: str = "Repository context has been refreshed in HANDOFF.md.",
    next_action: str = "Review HANDOFF.md, then continue from the safe stopping point.",
    notes: list[str] | None = None,
) -> Path:
    current_packet = relative_path(repo_root, packet_path) if packet_path is not None else None
    latest_change_spec_packet = latest_existing_path(
        repo_root,
        CHANGE_START_ROOT_PARTS,
        CHANGE_SPEC_PACKET_NAME,
    )
    latest_final_review_packet = latest_existing_path(
        repo_root,
        FINAL_REVIEW_ROOT_PARTS,
        FINAL_REVIEW_PACKET_NAME,
    )
    if packet_path is not None and packet_path.name == CHANGE_SPEC_PACKET_NAME and current_packet:
        latest_change_spec_packet = current_packet
    if packet_path is not None and packet_path.name == FINAL_REVIEW_PACKET_NAME and current_packet:
        latest_final_review_packet = current_packet

    content = build_handoff_content(
        updated_at=datetime.now().isoformat(timespec="seconds"),
        event=event,
        branch=current_branch(repo_root),
        status_text=normalized_status(repo_root),
        latest_change_spec_packet=latest_change_spec_packet,
        latest_change_spec=latest_existing_path(repo_root, CHANGE_START_ROOT_PARTS, CHANGE_SPEC_NAME),
        latest_final_review_packet=latest_final_review_packet,
        current_packet=current_packet,
        safe_stopping_point=safe_stopping_point,
        next_action=next_action,
        notes=notes or [],
    )
    handoff_path = repo_root / HANDOFF_NAME
    handoff_path.write_text(content, encoding="utf-8")
    return handoff_path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Refresh HANDOFF.md with current repository context.")
    parser.add_argument("--event", default="Manual HANDOFF refresh", help="short event label")
    parser.add_argument("--packet", type=Path, help="packet path related to this handoff update")
    parser.add_argument("--safe-stopping-point", help="current safe stopping point")
    parser.add_argument("--next-action", help="recommended next human action")
    parser.add_argument("--note", action="append", default=[], help="optional note; may be repeated")
    return parser.parse_args(argv)


def main() -> int:
    try:
        args = parse_args()
        repo_root = find_repo_root()
        handoff_path = update_handoff(
            repo_root,
            event=args.event,
            packet_path=args.packet,
            safe_stopping_point=args.safe_stopping_point
            or "Repository context has been refreshed in HANDOFF.md.",
            next_action=args.next_action
            or "Review HANDOFF.md, then continue from the safe stopping point.",
            notes=args.note,
        )
    except RuntimeError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    print(handoff_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
