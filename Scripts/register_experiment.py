#!/usr/bin/env python3
"""
Interactive manual registration of a logical experiment.

Creates Experiments/<experiment_id>/manifest.yaml and summary.md,
updates EXPERIMENT_INDEX.md, and never touches raw data paths on disk
(only records locations as text in metadata).

Repository layout and keys follow LAB_SCHEMA.md / SPEC.md (English only).
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import date
from pathlib import Path
from string import Template
from typing import Any, Mapping

# --- repo discovery -----------------------------------------------------------

MARKER_FILES = ("LAB_SCHEMA.md", "EXPERIMENT_INDEX.md")
PROJECT_REGISTRY_FILE = "PROJECT_REGISTRY.md"


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


# --- controlled vocabularies --------------------------------------------------

STATUS_VALUES = (
    "planned",
    "ongoing",
    "completed",
    "analyzed",
)


# --- project registry ---------------------------------------------------------


def parse_project_registry(repo_root: Path) -> list[dict[str, str]]:
    """
    Parse PROJECT_REGISTRY.md.

    Expected table columns:
    project_id, display_name, description, status
    """
    path = repo_root / PROJECT_REGISTRY_FILE
    if not path.is_file():
        raise FileNotFoundError(
            f"Missing {PROJECT_REGISTRY_FILE}. Create it before registering experiments."
        )

    text = path.read_text(encoding="utf-8")
    projects: list[dict[str, str]] = []

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        if "---" in stripped:
            continue

        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if len(cells) < 4:
            continue

        if cells[0] == "project_id":
            continue

        project_id, display_name, description, status = cells[:4]

        if not project_id:
            continue

        projects.append(
            {
                "project_id": project_id,
                "display_name": display_name,
                "description": description,
                "status": status,
            }
        )

    if not projects:
        raise ValueError(f"No projects found in {PROJECT_REGISTRY_FILE}.")

    return projects


def validate_project_id(project_id: str) -> None:
    """
    Require snake_case project_id:
    lowercase letters, numbers, and underscores.
    """
    if not re.fullmatch(r"[a-z0-9]+(?:_[a-z0-9]+)*", project_id):
        raise ValueError(
            f"Invalid project_id '{project_id}'. Use snake_case, e.g. demo_activation."
        )


def prompt_project_from_registry(repo_root: Path) -> str:
    projects = parse_project_registry(repo_root)

    print("\nAvailable projects:")
    for i, project in enumerate(projects, start=1):
        project_id = project["project_id"]
        display_name = project["display_name"]
        status = project["status"]
        description = project["description"]
        print(f"  {i}. {project_id} ({display_name}; {status})")
        if description:
            print(f"     {description}")

    while True:
        raw = input("Select project number or exact project_id: ").strip()

        if raw.isdigit():
            idx = int(raw)
            if 1 <= idx <= len(projects):
                project_id = projects[idx - 1]["project_id"]
                validate_project_id(project_id)
                return project_id

        for project in projects:
            if raw == project["project_id"]:
                validate_project_id(raw)
                return raw

        print("  Invalid project. Choose a number from the list or type the exact project_id.")


# --- experiment_id ------------------------------------------------------------


def parse_experiment_date(text: str) -> tuple[str, str]:
    """
    Return (YYYYMMDD, YYYY-MM-DD) from user input.
    Accepts YYYY-MM-DD or YYYYMMDD.
    """
    t = text.strip()
    if re.fullmatch(r"\d{8}", t):
        y, m, d = int(t[0:4]), int(t[4:6]), int(t[6:8])
        dt = date(y, m, d)
        return t, dt.isoformat()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", t):
        dt = date.fromisoformat(t)
        return dt.strftime("%Y%m%d"), dt.isoformat()
    raise ValueError("Use YYYYMMDD or YYYY-MM-DD.")


def sanitize_short_description(raw: str) -> str:
    """
    Build the short-description segment for EXP_YYYYMMDD_short-description.
    English-only: keep [A-Za-z0-9_], collapse underscores, non-empty.
    """
    s = raw.strip().replace(" ", "_").replace("-", "_")
    s = re.sub(r"[^A-Za-z0-9_]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s


def build_experiment_id(yyyymmdd: str, short_description: str) -> str:
    slug = sanitize_short_description(short_description)
    if not slug:
        raise ValueError("Short description must contain at least one English letter or digit.")
    if not re.fullmatch(r"[A-Za-z0-9_]+", slug):
        raise ValueError("Short description must be ASCII letters, digits, or underscores only.")
    return f"EXP_{yyyymmdd}_{slug}"


# --- prompts -----------------------------------------------------------------


def prompt_line(label: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default is not None else ""
    raw = input(f"{label}{suffix}: ").strip()
    if not raw and default is not None:
        return default
    return raw


def prompt_nonempty(label: str) -> str:
    while True:
        raw = input(f"{label}: ").strip()
        if raw:
            return raw
        print("  (required)")


def prompt_status() -> str:
    print("\nStatus must be one of:")
    print("  " + ", ".join(STATUS_VALUES))
    while True:
        s = input("status: ").strip()
        if s in STATUS_VALUES:
            return s
        print("  Invalid status. Pick from the list above.")


def prompt_date_with_default_today() -> tuple[str, str]:
    today_iso = date.today().isoformat()
    today_compact = date.today().strftime("%Y%m%d")
    raw = prompt_line("Experiment date (YYYYMMDD or YYYY-MM-DD)", today_iso)
    if not raw:
        return today_compact, today_iso
    try:
        return parse_experiment_date(raw)
    except ValueError as e:
        print(f"  {e}")
        return prompt_date_with_default_today()


def prompt_experimental_context() -> dict[str, str]:
    print("\n--- experimental_context ---")
    print("Use short English descriptions. These fields help AI understand the experiment.")
    biological_material = prompt_nonempty(
        "  biological_material (e.g. demo cell line, reference sample)"
    )
    stimulus = prompt_line(
        "  stimulus (e.g. compound_a, vehicle, untreated)",
        "untreated",
    )
    assay = prompt_nonempty(
        "  assay (e.g. Western blot, IF, qPCR, ELISA, flow cytometry)"
    )
    readout = prompt_nonempty(
        "  readout (e.g. marker intensity, transcript count, viability)"
    )
    comparison = prompt_nonempty(
        "  comparison (e.g. stimulated vs unstimulated)"
    )

    return {
        "biological_material": biological_material,
        "stimulus": stimulus,
        "assay": assay,
        "readout": readout,
        "comparison": comparison,
    }


def prompt_location_block(label: str, use_reference: bool) -> dict[str, str]:
    print(f"\n--- {label} ---")
    system = prompt_nonempty("  system (e.g. Benchling, Box, GitHub)")
    if use_reference:
        ref = prompt_nonempty("  reference (URL, page title, or free-text pointer)")
        return {"system": system, "reference": ref}

    second_key = "path_or_url"
    second = prompt_nonempty(f"  {second_key}")

    if label == "raw_data_location":
        notes = prompt_line(
            "  notes",
            "Raw data are stored externally and should not be renamed.",
        )
        return {"system": system, second_key: second, "notes": notes}

    return {"system": system, second_key: second}


def prompt_location_path(label: str) -> dict[str, str]:
    print(f"\n--- {label} ---")
    system = prompt_nonempty("  system (e.g. GitHub)")
    path = prompt_nonempty("  path (repo-relative or descriptive path)")
    return {"system": system, "path": path}


# --- YAML (stdlib-only, small subset: dict[str, Any], scalars, nested dict) ---


def _yaml_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        return str(value)
    if isinstance(value, str):
        return _yaml_double_quoted_string(value)
    raise TypeError(f"Unsupported scalar type: {type(value)}")


def _yaml_double_quoted_string(s: str) -> str:
    escaped = s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{escaped}"'


def dump_yaml_document(root: Mapping[str, Any]) -> str:
    """Emit a small YAML subset: nested dicts and scalars only (no lists)."""

    lines: list[str] = []

    def walk(obj: Any, indent: int) -> None:
        pad = "  " * indent
        if isinstance(obj, dict):
            for k, v in obj.items():
                if not isinstance(k, str):
                    raise TypeError("YAML keys must be str")
                if isinstance(v, dict):
                    lines.append(f"{pad}{k}:")
                    walk(v, indent + 1)
                else:
                    lines.append(f"{pad}{k}: {_yaml_scalar(v)}")
        else:
            raise TypeError("Top-level manifest must be a dict")

    walk(dict(root), 0)
    return "\n".join(lines) + "\n"


# --- index -------------------------------------------------------------------

INDEX_HEADER = (
    "| experiment_id | date | project | short_title | status | note_location | "
    "raw_data_location | analysis_location | summary |"
)
INDEX_SEP = (
    "|---|---|---|---|---|---|---|---|---|"
)


def experiment_id_in_index(text: str, experiment_id: str) -> bool:
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        parts = [c.strip() for c in stripped.split("|")]
        parts = [p for p in parts if p != ""]
        if parts and parts[0] == experiment_id:
            return True
    return False


def ensure_index_table(text: str) -> str:
    if INDEX_HEADER.strip() in text:
        return text
    text = text.rstrip() + "\n\n"
    text += "## Master index\n\n"
    text += INDEX_HEADER + "\n"
    text += INDEX_SEP + "\n"
    return text


def markdown_table_cell(value: str) -> str:
    v = value.replace("\n", " ").replace("|", "\\|").strip()
    return v


def append_index_row(text: str, cells: list[str]) -> str:
    text = ensure_index_table(text)
    row = "| " + " | ".join(markdown_table_cell(c) for c in cells) + " |"
    if text.endswith("\n"):
        text = text.rstrip("\n")
    return text + "\n" + row + "\n"


# --- summary template ---------------------------------------------------------


def load_summary_template(repo_root: Path) -> str:
    path = repo_root / "Templates" / "experiment_summary_template.md"
    return path.read_text(encoding="utf-8")


def render_summary(template_text: str, mapping: Mapping[str, str]) -> str:
    safe = {k: v.replace("$", "$$") for k, v in mapping.items()}
    return Template(template_text).substitute(safe)


# --- main flow ----------------------------------------------------------------


def collect_manifest(
    experiment_id: str,
    iso_date: str,
    project: str,
    purpose: str,
    status: str,
    experimental_context: dict[str, str],
    note_location: dict[str, str],
    raw_data_location: dict[str, str],
    processed_data_location: dict[str, str],
    analysis_location: dict[str, str],
) -> dict[str, Any]:
    summary_path = f"Experiments/{experiment_id}/summary.md"
    return {
        "experiment_id": experiment_id,
        "date": iso_date,
        "project": project,
        "purpose": purpose,
        "status": status,
        "experimental_context": experimental_context,
        "note_location": note_location,
        "raw_data_location": raw_data_location,
        "processed_data_location": processed_data_location,
        "analysis_location": analysis_location,
        "summary_location": {"system": "GitHub", "path": summary_path},
    }


def main() -> int:
    # Support `python3 Scripts/register_experiment.py --help` without starting prompts.
    parser = argparse.ArgumentParser(
        prog="register_experiment.py",
        description=(
            "Interactively register a logical experiment: creates Experiments/<experiment_id>/, "
            "manifest.yaml, summary.md, and appends a row to EXPERIMENT_INDEX.md."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Run without arguments to start the interactive questionnaire.",
    )
    parser.parse_known_args()

    print("Register experiment (manual / interactive). Ctrl+C to cancel.\n")
    try:
        repo_root = find_repo_root()
    except FileNotFoundError as e:
        print(e, file=sys.stderr)
        return 1

    yyyymmdd, iso_date = prompt_date_with_default_today()

    print("\nExperiment ID format suggestion:")
    print("  EXP_YYYYMMDD_biologicalMaterial_stimulus_assay")
    print("Example:")
    print("  EXP_20300101_demo_assay\n")

    short_desc = prompt_nonempty(
        "Short English description for the ID (e.g. demo_assay)"
    )
    try:
        experiment_id = build_experiment_id(yyyymmdd, short_desc)
    except ValueError as e:
        print(f"Invalid ID parts: {e}", file=sys.stderr)
        return 1

    exp_dir = repo_root / "Experiments" / experiment_id
    index_path = repo_root / "EXPERIMENT_INDEX.md"

    if exp_dir.exists():
        print(f"Refusing to overwrite existing folder: {exp_dir}", file=sys.stderr)
        return 1

    index_text = index_path.read_text(encoding="utf-8")
    if experiment_id_in_index(index_text, experiment_id):
        print(f"experiment_id already present in {index_path}", file=sys.stderr)
        return 1

    print(f"\nUsing experiment_id: {experiment_id}\n")

    try:
        project = prompt_project_from_registry(repo_root)
    except (FileNotFoundError, ValueError) as e:
        print(e, file=sys.stderr)
        return 1

    purpose_full = prompt_nonempty("purpose (single line)")
    status = prompt_status()

    experimental_context = prompt_experimental_context()

    short_title = prompt_line("short_title (for index)", project)
    if not short_title:
        short_title = project

    note_location = prompt_location_block("note_location", use_reference=True)
    raw_data_location = prompt_location_block("raw_data_location", use_reference=False)
    processed_data_location = prompt_location_block(
        "processed_data_location", use_reference=False
    )
    analysis_location = prompt_location_path("analysis_location")

    index_summary = prompt_line("One-line summary for EXPERIMENT_INDEX.md", short_title)

    manifest = collect_manifest(
        experiment_id=experiment_id,
        iso_date=iso_date,
        project=project,
        purpose=purpose_full,
        status=status,
        experimental_context=experimental_context,
        note_location=note_location,
        raw_data_location=raw_data_location,
        processed_data_location=processed_data_location,
        analysis_location=analysis_location,
    )

    note_summary = f"{note_location.get('system', '')}: {note_location.get('reference', '')}"
    raw_summary = f"{raw_data_location.get('system', '')}: {raw_data_location.get('path_or_url', '')}"
    analysis_summary = f"{analysis_location.get('system', '')}: {analysis_location.get('path', '')}"

    freeform = prompt_line("Optional freeform notes for summary.md (body)", "")
    template_text = load_summary_template(repo_root)
    summary_body = render_summary(
        template_text,
        {
            "experiment_id": experiment_id,
            "iso_date": iso_date,
            "project": project,
            "status": status,
            "purpose": purpose_full,
            "short_title": short_title,
            "freeform_notes": freeform or "(none)",
            "note_location_summary": note_summary,
            "raw_data_location_summary": raw_summary,
            "processed_data_location_summary": (
                f"{processed_data_location.get('system', '')}: "
                f"{processed_data_location.get('path_or_url', '')}"
            ),
            "analysis_location_summary": analysis_summary,
            "biological_material": experimental_context.get("biological_material", ""),
            "stimulus": experimental_context.get("stimulus", ""),
            "assay": experimental_context.get("assay", ""),
            "readout": experimental_context.get("readout", ""),
            "comparison": experimental_context.get("comparison", ""),
        },
    )

    exp_dir.mkdir(parents=True, exist_ok=False)
    manifest_path = exp_dir / "manifest.yaml"
    summary_path = exp_dir / "summary.md"
    manifest_path.write_text(dump_yaml_document(manifest), encoding="utf-8")
    summary_path.write_text(summary_body, encoding="utf-8")

    row = [
        experiment_id,
        iso_date,
        project,
        short_title,
        status,
        note_summary,
        raw_summary,
        analysis_summary,
        index_summary,
    ]
    new_index = append_index_row(index_text, row)
    index_path.write_text(new_index, encoding="utf-8")

    print("\nDone.")
    print(f"  {manifest_path.relative_to(repo_root)}")
    print(f"  {summary_path.relative_to(repo_root)}")
    print(f"  updated {index_path.relative_to(repo_root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
