import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "run_triage.py"


def write_synthetic_pubmed_fixture(tmp_path):
    fixture = tmp_path / "synthetic_pubmed_results.json"
    fixture.write_text(
        json.dumps(
            {
                "records": [
                    {
                        "pmid": "44444444",
                        "title": "Synthetic public PMC full text signaling article",
                        "authors": ["Ada Example", "Ben Public"],
                        "year": "2026",
                        "journal": "Journal of Synthetic Public PMC",
                        "doi": "10.0000/synthetic.fulltext.1",
                        "pmcid": "PMC4444444",
                        "abstract": (
                            "This synthetic abstract studies public kinase signaling "
                            "and cell-state regulation for fixture-only testing."
                        ),
                    },
                    {
                        "pmid": "55555555",
                        "title": "Synthetic PMCID record without exported XML",
                        "authors": ["Casey Fixture"],
                        "year": "2025",
                        "journal": "Synthetic Missing Fixtures",
                        "pmcid": "PMC5555555",
                        "abstract": "This synthetic abstract has no matching PMC XML fixture.",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    return fixture


def write_synthetic_pmc_fixture(tmp_path):
    fixture_dir = tmp_path / "synthetic_pmc_fixtures"
    fixture_dir.mkdir()
    (fixture_dir / "PMC4444444.xml").write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<article>
  <front>
    <article-meta>
      <title-group>
        <article-title>Synthetic public PMC full text signaling article</article-title>
      </title-group>
      <abstract>
        <p>Public PMC abstract sentence for synthetic kinase signaling.</p>
      </abstract>
    </article-meta>
  </front>
  <body>
    <sec>
      <title>Results</title>
      <p>Public PMC body text reports synthetic signaling evidence in exported XML.</p>
      <p>Public PMC body text describes cell-state regulation in a fixture paragraph.</p>
    </sec>
    <sec>
      <title>Methods</title>
      <p>Public PMC methods text describes fixture-only controls and extraction.</p>
    </sec>
    <fig>
      <caption>
        <p>Public PMC figure caption describes a synthetic signaling panel.</p>
      </caption>
    </fig>
  </body>
</article>
""",
        encoding="utf-8",
    )
    return fixture_dir


def run_full_text_draft_triage(tmp_path):
    pubmed_fixture = write_synthetic_pubmed_fixture(tmp_path)
    pmc_fixture_dir = write_synthetic_pmc_fixture(tmp_path)
    output_root = tmp_path / "exports" / "pubmed_ai_triage"
    args = [
        sys.executable,
        str(SCRIPT),
        "--goal",
        "Synthetic public PMC full-text draft goal for kinase signaling.",
        "--topic-slug",
        "synthetic_public_pmc_full_text_drafts",
        "--input-pubmed-json",
        str(pubmed_fixture),
        "--input-pmc-fixtures",
        str(pmc_fixture_dir),
        "--check-pmc-full-text",
        "--generate-full-text-drafts",
        "--pmc-top-n",
        "5",
        "--abstract-top-n",
        "2",
        "--output-root",
        str(output_root),
        "--timestamp",
        "20260526_150000",
    ]
    result = subprocess.run(
        args,
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )
    run_folder = output_root / "20260526_150000_synthetic_public_pmc_full_text_drafts"
    return result, run_folder


def full_text_draft_paths(run_folder):
    return sorted(
        path
        for path in (run_folder / "generated_notes" / "full_text_level").glob("*.md")
        if path.name != "README.md"
    )


def test_fixture_run_generates_public_pmc_full_text_draft(tmp_path):
    result, run_folder = run_full_text_draft_triage(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    full_text_notes = full_text_draft_paths(run_folder)
    assert len(full_text_notes) == 1
    note = full_text_notes[0].read_text(encoding="utf-8")

    assert "note_depth: public_full_text_reviewed" in note
    assert "security_tier: public" in note
    assert "read_depth: public_full_text_reviewed" in note
    assert "pmc_full_text: true" in note
    assert "public_pmc_xml: true" in note
    assert "pdf_full_text: false" in note
    assert "human_review_status: ai_draft_needs_human_review" in note
    assert "local_pmc_xml_export_path: \"pmc_full_text/xml/PMC4444444.xml\"" in note
    assert "local_pmc_text_export_path: \"pmc_full_text/text/PMC4444444.txt\"" in note


def test_generated_full_text_note_uses_synthetic_public_pmc_fixture_content(tmp_path):
    result, run_folder = run_full_text_draft_triage(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    note = full_text_draft_paths(run_folder)[0].read_text(encoding="utf-8")

    assert "Public PMC-Derived Summary" in note
    assert "Public PMC abstract sentence for synthetic kinase signaling" in note
    assert "Results: Public PMC body text reports synthetic signaling evidence" in note
    assert "Methods And Controls Visible In Public XML" in note
    assert "fixture-only controls and extraction" in note
    assert "Figure Captions Visible In Public XML" in note
    assert "synthetic signaling panel" in note
    assert "Local Heuristic Relevance Interpretation" in note
    assert "Unanswered Questions For Human Full-Text Review" in note


def test_generated_full_text_note_avoids_unsafe_metadata_and_labels(tmp_path):
    result, run_folder = run_full_text_draft_triage(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    note = full_text_draft_paths(run_folder)[0].read_text(encoding="utf-8")
    forbidden_fragments = [
        "abstract_metadata_only",
        "restricted_internal_full_text",
        "source_url",
        "file:" + "//",
        "/" + "Users/",
        str(tmp_path),
        "secret",
        "token",
        "credential",
        "private",
        "internal",
        "restricted",
    ]
    for fragment in forbidden_fragments:
        assert fragment not in note


def test_selected_notes_manifest_and_discussion_remain_safe(tmp_path):
    result, run_folder = run_full_text_draft_triage(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    selected_notes = (run_folder / "selected_notes.yaml").read_text(encoding="utf-8")
    assert "notes: []" in selected_notes
    assert "approved_for_import" not in selected_notes

    manifest = json.loads((run_folder / "pubmed_triage_manifest.json").read_text(encoding="utf-8"))
    assert manifest["workflow_phase"] == "public_pmc_full_text_draft_generation"
    assert manifest["external_ai_api_called"] is False
    assert manifest["pmc_full_text_checked"] is True
    assert manifest["pmc_full_text_retrieved"] is True
    assert manifest["pmc_text_extracted"] is True
    assert manifest["full_text_note_drafts_generated"] is True
    assert manifest["generated_full_text_note_count"] == 1
    assert manifest["pdf_reading_performed"] is False
    assert manifest["bookends_parsing_performed"] is False
    assert manifest["publisher_full_text_retrieved"] is False
    assert manifest["supplementary_files_retrieved"] is False
    assert manifest["paper_notes_imported"] is False
    assert manifest["papers_write_performed"] is False
    assert manifest["git_actions_performed"] is False

    discussion = (run_folder / "DISCUSS_IMPORT_TO_PAPERS.md").read_text(encoding="utf-8")
    assert "Generated Full-Text-Level Draft Note Paths" in discussion
    assert "generated_notes/full_text_level/" in discussion
    assert "pmc_full_text/text/PMC4444444.txt" in discussion
    assert "not automatically importable" in discussion


def test_pmc_availability_results_record_generated_draft_paths(tmp_path):
    result, run_folder = run_full_text_draft_triage(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    data = json.loads((run_folder / "pmc_availability_results.json").read_text(encoding="utf-8"))
    generated = next(item for item in data["pmc_availability_results"] if item["pmcid"] == "PMC4444444")
    missing = next(item for item in data["pmc_availability_results"] if item["pmcid"] == "PMC5555555")

    assert generated["full_text_note_draft_generated"] is True
    assert generated["generated_full_text_note_path"].startswith("generated_notes/full_text_level/")
    assert generated["local_xml_export_path"] == "pmc_full_text/xml/PMC4444444.xml"
    assert generated["local_text_export_path"] == "pmc_full_text/text/PMC4444444.txt"
    assert missing["full_text_note_draft_generated"] is False
    assert missing["generated_full_text_note_path"] == ""
