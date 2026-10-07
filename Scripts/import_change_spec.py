#!/usr/bin/env python3
"""
Import a downloaded CHANGE_SPEC.md into repository workflow locations.

This script is intentionally conservative. It copies one validated source file
to a generated exports/ path. It does not stage, commit, push, pull, switch
branches, delete, move, rename, clean exports, create pull requests, upload
files, or modify the downloaded source file.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


CHANGE_START_ROOT_PARTS = ("exports", "change_start")
ACTIVE_CHANGE_PARTS = ("exports", "active_change")
ARCHIVED_CHANGE_SPECS_PARTS = ("exports", "archived_change_specs")
CHANGE_SPEC_NAME = "CHANGE_SPEC.md"
MAX_CHANGE_SPEC_BYTES = 1_000_000
TIMESTAMP_DIR_PATTERN = re.compile(r"^\d{8}_\d{6}$")
REQUIRED_SPEC_MARKERS = (
    "# Change Spec",
    "## Metadata",
    "Spec ID",
    "Target repo",
    "Expected branch",
    "Task",
    "Created for / change class",
)
METADATA_FIELDS = (
    "Spec ID",
    "Target repo",
    "Expected branch",
    "Task",
    "Created for / change class",
)
UNSAFE_SPEC_MARKERS = (
    "/" + "Users/",
    "/" + "home/",
    "file:" + "//",
    "source" + "_url",
)
METADATA_PATTERN = re.compile(r"^- (?P<key>[^:]+):\s*(?P<value>.+?)\s*$")


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


def display_path(path: Path, repo_root: Path | None = None) -> str:
    resolved = path.expanduser().resolve()
    if repo_root is not None:
        try:
            return resolved.relative_to(repo_root.resolve()).as_posix()
        except ValueError:
            pass

    home = Path.home().resolve()
    try:
        return "~/" + resolved.relative_to(home).as_posix()
    except ValueError:
        return str(resolved)


def read_source_spec(source_path: Path) -> str:
    path = source_path.expanduser()
    try:
        if not path.is_file():
            raise RuntimeError(f"Source spec does not exist or is not a file: {display_path(path)}")
        if path.suffix.lower() != ".md":
            raise RuntimeError(f"Source spec must be a Markdown file: {display_path(path)}")
        if path.stat().st_size > MAX_CHANGE_SPEC_BYTES:
            raise RuntimeError(
                f"Source spec is too large; maximum size is {MAX_CHANGE_SPEC_BYTES} bytes: "
                f"{display_path(path)}"
            )
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        raise RuntimeError(f"Source spec must be UTF-8 text: {display_path(path)}") from error
    except OSError as error:
        raise RuntimeError(f"Could not read source spec {display_path(path)}: {error}") from error


def validate_change_spec(spec_text: str) -> None:
    missing = [marker for marker in REQUIRED_SPEC_MARKERS if marker not in spec_text]
    if missing:
        missing_text = ", ".join(missing)
        raise RuntimeError(f"Source file does not look like a CHANGE_SPEC.md; missing: {missing_text}")


def unsafe_spec_markers(spec_text: str) -> list[str]:
    return [marker for marker in UNSAFE_SPEC_MARKERS if marker in spec_text]


def parse_metadata(spec_text: str) -> dict[str, str]:
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

        match = METADATA_PATTERN.match(line.strip())
        if match is None:
            continue

        key = match.group("key").strip()
        value = match.group("value").strip().strip("`")
        if key in METADATA_FIELDS:
            metadata[key] = value

    return metadata


def find_latest_change_start_dir(repo_root: Path) -> Path:
    change_start_root = repo_root.joinpath(*CHANGE_START_ROOT_PARTS)
    if not change_start_root.is_dir():
        raise RuntimeError(f"No {'/'.join(CHANGE_START_ROOT_PARTS)}/ folder exists.")

    candidates = [
        path
        for path in change_start_root.iterdir()
        if path.is_dir() and TIMESTAMP_DIR_PATTERN.match(path.name)
    ]
    if not candidates:
        raise RuntimeError(f"No timestamped folders found under {'/'.join(CHANGE_START_ROOT_PARTS)}/.")
    return max(candidates, key=lambda path: path.name)


def import_change_spec(source_path: Path, repo_root: Path, force: bool = False) -> Path:
    spec_text = read_source_spec(source_path)
    validate_change_spec(spec_text)

    latest_dir = find_latest_change_start_dir(repo_root)
    target_path = latest_dir / CHANGE_SPEC_NAME
    if target_path.exists() and not force:
        raise RuntimeError(f"Target already exists: {target_path}. Re-run with --force to overwrite it.")

    shutil.copyfile(source_path.expanduser(), target_path)
    return target_path


def next_archive_path(archive_dir: Path, timestamp: str | None = None) -> Path:
    stamp = timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    candidate = archive_dir / f"CHANGE_SPEC_{stamp}.md"
    if not candidate.exists():
        return candidate

    counter = 2
    while True:
        candidate = archive_dir / f"CHANGE_SPEC_{stamp}_{counter}.md"
        if not candidate.exists():
            return candidate
        counter += 1


def activate_change_spec(source_path: Path, repo_root: Path) -> tuple[Path, Path | None, dict[str, str], list[str]]:
    spec_text = read_source_spec(source_path)
    validate_change_spec(spec_text)

    active_dir = repo_root.joinpath(*ACTIVE_CHANGE_PARTS)
    archive_dir = repo_root.joinpath(*ARCHIVED_CHANGE_SPECS_PARTS)
    active_dir.mkdir(parents=True, exist_ok=True)
    archive_dir.mkdir(parents=True, exist_ok=True)

    active_path = active_dir / CHANGE_SPEC_NAME
    archived_path: Path | None = None
    if active_path.exists():
        archived_path = next_archive_path(archive_dir)
        shutil.copyfile(active_path, archived_path)

    shutil.copyfile(source_path.expanduser(), active_path)
    return active_path, archived_path, parse_metadata(spec_text), unsafe_spec_markers(spec_text)


def reveal_imported_spec(spec_path: Path, no_open: bool = False) -> None:
    if no_open or sys.platform != "darwin":
        return

    result = subprocess.run(["open", "-R", str(spec_path)], check=False)
    if result.returncode != 0:
        print("Warning: could not reveal imported CHANGE_SPEC.md in Finder.", file=sys.stderr)


def print_active_summary(
    active_path: Path,
    archived_path: Path | None,
    metadata: dict[str, str],
    unsafe_markers: list[str],
    repo_root: Path,
) -> None:
    print("Active CHANGE_SPEC.md imported.")
    print(f"Active spec: {display_path(active_path, repo_root)}")
    if archived_path is not None:
        print(f"Archived previous spec: {display_path(archived_path, repo_root)}")

    if metadata:
        print("Metadata:")
        for field in METADATA_FIELDS:
            value = metadata.get(field)
            if value:
                print(f"- {field}: {value}")

    if unsafe_markers:
        print(
            "Warning: source spec contains unsafe local/path marker(s): "
            + ", ".join(unsafe_markers),
            file=sys.stderr,
        )

    print("Next instruction: Implement exports/active_change/CHANGE_SPEC.md only.")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import a downloaded CHANGE_SPEC.md into a repository workflow location."
    )
    parser.add_argument("source_spec", nargs="?", type=Path, help="downloaded or saved CHANGE_SPEC.md path")
    parser.add_argument(
        "--latest",
        action="store_true",
        help="copy into the latest exports/change_start/<timestamp>/ folder",
    )
    parser.add_argument(
        "--active",
        type=Path,
        metavar="PATH_TO_CHANGE_SPEC.md",
        help="copy into exports/active_change/CHANGE_SPEC.md and archive any previous active spec",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="overwrite an existing CHANGE_SPEC.md in the selected change-start folder",
    )
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="do not reveal the imported file in Finder on macOS",
    )
    return parser.parse_args(argv)


def main() -> int:
    try:
        args = parse_args()
        if args.active is not None:
            if args.latest:
                raise RuntimeError("Choose either --active or --latest, not both.")
            if args.force:
                raise RuntimeError("--force is only supported with --latest.")
            if args.source_spec is not None:
                raise RuntimeError("Pass the source path to --active, not as a positional argument.")

            repo_root = find_repo_root()
            active_path, archived_path, metadata, unsafe_markers = activate_change_spec(args.active, repo_root)
            print_active_summary(active_path, archived_path, metadata, unsafe_markers, repo_root)
            return 0

        if not args.latest:
            raise RuntimeError("Pass --latest or --active to select the import target.")
        if args.source_spec is None:
            raise RuntimeError("Pass a downloaded or saved CHANGE_SPEC.md path.")

        repo_root = find_repo_root()
        target_path = import_change_spec(args.source_spec, repo_root, force=args.force)
        reveal_imported_spec(target_path, no_open=args.no_open)
    except RuntimeError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    print(target_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
