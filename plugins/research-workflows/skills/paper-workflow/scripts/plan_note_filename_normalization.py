#!/usr/bin/env python3
"""Plan and optionally apply conservative one-time paper filename normalization."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


EXPORT_ROOT = Path("exports/paper_filename_normalization")
PAPERS_DIR = Path("Papers")
EXCLUDED_FILENAMES = {"README_generated_notes.md"}
METADATA_KEYS = {
    "first_author",
    "authors",
    "journal",
    "year",
    "doi",
    "pmid",
    "title",
    "note_depth",
    "source",
    "source_mode",
}
JOURNAL_ABBREVIATIONS = {
    "nature communications": "NatCommun",
    "nat commun": "NatCommun",
    "cell": "Cell",
    "science": "Science",
    "nature": "Nature",
    "pnas": "PNAS",
    "proceedings of the national academy of sciences": "PNAS",
    "journal of virology": "JVirol",
    "j virol": "JVirol",
    "elife": "eLife",
    "plos pathogens": "PLoSPathog",
    "plos pathog": "PLoSPathog",
    "molecular cell": "MolCell",
    "embo journal": "EMBOJ",
    "embo reports": "EMBORep",
}
REFERENCE_FILES = (
    Path("Indexes/PAPER_SOURCE_MAP.yaml"),
    Path("Papers/README_generated_notes.md"),
    Path("CURRENT_STATUS.md"),
    Path("NEXT_ACTIONS.md"),
)
FALLBACK_JOURNAL_STOPWORDS = {"a", "an", "and", "for", "in", "of", "on", "the", "to", "with"}


@dataclass
class Candidate:
    source_path: Path
    rel_path: Path
    metadata: dict[str, Any]
    frontmatter_sha256: str
    stat_size: int
    stat_mtime_ns: int
    first_author: str = ""
    journal: str = ""
    journal_abbrev: str = ""
    journal_abbrev_source: str = ""
    year: str = ""
    base_target_name: str = ""
    target_name: str = ""
    action: str = "skip"
    reason: str = ""
    collision_status: str = "none"
    references: list[dict[str, Any]] = field(default_factory=list)

    @property
    def target_path(self) -> Path:
        return PAPERS_DIR / self.target_name if self.target_name else Path("")


def timestamp_for_paths() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def run_git(repo_root: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo_root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def is_git_repo(repo_root: Path) -> bool:
    return (repo_root / ".git").exists()


def current_branch(repo_root: Path) -> str:
    if not is_git_repo(repo_root):
        return "(not a git repository)"
    result = run_git(repo_root, ["branch", "--show-current"])
    branch = result.stdout.strip()
    return branch or "(detached or unknown)"


def list_paper_markdown_files(repo_root: Path) -> list[Path]:
    if is_git_repo(repo_root):
        result = run_git(repo_root, ["ls-files", "--", "Papers/*.md"])
        if result.returncode == 0:
            return sorted(
                repo_root / rel_path
                for line in result.stdout.splitlines()
                if line.strip()
                for rel_path in [Path(line)]
                if rel_path.parent == PAPERS_DIR
            )
    papers_dir = repo_root / PAPERS_DIR
    return sorted(papers_dir.glob("*.md")) if papers_dir.exists() else []


def ascii_fold(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return normalized.encode("ascii", "ignore").decode("ascii")


def strip_wrapping_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1].strip()
    return value


def parse_inline_list(value: str) -> list[str]:
    value = value.strip()
    if not (value.startswith("[") and value.endswith("]")):
        return []
    inner = value[1:-1].strip()
    if not inner:
        return []
    return [strip_wrapping_quotes(part.strip()) for part in inner.split(",") if part.strip()]


def parse_metadata_block(text: str) -> tuple[str, dict[str, Any]]:
    if text.startswith("---\n"):
        end = text.find("\n---", 4)
        if end == -1:
            return "", {}
        block = text[4:end]
        return block, parse_simple_yaml(block)

    lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            break
        if stripped.startswith("#"):
            break
        if ":" not in line and not line.startswith((" ", "\t", "-")):
            break
        lines.append(line)
    block = "\n".join(lines)
    return block, parse_simple_yaml(block)


def parse_simple_yaml(block: str) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    current_key: str | None = None
    for raw_line in block.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        if raw_line.startswith((" ", "\t")) and current_key:
            stripped = raw_line.strip()
            if stripped.startswith("- "):
                metadata.setdefault(current_key, [])
                if isinstance(metadata[current_key], list):
                    metadata[current_key].append(strip_wrapping_quotes(stripped[2:]))
            continue
        if ":" not in raw_line:
            current_key = None
            continue
        key, raw_value = raw_line.split(":", 1)
        key = key.strip()
        current_key = key if key in METADATA_KEYS else None
        if key not in METADATA_KEYS:
            continue
        raw_value = raw_value.strip()
        if not raw_value:
            metadata[key] = []
            continue
        inline_list = parse_inline_list(raw_value)
        metadata[key] = inline_list if inline_list else strip_wrapping_quotes(raw_value)
    return metadata


def read_metadata_prefix(path: Path) -> str:
    lines: list[str] = []
    with path.open("r", encoding="utf-8") as handle:
        first_line = handle.readline()
        if not first_line:
            return ""
        lines.append(first_line)
        if first_line == "---\n":
            for line in handle:
                lines.append(line)
                if line.strip() == "---":
                    break
            return "".join(lines)

        for line in handle:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                break
            if ":" not in line and not line.startswith((" ", "\t", "-")):
                break
            lines.append(line)
    return "".join(lines)


def read_candidate(path: Path, repo_root: Path) -> Candidate:
    metadata_prefix = read_metadata_prefix(path)
    block, metadata = parse_metadata_block(metadata_prefix)
    stat = path.stat()
    return Candidate(
        source_path=path,
        rel_path=path.relative_to(repo_root),
        metadata=metadata,
        frontmatter_sha256=hashlib.sha256(block.encode("utf-8")).hexdigest(),
        stat_size=stat.st_size,
        stat_mtime_ns=stat.st_mtime_ns,
    )


def first_string(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        for item in value:
            if isinstance(item, str) and item.strip():
                return item.strip()
    return ""


def surname_from_author(author: str) -> str:
    author = re.sub(r"\bet\s+al\.?\b", "", author, flags=re.IGNORECASE).strip()
    if "," in author:
        return author.split(",", 1)[0].strip()
    pieces = [piece for piece in re.split(r"\s+", author) if piece]
    return pieces[-1] if pieces else ""


def sanitize_author(value: str) -> str:
    value = surname_from_author(value)
    value = ascii_fold(value)
    value = re.sub(r"[^A-Za-z0-9-]+", "", value)
    value = re.sub(r"-{2,}", "-", value).strip("-")
    return value


def sanitize_compact(value: str) -> str:
    value = ascii_fold(value)
    pieces = re.findall(r"[A-Za-z0-9]+", value)
    return "".join(piece[:1].upper() + piece[1:] for piece in pieces)


def sanitize_suffix(value: str, max_words: int = 3) -> str:
    value = ascii_fold(value)
    words = re.findall(r"[A-Za-z0-9]+", value)
    useful = [word for word in words if len(word) > 2 and word.lower() not in FALLBACK_JOURNAL_STOPWORDS]
    return "_".join(word[:1].upper() + word[1:] for word in useful[:max_words])


def normalize_journal_key(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", ascii_fold(value).lower())).strip()


def abbreviate_journal(journal: str) -> tuple[str, str]:
    key = normalize_journal_key(journal)
    if not key:
        return "", "missing"
    if key in JOURNAL_ABBREVIATIONS:
        return JOURNAL_ABBREVIATIONS[key], "explicit_map"
    words = [word for word in key.split() if word not in FALLBACK_JOURNAL_STOPWORDS]
    if not words:
        return "", "ambiguous"
    if len(words) <= 2:
        return "".join(word[:1].upper() + word[1:] for word in words), "fallback_compact_title_words"
    return "".join(word[0].upper() for word in words), "fallback_meaningful_initials"


def extract_year(value: Any) -> str:
    match = re.search(r"\b(18|19|20|21)\d{2}\b", str(value))
    return match.group(0) if match else ""


def doi_suffix(value: str) -> str:
    value = value.strip()
    if not value:
        return ""
    tail = value.rstrip("/").split("/")[-1]
    suffix = sanitize_suffix(tail, max_words=4)
    if suffix:
        return suffix[:40].strip("_")
    compact = re.sub(r"[^A-Za-z0-9]+", "", ascii_fold(tail))
    return compact[:24]


def pmid_suffix(value: str) -> str:
    digits = re.sub(r"\D+", "", value)
    return f"PMID{digits}" if digits else ""


def derive_candidate(candidate: Candidate) -> None:
    if candidate.rel_path.name in EXCLUDED_FILENAMES:
        candidate.action = "skip"
        candidate.reason = "excluded helper file"
        return

    metadata = candidate.metadata
    first_author_value = first_string(metadata.get("first_author")) or first_string(metadata.get("authors"))
    first_author = sanitize_author(first_author_value)
    journal = first_string(metadata.get("journal"))
    journal_abbrev, journal_source = abbreviate_journal(journal)
    year = extract_year(metadata.get("year", ""))

    candidate.first_author = first_author
    candidate.journal = journal
    candidate.journal_abbrev = journal_abbrev
    candidate.journal_abbrev_source = journal_source
    candidate.year = year

    missing = []
    if not first_author:
        missing.append("first_author/authors")
    if not journal_abbrev:
        missing.append("journal")
    if not year:
        missing.append("year")
    if missing:
        candidate.action = "skip"
        candidate.reason = "missing or ambiguous metadata: " + ", ".join(missing)
        return

    candidate.base_target_name = f"{first_author}_{journal_abbrev}_{year}.md"
    candidate.target_name = candidate.base_target_name
    if candidate.rel_path.name == candidate.target_name:
        candidate.action = "already_compliant"
        candidate.reason = "filename already matches derived rule"
    else:
        candidate.action = "rename"
        candidate.reason = "safe metadata-derived rename"


def target_with_suffix(candidate: Candidate, suffix: str) -> str:
    stem = candidate.base_target_name[:-3]
    suffix = re.sub(r"[^A-Za-z0-9_-]+", "", suffix).strip("_-")
    return f"{stem}_{suffix}.md" if suffix else candidate.base_target_name


def resolve_collisions(candidates: list[Candidate]) -> None:
    proposed: dict[str, list[Candidate]] = {}
    for candidate in candidates:
        if candidate.action == "rename":
            proposed.setdefault(candidate.target_name, []).append(candidate)

    for target_name, group in proposed.items():
        if len(group) < 2:
            continue
        for candidate in group:
            candidate.collision_status = f"collision_on:{target_name}"

        used: set[str] = set()
        unresolved: list[Candidate] = []
        for candidate in sorted(group, key=lambda item: item.rel_path.as_posix()):
            suffix = sanitize_suffix(first_string(candidate.metadata.get("title")))
            new_name = target_with_suffix(candidate, suffix)
            if suffix and new_name not in used:
                candidate.target_name = new_name
                candidate.collision_status = "resolved_with_title_suffix"
                candidate.reason = "collision resolved with deterministic title suffix"
                used.add(new_name)
                continue

            suffix = doi_suffix(first_string(candidate.metadata.get("doi")))
            new_name = target_with_suffix(candidate, suffix)
            if suffix and new_name not in used:
                candidate.target_name = new_name
                candidate.collision_status = "resolved_with_doi_suffix"
                candidate.reason = "collision resolved with deterministic DOI suffix"
                used.add(new_name)
                continue

            suffix = pmid_suffix(first_string(candidate.metadata.get("pmid")))
            new_name = target_with_suffix(candidate, suffix)
            if suffix and new_name not in used:
                candidate.target_name = new_name
                candidate.collision_status = "resolved_with_pmid_suffix"
                candidate.reason = "collision resolved with deterministic PMID suffix"
                used.add(new_name)
                continue

            unresolved.append(candidate)

        if unresolved:
            for candidate in unresolved:
                candidate.action = "human_review_required"
                candidate.target_name = ""
                candidate.collision_status = "unresolved_collision"
                candidate.reason = "human_review_required: collision could not be resolved deterministically"


def check_existing_targets(candidates: list[Candidate], repo_root: Path) -> None:
    source_paths = {candidate.rel_path for candidate in candidates}
    for candidate in candidates:
        if candidate.action != "rename":
            continue
        target_rel = candidate.target_path
        if target_rel in source_paths:
            candidate.action = "human_review_required"
            candidate.reason = "target path is another existing paper note; separate duplicate cleanup required"
            candidate.collision_status = "target_exists"
            continue
        if (repo_root / target_rel).exists():
            candidate.action = "human_review_required"
            candidate.reason = "target path already exists; separate duplicate cleanup required"
            candidate.collision_status = "target_exists"


def reference_replacements(candidate: Candidate) -> list[dict[str, str]]:
    if not candidate.target_name:
        return []
    old_path = candidate.rel_path.as_posix()
    new_path = candidate.target_path.as_posix()
    old_filename = candidate.rel_path.name
    new_filename = candidate.target_path.name
    replacements = [{"old": old_path, "new": new_path, "kind": "path"}]
    if old_filename != old_path:
        replacements.append({"old": old_filename, "new": new_filename, "kind": "filename"})
    return replacements


def find_exact_references(candidate: Candidate, repo_root: Path) -> list[dict[str, Any]]:
    replacements = reference_replacements(candidate)
    references: list[dict[str, Any]] = []
    for rel_file in REFERENCE_FILES:
        path = repo_root / rel_file
        if not path.exists() or not path.is_file():
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue
        matched_lines: list[int] = []
        for lineno, line in enumerate(lines, start=1):
            if any(replacement["old"] in line for replacement in replacements):
                matched_lines.append(lineno)
        if matched_lines:
            replacement_counts = [
                {**replacement, "count": sum(line.count(replacement["old"]) for line in lines)}
                for replacement in replacements
            ]
            references.append(
                {
                    "path": rel_file.as_posix(),
                    "line_numbers": matched_lines,
                    "match_type": "exact_path_or_filename",
                    "replacements": replacement_counts,
                    "safe_to_update_automatically": False,
                    "safe_to_update_when_requested": True,
                    "human_review_required": False,
                }
            )
    return references


def build_candidates(repo_root: Path) -> list[Candidate]:
    candidates: list[Candidate] = []
    for path in list_paper_markdown_files(repo_root):
        candidate = read_candidate(path, repo_root)
        derive_candidate(candidate)
        candidates.append(candidate)
    resolve_collisions(candidates)
    check_existing_targets(candidates, repo_root)
    for candidate in candidates:
        if candidate.action == "rename":
            candidate.references = find_exact_references(candidate, repo_root)
    return candidates


def candidate_to_json(candidate: Candidate) -> dict[str, Any]:
    return {
        "old_path": candidate.rel_path.as_posix(),
        "proposed_new_path": candidate.target_path.as_posix() if candidate.target_name else "",
        "action": candidate.action,
        "first_author_used": candidate.first_author,
        "journal_used": candidate.journal,
        "journal_abbreviation_used": candidate.journal_abbrev,
        "journal_abbreviation_source": candidate.journal_abbrev_source,
        "year_used": candidate.year,
        "collision_status": candidate.collision_status,
        "reason": candidate.reason,
        "references": candidate.references,
        "reference_updates_expected": bool(candidate.references),
        "metadata_for_verification": {
            "frontmatter_sha256": candidate.frontmatter_sha256,
            "stat_size": candidate.stat_size,
            "stat_mtime_ns": candidate.stat_mtime_ns,
        },
    }


def counts(entries: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "candidate_paper_notes_scanned": len(entries),
        "already_compliant": sum(1 for entry in entries if entry["action"] == "already_compliant"),
        "proposed_for_rename": sum(1 for entry in entries if entry["action"] == "rename"),
        "skipped": sum(1 for entry in entries if entry["action"] == "skip"),
        "human_review_required": sum(1 for entry in entries if entry["action"] == "human_review_required"),
    }


def markdown_escape(value: Any) -> str:
    text = str(value) if value is not None else ""
    return text.replace("|", "\\|").replace("\n", " ")


def write_plan_files(repo_root: Path, timestamp: str, entries: list[dict[str, Any]]) -> tuple[Path, Path]:
    output_dir = repo_root / EXPORT_ROOT / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)
    branch = current_branch(repo_root)
    summary = counts(entries)
    collisions = [entry for entry in entries if entry["collision_status"] != "none"]
    plan = {
        "schema_version": 1,
        "generated_at": timestamp,
        "repo_root_name": repo_root.name,
        "repo_branch": branch,
        "mode": "plan_only",
        "safety_boundary": {
            "paper_glob": "Papers/*.md",
            "body_text_used_for_filename_derivation": False,
            "pdfs_read": False,
            "bookends_xml_read": False,
            "git_stage_commit_push_performed": False,
        "reference_updates_require_apply_flag": True,
        },
        "summary": summary,
        "collision_summary": {
            "entries_with_collisions": len(collisions),
            "statuses": sorted({entry["collision_status"] for entry in collisions}),
        },
        "entries": entries,
    }

    json_path = output_dir / "paper_filename_rename_plan.json"
    json_path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    md_path = output_dir / "PAPER_FILENAME_RENAME_PLAN.md"
    md_path.write_text(render_markdown_plan(plan), encoding="utf-8")
    return md_path, json_path


def render_markdown_plan(plan: dict[str, Any]) -> str:
    summary = plan["summary"]
    collision_summary = plan["collision_summary"]
    lines = [
        "# Paper Filename Rename Plan",
        "",
        f"- generation timestamp: `{plan['generated_at']}`",
        f"- repo branch: `{plan['repo_branch']}`",
        f"- candidate paper notes scanned: `{summary['candidate_paper_notes_scanned']}`",
        f"- already compliant: `{summary['already_compliant']}`",
        f"- proposed for rename: `{summary['proposed_for_rename']}`",
        f"- skipped: `{summary['skipped']}`",
        f"- human review required: `{summary['human_review_required']}`",
        f"- collision entries: `{collision_summary['entries_with_collisions']}`",
        f"- collision statuses: `{', '.join(collision_summary['statuses']) or 'none'}`",
        "",
        "This is a plan-only review packet. No files were renamed unless `--apply` was used separately.",
        "",
        "Safety boundary: the helper considers tracked Markdown files directly under `Papers/`, reads only filename and top metadata/frontmatter for filename derivation, does not read PDFs or Bookends XML, does not summarize scientific note bodies, and reports reference/index updates instead of editing them.",
        "",
        "ChatGPT review instructions: inspect the proposed old and new paths, skipped reasons, collision statuses, and reported references. Approve an apply step only if each `rename` row is expected.",
        "",
        "After human approval only, run:",
        "",
        "```bash",
        "python3 scripts/plan_note_filename_normalization.py --apply --plan exports/paper_filename_normalization/<timestamp>/paper_filename_rename_plan.json --reveal-in-finder",
        "```",
        "",
        "Add `--update-references` to the apply command only if the exact-string reference replacements listed in this plan are approved. Without that flag, references remain report-only.",
        "",
        "The apply step does not stage, commit, push, pull, fetch, switch branches, create PRs, delete exports, or upload content.",
        "",
        "| old path | proposed new path | action | first author | journal | journal abbrev | year | collision status | reason | reference/index updates expected |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for entry in plan["entries"]:
        lines.append(
            "| "
            + " | ".join(
                markdown_escape(value)
                for value in [
                    entry["old_path"],
                    entry["proposed_new_path"],
                    entry["action"],
                    entry["first_author_used"],
                    entry["journal_used"],
                    entry["journal_abbreviation_used"],
                    entry["year_used"],
                    entry["collision_status"],
                    entry["reason"],
                    "yes" if entry["reference_updates_expected"] else "no",
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def reveal_in_finder(path: Path) -> None:
    if sys.platform != "darwin":
        print("--reveal-in-finder is only available on macOS; skipping.")
        return
    subprocess.run(["open", "-R", str(path)], check=False)


def plan_only(args: argparse.Namespace) -> int:
    repo_root = args.repo_root.expanduser().resolve()
    timestamp = args.timestamp or timestamp_for_paths()
    candidates = build_candidates(repo_root)
    entries = [candidate_to_json(candidate) for candidate in candidates]
    md_path, json_path = write_plan_files(repo_root, timestamp, entries)
    print(f"Wrote Markdown plan: {md_path}")
    print(f"Wrote JSON plan: {json_path}")
    if args.reveal_in_finder:
        reveal_in_finder(md_path)
    return 0


def load_plan(path: Path) -> dict[str, Any]:
    return json.loads(path.expanduser().read_text(encoding="utf-8"))


def verify_clean_worktree(repo_root: Path) -> None:
    if not is_git_repo(repo_root):
        return
    result = run_git(repo_root, ["status", "--short"])
    if result.returncode != 0:
        raise RuntimeError("Could not inspect git status before apply.")
    if result.stdout.strip():
        raise RuntimeError("Refusing to apply because the working tree has existing changes.")


def verify_source_matches_plan(repo_root: Path, entry: dict[str, Any]) -> Path:
    source = repo_root / entry["old_path"]
    if not source.exists():
        raise RuntimeError(f"Planned source file is missing: {entry['old_path']}")
    metadata = entry.get("metadata_for_verification", {})
    stat = source.stat()
    if metadata.get("stat_size") != stat.st_size or metadata.get("stat_mtime_ns") != stat.st_mtime_ns:
        raise RuntimeError(f"Planned source file changed since plan generation: {entry['old_path']}")
    block, _metadata = parse_metadata_block(read_metadata_prefix(source))
    current_frontmatter_hash = hashlib.sha256(block.encode("utf-8")).hexdigest()
    if metadata.get("frontmatter_sha256") != current_frontmatter_hash:
        raise RuntimeError(f"Planned source metadata changed since plan generation: {entry['old_path']}")
    return source


def validate_safe_reference_path(rel_path: Path) -> None:
    if rel_path not in REFERENCE_FILES:
        raise RuntimeError(f"Reference update path is not allowlisted: {rel_path.as_posix()}")


def apply_reference_updates(repo_root: Path, entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Apply exact replacements recorded in the approved plan for allowlisted files."""
    updates_by_file: dict[Path, list[dict[str, str]]] = {}
    for entry in entries:
        for reference in entry.get("references", []):
            rel_path = Path(reference.get("path", ""))
            validate_safe_reference_path(rel_path)
            updates_by_file.setdefault(rel_path, [])
            for replacement in reference.get("replacements", []):
                old = replacement.get("old", "")
                new = replacement.get("new", "")
                if old and new and old != new:
                    updates_by_file[rel_path].append({"old": old, "new": new, "kind": replacement.get("kind", "")})

    applied: list[dict[str, Any]] = []
    for rel_path, replacements in sorted(updates_by_file.items(), key=lambda item: item[0].as_posix()):
        path = repo_root / rel_path
        if not path.exists() or not path.is_file():
            raise RuntimeError(f"Planned reference file is missing: {rel_path.as_posix()}")
        text = path.read_text(encoding="utf-8")
        updated = text
        replacement_counts: list[dict[str, Any]] = []
        for replacement in replacements:
            count = updated.count(replacement["old"])
            if count:
                updated = updated.replace(replacement["old"], replacement["new"])
            replacement_counts.append({**replacement, "count": count})
        if updated != text:
            path.write_text(updated, encoding="utf-8")
            applied.append({"path": rel_path.as_posix(), "replacements": replacement_counts})
    return applied


def apply_plan(args: argparse.Namespace) -> int:
    if args.plan is None:
        print("--apply requires --plan PLAN_JSON", file=sys.stderr)
        return 2
    repo_root = args.repo_root.expanduser().resolve()
    plan = load_plan(args.plan)
    verify_clean_worktree(repo_root)

    rename_entries = [entry for entry in plan.get("entries", []) if entry.get("action") == "rename"]
    moves: list[tuple[Path, Path, dict[str, Any]]] = []
    for entry in rename_entries:
        source = verify_source_matches_plan(repo_root, entry)
        target_rel = Path(entry["proposed_new_path"])
        target = repo_root / target_rel
        if target.exists() and target.resolve() != source.resolve():
            raise RuntimeError(f"Planned target already exists: {target_rel.as_posix()}")
        moves.append((source, target, entry))

    for source, target, _entry in moves:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(target))

    reference_updates = apply_reference_updates(repo_root, rename_entries) if args.update_references else []

    timestamp = args.timestamp or timestamp_for_paths()
    packet = write_apply_packet(repo_root, timestamp, plan, moves, reference_updates, args.update_references)
    print(f"Wrote apply review packet: {packet}")
    print("Next human-controlled commands: review git status/diff, run tests, then stage and commit only if approved.")
    if args.reveal_in_finder:
        reveal_in_finder(packet)
    return 0


def command_output(repo_root: Path, args: list[str]) -> str:
    if not is_git_repo(repo_root):
        return "(not a git repository)"
    result = run_git(repo_root, args)
    output = (result.stdout + result.stderr).strip()
    return output or "(no output)"


def write_apply_packet(
    repo_root: Path,
    timestamp: str,
    plan: dict[str, Any],
    moves: list[tuple[Path, Path, dict[str, Any]]],
    reference_updates: list[dict[str, Any]],
    update_references_requested: bool,
) -> Path:
    output_dir = repo_root / EXPORT_ROOT / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)
    packet = output_dir / "PAPER_FILENAME_APPLY_REVIEW_PACKET.md"
    lines = [
        "# Paper Filename Apply Review Packet",
        "",
        f"- apply timestamp: `{timestamp}`",
        f"- source plan timestamp: `{plan.get('generated_at', '')}`",
        f"- renames applied: `{len(moves)}`",
        f"- reference updates requested: `{update_references_requested}`",
        f"- reference files changed: `{len(reference_updates)}`",
        "- git stage/commit/push performed: `False`",
        "- note body edits performed: `False`",
        f"- reference/index edits performed: `{bool(reference_updates)}`",
        "",
        "| old path | new path |",
        "| --- | --- |",
    ]
    for _source, _target, entry in moves:
        lines.append(f"| {markdown_escape(entry['old_path'])} | {markdown_escape(entry['proposed_new_path'])} |")
    lines.extend(
        [
            "",
            "## Reference Updates",
            "",
        ]
    )
    if reference_updates:
        lines.extend(["| reference file | replacement kind | old string | new string | count |", "| --- | --- | --- | --- | --- |"])
        for update in reference_updates:
            for replacement in update["replacements"]:
                lines.append(
                    "| "
                    + " | ".join(
                        markdown_escape(value)
                        for value in [
                            update["path"],
                            replacement["kind"],
                            replacement["old"],
                            replacement["new"],
                            replacement["count"],
                        ]
                    )
                    + " |"
                )
    elif update_references_requested:
        lines.append("No exact-string reference replacements were found in the approved plan.")
    else:
        lines.append("Reference updates were not requested; listed references remain report-only.")
    lines.extend(
        [
            "",
            "## git status --short",
            "",
            "```text",
            command_output(repo_root, ["status", "--short"]),
            "```",
            "",
            "## git diff --check",
            "",
            "```text",
            command_output(repo_root, ["diff", "--check"]),
            "```",
            "",
            "Next commands remain human-controlled. Review the rename diff, run validation, then stage and commit only the approved files.",
            "",
        ]
    )
    packet.write_text("\n".join(lines), encoding="utf-8")
    return packet


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-only", action="store_true", help="Generate a reviewable rename plan.")
    parser.add_argument("--apply", action="store_true", help="Apply approved rename actions from --plan.")
    parser.add_argument("--plan", type=Path, help="JSON plan path required with --apply.")
    parser.add_argument(
        "--update-references",
        action="store_true",
        help="With --apply, update exact old path/filename references in allowlisted files from the approved plan.",
    )
    parser.add_argument("--repo-root", type=Path, default=Path.cwd(), help="Repository root; useful for tests.")
    parser.add_argument("--timestamp", help="Deterministic timestamp override for tests.")
    parser.add_argument("--reveal-in-finder", action="store_true", help="Reveal generated review packet on macOS.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.apply and args.plan_only:
        parser.error("Use either --plan-only or --apply, not both.")
    try:
        if args.apply:
            return apply_plan(args)
        return plan_only(args)
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
