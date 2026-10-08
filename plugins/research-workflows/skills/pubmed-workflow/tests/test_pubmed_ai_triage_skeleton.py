import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "run_triage.py"


def run_skeleton(tmp_path, *extra_args):
    output_root = tmp_path / "exports" / "pubmed_ai_triage"
    args = [
        sys.executable,
        str(SCRIPT),
        "--goal",
        "Find public papers relevant to a one-sentence research goal.",
        "--topic-slug",
        "example_topic",
        "--output-root",
        str(output_root),
        "--timestamp",
        "20260526T123456Z",
        *extra_args,
    ]
    return subprocess.run(
        args,
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )


def test_skeleton_command_creates_expected_folder_shape(tmp_path):
    result = run_skeleton(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    run_folder = tmp_path / "exports" / "pubmed_ai_triage" / "20260526T123456Z_example_topic"
    assert run_folder.is_dir()
    assert (run_folder / "PUBMED_TRIAGE_SUMMARY.md").is_file()
    assert (run_folder / "pubmed_triage_manifest.json").is_file()
    assert (run_folder / "generated_notes").is_dir()
    assert (run_folder / "generated_notes" / "abstract_level").is_dir()
    assert (run_folder / "generated_notes" / "full_text_level").is_dir()
    assert (run_folder / "DISCUSS_IMPORT_TO_PAPERS.md").is_file()
    assert (run_folder / "selected_notes.yaml").is_file()
    assert str(run_folder) in result.stdout
    assert "PUBMED_TRIAGE_SUMMARY.md" in result.stdout
    assert "DISCUSS_IMPORT_TO_PAPERS.md" in result.stdout


def test_manifest_fields_are_skeleton_only(tmp_path):
    result = run_skeleton(
        tmp_path,
        "--retmax",
        "25",
        "--abstract-top-n",
        "3",
        "--full-text-top-n",
        "2",
    )

    assert result.returncode == 0, result.stderr + result.stdout
    manifest_path = (
        tmp_path
        / "exports"
        / "pubmed_ai_triage"
        / "20260526T123456Z_example_topic"
        / "pubmed_triage_manifest.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest["workflow_name"] == "pubmed_ai_triage"
    assert manifest["workflow_phase"] == "skeleton_export_only"
    assert manifest["goal"] == "Find public papers relevant to a one-sentence research goal."
    assert manifest["topic_slug"] == "example_topic"
    assert manifest["created_timestamp"] == "20260526T123456Z"
    assert manifest["planned_retmax"] == 25
    assert manifest["planned_abstract_level_top_n"] == 3
    assert manifest["planned_full_text_top_n"] == 2
    assert manifest["pubmed_search_performed"] is False
    assert manifest["abstracts_retrieved"] is False
    assert manifest["ai_screening_performed"] is False
    assert manifest["pmc_full_text_checked"] is False
    assert manifest["pmc_full_text_retrieved"] is False
    assert manifest["paper_notes_imported"] is False
    assert manifest["git_actions_performed"] is False
    assert manifest["future_output_locations"]["selected_notes"] == "selected_notes.yaml"
    assert "../paper-workflow/scripts/review_selected_notes.py" in manifest["compatibility_note"]


def test_selected_notes_is_safe_and_empty_by_default(tmp_path):
    result = run_skeleton(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    selected_notes = (
        tmp_path
        / "exports"
        / "pubmed_ai_triage"
        / "20260526T123456Z_example_topic"
        / "selected_notes.yaml"
    ).read_text(encoding="utf-8")

    assert "notes: []" in selected_notes
    assert "approved_for_import" not in selected_notes
    assert "target_path: Papers/" not in selected_notes


def test_summary_and_discussion_state_actions_not_performed(tmp_path):
    result = run_skeleton(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    run_folder = tmp_path / "exports" / "pubmed_ai_triage" / "20260526T123456Z_example_topic"
    combined_text = (
        (run_folder / "PUBMED_TRIAGE_SUMMARY.md").read_text(encoding="utf-8")
        + "\n"
        + (run_folder / "DISCUSS_IMPORT_TO_PAPERS.md").read_text(encoding="utf-8")
    )

    required_phrases = [
        "did not search PubMed",
        "call AI APIs",
        "perform AI screening",
        "retrieve PMC full text",
        "read PDFs",
        "parse Bookends",
        "write to `Papers/`",
        "perform Git actions",
    ]
    for phrase in required_phrases:
        assert phrase in combined_text


def test_rejects_unsafe_topic_slug(tmp_path):
    output_root = tmp_path / "exports" / "pubmed_ai_triage"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--goal",
            "Find public papers relevant to a one-sentence research goal.",
            "--topic-slug",
            "../bad",
            "--output-root",
            str(output_root),
            "--timestamp",
            "20260526T123456Z",
        ],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert not output_root.exists()


def test_rejects_blank_goal(tmp_path):
    output_root = tmp_path / "exports" / "pubmed_ai_triage"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--goal",
            "   ",
            "--topic-slug",
            "example_topic",
            "--output-root",
            str(output_root),
            "--timestamp",
            "20260526T123456Z",
        ],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert not output_root.exists()


def test_does_not_write_to_papers(tmp_path):
    result = run_skeleton(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    assert not (tmp_path / "Papers").exists()


def test_rejects_output_root_inside_papers(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--goal",
            "Find public papers relevant to a one-sentence research goal.",
            "--topic-slug",
            "example_topic",
            "--output-root",
            str(tmp_path / "Papers" / "exports"),
            "--timestamp",
            "20260526T123456Z",
        ],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert "Papers/" in result.stdout
    assert not (tmp_path / "Papers").exists()
