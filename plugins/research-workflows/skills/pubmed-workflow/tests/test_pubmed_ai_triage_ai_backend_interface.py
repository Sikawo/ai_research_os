import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "run_triage.py"


def write_synthetic_pubmed_fixture(tmp_path, *, unsafe_record=None):
    fixture = tmp_path / "synthetic_pubmed_results.json"
    record = {
        "pmid": "66666666",
        "title": "Synthetic public AI backend interface article",
        "authors": ["Ada Example"],
        "year": "2026",
        "journal": "Journal of Synthetic Public AI Backend Fixtures",
        "doi": "10.0000/synthetic.ai.backend",
        "pmcid": "PMC6666666",
        "abstract": (
            "This synthetic public abstract discusses kinase signaling and "
            "cell-state regulation for local backend interface testing."
        ),
    }
    if unsafe_record:
        record.update(unsafe_record)
    fixture.write_text(json.dumps({"records": [record]}), encoding="utf-8")
    return fixture


def write_synthetic_pmc_fixture(tmp_path, *, unsafe_text=""):
    fixture_dir = tmp_path / "synthetic_pmc_fixtures"
    fixture_dir.mkdir()
    extra = f"<p>{unsafe_text}</p>" if unsafe_text else ""
    (fixture_dir / "PMC6666666.xml").write_text(
        f"""<?xml version="1.0" encoding="UTF-8"?>
<article>
  <front>
    <article-meta>
      <title-group>
        <article-title>Synthetic public AI backend interface article</article-title>
      </title-group>
      <abstract>
        <p>Public PMC abstract text for synthetic backend interface testing.</p>
      </abstract>
    </article-meta>
  </front>
  <body>
    <sec>
      <title>Results</title>
      <p>Public PMC body text reports synthetic signaling evidence.</p>
      {extra}
    </sec>
  </body>
</article>
""",
        encoding="utf-8",
    )
    return fixture_dir


def run_ai_backend_triage(tmp_path, *extra_args, unsafe_record=None, unsafe_pmc_text=""):
    pubmed_fixture = write_synthetic_pubmed_fixture(tmp_path, unsafe_record=unsafe_record)
    pmc_fixture_dir = write_synthetic_pmc_fixture(tmp_path, unsafe_text=unsafe_pmc_text)
    output_root = tmp_path / "exports" / "pubmed_ai_triage"
    args = [
        sys.executable,
        str(SCRIPT),
        "--goal",
        "Synthetic public AI backend interface goal for kinase signaling.",
        "--topic-slug",
        "synthetic_public_ai_backend_interface",
        "--input-pubmed-json",
        str(pubmed_fixture),
        "--input-pmc-fixtures",
        str(pmc_fixture_dir),
        "--check-pmc-full-text",
        "--generate-full-text-drafts",
        "--pmc-top-n",
        "3",
        "--abstract-top-n",
        "1",
        "--output-root",
        str(output_root),
        "--timestamp",
        "20260526_160000",
        *extra_args,
    ]
    result = subprocess.run(
        args,
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )
    run_folder = output_root / "20260526_160000_synthetic_public_ai_backend_interface"
    return result, run_folder


def test_default_ai_backend_is_disabled_and_safe(tmp_path):
    result, run_folder = run_ai_backend_triage(tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    assert not (run_folder / "ai_backend").exists()
    manifest = json.loads((run_folder / "pubmed_triage_manifest.json").read_text(encoding="utf-8"))

    assert manifest["external_ai_backend_requested"] is False
    assert manifest["external_ai_backend_name"] == "disabled"
    assert manifest["external_ai_api_called"] is False
    assert manifest["external_ai_network_request_performed"] is False
    assert manifest["external_ai_api_key_used"] is False
    assert manifest["ai_public_only_gate_passed"] is False
    assert manifest["ai_prompt_packet_generated"] is False
    assert manifest["mock_ai_backend_used"] is False
    assert "notes: []" in (run_folder / "selected_notes.yaml").read_text(encoding="utf-8")


def test_mock_ai_backend_creates_labeled_deterministic_output(tmp_path):
    result, run_folder = run_ai_backend_triage(tmp_path, "--ai-backend", "mock")

    assert result.returncode == 0, result.stderr + result.stdout
    backend_dir = run_folder / "ai_backend"
    mock_response = json.loads((backend_dir / "mock_ai_response.json").read_text(encoding="utf-8"))
    backend_manifest = json.loads(
        (backend_dir / "ai_backend_manifest.json").read_text(encoding="utf-8")
    )
    main_manifest = json.loads((run_folder / "pubmed_triage_manifest.json").read_text(encoding="utf-8"))

    assert mock_response["label"] == "mock_ai_backend"
    assert mock_response["external_ai_result"] is False
    assert "not a real external AI result" in mock_response["notice"]
    assert backend_manifest["selected_backend_name"] == "mock"
    assert backend_manifest["backend_requested"] is True
    assert backend_manifest["public_only_gate_passed"] is True
    assert backend_manifest["mock_response_used"] is True
    assert backend_manifest["prompt_packet_generated"] is False
    assert backend_manifest["live_external_ai_api_call_attempted"] is False
    assert backend_manifest["network_ai_request_occurred"] is False
    assert backend_manifest["provider_specific_api_key_handling_occurred"] is False
    assert main_manifest["mock_ai_backend_used"] is True
    assert main_manifest["ai_backend_manifest_path"] == "ai_backend/ai_backend_manifest.json"


def test_prompt_packet_backend_exports_human_review_packet_only(tmp_path):
    result, run_folder = run_ai_backend_triage(tmp_path, "--ai-backend", "prompt_packet")

    assert result.returncode == 0, result.stderr + result.stdout
    packet = (run_folder / "ai_backend" / "AI_PROMPT_PACKET.md").read_text(encoding="utf-8")
    backend_manifest = json.loads(
        (run_folder / "ai_backend" / "ai_backend_manifest.json").read_text(encoding="utf-8")
    )

    assert "has not been sent to any external AI service" in packet
    assert "Human review is required" in packet
    assert "AI_SAFE.md" in packet
    assert "API keys" in packet
    assert "Synthetic public AI backend interface article" in packet
    assert backend_manifest["selected_backend_name"] == "prompt_packet"
    assert backend_manifest["prompt_packet_generated"] is True
    assert backend_manifest["mock_response_used"] is False
    assert backend_manifest["live_external_ai_api_call_succeeded"] is False
    assert backend_manifest["network_ai_request_occurred"] is False
    assert "pubmed_abstract_reviewed" in backend_manifest["input_read_depths_included"]
    assert "public_full_text_reviewed" in backend_manifest["input_read_depths_included"]
    assert "PubMed abstract" in backend_manifest["source_provenance_included"]
    assert "public PMC XML text" in backend_manifest["source_provenance_included"]


def test_public_only_gate_allows_synthetic_public_pubmed_and_pmc_fixtures(tmp_path):
    result, run_folder = run_ai_backend_triage(tmp_path, "--ai-backend", "prompt_packet")

    assert result.returncode == 0, result.stderr + result.stdout
    summary = (run_folder / "ai_backend" / "AI_BACKEND_INPUT_SUMMARY.md").read_text(encoding="utf-8")
    assert "public-only gate passed: `true`" in summary
    assert "network AI request occurred: `false`" in summary


def test_public_only_gate_blocks_unsafe_pubmed_fixture_markers(tmp_path):
    unsafe_cases = [
        {"source_url": "https://example.invalid/private"},
        {"abstract": "This fixture contains file:" + "//local/private.pdf"},
        {"abstract": "This fixture contains /" + "Users/example/secret-note.md"},
        {"abstract": "This fixture contains api_key marker text."},
        {"abstract": "This fixture is labeled private internal restricted."},
        {"abstract": "This fixture points to Papers/example.md"},
        {"abstract": "This fixture points to Indexes/PAPER_SOURCE_MAP.yaml"},
    ]
    for index, unsafe_record in enumerate(unsafe_cases):
        case_tmp = tmp_path / f"case_{index}"
        case_tmp.mkdir()
        result, _run_folder = run_ai_backend_triage(
            case_tmp,
            "--ai-backend",
            "prompt_packet",
            unsafe_record=unsafe_record,
        )

        assert result.returncode == 2
        assert "AI public-only gate blocked backend packet creation" in result.stdout


def test_public_only_gate_blocks_unsafe_pmc_fixture_markers(tmp_path):
    result, _run_folder = run_ai_backend_triage(
        tmp_path,
        "--ai-backend",
        "mock",
        unsafe_pmc_text="Bookends XML exported attachment path for a local paper PDF.",
    )

    assert result.returncode == 2
    assert "AI public-only gate blocked backend packet creation" in result.stdout


def test_unimplemented_live_external_backend_names_are_rejected_without_network(tmp_path):
    result, _run_folder = run_ai_backend_triage(tmp_path, "--ai-backend", "external_api")

    assert result.returncode != 0
    assert "live external AI backend `external_api` is not implemented" in result.stderr
