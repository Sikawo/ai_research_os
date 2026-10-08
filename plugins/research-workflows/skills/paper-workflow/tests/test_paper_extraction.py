from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_paper_extraction_module():
    script_path = REPO_ROOT / "scripts" / "build_bibliographic_note_packet.py"
    spec = importlib.util.spec_from_file_location("run_paper_extraction_for_tests", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def synthetic_bookends_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8"?>
<xml>
  <records>
    <record>
      <rec-number>1</rec-number>
      <titles>
        <title>Existing Study</title>
        <secondary-title>Journal of Synthetic Results</secondary-title>
      </titles>
      <contributors>
        <authors>
          <author>Doe, Jane</author>
        </authors>
      </contributors>
      <dates>
        <year>2024</year>
      </dates>
      <abstract>Public abstract text for the first synthetic record.</abstract>
    </record>
    <record>
      <rec-number>2</rec-number>
      <titles>
        <title>New Study</title>
        <secondary-title>Journal of Synthetic Results</secondary-title>
      </titles>
      <contributors>
        <authors>
          <author>Roe, Alex</author>
        </authors>
      </contributors>
      <dates>
        <year>2025</year>
      </dates>
      <abstract>Public abstract text for the second synthetic record.</abstract>
    </record>
  </records>
</xml>
"""


def test_prompt_packet_includes_route_metadata_without_local_paths(tmp_path: Path) -> None:
    paper_extraction = load_paper_extraction_module()
    template_text = (REPO_ROOT / "assets" / "paper_extraction_prompt_template.md").read_text(encoding="utf-8")
    note_template_text = (REPO_ROOT / "assets" / "paper_note_template.md").read_text(encoding="utf-8")
    note_path = tmp_path / "Papers" / "Roe_2025_New_Study.md"
    paper = paper_extraction.PaperRecord(
        record_id="2",
        title="New Study",
        authors=["Roe, Alex"],
        first_author="Roe",
        journal="Journal of Synthetic Results",
        year="2025",
        abstract="Public abstract text.",
        attachments=[
            paper_extraction.Attachment(
                local_path=tmp_path / "Bookends" / "Attachments" / "synthetic.pdf",
                storage_alias="bookends_attachments",
                relative_path="Attachments/synthetic.pdf",
                original_filename="synthetic.pdf",
                exists=False,
            )
        ],
    )
    route_metadata = paper_extraction.RouteMetadata(
        priority="medium",
        projects=["project_alpha", "project_beta"],
        tags=["batch", "abstract"],
    )

    packet = paper_extraction.render_prompt_packet(
        paper=paper,
        note_path=note_path,
        template_text=template_text,
        note_template_text=note_template_text,
        route_metadata=route_metadata,
    )

    assert "## Route Metadata" in packet
    assert 'source: "bookends_xml"' in packet
    assert 'note_depth: "abstract_metadata_only"' in packet
    assert 'security_tier: "public"' in packet
    assert 'status: "draft"' in packet
    assert 'priority: "medium"' in packet
    assert '  - "project_alpha"' in packet
    assert '  - "batch"' in packet
    assert "full-text, figure-level, or supplementary-material review" in packet
    assert "Papers/Roe_2025_New_Study.md" in packet
    assert str(tmp_path) not in packet
    assert "file:" + "//" not in packet


def test_main_skips_existing_notes_and_reports_batch_summary(tmp_path: Path, capsys) -> None:
    paper_extraction = load_paper_extraction_module()
    xml_path = tmp_path / "synthetic_export.xml"
    bookends_root = tmp_path / "Bookends"
    papers_dir = tmp_path / "Papers"
    output_dir = tmp_path / "packets"
    source_map_path = tmp_path / "Indexes" / "PAPER_SOURCE_MAP.yaml"
    bookends_root.mkdir()
    papers_dir.mkdir()
    xml_path.write_text(synthetic_bookends_xml(), encoding="utf-8")
    (papers_dir / "Doe_2024_Existing_Study.md").write_text("Existing note target.\n", encoding="utf-8")
    exit_code = paper_extraction.main(
        [
            "--source-mode",
            "bookends_xml",
            "--bookends-xml",
            str(xml_path),
            "--bookends-root",
            str(bookends_root),
            "--backend",
            "manual_prompt_packet",
            "--apply",
            "--output-dir",
            str(output_dir),
            "--papers-dir",
            str(papers_dir),
            "--source-map-output",
            str(source_map_path),
            "--priority",
            "high",
            "--project",
            "project_alpha",
            "--tag",
            "batch",
        ]
    )

    output = capsys.readouterr().out
    packets = sorted(output_dir.glob("*_prompt_packet.md"))
    assert exit_code == 0
    assert len(packets) == 1
    assert packets[0].name == "Roe_2025_New_Study_prompt_packet.md"
    packet_text = packets[0].read_text(encoding="utf-8")
    assert 'priority: "high"' in packet_text
    assert '  - "project_alpha"' in packet_text
    assert '  - "batch"' in packet_text
    assert str(tmp_path) not in packet_text
    assert "SKIP existing paper note target" in output
    assert "- records parsed: 2" in output
    assert "- prompt packets written: 1" in output
    assert "- prompt packets unchanged: 0" in output
    assert "- existing Papers/*.md targets skipped: 1" in output
    assert "- source map status: updated" in output
    assert "- external AI calls: 0" in output
    assert "- Bookends attachment modifications: 0" in output
    assert source_map_path.exists()


def test_main_defaults_to_dry_run_and_does_not_write(tmp_path: Path, capsys) -> None:
    paper_extraction = load_paper_extraction_module()
    xml_path = tmp_path / "synthetic_export.xml"
    bookends_root = tmp_path / "public-metadata"
    papers_dir = tmp_path / "paper-targets"
    output_dir = tmp_path / "packets"
    source_map_path = tmp_path / "review" / "source-map.yaml"
    bookends_root.mkdir()
    papers_dir.mkdir()
    xml_path.write_text(synthetic_bookends_xml(), encoding="utf-8")

    exit_code = paper_extraction.main(
        [
            "--source-mode",
            "bookends_xml",
            "--bookends-xml",
            str(xml_path),
            "--bookends-root",
            str(bookends_root),
            "--backend",
            "manual_prompt_packet",
            "--output-dir",
            str(output_dir),
            "--papers-dir",
            str(papers_dir),
            "--source-map-output",
            str(source_map_path),
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Dry run: True" in output
    assert "- prompt packets written: 0" in output
    assert "- prompt packets would be written in dry-run mode: 2" in output
    assert "- source map status: would update" in output
    assert not output_dir.exists()
    assert not source_map_path.exists()


def test_write_if_changed_distinguishes_dry_run_unchanged(tmp_path: Path) -> None:
    paper_extraction = load_paper_extraction_module()
    target = tmp_path / "packet.md"
    target.write_text("same\n", encoding="utf-8")

    unchanged = paper_extraction.write_if_changed(target, "same\n", dry_run=True)
    would_write = paper_extraction.write_if_changed(target, "different\n", dry_run=True)

    assert unchanged == paper_extraction.WRITE_UNCHANGED
    assert would_write == paper_extraction.WRITE_WOULD_WRITE
    assert target.read_text(encoding="utf-8") == "same\n"
