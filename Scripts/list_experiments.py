#!/usr/bin/env python3
"""
List experiments from EXPERIMENT_INDEX.md (read-only).

Parses the markdown table under the "Master index" heading and prints rows
in a readable format. Optional filters narrow rows; no files are modified.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
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
    """Split a markdown table row into cell values (no outer pipes)."""
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
    """
    Return table rows from the Master index section as list of dicts (keys = COLUMNS).
    """
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
    if len(header) != len(COLUMNS):
        raise ValueError(
            f"Expected {len(COLUMNS)} columns, found {len(header)} in header: {header!r}"
        )
    if header != COLUMNS:
        raise ValueError(
            "Table header does not match expected columns. "
            f"Got {header!r}, expected {COLUMNS!r}"
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


def print_experiment(row: dict[str, str], index: int, total: int) -> None:
    print(f"--- {index}/{total}  {row['experiment_id']} ---")
    for key in COLUMNS:
        if key == "experiment_id":
            continue
        print(f"  {key}: {row[key]}")
    print()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="List experiments from EXPERIMENT_INDEX.md (read-only)."
    )
    parser.add_argument(
        "--project",
        metavar="TEXT",
        help="Keep rows whose project contains TEXT (case-insensitive substring).",
    )
    parser.add_argument(
        "--status",
        metavar="VALUE",
        help="Keep rows whose status equals VALUE (case-insensitive).",
    )
    parser.add_argument(
        "--keyword",
        metavar="TEXT",
        help="Keep rows where TEXT appears in any column (case-insensitive substring).",
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

    filtered = [
        r
        for r in rows
        if row_matches_filters(r, args.project, args.status, args.keyword)
    ]

    print(f"Experiments listed: {len(filtered)} (from {len(rows)} in index)\n")

    if not filtered:
        print("No matching experiments.")
        return 0

    for i, row in enumerate(filtered, start=1):
        print_experiment(row, i, len(filtered))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
