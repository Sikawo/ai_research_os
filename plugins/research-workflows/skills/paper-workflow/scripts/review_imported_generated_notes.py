#!/usr/bin/env python3
"""Validate and optionally apply ChatGPT-generated abstract/metadata notes."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


DEFAULT_REVIEW_ROOT = Path("exports/paper_note_import_review")
REQUIRED_METADATA = {
    "source": "bookends_xml",
    "note_depth": "abstract_metadata_only",
    "security_tier": "public",
}
UNSAFE_SUBSTRINGS = (
    "/" + "Users/" + "the researcher",
    "file:" + "//",
    "source" + "_url",
    "Bookends/Attachments",
    "BEGIN OPENSSH PRIVATE KEY",
    "api_key",
    "password:",
    "secret:",
    "token:",
    "restricted_internal",
    "NIH-internal",
    "unpublished manuscript",
    "reviewer comments",
    "confidential figure",
)
FULL_TEXT_CLAIM_PATTERNS = (
    r"\bfull[- ]text (?:was )?(?:reviewed|read|analyzed|analysed)\b",
    r"\bfigure[- ]level\b",
    r"\bsupplementary[- ]material review\b",
    r"\bPDF (?:was )?(?:reviewed|read|analyzed|analysed)\b",
    r"\bbased on (?:the )?PDF\b",
)


@dataclass
class CandidateNote:
    archive_path: str
    filename: str
    destination: Path
    text: str
    errors: list[str] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.errors


@dataclass
class CommandResult:
    label: str
    returncode: int
    output: str


def timestamp_for_paths() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def safe_display_path(path: Path) -> str:
    expanded = path.expanduser()
    home = Path.home()
    try:
        return "~/" + expanded.resolve().relative_to(home.resolve()).as_posix()
    except ValueError:
        pass
    if expanded.is_absolute():
        try:
            return expanded.resolve().relative_to(Path.cwd().resolve()).as_posix()
        except ValueError:
            return expanded.name
    return expanded.as_posix()


def load_manifest(path: Path) -> dict[str, object]:
    return json.loads(path.expanduser().read_text(encoding="utf-8"))


def load_manifest_from_export_zip(path: Path) -> dict[str, object]:
    export_zip = path.expanduser()
    with zipfile.ZipFile(export_zip) as archive:
        return json.loads(archive.read("MANIFEST.json").decode("utf-8"))


def load_manifest_from_args(args: argparse.Namespace) -> dict[str, object]:
    if args.manifest is not None:
        return load_manifest(args.manifest)
    return load_manifest_from_export_zip(args.export_zip)


def manifest_display_from_args(args: argparse.Namespace) -> str:
    if args.manifest is not None:
        return safe_display_path(args.manifest)
    return safe_display_path(args.export_zip) + " (MANIFEST.json)"


def resolve_input_path(input_path: Path) -> Path:
    """Resolve a generated-note ZIP/folder, allowing one adjacent auto-unzip counterpart."""
    requested = input_path.expanduser()
    if requested.exists():
        return requested

    if requested.suffix.lower() == ".zip":
        extracted_folder = requested.with_suffix("")
        if extracted_folder.is_dir():
            return extracted_folder
        raise ValueError(
            "--input not found: "
            f"{safe_display_path(requested)}; auto-extracted folder not found: "
            f"{safe_display_path(extracted_folder)}"
        )

    zip_counterpart = requested.parent / f"{requested.name}.zip"
    if zip_counterpart.exists() and zipfile.is_zipfile(zip_counterpart):
        return zip_counterpart

    raise ValueError(
        "--input not found: "
        f"{safe_display_path(requested)}; ZIP counterpart not found: {safe_display_path(zip_counterpart)}"
    )


def expected_destinations(manifest: dict[str, object]) -> dict[str, Path]:
    values = manifest.get("expected_target_note_paths")
    if not isinstance(values, list):
        raise ValueError("Manifest is missing expected_target_note_paths.")

    destinations: dict[str, Path] = {}
    for value in values:
        if not isinstance(value, str):
            raise ValueError("Manifest expected_target_note_paths must contain strings.")
        path = Path(value)
        validate_destination_path(path)
        basename = path.name
        if basename in destinations:
            raise ValueError(f"Manifest has duplicate target basename: {basename}")
        destinations[basename] = path
    return destinations


def validate_destination_path(path: Path) -> None:
    if path.is_absolute():
        raise ValueError(f"Destination path must be relative: {path}")
    if path.suffix != ".md":
        raise ValueError(f"Destination path must be Markdown: {path}")
    if not path.parts or path.parts[0] != "Papers":
        raise ValueError(f"Destination path must be under Papers/: {path}")
    if ".." in path.parts:
        raise ValueError(f"Destination path must not contain '..': {path}")


def read_input_files(input_path: Path) -> tuple[dict[str, str], list[str]]:
    input_path = input_path.expanduser()
    files: dict[str, str] = {}
    unexpected: list[str] = []
    if input_path.is_dir():
        for path in sorted(child for child in input_path.rglob("*") if child.is_file()):
            rel = path.relative_to(input_path).as_posix()
            if path.suffix != ".md":
                unexpected.append(rel)
                continue
            files[rel] = path.read_text(encoding="utf-8")
        return files, unexpected

    if zipfile.is_zipfile(input_path):
        with zipfile.ZipFile(input_path) as archive:
            for info in archive.infolist():
                if info.is_dir():
                    continue
                name = info.filename
                if Path(name).suffix != ".md":
                    unexpected.append(name)
                    continue
                files[name] = archive.read(info).decode("utf-8")
        return files, unexpected

    raise ValueError(f"--input must be a ZIP file or folder: {input_path}")


def has_required_metadata(text: str, key: str, value: str) -> bool:
    pattern = rf"(?m)^\s*{re.escape(key)}\s*:\s*['\"]?{re.escape(value)}['\"]?\s*$"
    return re.search(pattern, text) is not None


def unsafe_markers(text: str) -> list[str]:
    markers = [marker for marker in UNSAFE_SUBSTRINGS if marker in text]
    for pattern in FULL_TEXT_CLAIM_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE):
            markers.append(pattern)
    return markers


def validate_candidate(candidate: CandidateNote, repo_root: Path) -> None:
    validate_destination_path(candidate.destination)
    for key, value in REQUIRED_METADATA.items():
        if not has_required_metadata(candidate.text, key, value):
            candidate.errors.append(f"missing required metadata {key}: {value}")

    markers = unsafe_markers(candidate.text)
    if markers:
        candidate.errors.append("unsafe or out-of-route marker(s): " + ", ".join(markers))

    destination = repo_root / candidate.destination
    if destination.exists():
        candidate.errors.append(f"destination already exists: {candidate.destination.as_posix()}")


def build_candidates(
    input_files: dict[str, str],
    expected: dict[str, Path],
    repo_root: Path,
) -> tuple[list[CandidateNote], list[str]]:
    candidates: list[CandidateNote] = []
    unexpected: list[str] = []
    seen: set[str] = set()
    for archive_path, text in sorted(input_files.items()):
        filename = Path(archive_path).name
        if filename in seen:
            unexpected.append(f"{archive_path} (duplicate basename)")
            continue
        seen.add(filename)
        destination = expected.get(filename)
        if destination is None:
            unexpected.append(archive_path)
            continue
        candidate = CandidateNote(
            archive_path=archive_path,
            filename=filename,
            destination=destination,
            text=text,
        )
        validate_candidate(candidate, repo_root)
        candidates.append(candidate)
    return candidates, unexpected


def run_command(repo_root: Path, label: str, args: list[str], env: dict[str, str] | None = None) -> CommandResult:
    result = subprocess.run(
        args,
        cwd=repo_root,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    output = "\n".join(part.rstrip() for part in (result.stdout, result.stderr) if part.strip())
    return CommandResult(label=label, returncode=result.returncode, output=output or "OK")


def git_status(repo_root: Path) -> CommandResult:
    return run_command(repo_root, "git status --short", ["git", "status", "--short"])


def run_review_commands(repo_root: Path) -> list[CommandResult]:
    results = [
        git_status(repo_root),
        run_command(repo_root, "git diff --check", ["git", "diff", "--check"]),
        run_command(repo_root, "git diff --cached --check", ["git", "diff", "--cached", "--check"]),
    ]
    safety_script = repo_root / "Scripts" / "run_safety_check.py"
    if safety_script.exists():
        env = os.environ.copy()
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        results.append(
            run_command(
                repo_root,
                "PYTHONDONTWRITEBYTECODE=1 python3 Scripts/run_safety_check.py",
                ["python3", "Scripts/run_safety_check.py"],
                env=env,
            )
        )
    else:
        results.append(CommandResult("PYTHONDONTWRITEBYTECODE=1 python3 Scripts/run_safety_check.py", 0, "SKIPPED: script not found"))
    return results


def copy_candidates(candidates: list[CandidateNote], repo_root: Path) -> list[str]:
    copied: list[str] = []
    for candidate in candidates:
        destination = repo_root / candidate.destination
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(candidate.text, encoding="utf-8")
        copied.append(candidate.destination.as_posix())
    return copied


def expected_status_entries(copied: list[str], command_results: list[CommandResult]) -> list[str]:
    entries = [f"?? {path}" for path in copied]
    status = next((result.output for result in command_results if result.label == "git status --short"), "")
    for line in status.splitlines():
        if line[3:].strip() == "Indexes/PAPER_SOURCE_MAP.yaml" and line not in entries:
            entries.append(line)
    return entries


def status_matches_expectation(copied: list[str], command_results: list[CommandResult]) -> bool:
    if not copied:
        return True
    status = next((result.output for result in command_results if result.label == "git status --short"), "")
    status_lines = {line for line in status.splitlines() if line.strip()}
    for path in copied:
        if f"?? {path}" not in status_lines:
            return False
    allowed = {f"?? {path}" for path in copied}
    allowed.update(line for line in status_lines if line[3:].strip() == "Indexes/PAPER_SOURCE_MAP.yaml")
    allowed.update(line for line in status_lines if line[3:].strip().startswith("exports/paper_note_import_review/"))
    return status_lines.issubset(allowed)


def command_checks_pass(command_results: list[CommandResult]) -> bool:
    return all(result.returncode == 0 for result in command_results if not result.label.startswith("git status"))


def decide(
    candidates: list[CandidateNote],
    unexpected: list[str],
    missing: list[str],
    copied: list[str],
    command_results: list[CommandResult],
) -> str:
    if unexpected or missing:
        return "INVESTIGATE"
    if any(not candidate.valid for candidate in candidates):
        return "INVESTIGATE"
    if not command_checks_pass(command_results):
        return "INVESTIGATE"
    if not status_matches_expectation(copied, command_results):
        return "INVESTIGATE"
    return "APPROVE CANDIDATE"


def fenced(text: str) -> str:
    return "```text\n" + (text.rstrip() or "OK") + "\n```"


def render_review_packet(
    args: argparse.Namespace,
    resolved_input: Path,
    expected: dict[str, Path],
    candidates: list[CandidateNote],
    unexpected: list[str],
    missing: list[str],
    copied: list[str],
    command_results: list[CommandResult],
    decision: str,
) -> str:
    expected_paths = [path.as_posix() for path in expected.values()]
    valid_paths = [candidate.destination.as_posix() for candidate in candidates if candidate.valid]
    invalid_lines = [
        f"- {candidate.archive_path}: {'; '.join(candidate.errors)}"
        for candidate in candidates
        if candidate.errors
    ]
    not_copied = [candidate.destination.as_posix() for candidate in candidates if candidate.valid and not args.apply]
    expected_status = expected_status_entries(copied, command_results)
    next_commands: list[str] = []
    if decision == "APPROVE CANDIDATE" and args.apply:
        add_paths = " ".join(copied + ["Indexes/PAPER_SOURCE_MAP.yaml"])
        next_commands = [
            f"git add {add_paths}".rstrip(),
            "git diff --cached --check",
            "PYTHONDONTWRITEBYTECODE=1 python3 Scripts/run_safety_check.py",
            'git commit -m "Add abstract metadata paper notes"',
            "git push origin main",
        ]
    elif decision == "APPROVE CANDIDATE":
        next_commands = ["python3 scripts/review_imported_generated_notes.py --apply --input <generated-note-zip-or-folder> --manifest <MANIFEST.json>"]

    sections = [
        "# Import Review Packet",
        "",
        f"- input: {safe_display_path(args.input)}",
        f"- resolved input: {safe_display_path(resolved_input)}",
        f"- manifest: {manifest_display_from_args(args)}",
        f"- apply used: {args.apply}",
        f"- suggested decision: {decision}",
        "",
        "## Expected Note Files",
        "\n".join(f"- `{path}`" for path in expected_paths) or "- none",
        "",
        "## Validated Note Files",
        "\n".join(f"- `{path}`" for path in valid_paths) or "- none",
        "",
        "## Rejected or Unexpected Files",
        "\n".join(f"- `{path}`" for path in unexpected) or "- none",
        "",
        "## Invalid Candidate Notes",
        "\n".join(invalid_lines) or "- none",
        "",
        "## Missing Expected Files",
        "\n".join(f"- `{path}`" for path in missing) or "- none",
        "",
        "## Files Copied",
        "\n".join(f"- `{path}`" for path in copied) or "- none",
        "",
        "## Files Not Copied",
        "\n".join(f"- `{path}`" for path in not_copied) or "- none",
        "",
        "## Expected git status --short Entries After Apply",
        "\n".join(f"- `{line}`" for line in expected_status) or "- none",
        "",
        "## Safety and Git Checks",
    ]
    for result in command_results:
        sections.extend(
            [
                f"### {result.label}",
                f"- exit code: {result.returncode}",
                fenced(result.output),
            ]
        )
    sections.extend(
        [
            "",
            "## Unsafe Marker Scan",
            "- PASS" if not any(candidate.errors for candidate in candidates) else "- INVESTIGATE candidate note errors above",
            "",
            "## Human-Controlled Next Commands",
            "\n".join(f"- `{command}`" for command in next_commands) or "- none",
            "",
        ]
    )
    return "\n".join(sections)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate and optionally apply ChatGPT-generated abstract/metadata paper notes.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--input", type=Path, required=True)
    manifest_group = parser.add_mutually_exclusive_group(required=True)
    manifest_group.add_argument("--manifest", type=Path)
    manifest_group.add_argument(
        "--export-zip",
        type=Path,
        help="Original ChatGPT handoff ZIP containing MANIFEST.json.",
    )
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--reveal-in-finder",
        action="store_true",
        help="On macOS, reveal the generated IMPORT_REVIEW_PACKET.md in Finder.",
    )
    parser.add_argument("--review-root", type=Path, default=DEFAULT_REVIEW_ROOT)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd(), help=argparse.SUPPRESS)
    parser.add_argument("--timestamp", help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def reveal_in_finder(packet_path: Path) -> None:
    if sys.platform != "darwin":
        print("--reveal-in-finder is only available on macOS; review packet was not revealed.")
        return
    result = subprocess.run(
        ["open", "-R", str(packet_path)],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode != 0:
        output = "\n".join(part.strip() for part in (result.stdout, result.stderr) if part.strip())
        detail = f": {output}" if output else ""
        print(f"Warning: could not reveal review packet in Finder{detail}")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = args.repo_root.expanduser().resolve()
    manifest = load_manifest_from_args(args)
    expected = expected_destinations(manifest)
    try:
        resolved_input = resolve_input_path(args.input)
    except ValueError as error:
        print(f"Error: {error}")
        return 1
    input_files, unexpected_files = read_input_files(resolved_input)
    candidates, unexpected_notes = build_candidates(input_files, expected, repo_root)
    unexpected = unexpected_files + unexpected_notes
    present = {candidate.filename for candidate in candidates}
    missing = [path.as_posix() for filename, path in expected.items() if filename not in present]

    copied: list[str] = []
    validation_passed = not unexpected and not missing and all(candidate.valid for candidate in candidates)
    if args.apply and validation_passed:
        copied = copy_candidates(candidates, repo_root)

    command_results = run_review_commands(repo_root)
    decision = decide(candidates, unexpected, missing, copied, command_results)
    timestamp = args.timestamp or timestamp_for_paths()
    review_dir = repo_root / args.review_root / timestamp
    review_dir.mkdir(parents=True, exist_ok=True)
    review_packet = review_dir / "IMPORT_REVIEW_PACKET.md"
    review_packet.write_text(
        render_review_packet(
            args,
            resolved_input,
            expected,
            candidates,
            unexpected,
            missing,
            copied,
            command_results,
            decision,
        ),
        encoding="utf-8",
    )

    print(f"Review packet: {review_packet}")
    print(f"Resolved input: {safe_display_path(resolved_input)}")
    print(f"Validated notes: {sum(1 for candidate in candidates if candidate.valid)}")
    print(f"Unexpected/rejected files: {len(unexpected)}")
    print(f"Missing expected files: {len(missing)}")
    print(f"Files copied: {len(copied)}")
    print(f"Suggested decision: {decision}")
    if args.reveal_in_finder:
        reveal_in_finder(review_packet)
    return 0 if validation_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
