from __future__ import annotations

import csv
import importlib.util
import json
import sys
import zipfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_pubmed_module():
    script_path = REPO_ROOT / "scripts" / "run_search.py"
    spec = importlib.util.spec_from_file_location("run_pubmed_search_for_tests", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_pubmed_search_writes_packet_csv_and_json(monkeypatch, tmp_path: Path) -> None:
    pubmed = load_pubmed_module()

    def fake_request_json(endpoint: str, params: dict[str, str], timeout: int = 30):
        if endpoint == "esearch.fcgi":
            assert params["db"] == "pubmed"
            assert params["term"] == "synthetic query"
            assert params["retmax"] == "2"
            assert params["sort"] == "relevance"
            return {"esearchresult": {"count": "42", "idlist": ["111", "222"]}}
        if endpoint == "esummary.fcgi":
            assert params["id"] == "111,222"
            return {
                "result": {
                    "uids": ["111", "222"],
                    "111": {
                        "title": "Synthetic PubMed Study One",
                        "fulljournalname": "Journal of Public Metadata",
                        "pubdate": "2025 Jan",
                    },
                    "222": {
                        "title": "Synthetic PubMed Study Two",
                        "source": "Metadata Letters",
                        "sortpubdate": "2024/06/01 00:00",
                    },
                }
            }
        raise AssertionError(endpoint)

    monkeypatch.setattr(pubmed, "request_json", fake_request_json)

    output_dir = pubmed.build_output(
        query="synthetic query",
        retmax=2,
        deep_read=1,
        topic_slug="Synthetic Topic!",
        sort="relevance",
        output_root=tmp_path / "exports" / "pubmed_search",
        timestamp="20260520_120000",
        retrieved_at="2026-05-20T12:00:00Z",
    )

    assert output_dir.name == "20260520_120000_Synthetic_Topic"
    packet_path = output_dir / "SEARCH_PACKET.md"
    csv_path = output_dir / "pubmed_results.csv"
    json_path = output_dir / "pubmed_results.json"
    assert packet_path.exists()
    assert csv_path.exists()
    assert json_path.exists()

    packet = packet_path.read_text(encoding="utf-8")
    assert "Original query: `synthetic query`" in packet
    assert "Total hit count: `42`" in packet
    assert "PMID order returned by PubMed: `111, 222`" in packet
    assert "`Full text reviewed` must not be used unless PMC, full text, or PDF content was actually read." in packet
    assert "external AI APIs" in packet

    with csv_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0] == {
        "rank": "1",
        "pmid": "111",
        "title": "Synthetic PubMed Study One",
        "year": "2025",
        "journal": "Journal of Public Metadata",
        "pubmed_url": "https://pubmed.ncbi.nlm.nih.gov/111/",
    }
    assert rows[1]["year"] == "2024"

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["search_config"]["database"] == "PubMed"
    assert payload["search_config"]["pmid_order"] == ["111", "222"]
    assert payload["safety"]["external_ai_api_calls"] == 0
    assert payload["safety"]["pdf_downloads"] == 0
    assert payload["results"][0]["pubmed_url"] == "https://pubmed.ncbi.nlm.nih.gov/111/"


def test_pubmed_search_writes_abstract_packet_doi_pmc_and_zip(monkeypatch, tmp_path: Path) -> None:
    pubmed = load_pubmed_module()

    def fake_request_json(endpoint: str, params: dict[str, str], timeout: int = 30):
        if endpoint == "esearch.fcgi":
            return {"esearchresult": {"count": "1", "idlist": ["333"]}}
        if endpoint == "esummary.fcgi":
            assert params["id"] == "333"
            return {
                "result": {
                    "uids": ["333"],
                    "333": {
                        "title": "Synthetic Abstract Study",
                        "fulljournalname": "Abstract Screening Journal",
                        "pubdate": "2026 Mar",
                    },
                }
            }
        raise AssertionError(endpoint)

    def fake_request_text(endpoint: str, params: dict[str, str], timeout: int = 30):
        assert endpoint == "efetch.fcgi"
        assert params["retmode"] == "xml"
        assert params["id"] == "333"
        return """<?xml version="1.0" encoding="UTF-8"?>
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation>
      <PMID>333</PMID>
      <Article>
        <AuthorList>
          <Author>
            <ForeName>Ada</ForeName>
            <LastName>Lovelace</LastName>
          </Author>
        </AuthorList>
        <Abstract>
          <AbstractText Label="Background">Synthetic background sentence.</AbstractText>
          <AbstractText Label="Results">Synthetic result sentence.</AbstractText>
        </Abstract>
        <ELocationID EIdType="doi">10.1234/synthetic.2026.001</ELocationID>
      </Article>
    </MedlineCitation>
    <PubmedData>
      <ArticleIdList>
        <ArticleId IdType="pubmed">333</ArticleId>
        <ArticleId IdType="doi">10.1234/synthetic.2026.001</ArticleId>
        <ArticleId IdType="pmc">PMC1234567</ArticleId>
      </ArticleIdList>
    </PubmedData>
  </PubmedArticle>
</PubmedArticleSet>
"""

    monkeypatch.setattr(pubmed, "request_json", fake_request_json)
    monkeypatch.setattr(pubmed, "request_text", fake_request_text)

    output_dir = pubmed.build_output(
        query="synthetic abstract query",
        retmax=1,
        deep_read=1,
        topic_slug="Abstract Topic",
        sort="relevance",
        output_root=tmp_path / "exports" / "pubmed_search",
        timestamp="20260520_130000",
        retrieved_at="2026-05-20T13:00:00Z",
        include_abstracts=True,
        include_pmc_links=True,
        include_doi=True,
        zip_output=True,
    )

    abstract_packet = output_dir / "ABSTRACT_SCREENING_PACKET.md"
    zip_path = output_dir / "pubmed_ai_handoff.zip"
    assert abstract_packet.exists()
    assert zip_path.exists()

    packet_text = abstract_packet.read_text(encoding="utf-8")
    assert "Original query: `synthetic abstract query`" in packet_text
    assert "Ada Lovelace" in packet_text
    assert "Background: Synthetic background sentence." in packet_text
    assert "DOI URL: https://doi.org/10.1234/synthetic.2026.001" in packet_text
    assert "PMCID: PMC1234567" in packet_text
    assert "PMC URL: https://pmc.ncbi.nlm.nih.gov/articles/PMC1234567/" in packet_text
    assert "`PubMed verified; abstract reviewed`" in packet_text
    assert "`Abstract reviewed; full text not available in this workflow`" in packet_text
    assert "`Full text not reviewed`" in packet_text
    assert "No PMC full text was fetched or parsed." in packet_text

    with (output_dir / "pubmed_results.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["abstract"] == "Background: Synthetic background sentence.\n\nResults: Synthetic result sentence."
    assert rows[0]["doi"] == "10.1234/synthetic.2026.001"
    assert rows[0]["doi_url"] == "https://doi.org/10.1234/synthetic.2026.001"
    assert rows[0]["pmcid"] == "PMC1234567"
    assert rows[0]["pmc_url"] == "https://pmc.ncbi.nlm.nih.gov/articles/PMC1234567/"
    assert rows[0]["pmc_availability"] == "PMC available"

    payload = json.loads((output_dir / "pubmed_results.json").read_text(encoding="utf-8"))
    assert payload["search_config"]["include_abstracts"] is True
    assert payload["search_config"]["include_pmc_links"] is True
    assert payload["search_config"]["include_doi"] is True
    assert payload["results"][0]["authors"] == ["Ada Lovelace"]

    with zipfile.ZipFile(zip_path) as archive:
        names = sorted(archive.namelist())
    assert names == [
        "ABSTRACT_SCREENING_PACKET.md",
        "SEARCH_PACKET.md",
        "pubmed_results.csv",
        "pubmed_results.json",
    ]
    assert all(not name.startswith("/") for name in names)


def test_pubmed_search_main_validates_arguments(capsys) -> None:
    pubmed = load_pubmed_module()

    exit_code = pubmed.main(
        [
            "--query",
            "synthetic query",
            "--retmax",
            "0",
            "--deep-read",
            "1",
            "--topic-slug",
            "bad",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "--retmax must be at least 1" in captured.err
