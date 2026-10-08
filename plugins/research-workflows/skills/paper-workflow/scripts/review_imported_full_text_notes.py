#!/usr/bin/env python3
"""Validate and optionally apply ChatGPT-generated public full-text paper notes."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


DEFAULT_REVIEW_ROOT = Path("exports/full_text_note_import_review")
DEFAULT_PAPERS_DIR = Path("Papers")
ALLOWED_METADATA_VERIFICATION = {
    "verified",
    "partial",
    "needs_human_check",
    "pdf_only_not_externally_checked",
    "conflict_needs_human_check",
}
REQUIRED_METADATA = {
    "source": "uploaded_public_pdf",
    "note_depth": "public_full_text_reviewed",
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
    "under-review manuscript",
    "unpublished manuscript",
    "reviewer comments",
    "confidential figure",
    "grant draft",
    "application-private",
    "CHATGPT_INSTRUCTIONS.md",
    "METADATA_VERIFICATION_INSTRUCTIONS.md",
    "RETURN_ZIP_REQUIREMENTS.md",
    "PUBLIC_FULL_TEXT_NOTE_TEMPLATE.md",
)
SUPPLEMENTARY_CLAIM_PATTERNS = (
    r"\bsupplementary (?:material|materials|data|figures?) (?:was|were)?\s*(?:reviewed|analyzed|analysed|read)\b",
    r"\bwe reviewed (?:the )?supplement(?:ary|al)?\b",
)
RAW_SOURCE_DUMP_PATTERNS = (
    r"\braw full text dump\b",
    r"\bcopied long source text\b",
)
SAFE_FILENAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*\.md$")


@dataclass
class CommandResult:
    label: str
    returncode: int
    output: str


@dataclass
class CandidateNote:
    archive_path: str
    filename: str
    destination: Path
    text: str
    metadata_verification: str = ""
    effective_mode: str = ""
    existing_destination: bool = False
    existing_note_depth: str = ""
    merge_candidate_path: Path | None = None
    copied: bool = False
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.errors


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


def resolve_input_path(input_path: Path) -> Path:
    requested = input_path.expanduser()
    if requested.exists():
        return requested

    if requested.suffix.lower() == ".md":
        raise ValueError(f"--input Markdown file not found: {safe_display_path(requested)}")

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


def input_type(input_path: Path) -> str:
    if input_path.is_dir():
        return "folder"
    if input_path.is_file() and input_path.suffix.lower() == ".md":
        return "single Markdown file"
    if zipfile.is_zipfile(input_path):
        return "ZIP file"
    return "unsupported file"


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

    if input_path.is_file() and input_path.suffix.lower() == ".md":
        return {input_path.name: input_path.read_text(encoding="utf-8")}, unexpected

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

    raise ValueError(f"--input must be a ZIP file, folder, or Markdown file: {safe_display_path(input_path)}")


def has_required_metadata(text: str, key: str, value: str) -> bool:
    pattern = rf"(?m)^\s*{re.escape(key)}\s*:\s*['\"]?{re.escape(value)}['\"]?\s*$"
    return re.search(pattern, text) is not None


def frontmatter_scalar(text: str, key: str) -> str:
    pattern = rf"(?m)^\s*{re.escape(key)}\s*:\s*['\"]?([^'\"\n#]+?)['\"]?\s*$"
    match = re.search(pattern, text)
    return match.group(1).strip() if match else ""


def filename_errors(filename: str, archive_path: str) -> list[str]:
    errors: list[str] = []
    path = Path(archive_path)
    if path.name != archive_path:
        errors.append("Markdown note must be at ZIP/folder top level")
    if filename.lower() == "readme.md":
        errors.append("README files are not allowed")
    if not filename.endswith(".md"):
        errors.append("filename must end in .md")
    if not SAFE_FILENAME_PATTERN.match(filename):
        errors.append("filename must be English-only and filesystem-safe")
    if filename.startswith(".") or ".." in Path(filename).parts:
        errors.append("filename must not be hidden or contain '..'")
    return errors


def destination_for_filename(filename: str, papers_dir: Path) -> Path:
    destination = papers_dir / filename
    validate_destination_path(destination, papers_dir)
    return destination


def validate_destination_path(path: Path, papers_dir: Path) -> None:
    if path.is_absolute():
        raise ValueError(f"Destination path must be relative: {path}")
    if path.suffix != ".md":
        raise ValueError(f"Destination path must be Markdown: {path}")
    if ".." in path.parts:
        raise ValueError(f"Destination path must not contain '..': {path}")
    if not path.parts or path.parts[0] != papers_dir.parts[0]:
        raise ValueError(f"Destination path must be under {papers_dir.as_posix()}/: {path}")


def unsafe_markers(text: str) -> list[str]:
    markers = [marker for marker in UNSAFE_SUBSTRINGS if marker in text]
    for pattern in SUPPLEMENTARY_CLAIM_PATTERNS + RAW_SOURCE_DUMP_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE):
            markers.append(pattern)
    return markers


def existing_note_depth(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        return frontmatter_scalar(path.read_text(encoding="utf-8"), "note_depth") or "unknown"
    except UnicodeDecodeError:
        return "unknown"


def choose_effective_mode(requested_mode: str, destination_path: Path) -> tuple[str, str]:
    exists = destination_path.exists()
    if requested_mode != "auto":
        return requested_mode, existing_note_depth(destination_path) if requested_mode == "merge" and exists else ""
    if not exists:
        return "new", ""
    depth = existing_note_depth(destination_path)
    if depth == "abstract_metadata_only":
        return "replace", depth
    return "merge", depth or "unknown"


def validate_candidate(candidate: CandidateNote, repo_root: Path, papers_dir: Path) -> None:
    candidate.errors.extend(filename_errors(candidate.filename, candidate.archive_path))
    try:
        validate_destination_path(candidate.destination, papers_dir)
    except ValueError as error:
        candidate.errors.append(str(error))

    for key, value in REQUIRED_METADATA.items():
        if not has_required_metadata(candidate.text, key, value):
            candidate.errors.append(f"missing required metadata {key}: {value}")

    metadata_verification = frontmatter_scalar(candidate.text, "metadata_verification")
    candidate.metadata_verification = metadata_verification
    if not metadata_verification:
        candidate.errors.append("missing required metadata metadata_verification")
    elif metadata_verification not in ALLOWED_METADATA_VERIFICATION:
        candidate.errors.append(f"invalid metadata_verification: {metadata_verification}")

    markers = unsafe_markers(candidate.text)
    if markers:
        candidate.errors.append("unsafe marker(s): " + ", ".join(markers))

    destination_path = repo_root / candidate.destination
    candidate.existing_destination = destination_path.exists()
    candidate.effective_mode, depth = choose_effective_mode(candidate.effective_mode, destination_path)
    candidate.existing_note_depth = depth

    if candidate.effective_mode == "new" and candidate.existing_destination:
        candidate.errors.append(f"destination already exists: {candidate.destination.as_posix()}")
    elif candidate.effective_mode == "replace" and candidate.existing_destination:
        candidate.warnings.append("existing destination will be replaced only if --apply is used")
    elif candidate.effective_mode == "replace":
        candidate.warnings.append("destination does not exist; replace mode is effectively new")
    elif candidate.effective_mode == "merge" and candidate.existing_destination:
        candidate.warnings.append("merge mode does not write into Papers/; review merged candidate under exports/")
    elif candidate.effective_mode == "merge":
        candidate.warnings.append("destination does not exist; merge mode is effectively new")


def build_candidates(
    input_files: dict[str, str],
    repo_root: Path,
    papers_dir: Path,
    mode: str,
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
        if filename.lower() == "readme.md":
            unexpected.append(archive_path)
        try:
            destination = destination_for_filename(filename, papers_dir)
        except ValueError:
            destination = papers_dir / filename
        candidate = CandidateNote(
            archive_path=archive_path,
            filename=filename,
            destination=destination,
            text=text,
            effective_mode=mode,
        )
        validate_candidate(candidate, repo_root, papers_dir)
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


def run_review_commands(repo_root: Path) -> list[CommandResult]:
    results = [
        run_command(repo_root, "git status --short", ["git", "status", "--short"]),
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


def command_checks_pass(command_results: list[CommandResult]) -> bool:
    return all(result.returncode == 0 for result in command_results if not result.label.startswith("git status"))


def copy_candidates(candidates: list[CandidateNote], repo_root: Path) -> list[str]:
    copied: list[str] = []
    for candidate in candidates:
        if not candidate.valid:
            continue
        if candidate.metadata_verification == "conflict_needs_human_check":
            continue
        if candidate.effective_mode == "merge" and candidate.existing_destination:
            continue
        destination = repo_root / candidate.destination
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(candidate.text, encoding="utf-8")
        candidate.copied = True
        copied.append(candidate.destination.as_posix())
    return copied


def merge_candidate_text(candidate: CandidateNote, existing_text: str, max_existing_chars: int = 20000) -> str:
    excerpt = existing_text
    truncated = False
    if len(existing_text) > max_existing_chars:
        excerpt = existing_text[:max_existing_chars].rstrip()
        truncated = True
    truncation_note = "\n\n[Existing note content truncated for review packet size.]\n" if truncated else ""
    return (
        "<!-- MERGE CANDIDATE ONLY: human review required before saving to Papers/. -->\n\n"
        + candidate.text.rstrip()
        + "\n\n# Prior Note Content To Review\n\n"
        + excerpt.rstrip()
        + truncation_note
        + "\n"
    )


def create_merge_candidates(candidates: list[CandidateNote], repo_root: Path, review_dir: Path) -> list[str]:
    generated: list[str] = []
    for candidate in candidates:
        if not candidate.valid:
            continue
        if candidate.effective_mode != "merge" or not candidate.existing_destination:
            continue
        destination_path = repo_root / candidate.destination
        existing_text = destination_path.read_text(encoding="utf-8")
        merge_path = review_dir / f"MERGED_CANDIDATE_{candidate.filename}"
        merge_path.write_text(merge_candidate_text(candidate, existing_text), encoding="utf-8")
        candidate.merge_candidate_path = merge_path
        generated.append(merge_path.relative_to(repo_root).as_posix() if merge_path.is_relative_to(repo_root) else merge_path.name)
    return generated


def expected_status_entries(candidates: list[CandidateNote], copied: list[str]) -> list[str]:
    entries: list[str] = []
    for candidate in candidates:
        if candidate.destination.as_posix() not in copied:
            continue
        prefix = "M " if candidate.existing_destination else "??"
        entries.append(f"{prefix} {candidate.destination.as_posix()}")
    return entries


def decision_from_metadata(candidates: list[CandidateNote]) -> str:
    statuses = {candidate.metadata_verification for candidate in candidates if candidate.valid}
    if "conflict_needs_human_check" in statuses:
        return "BLOCK APPLY UNTIL HUMAN REVIEW"
    if "needs_human_check" in statuses:
        return "INVESTIGATE"
    if "pdf_only_not_externally_checked" in statuses:
        return "REVIEW REQUIRED"
    return "APPROVE CANDIDATE"


def decide(candidates: list[CandidateNote], unexpected: list[str], command_results: list[CommandResult]) -> str:
    if not candidates:
        return "INVESTIGATE"
    if unexpected:
        return "BLOCK"
    if any("unsafe marker" in error or "Destination path" in error for candidate in candidates for error in candidate.errors):
        return "BLOCK"
    if any(not candidate.valid for candidate in candidates):
        return "INVESTIGATE"
    metadata_decision = decision_from_metadata(candidates)
    if metadata_decision != "APPROVE CANDIDATE":
        return metadata_decision
    if not command_checks_pass(command_results):
        return "INVESTIGATE"
    return "APPROVE CANDIDATE"


def fenced(text: str) -> str:
    return "```text\n" + (text.rstrip() or "OK") + "\n```"


def render_review_packet(
    args: argparse.Namespace,
    resolved_input: Path,
    candidates: list[CandidateNote],
    unexpected: list[str],
    copied: list[str],
    merge_candidates: list[str],
    command_results: list[CommandResult],
    decision: str,
) -> str:
    expected_paths = [candidate.destination.as_posix() for candidate in candidates]
    candidate_lines = [
        (
            f"- `{candidate.archive_path}` -> `{candidate.destination.as_posix()}`; "
            f"mode: `{candidate.effective_mode}`; metadata_verification: `{candidate.metadata_verification or 'missing'}`"
        )
        for candidate in candidates
    ]
    conflict_lines = [
        f"- `{candidate.destination.as_posix()}` exists; mode: `{candidate.effective_mode}`; prior note_depth: `{candidate.existing_note_depth or 'not read'}`"
        for candidate in candidates
        if candidate.existing_destination
    ]
    error_lines = [
        f"- `{candidate.archive_path}`: {'; '.join(candidate.errors)}"
        for candidate in candidates
        if candidate.errors
    ]
    warning_lines = [
        f"- `{candidate.archive_path}`: {'; '.join(candidate.warnings)}"
        for candidate in candidates
        if candidate.warnings
    ]
    not_copied = [
        candidate.destination.as_posix()
        for candidate in candidates
        if candidate.valid and not candidate.copied
    ]
    next_commands: list[str] = []
    if decision in {"APPROVE CANDIDATE", "REVIEW REQUIRED"} and not args.apply:
        next_commands = [
            f"python3 scripts/review_imported_full_text_notes.py --input <generated-note-zip-folder-or-md> --mode {args.mode} --apply",
        ]
    elif copied:
        next_commands = [
            "git status --short",
            "git diff --check",
            "PYTHONDONTWRITEBYTECODE=1 python3 Scripts/run_safety_check.py",
            "git add <reviewed Papers/*.md files only>",
            'git commit -m "Add public full-text paper notes"',
            "git push origin main",
        ]

    sections = [
        "# Full-Text Note Import Review Packet",
        "",
        f"- supplied input path: {safe_display_path(args.input)}",
        f"- resolved input path: {safe_display_path(resolved_input)}",
        f"- input type: {input_type(resolved_input)}",
        f"- mode: {args.mode}",
        f"- apply used: {args.apply}",
        f"- suggested decision: {decision}",
        "",
        "## Expected / Candidate Note Files",
        "\n".join(candidate_lines) or "- none",
        "",
        "## Destination Paths",
        "\n".join(f"- `{path}`" for path in expected_paths) or "- none",
        "",
        "## Existing Destination Conflicts",
        "\n".join(conflict_lines) or "- none",
        "",
        "## Metadata Verification Status",
        "\n".join(
            f"- `{candidate.filename}`: `{candidate.metadata_verification or 'missing'}`"
            for candidate in candidates
        )
        or "- none",
        "",
        "## Validation Errors",
        "\n".join(error_lines) or "- none",
        "",
        "## Validation Warnings",
        "\n".join(warning_lines) or "- none",
        "",
        "## Unsafe Marker Scan Result",
        "- PASS" if not any("unsafe marker" in error for candidate in candidates for error in candidate.errors) else "- BLOCK: unsafe marker found",
        "",
        "## Rejected or Unexpected Files",
        "\n".join(f"- `{path}`" for path in unexpected) or "- none",
        "",
        "## Files Copied",
        "\n".join(f"- `{path}`" for path in copied) or "- none",
        "",
        "## Files Not Copied",
        "\n".join(f"- `{path}`" for path in not_copied) or "- none",
        "",
        "## Generated Merge Candidate Paths",
        "\n".join(f"- `{path}`" for path in merge_candidates) or "- none",
        "",
        "## Expected git status --short After Apply",
        "\n".join(f"- `{line}`" for line in expected_status_entries(candidates, copied)) or "- none",
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
            "## Human-Controlled Next Commands",
            "\n".join(f"- `{command}`" for command in next_commands) or "- none",
            "",
        ]
    )
    return "\n".join(sections)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate and optionally apply ChatGPT-generated public full-text paper notes.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--mode", choices=["new", "replace", "merge", "auto"], default="auto")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--reveal-in-finder", action="store_true")
    parser.add_argument("--review-root", type=Path, default=DEFAULT_REVIEW_ROOT)
    parser.add_argument("--papers-dir", type=Path, default=DEFAULT_PAPERS_DIR)
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
    papers_dir = args.papers_dir
    if papers_dir.is_absolute() or ".." in papers_dir.parts:
        print("Error: --papers-dir must be a relative path without '..'.")
        return 1

    try:
        resolved_input = resolve_input_path(args.input)
        input_files, unexpected_files = read_input_files(resolved_input)
    except (OSError, ValueError, zipfile.BadZipFile) as error:
        print(f"Error: {error}")
        return 1

    candidates, unexpected_notes = build_candidates(input_files, repo_root, papers_dir, args.mode)
    unexpected = unexpected_files + unexpected_notes

    timestamp = args.timestamp or timestamp_for_paths()
    review_dir = repo_root / args.review_root / timestamp
    review_dir.mkdir(parents=True, exist_ok=True)

    merge_candidates = create_merge_candidates(candidates, repo_root, review_dir)
    copied: list[str] = []
    if args.apply:
        copied = copy_candidates(candidates, repo_root)

    command_results = run_review_commands(repo_root)
    decision = decide(candidates, unexpected, command_results)
    review_packet = review_dir / "FULL_TEXT_NOTE_IMPORT_REVIEW_PACKET.md"
    review_packet.write_text(
        render_review_packet(
            args,
            resolved_input,
            candidates,
            unexpected,
            copied,
            merge_candidates,
            command_results,
            decision,
        ),
        encoding="utf-8",
    )

    print(f"Review packet: {review_packet}")
    print(f"Resolved input: {safe_display_path(resolved_input)}")
    print(f"Candidate notes: {len(candidates)}")
    print(f"Unexpected/rejected files: {len(unexpected)}")
    print(f"Files copied: {len(copied)}")
    print(f"Merge candidates generated: {len(merge_candidates)}")
    print(f"Suggested decision: {decision}")
    if args.reveal_in_finder:
        reveal_in_finder(review_packet)
    validation_passed = bool(candidates) and not unexpected and all(candidate.valid for candidate in candidates)
    return 0 if validation_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
