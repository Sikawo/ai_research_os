#!/usr/bin/env python3
"""Import selected generated paper-note drafts after explicit human approval."""

from __future__ import annotations

import argparse
import dataclasses
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


REQUIRED_NOTE_FIELDS = (
    "note_depth",
    "security_tier",
    "read_depth",
    "source_provenance",
    "human_review_status",
)
SUPPORTED_ACTIONS = {"new", "replace_abstract_only", "skip", "review_only"}
IMPORT_ACTIONS = {"new", "replace_abstract_only"}
PUBLIC_FULL_TEXT_PROVENANCE_MARKERS = (
    "public_full_text",
    "public full text",
    "public_pdf",
    "public pdf",
    "pmc",
    "pubmed central",
    "publisher_public",
    "open_access",
    "open access",
)
RESTRICTED_MARKERS = ("restricted", "internal", "private", "unpublished", "confidential")
UNSAFE_CONTENT_PATTERNS = (
    re.compile("/" + "Users/"),
    re.compile(re.escape("file" + "://"), re.IGNORECASE),
    re.compile(r"(?m)^\s*" + re.escape("source" + "_url") + r"\s*:", re.IGNORECASE),
    re.compile(r"(?i)\b(api[_-]?key|access[_-]?token|secret[_-]?key|private[_-]?key)\b"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{12,}"),
)


@dataclasses.dataclass
class NoteDecision:
    note_id: str
    action: str
    source_note_path: str
    target_path: str
    selected: bool
    source_abs: Path | None = None
    target_abs: Path | None = None
    written: bool = False
    skipped_reason: str = ""
    warnings: list[str] = dataclasses.field(default_factory=list)
    errors: list[str] = dataclasses.field(default_factory=list)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate and optionally import selected generated paper-note drafts."
    )
    parser.add_argument("--source", required=True, help="Workflow export run folder.")
    parser.add_argument("--selection", required=True, help="selected_notes.yaml file.")
    parser.add_argument("--apply", action="store_true", help="Write approved notes to Papers/.")
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Repository root. Defaults to the current working directory.",
    )
    parser.add_argument(
        "--timestamp",
        default=None,
        help="Timestamp for deterministic tests, e.g. 20260526_120000.",
    )
    return parser.parse_args(argv)


def now_timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def display_path(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.name


def resolve_cli_path(path_text: str, repo_root: Path) -> Path:
    path = Path(path_text)
    if path.is_absolute():
        return path.resolve()
    return (repo_root / path).resolve()


def has_path_escape(path_text: str) -> bool:
    path = Path(path_text)
    return path.is_absolute() or ".." in path.parts


def resolve_inside(base: Path, relative_text: str, label: str) -> Path:
    if has_path_escape(relative_text):
        raise ValueError(f"{label} must be a relative path without '..': {relative_text}")
    candidate = (base / relative_text).resolve()
    base_resolved = base.resolve()
    try:
        candidate.relative_to(base_resolved)
    except ValueError as exc:
        raise ValueError(f"{label} escapes source folder: {relative_text}") from exc
    return candidate


def resolve_papers_target(repo_root: Path, target_text: str) -> Path:
    if has_path_escape(target_text):
        raise ValueError(f"target_path must be a relative Papers/*.md path: {target_text}")
    target_rel = Path(target_text)
    if not target_rel.parts or target_rel.parts[0] != "Papers":
        raise ValueError(f"target_path must be under Papers/: {target_text}")
    if target_rel.suffix != ".md":
        raise ValueError(f"target_path must be a Markdown file: {target_text}")
    target = (repo_root / target_rel).resolve()
    try:
        target.relative_to(repo_root.resolve() / "Papers")
    except ValueError as exc:
        raise ValueError(f"target_path escapes Papers/: {target_text}") from exc
    return target


def unsafe_markers(text: str) -> list[str]:
    markers: list[str] = []
    labels = (
        "absolute local path marker",
        "local file URL",
        "blocked source URL metadata field",
        "secret or token marker",
        "bearer token marker",
    )
    for label, pattern in zip(labels, UNSAFE_CONTENT_PATTERNS):
        if pattern.search(text):
            markers.append(label)
    return markers


def parse_simple_yaml(text: str) -> dict[str, Any]:
    try:
        import yaml  # type: ignore[import-not-found]
    except Exception:
        return parse_selected_notes_fallback(text)

    data = yaml.safe_load(text)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError("selected_notes.yaml must contain a mapping at the top level")
    return data


def parse_selected_notes_fallback(text: str) -> dict[str, Any]:
    notes: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    in_notes = False
    for raw_line in text.splitlines():
        line_without_comment = raw_line.split("#", 1)[0].rstrip()
        if not line_without_comment.strip():
            continue
        if re.match(r"^notes\s*:\s*$", line_without_comment):
            in_notes = True
            continue
        if not in_notes:
            continue
        item_match = re.match(r"^\s*-\s+([A-Za-z0-9_ -]+)\s*:\s*(.*?)\s*$", line_without_comment)
        if item_match:
            current = {}
            notes.append(current)
            key, value = item_match.groups()
            current[key.strip()] = unquote_scalar(value.strip())
            continue
        field_match = re.match(r"^\s+([A-Za-z0-9_ -]+)\s*:\s*(.*?)\s*$", line_without_comment)
        if field_match and current is not None:
            key, value = field_match.groups()
            current[key.strip()] = unquote_scalar(value.strip())
            continue
        raise ValueError(f"unsupported selected_notes.yaml line: {raw_line}")
    return {"notes": notes}


def unquote_scalar(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def load_selection(selection_path: Path) -> tuple[dict[str, Any], list[str]]:
    text = selection_path.read_text(encoding="utf-8")
    markers = unsafe_markers(text)
    if markers:
        raise ValueError("selected_notes.yaml contains unsafe marker(s): " + ", ".join(markers))
    return parse_simple_yaml(text), markers


def frontmatter_text(note_text: str) -> str:
    if not note_text.startswith("---\n"):
        return ""
    end_index = note_text.find("\n---", 4)
    if end_index == -1:
        return ""
    return note_text[4:end_index]


def scalar_field(text: str, field: str) -> str:
    match = re.search(rf"(?m)^\s*{re.escape(field)}\s*:\s*(.*?)\s*$", text)
    if not match:
        return ""
    value = match.group(1).strip()
    return unquote_scalar(value)


def field_block(text: str, field: str) -> str:
    lines = text.splitlines()
    collected: list[str] = []
    in_field = False
    for line in lines:
        if re.match(rf"^\s*{re.escape(field)}\s*:", line):
            in_field = True
            collected.append(line)
            continue
        if in_field:
            if re.match(r"^[A-Za-z0-9_-]+\s*:", line):
                break
            collected.append(line)
    return "\n".join(collected).strip()


def validate_note_content(
    note_text: str,
    decision: NoteDecision,
    selection_item: dict[str, Any],
) -> dict[str, str]:
    metadata_text = frontmatter_text(note_text) or note_text
    found: dict[str, str] = {field: scalar_field(metadata_text, field) for field in REQUIRED_NOTE_FIELDS}
    for field, value in found.items():
        if not value and field != "source_provenance":
            decision.errors.append(f"missing required provenance field: {field}")
    provenance_block = field_block(metadata_text, "source_provenance")
    if not provenance_block:
        decision.errors.append("missing required provenance field: source_provenance")

    note_depth = found.get("note_depth", "")
    security_tier = found.get("security_tier", "")
    read_depth = found.get("read_depth", "")
    human_review_status = found.get("human_review_status", "")
    expected_depth = str(selection_item.get("expected_note_depth", "") or "")
    expected_security = str(selection_item.get("expected_security_tier", "") or "")
    selection_review = str(selection_item.get("human_review_status", "") or "")

    if expected_depth and note_depth and expected_depth != note_depth:
        decision.errors.append(
            f"expected_note_depth {expected_depth!r} does not match note_depth {note_depth!r}"
        )
    if expected_security and security_tier and expected_security != security_tier:
        decision.errors.append(
            f"expected_security_tier {expected_security!r} does not match security_tier {security_tier!r}"
        )
    if selection_review != "approved_for_import":
        decision.errors.append("selection human_review_status must be approved_for_import")
    if human_review_status != "approved_for_import":
        decision.errors.append("note human_review_status must be approved_for_import")

    combined_depth_text = " ".join([note_depth, read_depth, expected_depth, security_tier]).lower()
    if any(marker in combined_depth_text for marker in RESTRICTED_MARKERS):
        decision.errors.append("restricted, internal, private, or unpublished note depths are not supported")
    if security_tier and security_tier != "public":
        decision.errors.append("security_tier must be public for this importer")
    if expected_security and expected_security != "public":
        decision.errors.append("expected_security_tier must be public for this importer")

    if note_depth == "abstract_metadata_only" and "full_text_reviewed" in read_depth:
        decision.errors.append("abstract_metadata_only drafts must not claim full-text review")
    if read_depth == "abstract_metadata_only" and "full_text_reviewed" in note_depth:
        decision.errors.append("full-text note_depth must not use abstract-only read_depth")
    if note_depth == "public_full_text_reviewed" or read_depth == "public_full_text_reviewed":
        provenance_lower = provenance_block.lower()
        if not any(marker in provenance_lower for marker in PUBLIC_FULL_TEXT_PROVENANCE_MARKERS):
            decision.errors.append(
                "public_full_text_reviewed drafts must cite a public full-text provenance marker"
            )
    return found


def parse_selection_items(selection_data: dict[str, Any]) -> list[dict[str, Any]]:
    notes = selection_data.get("notes")
    if not isinstance(notes, list):
        raise ValueError("selected_notes.yaml must define a notes list")
    parsed: list[dict[str, Any]] = []
    for item in notes:
        if not isinstance(item, dict):
            raise ValueError("each notes entry must be a mapping")
        parsed.append(item)
    return parsed


def validate_decisions(repo_root: Path, source_root: Path, items: list[dict[str, Any]]) -> list[NoteDecision]:
    decisions: list[NoteDecision] = []
    seen_targets: set[str] = set()
    for index, item in enumerate(items, start=1):
        action = str(item.get("import_action", "") or "")
        note_id = str(item.get("id", "") or f"entry_{index}")
        source_note_path = str(item.get("source_note_path", "") or "")
        target_path = str(item.get("target_path", "") or "")
        selected = action in IMPORT_ACTIONS
        decision = NoteDecision(
            note_id=note_id,
            action=action,
            source_note_path=source_note_path,
            target_path=target_path,
            selected=selected,
        )
        decisions.append(decision)

        if action not in SUPPORTED_ACTIONS:
            decision.errors.append(f"unsupported import_action: {action or '<missing>'}")
            continue
        if action in {"skip", "review_only"}:
            decision.skipped_reason = action

        for required in ("id", "source_note_path", "target_path", "expected_note_depth", "expected_security_tier"):
            if not item.get(required):
                decision.errors.append(f"missing selection field: {required}")

        try:
            decision.source_abs = resolve_inside(source_root, source_note_path, "source_note_path")
        except ValueError as exc:
            decision.errors.append(str(exc))
        try:
            decision.target_abs = resolve_papers_target(repo_root, target_path)
        except ValueError as exc:
            decision.errors.append(str(exc))

        if target_path in seen_targets and action in IMPORT_ACTIONS:
            decision.errors.append(f"duplicate selected target_path: {target_path}")
        if action in IMPORT_ACTIONS:
            seen_targets.add(target_path)

        if decision.source_abs is None or decision.target_abs is None:
            continue
        if decision.source_abs.suffix != ".md":
            decision.errors.append("source_note_path must point to a Markdown file")
        if not decision.source_abs.exists():
            decision.errors.append(f"source note does not exist: {source_note_path}")
            continue

        note_text = decision.source_abs.read_text(encoding="utf-8")
        markers = unsafe_markers(note_text)
        if markers:
            decision.errors.append("source note contains unsafe marker(s): " + ", ".join(markers))

        if action in IMPORT_ACTIONS:
            validate_note_content(note_text, decision, item)

        if action == "new" and decision.target_abs.exists():
            decision.errors.append("new import would overwrite an existing target")
        elif action == "replace_abstract_only":
            validate_replace_abstract_only(decision, note_text)
    return decisions


def validate_replace_abstract_only(decision: NoteDecision, new_note_text: str) -> None:
    if decision.target_abs is None:
        return
    if not decision.target_abs.exists():
        decision.errors.append("replace_abstract_only requires an existing abstract-only target")
        return
    new_metadata = frontmatter_text(new_note_text) or new_note_text
    if scalar_field(new_metadata, "note_depth") != "public_full_text_reviewed":
        decision.errors.append("replace_abstract_only requires a public_full_text_reviewed source note")
    existing_text = decision.target_abs.read_text(encoding="utf-8")
    existing_metadata = frontmatter_text(existing_text) or existing_text
    existing_depth = scalar_field(existing_metadata, "note_depth")
    existing_security = scalar_field(existing_metadata, "security_tier")
    if existing_depth != "abstract_metadata_only" or existing_security != "public":
        decision.errors.append("existing target is not clearly a public abstract_metadata_only note")
    if unsafe_markers(existing_text):
        decision.errors.append("existing target contains unsafe marker(s); refusing replacement")


def write_selected_notes(repo_root: Path, decisions: list[NoteDecision]) -> None:
    papers_root = repo_root.resolve() / "Papers"
    for decision in decisions:
        if not decision.selected or decision.errors:
            continue
        if decision.source_abs is None or decision.target_abs is None:
            continue
        try:
            decision.target_abs.resolve().relative_to(papers_root)
        except ValueError as exc:
            raise ValueError(f"refusing to write outside Papers/: {decision.target_path}") from exc
        decision.target_abs.parent.mkdir(parents=True, exist_ok=True)
        decision.target_abs.write_text(decision.source_abs.read_text(encoding="utf-8"), encoding="utf-8")
        decision.written = True


def review_packet_text(
    repo_root: Path,
    source_root: Path,
    selection_path: Path,
    decisions: list[NoteDecision],
    apply_used: bool,
) -> str:
    selected = [decision for decision in decisions if decision.selected]
    skipped = [decision for decision in decisions if not decision.selected]
    errors = [(decision, error) for decision in decisions for error in decision.errors]
    warnings = [(decision, warning) for decision in decisions for warning in decision.warnings]
    files_written = [decision for decision in decisions if decision.written]

    lines = [
        "# Selected Paper Note Import Review Packet",
        "",
        "## Summary",
        "",
        f"- source export folder: `{display_path(source_root, repo_root)}`",
        f"- selection file: `{display_path(selection_path, repo_root)}`",
        f"- apply used: {apply_used}",
        f"- files written: {len(files_written)}",
        "- Git actions performed: none",
        "",
        "## Selected Notes",
        "",
    ]
    if selected:
        for decision in selected:
            lines.append(
                f"- `{decision.note_id}`: `{decision.source_note_path}` -> "
                f"`{decision.target_path}` ({decision.action})"
            )
    else:
        lines.append("- none")

    lines.extend(["", "## Skipped Notes", ""])
    if skipped:
        for decision in skipped:
            reason = decision.skipped_reason or decision.action or "not selected"
            lines.append(f"- `{decision.note_id}`: `{decision.source_note_path}` ({reason})")
    else:
        lines.append("- none")

    lines.extend(["", "## Proposed Target Paths", ""])
    for decision in decisions:
        target = decision.target_path or "<missing>"
        lines.append(f"- `{decision.note_id}`: `{target}`")
    if not decisions:
        lines.append("- none")

    lines.extend(["", "## Import Actions", ""])
    for decision in decisions:
        status = "written" if decision.written else "not written"
        if decision.errors:
            status = "blocked"
        lines.append(f"- `{decision.note_id}`: {decision.action or '<missing>'}; {status}")
    if not decisions:
        lines.append("- none")

    lines.extend(["", "## Validation Warnings", ""])
    if warnings:
        for decision, warning in warnings:
            lines.append(f"- `{decision.note_id}`: {warning}")
    else:
        lines.append("- none")

    lines.extend(["", "## Validation Errors", ""])
    if errors:
        for decision, error in errors:
            lines.append(f"- `{decision.note_id}`: {error}")
    else:
        lines.append("- none")

    lines.extend(["", "## Files Written", ""])
    if files_written:
        for decision in files_written:
            lines.append(f"- `{decision.target_path}`")
    else:
        lines.append("- none")

    lines.extend(
        [
            "",
            "## Boundary Confirmation",
            "",
            "- The importer performed no Git add, commit, push, branch switching, or pull request actions.",
            "- Dry-run mode writes only this review packet under `exports/`.",
            "- Apply mode writes only approved, validated selected notes to `Papers/` targets.",
            "",
        ]
    )
    return "\n".join(lines)


def write_review_packet(
    repo_root: Path,
    timestamp: str,
    text: str,
) -> Path:
    packet_dir = repo_root / "exports" / "selected_paper_note_import_review" / timestamp
    packet_dir.mkdir(parents=True, exist_ok=True)
    packet_path = packet_dir / "SELECTED_PAPER_NOTE_IMPORT_REVIEW_PACKET.md"
    packet_path.write_text(text, encoding="utf-8")
    return packet_path


def run_import(args: argparse.Namespace) -> tuple[int, Path]:
    repo_root = Path(args.repo_root).resolve()
    source_root = resolve_cli_path(args.source, repo_root)
    selection_path = resolve_cli_path(args.selection, repo_root)
    timestamp = args.timestamp or now_timestamp()
    decisions: list[NoteDecision] = []

    fatal_errors: list[str] = []
    if not source_root.exists() or not source_root.is_dir():
        fatal_errors.append(f"source export folder does not exist: {args.source}")
    if not selection_path.exists() or not selection_path.is_file():
        fatal_errors.append(f"selection file does not exist: {args.selection}")

    if fatal_errors:
        decisions.append(
            NoteDecision(
                note_id="selection",
                action="review_only",
                source_note_path="",
                target_path="",
                selected=False,
                errors=fatal_errors,
            )
        )
    else:
        try:
            selection_data, _markers = load_selection(selection_path)
            items = parse_selection_items(selection_data)
            decisions = validate_decisions(repo_root, source_root, items)
        except Exception as exc:
            decisions.append(
                NoteDecision(
                    note_id="selection",
                    action="review_only",
                    source_note_path="",
                    target_path="",
                    selected=False,
                    errors=[str(exc)],
                )
            )

    has_errors = any(decision.errors for decision in decisions)
    if args.apply and not has_errors:
        write_selected_notes(repo_root, decisions)

    packet = review_packet_text(repo_root, source_root, selection_path, decisions, args.apply)
    packet_path = write_review_packet(repo_root, timestamp, packet)
    return (1 if has_errors else 0), packet_path


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        exit_code, packet_path = run_import(args)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote review packet: {packet_path}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
