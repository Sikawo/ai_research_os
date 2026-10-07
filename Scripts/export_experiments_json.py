#!/usr/bin/env python3
"""
Export the Master index from EXPERIMENT_INDEX.md to JSON (read-only).

Does not modify experiment folders or raw data. With --output, creates parent
directories as needed and writes the JSON file; otherwise prints to stdout.
"""

from __future__ import annotations

import argparse
import json
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

JSON_EXPERIMENT_FIELDS = COLUMNS


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
        "Could not find repository root (missing LAB_SCHEMA.md or EXPERIMENT_INDEX.md "
        "in this directory or any parent). Set RESEARCH_OS_WORKSPACE_ROOT or "
        "run from inside the research workspace."
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
    if len(header) != len(COLUMNS) or header != COLUMNS:
        raise ValueError(
            f"Unexpected table header: {header!r} (expected {COLUMNS!r})"
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


def row_matches_filters(
    row: dict[str, str],
    project: str | None,
    status: str | None,
    keyword: str | None,
) -> bool:
    if project is not None and project.casefold() not in row["project"].casefold():
        return False
    if status is not None and row["status"].casefold() != status.casefold():
        return False
    if keyword is not None:
        hay = " ".join(row[c] for c in COLUMNS).casefold()
        if keyword.casefold() not in hay:
            return False
    return True


def experiment_record(row: dict[str, str]) -> dict[str, str]:
    return {k: row.get(k, "") for k in JSON_EXPERIMENT_FIELDS}


def build_payload(
    rows: list[dict[str, str]],
    project: str | None,
    status: str | None,
    keyword: str | None,
) -> dict[str, object]:
    filtered = [r for r in rows if row_matches_filters(r, project, status, keyword)]
    experiments = [experiment_record(r) for r in filtered]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "record_count": len(experiments),
        "filters": {
            "project": project,
            "status": status,
            "keyword": keyword,
        },
        "experiments": experiments,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export EXPERIMENT_INDEX.md Master index table to JSON (read-only)."
    )
    parser.add_argument(
        "--output",
        "-o",
        metavar="PATH",
        help="Write JSON to this file (parent directories are created). Default: stdout.",
    )
    parser.add_argument(
        "--project",
        metavar="TEXT",
        help="Include rows whose project contains TEXT (case-insensitive substring).",
    )
    parser.add_argument(
        "--status",
        metavar="VALUE",
        help="Include rows whose status equals VALUE (case-insensitive).",
    )
    parser.add_argument(
        "--keyword",
        metavar="TEXT",
        help="Include rows where TEXT appears in any column (case-insensitive substring).",
    )
    args = parser.parse_args()

    try:
        repo_root = find_repo_root()
    except FileNotFoundError as e:
        print(e, file=sys.stderr)
        return 1

    index_path = repo_root / "EXPERIMENT_INDEX.md"
    text = index_path.read_text(encoding="utf-8")

    try:
        rows = parse_index_table(text)
    except ValueError as e:
        print(f"Error parsing index: {e}", file=sys.stderr)
        return 1

    payload = build_payload(rows, args.project, args.status, args.keyword)
    body = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"

    if args.output:
        out_path = Path(args.output)
        if not out_path.is_absolute():
            out_path = (Path.cwd() / out_path).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(body, encoding="utf-8")
    else:
        sys.stdout.write(body)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
