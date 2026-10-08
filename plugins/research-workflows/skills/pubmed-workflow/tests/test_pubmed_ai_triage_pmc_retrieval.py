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
                        "pmid": "11111111",
                        "title": "Synthetic public PMC kinase signaling article",
                        "authors": ["Ada Example", "Ben Public"],
                        "year": "2025",
                        "journal": "Journal of Synthetic PMC Fixtures",
                        "doi": "10.0000/synthetic.pmc.1",
                        "pmcid": "PMC1111111",
                        "abstract": (
                            "This synthetic abstract studies kinase signaling and "
                            "cell-state regulation using public metadata only."
                        ),
                    },
                    {
                        "pmid": "22222222",
                        "title": "Synthetic public PMC record without matching fixture",
                        "authors": ["Casey Fixture"],
                        "year": "2024",
                        "journal": "Synthetic Controls",
                        "pmcid": "PMC2222222",
                        "abstract": (
                            "This synthetic abstract has a PMCID but no local PMC XML "
                            "fixture, allowing retrieval failure to stay offline."
                        ),
                    },
                    {
                        "pmid": "33333333",
                        "title": "Synthetic public abstract without PMCID",
                        "authors": [],
                        "year": "2023",
                        "journal": "Fixture Methods",
                        "doi": "10.0000/synthetic.pmc.3",
                        "abstract": "Kinase pathway evidence is represented only in this abstract.",
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
    (fixture_dir / "PMC1111111.xml").write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<article>
  <front>
    <article-meta>
      <title-group>
        <article-title>Synthetic public PMC kinase signaling article</article-title>
      </title-group>
      <abstract>
        <p>Public PMC abstract text for synthetic kinase signaling.</p>
      </abstract>
    </article-meta>
  </front>
  <body>
    <sec>
      <title>Results</title>
      <p>Public PMC body paragraph describing synthetic signaling evidence.</p>
    </sec>
    <sec>
      <title>Methods</title>
      <p>Public PMC methods paragraph for fixture-only extraction.</p>
    </sec>
    <fig>
      <caption>
        <p>Public PMC figure caption text from XML only.</p>
      </caption>
    </fig>
  </body>
</article>
""",
        encoding="utf-8",
    )
    return fixture_dir


def run_pmc_triage(tmp_path, *extra_args):
    pubmed_fixture = write_synthetic_pubmed_fixture(tmp_path)
    pmc_fixture_dir = write_synthetic_pmc_fixture(tmp_path)
    output_root = tmp_path / "exports" / "pubmed_ai_triage"
    args = [
        sys.executable,
        str(SCRIPT),
        "--goal",
        "Synthetic public PMC full-text triage goal for kinase signaling.",
        "--topic-slug",
        "synthetic_public_pmc_triage",
        "--input-pubmed-json",
        str(pubmed_fixture),
        "--input-pmc-fixtures",
        str(pmc_fixture_dir),
        "--check-pmc-full-text",
        "--pmc-top-n",
        "3",
        "--abstract-top-n",
        "2",
        "--output-root",
        str(output_root),
        "--timestamp",
        "20260526_140000",
        *extra_args,
    ]
    result = subprocess.run(
        args,
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )
    run_folder = output_root / "20260526_140000_synthetic_public_pmc_triage"
    return result, run_folder


def test_fixture_run_creates_pmc_availability_results(tmp_path):
    result, run_folder = run_pmc_triage(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    availability_path = run_folder / "pmc_availability_results.json"
    assert availability_path.is_file()
    data = json.loads(availability_path.read_text(encoding="utf-8"))
    results = data["pmc_availability_results"]

    assert len(results) == 3
    loaded = next(item for item in results if item["pmcid"] == "PMC1111111")
    assert loaded["pmc_availability_status"] == "pmc_fixture_loaded"
    assert loaded["public_retrieval_source"] == "fixture"
    assert loaded["pmc_retrieval_attempted"] is True
    assert loaded["pmc_retrieval_succeeded"] is True
    assert loaded["pmc_text_extracted"] is True
    assert loaded["full_text_note_draft_generated"] is False
    assert loaded["text_character_count"] > 0


def test_fixture_run_writes_public_pmc_xml_and_text_only_under_run_folder(tmp_path):
    result, run_folder = run_pmc_triage(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    xml_path = run_folder / "pmc_full_text" / "xml" / "PMC1111111.xml"
    text_path = run_folder / "pmc_full_text" / "text" / "PMC1111111.txt"
    assert xml_path.is_file()
    assert text_path.is_file()
    assert (run_folder / "pmc_full_text" / "README.md").is_file()

    text = text_path.read_text(encoding="utf-8")
    assert "Public PMC XML Text Export" in text
    assert "Source: public PMC XML" in text
    assert "Public PMC body paragraph" in text
    assert "Public PMC figure caption text" in text
    assert "No PDFs" in text

    for exported_path in (xml_path, text_path):
        exported_path.resolve().relative_to(run_folder.resolve())


def test_full_text_level_contains_no_full_text_note_drafts(tmp_path):
    result, run_folder = run_pmc_triage(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    full_text_level = run_folder / "generated_notes" / "full_text_level"
    files = sorted(path.name for path in full_text_level.iterdir())
    assert files == ["README.md"]
    placeholder = (full_text_level / "README.md").read_text(encoding="utf-8")
    assert "Full-text-level Markdown paper-note drafting is not implemented" in placeholder
    assert "Phase 3b" in placeholder


def test_manifest_records_safe_pmc_phase_boundaries(tmp_path):
    result, run_folder = run_pmc_triage(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    manifest = json.loads((run_folder / "pubmed_triage_manifest.json").read_text(encoding="utf-8"))

    assert manifest["workflow_phase"] == "pmc_public_full_text_retrieval_export"
    assert manifest["external_ai_api_called"] is False
    assert manifest["pmc_full_text_checked"] is True
    assert manifest["pmc_full_text_retrieved"] is True
    assert manifest["pmc_text_extracted"] is True
    assert manifest["full_text_note_drafts_generated"] is False
    assert manifest["pdf_reading_performed"] is False
    assert manifest["bookends_parsing_performed"] is False
    assert manifest["paper_notes_imported"] is False
    assert manifest["papers_write_performed"] is False
    assert manifest["git_actions_performed"] is False
    assert manifest["pmcid_present_count"] == 2
    assert manifest["pmc_retrieved_or_fixture_loaded_count"] == 1


def test_selected_notes_remains_safe_and_pmc_text_is_separate(tmp_path):
    result, run_folder = run_pmc_triage(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    selected_notes = (run_folder / "selected_notes.yaml").read_text(encoding="utf-8")
    assert "notes: []" in selected_notes
    assert "approved_for_import" not in selected_notes
    assert "target_path: Papers/" not in selected_notes

    generated_note_paths = list((run_folder / "generated_notes").rglob("*"))
    assert not any("PMC1111111.txt" == path.name for path in generated_note_paths)
    assert (run_folder / "pmc_full_text" / "text" / "PMC1111111.txt").is_file()

    discussion = (run_folder / "DISCUSS_IMPORT_TO_PAPERS.md").read_text(encoding="utf-8")
    assert "PMC-Available Candidates" in discussion
    assert "pmc_full_text/text/PMC1111111.txt" in discussion
    assert "selected_notes.yaml` should remain safe by default" in discussion


def test_rejects_pmc_fixture_input_from_protected_repo_area(tmp_path):
    pubmed_fixture = write_synthetic_pubmed_fixture(tmp_path)
    private_fixture_dir = tmp_path / "Papers" / "synthetic_pmc_fixtures"
    private_fixture_dir.mkdir(parents=True)
    output_root = tmp_path / "exports" / "pubmed_ai_triage"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--goal",
            "Synthetic public PMC full-text triage goal for kinase signaling.",
            "--topic-slug",
            "synthetic_public_pmc_triage",
            "--input-pubmed-json",
            str(pubmed_fixture),
            "--input-pmc-fixtures",
            str(private_fixture_dir),
            "--check-pmc-full-text",
            "--output-root",
            str(output_root),
            "--timestamp",
            "20260526_140001",
        ],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert "Papers/" in result.stdout
