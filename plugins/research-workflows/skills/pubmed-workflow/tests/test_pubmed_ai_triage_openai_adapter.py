import importlib.util
import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "run_triage.py"
SPEC = importlib.util.spec_from_file_location("run_pubmed_ai_triage", SCRIPT)
triage = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(triage)


def write_pubmed_fixture(tmp_path, *, unsafe_record=None):
    record = {
        "pmid": "77777777",
        "title": "Synthetic public OpenAI adapter article",
        "authors": ["Ada Example"],
        "year": "2026",
        "journal": "Journal of Synthetic Public OpenAI Adapter Fixtures",
        "doi": "10.0000/synthetic.openai.adapter",
        "pmcid": "PMC7777777",
        "abstract": (
            "This synthetic public abstract discusses kinase signaling and "
            "cell-state regulation for OpenAI adapter testing."
        ),
    }
    if unsafe_record:
        record.update(unsafe_record)
    fixture = tmp_path / "synthetic_pubmed_results.json"
    fixture.write_text(json.dumps({"records": [record]}), encoding="utf-8")
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
        <article-title>Synthetic public OpenAI adapter article</article-title>
      </title-group>
      <abstract>
        <p>Public PMC abstract text for synthetic OpenAI adapter testing.</p>
      </abstract>
    </article-meta>
  </front>
  <body>
    <sec>
      <title>Results</title>
      <p>Public PMC body text reports synthetic signaling evidence.</p>
    </sec>
  </body>
</article>
""",
        encoding="utf-8",
    )
    return fixture_dir


def create_export(tmp_path, *, ai_backend="disabled", unsafe_record=None, **kwargs):
    return triage.create_triage_export(
        goal="Synthetic public OpenAI adapter goal for kinase signaling.",
        topic_slug="synthetic_public_openai_adapter",
        output_root=tmp_path / "exports" / "pubmed_ai_triage",
        timestamp="20260526_170000",
        retmax=5,
        abstract_top_n=1,
        full_text_top_n=1,
        query="",
        input_pubmed_json=write_pubmed_fixture(tmp_path, unsafe_record=unsafe_record),
        input_pmc_fixtures=write_pmc_fixture(tmp_path),
        check_pmc_full_text=True,
        generate_full_text_drafts=True,
        pmc_top_n=1,
        screening_backend="heuristic",
        ai_backend=ai_backend,
        allow_live_openai_api=kwargs.get("allow_live_openai_api", False),
        confirm_public_ai_export=kwargs.get("confirm_public_ai_export", False),
        openai_model=kwargs.get("openai_model", "gpt-5.5"),
        repo_root=tmp_path,
    )


def fail_if_network(*_args, **_kwargs):
    raise AssertionError("network request should not occur in this test")


class FakeOpenAIResponse:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        output_text = json.dumps(
            {
                "backend": "openai",
                "output_type": "pubmed_triage_suggestions",
                "candidate_updates": [
                    {
                        "pmid": "77777777",
                        "suggested_relevance": "high",
                        "reason": "Synthetic public abstract and PMC text mention kinase signaling.",
                        "read_depth_used": "public_full_text_reviewed",
                        "limitations": ["Synthetic fixture only."],
                    }
                ],
            }
        )
        return json.dumps({"id": "resp_synthetic", "output_text": output_text}).encode("utf-8")


def test_default_mode_does_not_lookup_openai_api_key_or_call_network(tmp_path, monkeypatch):
    monkeypatch.setattr(
        triage,
        "get_openai_api_key",
        lambda: (_ for _ in ()).throw(
            AssertionError("OPENAI_API_KEY should not be looked up by default")
        ),
    )
    monkeypatch.setattr(triage.urllib.request, "urlopen", fail_if_network)

    run_folder = create_export(tmp_path)

    assert not (run_folder / "ai_backend").exists()
    manifest = json.loads((run_folder / "pubmed_triage_manifest.json").read_text(encoding="utf-8"))
    assert manifest["external_ai_backend_requested"] is False
    assert manifest["external_ai_api_called"] is False
    assert manifest["external_ai_network_request_performed"] is False
    assert manifest["external_ai_api_key_used"] is False
    assert manifest["openai_model"] == ""
    assert "notes: []" in (run_folder / "selected_notes.yaml").read_text(encoding="utf-8")


def test_openai_without_live_opt_in_fails_before_network_or_key_lookup(tmp_path, monkeypatch):
    monkeypatch.setattr(
        triage,
        "get_openai_api_key",
        lambda: (_ for _ in ()).throw(
            AssertionError("OPENAI_API_KEY should not be looked up before live opt-in")
        ),
    )
    monkeypatch.setattr(triage.urllib.request, "urlopen", fail_if_network)

    with pytest.raises(ValueError, match="--allow-live-openai-api"):
        create_export(
            tmp_path,
            ai_backend="openai",
            confirm_public_ai_export=True,
        )


def test_openai_without_public_confirmation_fails_before_network_or_key_lookup(tmp_path, monkeypatch):
    monkeypatch.setattr(
        triage,
        "get_openai_api_key",
        lambda: (_ for _ in ()).throw(
            AssertionError("OPENAI_API_KEY should not be looked up before public confirmation")
        ),
    )
    monkeypatch.setattr(triage.urllib.request, "urlopen", fail_if_network)

    with pytest.raises(ValueError, match="--confirm-public-ai-export"):
        create_export(
            tmp_path,
            ai_backend="openai",
            allow_live_openai_api=True,
        )


def test_openai_missing_api_key_fails_before_request(tmp_path, monkeypatch):
    monkeypatch.setattr(triage, "get_openai_api_key", lambda: "")
    monkeypatch.setattr(triage.urllib.request, "urlopen", fail_if_network)

    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        create_export(
            tmp_path,
            ai_backend="openai",
            allow_live_openai_api=True,
            confirm_public_ai_export=True,
        )

    run_folder = tmp_path / "exports" / "pubmed_ai_triage" / "20260526_170000_synthetic_public_openai_adapter"
    assert not (run_folder / "ai_backend" / "OPENAI_REQUEST_REDACTED.json").exists()


def test_mocked_openai_response_is_parsed_and_logged_without_key(tmp_path, monkeypatch):
    secret_key = "sk-test-secret-value"
    captured = {}

    def fake_urlopen(request, timeout):
        captured["timeout"] = timeout
        captured["authorization"] = request.headers.get("Authorization")
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return FakeOpenAIResponse()

    monkeypatch.setattr(triage, "get_openai_api_key", lambda: secret_key)
    monkeypatch.setattr(triage.urllib.request, "urlopen", fake_urlopen)

    run_folder = create_export(
        tmp_path,
        ai_backend="openai",
        allow_live_openai_api=True,
        confirm_public_ai_export=True,
        openai_model="gpt-5.5",
    )
    backend_dir = run_folder / "ai_backend"
    request_log = (backend_dir / "OPENAI_REQUEST_REDACTED.json").read_text(encoding="utf-8")
    response = json.loads((backend_dir / "OPENAI_RESPONSE.json").read_text(encoding="utf-8"))
    backend_manifest = json.loads(
        (backend_dir / "ai_backend_manifest.json").read_text(encoding="utf-8")
    )
    main_manifest = json.loads((run_folder / "pubmed_triage_manifest.json").read_text(encoding="utf-8"))

    assert captured["authorization"] == f"Bearer {secret_key}"
    assert captured["timeout"] == 60
    assert captured["body"]["store"] is False
    assert "tools" not in captured["body"]
    assert secret_key not in request_log
    assert "Bearer <redacted>" in request_log
    assert response["external_ai_backend"] == "openai"
    assert response["external_ai_review_status"] == "ai_suggestion_needs_human_review"
    assert response["parsed_suggestions"]["candidate_updates"][0]["pmid"] == "77777777"
    assert backend_manifest["external_ai_api_called"] is True
    assert backend_manifest["external_ai_network_request_performed"] is True
    assert backend_manifest["external_ai_api_key_used"] is True
    assert backend_manifest["external_ai_api_key_logged"] is False
    assert backend_manifest["openai_model"] == "gpt-5.5"
    assert backend_manifest["openai_request_redacted_path"] == "ai_backend/OPENAI_REQUEST_REDACTED.json"
    assert backend_manifest["openai_response_path"] == "ai_backend/OPENAI_RESPONSE.json"
    assert backend_manifest["openai_response_summary_path"] == "ai_backend/OPENAI_RESPONSE_SUMMARY.md"
    assert backend_manifest["openai_store_false_requested"] is True
    assert backend_manifest["openai_tools_used"] == []
    assert backend_manifest["paper_notes_imported"] is False
    assert backend_manifest["papers_write_performed"] is False
    assert backend_manifest["git_actions_performed"] is False
    assert main_manifest["external_ai_api_called"] is True
    assert main_manifest["external_ai_network_request_performed"] is True
    assert main_manifest["external_ai_api_key_used"] is True
    assert main_manifest["external_ai_api_key_logged"] is False
    assert main_manifest["openai_tools_used"] == []
    assert "notes: []" in (run_folder / "selected_notes.yaml").read_text(encoding="utf-8")


def test_public_only_gate_blocks_unsafe_input_before_openai_request(tmp_path, monkeypatch):
    monkeypatch.setattr(triage, "get_openai_api_key", lambda: "sk-test-secret-value")
    monkeypatch.setattr(triage.urllib.request, "urlopen", fail_if_network)

    with pytest.raises(ValueError, match="AI public-only gate blocked backend packet creation"):
        create_export(
            tmp_path,
            ai_backend="openai",
            unsafe_record={"abstract": "This fixture includes /" + "Users/example/private-note.md"},
            allow_live_openai_api=True,
            confirm_public_ai_export=True,
        )

    run_folder = tmp_path / "exports" / "pubmed_ai_triage" / "20260526_170000_synthetic_public_openai_adapter"
    assert not (run_folder / "ai_backend" / "OPENAI_REQUEST_REDACTED.json").exists()
