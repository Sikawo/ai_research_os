#!/usr/bin/env python3
"""
Read-only validation of experiment index vs Experiments/<experiment_id>/ folders.

Does not modify any files or touch raw data paths beyond reading metadata files.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from collections import Counter
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

PROJECT_REGISTRY_COLUMNS = [
    "project_id",
    "display_name",
    "description",
    "status",
]

# Optional completeness hints (warnings only if missing from manifest text).
RECOMMENDED_MANIFEST_KEYS = (
    "date:",
    "project:",
    "purpose:",
    "status:",
    "note_location:",
    "raw_data_location:",
    "processed_data_location:",
    "analysis_location:",
    "summary_location:",
)


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


def parse_project_registry(text: str) -> set[str]:
    """Return valid project_id values from PROJECT_REGISTRY.md markdown table."""
    lines = text.splitlines()

    header_idx = -1
    header: list[str] = []

    for i, line in enumerate(lines):
        row = split_table_row(line)
        if row and row[0] == "project_id":
            header_idx = i
            header = row
            break

    if header_idx < 0:
        return set()

    if header != PROJECT_REGISTRY_COLUMNS:
        raise ValueError(
            f"Unexpected PROJECT_REGISTRY.md table header: {header!r} "
            f"(expected {PROJECT_REGISTRY_COLUMNS!r})"
        )

    project_ids: set[str] = set()

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
            project_ids.add(project_id)

    return project_ids


def read_manifest_scalar(manifest_text: str, key: str) -> str | None:
    """
    Return a simple top-level scalar from a small YAML-like manifest.

    This intentionally avoids external YAML dependencies and only reads lines like:
    key: value

    Indented nested keys are ignored.
    """
    prefix = f"{key}:"
    for raw in manifest_text.splitlines():
        if raw.startswith((" ", "\t")):
            continue

        line = raw.split("#", 1)[0].strip()
        if not line.startswith(prefix):
            continue

        rest = line[len(prefix) :].strip()
        if not rest:
            return None

        if (rest.startswith('"') and rest.endswith('"')) or (
            rest.startswith("'") and rest.endswith("'")
        ):
            inner = rest[1:-1]
            return inner.replace('\\"', '"').replace("\\'", "'")

        return rest.strip()

    return None


def read_manifest_experiment_id(manifest_text: str) -> str | None:
    """Return experiment_id scalar from a small manifest; None if absent or unparsable."""
    return read_manifest_scalar(manifest_text, "experiment_id")


def read_manifest_project(manifest_text: str) -> str | None:
    """Return top-level project scalar from a small manifest; None if absent or unparsable."""
    return read_manifest_scalar(manifest_text, "project")


def list_experiment_dirs(experiments_root: Path) -> list[str]:
    out: list[str] = []
    if not experiments_root.is_dir():
        return out
    for child in sorted(experiments_root.iterdir()):
        if not child.is_dir():
            continue
        name = child.name
        if name.startswith("EXP_"):
            out.append(name)
    return out


def validate() -> int:
    errors: list[str] = []
    warnings: list[str] = []

    try:
        repo_root = find_repo_root()
    except FileNotFoundError as e:
        print(e, file=sys.stderr)
        return 2

    index_path = repo_root / "EXPERIMENT_INDEX.md"
    registry_path = repo_root / "PROJECT_REGISTRY.md"
    experiments_root = repo_root / "Experiments"

    valid_project_ids: set[str] = set()

    if not registry_path.is_file():
        errors.append("PROJECT_REGISTRY.md is missing")
    else:
        try:
            valid_project_ids = parse_project_registry(
                registry_path.read_text(encoding="utf-8")
            )
        except ValueError as e:
            errors.append(f"PROJECT_REGISTRY.md parse error: {e}")

        if not valid_project_ids:
            errors.append("No project IDs found in PROJECT_REGISTRY.md")

    text = index_path.read_text(encoding="utf-8")
    try:
        rows = parse_index_table(text)
    except ValueError as e:
        print(f"Index parse error: {e}", file=sys.stderr)
        return 2

    for i, row in enumerate(rows, start=1):
        experiment_id = row.get("experiment_id", "").strip()
        project = row.get("project", "").strip()

        if not experiment_id:
            errors.append(f"Index row {i}: empty experiment_id")

        if not project:
            errors.append(f"Index row {i}: empty project")
        elif valid_project_ids and project not in valid_project_ids:
            errors.append(
                f"Index row {i} [{experiment_id}]: project {project!r} "
                "is not listed in PROJECT_REGISTRY.md"
            )

    ids_from_rows = [r["experiment_id"].strip() for r in rows if r.get("experiment_id", "").strip()]
    counts = Counter(ids_from_rows)
    dupes = [eid for eid, n in counts.items() if n > 1]
    if dupes:
        for eid in sorted(dupes):
            errors.append(
                f"Duplicate experiment_id in EXPERIMENT_INDEX.md: {eid!r} "
                f"({counts[eid]} rows)"
            )

    index_id_set = set(ids_from_rows)

    disk_ids = set(list_experiment_dirs(experiments_root))
    all_ids = sorted(index_id_set | disk_ids)

    print("Experiment validation report")
    print("=" * 60)
    print(f"Repository: {repo_root}")
    print(f"Index rows: {len(rows)}")
    print(f"Distinct experiment_id in index: {len(index_id_set)}")
    print(f"EXP_* folders on disk: {len(disk_ids)}")
    print(f"Project IDs in registry: {len(valid_project_ids)}")
    print()

    for eid in all_ids:
        prefix = f"[{eid}]"
        in_index = eid in index_id_set
        if not in_index:
            warnings.append(
                f"{prefix} Folder exists under Experiments/ but experiment_id is not listed "
                "in EXPERIMENT_INDEX.md Master index table"
            )

        exp_dir = experiments_root / eid
        if not exp_dir.is_dir():
            if in_index:
                errors.append(f"{prefix} Missing folder: {exp_dir.relative_to(repo_root)}")
            continue

        manifest_path = exp_dir / "manifest.yaml"
        summary_path = exp_dir / "summary.md"

        if not manifest_path.is_file():
            errors.append(f"{prefix} Missing file: manifest.yaml")
        if not summary_path.is_file():
            errors.append(f"{prefix} Missing file: summary.md")

        if manifest_path.is_file():
            mtext = manifest_path.read_text(encoding="utf-8")

            mid = read_manifest_experiment_id(mtext)
            if mid is None:
                errors.append(f"{prefix} manifest.yaml has no experiment_id field")
            elif mid != eid:
                errors.append(
                    f"{prefix} manifest experiment_id {mid!r} does not match folder name {eid!r}"
                )

            mproject = read_manifest_project(mtext)
            if mproject is None:
                errors.append(f"{prefix} manifest.yaml has no top-level project field")
            elif valid_project_ids and mproject not in valid_project_ids:
                errors.append(
                    f"{prefix} manifest project {mproject!r} "
                    "is not listed in PROJECT_REGISTRY.md"
                )

            if mid is not None:
                for key in RECOMMENDED_MANIFEST_KEYS:
                    if key not in mtext:
                        warnings.append(
                            f"{prefix} manifest may be missing recommended key {key[:-1]!r}"
                        )

    print("--- Findings ---")
    if not errors and not warnings:
        print("(none)")
    else:
        for msg in errors:
            print(f"ERROR: {msg}")
        for msg in warnings:
            print(f"WARN:  {msg}")
    print()
    print("=" * 60)

    if errors:
        print("Validation failed.")
        return 1
    if warnings:
        print("Validation completed with warnings.")
        return 0
    print("Validation passed.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate EXPERIMENT_INDEX.md against Experiments/*/ and PROJECT_REGISTRY.md.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Example: python3 Scripts/validate_experiments.py",
    )
    parser.parse_args()
    return validate()


if __name__ == "__main__":
    raise SystemExit(main())
