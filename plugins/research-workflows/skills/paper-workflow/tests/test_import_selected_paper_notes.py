from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_import_module():
    script_path = REPO_ROOT / "scripts" / "review_selected_notes.py"
    spec = importlib.util.spec_from_file_location("import_selected_paper_notes_for_tests", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def abstract_note_text() -> str:
    return """---
title: Synthetic Abstract Note
note_depth: abstract_metadata_only
security_tier: public
read_depth: abstract_metadata_only
source_provenance:
  - public abstract metadata
human_review_status: approved_for_import
---

# Synthetic Abstract Note

This synthetic note is based on public abstract and metadata information only.
"""


def public_full_text_note_text() -> str:
    return """---
title: Synthetic Full Text Note
note_depth: public_full_text_reviewed
security_tier: public
read_depth: public_full_text_reviewed
source_provenance:
  - public_full_text: PubMed Central synthetic fixture
human_review_status: approved_for_import
---

# Synthetic Full Text Note

This synthetic note represents a public full-text-reviewed upgrade.
"""


def selection_text(
    source: str = "generated_notes/Synthetic_2026.md",
    target: str = "Papers/Synthetic_2026.md",
    action: str = "new",
    depth: str = "abstract_metadata_only",
    review: str = "approved_for_import",
) -> str:
    return f"""notes:
  - id: synthetic_note
    source_note_path: {source}
    target_path: {target}
    import_action: {action}
    expected_note_depth: {depth}
    expected_security_tier: public
    human_review_status: {review}
"""


def make_export(tmp_path: Path, note_text: str = "") -> tuple[Path, Path, Path]:
    repo_root = tmp_path / "repo"
    source_root = repo_root / "exports" / "example_workflow" / "example_run"
    generated_notes = source_root / "generated_notes"
    generated_notes.mkdir(parents=True)
    (source_root / "selected_notes.yaml").write_text(selection_text(), encoding="utf-8")
    (generated_notes / "Synthetic_2026.md").write_text(note_text or abstract_note_text(), encoding="utf-8")
    return repo_root, source_root, source_root / "selected_notes.yaml"


def packet_path(repo_root: Path, timestamp: str) -> Path:
    return (
        repo_root
        / "exports"
        / "selected_paper_note_import_review"
        / timestamp
        / "SELECTED_PAPER_NOTE_IMPORT_REVIEW_PACKET.md"
    )


def test_dry_run_writes_review_packet_without_importing(tmp_path: Path) -> None:
    importer = load_import_module()
    repo_root, source_root, selection_path = make_export(tmp_path)

    exit_code = importer.main(
        [
            "--source",
            str(source_root),
            "--selection",
            str(selection_path),
            "--repo-root",
            str(repo_root),
            "--timestamp",
            "20260526_120000",
        ]
    )

    review_packet = packet_path(repo_root, "20260526_120000")
    review_text = review_packet.read_text(encoding="utf-8")
    assert exit_code == 0
    assert review_packet.exists()
    assert not (repo_root / "Papers" / "Synthetic_2026.md").exists()
    assert "- apply used: False" in review_text
    assert "- files written: 0" in review_text
    assert "- Git actions performed: none" in review_text
    assert "`synthetic_note`: `generated_notes/Synthetic_2026.md` -> `Papers/Synthetic_2026.md` (new)" in review_text


def test_apply_new_imports_selected_note(tmp_path: Path) -> None:
    importer = load_import_module()
    repo_root, source_root, selection_path = make_export(tmp_path)

    exit_code = importer.main(
        [
            "--source",
            str(source_root),
            "--selection",
            str(selection_path),
            "--repo-root",
            str(repo_root),
            "--apply",
            "--timestamp",
            "20260526_120100",
        ]
    )

    copied_note = repo_root / "Papers" / "Synthetic_2026.md"
    review_text = packet_path(repo_root, "20260526_120100").read_text(encoding="utf-8")
    assert exit_code == 0
    assert copied_note.read_text(encoding="utf-8") == abstract_note_text()
    assert "- apply used: True" in review_text
    assert "- files written: 1" in review_text


def test_skip_action_is_documented_but_not_imported(tmp_path: Path) -> None:
    importer = load_import_module()
    repo_root, source_root, selection_path = make_export(tmp_path)
    selection_path.write_text(selection_text(action="skip", review="needs_review"), encoding="utf-8")

    exit_code = importer.main(
        [
            "--source",
            str(source_root),
            "--selection",
            str(selection_path),
            "--repo-root",
            str(repo_root),
            "--apply",
            "--timestamp",
            "20260526_120200",
        ]
    )

    review_text = packet_path(repo_root, "20260526_120200").read_text(encoding="utf-8")
    assert exit_code == 0
    assert not (repo_root / "Papers" / "Synthetic_2026.md").exists()
    assert "`synthetic_note`: `generated_notes/Synthetic_2026.md` (skip)" in review_text


def test_source_path_traversal_is_rejected(tmp_path: Path) -> None:
    importer = load_import_module()
    repo_root, source_root, selection_path = make_export(tmp_path)
    selection_path.write_text(selection_text(source="../Synthetic_2026.md"), encoding="utf-8")

    exit_code = importer.main(
        [
            "--source",
            str(source_root),
            "--selection",
            str(selection_path),
            "--repo-root",
            str(repo_root),
            "--timestamp",
            "20260526_120300",
        ]
    )

    review_text = packet_path(repo_root, "20260526_120300").read_text(encoding="utf-8")
    assert exit_code == 1
    assert "source_note_path must be a relative path without '..'" in review_text


def test_target_outside_papers_is_rejected(tmp_path: Path) -> None:
    importer = load_import_module()
    repo_root, source_root, selection_path = make_export(tmp_path)
    selection_path.write_text(selection_text(target="Notes/Synthetic_2026.md"), encoding="utf-8")

    exit_code = importer.main(
        [
            "--source",
            str(source_root),
            "--selection",
            str(selection_path),
            "--repo-root",
            str(repo_root),
            "--timestamp",
            "20260526_120400",
        ]
    )

    review_text = packet_path(repo_root, "20260526_120400").read_text(encoding="utf-8")
    assert exit_code == 1
    assert "target_path must be under Papers/" in review_text


def test_unsafe_selection_marker_is_rejected(tmp_path: Path) -> None:
    importer = load_import_module()
    repo_root, source_root, selection_path = make_export(tmp_path)
    selection_path.write_text(selection_text() + "source_url: https://example.test\n", encoding="utf-8")

    exit_code = importer.main(
        [
            "--source",
            str(source_root),
            "--selection",
            str(selection_path),
            "--repo-root",
            str(repo_root),
            "--timestamp",
            "20260526_120500",
        ]
    )

    review_text = packet_path(repo_root, "20260526_120500").read_text(encoding="utf-8")
    assert exit_code == 1
    assert "selected_notes.yaml contains unsafe marker" in review_text
    assert "source URL metadata" in review_text


def test_unsafe_source_note_marker_is_rejected(tmp_path: Path) -> None:
    importer = load_import_module()
    repo_root, source_root, selection_path = make_export(
        tmp_path,
        abstract_note_text() + "\nlocal copy: file:" + "//synthetic/private.pdf\n",
    )

    exit_code = importer.main(
        [
            "--source",
            str(source_root),
            "--selection",
            str(selection_path),
            "--repo-root",
            str(repo_root),
            "--timestamp",
            "20260526_120600",
        ]
    )

    review_text = packet_path(repo_root, "20260526_120600").read_text(encoding="utf-8")
    assert exit_code == 1
    assert "source note contains unsafe marker" in review_text
    assert "local file URL" in review_text


def test_abstract_note_cannot_claim_full_text_review(tmp_path: Path) -> None:
    importer = load_import_module()
    invalid_note = abstract_note_text().replace(
        "read_depth: abstract_metadata_only",
        "read_depth: public_full_text_reviewed",
    )
    repo_root, source_root, selection_path = make_export(tmp_path, invalid_note)

    exit_code = importer.main(
        [
            "--source",
            str(source_root),
            "--selection",
            str(selection_path),
            "--repo-root",
            str(repo_root),
            "--timestamp",
            "20260526_120700",
        ]
    )

    review_text = packet_path(repo_root, "20260526_120700").read_text(encoding="utf-8")
    assert exit_code == 1
    assert "abstract_metadata_only drafts must not claim full-text review" in review_text


def test_new_action_does_not_overwrite_existing_target(tmp_path: Path) -> None:
    importer = load_import_module()
    repo_root, source_root, selection_path = make_export(tmp_path)
    target = repo_root / "Papers" / "Synthetic_2026.md"
    target.parent.mkdir()
    target.write_text(abstract_note_text(), encoding="utf-8")

    exit_code = importer.main(
        [
            "--source",
            str(source_root),
            "--selection",
            str(selection_path),
            "--repo-root",
            str(repo_root),
            "--apply",
            "--timestamp",
            "20260526_120800",
        ]
    )

    review_text = packet_path(repo_root, "20260526_120800").read_text(encoding="utf-8")
    assert exit_code == 1
    assert "new import would overwrite an existing target" in review_text
    assert target.read_text(encoding="utf-8") == abstract_note_text()


def test_replace_abstract_only_allows_public_full_text_upgrade(tmp_path: Path) -> None:
    importer = load_import_module()
    repo_root, source_root, selection_path = make_export(tmp_path, public_full_text_note_text())
    selection_path.write_text(
        selection_text(action="replace_abstract_only", depth="public_full_text_reviewed"),
        encoding="utf-8",
    )
    target = repo_root / "Papers" / "Synthetic_2026.md"
    target.parent.mkdir()
    target.write_text(abstract_note_text(), encoding="utf-8")

    exit_code = importer.main(
        [
            "--source",
            str(source_root),
            "--selection",
            str(selection_path),
            "--repo-root",
            str(repo_root),
            "--apply",
            "--timestamp",
            "20260526_120900",
        ]
    )

    assert exit_code == 0
    assert target.read_text(encoding="utf-8") == public_full_text_note_text()


def test_restricted_security_tier_is_rejected(tmp_path: Path) -> None:
    importer = load_import_module()
    restricted_note = abstract_note_text().replace("security_tier: public", "security_tier: internal")
    repo_root, source_root, selection_path = make_export(tmp_path, restricted_note)
    selection_path.write_text(
        selection_text().replace("expected_security_tier: public", "expected_security_tier: internal"),
        encoding="utf-8",
    )

    exit_code = importer.main(
        [
            "--source",
            str(source_root),
            "--selection",
            str(selection_path),
            "--repo-root",
            str(repo_root),
            "--timestamp",
            "20260526_121000",
        ]
    )

    review_text = packet_path(repo_root, "20260526_121000").read_text(encoding="utf-8")
    assert exit_code == 1
    assert "security_tier must be public" in review_text
