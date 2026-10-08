from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_normalizer():
    script_path = REPO_ROOT / "scripts" / "plan_note_filename_normalization.py"
    spec = importlib.util.spec_from_file_location("normalize_paper_filenames_for_tests", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def note_text(
    *,
    title: str = "Synthetic Study",
    first_author: str = "Rivera",
    authors: list[str] | None = None,
    journal: str = "Nature Communications",
    year: str = "2016",
    doi: str = "10.1000/synthetic.1",
    pmid: str = "123456",
    body: str = "Synthetic body that must be preserved exactly.\n",
) -> str:
    author_lines = ""
    if authors:
        author_lines = "authors:\n" + "".join(f"  - {author}\n" for author in authors)
    return f"""---
title: {title}
first_author: {first_author}
{author_lines}journal: {journal}
year: {year}
doi: {doi}
pmid: {pmid}
source: bookends_xml
note_depth: abstract_metadata_only
---

# {title}

{body}"""


def make_repo(tmp_path: Path) -> Path:
    repo_root = tmp_path / "repo"
    (repo_root / "Papers").mkdir(parents=True)
    return repo_root


def plan_paths(repo_root: Path, timestamp: str) -> tuple[Path, Path]:
    output_dir = repo_root / "exports" / "paper_filename_normalization" / timestamp
    return output_dir / "PAPER_FILENAME_RENAME_PLAN.md", output_dir / "paper_filename_rename_plan.json"


def load_plan(repo_root: Path, timestamp: str) -> dict[str, object]:
    _md_path, json_path = plan_paths(repo_root, timestamp)
    return json.loads(json_path.read_text(encoding="utf-8"))


def entry_by_old(plan: dict[str, object], old_path: str) -> dict[str, object]:
    entries = plan["entries"]
    assert isinstance(entries, list)
    for entry in entries:
        assert isinstance(entry, dict)
        if entry["old_path"] == old_path:
            return entry
    raise AssertionError(f"missing plan entry for {old_path}")


def test_plan_derives_expected_short_filenames(tmp_path: Path) -> None:
    normalizer = load_normalizer()
    repo_root = make_repo(tmp_path)
    (repo_root / "Papers" / "Rivera_2016_Long_Title.md").write_text(note_text(), encoding="utf-8")
    (repo_root / "Papers" / "Chen_2015_Cell_Study.md").write_text(
        note_text(title="Cell Study", first_author="Chen", journal="Cell", year="2015"),
        encoding="utf-8",
    )

    exit_code = normalizer.main(["--plan-only", "--repo-root", str(repo_root), "--timestamp", "20260518_120000"])

    plan = load_plan(repo_root, "20260518_120000")
    assert exit_code == 0
    assert entry_by_old(plan, "Papers/Rivera_2016_Long_Title.md")["proposed_new_path"] == "Papers/Rivera_NatCommun_2016.md"
    assert entry_by_old(plan, "Papers/Chen_2015_Cell_Study.md")["proposed_new_path"] == "Papers/Chen_Cell_2015.md"


def test_plan_skips_readme_and_missing_metadata(tmp_path: Path) -> None:
    normalizer = load_normalizer()
    repo_root = make_repo(tmp_path)
    (repo_root / "Papers" / "README_generated_notes.md").write_text("helper file\n", encoding="utf-8")
    (repo_root / "Papers" / "Missing_Metadata.md").write_text(
        "---\ntitle: Missing Metadata\n---\n\nbody should not matter\n",
        encoding="utf-8",
    )

    assert normalizer.main(["--plan-only", "--repo-root", str(repo_root), "--timestamp", "20260518_120100"]) == 0

    plan = load_plan(repo_root, "20260518_120100")
    readme = entry_by_old(plan, "Papers/README_generated_notes.md")
    missing = entry_by_old(plan, "Papers/Missing_Metadata.md")
    assert readme["action"] == "skip"
    assert "excluded helper file" in str(readme["reason"])
    assert missing["action"] == "skip"
    assert "missing or ambiguous metadata" in str(missing["reason"])


def test_plan_detects_already_compliant_filename(tmp_path: Path) -> None:
    normalizer = load_normalizer()
    repo_root = make_repo(tmp_path)
    (repo_root / "Papers" / "Rivera_NatCommun_2016.md").write_text(note_text(), encoding="utf-8")

    assert normalizer.main(["--plan-only", "--repo-root", str(repo_root), "--timestamp", "20260518_120200"]) == 0

    entry = entry_by_old(load_plan(repo_root, "20260518_120200"), "Papers/Rivera_NatCommun_2016.md")
    assert entry["action"] == "already_compliant"
    assert entry["proposed_new_path"] == "Papers/Rivera_NatCommun_2016.md"


def test_plan_resolves_collisions_with_title_then_doi_suffix(tmp_path: Path) -> None:
    normalizer = load_normalizer()
    repo_root = make_repo(tmp_path)
    (repo_root / "Papers" / "Chen_old_a.md").write_text(
        note_text(title="Signal Relay", first_author="Chen", journal="Cell", year="2015"),
        encoding="utf-8",
    )
    (repo_root / "Papers" / "Chen_old_b.md").write_text(
        note_text(title="Signal Relay", first_author="Chen", journal="Cell", year="2015", doi="10.1000/unique-beta"),
        encoding="utf-8",
    )

    assert normalizer.main(["--plan-only", "--repo-root", str(repo_root), "--timestamp", "20260518_120300"]) == 0

    plan = load_plan(repo_root, "20260518_120300")
    first = entry_by_old(plan, "Papers/Chen_old_a.md")
    second = entry_by_old(plan, "Papers/Chen_old_b.md")
    targets = {first["proposed_new_path"], second["proposed_new_path"]}
    assert targets == {"Papers/Chen_Cell_2015_Signal_Relay.md", "Papers/Chen_Cell_2015_Unique_Beta.md"}
    assert first["collision_status"] == "resolved_with_title_suffix"
    assert second["collision_status"] == "resolved_with_doi_suffix"
    assert not any("20260518" in str(target) for target in targets)


def test_plan_generates_markdown_json_and_reference_report(tmp_path: Path) -> None:
    normalizer = load_normalizer()
    repo_root = make_repo(tmp_path)
    (repo_root / "Papers" / "Rivera_old.md").write_text(note_text(), encoding="utf-8")
    (repo_root / "CURRENT_STATUS.md").write_text("See Papers/Rivera_old.md\n", encoding="utf-8")

    assert normalizer.main(["--plan-only", "--repo-root", str(repo_root), "--timestamp", "20260518_120400"]) == 0

    md_path, json_path = plan_paths(repo_root, "20260518_120400")
    plan = json.loads(json_path.read_text(encoding="utf-8"))
    md_text = md_path.read_text(encoding="utf-8")
    entry = entry_by_old(plan, "Papers/Rivera_old.md")
    assert md_path.exists()
    assert json_path.exists()
    assert "Paper Filename Rename Plan" in md_text
    assert "This is a plan-only review packet" in md_text
    assert entry["reference_updates_expected"] is True
    assert entry["references"][0]["path"] == "CURRENT_STATUS.md"
    assert entry["references"][0]["safe_to_update_automatically"] is False
    assert entry["references"][0]["safe_to_update_when_requested"] is True
    assert entry["references"][0]["human_review_required"] is False
    assert entry["references"][0]["replacements"] == [
        {"old": "Papers/Rivera_old.md", "new": "Papers/Rivera_NatCommun_2016.md", "kind": "path", "count": 1},
        {"old": "Rivera_old.md", "new": "Rivera_NatCommun_2016.md", "kind": "filename", "count": 1},
    ]


def test_apply_refuses_without_plan(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    normalizer = load_normalizer()
    repo_root = make_repo(tmp_path)

    exit_code = normalizer.main(["--apply", "--repo-root", str(repo_root)])

    assert exit_code == 2
    assert "--apply requires --plan" in capsys.readouterr().err


def test_apply_refuses_when_source_file_is_missing(tmp_path: Path) -> None:
    normalizer = load_normalizer()
    repo_root = make_repo(tmp_path)
    source = repo_root / "Papers" / "Rivera_old.md"
    source.write_text(note_text(), encoding="utf-8")
    assert normalizer.main(["--plan-only", "--repo-root", str(repo_root), "--timestamp", "20260518_120500"]) == 0
    _md_path, json_path = plan_paths(repo_root, "20260518_120500")
    source.unlink()

    exit_code = normalizer.main(["--apply", "--plan", str(json_path), "--repo-root", str(repo_root), "--timestamp", "20260518_120501"])

    assert exit_code == 1
    assert not (repo_root / "Papers" / "Rivera_NatCommun_2016.md").exists()


def test_apply_renames_only_planned_files_and_preserves_contents(tmp_path: Path) -> None:
    normalizer = load_normalizer()
    repo_root = make_repo(tmp_path)
    original = note_text(body="Line one.\nLine two with punctuation: !@#$%^&*()\n")
    source = repo_root / "Papers" / "Rivera_old.md"
    source.write_text(original, encoding="utf-8")
    skipped = repo_root / "Papers" / "Skipped.md"
    skipped.write_text("---\ntitle: skipped\n---\n\nunchanged\n", encoding="utf-8")
    assert normalizer.main(["--plan-only", "--repo-root", str(repo_root), "--timestamp", "20260518_120600"]) == 0
    _md_path, json_path = plan_paths(repo_root, "20260518_120600")

    exit_code = normalizer.main(["--apply", "--plan", str(json_path), "--repo-root", str(repo_root), "--timestamp", "20260518_120601"])

    target = repo_root / "Papers" / "Rivera_NatCommun_2016.md"
    packet = repo_root / "exports" / "paper_filename_normalization" / "20260518_120601" / "PAPER_FILENAME_APPLY_REVIEW_PACKET.md"
    assert exit_code == 0
    assert not source.exists()
    assert target.read_text(encoding="utf-8") == original
    assert skipped.exists()
    assert "reference/index edits performed: `False`" in packet.read_text(encoding="utf-8")


def test_apply_does_not_update_references_without_flag(tmp_path: Path) -> None:
    normalizer = load_normalizer()
    repo_root = make_repo(tmp_path)
    (repo_root / "Papers" / "Rivera_old.md").write_text(note_text(), encoding="utf-8")
    status = repo_root / "CURRENT_STATUS.md"
    status.write_text("See Papers/Rivera_old.md and Rivera_old.md\n", encoding="utf-8")
    assert normalizer.main(["--plan-only", "--repo-root", str(repo_root), "--timestamp", "20260518_120800"]) == 0
    _md_path, json_path = plan_paths(repo_root, "20260518_120800")

    exit_code = normalizer.main(["--apply", "--plan", str(json_path), "--repo-root", str(repo_root), "--timestamp", "20260518_120801"])

    packet = repo_root / "exports" / "paper_filename_normalization" / "20260518_120801" / "PAPER_FILENAME_APPLY_REVIEW_PACKET.md"
    assert exit_code == 0
    assert status.read_text(encoding="utf-8") == "See Papers/Rivera_old.md and Rivera_old.md\n"
    packet_text = packet.read_text(encoding="utf-8")
    assert "reference updates requested: `False`" in packet_text
    assert "Reference updates were not requested" in packet_text


def test_apply_updates_exact_references_with_flag_and_reports_counts(tmp_path: Path) -> None:
    normalizer = load_normalizer()
    repo_root = make_repo(tmp_path)
    (repo_root / "Papers" / "Rivera_old.md").write_text(note_text(), encoding="utf-8")
    (repo_root / "Indexes").mkdir()
    index = repo_root / "Indexes" / "PAPER_SOURCE_MAP.yaml"
    readme = repo_root / "Papers" / "README_generated_notes.md"
    status = repo_root / "CURRENT_STATUS.md"
    next_actions = repo_root / "NEXT_ACTIONS.md"
    index.write_text("- note: Papers/Rivera_old.md\n", encoding="utf-8")
    readme.write_text("Rivera_old.md\n", encoding="utf-8")
    status.write_text("See Papers/Rivera_old.md and Rivera_old.md\n", encoding="utf-8")
    next_actions.write_text("No matching paper here.\n", encoding="utf-8")
    assert normalizer.main(["--plan-only", "--repo-root", str(repo_root), "--timestamp", "20260518_120900"]) == 0
    _md_path, json_path = plan_paths(repo_root, "20260518_120900")

    exit_code = normalizer.main(
        [
            "--apply",
            "--plan",
            str(json_path),
            "--repo-root",
            str(repo_root),
            "--timestamp",
            "20260518_120901",
            "--update-references",
        ]
    )

    packet = repo_root / "exports" / "paper_filename_normalization" / "20260518_120901" / "PAPER_FILENAME_APPLY_REVIEW_PACKET.md"
    packet_text = packet.read_text(encoding="utf-8")
    assert exit_code == 0
    assert index.read_text(encoding="utf-8") == "- note: Papers/Rivera_NatCommun_2016.md\n"
    assert readme.read_text(encoding="utf-8") == "Rivera_NatCommun_2016.md\n"
    assert status.read_text(encoding="utf-8") == "See Papers/Rivera_NatCommun_2016.md and Rivera_NatCommun_2016.md\n"
    assert next_actions.read_text(encoding="utf-8") == "No matching paper here.\n"
    assert "reference updates requested: `True`" in packet_text
    assert "reference/index edits performed: `True`" in packet_text
    assert "| CURRENT_STATUS.md | path | Papers/Rivera_old.md | Papers/Rivera_NatCommun_2016.md | 1 |" in packet_text
    assert "| CURRENT_STATUS.md | filename | Rivera_old.md | Rivera_NatCommun_2016.md | 1 |" in packet_text
    assert "| Indexes/PAPER_SOURCE_MAP.yaml | path | Papers/Rivera_old.md | Papers/Rivera_NatCommun_2016.md | 1 |" in packet_text
    assert "| Papers/README_generated_notes.md | filename | Rivera_old.md | Rivera_NatCommun_2016.md | 1 |" in packet_text


def test_target_exists_requires_duplicate_cleanup_and_is_not_applied(tmp_path: Path) -> None:
    normalizer = load_normalizer()
    repo_root = make_repo(tmp_path)
    existing = repo_root / "Papers" / "Rivera_NatCommun_2016.md"
    older = repo_root / "Papers" / "Older_Rivera_2016.md"
    existing_text = note_text(title="Existing Note")
    older_text = note_text(title="Older Duplicate Candidate")
    existing.write_text(existing_text, encoding="utf-8")
    older.write_text(older_text, encoding="utf-8")
    assert normalizer.main(["--plan-only", "--repo-root", str(repo_root), "--timestamp", "20260518_121000"]) == 0
    _md_path, json_path = plan_paths(repo_root, "20260518_121000")

    plan = load_plan(repo_root, "20260518_121000")
    older_entry = entry_by_old(plan, "Papers/Older_Rivera_2016.md")
    exit_code = normalizer.main(["--apply", "--plan", str(json_path), "--repo-root", str(repo_root), "--timestamp", "20260518_121001"])

    assert older_entry["action"] == "human_review_required"
    assert older_entry["collision_status"] == "target_exists"
    assert "separate duplicate cleanup required" in str(older_entry["reason"])
    assert exit_code == 0
    assert existing.read_text(encoding="utf-8") == existing_text
    assert older.read_text(encoding="utf-8") == older_text


def test_apply_does_not_run_git_stage_commit_push(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    normalizer = load_normalizer()
    repo_root = make_repo(tmp_path)
    (repo_root / "Papers" / "Rivera_old.md").write_text(note_text(), encoding="utf-8")
    assert normalizer.main(["--plan-only", "--repo-root", str(repo_root), "--timestamp", "20260518_120700"]) == 0
    _md_path, json_path = plan_paths(repo_root, "20260518_120700")
    seen_commands: list[list[str]] = []

    def fake_run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        seen_commands.append(args)
        forbidden = {"add", "commit", "push", "pull", "fetch", "checkout", "switch", "mv"}
        if args and args[0] == "git" and any(part in forbidden for part in args[1:]):
            raise AssertionError(f"forbidden git command: {args}")
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(normalizer.subprocess, "run", fake_run)

    assert normalizer.main(["--apply", "--plan", str(json_path), "--repo-root", str(repo_root), "--timestamp", "20260518_120701"]) == 0
    assert not any(command and command[0] == "git" for command in seen_commands)
