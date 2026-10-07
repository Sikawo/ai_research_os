#!/usr/bin/env python3
"""
Register an experiment from a small request YAML file.

This is the request-file counterpart to Scripts/register_experiment.py. It
creates the same durable metadata files while keeping raw data external.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Mapping

from register_experiment import (
    PROJECT_REGISTRY_FILE,
    STATUS_VALUES,
    append_index_row,
    build_experiment_id,
    collect_manifest,
    dump_yaml_document,
    experiment_id_in_index,
    find_repo_root,
    load_summary_template,
    markdown_table_cell,
    parse_experiment_date,
    parse_project_registry,
    render_summary,
    validate_project_id,
)

UNSAFE_MARKERS = (
    "/" + "Users/",
    "/" + "home/",
    "file:" + "//",
    "source" + "_url",
)
DEFAULT_RAW_DATA_NOTES = "Raw data are stored externally and should not be renamed."


class RequestValidationError(RuntimeError):
    """Raised when an experiment request cannot be safely registered."""


def parse_request_yaml(text: str) -> dict[str, Any]:
    """
    Parse the conservative nested YAML subset used by the request template.

    Supported shape: two-space-indented mappings with scalar string/boolean
    values. Lists, multiline strings, anchors, and other YAML features are
    intentionally unsupported so the script needs no external dependency.
    """

    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, root)]

    for lineno, raw_line in enumerate(text.splitlines(), start=1):
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        if "\t" in raw_line:
            raise RequestValidationError(f"Line {lineno}: tabs are not supported.")

        indent = len(raw_line) - len(raw_line.lstrip(" "))
        if indent % 2 != 0:
            raise RequestValidationError(f"Line {lineno}: indentation must use two spaces.")

        line = raw_line.strip()
        if line.startswith("- "):
            raise RequestValidationError(f"Line {lineno}: lists are not supported.")
        if ":" not in line:
            raise RequestValidationError(f"Line {lineno}: expected 'key: value'.")

        key, rest = line.split(":", 1)
        key = key.strip()
        value_text = rest.strip()
        if not key:
            raise RequestValidationError(f"Line {lineno}: empty keys are not supported.")

        while stack and indent <= stack[-1][0]:
            stack.pop()
        if not stack:
            raise RequestValidationError(f"Line {lineno}: invalid indentation.")

        parent = stack[-1][1]
        if key in parent:
            raise RequestValidationError(f"Line {lineno}: duplicate key '{key}'.")

        if value_text == "":
            child: dict[str, Any] = {}
            parent[key] = child
            stack.append((indent, child))
        else:
            parent[key] = parse_scalar(value_text)

    return root


def parse_scalar(text: str) -> str | bool:
    if text in {"true", "True"}:
        return True
    if text in {"false", "False"}:
        return False
    if text.startswith('"') and text.endswith('"') and len(text) >= 2:
        return text[1:-1].replace('\\"', '"').replace("\\n", "\n")
    if text.startswith("'") and text.endswith("'") and len(text) >= 2:
        return text[1:-1].replace("\\'", "'")
    if " #" in text:
        text = text.split(" #", 1)[0].rstrip()
    return text


def read_request_file(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise RequestValidationError(f"Request file does not exist: {path}")
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        raise RequestValidationError(f"Could not read request file {path}: {e}") from e
    try:
        parsed = parse_request_yaml(text)
    except RequestValidationError:
        raise
    except Exception as e:
        raise RequestValidationError(f"Could not parse request file {path}: {e}") from e
    scan_for_unsafe_markers(parsed)
    return parsed


def scan_for_unsafe_markers(value: Any, path: str = "request") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if not isinstance(key, str):
                raise RequestValidationError(f"{path}: keys must be strings.")
            check_unsafe_text(key, f"{path}.{key}")
            child_path = f"{path}.{key}"
            if child_path == "request.storage.parent_path":
                continue
            scan_for_unsafe_markers(child, child_path)
        return
    if isinstance(value, str):
        check_unsafe_text(value, path)


def check_unsafe_text(text: str, path: str) -> None:
    for marker in UNSAFE_MARKERS:
        if marker in text:
            raise RequestValidationError(
                f"Unsafe marker '{marker}' found at {path}. Use a repo-safe external "
                "location, such as a cloud-relative path, rather than a local absolute path."
            )


def required_mapping(root: Mapping[str, Any], key: str) -> dict[str, Any]:
    value = root.get(key)
    if not isinstance(value, dict):
        raise RequestValidationError(f"Missing required section: {key}")
    return value


def required_text(root: Mapping[str, Any], key: str, section: str) -> str:
    value = root.get(key)
    if not isinstance(value, str) or not value.strip():
        raise RequestValidationError(f"Missing required field: {section}.{key}")
    return value.strip()


def optional_text(root: Mapping[str, Any], key: str, default: str = "") -> str:
    value = root.get(key)
    if value is None:
        return default
    if not isinstance(value, str):
        return str(value)
    return value.strip()


def request_bool(root: Mapping[str, Any], key: str, default: bool = False) -> bool:
    value = root.get(key, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.lower() in {"true", "false"}:
        return value.lower() == "true"
    raise RequestValidationError(f"Field project.{key} must be true or false.")


def location_with_required_fields(
    locations: Mapping[str, Any],
    name: str,
    required_fields: tuple[str, ...],
    defaults: Mapping[str, str] | None = None,
) -> dict[str, str]:
    section = required_mapping(locations, name)
    out: dict[str, str] = {}
    for field in required_fields:
        out[field] = required_text(section, field, name)
    for field, default in (defaults or {}).items():
        out[field] = optional_text(section, field, default)
    return out


def append_project_registry_row(text: str, project: Mapping[str, str]) -> str:
    row = "| " + " | ".join(
        markdown_table_cell(project[field])
        for field in ("project_id", "display_name", "description", "status")
    ) + " |"
    return text.rstrip() + "\n" + row + "\n"


def validate_project_request(
    repo_root: Path,
    project_section: Mapping[str, Any],
) -> tuple[str, bool, dict[str, str]]:
    project_id = required_text(project_section, "project_id", "project")
    validate_project_id(project_id)

    projects = parse_project_registry(repo_root)
    known_project_ids = {project["project_id"] for project in projects}
    if project_id in known_project_ids:
        return project_id, False, {}

    create_if_missing = request_bool(project_section, "create_if_missing", False)
    if not create_if_missing:
        raise RequestValidationError(
            f"Project '{project_id}' is not present in {PROJECT_REGISTRY_FILE}. "
            "Use an existing project_id or set project.create_if_missing: true."
        )

    new_project = {
        "project_id": project_id,
        "display_name": required_text(project_section, "display_name", "project"),
        "description": required_text(project_section, "description", "project"),
        "status": required_text(project_section, "status", "project"),
    }
    return project_id, True, new_project


def register_from_request(request_path: Path, repo_root: Path | None = None) -> dict[str, Any]:
    repo_root = repo_root or find_repo_root()
    request = read_request_file(request_path)

    project_section = required_mapping(request, "project")
    experiment_section = required_mapping(request, "experiment")
    context_section = required_mapping(request, "experimental_context")
    locations_section = required_mapping(request, "locations")
    summary_section = required_mapping(request, "summary")

    project_id, should_create_project, new_project = validate_project_request(
        repo_root, project_section
    )

    date_text = required_text(experiment_section, "date", "experiment")
    try:
        yyyymmdd, iso_date = parse_experiment_date(date_text)
    except ValueError as e:
        raise RequestValidationError(f"Invalid experiment.date: {e}") from e

    status = required_text(experiment_section, "status", "experiment")
    if status not in STATUS_VALUES:
        allowed = ", ".join(STATUS_VALUES)
        raise RequestValidationError(f"Invalid experiment.status '{status}'. Use one of: {allowed}.")

    short_description = required_text(experiment_section, "short_description", "experiment")
    try:
        experiment_id = build_experiment_id(yyyymmdd, short_description)
    except ValueError as e:
        raise RequestValidationError(f"Invalid experiment.short_description: {e}") from e

    exp_dir = repo_root / "Experiments" / experiment_id
    if exp_dir.exists():
        raise RequestValidationError(f"Refusing to overwrite existing folder: {exp_dir}")

    index_path = repo_root / "EXPERIMENT_INDEX.md"
    index_text = index_path.read_text(encoding="utf-8")
    if experiment_id_in_index(index_text, experiment_id):
        raise RequestValidationError(f"experiment_id already present in {index_path}: {experiment_id}")

    experimental_context = {
        "biological_material": required_text(
            context_section, "biological_material", "experimental_context"
        ),
        "stimulus": required_text(context_section, "stimulus", "experimental_context"),
        "assay": required_text(context_section, "assay", "experimental_context"),
        "readout": required_text(context_section, "readout", "experimental_context"),
        "comparison": required_text(context_section, "comparison", "experimental_context"),
    }
    note_location = location_with_required_fields(
        locations_section, "note_location", ("system", "reference")
    )
    raw_data_location = location_with_required_fields(
        locations_section,
        "raw_data_location",
        ("system", "path_or_url"),
        {"notes": DEFAULT_RAW_DATA_NOTES},
    )
    processed_data_location = location_with_required_fields(
        locations_section, "processed_data_location", ("system", "path_or_url")
    )
    analysis_location = location_with_required_fields(
        locations_section, "analysis_location", ("system", "path")
    )

    purpose = required_text(experiment_section, "purpose", "experiment")
    short_title = required_text(summary_section, "short_title", "summary")
    index_summary = required_text(summary_section, "index_summary", "summary")
    freeform_notes = optional_text(summary_section, "freeform_notes", "(none)") or "(none)"

    manifest = collect_manifest(
        experiment_id=experiment_id,
        iso_date=iso_date,
        project=project_id,
        purpose=purpose,
        status=status,
        experimental_context=experimental_context,
        note_location=note_location,
        raw_data_location=raw_data_location,
        processed_data_location=processed_data_location,
        analysis_location=analysis_location,
    )

    note_summary = f"{note_location.get('system', '')}: {note_location.get('reference', '')}"
    raw_summary = f"{raw_data_location.get('system', '')}: {raw_data_location.get('path_or_url', '')}"
    processed_summary = (
        f"{processed_data_location.get('system', '')}: "
        f"{processed_data_location.get('path_or_url', '')}"
    )
    analysis_summary = f"{analysis_location.get('system', '')}: {analysis_location.get('path', '')}"

    summary_body = render_summary(
        load_summary_template(repo_root),
        {
            "experiment_id": experiment_id,
            "iso_date": iso_date,
            "project": project_id,
            "status": status,
            "purpose": purpose,
            "short_title": short_title,
            "freeform_notes": freeform_notes,
            "note_location_summary": note_summary,
            "raw_data_location_summary": raw_summary,
            "processed_data_location_summary": processed_summary,
            "analysis_location_summary": analysis_summary,
            "biological_material": experimental_context.get("biological_material", ""),
            "stimulus": experimental_context.get("stimulus", ""),
            "assay": experimental_context.get("assay", ""),
            "readout": experimental_context.get("readout", ""),
            "comparison": experimental_context.get("comparison", ""),
        },
    )

    registry_path = repo_root / PROJECT_REGISTRY_FILE
    if should_create_project:
        registry_text = registry_path.read_text(encoding="utf-8")
        registry_path.write_text(
            append_project_registry_row(registry_text, new_project),
            encoding="utf-8",
        )

    exp_dir.mkdir(parents=True, exist_ok=False)
    manifest_path = exp_dir / "manifest.yaml"
    summary_path = exp_dir / "summary.md"
    manifest_path.write_text(dump_yaml_document(manifest), encoding="utf-8")
    summary_path.write_text(summary_body, encoding="utf-8")

    row = [
        experiment_id,
        iso_date,
        project_id,
        short_title,
        status,
        note_summary,
        raw_summary,
        analysis_summary,
        index_summary,
    ]
    index_path.write_text(append_index_row(index_text, row), encoding="utf-8")

    return {
        "experiment_id": experiment_id,
        "manifest_path": manifest_path,
        "summary_path": summary_path,
        "index_path": index_path,
        "project_registry_path": registry_path,
        "project_registry_updated": should_create_project,
    }


def print_success(result: Mapping[str, Any], repo_root: Path) -> None:
    print("Registered experiment from request.")
    print(f"  experiment_id: {result['experiment_id']}")
    print(f"  created manifest: {Path(result['manifest_path']).relative_to(repo_root)}")
    print(f"  created summary: {Path(result['summary_path']).relative_to(repo_root)}")
    print(f"  updated index: {Path(result['index_path']).relative_to(repo_root)}")
    if result["project_registry_updated"]:
        print(f"  updated project registry: {Path(result['project_registry_path']).relative_to(repo_root)}")
    else:
        print("  updated project registry: no")
    print()
    print("Recommended next commands:")
    print("  python3 Scripts/validate_experiments.py")
    print("  python3 Scripts/run_safety_check.py")
    print("  git diff -- PROJECT_REGISTRY.md EXPERIMENT_INDEX.md Experiments/")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="register_experiment_from_request.py",
        description="Register an experiment from a request YAML file.",
    )
    parser.add_argument("request_yaml", help="Path to the experiment request YAML file.")
    args = parser.parse_args(argv)

    try:
        repo_root = find_repo_root()
        result = register_from_request(Path(args.request_yaml), repo_root)
    except (
        FileNotFoundError,
        OSError,
        RequestValidationError,
        ValueError,
    ) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    print_success(result, repo_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
