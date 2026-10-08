import importlib.util
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "run_triage.py"
SPEC = importlib.util.spec_from_file_location("run_pubmed_ai_triage", SCRIPT)
triage = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(triage)


def test_public_only_gate_allows_benign_public_pmc_xml_terms():
    public_pmc_text = """
    <article>
      <body>
        <sec><title>Results</title>
          <p>The public PMC XML discusses an internal ribosome entry site.</p>
          <p>Cells showed internalization and an internal control.</p>
          <p>The article page includes Download PDF, article PDF, and PDF version links.</p>
          <p>References include public citation labels and journal access text.</p>
        </sec>
      </body>
    </article>
    """

    assert triage.collect_ai_public_only_violations(public_pmc_text, "pmc_xml_PMCSYN") == []
    triage.assert_ai_public_only_gate([("pmc_xml_PMCSYN", public_pmc_text)])


@pytest.mark.parametrize(
    "public_bookends_text",
    [
        "bookends the response",
        "bookended by public evidence",
        "bookending the pathway",
        "This observation bookends the mechanism.",
        "The figure bookends the model.",
        "The article text says Bookends the response.",
    ],
)
def test_public_only_gate_allows_benign_bookends_prose(public_bookends_text):
    assert (
        triage.collect_ai_public_only_violations(public_bookends_text, "pmc_xml_PMCSYN")
        == []
    )
    triage.assert_ai_public_only_gate([("pmc_xml_PMCSYN", public_bookends_text)])


@pytest.mark.parametrize(
    ("unsafe_text", "expected_reason"),
    [
        ("/" + "Users/example/private.pdf", "local absolute path"),
        ("file:" + "//" + "/" + "Users/example/private.pdf", "local file URL"),
        ("source_url: https://example.invalid/private", "blocked metadata field"),
        ("Bookends/Attachments/private.pdf", "Bookends marker"),
        ("Bookends Attachments/private.pdf", "Bookends marker"),
        ("Bookends XML", "Bookends marker"),
        ("Bookends export", "Bookends marker"),
        ("Bookends attachment", "Bookends marker"),
        ("Bookends library", "Bookends marker"),
        ("Bookends database", "Bookends marker"),
        ("Bookends path", "Bookends marker"),
        ("Bookends PDF", "Bookends marker"),
        ("Bookends relative_path", "Bookends marker"),
        ("storage_alias: bookends", "Bookends marker"),
        ("bookends_attachment", "Bookends marker"),
        ("bookends_xml", "Bookends marker"),
        ("bookends_export", "Bookends marker"),
        ("Papers/example.md", "protected repository path"),
        ("Applications/example.md", "protected repository path"),
        ("Meeting_Notes/example.md", "protected repository path"),
        ("Collaborators/example.md", "protected repository path"),
        ("Grants/example.md", "protected repository path"),
        ("Indexes/PAPER_SOURCE_MAP.yaml", "protected paper source map"),
        ("OPENAI_API_KEY", "secret/token/API-key marker"),
        ("secret token", "secret/token/API-key marker"),
        ("private note", "private/confidential label"),
        ("internal lab note", "private/confidential label"),
        ("restricted material", "private/confidential label"),
        ("unpublished manuscript", "private/confidential label"),
        ("under review confidential draft", "private/confidential label"),
    ],
)
def test_public_only_gate_blocks_unsafe_markers_with_specific_reasons(
    unsafe_text, expected_reason
):
    violations = triage.collect_ai_public_only_violations(unsafe_text, "pmc_xml_PMCSYN")

    assert any(expected_reason in violation for violation in violations)
    with pytest.raises(
        triage.AIBackendPublicOnlyGateError,
        match="AI public-only gate blocked backend packet creation",
    ) as exc_info:
        triage.assert_ai_public_only_gate([("pmc_xml_PMCSYN", unsafe_text)])
    assert expected_reason in str(exc_info.value)
