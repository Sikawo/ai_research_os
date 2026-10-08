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
                        "title": "Synthetic kinase signaling in public abstract records",
                        "authors": ["Ada Example", "Ben Public"],
                        "year": "2025",
                        "journal": "Journal of Synthetic PubMed Fixtures",
                        "doi": "10.0000/synthetic.1",
                        "pmcid": "PMC1111111",
                        "abstract": (
                            "This synthetic abstract studies kinase signaling and "
                            "cell-state regulation using public metadata only. "
                            "It reports abstract-level observations for testing."
                        ),
                    },
                    {
                        "pmid": "22222222",
                        "title": "Unrelated public metadata control record",
                        "authors": ["Casey Fixture"],
                        "year": "2024",
                        "journal": "Synthetic Controls",
                        "abstract": (
                            "This abstract describes a control topic without the "
                            "target keyword overlap used by the heuristic."
                        ),
                    },
                    {
                        "pmid": "33333333",
                        "title": "Synthetic kinase abstract without PMCID",
                        "authors": [],
                        "year": "2023",
                        "journal": "Fixture Methods",
                        "doi": "10.0000/synthetic.3",
                        "abstract": "Kinase pathway evidence is represented only in this abstract.",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    return fixture


def run_triage(tmp_path, *extra_args):
    fixture = write_synthetic_pubmed_fixture(tmp_path)
    output_root = tmp_path / "exports" / "pubmed_ai_triage"
    args = [
        sys.executable,
        str(SCRIPT),
        "--goal",
        "Find public papers about synthetic kinase signaling.",
        "--topic-slug",
        "synthetic_public_literature_triage",
        "--input-pubmed-json",
        str(fixture),
        "--output-root",
        str(output_root),
        "--timestamp",
        "20260526_130000",
        "--abstract-top-n",
        "2",
        "--screening-backend",
        "heuristic",
        *extra_args,
    ]
    result = subprocess.run(
        args,
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )
    run_folder = output_root / "20260526_130000_synthetic_public_literature_triage"
    return result, run_folder


def test_fixture_run_creates_expected_output_files(tmp_path):
    result, run_folder = run_triage(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    assert run_folder.is_dir()
    assert (run_folder / "PUBMED_TRIAGE_SUMMARY.md").is_file()
    assert (run_folder / "pubmed_triage_manifest.json").is_file()
    assert (run_folder / "pubmed_results.json").is_file()
    assert (run_folder / "pubmed_results.csv").is_file()
    assert (run_folder / "abstract_screening_results.json").is_file()
    assert (run_folder / "generated_notes" / "abstract_level").is_dir()
    assert (run_folder / "generated_notes" / "full_text_level").is_dir()
    assert (run_folder / "DISCUSS_IMPORT_TO_PAPERS.md").is_file()
    assert (run_folder / "selected_notes.yaml").is_file()
    assert str(run_folder) in result.stdout
    assert "abstract_screening_results.json" in result.stdout


def test_generated_abstract_notes_are_abstract_only_and_public(tmp_path):
    result, run_folder = run_triage(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    note_paths = sorted((run_folder / "generated_notes" / "abstract_level").glob("*.md"))
    assert len(note_paths) == 2
    combined_notes = "\n".join(path.read_text(encoding="utf-8") for path in note_paths)

    assert "note_depth: abstract_metadata_only" in combined_notes
    assert "security_tier: public" in combined_notes
    assert "read_depth: pubmed_abstract_reviewed" in combined_notes
    assert "human_review_status: ai_draft_needs_human_review" in combined_notes
    assert "pubmed_metadata: true" in combined_notes
    assert "pubmed_abstract: true" in combined_notes
    assert "pmc_full_text: false" in combined_notes
    assert "pdf_full_text: false" in combined_notes
    assert "public_full_text_reviewed" not in combined_notes
    assert "restricted_internal_full_text" not in combined_notes
    assert "full_text_reviewed" not in combined_notes
    assert "source_url:" not in combined_notes
    assert "file:" + "//" not in combined_notes
    assert "/" + "Users/" not in combined_notes


def test_full_text_folder_is_placeholder_only(tmp_path):
    result, run_folder = run_triage(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    full_text_files = sorted((run_folder / "generated_notes" / "full_text_level").iterdir())
    assert [path.name for path in full_text_files] == ["README.md"]
    placeholder = full_text_files[0].read_text(encoding="utf-8")
    assert "not implemented" in placeholder
    assert "retrieve PMC full text" in placeholder


def test_selected_notes_is_safe_by_default(tmp_path):
    result, run_folder = run_triage(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    selected_notes = (run_folder / "selected_notes.yaml").read_text(encoding="utf-8")
    assert "notes: []" in selected_notes
    assert "approved_for_import" not in selected_notes
    assert "target_path: Papers/" not in selected_notes


def test_manifest_records_safe_phase_two_boundaries(tmp_path):
    result, run_folder = run_triage(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    manifest = json.loads((run_folder / "pubmed_triage_manifest.json").read_text(encoding="utf-8"))

    assert manifest["workflow_phase"] == "abstract_screening_drafts"
    assert manifest["records_loaded"] == 3
    assert manifest["pubmed_search_performed"] is False
    assert manifest["input_pubmed_json_used"] is True
    assert manifest["abstracts_retrieved"] is True
    assert manifest["ai_screening_performed"] is True
    assert manifest["screening_backend"] == "heuristic"
    assert manifest["external_ai_api_called"] is False
    assert manifest["pmc_full_text_checked"] is False
    assert manifest["pmc_full_text_retrieved"] is False
    assert manifest["pdf_reading_performed"] is False
    assert manifest["bookends_parsing_performed"] is False
    assert manifest["paper_notes_imported"] is False
    assert manifest["git_actions_performed"] is False
    assert manifest["papers_write_performed"] is False
    assert len(manifest["generated_abstract_note_paths"]) == 2


def test_screening_results_include_required_metadata(tmp_path):
    result, run_folder = run_triage(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    data = json.loads((run_folder / "abstract_screening_results.json").read_text(encoding="utf-8"))
    results = data["screening_results"]

    assert len(results) == 3
    for item in results:
        assert item["pmid"]
        assert item["title"]
        assert "year" in item
        assert "journal" in item
        assert "doi" in item
        assert "pmcid" in item
        assert isinstance(item["score"], float)
        assert item["relevance_label"] in {"high", "medium", "low", "unclear"}
        assert item["screening_backend"] == "heuristic"
        assert item["read_depth"] == "abstract"
        assert "PubMed metadata and abstract text" in item["support_evidence_limitations"]
        assert item["reason"]


def test_discussion_packet_summarizes_review_context(tmp_path):
    result, run_folder = run_triage(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    discussion = (run_folder / "DISCUSS_IMPORT_TO_PAPERS.md").read_text(encoding="utf-8")

    assert "Find public papers about synthetic kinase signaling." in discussion
    assert "records retrieved or loaded: `3`" in discussion
    assert "screening backend: `heuristic`" in discussion
    assert "Generated Abstract-Only Draft Notes" in discussion
    assert "Full-text-level drafting is not implemented yet." in discussion
    assert "notes: []" in discussion


def test_mock_backend_is_local_and_deterministic(tmp_path):
    result, run_folder = run_triage(tmp_path, "--screening-backend", "mock")

    assert result.returncode == 0, result.stderr + result.stdout
    data = json.loads((run_folder / "abstract_screening_results.json").read_text(encoding="utf-8"))
    scores = [item["score"] for item in data["screening_results"]]
    assert scores == [100.0, 90.0, 80.0]
    assert {item["screening_backend"] for item in data["screening_results"]} == {"mock"}
    manifest = json.loads((run_folder / "pubmed_triage_manifest.json").read_text(encoding="utf-8"))
    assert manifest["external_ai_api_called"] is False


def test_does_not_write_to_papers_or_private_inputs(tmp_path):
    result, _run_folder = run_triage(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    assert not (tmp_path / "Papers").exists()

    private_input = tmp_path / "Papers" / "private_fixture.json"
    private_input.parent.mkdir()
    private_input.write_text("[]", encoding="utf-8")
    output_root = tmp_path / "exports" / "pubmed_ai_triage"
    blocked = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--goal",
            "Find public papers about synthetic kinase signaling.",
            "--topic-slug",
            "synthetic_public_literature_triage",
            "--input-pubmed-json",
            str(private_input),
            "--output-root",
            str(output_root),
            "--timestamp",
            "20260526_130001",
        ],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )
    assert blocked.returncode == 2
    assert "Papers/" in blocked.stdout
