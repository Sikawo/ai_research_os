#!/usr/bin/env python3
"""
Step 1 of the shared_core deterministic governance check.

Read-only inspection of:
  - ``shared_core/`` at the repo root: every regular file is checked for the
    canonical-source marker in both the HTML-comment form and the blockquote
    form, and every ``CORE_*.md`` file is checked for a ``Source:`` line.
  - ``REPO_PROFILE.md`` at the repo root, if present: its
    ``## Floor-leak watch terms`` section is loaded and each term is searched,
    whole-word and case-insensitive, against the contents of ``shared_core/``.

This script writes no repository files. It uses the Python standard library
only and makes no external network calls.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path


SHARED_CORE_DIRNAME = "shared_core"
REPO_PROFILE_NAME = "REPO_PROFILE.md"
WATCH_TERMS_HEADING = "## Floor-leak watch terms"
CORE_FILE_PREFIX = "CORE_"
MARKDOWN_SUFFIX = ".md"
HTML_MARKER_TOKEN = "SHARED CORE"
BLOCKQUOTE_MARKER_TOKEN = "**SHARED CORE**"
SOURCE_LINE_PREFIX = "Source:"


@dataclass
class LeakMatch:
    path: str
    line_number: int
    term: str


@dataclass
class SharedCoreReport:
    shared_core_present: bool = False
    repo_profile_present: bool = False
    watch_section_present: bool = False
    watch_terms: list[str] = field(default_factory=list)
    marker_failures: list[str] = field(default_factory=list)
    source_failures: list[str] = field(default_factory=list)
    leak_matches: list[LeakMatch] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    info_lines: list[str] = field(default_factory=list)


def find_repo_root(start: Path | None = None) -> Path | None:
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
        return None
    return Path(result.stdout.strip()).resolve()


def iter_shared_core_files(shared_core_dir: Path) -> list[Path]:
    return sorted(p for p in shared_core_dir.rglob("*") if p.is_file())


def has_html_marker(text: str) -> bool:
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("<!--") and HTML_MARKER_TOKEN in stripped:
            return True
    return False


def has_blockquote_marker(text: str) -> bool:
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith(">") and BLOCKQUOTE_MARKER_TOKEN in stripped:
            return True
    return False


def has_source_line(text: str) -> bool:
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith(SOURCE_LINE_PREFIX):
            return True
    return False


def is_core_md_file(name: str) -> bool:
    return name.startswith(CORE_FILE_PREFIX) and name.endswith(MARKDOWN_SUFFIX)


def load_watch_terms(repo_profile_path: Path) -> tuple[bool, list[str]]:
    """Parse the ``## Floor-leak watch terms`` section.

    Returns ``(section_present, terms)``. The section ends at the next
    Markdown heading (``#`` at the start of the stripped line) or end of file.
    Inside the section, each line beginning with ``- `` contributes one term
    (the first whitespace-delimited token of the bullet body). Lines beginning
    with ``<!--`` are skipped.
    """
    try:
        text = repo_profile_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return (False, [])

    section_present = False
    in_section = False
    terms: list[str] = []

    for line in text.splitlines():
        stripped = line.strip()
        if stripped == WATCH_TERMS_HEADING:
            section_present = True
            in_section = True
            continue
        if not in_section:
            continue
        if stripped.startswith("#"):
            in_section = False
            continue
        if stripped.startswith("<!--"):
            continue
        if stripped.startswith("- "):
            bullet_body = stripped[2:].strip()
            if not bullet_body:
                continue
            term = bullet_body.split()[0]
            if term:
                terms.append(term)

    return (section_present, terms)


def scan_for_leaks(
    files: list[Path],
    terms: list[str],
    repo_root: Path,
) -> list[LeakMatch]:
    if not terms:
        return []

    patterns = [
        (term, re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE))
        for term in terms
    ]
    matches: list[LeakMatch] = []

    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        try:
            rel = path.relative_to(repo_root).as_posix()
        except ValueError:
            rel = str(path)
        for line_number, line in enumerate(text.splitlines(), start=1):
            for term, pattern in patterns:
                if pattern.search(line):
                    matches.append(
                        LeakMatch(path=rel, line_number=line_number, term=term)
                    )

    return matches


def check_shared_core(repo_root: Path) -> SharedCoreReport:
    report = SharedCoreReport()
    shared_core_dir = repo_root / SHARED_CORE_DIRNAME

    if not shared_core_dir.is_dir():
        report.info_lines.append(
            f"{SHARED_CORE_DIRNAME}/: not present, shared_core check skipped"
        )
        return report

    report.shared_core_present = True
    files = iter_shared_core_files(shared_core_dir)

    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        try:
            rel = path.relative_to(repo_root).as_posix()
        except ValueError:
            rel = str(path)

        if not has_html_marker(text):
            report.marker_failures.append(
                f"{rel}: missing HTML-comment SHARED CORE marker"
            )
        if not has_blockquote_marker(text):
            report.marker_failures.append(
                f"{rel}: missing blockquote **SHARED CORE** marker"
            )

        if is_core_md_file(path.name) and not has_source_line(text):
            report.source_failures.append(f"{rel}: missing Source: line")

    repo_profile_path = repo_root / REPO_PROFILE_NAME
    if not repo_profile_path.is_file():
        report.info_lines.append(
            f"{REPO_PROFILE_NAME}: not present, leak scan skipped"
        )
    else:
        report.repo_profile_present = True
        section_present, terms = load_watch_terms(repo_profile_path)
        report.watch_section_present = section_present
        report.watch_terms = sorted(terms)

        if not section_present:
            report.info_lines.append(
                f"{REPO_PROFILE_NAME}: present, "
                f"{WATCH_TERMS_HEADING} section not present, leak scan skipped"
            )
        elif not terms:
            report.info_lines.append(
                f"{REPO_PROFILE_NAME}: present, "
                f"{WATCH_TERMS_HEADING} section present, watch terms loaded: 0"
            )
        else:
            report.info_lines.append(
                f"{REPO_PROFILE_NAME}: present, watch terms loaded: {len(terms)}"
            )
            report.info_lines.append(
                f"Watch terms (sorted): {', '.join(report.watch_terms)}"
            )
            report.leak_matches = scan_for_leaks(files, terms, repo_root)

    for fail in report.marker_failures:
        report.errors.append(f"Shared Core marker missing: {fail}")
    for fail in report.source_failures:
        report.errors.append(f"Shared Core Source line missing: {fail}")
    for match in report.leak_matches:
        report.warnings.append(
            f"Shared Core leak: {match.path}:{match.line_number}: {match.term}"
        )

    return report


def render_report(report: SharedCoreReport) -> list[str]:
    lines: list[str] = []

    for info in report.info_lines:
        lines.append(info)

    if report.marker_failures:
        lines.append("FAIL: shared_core marker missing in the following files:")
        for fail in report.marker_failures:
            lines.append(f"  {fail}")

    if report.source_failures:
        lines.append("FAIL: shared_core Source: line missing in the following files:")
        for fail in report.source_failures:
            lines.append(f"  {fail}")

    if report.leak_matches:
        lines.append(
            "WARN: shared_core contains repo-specific terms from "
            "REPO_PROFILE.md watch list:"
        )
        for match in report.leak_matches:
            lines.append(f"  {match.path}:{match.line_number}: {match.term}")

    if report.shared_core_present and not report.marker_failures and not report.source_failures:
        if not report.leak_matches:
            lines.append("OK: shared_core marker, Source, and leak checks passed.")
        else:
            lines.append(
                "OK: shared_core marker and Source checks passed "
                "(leak findings are WARN only)."
            )

    return lines


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inspect shared_core/ for marker, Source, and leak issues.",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        help="repository root to inspect (default: discovered from cwd via git).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if args.repo_root is not None:
        repo_root = args.repo_root.resolve()
    else:
        discovered = find_repo_root()
        if discovered is None:
            print(
                "FAIL: This command must be run inside a git repository "
                "(or pass --repo-root).",
                file=sys.stderr,
            )
            return 1
        repo_root = discovered

    print("Shared Core check")
    print(f"Repo root: {repo_root}")

    report = check_shared_core(repo_root)
    for line in render_report(report):
        print(line)

    print()
    if report.errors:
        print(f"FAIL ({len(report.errors)} blocking issue(s))")
        return 1
    if report.warnings:
        print(f"WARN ({len(report.warnings)} non-blocking finding(s))")
        return 0
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
