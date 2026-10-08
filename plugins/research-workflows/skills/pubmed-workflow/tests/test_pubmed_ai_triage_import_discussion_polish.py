import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "run_triage.py"


def write_pubmed_fixture(tmp_path):
    fixture = tmp_path / "synthetic_pubmed_results.json"
    fixture.write_text(
        json.dumps(
            {
                "records": [
                    {
                        "pmid": "77777777",
                        "title": "Synthetic import discussion public PMC candidate",
                        "authors": ["Ada Example"],
                        "year": "2026",
                        "journal": "Synthetic Import Review",
                        "doi": "10.0000/import.discussion.1",
                        "pmcid": "PMC7777777",
                        "abstract": (
                            "Synthetic public abstract about kinase signaling and "
                            "triage import discussion decisions."
                        ),
                    },
                    {
                        "pmid": "88888888",
                        "title": "Synthetic abstract only import discussion candidate",
                        "authors": ["Ben Public"],
                        "year": "2025",
                        "journal": "Synthetic Abstract Review",
                        "doi": "10.0000/import.discussion.2",
                        "abstract": (
                            "Synthetic public abstract about kinase signaling without "
                            "public PMC full text."
                        ),
                    },
                    {
                        "pmid": "99999999",
                        "title": "Synthetic PMCID candidate without fixture text",
                        "authors": ["Casey Fixture"],
                        "year": "2024",
                        "journal": "Synthetic Missing Review",
                        "pmcid": "PMC9999999",
                        "abstract": "Synthetic public abstract with a missing public PMC fixture.",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    return fixture


def write_pmc_fixture(tmp_path):
    fixture_dir = tmp_path / "synthetic_pmc_fixtures"
    fixture_dir.mkdir()
    (fixture_dir / "PMC7777777.xml").write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<article>
  <front>
    <article-meta>
      <title-group>
        <article-title>Synthetic import discussion public PMC candidate</article-title>
      </title-group>
      <abstract>
        <p>Public PMC abstract text for synthetic import discussion.</p>
      </abstract>
    </article-meta>
  </front>
  <body>
    <sec>
      <title>Results</title>
      <p>Public PMC body text supports synthetic import discussion review.</p>
    </sec>
    <sec>
      <title>Methods</title>
      <p>Public PMC methods text describes fixture-only review controls.</p>
    </sec>
  </body>
</article>
""",
        encoding="utf-8",
    )
    return fixture_dir


def run_triage(tmp_path):
    pubmed_fixture = write_pubmed_fixture(tmp_path)
    pmc_fixture_dir = write_pmc_fixture(tmp_path)
    output_root = tmp_path / "exports" / "pubmed_ai_triage"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--goal",
            "Synthetic public import discussion polish goal.",
            "--topic-slug",
            "synthetic_public_import_discussion_polish",
            "--input-pubmed-json",
            str(pubmed_fixture),
            "--input-pmc-fixtures",
            str(pmc_fixture_dir),
            "--check-pmc-full-text",
            "--generate-full-text-drafts",
            "--ai-backend",
            "mock",
            "--abstract-top-n",
            "3",
            "--pmc-top-n",
            "3",
            "--output-root",
            str(output_root),
            "--timestamp",
            "20260526_180000",
        ],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )
    run_folder = output_root / "20260526_180000_synthetic_public_import_discussion_polish"
    return result, run_folder


def test_discussion_packet_separates_import_decision_categories(tmp_path):
    result, run_folder = run_triage(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    discussion = (run_folder / "DISCUSS_IMPORT_TO_PAPERS.md").read_text(encoding="utf-8")

    assert "topic slug: `synthetic_public_import_discussion_polish`" in discussion
    assert "PubMed query or fixture status: fixture PubMed JSON input was used" in discussion
    assert "records retrieved or loaded: `3`" in discussion
    assert "abstract-level generated note count: `3`" in discussion
    assert "public-PMC-full-text generated note count: `1`" in discussion
    assert "AI backend interface `mock` generated local safety-gated output only" in discussion
    assert "## Abstract-Only Draft Candidates" in discussion
    assert "## Public PMC Full-Text Draft Candidates" in discussion
    assert "## Candidates Not Ready For Import" in discussion
    assert "## Notes Requiring Further Review Before Import" in discussion


def test_discussion_includes_paths_prompt_and_human_review_reminders(tmp_path):
    result, run_folder = run_triage(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    discussion = (run_folder / "DISCUSS_IMPORT_TO_PAPERS.md").read_text(encoding="utf-8")

    assert "generated_notes/abstract_level/" in discussion
    assert "generated_notes/full_text_level/" in discussion
    assert "pmc_full_text/text/PMC7777777.txt" in discussion
    assert "Copy-paste-ready AI discussion prompt" in discussion
    assert "recommend one of: new, replace_abstract_only, skip, or needs_more_human_review" in discussion
    assert "Generated note drafts normally contain" in discussion
    assert "human_review_status: ai_draft_needs_human_review" in discussion
    assert "human_review_status: approved_for_import" in discussion
    assert "selected_notes.yaml` alone may not be enough" in discussion
    assert "The PubMed AI triage script does not write to `Papers/`" in discussion
    assert "Private, restricted, PDF-derived, Bookends-derived, or unreviewed material" in discussion


def test_selected_notes_safe_default_and_instructions_cover_actions(tmp_path):
    result, run_folder = run_triage(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    selected_notes = (run_folder / "selected_notes.yaml").read_text(encoding="utf-8")
    instructions = (run_folder / "selected_notes_instructions.md").read_text(encoding="utf-8")

    assert "notes: []" in selected_notes
    assert "approved_for_import" not in selected_notes
    assert "action: new" in instructions
    assert "action: replace_abstract_only" in instructions
    assert "action: skip" in instructions
    assert "expected note depth: `abstract_metadata_only`" in instructions
    assert "read depth: `pubmed_abstract_reviewed`" in instructions
    assert "expected note depth: `public_full_text_reviewed`" in instructions
    assert "read depth: `public_full_text_reviewed`" in instructions
    assert "external AI suggestions only" in instructions
    assert "not human approval" in instructions
    assert "should not change `human_review_status` without human review" in instructions


def test_summary_manifest_and_outputs_preserve_human_control(tmp_path):
    result, run_folder = run_triage(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    summary = (run_folder / "PUBMED_TRIAGE_SUMMARY.md").read_text(encoding="utf-8")
    manifest = json.loads((run_folder / "pubmed_triage_manifest.json").read_text(encoding="utf-8"))

    assert "## End-To-End Import Workflow" in summary
    assert "Review `DISCUSS_IMPORT_TO_PAPERS.md` with AI or manually" in summary
    assert "Run `../paper-workflow/scripts/review_selected_notes.py` in dry-run mode" in summary
    assert "Run the importer with `--apply` only after reviewing the import review packet" in summary
    assert "Generated exports remain temporary under `exports/`" in summary
    assert manifest["output_locations"]["selected_notes_instructions"] == "selected_notes_instructions.md"
    assert manifest["paper_notes_imported"] is False
    assert manifest["papers_write_performed"] is False
    assert manifest["git_actions_performed"] is False
    assert manifest["external_ai_api_called"] is False
    assert manifest["external_ai_api_key_used"] is False
    assert manifest["mock_ai_backend_used"] is True
    assert not (tmp_path / "Papers").exists()
