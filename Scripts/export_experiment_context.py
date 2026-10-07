#!/usr/bin/env python3
"""
Export one experiment as a single AI-readable Markdown context (read-only).

Reads only EXPERIMENT_INDEX.md and (when present) manifest.yaml and summary.md
under Experiments/<experiment_id>/. Never reads, copies, or modifies raw data.

Write path: optional --output only; everything else is read-only.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

MARKER_FILES = ("LAB_SCHEMA.md", "EXPERIMENT_INDEX.md")

SECTION_HEADING = "## Master index"

COLUMNS = [
    "experiment_id",
    "date",
    "project",
    "short_title",
    "status",
    "note_location",
    "raw_data_location",
    "analysis_location",
    "summary",
]


def find_repo_root(start: Path | None = None) -> Path:
    """Walk parents until both marker files exist."""
    configured_root = os.environ.get("RESEARCH_OS_WORKSPACE_ROOT")
    if configured_root:
        root = Path(configured_root).expanduser().resolve()
        if all((root / name).is_file() for name in MARKER_FILES):
            return root
        raise FileNotFoundError(
            "RESEARCH_OS_WORKSPACE_ROOT does not contain LAB_SCHEMA.md and "
            "EXPERIMENT_INDEX.md."
        )

    cur = (start or Path.cwd()).resolve()
    for parent in [cur, *cur.parents]:
        if all((parent / name).is_file() for name in MARKER_FILES):
            return parent
    raise FileNotFoundError(
        "Could not find the repository root.\n"
        "  Looked for LAB_SCHEMA.md and EXPERIMENT_INDEX.md in this folder and parents.\n"
        "  Tip: set RESEARCH_OS_WORKSPACE_ROOT or run from inside the research workspace."
    )


def split_table_row(line: str) -> list[str]:
    line = line.strip()
    if not line.startswith("|"):
        return []
    parts = [p.strip() for p in line.split("|")]
    return [p for p in parts if p != ""]


def is_separator_row(line: str) -> bool:
    stripped = line.strip()
    if not stripped.startswith("|"):
        return False
    inner = stripped.strip("|").strip()
    if not inner:
        return False
    return bool(re.fullmatch(r"[-\s|]+", inner))


def parse_index_table(text: str) -> list[dict[str, str]]:
    lines = text.splitlines()
    start = -1
    for i, line in enumerate(lines):
        if line.strip() == SECTION_HEADING:
            start = i + 1
            break
    if start < 0:
        raise ValueError(f'Missing "{SECTION_HEADING}" in EXPERIMENT_INDEX.md.')

    header_idx = -1
    for j in range(start, len(lines)):
        row = split_table_row(lines[j])
        if row and row[0] == "experiment_id":
            header_idx = j
            break
    if header_idx < 0:
        raise ValueError("Could not find the experiment table header (first cell: experiment_id).")

    header = split_table_row(lines[header_idx])
    if len(header) != len(COLUMNS) or header != COLUMNS:
        raise ValueError(
            "EXPERIMENT_INDEX.md table header does not match the expected columns.\n"
            f"  Expected: {COLUMNS}\n"
            f"  Found:    {header}"
        )

    rows: list[dict[str, str]] = []
    for k in range(header_idx + 1, len(lines)):
        line = lines[k]
        if not line.strip().startswith("|"):
            break
        if is_separator_row(line):
            continue
        cells = split_table_row(line)
        if len(cells) != len(COLUMNS):
            continue
        rows.append(dict(zip(COLUMNS, cells)))
    return rows


def find_index_row(rows: list[dict[str, str]], experiment_id: str) -> dict[str, str] | None:
    for row in rows:
        if row.get("experiment_id", "").strip() == experiment_id:
            return row
    return None


def extract_manifest_block(manifest_text: str, key: str) -> str | None:
    """Return YAML subtree for a top-level key, or None."""
    lines = manifest_text.splitlines()
    prefix = f"{key}:"
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        if line.startswith(prefix):
            chunk: list[str] = [line]
            base_indent = len(line) - len(line.lstrip())
            for j in range(i + 1, len(lines)):
                nxt = lines[j]
                if nxt.strip() == "":
                    chunk.append(nxt)
                    continue
                nxt_indent = len(nxt) - len(nxt.lstrip())
                if nxt.strip().startswith("#"):
                    chunk.append(nxt)
                    continue
                if nxt_indent <= base_indent and ":" in nxt.split("#", 1)[0]:
                    break
                chunk.append(nxt)
            return "\n".join(chunk).strip()
    return None


def missing_file_note(relative_path: Path, friendly_name: str) -> list[str]:
    """Markdown lines explaining a missing optional file."""
    return [
        f"> **Missing file:** `{relative_path.as_posix()}`",
        ">",
        f"> This file was expected but not found on disk. The **{friendly_name}** section "
        "below is therefore incomplete. Add the file (for example with "
        "`Scripts/register_experiment.py`) and run this export again to include it.",
        "",
    ]


def build_markdown(
    experiment_id: str,
    generated_at: str,
    index_row: dict[str, str],
    manifest_text: str | None,
    summary_text: str | None,
) -> str:
    rel_exp = Path("Experiments") / experiment_id
    title = f"# Experiment context for AI discussion: `{experiment_id}`"
    lines: list[str] = [
        title,
        "",
        "## Document metadata",
        "",
        f"- **Generated at (UTC):** {generated_at}",
        f"- **experiment_id:** `{experiment_id}`",
        "",
        "## Index row (EXPERIMENT_INDEX.md Master index)",
        "",
        "Fields from the repository index (text only):",
        "",
    ]
    for col in COLUMNS:
        val = index_row.get(col, "").replace("\n", " ").strip()
        lines.append(f"- **{col}:** {val}")

    lines.extend(["", "## Raw data location (text only)", ""])
    raw_index = index_row.get("raw_data_location", "").strip()
    lines.append("From the index `raw_data_location` column:")
    lines.append("")
    lines.append(raw_index if raw_index else "*(empty in index)*")
    lines.append("")

    if manifest_text is not None:
        raw_block = extract_manifest_block(manifest_text, "raw_data_location")
        if raw_block:
            lines.append("From `manifest.yaml` (`raw_data_location` subtree):")
            lines.append("")
            lines.append("```yaml")
            lines.append(raw_block)
            lines.append("```")
            lines.append("")
        else:
            lines.append(
                "*No `raw_data_location` block was found inside manifest.yaml (file exists).*"
            )
            lines.append("")
    else:
        lines.append(
            "*Cannot show manifest `raw_data_location` subtree because manifest.yaml is missing.*"
        )
        lines.append("")

    lines.extend(["## manifest.yaml (full file)", ""])
    rel_manifest = rel_exp / "manifest.yaml"
    if manifest_text is not None:
        lines.extend(
            [
                f"Copy of `{rel_manifest.as_posix()}` (paths and metadata as text only):",
                "",
                "```yaml",
                manifest_text.rstrip("\n"),
                "```",
                "",
            ]
        )
    else:
        lines.extend(missing_file_note(rel_manifest, "manifest"))

    lines.extend(["## summary.md (full file)", ""])
    rel_summary = rel_exp / "summary.md"
    if summary_text is not None:
        lines.extend(
            [
                f"Contents of `{rel_summary.as_posix()}`:",
                "",
                summary_text.rstrip("\n"),
                "",
            ]
        )
    else:
        lines.extend(missing_file_note(rel_summary, "summary"))

    lines.extend(
        [
            "---",
            "",
            "**Note:** Raw instrument files and other large binaries are **not** read or "
            "included here—only lightweight repository text. Do not rename, move, or edit "
            "raw data without explicit human approval.",
            "",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    examples = """
Examples:
  python3 Scripts/export_experiment_context.py EXP_20300101_demo
  python3 Scripts/export_experiment_context.py EXP_20300101_demo \\
      --output exports/EXP_20300101_demo_context.md
"""
    parser = argparse.ArgumentParser(
        description=(
            "Build one Markdown document with index row + manifest + summary for pasting "
            "into an AI assistant. Read-only except when writing --output."
        ),
        epilog=examples,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "experiment_id",
        help="Experiment ID (must match a row in EXPERIMENT_INDEX.md), e.g. EXP_20300101_demo.",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        metavar="PATH",
        help="Write Markdown here (parent folders are created). Omit to print to stdout.",
    )
    args = parser.parse_args()

    experiment_id = args.experiment_id.strip()
    if not experiment_id:
        print("error: experiment_id cannot be empty.", file=sys.stderr)
        return 1

    try:
        repo_root = find_repo_root()
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    index_path = repo_root / "EXPERIMENT_INDEX.md"
    try:
        text = index_path.read_text(encoding="utf-8")
        rows = parse_index_table(text)
    except OSError as e:
        print(f"error: cannot read {index_path}: {e}", file=sys.stderr)
        return 1
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    index_row = find_index_row(rows, experiment_id)
    if index_row is None:
        print(
            f"error: no experiment_id {experiment_id!r} in EXPERIMENT_INDEX.md (Master index).\n"
            "  Check spelling and date. Tip: python3 Scripts/list_experiments.py",
            file=sys.stderr,
        )
        return 1

    exp_dir = repo_root / "Experiments" / experiment_id
    if not exp_dir.is_dir():
        rel = exp_dir.relative_to(repo_root)
        print(
            f"error: experiment folder does not exist:\n"
            f"  {exp_dir}\n"
            f"  (expected directory {rel.as_posix()}/)\n"
            "  The ID is listed in the index, but the folder is missing on disk.\n"
            "  Tip: create it with python3 Scripts/register_experiment.py or restore from backup.",
            file=sys.stderr,
        )
        return 1

    manifest_path = exp_dir / "manifest.yaml"
    summary_path = exp_dir / "summary.md"

    manifest_text: str | None = None
    summary_text: str | None = None

    if manifest_path.is_file():
        try:
            manifest_text = manifest_path.read_text(encoding="utf-8")
        except OSError as e:
            print(f"warning: could not read manifest.yaml: {e}", file=sys.stderr)
            manifest_text = None
    else:
        print(
            f"note: missing {manifest_path.relative_to(repo_root).as_posix()} "
            "(a placeholder is included in the export).",
            file=sys.stderr,
        )

    if summary_path.is_file():
        try:
            summary_text = summary_path.read_text(encoding="utf-8")
        except OSError as e:
            print(f"warning: could not read summary.md: {e}", file=sys.stderr)
            summary_text = None
    else:
        print(
            f"note: missing {summary_path.relative_to(repo_root).as_posix()} "
            "(a placeholder is included in the export).",
            file=sys.stderr,
        )

    generated_at = datetime.now(timezone.utc).isoformat()
    md = build_markdown(
        experiment_id,
        generated_at,
        index_row,
        manifest_text,
        summary_text,
    )

    if args.output is not None:
        out_path = args.output
        if not out_path.is_absolute():
            out_path = (Path.cwd() / out_path).resolve()
        try:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(md, encoding="utf-8")
        except OSError as e:
            print(f"error: cannot write {out_path}: {e}", file=sys.stderr)
            return 1
    else:
        try:
            sys.stdout.write(md)
        except BrokenPipeError:
            return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
