from __future__ import annotations

import importlib.util
import stat
import sys
import zipfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
REQUIRED_FILES = (
    "SEARCH_SUMMARY.md",
    "SCREENING_TABLE.md",
    "DEEP_READING_SELECTION.md",
    "ABSTRACT_REVIEW.md",
    "FULL_TEXT_READING_PLAN.md",
)


def load_import_module():
    script_path = REPO_ROOT / "scripts" / "import_screening_record.py"
    spec = importlib.util.spec_from_file_location("import_pubmed_screening_record_for_tests", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_screening_source(source: Path, text: str = "reviewed abstract-screening record\n") -> None:
    source.mkdir(parents=True)
    for filename in REQUIRED_FILES:
        (source / filename).write_text(f"# {filename}\n\n{text}", encoding="utf-8")


def write_screening_zip(
    archive_path: Path,
    text: str = "reviewed abstract-screening record\n",
    prefix: str = "",
    omit: set[str] | None = None,
    extras: dict[str, str] | None = None,
) -> None:
    prefix = prefix.strip("/")
    base = f"{prefix}/" if prefix else ""
    omit = omit or set()
    extras = extras or {}
    with zipfile.ZipFile(archive_path, "w") as archive:
        for filename in REQUIRED_FILES:
            if filename in omit:
                continue
            archive.writestr(f"{base}{filename}", f"# {filename}\n\n{text}")
        for relative_path, content in extras.items():
            archive.writestr(f"{base}{relative_path}", content)


def destination(repo_root: Path) -> Path:
    return repo_root / "Literature_Searches" / "2026-05-20_AAV6_primary_T_cell_HSPC"


def run_import(importer, repo_root: Path, source: Path, *extra: str) -> int:
    return importer.main(
        [
            "--source",
            str(source),
            "--topic-slug",
            "AAV6_primary_T_cell_HSPC",
            "--date",
            "2026-05-20",
            "--repo-root",
            str(repo_root),
            *extra,
        ]
    )


def test_successful_import_copies_only_required_markdown_and_ignores_unexpected(capsys, tmp_path: Path) -> None:
    importer = load_import_module()
    source = tmp_path / "screening_outputs"
    repo_root = tmp_path / "repo"
    write_screening_source(source)
    (source / "paper_note_drafts").mkdir()
    (source / "paper_note_drafts" / "draft.md").write_text("draft", encoding="utf-8")
    (source / "exports").mkdir()
    (source / "exports" / "artifact.md").write_text("temporary", encoding="utf-8")
    for filename in ["handoff.zip", "results.csv", "payload.json", "records.xml", "paper.pdf", "unexpected.txt"]:
        (source / filename).write_text("ignored", encoding="utf-8")

    exit_code = run_import(importer, repo_root, source, "--apply")

    captured = capsys.readouterr()
    dest = destination(repo_root)
    assert exit_code == 0
    assert sorted(path.name for path in dest.iterdir()) == sorted(REQUIRED_FILES)
    assert not (repo_root / "Papers").exists()
    assert "paper_note_drafts/" in captured.out
    assert "handoff.zip" in captured.out
    assert "unexpected.txt" in captured.out
    assert "Source type: directory" in captured.out
    assert "Safety scan result: PASS" in captured.out
    assert "No Papers/, Bookends files, PDFs, raw data, or external AI APIs were touched." in captured.out


def test_default_mode_is_dry_run_and_does_not_write_files(capsys, tmp_path: Path) -> None:
    importer = load_import_module()
    source = tmp_path / "screening_outputs"
    repo_root = tmp_path / "repo"
    write_screening_source(source)

    exit_code = run_import(importer, repo_root, source)

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Dry run complete" in captured.out
    assert not destination(repo_root).exists()


def test_zip_source_imports_required_markdown_at_zip_root_and_ignores_unexpected(
    capsys, tmp_path: Path
) -> None:
    importer = load_import_module()
    source = tmp_path / "Archive(1).zip"
    repo_root = tmp_path / "repo"
    write_screening_zip(
        source,
        extras={
            "paper_note_drafts/candidate.md": "draft",
            "exports/artifact.md": "temporary",
            "handoff.zip": "ignored",
            "results.csv": "ignored",
            "payload.json": "ignored",
            "records.xml": "ignored",
            "paper.pdf": "ignored",
            "unexpected.txt": "ignored",
        },
    )

    exit_code = run_import(importer, repo_root, source, "--apply")

    captured = capsys.readouterr()
    dest = destination(repo_root)
    assert exit_code == 0
    assert sorted(path.name for path in dest.iterdir()) == sorted(REQUIRED_FILES)
    assert not (repo_root / "Papers").exists()
    assert not (dest / "paper_note_drafts").exists()
    assert "Source type: zip" in captured.out
    assert "paper_note_drafts/" in captured.out
    assert "exports/" in captured.out
    assert "handoff.zip" in captured.out
    assert "results.csv" in captured.out
    assert "payload.json" in captured.out
    assert "records.xml" in captured.out
    assert "paper.pdf" in captured.out
    assert "unexpected.txt" in captured.out


def test_zip_source_imports_required_markdown_inside_one_top_level_folder(
    capsys, tmp_path: Path
) -> None:
    importer = load_import_module()
    source = tmp_path / "Archive.zip"
    repo_root = tmp_path / "repo"
    write_screening_zip(
        source,
        prefix="screening_outputs",
        extras={"paper_note_drafts/candidate.md": "draft", "unexpected.txt": "ignored"},
    )

    exit_code = run_import(importer, repo_root, source, "--apply")

    captured = capsys.readouterr()
    dest = destination(repo_root)
    assert exit_code == 0
    assert sorted(path.name for path in dest.iterdir()) == sorted(REQUIRED_FILES)
    assert "Source type: zip" in captured.out
    assert "screening_outputs/paper_note_drafts/" in captured.out
    assert "screening_outputs/unexpected.txt" in captured.out
    assert "- screening_outputs/" not in captured.out.splitlines()


def test_zip_source_dry_run_does_not_write_files(capsys, tmp_path: Path) -> None:
    importer = load_import_module()
    source = tmp_path / "Archive.zip"
    repo_root = tmp_path / "repo"
    write_screening_zip(source)

    exit_code = run_import(importer, repo_root, source, "--dry-run")

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Dry run complete" in captured.out
    assert "Source type: zip" in captured.out
    assert "Safety scan result: PASS" in captured.out
    assert not destination(repo_root).exists()


def test_zip_source_with_missing_required_file_fails(capsys, tmp_path: Path) -> None:
    importer = load_import_module()
    source = tmp_path / "Archive.zip"
    repo_root = tmp_path / "repo"
    write_screening_zip(source, omit={"ABSTRACT_REVIEW.md"})

    exit_code = run_import(importer, repo_root, source)

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Missing required Markdown file(s): ABSTRACT_REVIEW.md" in captured.err
    assert not destination(repo_root).exists()


def test_zip_source_with_unsafe_marker_fails(capsys, tmp_path: Path) -> None:
    importer = load_import_module()
    source = tmp_path / "Archive.zip"
    repo_root = tmp_path / "repo"
    write_screening_zip(source, text="reviewed abstract-screening record\nfull_text_reviewed: yes\n")

    exit_code = run_import(importer, repo_root, source)

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Unsafe marker(s) detected" in captured.err
    assert "full_text_reviewed: yes" in captured.err
    assert not destination(repo_root).exists()


def test_zip_source_with_path_traversal_entry_fails(capsys, tmp_path: Path) -> None:
    importer = load_import_module()
    source = tmp_path / "Archive.zip"
    repo_root = tmp_path / "repo"
    write_screening_zip(source, extras={"../evil.md": "do not extract"})

    exit_code = run_import(importer, repo_root, source)

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Unsafe zip entry path: ../evil.md" in captured.err
    assert not (tmp_path / "evil.md").exists()
    assert not destination(repo_root).exists()


def test_zip_source_with_symlink_entry_fails(capsys, tmp_path: Path) -> None:
    importer = load_import_module()
    source = tmp_path / "Archive.zip"
    repo_root = tmp_path / "repo"
    write_screening_zip(source)
    with zipfile.ZipFile(source, "a") as archive:
        info = zipfile.ZipInfo("paper_note_drafts/link.md")
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(info, "target.md")

    exit_code = run_import(importer, repo_root, source)

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Unsafe zip entry is a symlink: paper_note_drafts/link.md" in captured.err
    assert not destination(repo_root).exists()


def test_zip_source_overwrite_replaces_only_managed_files(capsys, tmp_path: Path) -> None:
    importer = load_import_module()
    source = tmp_path / "Archive.zip"
    repo_root = tmp_path / "repo"
    write_screening_zip(source, text="new reviewed content\n")
    dest = destination(repo_root)
    dest.mkdir(parents=True)
    (dest / "SEARCH_SUMMARY.md").write_text("old", encoding="utf-8")
    (dest / "KEEP.md").write_text("keep me", encoding="utf-8")

    exit_code = run_import(importer, repo_root, source, "--apply", "--overwrite")

    capsys.readouterr()
    assert exit_code == 0
    assert "new reviewed content" in (dest / "SEARCH_SUMMARY.md").read_text(encoding="utf-8")
    assert (dest / "KEEP.md").read_text(encoding="utf-8") == "keep me"
    assert sorted(path.name for path in dest.iterdir()) == sorted((*REQUIRED_FILES, "KEEP.md"))


def test_missing_required_file_fails(capsys, tmp_path: Path) -> None:
    importer = load_import_module()
    source = tmp_path / "screening_outputs"
    repo_root = tmp_path / "repo"
    write_screening_source(source)
    (source / "ABSTRACT_REVIEW.md").unlink()

    exit_code = run_import(importer, repo_root, source, "--apply")

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Missing required Markdown file(s): ABSTRACT_REVIEW.md" in captured.err
    assert not destination(repo_root).exists()


def test_existing_non_empty_destination_fails_without_overwrite(capsys, tmp_path: Path) -> None:
    importer = load_import_module()
    source = tmp_path / "screening_outputs"
    repo_root = tmp_path / "repo"
    write_screening_source(source, text="new content\n")
    dest = destination(repo_root)
    dest.mkdir(parents=True)
    (dest / "README.md").write_text("existing", encoding="utf-8")

    exit_code = run_import(importer, repo_root, source)

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Destination already exists and is non-empty" in captured.err
    assert (dest / "README.md").read_text(encoding="utf-8") == "existing"
    assert not (dest / "SEARCH_SUMMARY.md").exists()


def test_overwrite_replaces_only_managed_files(capsys, tmp_path: Path) -> None:
    importer = load_import_module()
    source = tmp_path / "screening_outputs"
    repo_root = tmp_path / "repo"
    write_screening_source(source, text="new reviewed content\n")
    dest = destination(repo_root)
    dest.mkdir(parents=True)
    (dest / "SEARCH_SUMMARY.md").write_text("old", encoding="utf-8")
    (dest / "KEEP.md").write_text("keep me", encoding="utf-8")

    exit_code = run_import(importer, repo_root, source, "--apply", "--overwrite")

    capsys.readouterr()
    assert exit_code == 0
    assert "new reviewed content" in (dest / "SEARCH_SUMMARY.md").read_text(encoding="utf-8")
    assert (dest / "KEEP.md").read_text(encoding="utf-8") == "keep me"
    assert sorted(path.name for path in dest.iterdir()) == sorted((*REQUIRED_FILES, "KEEP.md"))


def test_paper_note_drafts_are_ignored_not_imported(tmp_path: Path) -> None:
    importer = load_import_module()
    source = tmp_path / "screening_outputs"
    repo_root = tmp_path / "repo"
    write_screening_source(source)
    (source / "paper_note_drafts").mkdir()
    (source / "paper_note_drafts" / "candidate.md").write_text("candidate note", encoding="utf-8")

    exit_code = run_import(importer, repo_root, source, "--apply")

    assert exit_code == 0
    assert not (destination(repo_root) / "paper_note_drafts").exists()
    assert not (repo_root / "Papers").exists()


def test_unsafe_markers_block_import(capsys, tmp_path: Path) -> None:
    importer = load_import_module()
    source = tmp_path / "screening_outputs"
    repo_root = tmp_path / "repo"
    write_screening_source(source)
    (source / "SEARCH_SUMMARY.md").write_text(
        "\n".join(
            [
                "This mentions a full-text-reviewed note-depth label without claiming metadata.",
                "note_depth: full_text_reviewed",
            ]
        ),
        encoding="utf-8",
    )

    exit_code = run_import(importer, repo_root, source, "--apply")

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Unsafe marker(s) detected" in captured.err
    assert "note_depth: full_text_reviewed" in captured.err
    assert not destination(repo_root).exists()


def test_explanatory_full_text_phrase_without_exact_metadata_claim_is_allowed(tmp_path: Path) -> None:
    importer = load_import_module()
    source = tmp_path / "screening_outputs"
    repo_root = tmp_path / "repo"
    write_screening_source(
        source,
        text="This explains the full-text-reviewed note-depth label without asserting metadata.\n",
    )

    exit_code = run_import(importer, repo_root, source, "--apply")

    assert exit_code == 0
    assert destination(repo_root).exists()


def test_path_safe_validation_for_date_and_topic_slug(capsys, tmp_path: Path) -> None:
    importer = load_import_module()
    source = tmp_path / "screening_outputs"
    repo_root = tmp_path / "repo"
    write_screening_source(source)

    bad_slug_code = importer.main(
        [
            "--source",
            str(source),
            "--topic-slug",
            "../bad",
            "--date",
            "2026-05-20",
            "--repo-root",
            str(repo_root),
        ]
    )
    bad_date_code = importer.main(
        [
            "--source",
            str(source),
            "--topic-slug",
            "safe_slug",
            "--date",
            "2026-5-20",
            "--repo-root",
            str(repo_root),
        ]
    )

    captured = capsys.readouterr()
    assert bad_slug_code == 1
    assert bad_date_code == 1
    assert "letters, numbers, underscores, and hyphens" in captured.err
    assert "--date must use YYYY-MM-DD" in captured.err


def test_required_source_symlink_fails(capsys, tmp_path: Path) -> None:
    importer = load_import_module()
    source = tmp_path / "screening_outputs"
    repo_root = tmp_path / "repo"
    write_screening_source(source)
    outside = tmp_path / "outside.md"
    outside.write_text("external", encoding="utf-8")
    (source / "SEARCH_SUMMARY.md").unlink()
    (source / "SEARCH_SUMMARY.md").symlink_to(outside)

    exit_code = run_import(importer, repo_root, source)

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "SEARCH_SUMMARY.md is a symlink" in captured.err
    assert not destination(repo_root).exists()


def test_source_directory_symlink_fails(capsys, tmp_path: Path) -> None:
    importer = load_import_module()
    source = tmp_path / "screening_outputs"
    source_link = tmp_path / "screening_outputs_link"
    repo_root = tmp_path / "repo"
    write_screening_source(source)
    source_link.symlink_to(source, target_is_directory=True)

    exit_code = run_import(importer, repo_root, source_link)

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "--source must not be a symlink" in captured.err
    assert not destination(repo_root).exists()


def test_overwrite_refuses_managed_destination_symlink(capsys, tmp_path: Path) -> None:
    importer = load_import_module()
    source = tmp_path / "screening_outputs"
    repo_root = tmp_path / "repo"
    write_screening_source(source)
    dest = destination(repo_root)
    dest.mkdir(parents=True)
    outside = tmp_path / "outside.md"
    outside.write_text("do not touch", encoding="utf-8")
    (dest / "SEARCH_SUMMARY.md").symlink_to(outside)

    exit_code = run_import(importer, repo_root, source, "--apply", "--overwrite")

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Unsafe managed destination file(s): SEARCH_SUMMARY.md is a symlink" in captured.err
    assert outside.read_text(encoding="utf-8") == "do not touch"
