from __future__ import annotations

import importlib.util
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_import_module():
    script_path = REPO_ROOT / "scripts" / "review_imported_full_text_notes.py"
    spec = importlib.util.spec_from_file_location("import_full_text_paper_notes_for_tests", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def valid_note_text(metadata_verification: str = "verified") -> str:
    return f"""---
title: Zip Full Text Study
authors:
  - Lane, Avery
year: 2026
journal: Journal of Synthetic Full Text
doi: 10.0000/example
pmid:
pmcid:
source: uploaded_public_pdf
note_depth: public_full_text_reviewed
security_tier: public
metadata_verification: {metadata_verification}
metadata_verified_against:
  - DOI
metadata_verification_notes: ""
status: draft
priority: medium
projects: []
tags: []
---

# Citation

Lane A. Zip Full Text Study.

# Figure-by-Figure Summary

Figure 1 is summarized from the visible uploaded public PDF figure.
"""


def write_zip(path: Path, members: dict[str, str]) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for name, text in members.items():
            archive.writestr(name, text)


def test_import_dry_run_validates_pdf_only_note_without_copying(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    importer = load_import_module()
    input_zip = tmp_path / "generated_notes.zip"
    repo_root = tmp_path / "repo"
    write_zip(input_zip, {"Lane_2026_Zip_Full_Text_Study.md": valid_note_text()})
    repo_root.mkdir()
    monkeypatch.setattr(importer, "run_review_commands", lambda repo_root: [])

    exit_code = importer.main(
        [
            "--input",
            str(input_zip),
            "--mode",
            "new",
            "--repo-root",
            str(repo_root),
            "--timestamp",
            "20260518_131000",
        ]
    )

    review_packet = repo_root / "exports" / "full_text_note_import_review" / "20260518_131000" / "FULL_TEXT_NOTE_IMPORT_REVIEW_PACKET.md"
    review_text = review_packet.read_text(encoding="utf-8")
    assert exit_code == 0
    assert "apply used: False" in review_text
    assert "`Papers/Lane_2026_Zip_Full_Text_Study.md`" in review_text
    assert "metadata_verification: `verified`" in review_text
    assert "suggested decision: APPROVE CANDIDATE" in review_text
    assert not (repo_root / "Papers" / "Lane_2026_Zip_Full_Text_Study.md").exists()


def test_import_accepts_single_markdown_file_as_one_note_batch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    importer = load_import_module()
    input_note = tmp_path / "Rivera_NatCommun_2016.md"
    repo_root = tmp_path / "repo"
    input_note.write_text(valid_note_text(), encoding="utf-8")
    repo_root.mkdir()
    monkeypatch.setattr(importer, "run_review_commands", lambda repo_root: [])

    exit_code = importer.main(
        [
            "--input",
            str(input_note),
            "--mode",
            "new",
            "--repo-root",
            str(repo_root),
            "--timestamp",
            "20260518_131050",
        ]
    )

    review_packet = repo_root / "exports" / "full_text_note_import_review" / "20260518_131050" / "FULL_TEXT_NOTE_IMPORT_REVIEW_PACKET.md"
    review_text = review_packet.read_text(encoding="utf-8")
    assert exit_code == 0
    assert "- supplied input path: Rivera_NatCommun_2016.md" in review_text
    assert "- resolved input path: Rivera_NatCommun_2016.md" in review_text
    assert "- input type: single Markdown file" in review_text
    assert "`Rivera_NatCommun_2016.md` -> `Papers/Rivera_NatCommun_2016.md`" in review_text
    assert "apply used: False" in review_text
    assert not (repo_root / "Papers" / "Rivera_NatCommun_2016.md").exists()


def test_import_apply_new_copies_valid_note(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    importer = load_import_module()
    input_folder = tmp_path / "generated_notes"
    repo_root = tmp_path / "repo"
    input_folder.mkdir()
    (input_folder / "Lane_2026_Zip_Full_Text_Study.md").write_text(valid_note_text("partial"), encoding="utf-8")
    repo_root.mkdir()
    monkeypatch.setattr(importer, "run_review_commands", lambda repo_root: [])

    exit_code = importer.main(
        [
            "--input",
            str(input_folder),
            "--mode",
            "new",
            "--apply",
            "--repo-root",
            str(repo_root),
            "--timestamp",
            "20260518_131100",
        ]
    )

    copied_note = repo_root / "Papers" / "Lane_2026_Zip_Full_Text_Study.md"
    assert exit_code == 0
    assert copied_note.exists()
    assert copied_note.read_text(encoding="utf-8") == valid_note_text("partial")


def test_import_apply_copies_valid_single_markdown_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    importer = load_import_module()
    input_note = tmp_path / "Dahmane_NatCommun_2022.md"
    repo_root = tmp_path / "repo"
    input_note.write_text(valid_note_text("partial"), encoding="utf-8")
    repo_root.mkdir()
    monkeypatch.setattr(importer, "run_review_commands", lambda repo_root: [])

    exit_code = importer.main(
        [
            "--input",
            str(input_note),
            "--mode",
            "new",
            "--apply",
            "--repo-root",
            str(repo_root),
            "--timestamp",
            "20260518_131150",
        ]
    )

    copied_note = repo_root / "Papers" / "Dahmane_NatCommun_2022.md"
    assert exit_code == 0
    assert copied_note.exists()
    assert copied_note.read_text(encoding="utf-8") == valid_note_text("partial")


def test_import_uses_auto_extracted_folder_when_zip_path_is_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    importer = load_import_module()
    missing_zip = tmp_path / "generated_notes.zip"
    extracted_folder = tmp_path / "generated_notes"
    repo_root = tmp_path / "repo"
    extracted_folder.mkdir()
    (extracted_folder / "Lane_2026_Zip_Full_Text_Study.md").write_text(valid_note_text(), encoding="utf-8")
    repo_root.mkdir()
    monkeypatch.setattr(importer, "run_review_commands", lambda repo_root: [])

    exit_code = importer.main(
        [
            "--input",
            str(missing_zip),
            "--repo-root",
            str(repo_root),
            "--timestamp",
            "20260518_131200",
        ]
    )

    review_packet = repo_root / "exports" / "full_text_note_import_review" / "20260518_131200" / "FULL_TEXT_NOTE_IMPORT_REVIEW_PACKET.md"
    review_text = review_packet.read_text(encoding="utf-8")
    assert exit_code == 0
    assert "- supplied input path: generated_notes.zip" in review_text
    assert "- resolved input path: generated_notes" in review_text


def test_import_missing_markdown_path_does_not_try_zip_counterpart(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    importer = load_import_module()
    missing_note = tmp_path / "Missing_NatCommun_2026.md"
    zip_counterpart = tmp_path / "Missing_NatCommun_2026.md.zip"
    write_zip(zip_counterpart, {"Missing_NatCommun_2026.md": valid_note_text()})

    exit_code = importer.main(["--input", str(missing_note), "--repo-root", str(tmp_path / "repo")])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "--input Markdown file not found" in captured.out
    assert "ZIP counterpart" not in captured.out


def test_import_rejects_non_markdown_single_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    importer = load_import_module()
    input_file = tmp_path / "generated_notes.txt"
    input_file.write_text(valid_note_text(), encoding="utf-8")

    exit_code = importer.main(["--input", str(input_file), "--repo-root", str(tmp_path / "repo")])

    assert exit_code == 1
    assert "--input must be a ZIP file, folder, or Markdown file" in capsys.readouterr().out


def test_import_auto_replaces_existing_abstract_note_only_with_apply(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    importer = load_import_module()
    input_zip = tmp_path / "generated_notes.zip"
    repo_root = tmp_path / "repo"
    existing = repo_root / "Papers" / "Lane_2026_Zip_Full_Text_Study.md"
    existing.parent.mkdir(parents=True)
    existing.write_text("---\nnote_depth: abstract_metadata_only\n---\n\nOld abstract note.\n", encoding="utf-8")
    write_zip(input_zip, {"Lane_2026_Zip_Full_Text_Study.md": valid_note_text()})
    monkeypatch.setattr(importer, "run_review_commands", lambda repo_root: [])

    exit_code = importer.main(
        [
            "--input",
            str(input_zip),
            "--mode",
            "auto",
            "--apply",
            "--repo-root",
            str(repo_root),
            "--timestamp",
            "20260518_131300",
        ]
    )

    review_packet = repo_root / "exports" / "full_text_note_import_review" / "20260518_131300" / "FULL_TEXT_NOTE_IMPORT_REVIEW_PACKET.md"
    review_text = review_packet.read_text(encoding="utf-8")
    assert exit_code == 0
    assert "mode: `replace`" in review_text
    assert "existing destination will be replaced" in review_text
    assert existing.read_text(encoding="utf-8") == valid_note_text()


def test_import_merge_generates_candidate_without_overwriting(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    importer = load_import_module()
    input_zip = tmp_path / "generated_notes.zip"
    repo_root = tmp_path / "repo"
    existing = repo_root / "Papers" / "Lane_2026_Zip_Full_Text_Study.md"
    existing.parent.mkdir(parents=True)
    existing.write_text("---\nnote_depth: public_full_text_reviewed\n---\n\nPrior reviewed note.\n", encoding="utf-8")
    write_zip(input_zip, {"Lane_2026_Zip_Full_Text_Study.md": valid_note_text()})
    monkeypatch.setattr(importer, "run_review_commands", lambda repo_root: [])

    exit_code = importer.main(
        [
            "--input",
            str(input_zip),
            "--mode",
            "auto",
            "--apply",
            "--repo-root",
            str(repo_root),
            "--timestamp",
            "20260518_131400",
        ]
    )

    review_dir = repo_root / "exports" / "full_text_note_import_review" / "20260518_131400"
    merge_candidate = review_dir / "MERGED_CANDIDATE_Lane_2026_Zip_Full_Text_Study.md"
    assert exit_code == 0
    assert merge_candidate.exists()
    assert "Prior Note Content To Review" in merge_candidate.read_text(encoding="utf-8")
    assert existing.read_text(encoding="utf-8") == "---\nnote_depth: public_full_text_reviewed\n---\n\nPrior reviewed note.\n"


def test_import_rejects_unexpected_files_and_unsafe_markers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    importer = load_import_module()
    input_zip = tmp_path / "generated_notes.zip"
    repo_root = tmp_path / "repo"
    unsafe_note = valid_note_text().replace(
        "Figure 1 is summarized from the visible uploaded public PDF figure.",
        "The supplementary material was reviewed and source_url was used.",
    )
    write_zip(
        input_zip,
        {
            "Lane_2026_Zip_Full_Text_Study.md": unsafe_note,
            "README.md": "extra file",
            "notes.txt": "not markdown",
        },
    )
    repo_root.mkdir()
    monkeypatch.setattr(importer, "run_review_commands", lambda repo_root: [])

    exit_code = importer.main(
        [
            "--input",
            str(input_zip),
            "--mode",
            "new",
            "--repo-root",
            str(repo_root),
            "--timestamp",
            "20260518_131500",
        ]
    )

    review_packet = repo_root / "exports" / "full_text_note_import_review" / "20260518_131500" / "FULL_TEXT_NOTE_IMPORT_REVIEW_PACKET.md"
    review_text = review_packet.read_text(encoding="utf-8")
    assert exit_code == 1
    assert "README.md" in review_text
    assert "notes.txt" in review_text
    assert "unsafe marker" in review_text
    assert "suggested decision: BLOCK" in review_text


def test_import_rejects_empty_input_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    importer = load_import_module()
    input_folder = tmp_path / "generated_notes"
    repo_root = tmp_path / "repo"
    input_folder.mkdir()
    repo_root.mkdir()
    monkeypatch.setattr(importer, "run_review_commands", lambda repo_root: [])

    exit_code = importer.main(
        [
            "--input",
            str(input_folder),
            "--repo-root",
            str(repo_root),
            "--timestamp",
            "20260518_131600",
        ]
    )

    review_packet = repo_root / "exports" / "full_text_note_import_review" / "20260518_131600" / "FULL_TEXT_NOTE_IMPORT_REVIEW_PACKET.md"
    review_text = review_packet.read_text(encoding="utf-8")
    assert exit_code == 1
    assert "Candidate notes: 0" not in review_text
    assert "suggested decision: INVESTIGATE" in review_text


def test_reveal_in_finder_skips_non_macos_without_failing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    importer = load_import_module()
    called = False
    monkeypatch.setattr(importer.sys, "platform", "linux")

    def fake_run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        nonlocal called
        called = True
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(importer.subprocess, "run", fake_run)

    importer.reveal_in_finder(tmp_path / "FULL_TEXT_NOTE_IMPORT_REVIEW_PACKET.md")

    assert not called
    assert "only available on macOS" in capsys.readouterr().out
