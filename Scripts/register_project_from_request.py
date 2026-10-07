#!/usr/bin/env python3
"""
Register one project from a small request YAML file.

The request format is intentionally tiny so this script can stay
standard-library-only and deterministic.
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path
from typing import Any, Mapping

from register_experiment import (
    PROJECT_REGISTRY_FILE,
    find_repo_root,
    markdown_table_cell,
    parse_project_registry,
    validate_project_id,
)

ALLOWED_FIELDS = ("project_id", "name", "status", "description", "notes")
REQUIRED_FIELDS = ("project_id", "name", "description")
STATUS_VALUES = ("active", "planned", "paused", "archived")
MAX_VALUE_LENGTHS = {
    "project_id": 64,
    "name": 120,
    "status": 24,
    "description": 500,
    "notes": 500,
}
UNSAFE_KEY_MARKERS = (
    "source" + "_url",
    "api_key",
    "access_token",
    "private_key",
    "credential",
    "credentials",
    "password",
    "token",
    ".env",
)
UNSAFE_VALUE_MARKERS = (
    "file:" + "//",
    "source" + "_url",
    "api_key",
    "access_token",
    "private_key",
    "credential",
    "credentials",
    "password",
    "token",
    ".env",
)


class RequestValidationError(RuntimeError):
    """Raised when a project request cannot be safely registered."""


def parse_request_yaml(text: str) -> dict[str, str]:
    """
    Parse a conservative top-level YAML subset.

    Supported lines are `key: value` with quoted or plain scalar values.
    Nested mappings, lists, multiline strings, anchors, and indentation are
    intentionally unsupported.
    """

    parsed: dict[str, str] = {}
    for lineno, raw_line in enumerate(text.splitlines(), start=1):
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        if "\t" in raw_line:
            raise RequestValidationError(f"Line {lineno}: tabs are not supported.")
        if raw_line[:1].isspace():
            raise RequestValidationError(f"Line {lineno}: indentation is not supported.")

        line = raw_line.strip()
        if line.startswith("- "):
            raise RequestValidationError(f"Line {lineno}: lists are not supported.")
        if ":" not in line:
            raise RequestValidationError(f"Line {lineno}: expected 'key: value'.")

        key, rest = line.split(":", 1)
        key = key.strip()
        value_text = rest.strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            raise RequestValidationError(f"Line {lineno}: invalid key '{key}'.")
        if key in parsed:
            raise RequestValidationError(f"Line {lineno}: duplicate key '{key}'.")
        if key not in ALLOWED_FIELDS:
            raise RequestValidationError(f"Line {lineno}: unsupported field '{key}'.")
        if value_text == "":
            raise RequestValidationError(f"Line {lineno}: field '{key}' needs a value.")

        parsed[key] = parse_scalar(value_text, lineno)

    return parsed


def parse_scalar(text: str, lineno: int) -> str:
    if text in {"|", ">"} or text.startswith(("|", ">")):
        raise RequestValidationError(f"Line {lineno}: multiline values are not supported.")
    if text.startswith(("{", "[", "&", "*", "!")):
        raise RequestValidationError(f"Line {lineno}: complex YAML values are not supported.")

    if text.startswith(('"', "'")):
        if len(text) < 2 or not text.endswith(text[0]):
            raise RequestValidationError(f"Line {lineno}: quoted value is not closed.")
        try:
            value = ast.literal_eval(text)
        except (SyntaxError, ValueError) as e:
            raise RequestValidationError(f"Line {lineno}: invalid quoted value.") from e
        if not isinstance(value, str):
            raise RequestValidationError(f"Line {lineno}: value must be a string.")
        return value.strip()

    if " #" in text:
        text = text.split(" #", 1)[0].rstrip()
    return text.strip()


def read_request_file(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise RequestValidationError(f"Request file does not exist: {path}")
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        raise RequestValidationError(f"Could not read request file {path}: {e}") from e
    return parse_request_yaml(text)


def require_text(request: Mapping[str, str], key: str) -> str:
    value = request.get(key)
    if value is None or not value.strip():
        raise RequestValidationError(f"Missing required field: {key}")
    return value.strip()


def check_unsafe_text(key: str, value: str) -> None:
    lowered_key = key.lower()
    lowered_value = value.lower()
    for marker in UNSAFE_KEY_MARKERS:
        if marker in lowered_key:
            raise RequestValidationError(f"Unsafe field name: {key}")
    for marker in UNSAFE_VALUE_MARKERS:
        if marker in lowered_value:
            raise RequestValidationError(f"Unsafe value in field: {key}")
    if re.search(r"(^|[\s\"'=])/(Users|home|Volumes|private|tmp|var)/", value):
        raise RequestValidationError(f"Local absolute path found in field: {key}")
    if "../" in value or "..\\" in value or "/.." in value:
        raise RequestValidationError(f"Path traversal-like content found in field: {key}")
    if "\n" in value or "\r" in value:
        raise RequestValidationError(f"Multiline value found in field: {key}")


def validate_project_request(
    repo_root: Path,
    request: Mapping[str, str],
) -> dict[str, str]:
    for key in REQUIRED_FIELDS:
        require_text(request, key)

    project_id = require_text(request, "project_id")
    try:
        validate_project_id(project_id)
    except ValueError as e:
        raise RequestValidationError(str(e)) from e

    status = request.get("status", "active").strip() or "active"
    if status not in STATUS_VALUES:
        allowed = ", ".join(STATUS_VALUES)
        raise RequestValidationError(f"Invalid status '{status}'. Use one of: {allowed}.")

    project = {
        "project_id": project_id,
        "display_name": require_text(request, "name"),
        "description": require_text(request, "description"),
        "status": status,
        "notes": request.get("notes", "").strip(),
    }

    for key, value in project.items():
        max_length = MAX_VALUE_LENGTHS.get("name" if key == "display_name" else key, 500)
        if len(value) > max_length:
            raise RequestValidationError(f"Field '{key}' is too long.")
        check_unsafe_text(key, value)

    projects = parse_project_registry(repo_root)
    known_project_ids = {project["project_id"] for project in projects}
    if project_id in known_project_ids:
        raise RequestValidationError(f"project_id already exists: {project_id}")

    return project


def append_project_registry_row(text: str, project: Mapping[str, str]) -> str:
    row = "| " + " | ".join(
        markdown_table_cell(project[field])
        for field in ("project_id", "display_name", "description", "status")
    ) + " |"
    return text.rstrip() + "\n" + row + "\n"


def register_project_from_request(
    request_path: Path,
    repo_root: Path | None = None,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    repo_root = repo_root or find_repo_root()
    request = read_request_file(request_path)
    project = validate_project_request(repo_root, request)

    registry_path = repo_root / PROJECT_REGISTRY_FILE
    registry_text = registry_path.read_text(encoding="utf-8")
    new_registry_text = append_project_registry_row(registry_text, project)
    if not dry_run:
        registry_path.write_text(new_registry_text, encoding="utf-8")

    return {
        "project_id": project["project_id"],
        "registry_path": registry_path,
        "row": append_project_registry_row("", project).strip(),
        "dry_run": dry_run,
    }


def print_success(result: Mapping[str, Any], repo_root: Path) -> None:
    if result["dry_run"]:
        print("Dry run passed. No files changed.")
        print(f"  project_id: {result['project_id']}")
        print(f"  would append: {result['row']}")
        return

    registry_rel = Path(result["registry_path"]).relative_to(repo_root)
    print("Registered project from request.")
    print(f"  project_id: {result['project_id']}")
    print(f"  updated registry: {registry_rel}")
    print()
    print("Recommended next commands:")
    print("  python3 Scripts/validate_experiments.py")
    print("  python3 Scripts/run_safety_check.py")
    print("  python3 Scripts/check_daily_metadata_lane.py")
    print("  git diff -- PROJECT_REGISTRY.md")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="register_project_from_request.py",
        description="Register a project from a small request YAML file.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Validate without editing.")
    parser.add_argument("request_yaml", help="Path to the project request YAML file.")
    args = parser.parse_args(argv)

    try:
        repo_root = find_repo_root()
        result = register_project_from_request(
            Path(args.request_yaml),
            repo_root,
            dry_run=args.dry_run,
        )
    except (FileNotFoundError, OSError, RequestValidationError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    print_success(result, repo_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
