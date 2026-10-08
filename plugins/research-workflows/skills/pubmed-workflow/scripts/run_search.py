#!/usr/bin/env python3
"""Retrieve public PubMed metadata and write an AI-readable search packet."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
DEFAULT_OUTPUT_ROOT = Path("exports/pubmed_search")
PUBMED_DATABASE = "PubMed"
PUBMED_URL_TEMPLATE = "https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
TOOL_NAME = "user-selected private workspace_pubmed_search"


def utc_timestamp_for_paths() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def utc_timestamp_for_display() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def sanitize_topic_slug(topic_slug: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", topic_slug.strip())
    slug = re.sub(r"_+", "_", slug).strip("._-")
    return slug or "pubmed_search"


def request_json(endpoint: str, params: dict[str, str], timeout: int = 30) -> dict[str, Any]:
    query = urllib.parse.urlencode(params)
    url = f"{EUTILS_BASE}/{endpoint}?{query}"
    request = urllib.request.Request(
        url,
        headers={"User-Agent": f"{TOOL_NAME}/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not retrieve PubMed metadata: {exc}") from exc
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError("NCBI E-utilities returned non-JSON content.") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("NCBI E-utilities returned an unexpected JSON structure.")
    return parsed


def request_text(endpoint: str, params: dict[str, str], timeout: int = 30) -> str:
    query = urllib.parse.urlencode(params)
    url = f"{EUTILS_BASE}/{endpoint}?{query}"
    request = urllib.request.Request(
        url,
        headers={"User-Agent": f"{TOOL_NAME}/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read().decode("utf-8")
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not retrieve PubMed metadata: {exc}") from exc


def search_pubmed(query: str, retmax: int, sort: str, timeout: int = 30) -> dict[str, Any]:
    params = {
        "db": "pubmed",
        "term": query,
        "retmax": str(retmax),
        "retmode": "json",
        "tool": TOOL_NAME,
        "sort": sort,
    }
    payload = request_json("esearch.fcgi", params, timeout=timeout)
    result = payload.get("esearchresult")
    if not isinstance(result, dict):
        raise RuntimeError("PubMed search response did not include esearchresult.")
    return result


def summarize_pubmed(pmids: list[str], timeout: int = 30) -> dict[str, Any]:
    if not pmids:
        return {"uids": []}
    params = {
        "db": "pubmed",
        "id": ",".join(pmids),
        "retmode": "json",
        "tool": TOOL_NAME,
    }
    payload = request_json("esummary.fcgi", params, timeout=timeout)
    result = payload.get("result")
    if not isinstance(result, dict):
        raise RuntimeError("PubMed summary response did not include result metadata.")
    return result


def fetch_pubmed_xml(pmids: list[str], timeout: int = 30) -> str:
    if not pmids:
        return ""
    params = {
        "db": "pubmed",
        "id": ",".join(pmids),
        "retmode": "xml",
        "tool": TOOL_NAME,
    }
    return request_text("efetch.fcgi", params, timeout=timeout)


def first_year(*values: object) -> str:
    for value in values:
        if not isinstance(value, str):
            continue
        match = re.search(r"\b(18|19|20|21)\d{2}\b", value)
        if match:
            return match.group(0)
    return ""


def normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def text_content(element: ET.Element) -> str:
    return normalize_whitespace(" ".join(text.strip() for text in element.itertext() if text.strip()))


def doi_url(doi: str) -> str:
    return f"https://doi.org/{doi}" if doi else ""


def pmc_url(pmcid: str) -> str:
    return f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/" if pmcid else ""


def parse_authors(article: ET.Element) -> list[str]:
    authors: list[str] = []
    for author in article.findall("./MedlineCitation/Article/AuthorList/Author"):
        collective = text_content(author.find("CollectiveName")) if author.find("CollectiveName") is not None else ""
        if collective:
            authors.append(collective)
            continue
        last = text_content(author.find("LastName")) if author.find("LastName") is not None else ""
        fore = text_content(author.find("ForeName")) if author.find("ForeName") is not None else ""
        initials = text_content(author.find("Initials")) if author.find("Initials") is not None else ""
        if last and fore:
            authors.append(f"{fore} {last}")
        elif last and initials:
            authors.append(f"{last} {initials}")
        elif last:
            authors.append(last)
    return authors


def parse_abstract(article: ET.Element) -> str:
    parts: list[str] = []
    for abstract_text in article.findall("./MedlineCitation/Article/Abstract/AbstractText"):
        label = abstract_text.attrib.get("Label", "").strip()
        text = text_content(abstract_text)
        if not text:
            continue
        parts.append(f"{label}: {text}" if label else text)
    return "\n\n".join(parts)


def parse_article_ids(article: ET.Element) -> tuple[str, str]:
    doi = ""
    pmcid = ""
    for article_id in article.findall("./PubmedData/ArticleIdList/ArticleId"):
        id_type = article_id.attrib.get("IdType", "").lower()
        value = text_content(article_id)
        if id_type == "doi" and value and not doi:
            doi = value
        if id_type == "pmc" and value and not pmcid:
            pmcid = value
    if not doi:
        for elocation in article.findall("./MedlineCitation/Article/ELocationID"):
            if elocation.attrib.get("EIdType", "").lower() == "doi":
                doi = text_content(elocation)
                if doi:
                    break
    return doi, pmcid


def parse_pubmed_xml(xml_text: str) -> dict[str, dict[str, Any]]:
    if not xml_text:
        return {}
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise RuntimeError("PubMed EFetch returned invalid XML.") from exc

    details: dict[str, dict[str, Any]] = {}
    for article in root.findall("./PubmedArticle"):
        pmid_element = article.find("./MedlineCitation/PMID")
        pmid = text_content(pmid_element) if pmid_element is not None else ""
        if not pmid:
            continue
        doi, pmcid = parse_article_ids(article)
        details[pmid] = {
            "authors": parse_authors(article),
            "abstract": parse_abstract(article),
            "doi": doi,
            "doi_url": doi_url(doi),
            "pmcid": pmcid,
            "pmc_url": pmc_url(pmcid),
            "pmc_availability": "PMC available" if pmcid else "No PMCID in PubMed metadata",
        }
    return details


def metadata_from_summary(pmids: list[str], summary: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for rank, pmid in enumerate(pmids, start=1):
        item = summary.get(pmid, {})
        if not isinstance(item, dict):
            item = {}
        title = str(item.get("title") or "").strip()
        journal = str(item.get("fulljournalname") or item.get("source") or "").strip()
        year = first_year(item.get("pubdate"), item.get("epubdate"), item.get("sortpubdate"))
        summary_authors = []
        for author in item.get("authors", []) if isinstance(item.get("authors"), list) else []:
            if isinstance(author, dict) and author.get("name"):
                summary_authors.append(str(author["name"]))
        rows.append(
            {
                "rank": rank,
                "pmid": pmid,
                "title": title,
                "year": year,
                "journal": journal,
                "authors": summary_authors,
                "pubmed_url": PUBMED_URL_TEMPLATE.format(pmid=pmid),
            }
        )
    return rows


def apply_pubmed_details(
    rows: list[dict[str, Any]],
    details: dict[str, dict[str, Any]],
    include_abstracts: bool,
    include_pmc_links: bool,
    include_doi: bool,
) -> list[dict[str, Any]]:
    for row in rows:
        detail = details.get(str(row.get("pmid")), {})
        if detail.get("authors"):
            row["authors"] = detail["authors"]
        if include_abstracts:
            row["abstract"] = detail.get("abstract", "")
        if include_doi:
            row["doi"] = detail.get("doi", "")
            row["doi_url"] = detail.get("doi_url", "")
        if include_pmc_links:
            row["pmcid"] = detail.get("pmcid", "")
            row["pmc_url"] = detail.get("pmc_url", "")
            row["pmc_availability"] = detail.get("pmc_availability", "No PMCID in PubMed metadata")
    return rows


def markdown_escape(value: object) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", " ").strip()


def render_metadata_table(rows: list[dict[str, Any]]) -> str:
    lines = [
        "| Rank | PMID | Year | Journal | Title |",
        "| ---: | --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            "| {rank} | [{pmid}]({url}) | {year} | {journal} | {title} |".format(
                rank=row["rank"],
                pmid=markdown_escape(row["pmid"]),
                url=row["pubmed_url"],
                year=markdown_escape(row["year"]),
                journal=markdown_escape(row["journal"]),
                title=markdown_escape(row["title"]),
            )
        )
    return "\n".join(lines)


def format_author_list(authors: object) -> str:
    if isinstance(authors, list):
        return ", ".join(str(author) for author in authors if author)
    return str(authors or "")


def render_search_packet(config: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    pmid_order = ", ".join(config["pmid_order"]) if config["pmid_order"] else "(no PMIDs returned)"
    top_n = min(config["retmax"], len(rows))
    deep_read = config["deep_read"]
    return f"""# PubMed Search Packet

## Search Configuration

- Original query: `{config["query"]}`
- Retrieval date/time: `{config["retrieved_at"]}`
- Database: `{PUBMED_DATABASE}`
- Sort mode: `{config["sort"]}`
- Requested `retmax`: `{config["retmax"]}`
- Requested `deep-read`: `{deep_read}`
- Total hit count: `{config["total_count"]}`
- PMID order returned by PubMed: `{pmid_order}`

## Metadata Table

{render_metadata_table(rows)}

## Read-Depth Definitions

- `PubMed verified`: PMID, title, year, and journal were retrieved from PubMed/NCBI metadata.
- `Abstract screened`: relevance was judged from PubMed metadata and public abstract-level context only.
- `Full text reviewed`: use this only when PMC, publisher full text, or PDF content was actually read.

## AI Screening Instructions

Use the PubMed metadata above as a candidate list, not as a claim of scientific importance.
Screen the top {top_n} papers for relevance to the original query. For each paper, classify relevance as high, medium, low, or unclear, and give a short evidence-grounded reason using only the provided PubMed metadata unless the human supplies additional public text.

Do not claim full-text, figure-level, methods-level, or supplementary-material review unless the human provides that content and asks you to analyze it.

## Deeper-Reading Selection Instructions

Choose up to {deep_read} papers for deeper reading. Prioritize papers that are most directly relevant, likely to answer the research question, or necessary to disambiguate competing interpretations. Explain why each selected paper should be read next and what evidence should be checked in the full text.

## Safety Notes

- PubMed Best Match top-N is a candidate list, not a ranking of scientific importance.
- AI may help judge relevance and support, but human scientific judgment remains primary.
- `PubMed verified` means PMID, title, year, and journal were retrieved from PubMed/NCBI.
- `Full text reviewed` must not be used unless PMC, full text, or PDF content was actually read.
- This packet used public PubMed metadata only. It did not download PDFs, access Bookends, modify `Papers/`, modify `Indexes/PAPER_SOURCE_MAP.yaml`, or call external AI APIs.

## Repo-Reflection Guidance

After human review, durable outputs may be saved manually in appropriate repository locations. Keep any durable note explicit about read depth, evidence source, and remaining uncertainty. Do not turn this generated packet into a permanent paper note without human review.
"""


def render_abstract_screening_packet(config: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    pmid_order = ", ".join(config["pmid_order"]) if config["pmid_order"] else "(no PMIDs returned)"
    top_n = min(config["retmax"], len(rows))
    record_blocks: list[str] = []
    for row in rows:
        abstract = str(row.get("abstract") or "").strip() or "Abstract not available in the retrieved PubMed metadata."
        doi = str(row.get("doi") or "").strip() or "Not available"
        doi_link = str(row.get("doi_url") or "").strip() or "Not available"
        pmcid = str(row.get("pmcid") or "").strip() or "Not available"
        pmc_link = str(row.get("pmc_url") or "").strip() or "Not available"
        pmc_availability = str(row.get("pmc_availability") or "").strip() or "No PMCID in PubMed metadata"
        record_blocks.append(
            f"""### {row["rank"]}. {row.get("title") or "(untitled)"}

- PMID: [{row["pmid"]}]({row["pubmed_url"]})
- Authors: {format_author_list(row.get("authors")) or "Not available"}
- Year: {row.get("year") or "Not available"}
- Journal: {row.get("journal") or "Not available"}
- DOI: {doi}
- DOI URL: {doi_link}
- PMCID: {pmcid}
- PMC URL: {pmc_link}
- PMC availability: {pmc_availability}
- Read-depth label: `PubMed verified; abstract reviewed`
- Full-text status: `Full text not reviewed`

Abstract:

{abstract}
"""
        )

    records = "\n".join(record_blocks) if record_blocks else "No PubMed records were returned."
    return f"""# PubMed Abstract Screening Packet

## Search Configuration

- Original query: `{config["query"]}`
- Topic slug: `{config["topic_slug"]}`
- Retrieval date/time: `{config["retrieved_at"]}`
- Database: `{PUBMED_DATABASE}`
- Sort mode: `{config["sort"]}`
- Requested `retmax`: `{config["retmax"]}`
- Requested `deep-read`: `{config["deep_read"]}`
- Total hit count: `{config["total_count"]}`
- PMID order returned by PubMed: `{pmid_order}`

## Source And Read-Depth Notes

This packet is derived from PubMed/NCBI metadata and abstracts. It is not a full-text review unless full text is explicitly supplied in a later workflow.

Use these labels carefully:

- `PubMed verified; abstract reviewed`: PMID and metadata came from PubMed/NCBI, and the abstract text in this packet may be screened.
- `Abstract reviewed; full text not available in this workflow`: abstract-level evidence was reviewed, but this script did not retrieve PMC full text, publisher full text, PDFs, figures, methods details, or supplements.
- `Full text not reviewed`: no full-text content was read in this workflow.

## AI Screening Instructions

Screen the top {top_n} PubMed records below for relevance to the original query. Select up to {config["deep_read"]} deep-reading candidates, but do not claim that these are the objectively top papers or that full text has been reviewed.

For each candidate, report:

- relevance: high, medium, low, or unclear
- evidence used from the provided abstract and metadata
- whether full text should be checked next
- the exact read-depth label used

Do not infer results beyond the supplied abstracts and metadata. Do not claim figure-level, methods-level, supplementary-material, or PDF review. PMCID and PMC URLs indicate availability metadata only; this workflow did not download or parse PMC full text.

## PubMed Records

{records}

## Safety Notes

- This packet used public PubMed/NCBI metadata and abstracts only.
- No PDFs were downloaded.
- No PMC full text was fetched or parsed.
- No Bookends files were accessed.
- No `Papers/` notes or `Indexes/PAPER_SOURCE_MAP.yaml` entries were modified.
- No external AI APIs were called.
"""


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = ["rank", "pmid", "title", "year", "journal"]
    if any(row.get("authors") for row in rows):
        fieldnames.append("authors")
    fieldnames.append("pubmed_url")
    optional_fields = ["abstract", "doi", "doi_url", "pmcid", "pmc_url", "pmc_availability"]
    for field in optional_fields:
        if any(field in row for row in rows):
            fieldnames.append(field)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    field: format_author_list(row.get(field)) if field == "authors" else row.get(field, "")
                    for field in fieldnames
                }
            )


def write_json(path: Path, config: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    payload = {
        "search_config": config,
        "results": rows,
        "safety": {
            "pdf_downloads": 0,
            "bookends_access": 0,
            "external_ai_api_calls": 0,
            "papers_directory_modifications": 0,
            "paper_source_map_modifications": 0,
        },
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_handoff_zip(path: Path, output_dir: Path, filenames: list[str]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for filename in filenames:
            source = output_dir / filename
            if source.exists():
                archive.write(source, arcname=filename)


def build_output(
    query: str,
    retmax: int,
    deep_read: int,
    topic_slug: str,
    sort: str,
    output_root: Path,
    timestamp: str | None = None,
    retrieved_at: str | None = None,
    timeout: int = 30,
    include_abstracts: bool = False,
    include_pmc_links: bool = False,
    include_doi: bool = False,
    zip_output: bool = False,
) -> Path:
    search_result = search_pubmed(query, retmax, sort, timeout=timeout)
    pmids = [str(pmid) for pmid in search_result.get("idlist", [])]
    total_count = str(search_result.get("count", "unknown"))
    summary = summarize_pubmed(pmids, timeout=timeout)
    rows = metadata_from_summary(pmids, summary)
    if include_abstracts or include_pmc_links or include_doi:
        details = parse_pubmed_xml(fetch_pubmed_xml(pmids, timeout=timeout))
        rows = apply_pubmed_details(rows, details, include_abstracts, include_pmc_links, include_doi)
    safe_slug = sanitize_topic_slug(topic_slug)
    output_dir = output_root / f"{timestamp or utc_timestamp_for_paths()}_{safe_slug}"
    output_dir.mkdir(parents=True, exist_ok=False)

    config = {
        "query": query,
        "retrieved_at": retrieved_at or utc_timestamp_for_display(),
        "database": PUBMED_DATABASE,
        "sort": sort,
        "retmax": retmax,
        "deep_read": deep_read,
        "topic_slug": safe_slug,
        "total_count": total_count,
        "pmid_order": pmids,
        "output_policy": "generated outputs only under exports/pubmed_search by default",
        "include_abstracts": include_abstracts,
        "include_pmc_links": include_pmc_links,
        "include_doi": include_doi,
        "zip_output": zip_output,
    }

    (output_dir / "SEARCH_PACKET.md").write_text(render_search_packet(config, rows), encoding="utf-8")
    generated_files = ["SEARCH_PACKET.md"]
    if include_abstracts:
        (output_dir / "ABSTRACT_SCREENING_PACKET.md").write_text(
            render_abstract_screening_packet(config, rows),
            encoding="utf-8",
        )
        generated_files.append("ABSTRACT_SCREENING_PACKET.md")
    write_csv(output_dir / "pubmed_results.csv", rows)
    generated_files.append("pubmed_results.csv")
    write_json(output_dir / "pubmed_results.json", config, rows)
    generated_files.append("pubmed_results.json")
    if zip_output:
        write_handoff_zip(output_dir / "pubmed_ai_handoff.zip", output_dir, generated_files)
    return output_dir


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Retrieve public PubMed metadata and generate an AI-readable search packet.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--query", required=True, help="PubMed query string.")
    parser.add_argument("--retmax", type=int, required=True, help="Maximum number of PubMed records to retrieve.")
    parser.add_argument("--deep-read", type=int, required=True, help="Number of papers to nominate for deeper reading.")
    parser.add_argument("--topic-slug", required=True, help="Short slug used in the output folder name.")
    parser.add_argument("--sort", default="relevance", help="PubMed ESearch sort mode.")
    parser.add_argument("--timeout", type=int, default=30, help="HTTP timeout in seconds.")
    parser.add_argument("--include-abstracts", action="store_true", help="Retrieve and include PubMed abstracts when available.")
    parser.add_argument("--include-pmc-links", action="store_true", help="Include PMCID and PMC article links from PubMed metadata.")
    parser.add_argument("--include-doi", action="store_true", help="Include DOI values and DOI links from PubMed metadata.")
    parser.add_argument("--zip-output", action="store_true", help="Create pubmed_ai_handoff.zip from safe generated workflow outputs.")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT, help=argparse.SUPPRESS)
    parser.add_argument("--timestamp", help=argparse.SUPPRESS)
    parser.add_argument("--retrieved-at", help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def validate_args(args: argparse.Namespace) -> None:
    if args.retmax < 1:
        raise ValueError("--retmax must be at least 1.")
    if args.deep_read < 0:
        raise ValueError("--deep-read must be 0 or greater.")
    if args.timeout < 1:
        raise ValueError("--timeout must be at least 1 second.")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        validate_args(args)
        output_dir = build_output(
            query=args.query,
            retmax=args.retmax,
            deep_read=args.deep_read,
            topic_slug=args.topic_slug,
            sort=args.sort,
            output_root=args.output_root,
            timestamp=args.timestamp,
            retrieved_at=args.retrieved_at,
            timeout=args.timeout,
            include_abstracts=args.include_abstracts,
            include_pmc_links=args.include_pmc_links,
            include_doi=args.include_doi,
            zip_output=args.zip_output,
        )
    except (RuntimeError, OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print("PubMed search packet generated")
    print(f"- output: {output_dir.as_posix()}")
    files = ["SEARCH_PACKET.md", "pubmed_results.csv", "pubmed_results.json"]
    if args.include_abstracts:
        files.insert(1, "ABSTRACT_SCREENING_PACKET.md")
    if args.zip_output:
        files.append("pubmed_ai_handoff.zip")
    print(f"- files: {', '.join(files)}")
    print("- external AI calls: 0")
    print("- PDF downloads: 0")
    print("- Bookends access: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
