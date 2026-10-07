#!/usr/bin/env python3
"""
Create a pre-implementation change-spec packet for human-supervised AI work.

This script is intentionally conservative. It does not stage, commit, push,
delete, move, or rename files. It writes a timestamped packet under
exports/change_start/<timestamp>/ and refreshes HANDOFF.md.
"""

from __future__ import annotations

import argparse
import importlib.util
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path


OUTPUT_ROOT_PARTS = ("exports", "change_start")
PACKET_NAME = "CHANGE_SPEC_PACKET.md"
ACTIVE_CHANGE_SPEC_PATH = Path("exports") / "active_change" / "CHANGE_SPEC.md"
FINAL_REVIEW_PACKET_NAME = "FINAL_REVIEW_PACKET.md"
FINAL_REVIEW_ROOT = Path("exports") / "final_review"
MAX_EXCERPT_CHARS = 4_000
GUIDANCE_FILES = (
    "AGENTS.md",
    "AI_SAFE.md",
    "AI_INSTRUCTIONS.md",
    "CURRENT_STATUS.md",
    "NEXT_ACTIONS.md",
    "Docs/final_review_workflow.md",
    "Templates/change_spec_template.md",
    "Templates/expected_behavior_template.md",
)
SPEC_METADATA_PATTERN = re.compile(r"^- (?P<key>[^:]+):\s*(?P<value>.+?)\s*$")
SPEC_METADATA_FIELDS = (
    "Spec ID",
    "Target repo",
    "Task",
    "Created for / change class",
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


def repo_relative_path(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def parse_spec_metadata(spec_text: str) -> dict[str, str]:
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

        match = SPEC_METADATA_PATTERN.match(line.strip())
        if match is None:
            continue

        key = match.group("key").strip()
        value = match.group("value").strip().strip("`")
        if key in SPEC_METADATA_FIELDS:
            metadata[key] = value

    return metadata


def latest_commit_short(repo_root: Path) -> str:
    try:
        return run_git(repo_root, ["rev-parse", "--short", "HEAD"]).strip() or "(unavailable)"
    except RuntimeError:
        return "(unavailable)"


def latest_final_review_packet(repo_root: Path) -> Path | None:
    final_review_root = repo_root / FINAL_REVIEW_ROOT
    if not final_review_root.is_dir():
        return None

    candidates = [
        path
        for path in final_review_root.glob(f"*/{FINAL_REVIEW_PACKET_NAME}")
        if path.is_file()
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def markdown_code_block(text: str, language: str = "") -> str:
    body = text.rstrip("\n") if text.strip() else "(none)"
    fence = f"```{language}".rstrip()
    return f"{fence}\n{body}\n```"


def brief_excerpt(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    if len(text) <= MAX_EXCERPT_CHARS:
        return text
    omitted = len(text) - MAX_EXCERPT_CHARS
    return text[:MAX_EXCERPT_CHARS].rstrip() + f"\n\n[truncated {omitted} characters]"


def guidance_excerpts(repo_root: Path) -> str:
    sections: list[str] = []
    for path_text in GUIDANCE_FILES:
        path = repo_root / path_text
        if not path.is_file():
            continue
        try:
            excerpt = brief_excerpt(path)
        except (OSError, UnicodeDecodeError) as error:
            excerpt = f"Could not read excerpt: {error}"
        sections.extend(
            [
                f"### {path_text}",
                "",
                markdown_code_block(excerpt, "markdown"),
                "",
            ]
        )
    if not sections:
        return "(none found)"
    return "\n".join(sections).rstrip()


def active_spec_diagnostic(repo_root: Path, branch: str, status_text: str) -> str:
    active_path = repo_root / ACTIVE_CHANGE_SPEC_PATH
    if not active_path.is_file():
        return ""

    try:
        metadata = parse_spec_metadata(active_path.read_text(encoding="utf-8"))
        spec_id = metadata.get("Spec ID", "(not found)")
    except (OSError, UnicodeDecodeError) as error:
        spec_id = f"(could not read: {error})"

    latest_packet = latest_final_review_packet(repo_root)
    latest_packet_text = (
        repo_relative_path(latest_packet, repo_root) if latest_packet is not None else "(none found)"
    )

    return "\n".join(
        [
            "## Existing Active Spec Diagnostic",
            "",
            "`exports/active_change/CHANGE_SPEC.md` already exists. A different active spec must not be silently replaced.",
            "",
            f"- Active spec path: `{ACTIVE_CHANGE_SPEC_PATH.as_posix()}`",
            f"- Active Spec ID: `{spec_id}`",
            f"- Current branch: `{branch}`",
            f"- Latest commit short SHA: `{latest_commit_short(repo_root)}`",
            f"- Latest final review packet: `{latest_packet_text}`",
            "- Git status summary:",
            "",
            markdown_code_block(status_text),
            "",
            "After confirming the previous task was reviewed, committed, pushed, and `git status --short` is clean, the human can run:",
            "",
            "```bash",
            "python3 Scripts/finalize_completed_change.py --archive-active-spec",
            "```",
            "",
            "`Scripts/start_change.py` does not auto-archive or auto-delete active specs.",
        ]
    )


def build_packet(repo_root: Path, task: str) -> str:
    branch = current_branch(repo_root)
    status_text = run_git(repo_root, ["status", "--short"])
    stale_active_spec_note = active_spec_diagnostic(repo_root, branch, status_text)

    packet_parts = [
        "# Change Spec Packet",
        "",
        "## User Task",
        "",
        task,
        "",
        "## Current Branch",
        "",
        markdown_code_block(branch),
        "",
        "## Git Status",
        "",
        markdown_code_block(status_text),
        "",
    ]
    if stale_active_spec_note:
        packet_parts.extend([stale_active_spec_note, ""])

    packet_parts.extend(
        [
            "## Relevant Repository Guidance Excerpts",
            "",
            guidance_excerpts(repo_root),
            "",
            "## Request For ChatGPT",
            "",
            "Create a concise, self-contained `CHANGE_SPEC.md` for this task before implementation.",
            "",
            "If the chat interface supports file creation, provide long artifacts as downloadable files instead of relying only on code blocks. If a code block is also shown, keep it secondary.",
            "",
            "For this request, provide the result as a downloadable `CHANGE_SPEC.md` file whenever possible, not only as inline Markdown in the chat response. The user should be able to save or download one file and give that same file to Codex or Cursor for implementation and to ChatGPT later for final review.",
            "",
            "If a downloadable file cannot be created in the current chat context, provide the complete spec as one clean Markdown code block with no nested broken fences. The preferred output remains a downloadable `CHANGE_SPEC.md` file.",
            "",
            "Examples of long artifacts include `CHANGE_SPEC.md`, `doc_sync.patch`, long prompts, review templates, `FINAL_REVIEW_PACKET.md`-derived templates, and other long Markdown, patch, or text artifacts.",
            "",
            "When Codex, Cursor, Claude Code, or another implementation-side AI tool receives the approved `CHANGE_SPEC.md`, its instructions must require it to save or copy the exact received spec to `exports/active_change/CHANGE_SPEC.md` before making implementation changes. If `exports/active_change/CHANGE_SPEC.md` already exists and differs from the received spec, the tool must not replace it silently; it must stop and ask the human to finalize the previous active spec or resolve the conflict.",
            "",
            "The recommended final review command after implementation is `python3 Scripts/finish_change.py --spec exports/active_change/CHANGE_SPEC.md`. If supported by the local helper, `python3 Scripts/finish_change.py --active-spec` may be used as the equivalent shortcut.",
            "",
            "The older change-start import workflow remains acceptable when needed: `python3 Scripts/import_change_spec.py --latest PATH_TO_DOWNLOADED_CHANGE_SPEC.md` copies the approved spec into the newest `exports/change_start/<timestamp>/CHANGE_SPEC.md`, making `python3 Scripts/finish_change.py --latest-spec` safe and easy to use after implementation.",
            "",
            "The spec should be practical, small in scope, and written in English. It should define expected behavior clearly enough that Codex or Cursor can implement the change and ChatGPT can later compare the final diff against the intended scope without relying on implicit chat context.",
            "",
            "Include a self-identifying metadata section near the top of the spec. At minimum, include `Spec ID`, `Target repo`, `Expected branch`, `Task`, and `Created for / change class`. The `Spec ID` should be stable enough to identify this requested change during final review.",
            "",
            "Include a top-level section titled exactly `## Recommended AI execution settings`.",
            "",
            "That section must include task classification: task type, change class, data/safety risk, and cross-repo/shared-core risk when relevant.",
            "",
            "For Codex/Cursor, include recommended model, reasoning level, speed, local workspace mode, permission boundaries, and when to ask the human or escalate.",
            "",
            "For Claude Code, include recommended model, effort/thinking level, permission mode, when to use Sonnet vs Opus, permission boundaries, and when to ask the human or escalate.",
            "",
            "The recommended settings should vary by task type. At minimum, distinguish docs-only or template wording, small bugfix, test-only change, CLI/script behavior change, workflow/safety/review policy change, shared-core or cross-repo sync change, broad refactor/migration, and private-data-risk change.",
            "",
            "The section must say clearly that model, reasoning, effort, speed, workspace, and permission recommendations are advisory only and never override the active `CHANGE_SPEC.md`, command permission policy, positive/negative/forbidden file lists, repository-specific safety boundaries, final review, or human-controlled Git.",
            "",
            "Include exactly these sections:",
            "",
            "- Metadata",
            "- Goal",
            "- Recommended AI execution settings",
            "- Expected behavior",
            "- Out of scope",
            "- Positive file list",
            "- Negative file list",
            "- Forbidden file list",
            "- Command permission policy",
            "- Validation commands",
            "- Minimal prompt for Codex or Cursor",
            "- Instructions for Codex or Cursor",
            "- Instructions for ChatGPT Final Review",
            "- Final verdict labels",
            "",
            "Include a short `Minimal prompt for Codex or Cursor` section that the user can copy and paste as the launcher prompt. It should tell Codex or Cursor to implement this `CHANGE_SPEC.md` only, follow the `Instructions for Codex or Cursor` section, run the validation commands listed in the spec and show the results, and not stage, commit, push, delete, rename, move files, switch branches, clean generated files, open a pull request, or upload anything.",
            "",
            "The Codex or Cursor instructions should tell the implementation tool to implement only the approved spec, respect the file-scope lists, avoid raw data and sensitive files, and not stage, commit, push, delete, rename, or move files unless explicitly approved.",
            "",
            "Include a `Command permission policy` section for the implementation-side AI tool. It should classify commands into `Allowed without extra human confirmation`, `Ask first`, and `Forbidden unless explicitly approved in the current spec`, while keeping final staging, commit, push, pull request creation, cleanup, deletion, and external upload human-controlled.",
            "",
            "The ChatGPT Final Review instructions should ask the reviewer to compare the final diff against the same `CHANGE_SPEC.md`, confirm whether validation passed, identify unexpected or forbidden files, and choose one final verdict label.",
            "",
            "The final review instructions should tell the user to give the approved `CHANGE_SPEC.md` to Codex, Cursor, Claude Code, or another implementation-side AI tool, and that tool's instructions must require it to preserve the exact received spec at `exports/active_change/CHANGE_SPEC.md` before implementation. After implementation, final review should run `python3 Scripts/finish_change.py --spec exports/active_change/CHANGE_SPEC.md`. If the active spec path is unavailable, use `python3 Scripts/finish_change.py --spec PATH` so the final packet can report the spec source path, Spec ID, spec SHA256, target repo, expected branch, current branch, task, and created-for / change class.",
            "",
            "When Codex, Cursor, Claude Code, or another implementation-side AI tool receives the approved `CHANGE_SPEC.md`, its instructions must require it to save or copy the exact received spec to `exports/active_change/CHANGE_SPEC.md` before implementation. The final review instructions should prefer `python3 Scripts/finish_change.py --spec exports/active_change/CHANGE_SPEC.md` whenever possible.",
            "",
            "Define these final verdict labels exactly: `APPROVE`, `REQUEST CHANGES`, `BLOCK COMMIT`, and `REVERT OR EXPLAIN`.",
            "",
            "Explain that Medium and Heavy changes should use a saved or downloadable `CHANGE_SPEC.md`, not only chat context, and that the same `CHANGE_SPEC.md` should be given to the implementation AI tool and later included in final review.",
            "",
            "The human should only need to give the approved `CHANGE_SPEC.md` to the implementation-side AI tool; the tool is responsible for preserving the active copy. Use `--latest-spec` only when a real `CHANGE_SPEC.md` exists under `exports/change_start/*/`.",
            "",
            "Do not call external AI APIs. Do not include raw data. Do not ask the implementation tool to stage, commit, push, delete, rename, or move files.",
            "",
        ]
    )
    return "\n".join(packet_parts)


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
        event="Generated change-spec packet",
        packet_path=packet_path,
        safe_stopping_point="A change-spec packet has been generated for human review.",
        next_action=(
            "Review or import the resulting CHANGE_SPEC.md, then give that approved spec "
            "to Codex or Cursor for implementation."
        ),
    )


def reveal_packet_in_finder(packet_path: Path) -> None:
    if sys.platform != "darwin":
        return

    result = subprocess.run(["open", "-R", str(packet_path)], check=False)
    if result.returncode != 0:
        print("Warning: could not reveal change spec packet in Finder.", file=sys.stderr)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a pre-implementation packet for drafting a CHANGE_SPEC.md."
    )
    parser.add_argument("task", nargs="+", help="one-line task description")
    return parser.parse_args(argv)


def normalize_task(parts: list[str]) -> str:
    task = " ".join(parts).strip()
    task = " ".join(task.splitlines())
    if not task:
        raise RuntimeError("Task description must not be empty.")
    return task


def main() -> int:
    try:
        args = parse_args()
        task = normalize_task(args.task)
        repo_root = find_repo_root()
        output_dir = create_output_dir(repo_root)
        packet_path = write_packet(output_dir, build_packet(repo_root, task))
        try:
            refresh_handoff(repo_root, packet_path)
        except Exception as error:
            print(f"Warning: could not update HANDOFF.md: {error}", file=sys.stderr)
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
