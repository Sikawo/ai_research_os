from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_import_module():
    script_path = REPO_ROOT / "scripts" / "review_imported_generated_notes.py"
    spec = importlib.util.spec_from_file_location("import_generated_paper_notes_for_tests", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def manifest_text() -> str:
    return json.dumps(
        {
            "generated_at": "2026-05-18T12:00:00",
            "source_mode": "bookends_xml",
            "route": "abstract_metadata_only",
            "source_xml_display_name": "synthetic_bookends.xml",
            "expected_prompt_packet_filenames": ["Lane_2026_Zip_Handoff_Study_prompt_packet.md"],
            "expected_target_note_paths": ["Papers/Lane_2026_Zip_Handoff_Study.md"],
            "external_ai_calls": 0,
            "bookends_attachment_modifications": 0,
        }
    )


def valid_note_text() -> str:
    return """---
title: Zip Handoff Study
authors:
  - Lane, Avery
year: 2026
source: bookends_xml
note_depth: abstract_metadata_only
security_tier: public
status: draft
priority: medium
projects: []
tags: []
---

# Zip Handoff Study

This note is based on public abstract and metadata information only.
"""


def write_zip(path: Path, members: dict[str, str]) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for name, text in members.items():
            archive.writestr(name, text)


def test_import_dry_run_validates_expected_note_without_copying(tmp_path: Path) -> None:
    importer = load_import_module()
    manifest_path = tmp_path / "MANIFEST.json"
    input_zip = tmp_path / "generated_notes.zip"
    repo_root = tmp_path / "repo"
    manifest_path.write_text(manifest_text(), encoding="utf-8")
    write_zip(input_zip, {"Lane_2026_Zip_Handoff_Study.md": valid_note_text()})
    repo_root.mkdir()

    exit_code = importer.main(
        [
            "--input",
            str(input_zip),
            "--manifest",
            str(manifest_path),
            "--repo-root",
            str(repo_root),
            "--timestamp",
            "20260518_121500",
        ]
    )

    review_packet = repo_root / "exports" / "paper_note_import_review" / "20260518_121500" / "IMPORT_REVIEW_PACKET.md"
    assert exit_code == 0
    assert review_packet.exists()
    assert not (repo_root / "Papers" / "Lane_2026_Zip_Handoff_Study.md").exists()
    review_text = review_packet.read_text(encoding="utf-8")
    assert "apply used: False" in review_text
    assert "`Papers/Lane_2026_Zip_Handoff_Study.md`" in review_text
    assert "Files Not Copied" in review_text
    assert "Suggested decision" not in review_text


def test_import_uses_auto_extracted_folder_when_zip_path_is_missing(tmp_path: Path) -> None:
    importer = load_import_module()
    manifest_path = tmp_path / "MANIFEST.json"
    missing_input_zip = tmp_path / "generated_notes.zip"
    extracted_folder = tmp_path / "generated_notes"
    repo_root = tmp_path / "repo"
    manifest_path.write_text(manifest_text(), encoding="utf-8")
    extracted_folder.mkdir()
    (extracted_folder / "Lane_2026_Zip_Handoff_Study.md").write_text(valid_note_text(), encoding="utf-8")
    repo_root.mkdir()

    exit_code = importer.main(
        [
            "--input",
            str(missing_input_zip),
            "--manifest",
            str(manifest_path),
            "--repo-root",
            str(repo_root),
            "--timestamp",
            "20260518_121600",
        ]
    )

    review_packet = repo_root / "exports" / "paper_note_import_review" / "20260518_121600" / "IMPORT_REVIEW_PACKET.md"
    review_text = review_packet.read_text(encoding="utf-8")
    assert exit_code == 0
    assert "- input: generated_notes.zip" in review_text
    assert "- resolved input: generated_notes" in review_text


def test_import_uses_zip_counterpart_when_folder_path_is_missing(tmp_path: Path) -> None:
    importer = load_import_module()
    manifest_path = tmp_path / "MANIFEST.json"
    missing_input_folder = tmp_path / "generated_notes"
    input_zip = tmp_path / "generated_notes.zip"
    repo_root = tmp_path / "repo"
    manifest_path.write_text(manifest_text(), encoding="utf-8")
    write_zip(input_zip, {"Lane_2026_Zip_Handoff_Study.md": valid_note_text()})
    repo_root.mkdir()

    exit_code = importer.main(
        [
            "--input",
            str(missing_input_folder),
            "--manifest",
            str(manifest_path),
            "--repo-root",
            str(repo_root),
            "--timestamp",
            "20260518_121700",
        ]
    )

    review_packet = repo_root / "exports" / "paper_note_import_review" / "20260518_121700" / "IMPORT_REVIEW_PACKET.md"
    review_text = review_packet.read_text(encoding="utf-8")
    assert exit_code == 0
    assert "- input: generated_notes" in review_text
    assert "- resolved input: generated_notes.zip" in review_text


def test_import_missing_input_names_requested_path_and_counterpart(tmp_path: Path) -> None:
    importer = load_import_module()

    with pytest.raises(ValueError, match="auto-extracted folder not found") as error:
        importer.resolve_input_path(tmp_path / "generated_notes.zip")

    message = str(error.value)
    assert "generated_notes.zip" in message
    assert "generated_notes" in message


def test_import_apply_copies_only_valid_expected_note(tmp_path: Path) -> None:
    importer = load_import_module()
    manifest_path = tmp_path / "MANIFEST.json"
    input_folder = tmp_path / "generated_notes"
    repo_root = tmp_path / "repo"
    manifest_path.write_text(manifest_text(), encoding="utf-8")
    input_folder.mkdir()
    (input_folder / "Lane_2026_Zip_Handoff_Study.md").write_text(valid_note_text(), encoding="utf-8")
    repo_root.mkdir()

    exit_code = importer.main(
        [
            "--input",
            str(input_folder),
            "--manifest",
            str(manifest_path),
            "--repo-root",
            str(repo_root),
            "--apply",
            "--timestamp",
            "20260518_122000",
        ]
    )

    copied_note = repo_root / "Papers" / "Lane_2026_Zip_Handoff_Study.md"
    assert exit_code == 0
    assert copied_note.exists()
    assert copied_note.read_text(encoding="utf-8") == valid_note_text()


def test_import_reveal_in_finder_runs_open_for_review_packet(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    importer = load_import_module()
    manifest_path = tmp_path / "MANIFEST.json"
    input_zip = tmp_path / "generated_notes.zip"
    repo_root = tmp_path / "repo"
    manifest_path.write_text(manifest_text(), encoding="utf-8")
    write_zip(input_zip, {"Lane_2026_Zip_Handoff_Study.md": valid_note_text()})
    repo_root.mkdir()
    calls: list[list[str]] = []

    monkeypatch.setattr(importer, "run_review_commands", lambda repo_root: [])
    monkeypatch.setattr(importer.sys, "platform", "darwin")

    def fake_run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(importer.subprocess, "run", fake_run)

    exit_code = importer.main(
        [
            "--input",
            str(input_zip),
            "--manifest",
            str(manifest_path),
            "--repo-root",
            str(repo_root),
            "--timestamp",
            "20260518_122100",
            "--reveal-in-finder",
        ]
    )

    review_packet = repo_root / "exports" / "paper_note_import_review" / "20260518_122100" / "IMPORT_REVIEW_PACKET.md"
    assert exit_code == 0
    assert calls == [["open", "-R", str(review_packet)]]


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

    importer.reveal_in_finder(tmp_path / "IMPORT_REVIEW_PACKET.md")

    assert not called
    assert "only available on macOS" in capsys.readouterr().out


def test_import_can_read_manifest_from_original_export_zip(tmp_path: Path) -> None:
    importer = load_import_module()
    export_zip = tmp_path / "paper_ai_packets_for_chatgpt.zip"
    input_zip = tmp_path / "generated_notes.zip"
    repo_root = tmp_path / "repo"
    write_zip(export_zip, {"MANIFEST.json": manifest_text()})
    write_zip(input_zip, {"Lane_2026_Zip_Handoff_Study.md": valid_note_text()})
    repo_root.mkdir()

    exit_code = importer.main(
        [
            "--input",
            str(input_zip),
            "--export-zip",
            str(export_zip),
            "--repo-root",
            str(repo_root),
            "--timestamp",
            "20260518_122200",
        ]
    )

    review_packet = repo_root / "exports" / "paper_note_import_review" / "20260518_122200" / "IMPORT_REVIEW_PACKET.md"
    assert exit_code == 0
    assert "MANIFEST.json" in review_packet.read_text(encoding="utf-8")


def test_import_dry_run_flags_existing_destination_without_reading_note(tmp_path: Path) -> None:
    importer = load_import_module()
    manifest_path = tmp_path / "MANIFEST.json"
    input_zip = tmp_path / "generated_notes.zip"
    repo_root = tmp_path / "repo"
    manifest_path.write_text(manifest_text(), encoding="utf-8")
    write_zip(input_zip, {"Lane_2026_Zip_Handoff_Study.md": valid_note_text()})
    existing_note = repo_root / "Papers" / "Lane_2026_Zip_Handoff_Study.md"
    existing_note.parent.mkdir(parents=True)
    existing_note.write_text("existing private note body should not be inspected\n", encoding="utf-8")

    exit_code = importer.main(
        [
            "--input",
            str(input_zip),
            "--manifest",
            str(manifest_path),
            "--repo-root",
            str(repo_root),
            "--timestamp",
            "20260518_122300",
        ]
    )

    review_packet = repo_root / "exports" / "paper_note_import_review" / "20260518_122300" / "IMPORT_REVIEW_PACKET.md"
    review_text = review_packet.read_text(encoding="utf-8")
    assert exit_code == 1
    assert "destination already exists: Papers/Lane_2026_Zip_Handoff_Study.md" in review_text
    assert "existing private note body" not in review_text


def test_import_rejects_unexpected_files_and_route_violations(tmp_path: Path) -> None:
    importer = load_import_module()
    manifest_path = tmp_path / "MANIFEST.json"
    input_zip = tmp_path / "generated_notes.zip"
    repo_root = tmp_path / "repo"
    manifest_path.write_text(manifest_text(), encoding="utf-8")
    unsafe_note = valid_note_text().replace(
        "This note is based on public abstract and metadata information only.",
        "The full text was reviewed and the source_url was checked.",
    )
    write_zip(
        input_zip,
        {
            "Lane_2026_Zip_Handoff_Study.md": unsafe_note,
            "README.md": "extra file",
            "notes.txt": "not markdown",
        },
    )
    repo_root.mkdir()

    exit_code = importer.main(
        [
            "--input",
            str(input_zip),
            "--manifest",
            str(manifest_path),
            "--repo-root",
            str(repo_root),
            "--timestamp",
            "20260518_122500",
        ]
    )

    review_packet = repo_root / "exports" / "paper_note_import_review" / "20260518_122500" / "IMPORT_REVIEW_PACKET.md"
    review_text = review_packet.read_text(encoding="utf-8")
    assert exit_code == 1
    assert "README.md" in review_text
    assert "notes.txt" in review_text
    assert "unsafe or out-of-route marker" in review_text
    assert "INVESTIGATE" in review_text
