#!/usr/bin/env python3
"""
Export AI-readable Markdown context for one project.

Read-only:
- Reads PROJECT_REGISTRY.md
- Reads EXPERIMENT_INDEX.md
- Reads Experiments/<experiment_id>/manifest.yaml
- Reads Experiments/<experiment_id>/summary.md

Does not read, move, rename, or modify raw data.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

MARKER_FILES = ("LAB_SCHEMA.md", "EXPERIMENT_INDEX.md")

SECTION_HEADING = "## Master index"

INDEX_COLUMNS = [
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

PROJECT_REGISTRY_COLUMNS = [
    "project_id",
    "display_name",
    "description",
    "status",
]


def find_repo_root(start: Path | None = None) -> Path:
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
        "Could not find the research workspace. Set RESEARCH_OS_WORKSPACE_ROOT "
        "or run this command from inside the workspace."
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
        raise ValueError(f'No "{SECTION_HEADING}" section found in EXPERIMENT_INDEX.md.')

    header_idx = -1
    for j in range(start, len(lines)):
        row = split_table_row(lines[j])
        if row and row[0] == "experiment_id":
            header_idx = j
            break

    if header_idx < 0:
        raise ValueError("No experiment table header row starting with experiment_id.")

    header = split_table_row(lines[header_idx])
    if header != INDEX_COLUMNS:
        raise ValueError(
            f"Unexpected EXPERIMENT_INDEX.md table header: {header!r}"
        )

    rows: list[dict[str, str]] = []

    for k in range(header_idx + 1, len(lines)):
        line = lines[k]

        if not line.strip().startswith("|"):
            break

        if is_separator_row(line):
            continue

        cells = split_table_row(line)
        if len(cells) != len(INDEX_COLUMNS):
            continue

        rows.append(dict(zip(INDEX_COLUMNS, cells)))

    return rows


def parse_project_registry(text: str) -> dict[str, dict[str, str]]:
    lines = text.splitlines()

    header_idx = -1
    for i, line in enumerate(lines):
        row = split_table_row(line)
        if row and row[0] == "project_id":
            header_idx = i
            header = row
            break
    else:
        return {}

    if header != PROJECT_REGISTRY_COLUMNS:
        raise ValueError(
            f"Unexpected PROJECT_REGISTRY.md table header: {header!r}"
        )

    projects: dict[str, dict[str, str]] = {}

    for j in range(header_idx + 1, len(lines)):
        line = lines[j]

        if not line.strip().startswith("|"):
            break

        if is_separator_row(line):
            continue

        cells = split_table_row(line)
        if len(cells) != len(PROJECT_REGISTRY_COLUMNS):
            continue

        record = dict(zip(PROJECT_REGISTRY_COLUMNS, cells))
        project_id = record["project_id"].strip()

        if project_id:
            projects[project_id] = record

    return projects


def markdown_table(rows: list[dict[str, str]], columns: list[str]) -> str:
    out: list[str] = []
    out.append("| " + " | ".join(columns) + " |")
    out.append("| " + " | ".join(["---"] * len(columns)) + " |")

    for row in rows:
        out.append("| " + " | ".join(row.get(col, "") for col in columns) + " |")

    return "\n".join(out)


def build_project_context(repo_root: Path, project_id: str) -> str:
    registry_path = repo_root / "PROJECT_REGISTRY.md"
    index_path = repo_root / "EXPERIMENT_INDEX.md"
    experiments_root = repo_root / "Experiments"

    if not registry_path.is_file():
        raise FileNotFoundError("PROJECT_REGISTRY.md not found.")

    projects = parse_project_registry(registry_path.read_text(encoding="utf-8"))

    if not projects:
        raise ValueError("No project IDs found in PROJECT_REGISTRY.md.")

    if project_id not in projects:
        available = ", ".join(sorted(projects))
        raise ValueError(
            f"Unknown project_id: {project_id!r}. Available project_id values: {available}"
        )

    rows = parse_index_table(index_path.read_text(encoding="utf-8"))
    project_rows = [row for row in rows if row.get("project", "").strip() == project_id]

    project_rows = sorted(
        project_rows,
        key=lambda row: (
            row.get("date", ""),
            row.get("experiment_id", ""),
        ),
    )

    project_record = projects[project_id]

    lines: list[str] = []

    lines.append(f"# AI project context: {project_id}")
    lines.append("")
    lines.append("This file is an AI-readable context export for one project.")
    lines.append("")
    lines.append("**Safety note:** Raw instrument files and large binary data are not read or included here. This export only includes lightweight repository metadata and text summaries.")
    lines.append("")

    lines.append("## Project registry entry")
    lines.append("")
    lines.append(f"- **project_id:** {project_record['project_id']}")
    lines.append(f"- **display_name:** {project_record['display_name']}")
    lines.append(f"- **description:** {project_record['description']}")
    lines.append(f"- **status:** {project_record['status']}")
    lines.append("")

    lines.append("## Experiment index rows for this project")
    lines.append("")
    lines.append(f"Experiments found: {len(project_rows)}")
    lines.append("")

    if project_rows:
        lines.append(markdown_table(project_rows, INDEX_COLUMNS))
    else:
        lines.append("_No experiments found for this project in EXPERIMENT_INDEX.md._")

    lines.append("")

    lines.append("## Experiment details")
    lines.append("")

    for row in project_rows:
        eid = row["experiment_id"]
        exp_dir = experiments_root / eid
        manifest_path = exp_dir / "manifest.yaml"
        summary_path = exp_dir / "summary.md"

        lines.append(f"### {eid}")
        lines.append("")
        lines.append("#### Index row")
        lines.append("")
        lines.append(markdown_table([row], INDEX_COLUMNS))
        lines.append("")

        lines.append("#### manifest.yaml")
        lines.append("")
        if manifest_path.is_file():
            lines.append(f"Copy of `{manifest_path.relative_to(repo_root)}`:")
            lines.append("")
            lines.append("```yaml")
            lines.append(manifest_path.read_text(encoding="utf-8").rstrip())
            lines.append("```")
        else:
            lines.append("_manifest.yaml not found._")
        lines.append("")

        lines.append("#### summary.md")
        lines.append("")
        if summary_path.is_file():
            lines.append(f"Contents of `{summary_path.relative_to(repo_root)}`:")
            lines.append("")
            lines.append(summary_path.read_text(encoding="utf-8").rstrip())
        else:
            lines.append("_summary.md not found._")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export AI-readable Markdown context for one project.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python3 Scripts/export_project_context.py demo_project\n"
            "  python3 Scripts/export_project_context.py demo_project --output exports/demo_project_context.md"
        ),
    )
    parser.add_argument("project_id", help="Project ID from PROJECT_REGISTRY.md")
    parser.add_argument(
        "--output",
        "-o",
        help="Optional output Markdown path. If omitted, prints to stdout.",
    )

    args = parser.parse_args()

    try:
        repo_root = find_repo_root()
        context = build_project_context(repo_root, args.project_id)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(context, encoding="utf-8")
        print(f"Wrote {output_path}")
    else:
        print(context, end="")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
