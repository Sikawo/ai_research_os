#!/usr/bin/env python3
"""Safely import reviewed PubMed abstract-screening records."""

from __future__ import annotations

import argparse
import os
import re
import shutil
import stat
import sys
import tempfile
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


REQUIRED_MARKDOWN_FILES = (
    "SEARCH_SUMMARY.md",
    "SCREENING_TABLE.md",
    "DEEP_READING_SELECTION.md",
    "ABSTRACT_REVIEW.md",
    "FULL_TEXT_READING_PLAN.md",
)
IGNORED_SUFFIXES = {".zip", ".csv", ".json", ".xml", ".pdf"}
UNSAFE_LITERAL_MARKERS = (
    "/" + "Users/" + "the researcher",
    "file:" + "//",
    "source" + "_url",
)
UNSAFE_METADATA_PATTERNS = (
    ("full_text_reviewed: yes", re.compile(r"(?mi)^\s*full_text_reviewed\s*:\s*yes\s*$")),
    (
        "note_depth: full_text_reviewed",
        re.compile(r"(?mi)^\s*note_depth\s*:\s*full_text_reviewed\s*$"),
    ),
)
TOPIC_SLUG_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


@dataclass
class ImportPlan:
    source: Path
    source_type: str
    source_root: Path
    managed_root: Path
    destination: Path
    required_files: tuple[str, ...]
    ignored: list[str] = field(default_factory=list)
    safety_markers: dict[str, list[str]] = field(default_factory=dict)
    temp_dir: tempfile.TemporaryDirectory[str] | None = None

    @property
    def safety_passed(self) -> bool:
        return not self.safety_markers

    def cleanup(self) -> None:
        if self.temp_dir is not None:
            self.temp_dir.cleanup()
            self.temp_dir = None


def safe_display_path(path: Path, repo_root: Path | None = None) -> str:
    expanded = path.expanduser()
    try:
        resolved = expanded.resolve()
    except OSError:
        resolved = expanded.absolute()
    if repo_root is not None:
        try:
            return resolved.relative_to(repo_root.resolve()).as_posix()
        except ValueError:
            pass
    home = Path.home()
    try:
        return "~/" + resolved.relative_to(home.resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def validate_source_path(source: Path) -> Path:
    requested = source.expanduser()
    if requested.is_symlink():
        raise ValueError(f"--source must not be a symlink: {source}")
    resolved = requested.resolve()
    if not resolved.exists():
        raise ValueError(f"--source must exist: {source}")
    if not resolved.is_dir() and not resolved.is_file():
        raise ValueError(f"--source must be a directory or .zip file: {source}")
    return resolved


def is_zip_symlink(info: zipfile.ZipInfo) -> bool:
    file_type = stat.S_IFMT(info.external_attr >> 16)
    return file_type == stat.S_IFLNK


def validate_zip_member(info: zipfile.ZipInfo) -> None:
    name = info.filename
    path = Path(name)
    if path.is_absolute() or name.startswith(("/", "\\")):
        raise ValueError(f"Unsafe zip entry path: {name}")
    normalized_parts = [part for part in name.replace("\\", "/").split("/") if part not in {"", "."}]
    if any(part == ".." for part in normalized_parts):
        raise ValueError(f"Unsafe zip entry path: {name}")
    if is_zip_symlink(info):
        raise ValueError(f"Unsafe zip entry is a symlink: {name}")


def locate_managed_root(extraction_root: Path) -> Path:
    candidates = [extraction_root]
    candidates.extend(path for path in sorted(extraction_root.iterdir()) if path.is_dir() and not path.is_symlink())
    matching = [candidate for candidate in candidates if all((candidate / filename).exists() for filename in REQUIRED_MARKDOWN_FILES)]
    if not matching:
        scored = [
            (sum(1 for filename in REQUIRED_MARKDOWN_FILES if (candidate / filename).exists()), candidate)
            for candidate in candidates
        ]
        found_count, best_candidate = max(scored, key=lambda item: item[0])
        missing = [
            filename for filename in REQUIRED_MARKDOWN_FILES if not (best_candidate / filename).exists()
        ]
        if found_count == 0:
            missing = list(REQUIRED_MARKDOWN_FILES)
        raise ValueError("Missing required Markdown file(s): " + ", ".join(missing))
    if len(matching) > 1:
        display = ", ".join(path.relative_to(extraction_root).as_posix() or "." for path in matching)
        raise ValueError(f"Multiple managed Markdown source folders found in zip: {display}")
    return matching[0]


def prepare_source(source: Path) -> tuple[Path, str, Path, Path, tempfile.TemporaryDirectory[str] | None]:
    resolved = validate_source_path(source)
    if resolved.is_dir():
        return resolved, "directory", resolved, resolved, None
    if resolved.suffix.lower() != ".zip":
        raise ValueError(f"--source must be a directory or .zip file: {source}")
    temp_dir = tempfile.TemporaryDirectory(prefix="pubmed_screening_import_")
    extraction_root = Path(temp_dir.name)
    try:
        with zipfile.ZipFile(resolved) as archive:
            for info in archive.infolist():
                validate_zip_member(info)
            archive.extractall(extraction_root)
        managed_root = locate_managed_root(extraction_root)
    except zipfile.BadZipFile as exc:
        temp_dir.cleanup()
        raise ValueError(f"--source is not a readable zip file: {source}") from exc
    except ValueError:
        temp_dir.cleanup()
        raise
    return resolved, "zip", extraction_root, managed_root, temp_dir


def validate_topic_slug(topic_slug: str) -> str:
    if not TOPIC_SLUG_PATTERN.fullmatch(topic_slug):
        raise ValueError("--topic-slug may contain only letters, numbers, underscores, and hyphens")
    return topic_slug


def validate_date(value: str) -> str:
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError("--date must use YYYY-MM-DD") from exc
    if parsed.strftime("%Y-%m-%d") != value:
        raise ValueError("--date must use YYYY-MM-DD")
    return value


def ensure_under_literature_searches(repo_root: Path, destination: Path) -> Path:
    literature_root = (repo_root / "Literature_Searches").resolve()
    resolved_destination = destination.resolve()
    try:
        resolved_destination.relative_to(literature_root)
    except ValueError as exc:
        raise ValueError("Destination must stay under Literature_Searches/") from exc
    return resolved_destination


def destination_for(repo_root: Path, date: str, topic_slug: str) -> Path:
    return ensure_under_literature_searches(
        repo_root.resolve(),
        repo_root.resolve() / "Literature_Searches" / f"{date}_{topic_slug}",
    )


def validate_required_source_files(source: Path) -> None:
    missing: list[str] = []
    invalid: list[str] = []
    for filename in REQUIRED_MARKDOWN_FILES:
        path = source / filename
        if not path.exists():
            missing.append(filename)
            continue
        if path.is_symlink():
            invalid.append(f"{filename} is a symlink")
            continue
        if not path.is_file():
            invalid.append(f"{filename} is not a regular file")
    if missing:
        raise ValueError("Missing required Markdown file(s): " + ", ".join(missing))
    if invalid:
        raise ValueError("Unsafe required source file(s): " + ", ".join(invalid))


def destination_has_unmanaged_content(destination: Path) -> bool:
    if not destination.exists():
        return False
    return any(destination.iterdir())


def validate_destination_managed_files(destination: Path) -> None:
    if not destination.exists():
        return
    invalid: list[str] = []
    for filename in REQUIRED_MARKDOWN_FILES:
        path = destination / filename
        if not path.exists() and not path.is_symlink():
            continue
        if path.is_symlink():
            invalid.append(f"{filename} is a symlink")
        elif not path.is_file():
            invalid.append(f"{filename} is not a regular file")
    if invalid:
        raise ValueError("Unsafe managed destination file(s): " + ", ".join(invalid))


def classify_ignored_path(relative_path: str, is_dir: bool) -> str | None:
    parts = Path(relative_path).parts
    if any(part in {"paper_note_drafts", "exports"} for part in parts):
        return relative_path + ("/" if is_dir and not relative_path.endswith("/") else "")
    if any("Bookends" in part for part in parts):
        return relative_path + ("/" if is_dir and not relative_path.endswith("/") else "")
    if is_dir:
        return relative_path + "/"
    suffix = Path(relative_path).suffix.lower()
    if suffix in IGNORED_SUFFIXES:
        return relative_path
    return relative_path


def ignored_source_paths(scan_root: Path, managed_root: Path) -> list[str]:
    imported = {
        (managed_root / filename).relative_to(scan_root).as_posix() for filename in REQUIRED_MARKDOWN_FILES
    }
    ignored: list[str] = []
    for root, dirnames, filenames in os.walk(scan_root, followlinks=False):
        root_path = Path(root)
        for dirname in sorted(dirnames):
            path = root_path / dirname
            if path == managed_root or path in managed_root.parents:
                continue
            relative = path.relative_to(scan_root).as_posix()
            ignored_path = classify_ignored_path(relative, is_dir=True)
            if ignored_path is not None:
                ignored.append(ignored_path)
        for filename in sorted(filenames):
            path = root_path / filename
            relative = path.relative_to(scan_root).as_posix()
            if relative in imported and not path.is_symlink():
                continue
            ignored_path = classify_ignored_path(relative, is_dir=False)
            if ignored_path is not None:
                ignored.append(ignored_path + (" (symlink)" if path.is_symlink() else ""))
    return sorted(dict.fromkeys(ignored))


def unsafe_markers_in_text(text: str) -> list[str]:
    markers = [marker for marker in UNSAFE_LITERAL_MARKERS if marker in text]
    for label, pattern in UNSAFE_METADATA_PATTERNS:
        if pattern.search(text):
            markers.append(label)
    return markers


def safety_scan(source: Path) -> dict[str, list[str]]:
    findings: dict[str, list[str]] = {}
    for filename in REQUIRED_MARKDOWN_FILES:
        text = (source / filename).read_text(encoding="utf-8")
        markers = unsafe_markers_in_text(text)
        if markers:
            findings[filename] = markers
    return findings


def build_plan(args: argparse.Namespace) -> ImportPlan:
    repo_root = args.repo_root.expanduser().resolve()
    temp_dir: tempfile.TemporaryDirectory[str] | None = None
    try:
        source, source_type, source_root, managed_root, temp_dir = prepare_source(args.source)
        topic_slug = validate_topic_slug(args.topic_slug)
        date = validate_date(args.date)
        destination = destination_for(repo_root, date, topic_slug)

        validate_required_source_files(managed_root)
        if destination_has_unmanaged_content(destination) and not args.overwrite:
            raise ValueError(
                "Destination already exists and is non-empty; pass --overwrite to replace managed Markdown files only"
            )
        validate_destination_managed_files(destination)

        plan = ImportPlan(
            source=source,
            source_type=source_type,
            source_root=source_root,
            managed_root=managed_root,
            destination=destination,
            required_files=REQUIRED_MARKDOWN_FILES,
            ignored=ignored_source_paths(source_root, managed_root),
            safety_markers=safety_scan(managed_root),
            temp_dir=temp_dir,
        )
        if not plan.safety_passed:
            detail = "; ".join(
                f"{filename}: {', '.join(markers)}" for filename, markers in plan.safety_markers.items()
            )
            raise ValueError(f"Unsafe marker(s) detected in source Markdown: {detail}")
        return plan
    except ValueError:
        if temp_dir is not None:
            temp_dir.cleanup()
        raise


def copy_managed_files(plan: ImportPlan) -> list[str]:
    plan.destination.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    for filename in plan.required_files:
        shutil.copyfile(plan.managed_root / filename, plan.destination / filename, follow_symlinks=False)
        copied.append(filename)
    return copied


def render_summary(
    plan: ImportPlan,
    copied: list[str],
    dry_run: bool,
    repo_root: Path,
) -> str:
    action = "Dry run complete" if dry_run else "Import complete"
    ignored = "\n".join(f"- {path}" for path in plan.ignored) or "- none"
    copied_lines = "\n".join(f"- {filename}" for filename in copied) or "- none"
    safety_result = "PASS" if plan.safety_passed else "BLOCKED"
    return "\n".join(
        [
            action,
            f"Source path: {safe_display_path(plan.source, repo_root)}",
            f"Source type: {plan.source_type}",
            f"Destination folder: {safe_display_path(plan.destination, repo_root)}",
            "",
            "Managed Markdown files:",
            copied_lines,
            "",
            "Ignored files or folders:",
            ignored,
            "",
            f"Safety scan result: {safety_result}",
            "No Papers/, Bookends files, PDFs, raw data, or external AI APIs were touched.",
        ]
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import reviewed PubMed abstract-screening Markdown records into Literature_Searches/.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--topic-slug", required=True)
    parser.add_argument("--date", required=True)
    parser.add_argument("--overwrite", action="store_true")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        default=True,
        help="Preview the import without writing files (the default).",
    )
    mode.add_argument(
        "--apply",
        dest="dry_run",
        action="store_false",
        help="Write the five reviewed Markdown records after the preview is approved.",
    )
    parser.add_argument("--repo-root", type=Path, default=Path.cwd(), help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = args.repo_root.expanduser().resolve()
    try:
        plan = build_plan(args)
    except ValueError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    try:
        copied = list(plan.required_files)
        if not args.dry_run:
            copied = copy_managed_files(plan)
        print(render_summary(plan, copied, args.dry_run, repo_root))
        return 0
    finally:
        plan.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
