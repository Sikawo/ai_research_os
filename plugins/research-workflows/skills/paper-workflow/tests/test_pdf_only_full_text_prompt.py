from __future__ import annotations

import importlib.util
import json
import sys
import zipfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_export_module():
    script_path = REPO_ROOT / "scripts" / "export_public_pdf_prompt.py"
    spec = importlib.util.spec_from_file_location("export_pdf_only_full_text_prompt_for_tests", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_export_creates_prompt_zip_without_pdf_inputs(tmp_path: Path) -> None:
    exporter = load_export_module()
    output_root = tmp_path / "exports" / "pdf_only_full_text_prompt"
    output_zip = tmp_path / "Downloads" / "public_pdf_prompt.zip"

    exit_code = exporter.main(
        [
            "--batch-name",
            "kinase review batch",
            "--priority",
            "high",
            "--project",
            "public_project",
            "--tag",
            "full_text",
            "--max-pdfs",
            "3",
            "--output-root",
            str(output_root),
            "--output-zip",
            str(output_zip),
            "--timestamp",
            "20260518_130000",
        ]
    )

    assert exit_code == 0
    assert output_zip.exists()
    with zipfile.ZipFile(output_zip) as archive:
        names = sorted(archive.namelist())
        assert names == [
            "BATCH_MANIFEST.json",
            "CHATGPT_INSTRUCTIONS.md",
            "METADATA_VERIFICATION_INSTRUCTIONS.md",
            "PUBLIC_FULL_TEXT_NOTE_TEMPLATE.md",
            "RETURN_ZIP_REQUIREMENTS.md",
        ]
        instructions = archive.read("CHATGPT_INSTRUCTIONS.md").decode("utf-8")
        metadata = archive.read("METADATA_VERIFICATION_INSTRUCTIONS.md").decode("utf-8")
        template = archive.read("PUBLIC_FULL_TEXT_NOTE_TEMPLATE.md").decode("utf-8")
        return_requirements = archive.read("RETURN_ZIP_REQUIREMENTS.md").decode("utf-8")
        manifest = json.loads(archive.read("BATCH_MANIFEST.json").decode("utf-8"))

    assert "source: uploaded_public_pdf" in instructions
    assert "note_depth: public_full_text_reviewed" in instructions
    assert "security_tier: public" in instructions
    assert "Please MD this paper PDF." in instructions
    assert "このPDFを論文MD化して" in instructions
    assert "1-3 PDFs" in instructions
    assert "FirstAuthor_JournalAbbrev_Year.md" in instructions
    assert "Rivera_NatCommun_2016.md" in instructions
    assert "random numbers, timestamps, or session-specific suffixes" in instructions
    assert "Configured prompt ZIP maximum PDF count: 3." in instructions
    assert "conflict_needs_human_check" in metadata
    assert "# Figure-by-Figure Summary" in template
    assert "include no PDFs" in return_requirements
    assert "FirstAuthor_JournalAbbrev_Year.md" in return_requirements
    assert "Dahmane_NatCommun_2022.md" in return_requirements
    assert "DOI-derived suffix" in return_requirements
    assert manifest["bookends_xml_required"] is False
    assert manifest["pdf_files_read_copied_modified_uploaded"] == 0
    assert manifest["projects"] == ["public_project"]
    assert manifest["tags"] == ["full_text"]

    manifest_path = output_root / "20260518_130000" / "BATCH_MANIFEST.json"
    assert manifest_path.exists()
    assert str(tmp_path) not in manifest_path.read_text(encoding="utf-8")


def test_export_rejects_zero_max_pdfs(tmp_path: Path) -> None:
    exporter = load_export_module()

    exit_code = exporter.main(
        [
            "--max-pdfs",
            "0",
            "--output-root",
            str(tmp_path / "exports"),
            "--output-zip",
            str(tmp_path / "prompt.zip"),
        ]
    )

    assert exit_code == 1
    assert not (tmp_path / "prompt.zip").exists()
