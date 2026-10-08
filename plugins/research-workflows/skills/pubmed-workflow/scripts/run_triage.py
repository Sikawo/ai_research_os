#!/usr/bin/env python3
"""Run safe PubMed abstract/full-text triage exports.

This phase uses only public PubMed metadata and abstracts, or a synthetic JSON
fixture supplied by tests. It performs deterministic local screening and writes
abstract-only draft notes under exports/. When explicitly requested, it also
checks public PMC availability, exports public PMC XML/text evidence under
exports/, and can generate deterministic public PMC full-text draft notes from
that same exported XML/text. It intentionally performs no external AI API, PDF,
Bookends, Papers/, import, or Git actions.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
import urllib.parse
import urllib.request
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


WORKFLOW_NAME = "pubmed_ai_triage"
WORKFLOW_PHASE = "abstract_screening_drafts"
PMC_PHASE = "pmc_public_full_text_retrieval_export"
FULL_TEXT_DRAFT_PHASE = "public_pmc_full_text_draft_generation"
SKELETON_PHASE = "skeleton_export_only"
DEFAULT_OUTPUT_ROOT = Path("exports/pubmed_ai_triage")
PUBMED_SORT_MODES = ("best_match", "newest", "oldest")
PUBMED_ESEARCH_SORT = {
    "best_match": "relevance",
    "newest": "pub date",
    "oldest": "pub date",
}
SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$")
TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$")
WORD_RE = re.compile(r"[A-Za-z0-9]+")
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")
STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "in",
    "into",
    "is",
    "it",
    "of",
    "on",
    "or",
    "public",
    "relevant",
    "research",
    "the",
    "to",
    "with",
}
FORBIDDEN_REPO_INPUT_DIRS = (
    "Papers",
    "Applications",
    "Meeting_Notes",
    "Meetings",
    "Collaborators",
    "People",
    "Grants",
    "Hypothesis",
    "Manuscripts_Internal",
    "Indexes",
)
AI_BACKENDS = ("disabled", "heuristic", "mock", "prompt_packet", "openai")
LIVE_EXTERNAL_AI_BACKENDS = {"external_api", "chatgpt", "claude", "anthropic"}
OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
DEFAULT_OPENAI_MODEL = "gpt-5.5"
DEFAULT_OPENAI_MAX_OUTPUT_TOKENS = 1200
AI_BLOCKED_FIELD_NAMES = {"source" + "_url"}
LOCAL_FILE_URL_RE = r"\b" + "file" + r"://\S+"
SOURCE_URL_FIELD_RE = r"\bsource" + r"_url\b"
AI_PUBLIC_ONLY_STRUCTURAL_BLOCKED_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("local file URL", re.compile(LOCAL_FILE_URL_RE, re.IGNORECASE)),
    (
        "local absolute path",
        re.compile(r"(?<![A-Za-z0-9._-])/(Users|Volumes|private|tmp|var|etc|home)/[^\s<>\"]+"),
    ),
    ("blocked metadata field", re.compile(SOURCE_URL_FIELD_RE, re.IGNORECASE)),
    (
        "secret/token/API-key marker",
        re.compile(
            r"(?<![A-Za-z0-9])"
            r"((?:[A-Za-z0-9]+[_-])?"
            r"(?:api[_-]?key|secret|token|credential|private[_-]?key|access[_-]?key)"
            r"|bearer\s+[A-Za-z0-9._-]+)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "protected repository path",
        re.compile(
            r"(^|[\\/\s`\"'])"
            r"(Papers|Applications|Meeting_Notes|Meetings|Collaborators|People|Grants|Hypothesis|Manuscripts_Internal)"
            r"([\\/]|$)",
            re.IGNORECASE,
        ),
    ),
    (
        "protected paper source map",
        re.compile(r"Indexes[\\/]PAPER_SOURCE_MAP\.yaml", re.IGNORECASE),
    ),
    (
        "Bookends marker",
        re.compile(
            r"\bBookends\b\s*(?:[\\/]\s*)?Attachments?\b|"
            r"\bBookends\b\s+"
            r"(?:XML|exports?|attachments?|library|libraries|databases?|paths?|PDFs?|relative[_-]?paths?)\b|"
            r"\bstorage_alias\s*:\s*bookends\b|"
            r"\bbookends[_-]"
            r"(?:attachments?|xml|exports?|library|libraries|databases?|paths?|pdfs?|relative[_-]?paths?)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "local PDF path",
        re.compile(
            r"(?<![A-Za-z0-9._:/-])"
            r"(?:~[\\/]|\.{1,2}[\\/]|[A-Za-z]:[\\/]|(?:[A-Za-z0-9._ -]+[\\/])+)"
            r"[^\s<>\"]+\.pdf\b",
            re.IGNORECASE,
        ),
    ),
    ("local PDF reference", re.compile(r"\blocal\s+(?:paper\s+)?PDFs?\b", re.IGNORECASE)),
    (
        "protected data marker",
        re.compile(
            r"\b(raw|microscopy|sequencing|instrument)\s+"
            r"(data|output|outputs|export|exports|path|paths|folder|folders|file|files)\b",
            re.IGNORECASE,
        ),
    ),
)
AI_PUBLIC_ONLY_CONTEXTUAL_LABEL_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "private/confidential label",
        re.compile(
            r"\b("
            r"restricted_internal_full_text|"
            r"private\s+(?:note|lab|repository|repo|data|material|source|draft|record|file|content)|"
            r"internal\s+(?:lab|repository|repo|research|confidential|restricted|private)\s+"
            r"(?:note|data|material|source|draft|record|file|content)?|"
            r"private\s+internal\s+restricted|"
            r"restricted\s+(?:material|note|data|content|access|source|record|draft|file)|"
            r"unpublished\s+(?:manuscript|draft|paper|data|result|results|work)|"
            r"under\s+review|"
            r"confidential|"
            r"do\s+not\s+share"
            r")\b",
            re.IGNORECASE,
        ),
    ),
)


class AIBackendPublicOnlyGateError(ValueError):
    """Raised when backend packet inputs fail the conservative public-only gate."""


def positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return parsed


def nonnegative_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be at least 0")
    return parsed


def validate_topic_slug(topic_slug: str) -> str:
    if not SLUG_RE.fullmatch(topic_slug):
        raise argparse.ArgumentTypeError(
            "topic slug must be 1-80 characters using only letters, digits, "
            "underscores, or hyphens, and must start with a letter or digit"
        )
    return topic_slug


def validate_timestamp(timestamp: str) -> str:
    if not TOKEN_RE.fullmatch(timestamp):
        raise argparse.ArgumentTypeError(
            "timestamp must be 1-80 safe characters and must not contain spaces "
            "or path separators"
        )
    return timestamp


def validate_goal(goal: str) -> str:
    stripped = goal.strip()
    if not stripped:
        raise argparse.ArgumentTypeError("goal must not be blank")
    return stripped


def validate_ai_backend(value: str) -> str:
    backend = value.strip().lower()
    if backend in LIVE_EXTERNAL_AI_BACKENDS:
        raise argparse.ArgumentTypeError(
            f"live external AI backend `{backend}` is not implemented in this phase; "
            "use disabled, heuristic, mock, prompt_packet, or openai"
        )
    if backend not in AI_BACKENDS:
        raise argparse.ArgumentTypeError(
            "AI backend must be disabled, heuristic, mock, prompt_packet, or openai"
        )
    return backend


def validate_pubmed_sort(value: str) -> str:
    sort_mode = value.strip().lower().replace("-", "_")
    if sort_mode not in PUBMED_SORT_MODES:
        raise argparse.ArgumentTypeError(
            "PubMed sort must be one of: best_match, newest, oldest"
        )
    return sort_mode


def validate_openai_model(value: str) -> str:
    model = value.strip()
    if not model:
        raise argparse.ArgumentTypeError("OpenAI model must not be blank")
    if not TOKEN_RE.fullmatch(model):
        raise argparse.ArgumentTypeError(
            "OpenAI model must use only safe token characters and must not contain spaces"
        )
    return model


def get_openai_api_key() -> str:
    return os.environ.get("OPENAI_API_KEY", "")


def default_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def ensure_safe_output_root(output_root: Path, repo_root: Path) -> Path:
    resolved = output_root.expanduser().resolve()
    papers_root = (repo_root / "Papers").resolve()
    if resolved == papers_root or is_relative_to(resolved, papers_root):
        raise ValueError("output root must not be Papers/ or inside Papers/")
    allowed_root = (repo_root / DEFAULT_OUTPUT_ROOT).resolve()
    if resolved != allowed_root and not is_relative_to(resolved, allowed_root):
        raise ValueError("output root must be exports/pubmed_ai_triage/ or inside it")
    return resolved


def ensure_safe_input_json(input_path: Path, repo_root: Path) -> Path:
    resolved = input_path.expanduser().resolve()
    if resolved.suffix.lower() != ".json":
        raise ValueError("--input-pubmed-json must point to a JSON file")
    ensure_not_protected_repo_input(resolved, repo_root, "--input-pubmed-json")
    return resolved


def ensure_not_protected_repo_input(resolved: Path, repo_root: Path, option_name: str) -> None:
    for dirname in FORBIDDEN_REPO_INPUT_DIRS:
        protected_root = (repo_root / dirname).resolve()
        if resolved == protected_root or is_relative_to(resolved, protected_root):
            raise ValueError(f"{option_name} must not read from {dirname}/")


def ensure_safe_pmc_fixture_dir(input_path: Path, repo_root: Path) -> Path:
    resolved = input_path.expanduser().resolve()
    ensure_not_protected_repo_input(resolved, repo_root, "--input-pmc-fixtures")
    if not resolved.is_dir():
        raise ValueError("--input-pmc-fixtures must point to a directory")
    return resolved


def tokens(text: str) -> set[str]:
    return {
        token.lower()
        for token in WORD_RE.findall(text)
        if len(token) > 2 and token.lower() not in STOPWORDS
    }


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", html.unescape(str(value))).strip()


def collect_ai_public_only_violations(value: Any, label: str) -> list[str]:
    violations: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key)
            if key_text.lower() in AI_BLOCKED_FIELD_NAMES:
                violations.append(f"{label}.{key_text}: blocked metadata field")
            violations.extend(collect_ai_public_only_violations(item, f"{label}.{key_text}"))
        return violations
    if isinstance(value, list):
        for index, item in enumerate(value):
            violations.extend(collect_ai_public_only_violations(item, f"{label}[{index}]"))
        return violations
    if value is None or isinstance(value, (bool, int, float)):
        return violations

    text = str(value)
    for reason, pattern in (
        AI_PUBLIC_ONLY_STRUCTURAL_BLOCKED_PATTERNS
        + AI_PUBLIC_ONLY_CONTEXTUAL_LABEL_PATTERNS
    ):
        if pattern.search(text):
            violations.append(f"{label}: {reason}")
    return violations


def assert_ai_public_only_gate(named_values: list[tuple[str, Any]]) -> None:
    violations: list[str] = []
    for label, value in named_values:
        violations.extend(collect_ai_public_only_violations(value, label))
    if violations:
        details = "; ".join(violations[:5])
        raise AIBackendPublicOnlyGateError(
            f"AI public-only gate blocked backend packet creation: {details}"
        )


def yaml_quote(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def note_slug(value: str, fallback: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", value.lower()).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    return (slug or fallback)[:72]


def first_present(record: dict[str, Any], names: tuple[str, ...]) -> Any:
    for name in names:
        if name in record and record[name] not in (None, ""):
            return record[name]
    return ""


def normalize_authors(value: Any) -> list[str]:
    if isinstance(value, list):
        authors: list[str] = []
        for item in value:
            if isinstance(item, dict):
                name = clean_text(
                    item.get("name")
                    or " ".join(
                        part
                        for part in (item.get("fore_name"), item.get("last_name"))
                        if part
                    )
                )
            else:
                name = clean_text(item)
            if name:
                authors.append(name)
        return authors
    text = clean_text(value)
    if not text:
        return []
    return [part.strip() for part in re.split(r"\s*;\s*", text) if part.strip()]


def normalize_pubmed_record(record: dict[str, Any]) -> dict[str, Any]:
    pmid = clean_text(first_present(record, ("pmid", "PMID", "uid", "id")))
    title = clean_text(first_present(record, ("title", "Title", "article_title")))
    abstract = clean_text(first_present(record, ("abstract", "Abstract", "abstract_text")))
    journal = clean_text(first_present(record, ("journal", "Journal", "source")))
    year = clean_text(first_present(record, ("year", "Year", "pub_year", "publication_year")))
    doi = clean_text(first_present(record, ("doi", "DOI")))
    pmcid = clean_text(first_present(record, ("pmcid", "PMCID")))
    authors = normalize_authors(first_present(record, ("authors", "Authors", "author_list")))
    return {
        "pmid": pmid,
        "title": title,
        "abstract": abstract,
        "authors": authors,
        "year": year,
        "journal": journal,
        "doi": doi,
        "pmcid": pmcid,
    }


def load_pubmed_json(
    path: Path,
    repo_root: Path,
    *,
    ai_public_only_gate_requested: bool = False,
) -> list[dict[str, Any]]:
    safe_path = ensure_safe_input_json(path, repo_root)
    data = json.loads(safe_path.read_text(encoding="utf-8"))
    if ai_public_only_gate_requested:
        assert_ai_public_only_gate([("input_pubmed_json", data)])
    if isinstance(data, list):
        raw_records = data
    elif isinstance(data, dict):
        raw_records = (
            data.get("records")
            or data.get("results")
            or data.get("pubmed_results")
            or data.get("articles")
            or []
        )
    else:
        raise ValueError("PubMed input JSON must be a list or mapping with records")
    if not isinstance(raw_records, list):
        raise ValueError("PubMed input JSON records must be a list")
    records = [normalize_pubmed_record(item) for item in raw_records if isinstance(item, dict)]
    return [record for record in records if record["pmid"] or record["title"]]


def pubmed_record_sort_year(record: dict[str, Any]) -> int:
    year_match = re.search(r"\b(19|20)\d{2}\b", clean_text(record.get("year")))
    return int(year_match.group(0)) if year_match else 0


def sort_pubmed_records(records: list[dict[str, Any]], sort_mode: str) -> list[dict[str, Any]]:
    if sort_mode == "newest":
        return sorted(
            records,
            key=lambda record: (
                pubmed_record_sort_year(record),
                clean_text(record.get("pmid")),
                clean_text(record.get("title")),
            ),
            reverse=True,
        )
    if sort_mode == "oldest":
        return sorted(
            records,
            key=lambda record: (
                pubmed_record_sort_year(record) or 9999,
                clean_text(record.get("pmid")),
                clean_text(record.get("title")),
            ),
        )
    return records


def fetch_pubmed_records(query: str, retmax: int, sort_mode: str) -> list[dict[str, Any]]:
    if sort_mode not in PUBMED_ESEARCH_SORT:
        raise ValueError(f"unsupported PubMed sort mode: {sort_mode}")
    params = urllib.parse.urlencode(
        {
            "db": "pubmed",
            "term": query,
            "retmax": str(retmax),
            "retmode": "json",
            "sort": PUBMED_ESEARCH_SORT[sort_mode],
        }
    )
    search_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?{params}"
    with urllib.request.urlopen(search_url, timeout=30) as response:
        search_data = json.loads(response.read().decode("utf-8"))
    id_list = search_data.get("esearchresult", {}).get("idlist", [])
    if not id_list:
        return []

    fetch_params = urllib.parse.urlencode(
        {
            "db": "pubmed",
            "id": ",".join(id_list),
            "retmode": "xml",
        }
    )
    fetch_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?{fetch_params}"
    with urllib.request.urlopen(fetch_url, timeout=30) as response:
        xml_text = response.read().decode("utf-8")
    return sort_pubmed_records(parse_pubmed_xml(xml_text), sort_mode)


def element_text(element: ET.Element | None) -> str:
    if element is None:
        return ""
    return clean_text(" ".join(element.itertext()))


def parse_pubmed_xml(xml_text: str) -> list[dict[str, Any]]:
    root = ET.fromstring(xml_text)
    records: list[dict[str, Any]] = []
    for article in root.findall(".//PubmedArticle"):
        pmid = element_text(article.find(".//MedlineCitation/PMID"))
        title = element_text(article.find(".//ArticleTitle"))
        abstract = clean_text(
            " ".join(element_text(node) for node in article.findall(".//Abstract/AbstractText"))
        )
        journal = element_text(article.find(".//Journal/Title"))
        year = element_text(article.find(".//PubDate/Year"))
        if not year:
            medline_date = element_text(article.find(".//PubDate/MedlineDate"))
            year_match = re.search(r"\b(19|20)\d{2}\b", medline_date)
            year = year_match.group(0) if year_match else ""
        authors = []
        for author in article.findall(".//AuthorList/Author"):
            fore_name = element_text(author.find("ForeName"))
            last_name = element_text(author.find("LastName"))
            collective = element_text(author.find("CollectiveName"))
            name = clean_text(" ".join(part for part in (fore_name, last_name) if part))
            authors.append(collective or name)
        doi = ""
        pmcid = ""
        for article_id in article.findall(".//PubmedData/ArticleIdList/ArticleId"):
            id_type = article_id.attrib.get("IdType", "").lower()
            id_text = element_text(article_id)
            if id_type == "doi":
                doi = id_text
            elif id_type == "pmc":
                pmcid = id_text
        records.append(
            {
                "pmid": pmid,
                "title": title,
                "abstract": abstract,
                "authors": [author for author in authors if author],
                "year": year,
                "journal": journal,
                "doi": doi,
                "pmcid": pmcid,
            }
        )
    return records


def relevance_label(score: float) -> str:
    if score >= 60:
        return "high"
    if score >= 30:
        return "medium"
    if score > 0:
        return "low"
    return "unclear"


def screen_records(
    records: list[dict[str, Any]],
    *,
    goal: str,
    query: str,
    backend: str,
) -> list[dict[str, Any]]:
    goal_terms = tokens(goal + " " + query)
    screened: list[dict[str, Any]] = []
    for index, record in enumerate(records):
        text_terms = tokens(f"{record.get('title', '')} {record.get('abstract', '')}")
        overlap = sorted(goal_terms & text_terms)
        abstract = clean_text(record.get("abstract"))
        title = clean_text(record.get("title"))
        if backend == "mock":
            score = max(0.0, 100.0 - index * 10.0)
            reason = "Mock screening backend assigned deterministic rank-order score."
        else:
            denominator = max(len(goal_terms), 1)
            overlap_score = min(100.0, (len(overlap) / denominator) * 100.0)
            abstract_bonus = 10.0 if abstract else 0.0
            score = round(min(100.0, overlap_score + abstract_bonus), 2)
            if overlap:
                reason = (
                    "Local heuristic found title/abstract keyword overlap with: "
                    + ", ".join(overlap[:8])
                    + "."
                )
            else:
                reason = "Local heuristic found no clear title/abstract keyword overlap."
        screened.append(
            {
                "pmid": clean_text(record.get("pmid")),
                "title": title,
                "year": clean_text(record.get("year")),
                "journal": clean_text(record.get("journal")),
                "doi": clean_text(record.get("doi")),
                "pmcid": clean_text(record.get("pmcid")),
                "score": score,
                "relevance_label": relevance_label(score),
                "screening_backend": backend,
                "read_depth": "abstract",
                "support_evidence_limitations": (
                    "Screened only PubMed metadata and abstract text; no full text, "
                    "figures, supplements, PDFs, Bookends records, or private notes were reviewed."
                ),
                "reason": reason,
                "abstract_available": bool(abstract),
            }
        )
    return sorted(screened, key=lambda item: (-float(item["score"]), item["pmid"], item["title"]))


def concise_abstract_summary(abstract: str) -> str:
    abstract = clean_text(abstract)
    if not abstract:
        return "No abstract text was available in the PubMed metadata for this record."
    sentences = [sentence.strip() for sentence in SENTENCE_RE.split(abstract) if sentence.strip()]
    summary = " ".join(sentences[:2]) if sentences else abstract
    return textwrap.shorten(summary, width=700, placeholder="...")


def write_pubmed_results(run_folder: Path, records: list[dict[str, Any]]) -> None:
    (run_folder / "pubmed_results.json").write_text(
        json.dumps({"records": records}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with (run_folder / "pubmed_results.csv").open("w", encoding="utf-8", newline="") as handle:
        fieldnames = ("pmid", "title", "year", "journal", "doi", "pmcid", "abstract")
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            writer.writerow({field: record.get(field, "") for field in fieldnames})


def safe_pmcid_token(pmcid: str) -> str:
    token = clean_text(pmcid).upper()
    if token.startswith("PMC"):
        token = "PMC" + re.sub(r"[^0-9]", "", token[3:])
    else:
        token = re.sub(r"[^A-Z0-9_-]", "", token)
    return token[:80]


def pmcid_numeric_id(pmcid: str) -> str:
    token = clean_text(pmcid).upper()
    if token.startswith("PMC"):
        token = token[3:]
    token = re.sub(r"[^0-9]", "", token)
    if not token:
        raise ValueError(f"PMCID has no numeric PMC identifier: {pmcid}")
    return token


def load_pmc_fixture_xml(pmcid: str, fixture_dir: Path) -> str | None:
    token = safe_pmcid_token(pmcid)
    candidates = [
        fixture_dir / f"{token}.xml",
        fixture_dir / f"{token.lower()}.xml",
        fixture_dir / f"{pmcid_numeric_id(token)}.xml",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate.read_text(encoding="utf-8")
    return None


def fetch_pmc_xml(pmcid: str) -> str:
    params = urllib.parse.urlencode(
        {
            "db": "pmc",
            "id": pmcid_numeric_id(pmcid),
            "retmode": "xml",
        }
    )
    url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?{params}"
    with urllib.request.urlopen(url, timeout=30) as response:
        return response.read().decode("utf-8")


def local_name(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def descendants_by_name(element: ET.Element, name: str) -> list[ET.Element]:
    return [node for node in element.iter() if local_name(node) == name]


def first_descendant_text(element: ET.Element, name: str) -> str:
    for node in descendants_by_name(element, name):
        text = element_text(node)
        if text:
            return text
    return ""


def extract_public_pmc_text(xml_text: str, pmcid: str) -> str:
    root = ET.fromstring(xml_text)
    title = first_descendant_text(root, "article-title")
    lines = [
        "# Public PMC XML Text Export",
        "",
        f"PMCID: {pmcid}",
        "Source: public PMC XML.",
        (
            "Limitations: extracted plain text only from public PMC XML. No PDFs, "
            "supplementary files, OCR, publisher full text, Bookends records, or "
            "private repository notes were read."
        ),
        "",
    ]
    if title:
        lines.extend(["## Article Title", "", title, ""])

    abstracts = descendants_by_name(root, "abstract")
    if abstracts:
        lines.extend(["## Abstract", ""])
        for abstract in abstracts:
            abstract_title = first_descendant_text(abstract, "title")
            if abstract_title:
                lines.append(f"### {abstract_title}")
            paragraphs = [element_text(node) for node in descendants_by_name(abstract, "p")]
            if paragraphs:
                lines.extend(text for text in paragraphs if text)
            else:
                text = element_text(abstract)
                if text:
                    lines.append(text)
        lines.append("")

    bodies = descendants_by_name(root, "body")
    if bodies:
        lines.extend(["## Body Text", ""])
        for body in bodies:
            for node in body.iter():
                node_name = local_name(node)
                text = element_text(node)
                if not text:
                    continue
                if node_name == "title":
                    lines.extend([f"### {text}", ""])
                elif node_name == "p":
                    lines.extend([text, ""])

    captions: list[str] = []
    for fig in descendants_by_name(root, "fig"):
        for caption in descendants_by_name(fig, "caption"):
            text = element_text(caption)
            if text:
                captions.append(text)
    if captions:
        lines.extend(["## Figure Captions From Public XML", ""])
        for caption in captions:
            lines.extend([caption, ""])

    text = "\n".join(lines).strip() + "\n"
    return text


def build_pmc_readme() -> str:
    return """# PMC Public Full-Text Exports

This folder contains temporary review artifacts generated from public PMC XML.
XML files are stored under `xml/`, and conservative plain-text exports are
stored under `text/`.

These files are not full-text Markdown paper-note drafts. Phase 3a only checks
PMC availability and exports public XML/text evidence for later review. Phase 3b
is reserved for full-text Markdown draft generation from public PMC content.

No PDFs, supplementary files, publisher full text outside PMC, Bookends records,
private notes, `Papers/` files, or external AI APIs are used here.
"""


def safe_note_text(value: str, *, width: int = 900) -> str:
    text = clean_text(value)
    local_file_scheme = "file:" + "//"
    source_key = "source" + "_" + "url"
    text = re.sub(
        re.escape(local_file_scheme) + r"\S+",
        "[local file link removed]",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub("/" + r"Users/[^\s)]+", "[local path removed]", text)
    text = re.sub(rf"\b{source_key}\b", "source url", text, flags=re.IGNORECASE)
    text = re.sub(r"\brestricted_internal_full_text\b", "nonpublic full text label removed", text)
    text = re.sub(r"\b(private|internal|restricted)\b", "nonpublic", text, flags=re.IGNORECASE)
    if width > 0:
        text = textwrap.shorten(text, width=width, placeholder="...")
    return text


def text_sentences(value: str, limit: int, *, width: int = 900) -> list[str]:
    sentences = [safe_note_text(sentence, width=width) for sentence in SENTENCE_RE.split(value)]
    return [sentence for sentence in sentences if sentence][:limit]


def direct_child_texts(element: ET.Element, name: str) -> list[str]:
    texts: list[str] = []
    for child in list(element):
        if local_name(child) == name:
            text = element_text(child)
            if text:
                texts.append(text)
    return texts


def section_title(section: ET.Element) -> str:
    for child in list(section):
        if local_name(child) == "title":
            return element_text(child)
    return ""


def extract_pmc_draft_evidence(xml_text: str, text_export: str) -> dict[str, Any]:
    root = ET.fromstring(xml_text)
    abstract_text = " ".join(element_text(node) for node in descendants_by_name(root, "abstract"))
    body_paragraph_text = " ".join(
        element_text(node)
        for body in descendants_by_name(root, "body")
        for node in descendants_by_name(body, "p")
    )
    body_sentences = text_sentences(body_paragraph_text or text_export, 5)
    summary_source = abstract_text or text_export
    summary = " ".join(text_sentences(summary_source, 3, width=450))
    if not summary:
        summary = "Public PMC XML/text was exported, but no concise sentence-level summary was extracted."

    section_bullets: list[dict[str, str]] = []
    methods_bullets: list[str] = []
    for body in descendants_by_name(root, "body"):
        for section in descendants_by_name(body, "sec"):
            title = section_title(section) or "Untitled public XML section"
            paragraphs = direct_child_texts(section, "p")
            if not paragraphs:
                paragraphs = [
                    element_text(node)
                    for node in descendants_by_name(section, "p")[:2]
                    if element_text(node)
                ]
            if not paragraphs:
                continue
            bullet = safe_note_text(" ".join(paragraphs[:2]), width=700)
            section_bullets.append({"title": safe_note_text(title, width=120), "text": bullet})
            title_lower = title.lower()
            paragraph_lower = " ".join(paragraphs).lower()
            if (
                "method" in title_lower
                or "material" in title_lower
                or "control" in title_lower
                or "control" in paragraph_lower
            ):
                methods_bullets.append(bullet)
            if len(section_bullets) >= 8:
                break
        if len(section_bullets) >= 8:
            break

    captions: list[str] = []
    for fig in descendants_by_name(root, "fig"):
        for caption in descendants_by_name(fig, "caption"):
            text = safe_note_text(element_text(caption), width=700)
            if text:
                captions.append(text)
        if len(captions) >= 5:
            break

    return {
        "summary": summary,
        "abstract_sentences": text_sentences(abstract_text, 3, width=500),
        "body_sentences": body_sentences,
        "section_bullets": section_bullets[:8],
        "methods_bullets": methods_bullets[:5],
        "figure_captions": captions[:5],
    }


def select_pmc_candidates(
    records: list[dict[str, Any]],
    screening_results: list[dict[str, Any]],
    pmc_top_n: int,
) -> list[tuple[dict[str, Any], dict[str, Any] | None]]:
    if pmc_top_n <= 0:
        return []
    record_by_pmid = {clean_text(record.get("pmid")): record for record in records}
    candidates: list[tuple[dict[str, Any], dict[str, Any] | None]] = []
    if screening_results:
        for screening in screening_results[:pmc_top_n]:
            record = record_by_pmid.get(clean_text(screening.get("pmid")))
            if record is not None:
                candidates.append((record, screening))
        return candidates
    return [(record, None) for record in records[:pmc_top_n]]


def write_pmc_availability_exports(
    *,
    run_folder: Path,
    records: list[dict[str, Any]],
    screening_results: list[dict[str, Any]],
    pmc_top_n: int,
    fixture_dir: Path | None,
    ai_public_only_gate_requested: bool,
) -> list[dict[str, Any]]:
    pmc_root = run_folder / "pmc_full_text"
    xml_folder = pmc_root / "xml"
    text_folder = pmc_root / "text"
    xml_folder.mkdir(parents=True, exist_ok=True)
    text_folder.mkdir(parents=True, exist_ok=True)
    (pmc_root / "README.md").write_text(build_pmc_readme(), encoding="utf-8")

    results: list[dict[str, Any]] = []
    for record, screening in select_pmc_candidates(records, screening_results, pmc_top_n):
        pmcid = clean_text(record.get("pmcid"))
        result: dict[str, Any] = {
            "pmid": clean_text(record.get("pmid")),
            "pmcid": pmcid,
            "title": clean_text(record.get("title")),
            "year": clean_text(record.get("year")),
            "journal": clean_text(record.get("journal")),
            "doi": clean_text(record.get("doi")),
            "abstract_screening_score": screening.get("score") if screening else None,
            "abstract_relevance_label": screening.get("relevance_label") if screening else "",
            "pmcid_present": bool(pmcid),
            "pmc_retrieval_attempted": False,
            "pmc_retrieval_succeeded": False,
            "pmc_text_extracted": False,
            "full_text_note_draft_generated": False,
            "pmc_availability_status": "pmc_not_available",
            "public_retrieval_source": "not_attempted",
            "local_xml_export_path": "",
            "local_text_export_path": "",
            "generated_full_text_note_path": "",
            "text_character_count": 0,
            "limitations": [
                "PMC evidence is limited to public PMC XML/text.",
                "Full-text Markdown note drafts are generated only when explicitly requested.",
            ],
            "warnings": [],
        }
        if not pmcid:
            result["warnings"].append("No PMCID was present in PubMed metadata.")
            results.append(result)
            continue

        result["pmc_availability_status"] = "pmcid_present"
        result["pmc_retrieval_attempted"] = True
        try:
            if fixture_dir is not None:
                xml_text = load_pmc_fixture_xml(pmcid, fixture_dir)
                result["public_retrieval_source"] = "fixture"
                if xml_text is None:
                    result["pmc_availability_status"] = "pmc_retrieval_failed"
                    result["warnings"].append("No synthetic PMC XML fixture matched this PMCID.")
                    results.append(result)
                    continue
                result["pmc_availability_status"] = "pmc_fixture_loaded"
            else:
                xml_text = fetch_pmc_xml(pmcid)
                result["public_retrieval_source"] = "ncbi_pmc"
                result["pmc_availability_status"] = "pmc_retrieved"

            if ai_public_only_gate_requested:
                assert_ai_public_only_gate([(f"pmc_xml_{safe_pmcid_token(pmcid)}", xml_text)])
            ET.fromstring(xml_text)
            token = safe_pmcid_token(pmcid)
            xml_path = xml_folder / f"{token}.xml"
            text_path = text_folder / f"{token}.txt"
            xml_path.write_text(xml_text, encoding="utf-8")
            extracted_text = extract_public_pmc_text(xml_text, token)
            text_path.write_text(extracted_text, encoding="utf-8")
            result["pmc_retrieval_succeeded"] = True
            result["pmc_text_extracted"] = bool(extracted_text.strip())
            result["local_xml_export_path"] = xml_path.relative_to(run_folder).as_posix()
            result["local_text_export_path"] = text_path.relative_to(run_folder).as_posix()
            result["text_character_count"] = len(extracted_text)
        except AIBackendPublicOnlyGateError:
            raise
        except (OSError, ValueError, ET.ParseError) as exc:
            result["pmc_availability_status"] = "pmc_retrieval_failed"
            result["warnings"].append(f"PMC XML retrieval or extraction failed: {exc}")
        results.append(result)
    return results


def render_note(
    *,
    record: dict[str, Any],
    screening: dict[str, Any],
    goal: str,
) -> str:
    title = clean_text(record.get("title")) or "Untitled PubMed record"
    authors = normalize_authors(record.get("authors"))
    author_lines = "\n".join(f"  - {yaml_quote(author)}" for author in authors)
    if not author_lines:
        author_lines = "  []"
    pmcid_line = f"pmcid: {yaml_quote(clean_text(record.get('pmcid')))}\n" if record.get("pmcid") else ""
    doi_line = f"doi: {yaml_quote(clean_text(record.get('doi')))}\n" if record.get("doi") else ""
    abstract_summary = concise_abstract_summary(clean_text(record.get("abstract")))
    relevance = clean_text(screening.get("reason"))
    return f"""---
title: {yaml_quote(title)}
authors:
{author_lines}
year: {yaml_quote(clean_text(record.get("year")))}
journal: {yaml_quote(clean_text(record.get("journal")))}
pmid: {yaml_quote(clean_text(record.get("pmid")))}
{pmcid_line}{doi_line}note_depth: abstract_metadata_only
security_tier: public
read_depth: pubmed_abstract_reviewed
source_provenance:
  - pubmed_metadata: true
  - pubmed_abstract: true
  - pmc_full_text: false
  - pdf_full_text: false
human_review_status: ai_draft_needs_human_review
screening_backend: {yaml_quote(clean_text(screening.get("screening_backend")))}
screening_score: {screening.get("score", 0)}
relevance_label: {yaml_quote(clean_text(screening.get("relevance_label")))}
---

# {title}

## Abstract-Level Summary

{abstract_summary}

## Why This May Be Relevant

User goal: {goal}

{relevance}

## Evidence Limits

This draft is based only on PubMed metadata and abstract text. No PMC full text,
publisher full text, PDF, figures, methods details beyond the abstract,
supplements, Bookends records, private notes, or internal research material were
reviewed.

## Suggested Full-Text Checks

- Confirm the main claims, methods, figures, and limitations in the full article.
- Check whether a public full-text source is available before any deeper draft.
- Verify relevance and import suitability by human review before editing `selected_notes.yaml`.

## Human Review Reminder

This is an abstract-metadata-only draft and is not reviewed at full-text level.
"""


def write_generated_notes(
    *,
    run_folder: Path,
    records: list[dict[str, Any]],
    screening_results: list[dict[str, Any]],
    goal: str,
    abstract_top_n: int,
) -> list[str]:
    abstract_folder = run_folder / "generated_notes" / "abstract_level"
    record_by_pmid = {clean_text(record.get("pmid")): record for record in records}
    generated: list[str] = []
    for screening in screening_results[:abstract_top_n]:
        record = record_by_pmid.get(clean_text(screening.get("pmid")))
        if record is None:
            continue
        pmid = clean_text(record.get("pmid")) or "no-pmid"
        filename = f"{note_slug(pmid, 'pmid')}_{note_slug(clean_text(record.get('title')), 'untitled')}.md"
        note_path = abstract_folder / filename
        note_path.write_text(render_note(record=record, screening=screening, goal=goal), encoding="utf-8")
        generated.append(note_path.relative_to(run_folder).as_posix())
    return generated


def render_public_pmc_full_text_note(
    *,
    record: dict[str, Any],
    screening: dict[str, Any] | None,
    pmc_result: dict[str, Any],
    evidence: dict[str, Any],
    goal: str,
) -> str:
    title = safe_note_text(
        clean_text(record.get("title"))
        or clean_text(pmc_result.get("title"))
        or "Untitled PubMed record",
        width=180,
    )
    authors = normalize_authors(record.get("authors"))
    author_lines = "\n".join(f"  - {yaml_quote(author)}" for author in authors) or "  []"
    doi = clean_text(record.get("doi")) or clean_text(pmc_result.get("doi"))
    doi_line = f"doi: {yaml_quote(doi)}\n" if doi else ""
    score = (
        screening.get("score", "")
        if screening
        else pmc_result.get("abstract_screening_score", "")
    )
    relevance_label = (
        clean_text(screening.get("relevance_label"))
        if screening
        else clean_text(pmc_result.get("abstract_relevance_label"))
    )
    backend = clean_text(screening.get("screening_backend")) if screening else ""
    relevance_reason = safe_note_text(
        clean_text(screening.get("reason")) if screening else "",
        width=500,
    )
    xml_path = clean_text(pmc_result.get("local_xml_export_path"))
    text_path = clean_text(pmc_result.get("local_text_export_path"))
    pmc_status = clean_text(pmc_result.get("pmc_availability_status"))

    abstract_context = "\n".join(f"- {sentence}" for sentence in evidence["abstract_sentences"]) or (
        "- No abstract sentence was extracted from the public PMC XML."
    )
    body_context = "\n".join(f"- {sentence}" for sentence in evidence["body_sentences"]) or (
        "- No body sentence was extracted from the public PMC XML/text export."
    )
    section_bullets = "\n".join(
        f"- {item['title']}: {item['text']}" for item in evidence["section_bullets"]
    ) or "- No section-level body bullets were extracted from the public PMC XML."
    methods_section = ""
    if evidence["methods_bullets"]:
        methods_lines = "\n".join(f"- {item}" for item in evidence["methods_bullets"])
        methods_section = f"""
## Methods And Controls Visible In Public XML

{methods_lines}
"""
    figure_section = ""
    if evidence["figure_captions"]:
        figure_lines = "\n".join(f"- {item}" for item in evidence["figure_captions"])
        figure_section = f"""
## Figure Captions Visible In Public XML

{figure_lines}
"""
    heuristic_text = (
        f"Screening backend `{backend}` assigned score `{score}` with label `{relevance_label}`. {relevance_reason}"
        if backend
        else "No abstract screening backend metadata was available for this record."
    )
    return f"""---
title: {yaml_quote(title)}
authors:
{author_lines}
year: {yaml_quote(clean_text(record.get("year")) or clean_text(pmc_result.get("year")))}
journal: {yaml_quote(clean_text(record.get("journal")) or clean_text(pmc_result.get("journal")))}
{doi_line}pmid: {yaml_quote(clean_text(record.get("pmid")) or clean_text(pmc_result.get("pmid")))}
pmcid: {yaml_quote(clean_text(record.get("pmcid")) or clean_text(pmc_result.get("pmcid")))}
note_depth: public_full_text_reviewed
security_tier: public
read_depth: public_full_text_reviewed
source_provenance:
  - pubmed_metadata: true
  - pubmed_abstract: true
  - pmc_full_text: true
  - public_pmc_xml: true
  - pdf_full_text: false
human_review_status: ai_draft_needs_human_review
screening_backend: {yaml_quote(backend)}
screening_score: {yaml_quote(str(score))}
relevance_label: {yaml_quote(relevance_label)}
pmc_availability_status: {yaml_quote(pmc_status)}
local_pmc_xml_export_path: {yaml_quote(xml_path)}
local_pmc_text_export_path: {yaml_quote(text_path)}
---

# {title}

## Draft Status

This is a deterministic draft generated from public PMC XML/text exported in
this same run. It has not been scientifically approved by a human reviewer and
must stay outside `Papers/` until explicit human review and import selection.

## Public PMC-Derived Summary

{evidence["summary"]}

## Claims Directly Visible In Public PMC XML/Text

{section_bullets}

## Abstract-Level Content

{abstract_context}

## Public XML Body Text Signals

{body_context}

## Local Heuristic Relevance Interpretation

User goal: {safe_note_text(goal, width=500)}

{heuristic_text}
{methods_section}{figure_section}
## Unanswered Questions For Human Full-Text Review

- Verify whether the public XML body text supports the draft summary above.
- Check methods, controls, figures, and limitations against the article before import.
- Decide whether the note should be edited and explicitly selected in `selected_notes.yaml`.

## Deterministic Generation Limits

- This draft used local rule-based extraction only; no ChatGPT, OpenAI, Claude,
  or other external AI API was called.
- Evidence was limited to public PMC XML/text exported under this run folder.
- No PDF, Bookends attachment, publisher full text outside PMC, supplement,
  repository note, or human scientific approval was used.

## Import Review Reminder

`selected_notes.yaml` intentionally remains `notes: []`. A human must review,
edit, and select any generated draft before running the selected paper-note
importer.
"""


def write_full_text_draft_notes(
    *,
    run_folder: Path,
    records: list[dict[str, Any]],
    screening_results: list[dict[str, Any]],
    pmc_availability_results: list[dict[str, Any]],
    goal: str,
    pmc_top_n: int,
) -> list[str]:
    full_text_folder = run_folder / "generated_notes" / "full_text_level"
    record_by_pmid = {clean_text(record.get("pmid")): record for record in records}
    screening_by_pmid = {
        clean_text(screening.get("pmid")): screening for screening in screening_results
    }
    generated: list[str] = []
    for pmc_result in pmc_availability_results:
        if len(generated) >= pmc_top_n:
            break
        if not (
            pmc_result.get("pmcid_present")
            and pmc_result.get("pmc_retrieval_succeeded")
            and pmc_result.get("pmc_text_extracted")
            and pmc_result.get("local_xml_export_path")
            and pmc_result.get("local_text_export_path")
            and pmc_result.get("public_retrieval_source") in {"fixture", "ncbi_pmc"}
        ):
            continue
        xml_path = run_folder / clean_text(pmc_result.get("local_xml_export_path"))
        text_path = run_folder / clean_text(pmc_result.get("local_text_export_path"))
        if not (
            is_relative_to(xml_path.resolve(), run_folder.resolve())
            and is_relative_to(text_path.resolve(), run_folder.resolve())
            and xml_path.is_file()
            and text_path.is_file()
        ):
            continue
        xml_text = xml_path.read_text(encoding="utf-8")
        text_export = text_path.read_text(encoding="utf-8")
        if not text_export.strip():
            continue
        evidence = extract_pmc_draft_evidence(xml_text, text_export)
        record = record_by_pmid.get(clean_text(pmc_result.get("pmid")), {})
        screening = screening_by_pmid.get(clean_text(pmc_result.get("pmid")))
        pmid = clean_text(pmc_result.get("pmid")) or clean_text(pmc_result.get("pmcid")) or "no-id"
        title = clean_text(record.get("title")) or clean_text(pmc_result.get("title"))
        note_path = full_text_folder / f"{note_slug(pmid, 'pmid')}_{note_slug(title, 'untitled')}_public_pmc_full_text.md"
        note_path.write_text(
            render_public_pmc_full_text_note(
                record=record,
                screening=screening,
                pmc_result=pmc_result,
                evidence=evidence,
                goal=goal,
            ),
            encoding="utf-8",
        )
        generated.append(note_path.relative_to(run_folder).as_posix())
        pmc_result["full_text_note_draft_generated"] = True
        pmc_result["generated_full_text_note_path"] = note_path.relative_to(run_folder).as_posix()
    return generated


def render_full_text_placeholder() -> str:
    return """# Full-Text-Level Drafts Not Implemented

Full-text-level Markdown paper-note drafting is not implemented in this phase.
Phase 3a may check PMC availability and retrieve public PMC XML/text evidence
under `pmc_full_text/`, but it does not generate full-text-level notes.
When `--check-pmc-full-text` is not used, this run does not retrieve PMC full text.

Phase 3b is reserved for full-text Markdown draft generation from public PMC
content after a separate approved spec.
"""


def ai_backend_requested(ai_backend: str) -> bool:
    return ai_backend != "disabled"


def ai_screening_entry(screening: dict[str, Any] | None) -> dict[str, Any]:
    if not screening:
        return {}
    return {
        "score": screening.get("score"),
        "relevance_label": clean_text(screening.get("relevance_label")),
        "screening_backend": clean_text(screening.get("screening_backend")),
        "reason": clean_text(screening.get("reason")),
        "read_depth": "pubmed_abstract_reviewed",
    }


def build_ai_input_packet(
    *,
    run_folder: Path,
    goal: str,
    records: list[dict[str, Any]],
    screening_results: list[dict[str, Any]],
    pmc_availability_results: list[dict[str, Any]],
    generated_note_paths: list[str],
    generated_full_text_note_paths: list[str],
) -> dict[str, Any]:
    screening_by_pmid = {
        clean_text(screening.get("pmid")): screening for screening in screening_results
    }
    pubmed_records: list[dict[str, Any]] = []
    for record in records:
        pmid = clean_text(record.get("pmid"))
        pubmed_records.append(
            {
                "pmid": pmid,
                "title": clean_text(record.get("title")),
                "authors": normalize_authors(record.get("authors")),
                "year": clean_text(record.get("year")),
                "journal": clean_text(record.get("journal")),
                "doi": clean_text(record.get("doi")),
                "pmcid": clean_text(record.get("pmcid")),
                "abstract": textwrap.shorten(
                    clean_text(record.get("abstract")),
                    width=2400,
                    placeholder="...",
                ),
                "source_provenance": ["PubMed metadata", "PubMed abstract"],
                "screening": ai_screening_entry(screening_by_pmid.get(pmid)),
            }
        )

    public_full_text_entries: list[dict[str, Any]] = []
    for pmc_result in pmc_availability_results:
        if not (
            pmc_result.get("pmc_retrieval_succeeded")
            and pmc_result.get("pmc_text_extracted")
            and pmc_result.get("local_xml_export_path")
            and pmc_result.get("local_text_export_path")
        ):
            continue
        xml_path = run_folder / clean_text(pmc_result.get("local_xml_export_path"))
        text_path = run_folder / clean_text(pmc_result.get("local_text_export_path"))
        if not (
            is_relative_to(xml_path.resolve(), run_folder.resolve())
            and is_relative_to(text_path.resolve(), run_folder.resolve())
            and xml_path.is_file()
            and text_path.is_file()
        ):
            continue
        xml_text = xml_path.read_text(encoding="utf-8")
        text_export = text_path.read_text(encoding="utf-8")
        evidence = extract_pmc_draft_evidence(xml_text, text_export)
        public_full_text_entries.append(
            {
                "pmid": clean_text(pmc_result.get("pmid")),
                "pmcid": clean_text(pmc_result.get("pmcid")),
                "title": clean_text(pmc_result.get("title")),
                "public_retrieval_source": clean_text(pmc_result.get("public_retrieval_source")),
                "read_depth": "public_full_text_reviewed",
                "source_provenance": ["public PMC XML text"],
                "summary": evidence["summary"],
                "abstract_sentences": evidence["abstract_sentences"],
                "body_sentences": evidence["body_sentences"],
                "section_bullets": evidence["section_bullets"],
                "figure_captions": evidence["figure_captions"],
            }
        )

    return {
        "safety_notice": (
            "Local packet only. The script has not sent this content to any external AI service."
        ),
        "goal": goal,
        "pubmed_records": pubmed_records,
        "public_pmc_full_text_entries": public_full_text_entries,
        "generated_abstract_note_paths": generated_note_paths,
        "generated_full_text_note_paths": generated_full_text_note_paths,
    }


def ai_input_read_depths(packet: dict[str, Any]) -> list[str]:
    depths: list[str] = []
    if packet.get("pubmed_records"):
        depths.append("pubmed_abstract_reviewed")
    if packet.get("public_pmc_full_text_entries"):
        depths.append("public_full_text_reviewed")
    return depths


def ai_source_provenance(packet: dict[str, Any]) -> list[str]:
    provenance: list[str] = []
    if packet.get("pubmed_records"):
        provenance.extend(["PubMed metadata", "PubMed abstract"])
    if packet.get("public_pmc_full_text_entries"):
        provenance.append("public PMC XML text")
    return sorted(set(provenance))


def render_ai_input_summary(
    *,
    ai_backend: str,
    packet: dict[str, Any],
    prompt_packet_generated: bool,
    mock_response_used: bool,
) -> str:
    read_depths = ", ".join(ai_input_read_depths(packet)) or "none"
    provenance = ", ".join(ai_source_provenance(packet)) or "none"
    openai_live = ai_backend == "openai"
    external_status = (
        "This is a safety-gated packet for the explicitly enabled live OpenAI adapter. "
        "Only public PubMed/PMC inputs are eligible, and generated suggestions require human review."
        if openai_live
        else (
            "This is a safety-gated local backend interface only. The script did not send "
            "this packet to ChatGPT, OpenAI, Claude, Anthropic, or any external AI service."
        )
    )
    return f"""# AI Backend Input Summary

Backend selected: `{ai_backend}`

{external_status}

Human review is required before any future prompt packet is uploaded anywhere.
Any later upload must follow `AI_SAFE.md` and must exclude private repository
content, PDFs, Bookends content, local paths, secrets, raw data, and protected
research materials.

## Gate Result

- public-only gate passed: `true`
- live external AI API call attempted: `{str(openai_live).lower()}`
- live external AI API call succeeded: `{str(openai_live).lower()}`
- provider API key handling occurred: `{str(openai_live).lower()}`
- network AI request occurred: `{str(openai_live).lower()}`
- prompt/input packet exported: `{str(prompt_packet_generated).lower()}`
- mock response used: `{str(mock_response_used).lower()}`

## Included Public Inputs

- PubMed records: `{len(packet["pubmed_records"])}`
- public PMC full-text entries: `{len(packet["public_pmc_full_text_entries"])}`
- read depths: `{read_depths}`
- source provenance: `{provenance}`
"""


def render_ai_prompt_packet(*, ai_backend: str, packet: dict[str, Any]) -> str:
    records_json = json.dumps(packet, indent=2, sort_keys=True, ensure_ascii=False)
    return f"""# AI Prompt Packet For Human Review

Backend mode: `{ai_backend}`

This packet has not been sent to any external AI service by this script. It was
generated locally for review and has not been uploaded anywhere.

Human review is required before uploading any content anywhere. Follow
`AI_SAFE.md`; no private repository content, PDFs, Bookends content, local
paths, secrets, raw data, protected research materials, or unpublished internal
context should be included.

Live external AI integration is not implemented in this phase. API keys,
provider SDK dependencies, network requests, and provider-specific response
parsing are intentionally out of scope.

## Suggested Future Task

Review the public PubMed metadata, public abstracts, and public PMC XML-derived
text below for relevance to the stated goal. Clearly separate abstract-level
evidence from public full-text evidence and avoid making claims beyond the
provided public text.

## Local Public Input Packet

```json
{records_json}
```
"""


def build_openai_request_body(
    *,
    packet: dict[str, Any],
    model: str,
    max_output_tokens: int = DEFAULT_OPENAI_MAX_OUTPUT_TOKENS,
) -> dict[str, Any]:
    packet_json = json.dumps(packet, indent=2, sort_keys=True, ensure_ascii=False)
    instructions = (
        "You are reviewing only public PubMed metadata, public abstracts, and public PMC XML-derived "
        "text supplied in the input. Return JSON only. Do not use tools, web search, file search, "
        "code execution, uploads, external files, or prior conversation state. Do not infer from PDFs, "
        "private notes, Bookends records, raw data, or local files. Treat all suggestions as requiring "
        "human review. Use short public-evidence-based reasons and include limitations."
    )
    schema_hint = {
        "backend": "openai",
        "output_type": "pubmed_triage_suggestions",
        "candidate_updates": [
            {
                "pmid": "string",
                "suggested_relevance": "high|medium|low|unclear",
                "reason": "short public-evidence-based reason",
                "read_depth_used": "pubmed_abstract_reviewed|public_full_text_reviewed",
                "limitations": ["short limitation"],
            }
        ],
    }
    return {
        "model": model,
        "store": False,
        "temperature": 0,
        "max_output_tokens": max_output_tokens,
        "instructions": instructions,
        "input": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "Return JSON matching this shape:\n"
                            f"{json.dumps(schema_hint, indent=2, sort_keys=True)}\n\n"
                            "Public-only PubMed/PMC triage packet:\n"
                            f"{packet_json}"
                        ),
                    }
                ],
            }
        ],
        "metadata": {
            "workflow": WORKFLOW_NAME,
            "adapter": "pubmed_ai_triage_openai",
            "security_tier": "public",
        },
    }


def redacted_openai_request_log(request_body: dict[str, Any]) -> dict[str, Any]:
    return {
        "method": "POST",
        "url": OPENAI_RESPONSES_URL,
        "headers": {
            "Authorization": "Bearer <redacted>",
            "Content-Type": "application/json",
        },
        "body": request_body,
        "openai_api_key_available": True,
        "openai_api_key_logged": False,
    }


def call_openai_responses_api(*, request_body: dict[str, Any], credential: str) -> dict[str, Any]:
    request = urllib.request.Request(
        OPENAI_RESPONSES_URL,
        data=json.dumps(request_body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {credential}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        response_text = response.read().decode("utf-8")
    return json.loads(response_text)


def extract_openai_response_text(response: dict[str, Any]) -> str:
    direct = response.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    chunks: list[str] = []
    output = response.get("output")
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for content_item in content:
                if not isinstance(content_item, dict):
                    continue
                text = content_item.get("text")
                if isinstance(text, str) and text.strip():
                    chunks.append(text.strip())
    return "\n".join(chunks).strip()


def parse_json_object_from_text(text: str) -> dict[str, Any]:
    candidate = clean_text(text)
    fence_match = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", candidate, re.DOTALL | re.IGNORECASE)
    if fence_match:
        candidate = fence_match.group(1).strip()
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start == -1 or end <= start:
            return {"unparsed_output_text": text}
        try:
            parsed = json.loads(candidate[start : end + 1])
        except json.JSONDecodeError:
            return {"unparsed_output_text": text}
    if isinstance(parsed, dict):
        return parsed
    return {"parsed_output": parsed}


def parsed_openai_suggestions(response: dict[str, Any]) -> dict[str, Any]:
    output_text = extract_openai_response_text(response)
    parsed = parse_json_object_from_text(output_text) if output_text else {}
    candidate_updates = parsed.get("candidate_updates") if isinstance(parsed, dict) else []
    if not isinstance(candidate_updates, list):
        candidate_updates = []
    return {
        "external_ai_backend": "openai",
        "external_ai_review_status": "ai_suggestion_needs_human_review",
        "backend": "openai",
        "output_type": clean_text(parsed.get("output_type")) or "pubmed_triage_suggestions",
        "candidate_updates": candidate_updates,
        "parsed_response": parsed,
        "raw_output_text": output_text,
    }


def render_openai_response_summary(
    *,
    parsed_response: dict[str, Any],
    model: str,
    api_called: bool,
) -> str:
    candidate_count = len(parsed_response.get("candidate_updates", []))
    return f"""# OpenAI Response Summary

external_ai_backend: openai
external_ai_review_status: ai_suggestion_needs_human_review

This file summarizes an external AI suggestion generated through the disabled-by-default
OpenAI adapter. The suggestions require human review and do not approve any note for import.

- model: `{model}`
- API called: `{str(api_called).lower()}`
- candidate updates parsed: `{candidate_count}`
- API key logged: `false`
- tools used: `[]`
- store false requested: `true`
- selected_notes.yaml remains: `notes: []`
"""


def build_mock_ai_response(packet: dict[str, Any]) -> dict[str, Any]:
    responses: list[dict[str, Any]] = []
    for index, record in enumerate(packet["pubmed_records"]):
        score = max(0, 75 - index * 5)
        responses.append(
            {
                "label": "mock_ai_backend",
                "pmid": record.get("pmid", ""),
                "title": record.get("title", ""),
                "mock_score": score,
                "mock_comment": (
                    "Deterministic mock output for interface validation only; "
                    "not a real external AI review."
                ),
            }
        )
    return {
        "backend": "mock",
        "label": "mock_ai_backend",
        "external_ai_result": False,
        "notice": "This deterministic fixture response is not a real external AI result.",
        "record_suggestions": responses,
    }


def default_ai_backend_state(ai_backend: str) -> dict[str, Any]:
    return {
        "selected_backend_name": ai_backend,
        "backend_requested": False,
        "public_only_gate_passed": False,
        "prompt_packet_generated": False,
        "mock_response_used": False,
        "live_external_ai_api_call_attempted": False,
        "live_external_ai_api_call_succeeded": False,
        "provider_specific_api_key_handling_occurred": False,
        "network_ai_request_occurred": False,
        "external_ai_api_called": False,
        "external_ai_api_key_used": False,
        "external_ai_api_key_logged": False,
        "openai_model": "",
        "openai_request_redacted_path": "",
        "openai_response_path": "",
        "openai_response_summary_path": "",
        "openai_store_false_requested": False,
        "openai_tools_used": [],
        "input_read_depths_included": [],
        "source_provenance_included": [],
        "generated_output_paths": [],
        "manifest_path": "",
        "limitations": [
            "AI backend disabled; no backend packet was requested.",
            "No live external AI API calls are implemented in this phase.",
        ],
        "warnings": [],
    }


def write_ai_backend_interface(
    *,
    run_folder: Path,
    ai_backend: str,
    goal: str,
    records: list[dict[str, Any]],
    screening_results: list[dict[str, Any]],
    pmc_availability_results: list[dict[str, Any]],
    generated_note_paths: list[str],
    generated_full_text_note_paths: list[str],
    allow_live_openai_api: bool = False,
    confirm_public_ai_export: bool = False,
    openai_model: str = DEFAULT_OPENAI_MODEL,
) -> dict[str, Any]:
    if not ai_backend_requested(ai_backend):
        return default_ai_backend_state(ai_backend)
    openai_response_used = ai_backend == "openai"
    if ai_backend == "openai":
        if not allow_live_openai_api:
            raise ValueError(
                "--ai-backend openai requires explicit --allow-live-openai-api opt-in"
            )
        if not confirm_public_ai_export:
            raise ValueError(
                "--ai-backend openai requires explicit --confirm-public-ai-export confirmation"
            )

    packet = build_ai_input_packet(
        run_folder=run_folder,
        goal=goal,
        records=records,
        screening_results=screening_results,
        pmc_availability_results=pmc_availability_results,
        generated_note_paths=generated_note_paths,
        generated_full_text_note_paths=generated_full_text_note_paths,
    )
    assert_ai_public_only_gate(
        [
            ("ai_goal", goal),
            ("ai_pubmed_records", packet["pubmed_records"]),
            ("ai_public_pmc_full_text_entries", packet["public_pmc_full_text_entries"]),
        ]
    )
    openai_credential = ""
    if openai_response_used:
        openai_credential = get_openai_api_key()
        if not openai_credential:
            raise ValueError(
                "--ai-backend openai requires OPENAI_API_KEY in the process environment"
            )

    backend_folder = run_folder / "ai_backend"
    backend_folder.mkdir(parents=True, exist_ok=False)
    generated_paths: list[str] = []
    prompt_packet_generated = ai_backend == "prompt_packet"
    mock_response_used = ai_backend == "mock"

    summary_path = backend_folder / "AI_BACKEND_INPUT_SUMMARY.md"
    summary_path.write_text(
        render_ai_input_summary(
            ai_backend=ai_backend,
            packet=packet,
            prompt_packet_generated=prompt_packet_generated,
            mock_response_used=mock_response_used,
        ),
        encoding="utf-8",
    )
    generated_paths.append(summary_path.relative_to(run_folder).as_posix())

    if prompt_packet_generated:
        packet_path = backend_folder / "AI_PROMPT_PACKET.md"
        packet_path.write_text(
            render_ai_prompt_packet(ai_backend=ai_backend, packet=packet),
            encoding="utf-8",
        )
        generated_paths.append(packet_path.relative_to(run_folder).as_posix())

    if mock_response_used:
        mock_path = backend_folder / "mock_ai_response.json"
        mock_path.write_text(
            json.dumps(build_mock_ai_response(packet), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        generated_paths.append(mock_path.relative_to(run_folder).as_posix())

    openai_request_redacted_path = ""
    openai_response_path = ""
    openai_response_summary_path = ""
    openai_api_called = False
    openai_network_request_performed = False
    openai_api_key_used = False
    if openai_response_used:
        request_body = build_openai_request_body(packet=packet, model=openai_model)
        request_path = backend_folder / "OPENAI_REQUEST_REDACTED.json"
        request_path.write_text(
            json.dumps(redacted_openai_request_log(request_body), indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        generated_paths.append(request_path.relative_to(run_folder).as_posix())
        openai_request_redacted_path = request_path.relative_to(run_folder).as_posix()

        openai_api_called = True
        openai_network_request_performed = True
        openai_api_key_used = True
        raw_response = call_openai_responses_api(
            request_body=request_body,
            credential=openai_credential,
        )
        parsed_response = parsed_openai_suggestions(raw_response)
        response_path = backend_folder / "OPENAI_RESPONSE.json"
        response_path.write_text(
            json.dumps(
                {
                    "external_ai_backend": "openai",
                    "external_ai_output": True,
                    "external_ai_review_status": "ai_suggestion_needs_human_review",
                    "openai_model": openai_model,
                    "parsed_suggestions": parsed_response,
                    "raw_response": raw_response,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        generated_paths.append(response_path.relative_to(run_folder).as_posix())
        openai_response_path = response_path.relative_to(run_folder).as_posix()

        response_summary_path = backend_folder / "OPENAI_RESPONSE_SUMMARY.md"
        response_summary_path.write_text(
            render_openai_response_summary(
                parsed_response=parsed_response,
                model=openai_model,
                api_called=openai_api_called,
            ),
            encoding="utf-8",
        )
        generated_paths.append(response_summary_path.relative_to(run_folder).as_posix())
        openai_response_summary_path = response_summary_path.relative_to(run_folder).as_posix()

    manifest: dict[str, Any] = {
        "selected_backend_name": ai_backend,
        "backend_requested": True,
        "public_only_gate_passed": True,
        "prompt_packet_generated": prompt_packet_generated,
        "mock_response_used": mock_response_used,
        "live_external_ai_api_call_attempted": openai_api_called,
        "live_external_ai_api_call_succeeded": openai_api_called,
        "provider_specific_api_key_handling_occurred": openai_response_used,
        "network_ai_request_occurred": openai_network_request_performed,
        "external_ai_api_called": openai_api_called,
        "external_ai_backend_requested": True,
        "external_ai_backend_name": ai_backend,
        "external_ai_network_request_performed": openai_network_request_performed,
        "external_ai_api_key_used": openai_api_key_used,
        "external_ai_api_key_logged": False,
        "openai_model": openai_model if openai_response_used else "",
        "openai_request_redacted_path": openai_request_redacted_path,
        "openai_response_path": openai_response_path,
        "openai_response_summary_path": openai_response_summary_path,
        "openai_store_false_requested": openai_response_used,
        "openai_tools_used": [],
        "paper_notes_imported": False,
        "papers_write_performed": False,
        "git_actions_performed": False,
        "input_read_depths_included": ai_input_read_depths(packet),
        "source_provenance_included": ai_source_provenance(packet),
        "generated_output_paths": generated_paths,
        "manifest_path": "ai_backend/ai_backend_manifest.json",
        "limitations": [
            (
                "OpenAI adapter output is an external AI suggestion requiring human review."
                if openai_response_used
                else "Safety-gated interface only; no live external AI backend was called."
            ),
            "Mock output, when present, is deterministic fixture output only.",
            "Prompt packets require human review before any future external upload.",
            "Workflow C / Bookends local PDF reading remains separate and is not implemented here.",
        ],
        "warnings": [],
    }
    manifest_path = backend_folder / "ai_backend_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def build_manifest(
    *,
    goal: str,
    topic_slug: str,
    timestamp: str,
    retmax: int,
    abstract_top_n: int,
    full_text_top_n: int,
    query: str,
    sort_mode: str,
    input_pubmed_json: bool,
    records: list[dict[str, Any]],
    screening_backend: str,
    ai_screening_performed: bool,
    generated_note_paths: list[str],
    generated_full_text_note_paths: list[str],
    check_pmc_full_text: bool,
    generate_full_text_drafts: bool,
    generate_chatgpt_note_packet: bool,
    pmc_top_n: int,
    input_pmc_fixtures: bool,
    pmc_availability_results: list[dict[str, Any]],
    skeleton_only: bool,
    ai_backend_state: dict[str, Any],
) -> dict[str, object]:
    output_locations = {
        "summary": "PUBMED_TRIAGE_SUMMARY.md",
        "manifest": "pubmed_triage_manifest.json",
        "pubmed_results_json": "pubmed_results.json",
        "pubmed_results_csv": "pubmed_results.csv",
        "abstract_screening_results": "abstract_screening_results.json",
        "generated_notes": "generated_notes/",
        "abstract_level_notes": "generated_notes/abstract_level/",
        "full_text_level_notes": "generated_notes/full_text_level/",
        "pmc_availability_results": "pmc_availability_results.json",
        "pmc_full_text": "pmc_full_text/",
        "pmc_full_text_xml": "pmc_full_text/xml/",
        "pmc_full_text_text": "pmc_full_text/text/",
        "full_text_level_draft_notes": "generated_notes/full_text_level/",
        "ai_backend": "ai_backend/",
        "ai_backend_manifest": ai_backend_state.get("manifest_path", ""),
        "chatgpt_note_packet": "chatgpt_note_packet/" if generate_chatgpt_note_packet else "",
        "chatgpt_note_packet_primary": (
            "chatgpt_note_packet/CHATGPT_CREATE_NOTES_PACKET.md"
            if generate_chatgpt_note_packet
            else ""
        ),
        "chatgpt_note_packet_zip": (
            f"chatgpt_note_packet/{chatgpt_packet_filename(topic_slug, timestamp, '.zip')}"
            if generate_chatgpt_note_packet
            else ""
        ),
        "import_discussion": "DISCUSS_IMPORT_TO_PAPERS.md",
        "selected_notes": "selected_notes.yaml",
        "selected_notes_instructions": "selected_notes_instructions.md",
    }
    pmc_full_text_retrieved = any(
        bool(item.get("pmc_retrieval_succeeded")) for item in pmc_availability_results
    )
    pmc_text_extracted = any(bool(item.get("pmc_text_extracted")) for item in pmc_availability_results)
    return {
        "workflow_name": WORKFLOW_NAME,
        "workflow_phase": (
            SKELETON_PHASE
            if skeleton_only
            else FULL_TEXT_DRAFT_PHASE
            if generate_full_text_drafts and generated_full_text_note_paths
            else PMC_PHASE
            if check_pmc_full_text
            else WORKFLOW_PHASE
        ),
        "goal": goal,
        "topic_slug": topic_slug,
        "created_timestamp": timestamp,
        "query": query,
        "pubmed_sort_mode": sort_mode,
        "planned_retmax": retmax,
        "planned_abstract_level_top_n": abstract_top_n,
        "planned_full_text_top_n": full_text_top_n,
        "planned_pmc_top_n": pmc_top_n,
        "records_loaded": len(records),
        "pubmed_search_performed": bool(query and not input_pubmed_json),
        "public_pubmed_metadata_retrieval_performed": bool(query and not input_pubmed_json),
        "input_pubmed_json_used": input_pubmed_json,
        "input_pmc_fixtures_used": input_pmc_fixtures,
        "abstracts_retrieved": any(clean_text(record.get("abstract")) for record in records),
        "ai_screening_performed": ai_screening_performed,
        "screening_backend": screening_backend if ai_screening_performed else "",
        "external_ai_api_called": bool(ai_backend_state.get("external_ai_api_called")),
        "external_ai_backend_requested": bool(ai_backend_state.get("backend_requested")),
        "external_ai_backend_name": ai_backend_state.get("selected_backend_name", "disabled"),
        "external_ai_network_request_performed": bool(
            ai_backend_state.get("external_ai_network_request_performed")
        ),
        "external_ai_api_key_used": bool(ai_backend_state.get("external_ai_api_key_used")),
        "external_ai_api_key_logged": False,
        "ai_public_only_gate_passed": bool(ai_backend_state.get("public_only_gate_passed")),
        "ai_prompt_packet_generated": bool(ai_backend_state.get("prompt_packet_generated")),
        "mock_ai_backend_used": bool(ai_backend_state.get("mock_response_used")),
        "ai_backend_manifest_path": ai_backend_state.get("manifest_path", ""),
        "openai_model": ai_backend_state.get("openai_model", ""),
        "openai_request_redacted_path": ai_backend_state.get("openai_request_redacted_path", ""),
        "openai_response_path": ai_backend_state.get("openai_response_path", ""),
        "openai_response_summary_path": ai_backend_state.get("openai_response_summary_path", ""),
        "openai_store_false_requested": bool(ai_backend_state.get("openai_store_false_requested")),
        "openai_tools_used": ai_backend_state.get("openai_tools_used", []),
        "pmc_full_text_checked": check_pmc_full_text,
        "pmc_full_text_retrieved": pmc_full_text_retrieved,
        "pmc_text_extracted": pmc_text_extracted,
        "full_text_note_drafts_requested": generate_full_text_drafts,
        "full_text_note_drafts_generated": bool(generated_full_text_note_paths),
        "generated_full_text_note_count": len(generated_full_text_note_paths),
        "chatgpt_note_packet_requested": generate_chatgpt_note_packet,
        "chatgpt_note_packet_generated": generate_chatgpt_note_packet,
        "chatgpt_note_packet_primary_path": (
            "chatgpt_note_packet/CHATGPT_CREATE_NOTES_PACKET.md"
            if generate_chatgpt_note_packet
            else ""
        ),
        "chatgpt_note_packet_zip_path": (
            f"chatgpt_note_packet/{chatgpt_packet_filename(topic_slug, timestamp, '.zip')}"
            if generate_chatgpt_note_packet
            else ""
        ),
        "pdf_reading_performed": False,
        "bookends_parsing_performed": False,
        "publisher_full_text_retrieved": False,
        "supplementary_files_retrieved": False,
        "paper_notes_imported": False,
        "git_actions_performed": False,
        "papers_write_performed": False,
        "generated_abstract_note_paths": generated_note_paths,
        "generated_full_text_note_paths": generated_full_text_note_paths,
        "pmc_availability_results_count": len(pmc_availability_results),
        "pmcid_present_count": sum(1 for item in pmc_availability_results if item.get("pmcid_present")),
        "pmc_retrieved_or_fixture_loaded_count": sum(
            1 for item in pmc_availability_results if item.get("pmc_retrieval_succeeded")
        ),
        "output_locations": output_locations,
        "future_output_locations": output_locations,
        "compatibility_note": (
            "selected_notes.yaml is intentionally empty and compatible with "
            "../paper-workflow/scripts/review_selected_notes.py only after generated notes "
            "are human-reviewed and explicitly selected."
        ),
    }


def render_summary(
    *,
    goal: str,
    topic_slug: str,
    timestamp: str,
    query: str,
    sort_mode: str,
    records: list[dict[str, Any]],
    screening_backend: str,
    generated_note_paths: list[str],
    generated_full_text_note_paths: list[str],
    check_pmc_full_text: bool,
    generate_full_text_drafts: bool,
    pmc_availability_results: list[dict[str, Any]],
    input_pubmed_json: bool,
    input_pmc_fixtures: bool,
    skeleton_only: bool,
    ai_backend_state: dict[str, Any],
) -> str:
    if skeleton_only:
        status = (
            "This is a skeleton export only. It prepared the review folder shape, "
            "but it did not search PubMed, retrieve abstracts, call AI APIs, "
            "perform AI screening, check PMC availability, retrieve PMC full "
            "text, read PDFs, parse Bookends, write to `Papers/`, import paper "
            "notes, or perform Git actions."
        )
    else:
        status = (
            "This Phase 2 run used public PubMed metadata and abstracts only. "
            f"It screened {len(records)} record(s) with the `{screening_backend}` "
            "local backend and generated abstract-metadata-only draft notes for "
            f"{len(generated_note_paths)} top candidate(s)."
        )
        if check_pmc_full_text:
            source = "synthetic PMC fixtures" if input_pmc_fixtures else "public NCBI PMC"
            status += (
                f" It also performed Phase 3a PMC availability checks using {source} "
                "and exported public PMC XML/text evidence when available."
            )
        if generate_full_text_drafts:
            status += (
                " It then performed Phase 3b deterministic public PMC full-text "
                "Markdown draft generation from the exported XML/text."
            )
    note_list = "\n".join(f"- `{path}`" for path in generated_note_paths) or "- None"
    full_text_note_list = (
        "\n".join(f"- `{path}`" for path in generated_full_text_note_paths) or "- None"
    )
    pmcid_present_count = sum(1 for item in pmc_availability_results if item.get("pmcid_present"))
    pmc_loaded_count = sum(
        1 for item in pmc_availability_results if item.get("pmc_retrieval_succeeded")
    )
    pmc_results_location = (
        "`pmc_availability_results.json`" if check_pmc_full_text else "Not generated in this run."
    )
    pmc_export_location = "`pmc_full_text/xml/` and `pmc_full_text/text/`" if check_pmc_full_text else "Not generated in this run."
    input_source = "fixture input" if input_pubmed_json else "live PubMed query" if query else "skeleton input"
    ai_backend_name = clean_text(ai_backend_state.get("selected_backend_name", "disabled"))
    ai_backend_manifest = clean_text(ai_backend_state.get("manifest_path", "")) or "Not generated."
    ai_api_called = bool(ai_backend_state.get("external_ai_api_called"))
    ai_network_request = bool(ai_backend_state.get("external_ai_network_request_performed"))
    ai_api_key_used = bool(ai_backend_state.get("external_ai_api_key_used"))
    if ai_backend_name == "openai" and ai_api_called:
        ai_packet_status = (
            "The disabled-by-default OpenAI adapter was explicitly requested and produced "
            "external AI suggestions requiring human review."
        )
    else:
        ai_packet_status = (
            "A safety-gated local AI backend interface packet was generated for "
            f"`{ai_backend_name}` mode. No live external AI API, API key handling, "
            "or network AI request occurred."
            if ai_backend_state.get("backend_requested")
            else "AI backend interface disabled; no AI prompt packet or mock response was requested."
        )
    return f"""# PubMed AI Triage Summary

## User Goal

{goal}

## Query Or Fixture Input

{query or input_source}

PubMed sort mode: `{sort_mode}`

## Status

{status}

## Counts

- PubMed records loaded/retrieved: `{len(records)}`
- Abstract-level drafts generated: `{len(generated_note_paths)}`
- PMCID-present records checked: `{pmcid_present_count}`
- PMC full-text records retrieved or loaded from fixture: `{pmc_loaded_count}`
- Full-text-level Markdown draft notes generated: `{len(generated_full_text_note_paths)}`
- AI backend selected: `{ai_backend_name}`
- AI public-only gate passed: `{str(bool(ai_backend_state.get("public_only_gate_passed"))).lower()}`

## Generated Abstract-Level Drafts

{note_list}

## PMC Availability Results

- availability results: {pmc_results_location}
- XML/text exports: {pmc_export_location}

## Generated Full-Text-Level Drafts

{full_text_note_list}

Full-text-level Markdown draft generation is deterministic and local when
`--generate-full-text-drafts` is used. It uses only public PMC XML/text exported
under this run folder. No external AI API was called. No PDF, Bookends,
publisher full text outside PMC, supplementary file, `Papers/`, or repository
research note content was used.

## AI Backend Interface

{ai_packet_status}

- AI backend manifest: {ai_backend_manifest}
- prompt packet generated: `{str(bool(ai_backend_state.get("prompt_packet_generated"))).lower()}`
- mock backend used: `{str(bool(ai_backend_state.get("mock_response_used"))).lower()}`
- live external AI API call attempted: `{str(ai_api_called).lower()}`
- network AI request performed: `{str(ai_network_request).lower()}`
- API key used: `{str(ai_api_key_used).lower()}`
- API key logged: `false`

## Generated Files

- `PUBMED_TRIAGE_SUMMARY.md`
- `pubmed_triage_manifest.json`
- `pubmed_results.json`
- `pubmed_results.csv`
- `abstract_screening_results.json`
- `generated_notes/abstract_level/`
- `generated_notes/full_text_level/`
- `pmc_availability_results.json` when `--check-pmc-full-text` is used
- `pmc_full_text/` when `--check-pmc-full-text` is used
- `DISCUSS_IMPORT_TO_PAPERS.md`
- `selected_notes.yaml`
- `selected_notes_instructions.md`

## End-To-End Import Workflow

1. Review generated notes under `generated_notes/`.
2. Review `DISCUSS_IMPORT_TO_PAPERS.md` with AI or manually.
3. Edit `selected_notes.yaml` only after human review.
4. Confirm selected generated notes have `human_review_status: approved_for_import` if the importer requires it.
5. Run `../paper-workflow/scripts/review_selected_notes.py` in dry-run mode.
6. Run the importer with `--apply` only after reviewing the import review packet.
7. Commit only intentional `Papers/` changes manually.

Generated exports remain temporary under `exports/`. The triage script did not
write to `Papers/`, did not invoke the importer, and did not perform Git
actions.

Topic slug: `{topic_slug}`
Created timestamp: `{timestamp}`
"""


def render_candidate_entries(
    *,
    paths: list[str],
    screening_results: list[dict[str, Any]],
    pmc_availability_results: list[dict[str, Any]],
    level: str,
) -> str:
    if not paths:
        return "- None"
    pmc_by_generated_path = {
        clean_text(item.get("generated_full_text_note_path")): item
        for item in pmc_availability_results
        if item.get("generated_full_text_note_path")
    }
    lines: list[str] = []
    for index, path in enumerate(paths):
        if level == "full_text":
            item = pmc_by_generated_path.get(path, {})
            read_depth = "public_full_text_reviewed"
            note_depth = "public_full_text_reviewed"
        else:
            item = screening_results[index] if index < len(screening_results) else {}
            read_depth = "pubmed_abstract_reviewed"
            note_depth = "abstract_metadata_only"
        title = clean_text(item.get("title")) or "Untitled candidate"
        pmid = clean_text(item.get("pmid")) or "unknown"
        lines.append(
            f"- `{path}` | PMID `{pmid}` | {title} | note depth `{note_depth}` | read depth `{read_depth}`"
        )
    return "\n".join(lines)


def render_not_ready_candidates(
    *,
    pmc_availability_results: list[dict[str, Any]],
    generated_full_text_note_paths: list[str],
    check_pmc_full_text: bool,
) -> str:
    if not check_pmc_full_text:
        return "- PMC full-text readiness was not checked in this run."
    generated_paths = set(generated_full_text_note_paths)
    lines: list[str] = []
    for item in pmc_availability_results:
        generated_path = clean_text(item.get("generated_full_text_note_path"))
        if generated_path and generated_path in generated_paths:
            continue
        reasons: list[str] = []
        if not item.get("pmcid_present"):
            reasons.append("no PMCID in PubMed metadata")
        if item.get("pmcid_present") and not item.get("pmc_retrieval_succeeded"):
            reasons.append("public PMC XML/text was not retrieved or loaded")
        if item.get("pmc_retrieval_succeeded") and not item.get("pmc_text_extracted"):
            reasons.append("public PMC XML/text had no extracted text")
        if not generated_path:
            reasons.append("no full-text draft path was generated")
        reason_text = "; ".join(dict.fromkeys(reasons)) or "not selected for full-text draft generation"
        lines.append(
            f"- PMID `{item.get('pmid', '') or 'unknown'}` | PMCID `{item.get('pmcid', '') or 'none'}` | {item.get('title', '') or 'Untitled candidate'} | {reason_text}"
        )
    return "\n".join(lines) if lines else "- None"


def render_review_required_notes(
    *,
    generated_note_paths: list[str],
    generated_full_text_note_paths: list[str],
) -> str:
    paths = generated_note_paths + generated_full_text_note_paths
    if not paths:
        return "- None"
    return "\n".join(
        f"- `{path}` requires human review and, if appropriate, manual frontmatter editing before import."
        for path in paths
    )


def render_discussion(
    *,
    goal: str,
    topic_slug: str,
    timestamp: str,
    query: str,
    records: list[dict[str, Any]],
    screening_backend: str,
    screening_results: list[dict[str, Any]],
    generated_note_paths: list[str],
    generated_full_text_note_paths: list[str],
    check_pmc_full_text: bool,
    generate_full_text_drafts: bool,
    pmc_availability_results: list[dict[str, Any]],
    ai_backend_state: dict[str, Any],
) -> str:
    abstract_candidate_entries = render_candidate_entries(
        paths=generated_note_paths,
        screening_results=screening_results,
        pmc_availability_results=pmc_availability_results,
        level="abstract",
    )
    full_text_candidate_entries = render_candidate_entries(
        paths=generated_full_text_note_paths,
        screening_results=screening_results,
        pmc_availability_results=pmc_availability_results,
        level="full_text",
    )
    not_ready_candidates = render_not_ready_candidates(
        pmc_availability_results=pmc_availability_results,
        generated_full_text_note_paths=generated_full_text_note_paths,
        check_pmc_full_text=check_pmc_full_text,
    )
    review_required_notes = render_review_required_notes(
        generated_note_paths=generated_note_paths,
        generated_full_text_note_paths=generated_full_text_note_paths,
    )
    pmc_candidates = "\n".join(
        f"- PMID `{item['pmid']}` | PMCID `{item['pmcid']}` | {item['pmc_availability_status']} | {item['title']}"
        for item in pmc_availability_results
        if item.get("pmcid_present")
    )
    pmc_candidates = pmc_candidates or "- None"
    pmc_text_paths = "\n".join(
        f"- `{item['local_text_export_path']}`"
        for item in pmc_availability_results
        if item.get("local_text_export_path")
    )
    pmc_text_paths = pmc_text_paths or "- None"
    pmc_status = (
        "PMC public full-text availability was checked. Public PMC XML/text "
        "exports, when available, are stored separately under `pmc_full_text/`."
        if check_pmc_full_text
        else "PMC public full-text availability was not checked in this run."
    )
    full_text_status = (
        "Deterministic public PMC full-text draft generation was requested. "
        "Generated drafts are not automatically importable."
        if generate_full_text_drafts
        else (
            "Full-text-level drafting is not implemented yet. For this run, "
            "full-text draft generation was skipped because "
            "`--generate-full-text-drafts` was not requested."
        )
    )
    ai_backend_name = clean_text(ai_backend_state.get("selected_backend_name", "disabled"))
    if ai_backend_name == "openai" and ai_backend_state.get("external_ai_api_called"):
        ai_backend_status = (
            "AI backend interface `openai` generated external AI suggestions through the "
            "explicitly enabled OpenAI adapter. These suggestions require human review and "
            "do not approve import."
        )
    else:
        ai_backend_status = (
            f"AI backend interface `{ai_backend_name}` generated local safety-gated output only. "
            "It did not call a live external AI API, use an API key, or perform a network AI request."
            if ai_backend_state.get("backend_requested")
        else "AI backend interface disabled; no prompt packet or mock response was generated."
    )
    external_ai_review_status = (
        "ai_suggestion_needs_human_review"
        if ai_backend_name == "openai" and ai_backend_state.get("external_ai_api_called")
        else "not_applicable"
    )
    input_status = (
        "fixture PubMed JSON input was used"
        if records and not query
        else "live PubMed query was used"
        if query
        else "skeleton run with no PubMed records"
    )
    return f"""# Discuss Import To Papers

## Run Context

- workflow: `{WORKFLOW_NAME}`
- workflow phase: `{WORKFLOW_PHASE}`
- topic slug: `{topic_slug}`
- created timestamp: `{timestamp}`
- user goal: {goal}
- PubMed query or fixture status: {query or input_status}
- records retrieved or loaded: `{len(records)}`
- abstract-level generated note count: `{len(generated_note_paths)}`
- public-PMC-full-text generated note count: `{len(generated_full_text_note_paths)}`
- screening backend: `{screening_backend}`
- selected notes file: `selected_notes.yaml`
- selected notes instructions: `selected_notes_instructions.md`

## Abstract-Only Draft Candidates

Generated Abstract-Only Draft Notes:

{abstract_candidate_entries}

These drafts are `abstract_metadata_only`, public-tier, and have read depth
`pubmed_abstract_reviewed`. They require human review before any import
decision.

## Public PMC Full-Text Draft Candidates

Generated Full-Text-Level Draft Note Paths:

{full_text_candidate_entries}

These drafts are `public_full_text_reviewed`, public-tier, and have read depth
`public_full_text_reviewed`. They still require human review before import.

## Candidates Not Ready For Import

{not_ready_candidates}

## Notes Requiring Further Review Before Import

{review_required_notes}

Generated note drafts normally contain
`human_review_status: ai_draft_needs_human_review`. If
`../paper-workflow/scripts/review_selected_notes.py` requires
`human_review_status: approved_for_import`, a human reviewer must edit the
selected generated note draft frontmatter after review. Editing
`selected_notes.yaml` alone may not be enough.

## PMC-Available Candidates And Evidence Paths

{pmc_candidates}

Text exports:

{pmc_text_paths}

{full_text_status}

{pmc_status}

## AI Backend Interface

{ai_backend_status}

- manifest: `{ai_backend_state.get("manifest_path", "") or "not generated"}`
- prompt packet generated: `{str(bool(ai_backend_state.get("prompt_packet_generated"))).lower()}`
- mock backend used: `{str(bool(ai_backend_state.get("mock_response_used"))).lower()}`
- external AI backend: `{ai_backend_state.get("selected_backend_name", "disabled")}`
- external AI review status: `{external_ai_review_status}`

Generated full-text-level drafts require human review and editing before any
selection for import. This run did not retrieve publisher full text outside PMC,
read PDFs or supplements, parse Bookends, or write to `Papers/`.

## Limitations

- Screening is deterministic local heuristic/mock screening, not external AI or human scientific judgment.
- Evidence is limited to PubMed metadata and abstract text.
- PMC text exports, if present, are public XML-derived review artifacts.
- Full-text draft notes, if present, are deterministic public PMC XML/text drafts and still require human review.
- No supplement, PDF, Bookends, or publisher-site claims should be inferred from generated drafts.

## Discussion Instructions

Discuss whether any abstract-only draft, public PMC XML/text export, or
full-text-level draft is worth deeper human review. `selected_notes.yaml` should
remain safe by default until a human edits it to select reviewed notes for the
selected-note importer under the repository's normal review rules.

Legacy review reminder: `selected_notes.yaml` should remain safe by default.

Suggested review questions:

1. Which candidates are relevant enough to review against the available public evidence?
2. Which abstract-only candidates need public full-text review before import?
3. Which public PMC full-text drafts are accurate enough after human review to import?
4. Which candidates should stay skipped because evidence is too thin or off-goal?
5. Which selected drafts need `human_review_status: approved_for_import` frontmatter edits?

Copy-paste-ready AI discussion prompt:

```text
You are helping discuss import decisions for a local PubMed AI triage export.
Use only the relative paths and public-review metadata in this handoff. Do not
approve imports yourself. Separate abstract-only candidates from public PMC
full-text candidates. For each candidate, recommend one of: new, replace_abstract_only, skip, or needs_more_human_review. Remind me that
generated notes require human review, selected note draft frontmatter may need
human_review_status: approved_for_import, selected_notes.yaml must be edited
manually, the importer should be run first as a dry run, and Papers/ is not
written by the triage script.
```

Private, restricted, PDF-derived, Bookends-derived, or unreviewed material must
not be approved. OpenAI-derived suggestions, when present, are suggestions only
and must not change `human_review_status` without human review. The PubMed AI triage script does not write to `Papers/`; import is a separate explicit step.

## Safe Default Selection

`selected_notes.yaml` is intentionally:

```yaml
notes: []
```

Preferred safe path:

1. Human reviews the generated note draft.
2. Human edits the selected generated note draft frontmatter to `approved_for_import` if appropriate.
3. Human edits `selected_notes.yaml`.
4. Human runs `../paper-workflow/scripts/review_selected_notes.py` first in dry-run mode.
5. Human runs the importer with `--apply` only after review.
"""


def render_selected_notes() -> str:
    return """# Empty by design for PubMed abstract-level triage.
# Generated drafts require human review before selection.
notes: []
"""


def render_selected_notes_instructions() -> str:
    return """# Selected Notes Instructions

`selected_notes.yaml` is safe by default and must remain empty until a human
reviewer selects generated drafts:

```yaml
notes: []
```

Use `../paper-workflow/scripts/review_selected_notes.py` first in dry-run mode. Use `--apply`
only after reviewing the importer packet.

Safe action examples:

```yaml
notes:
  - id: synthetic_new_note
    source: generated_notes/full_text_level/example_public_full_text.md
    action: new

  - id: synthetic_replace_abstract_note
    source: generated_notes/full_text_level/example_public_full_text.md
    action: replace_abstract_only
    existing: Papers/example_existing_abstract_only.md

  - id: synthetic_skip_note
    source: generated_notes/abstract_level/example_abstract_only.md
    action: skip
```

Abstract-only drafts:

- expected note depth: `abstract_metadata_only`
- read depth: `pubmed_abstract_reviewed`

Public PMC full-text drafts:

- expected note depth: `public_full_text_reviewed`
- read depth: `public_full_text_reviewed`

OpenAI-derived suggestions:

- external AI suggestions only
- not human approval
- should not change `human_review_status` without human review

If the importer requires generated note frontmatter to contain
`human_review_status: approved_for_import`, a human reviewer must update the
selected generated note draft after review. `selected_notes.yaml` approval alone
may not be enough when a draft still says
`human_review_status: ai_draft_needs_human_review`.

Do not approve private, restricted, PDF-derived, Bookends-derived, or unreviewed
material. The PubMed AI triage script does not write to `Papers/`, does not
invoke the importer, and does not perform Git actions.
"""


def chatgpt_packet_filename(topic_slug: str, timestamp: str, suffix: str) -> str:
    return f"CHATGPT_CREATE_NOTES_PACKET_{topic_slug}_{timestamp}{suffix}"


def packet_record_entry(
    record: dict[str, Any],
    screening: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "pmid": clean_text(record.get("pmid")),
        "title": clean_text(record.get("title")),
        "authors": normalize_authors(record.get("authors")),
        "year": clean_text(record.get("year")),
        "journal": clean_text(record.get("journal")),
        "doi": clean_text(record.get("doi")),
        "pmcid": clean_text(record.get("pmcid")),
        "abstract": clean_text(record.get("abstract")) or "Not available in packet.",
        "note_depth": "abstract_metadata_only",
        "read_depth": "pubmed_abstract_reviewed",
        "human_review_status": "ai_draft_needs_human_review",
        "source_provenance": ["PubMed metadata", "PubMed abstract"],
        "screening": ai_screening_entry(screening),
    }


def packet_public_pmc_entry(run_folder: Path, pmc_result: dict[str, Any]) -> dict[str, Any] | None:
    if not (
        pmc_result.get("pmc_retrieval_succeeded")
        and pmc_result.get("pmc_text_extracted")
        and pmc_result.get("local_xml_export_path")
        and pmc_result.get("local_text_export_path")
    ):
        return None
    xml_path = run_folder / clean_text(pmc_result.get("local_xml_export_path"))
    text_path = run_folder / clean_text(pmc_result.get("local_text_export_path"))
    if not (
        is_relative_to(xml_path.resolve(), run_folder.resolve())
        and is_relative_to(text_path.resolve(), run_folder.resolve())
        and xml_path.is_file()
        and text_path.is_file()
    ):
        return None
    xml_text = xml_path.read_text(encoding="utf-8")
    text_export = text_path.read_text(encoding="utf-8")
    evidence = extract_pmc_draft_evidence(xml_text, text_export)
    return {
        "pmid": clean_text(pmc_result.get("pmid")),
        "pmcid": clean_text(pmc_result.get("pmcid")),
        "title": clean_text(pmc_result.get("title")),
        "public_retrieval_source": clean_text(pmc_result.get("public_retrieval_source")),
        "relative_xml_export_path": clean_text(pmc_result.get("local_xml_export_path")),
        "relative_text_export_path": clean_text(pmc_result.get("local_text_export_path")),
        "note_depth": "public_full_text_reviewed",
        "read_depth": "public_full_text_reviewed",
        "human_review_status": "ai_draft_needs_human_review",
        "source_provenance": ["PubMed metadata", "PubMed abstract", "public PMC XML text"],
        "summary": evidence["summary"] or "Not available in packet.",
        "abstract_sentences": evidence["abstract_sentences"],
        "body_sentences": evidence["body_sentences"],
        "section_bullets": evidence["section_bullets"],
        "figure_captions": evidence["figure_captions"],
    }


def build_chatgpt_note_packet_data(
    *,
    run_folder: Path,
    records: list[dict[str, Any]],
    screening_results: list[dict[str, Any]],
    pmc_availability_results: list[dict[str, Any]],
    generated_note_paths: list[str],
    generated_full_text_note_paths: list[str],
) -> dict[str, Any]:
    screening_by_pmid = {
        clean_text(screening.get("pmid")): screening for screening in screening_results
    }
    abstract_candidates = [
        packet_record_entry(record, screening_by_pmid.get(clean_text(record.get("pmid"))))
        for record in records
    ]
    public_pmc_candidates = [
        entry
        for item in pmc_availability_results
        if (entry := packet_public_pmc_entry(run_folder, item)) is not None
    ]
    source_values = [
        ("chatgpt_pubmed_records", abstract_candidates),
        ("chatgpt_public_pmc_candidates", public_pmc_candidates),
    ]
    assert_ai_public_only_gate(source_values)
    return {
        "abstract_candidates": abstract_candidates,
        "public_pmc_candidates": public_pmc_candidates,
        "generated_abstract_note_paths": generated_note_paths,
        "generated_full_text_note_paths": generated_full_text_note_paths,
    }


def render_abstract_candidates_md(abstract_candidates: list[dict[str, Any]]) -> str:
    if not abstract_candidates:
        return "# Abstract Candidates\n\nNo PubMed abstract candidates were included.\n"
    lines = ["# Abstract Candidates", ""]
    for candidate in abstract_candidates:
        lines.extend(
            [
                f"## {candidate['title'] or 'Untitled PubMed record'}",
                "",
                f"- PMID: `{candidate['pmid'] or 'Not available in packet.'}`",
                f"- Year: `{candidate['year'] or 'Not available in packet.'}`",
                f"- Journal: {candidate['journal'] or 'Not available in packet.'}",
                f"- DOI: `{candidate['doi'] or 'Not available in packet.'}`",
                f"- PMCID: `{candidate['pmcid'] or 'Not available in packet.'}`",
                f"- note_depth: `{candidate['note_depth']}`",
                f"- read_depth: `{candidate['read_depth']}`",
                f"- human_review_status: `{candidate['human_review_status']}`",
                "",
                "### Abstract",
                "",
                candidate["abstract"] or "Not available in packet.",
                "",
                "### Screening",
                "",
                json.dumps(candidate["screening"], indent=2, sort_keys=True, ensure_ascii=False),
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def render_pmc_candidates_md(public_pmc_candidates: list[dict[str, Any]]) -> str:
    if not public_pmc_candidates:
        return "# Public PMC Full-Text Candidates\n\nNo public PMC XML/text candidates were included.\n"
    lines = ["# Public PMC Full-Text Candidates", ""]
    for candidate in public_pmc_candidates:
        section_bullets = candidate.get("section_bullets") or []
        section_text = "\n".join(
            f"- {item.get('title', 'Untitled section')}: {item.get('text', '')}"
            for item in section_bullets
        ) or "- Not available in packet."
        body_sentences = "\n".join(f"- {item}" for item in candidate.get("body_sentences", []))
        body_sentences = body_sentences or "- Not available in packet."
        figure_captions = "\n".join(f"- {item}" for item in candidate.get("figure_captions", []))
        figure_captions = figure_captions or "- Not available in packet."
        lines.extend(
            [
                f"## {candidate['title'] or 'Untitled public PMC candidate'}",
                "",
                f"- PMID: `{candidate['pmid'] or 'Not available in packet.'}`",
                f"- PMCID: `{candidate['pmcid'] or 'Not available in packet.'}`",
                f"- public retrieval source: `{candidate['public_retrieval_source']}`",
                f"- relative XML export: `{candidate['relative_xml_export_path']}`",
                f"- relative text export: `{candidate['relative_text_export_path']}`",
                f"- note_depth: `{candidate['note_depth']}`",
                f"- read_depth: `{candidate['read_depth']}`",
                f"- human_review_status: `{candidate['human_review_status']}`",
                "",
                "### Public PMC XML/Text Summary",
                "",
                candidate["summary"] or "Not available in packet.",
                "",
                "### Section-Level Evidence",
                "",
                section_text,
                "",
                "### Body Sentences",
                "",
                body_sentences,
                "",
                "### Figure Captions In Public XML",
                "",
                figure_captions,
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def render_chatgpt_expected_output_schema() -> str:
    return """# Expected Output Schema

Return a ZIP-ready Markdown tree in the response:

```text
generated_notes/
  abstract_level/*.md
  full_text_level/*.md

selected_notes.yaml draft suggestion
review_summary.md
```

Each generated note must be English Markdown with YAML frontmatter containing:

For abstract-only notes generated from PubMed metadata and PubMed abstract only:

```yaml
source: pubmed_ai_triage_chatgpt_packet
note_depth: abstract_metadata_only
security_tier: public
read_depth: pubmed_abstract_reviewed
human_review_status: ai_draft_needs_human_review
source_provenance:
  - PubMed metadata
  - PubMed abstract
```

For notes generated from included public PMC XML/text evidence:

```yaml
source: pubmed_ai_triage_chatgpt_packet
note_depth: public_full_text_reviewed
security_tier: public
read_depth: public_full_text_reviewed
human_review_status: ai_draft_needs_human_review
source_provenance:
  - PubMed metadata
  - PubMed abstract
  - public PMC XML text
```

Use `abstract_metadata_only` and `pubmed_abstract_reviewed` for abstract-only
notes, and do not include `public PMC XML text` in `source_provenance` unless
public PMC XML/text evidence was actually used for that specific generated note.
Use `public_full_text_reviewed` for notes based on included public PMC XML/text
evidence. Use `security_tier: public` only because this packet is restricted to
public PubMed/PMC evidence.

Do not mark anything `approved_for_import`. A selected-notes suggestion is only
a draft for human review, not approval.
"""


def render_chatgpt_start_here(topic_slug: str, timestamp: str, zip_name: str) -> str:
    return f"""# Start Here

This local packet was generated for manual drag-and-drop into ChatGPT.

- Topic slug: `{topic_slug}`
- Timestamp: `{timestamp}`
- Primary prompt: `CHATGPT_CREATE_NOTES_PACKET.md`
- ZIP archive: `{zip_name}`

Drag either the ZIP archive or the primary Markdown packet into ChatGPT. The
script did not upload anything automatically and did not call an external AI
API for this packet.

Review any generated notes before using the repository importer workflow. The
selected-notes template is intentionally:

```yaml
notes: []
```
"""


def render_source_manifest(
    *,
    goal: str,
    topic_slug: str,
    timestamp: str,
    query: str,
    sort_mode: str,
    abstract_candidates: list[dict[str, Any]],
    public_pmc_candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "workflow_name": WORKFLOW_NAME,
        "packet_type": "chatgpt_note_packet",
        "topic_slug": topic_slug,
        "created_timestamp": timestamp,
        "goal": goal,
        "query": query,
        "pubmed_sort_mode": sort_mode,
        "record_counts": {
            "pubmed_records": len(abstract_candidates),
            "abstract_candidates": len(abstract_candidates),
            "public_pmc_full_text_candidates": len(public_pmc_candidates),
        },
        "included_public_sources": [
            "PubMed metadata",
            "PubMed abstracts",
            "public PMC XML/text exported by this run",
        ],
        "excluded_sources": [
            "PDFs",
            "Bookends files",
            "existing paper-note contents",
            "private notes",
            "applications, meetings, collaborators, grants, manuscripts, raw data",
            "local absolute paths and local-file links",
            "authentication material",
        ],
        "pubmed_metadata_included": True,
        "pubmed_abstracts_included": True,
        "public_pmc_xml_text_included": bool(public_pmc_candidates),
        "pdfs_included": False,
        "bookends_files_included": False,
        "existing_paper_notes_included": False,
        "private_notes_included": False,
        "external_ai_api_called": False,
        "automatic_upload_performed": False,
        "papers_write_performed": False,
        "importer_invoked": False,
        "git_actions_performed": False,
    }


def render_chatgpt_primary_packet(
    *,
    goal: str,
    topic_slug: str,
    timestamp: str,
    query: str,
    sort_mode: str,
    abstract_candidates: list[dict[str, Any]],
    public_pmc_candidates: list[dict[str, Any]],
    abstract_candidates_md: str,
    pmc_candidates_md: str,
    source_manifest: dict[str, Any],
) -> str:
    return f"""# ChatGPT Create Notes Packet

## Task

Generate draft candidate Markdown paper notes from only the public evidence in
this packet.

- User goal: {goal}
- Topic slug: `{topic_slug}`
- Timestamp: `{timestamp}`
- PubMed query: {query or "Not available in packet."}
- PubMed sort mode: `{sort_mode}`
- PubMed record count: `{len(abstract_candidates)}`
- Abstract candidate count: `{len(abstract_candidates)}`
- Public PMC full-text candidate count: `{len(public_pmc_candidates)}`

## Evidence Rules

Use only the included public PubMed metadata, public PubMed abstracts, and
public PMC XML/text-derived evidence. `security_tier: public` is appropriate
only because this packet is restricted to public PubMed/PMC evidence.
Do not use prior memory, private notes, restricted evidence, unpublished evidence,
PDFs, Bookends files, local paths, repository-private evidence,
outside assumptions, external browsing, or any source not included in this
packet.

Do not invent PMIDs, DOIs, titles, methods, results, citations, claims, figure
details, or any missing evidence. If evidence is missing, write `Not available
in packet`.

## Required Note Status

- abstract-only notes: `note_depth: abstract_metadata_only`
- abstract-only read depth: `read_depth: pubmed_abstract_reviewed`
- public PMC notes: `note_depth: public_full_text_reviewed`
- public PMC read depth: `read_depth: public_full_text_reviewed`
- all generated notes: `security_tier: public`
- all generated notes: `human_review_status: ai_draft_needs_human_review`

Do not mark anything `approved_for_import`. A selected-notes suggestion is only
a draft suggestion, not approval. Final import requires human review and the
repository importer workflow.

## Source Provenance Rules

For abstract-only notes generated from PubMed metadata and PubMed abstract only,
use exactly:

```yaml
source: pubmed_ai_triage_chatgpt_packet
note_depth: abstract_metadata_only
security_tier: public
read_depth: pubmed_abstract_reviewed
human_review_status: ai_draft_needs_human_review
source_provenance:
  - PubMed metadata
  - PubMed abstract
```

Do not include `public PMC XML text` in an abstract-only note's
`source_provenance` unless public PMC XML/text evidence was actually used for
that specific generated note.

For notes generated from included public PMC XML/text evidence, use exactly:

```yaml
source: pubmed_ai_triage_chatgpt_packet
note_depth: public_full_text_reviewed
security_tier: public
read_depth: public_full_text_reviewed
human_review_status: ai_draft_needs_human_review
source_provenance:
  - PubMed metadata
  - PubMed abstract
  - public PMC XML text
```

## Requested Output

Return:

```text
generated_notes/
  abstract_level/*.md
  full_text_level/*.md

selected_notes.yaml draft suggestion
review_summary.md
```

The selected-notes draft suggestion must not approve import. Keep it clearly
labeled as a draft for human review.

## Source Provenance Summary

```json
{json.dumps(source_manifest, indent=2, sort_keys=True, ensure_ascii=False)}
```

## Abstract Candidates

{abstract_candidates_md}

## Public PMC Full-Text Candidates

{pmc_candidates_md}
"""


def sanitize_chatgpt_context_text(text: str) -> str:
    replacements = {
        "Papers/": "repository paper-note folder",
        "Applications/": "protected application-material folder",
        "Meeting_Notes/": "protected meeting-notes folder",
        "Meetings/": "protected meetings folder",
        "Collaborators/": "protected collaborator folder",
        "People/": "protected people folder",
        "Grants/": "protected grants folder",
        "Hypothesis/": "protected hypothesis folder",
        "Manuscripts_Internal/": "protected manuscript folder",
        "Indexes/PAPER_SOURCE_MAP.yaml": "protected paper-source map",
        "source_url": "source URL field",
        "file" + "://": "local-file URL scheme",
        "API key": "credential",
        "API-key": "credential",
        "OPENAI_API_KEY": "OpenAI credential environment value",
    }
    sanitized = text
    for old, new in replacements.items():
        sanitized = sanitized.replace(old, new)
    sanitized = re.sub("/" + r"Users/[^\s)]+", "[local path removed]", sanitized)
    return sanitized


def write_chatgpt_note_packet(
    *,
    run_folder: Path,
    goal: str,
    topic_slug: str,
    timestamp: str,
    query: str,
    sort_mode: str,
    records: list[dict[str, Any]],
    screening_results: list[dict[str, Any]],
    pmc_availability_results: list[dict[str, Any]],
    generated_note_paths: list[str],
    generated_full_text_note_paths: list[str],
) -> dict[str, str]:
    packet_folder = run_folder / "chatgpt_note_packet"
    public_sources = packet_folder / "public_sources"
    generated_context = packet_folder / "generated_context"
    public_sources.mkdir(parents=True, exist_ok=False)
    generated_context.mkdir(parents=True, exist_ok=False)

    packet_data = build_chatgpt_note_packet_data(
        run_folder=run_folder,
        records=records,
        screening_results=screening_results,
        pmc_availability_results=pmc_availability_results,
        generated_note_paths=generated_note_paths,
        generated_full_text_note_paths=generated_full_text_note_paths,
    )
    abstract_candidates = packet_data["abstract_candidates"]
    public_pmc_candidates = packet_data["public_pmc_candidates"]
    abstract_candidates_md = render_abstract_candidates_md(abstract_candidates)
    pmc_candidates_md = render_pmc_candidates_md(public_pmc_candidates)
    source_manifest = render_source_manifest(
        goal=goal,
        topic_slug=topic_slug,
        timestamp=timestamp,
        query=query,
        sort_mode=sort_mode,
        abstract_candidates=abstract_candidates,
        public_pmc_candidates=public_pmc_candidates,
    )

    zip_name = chatgpt_packet_filename(topic_slug, timestamp, ".zip")
    (packet_folder / "README_START_HERE.md").write_text(
        render_chatgpt_start_here(topic_slug, timestamp, zip_name),
        encoding="utf-8",
    )
    (packet_folder / "expected_output_schema.md").write_text(
        render_chatgpt_expected_output_schema(),
        encoding="utf-8",
    )
    (packet_folder / "selected_notes_template.yaml").write_text("notes: []\n", encoding="utf-8")
    (public_sources / "pubmed_records.json").write_text(
        json.dumps({"records": abstract_candidates}, indent=2, sort_keys=True, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )
    (public_sources / "abstract_candidates.md").write_text(
        abstract_candidates_md,
        encoding="utf-8",
    )
    (public_sources / "pmc_full_text_candidates.md").write_text(
        pmc_candidates_md,
        encoding="utf-8",
    )
    (public_sources / "source_manifest.json").write_text(
        json.dumps(source_manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (generated_context / "PUBMED_TRIAGE_SUMMARY.md").write_text(
        sanitize_chatgpt_context_text(
            (run_folder / "PUBMED_TRIAGE_SUMMARY.md").read_text(encoding="utf-8")
        ),
        encoding="utf-8",
    )
    (generated_context / "DISCUSS_IMPORT_TO_PAPERS.md").write_text(
        sanitize_chatgpt_context_text(
            (run_folder / "DISCUSS_IMPORT_TO_PAPERS.md").read_text(encoding="utf-8")
        ),
        encoding="utf-8",
    )

    primary_packet_path = packet_folder / "CHATGPT_CREATE_NOTES_PACKET.md"
    primary_packet_path.write_text(
        render_chatgpt_primary_packet(
            goal=goal,
            topic_slug=topic_slug,
            timestamp=timestamp,
            query=query,
            sort_mode=sort_mode,
            abstract_candidates=abstract_candidates,
            public_pmc_candidates=public_pmc_candidates,
            abstract_candidates_md=abstract_candidates_md,
            pmc_candidates_md=pmc_candidates_md,
            source_manifest=source_manifest,
        ),
        encoding="utf-8",
    )
    deterministic_primary_path = packet_folder / chatgpt_packet_filename(
        topic_slug, timestamp, ".md"
    )
    shutil.copyfile(primary_packet_path, deterministic_primary_path)

    zip_path = packet_folder / zip_name
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(packet_folder.rglob("*")):
            if path == zip_path or not path.is_file():
                continue
            archive.write(path, path.relative_to(packet_folder).as_posix())

    return {
        "packet_folder": packet_folder.as_posix(),
        "primary_packet": primary_packet_path.as_posix(),
        "deterministic_primary_packet": deterministic_primary_path.as_posix(),
        "zip_packet": zip_path.as_posix(),
    }


def find_chatgpt_packet_artifacts(run_folder: Path) -> dict[str, Path]:
    packet_folder = run_folder / "chatgpt_note_packet"
    primary_packet = packet_folder / "CHATGPT_CREATE_NOTES_PACKET.md"
    deterministic_packets = sorted(
        path
        for path in packet_folder.glob("CHATGPT_CREATE_NOTES_PACKET_*.md")
        if path.name != primary_packet.name
    )
    zip_packets = sorted(packet_folder.glob("CHATGPT_CREATE_NOTES_PACKET_*.zip"))
    if not primary_packet.is_file() or len(deterministic_packets) != 1 or len(zip_packets) != 1:
        raise FileNotFoundError("could not find generated ChatGPT packet Markdown and ZIP artifacts")
    return {
        "packet_folder": packet_folder,
        "primary_packet": primary_packet,
        "deterministic_primary_packet": deterministic_packets[0],
        "zip_packet": zip_packets[0],
    }


def safe_unique_destination(directory: Path, filename: str) -> Path:
    destination = directory / filename
    if not destination.exists():
        return destination
    stem = destination.stem
    suffix = destination.suffix
    for index in range(1, 1000):
        candidate = directory / f"{stem}_{index}{suffix}"
        if not candidate.exists():
            return candidate
    raise FileExistsError(f"could not choose a unique destination for {filename}")


def copy_packet_artifacts_to_downloads(
    *,
    primary_packet_path: Path,
    zip_packet_path: Path,
    downloads_dir: Path | None = None,
) -> dict[str, Path]:
    target_dir = (downloads_dir or (Path.home() / "Downloads")).expanduser()
    target_dir.mkdir(parents=True, exist_ok=True)
    copied_md = safe_unique_destination(target_dir, primary_packet_path.name)
    copied_zip = safe_unique_destination(target_dir, zip_packet_path.name)
    shutil.copyfile(primary_packet_path, copied_md)
    shutil.copyfile(zip_packet_path, copied_zip)
    return {"md": copied_md, "zip": copied_zip}


def reveal_packet_in_finder(zip_packet_path: Path, *, platform: str | None = None) -> bool:
    current_platform = platform or sys.platform
    if current_platform != "darwin":
        return False
    try:
        subprocess.run(["open", "-R", str(zip_packet_path)], check=True)
    except (OSError, subprocess.CalledProcessError):
        return False
    return True


def create_triage_export(
    *,
    goal: str,
    topic_slug: str,
    output_root: Path,
    timestamp: str,
    retmax: int,
    abstract_top_n: int,
    full_text_top_n: int,
    query: str,
    sort_mode: str = "best_match",
    input_pubmed_json: Path | None,
    input_pmc_fixtures: Path | None,
    check_pmc_full_text: bool,
    generate_full_text_drafts: bool,
    generate_chatgpt_note_packet: bool = False,
    pmc_top_n: int,
    screening_backend: str,
    ai_backend: str,
    allow_live_openai_api: bool,
    confirm_public_ai_export: bool,
    openai_model: str,
    repo_root: Path,
) -> Path:
    if generate_full_text_drafts and not check_pmc_full_text:
        raise ValueError("--generate-full-text-drafts requires --check-pmc-full-text")

    safe_output_root = ensure_safe_output_root(output_root, repo_root)
    run_folder = safe_output_root / f"{timestamp}_{topic_slug}"

    abstract_folder = run_folder / "generated_notes" / "abstract_level"
    full_text_folder = run_folder / "generated_notes" / "full_text_level"
    abstract_folder.mkdir(parents=True, exist_ok=False)
    full_text_folder.mkdir(parents=True, exist_ok=False)

    if input_pubmed_json is not None:
        records = load_pubmed_json(
            input_pubmed_json,
            repo_root,
            ai_public_only_gate_requested=ai_backend_requested(ai_backend),
        )
        records = sort_pubmed_records(records, sort_mode)
    elif query:
        records = fetch_pubmed_records(query, retmax, sort_mode)
    else:
        records = []
    safe_pmc_fixture_dir = (
        ensure_safe_pmc_fixture_dir(input_pmc_fixtures, repo_root)
        if input_pmc_fixtures is not None
        else None
    )

    skeleton_only = not records and not query and input_pubmed_json is None
    write_pubmed_results(run_folder, records)

    screening_results = (
        screen_records(records, goal=goal, query=query, backend=screening_backend)
        if records
        else []
    )
    (run_folder / "abstract_screening_results.json").write_text(
        json.dumps({"screening_results": screening_results}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    generated_note_paths = write_generated_notes(
        run_folder=run_folder,
        records=records,
        screening_results=screening_results,
        goal=goal,
        abstract_top_n=abstract_top_n,
    )
    (full_text_folder / "README.md").write_text(render_full_text_placeholder(), encoding="utf-8")
    pmc_availability_results: list[dict[str, Any]] = []
    generated_full_text_note_paths: list[str] = []
    if check_pmc_full_text:
        pmc_availability_results = write_pmc_availability_exports(
            run_folder=run_folder,
            records=records,
            screening_results=screening_results,
            pmc_top_n=pmc_top_n,
            fixture_dir=safe_pmc_fixture_dir,
            ai_public_only_gate_requested=ai_backend_requested(ai_backend),
        )
        if generate_full_text_drafts:
            generated_full_text_note_paths = write_full_text_draft_notes(
                run_folder=run_folder,
                records=records,
                screening_results=screening_results,
                pmc_availability_results=pmc_availability_results,
                goal=goal,
                pmc_top_n=pmc_top_n,
            )
        (run_folder / "pmc_availability_results.json").write_text(
            json.dumps({"pmc_availability_results": pmc_availability_results}, indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
    ai_backend_state = write_ai_backend_interface(
        run_folder=run_folder,
        ai_backend=ai_backend,
        goal=goal,
        records=records,
        screening_results=screening_results,
        pmc_availability_results=pmc_availability_results,
        generated_note_paths=generated_note_paths,
        generated_full_text_note_paths=generated_full_text_note_paths,
        allow_live_openai_api=allow_live_openai_api,
        confirm_public_ai_export=confirm_public_ai_export,
        openai_model=openai_model,
    )
    manifest = build_manifest(
        goal=goal,
        topic_slug=topic_slug,
        timestamp=timestamp,
        retmax=retmax,
        abstract_top_n=abstract_top_n,
        full_text_top_n=full_text_top_n,
        query=query,
        sort_mode=sort_mode,
        input_pubmed_json=input_pubmed_json is not None,
        records=records,
        screening_backend=screening_backend,
        ai_screening_performed=bool(records),
        generated_note_paths=generated_note_paths,
        generated_full_text_note_paths=generated_full_text_note_paths,
        check_pmc_full_text=check_pmc_full_text,
        generate_full_text_drafts=generate_full_text_drafts,
        generate_chatgpt_note_packet=generate_chatgpt_note_packet,
        pmc_top_n=pmc_top_n,
        input_pmc_fixtures=input_pmc_fixtures is not None,
        pmc_availability_results=pmc_availability_results,
        skeleton_only=skeleton_only,
        ai_backend_state=ai_backend_state,
    )
    (run_folder / "pubmed_triage_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (run_folder / "PUBMED_TRIAGE_SUMMARY.md").write_text(
        render_summary(
            goal=goal,
            topic_slug=topic_slug,
            timestamp=timestamp,
            query=query,
            sort_mode=sort_mode,
            records=records,
            screening_backend=screening_backend,
            generated_note_paths=generated_note_paths,
            generated_full_text_note_paths=generated_full_text_note_paths,
            check_pmc_full_text=check_pmc_full_text,
            generate_full_text_drafts=generate_full_text_drafts,
            pmc_availability_results=pmc_availability_results,
            input_pubmed_json=input_pubmed_json is not None,
            input_pmc_fixtures=input_pmc_fixtures is not None,
            skeleton_only=skeleton_only,
            ai_backend_state=ai_backend_state,
        ),
        encoding="utf-8",
    )
    (run_folder / "DISCUSS_IMPORT_TO_PAPERS.md").write_text(
        render_discussion(
            goal=goal,
            topic_slug=topic_slug,
            timestamp=timestamp,
            query=query,
            records=records,
            screening_backend=screening_backend,
            screening_results=screening_results,
            generated_note_paths=generated_note_paths,
            generated_full_text_note_paths=generated_full_text_note_paths,
            check_pmc_full_text=check_pmc_full_text,
            generate_full_text_drafts=generate_full_text_drafts,
            pmc_availability_results=pmc_availability_results,
            ai_backend_state=ai_backend_state,
        ),
        encoding="utf-8",
    )
    (run_folder / "selected_notes.yaml").write_text(render_selected_notes(), encoding="utf-8")
    (run_folder / "selected_notes_instructions.md").write_text(
        render_selected_notes_instructions(),
        encoding="utf-8",
    )
    if generate_chatgpt_note_packet:
        write_chatgpt_note_packet(
            run_folder=run_folder,
            goal=goal,
            topic_slug=topic_slug,
            timestamp=timestamp,
            query=query,
            sort_mode=sort_mode,
            records=records,
            screening_results=screening_results,
            pmc_availability_results=pmc_availability_results,
            generated_note_paths=generated_note_paths,
            generated_full_text_note_paths=generated_full_text_note_paths,
        )

    return run_folder


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run safe PubMed abstract-level triage exports."
    )
    parser.add_argument(
        "--goal",
        required=True,
        type=validate_goal,
        help="One-sentence human research goal.",
    )
    parser.add_argument(
        "--topic-slug",
        required=True,
        type=validate_topic_slug,
        help="Safe topic slug for the export folder.",
    )
    parser.add_argument(
        "--query",
        default="",
        help="Public PubMed query for live metadata/abstract retrieval.",
    )
    parser.add_argument(
        "--sort",
        default="best_match",
        type=validate_pubmed_sort,
        help="Safe PubMed sort mode: best_match, newest, or oldest.",
    )
    parser.add_argument(
        "--input-pubmed-json",
        default=None,
        type=Path,
        help="Synthetic or previously exported PubMed-like JSON input for offline runs.",
    )
    parser.add_argument(
        "--input-pmc-fixtures",
        default=None,
        type=Path,
        help="Directory of synthetic public PMC XML fixtures for offline PMC checks.",
    )
    parser.add_argument(
        "--check-pmc-full-text",
        action="store_true",
        help="Check public PMC availability and export public PMC XML/text evidence.",
    )
    parser.add_argument(
        "--generate-full-text-drafts",
        action="store_true",
        help=(
            "Generate deterministic public PMC full-text Markdown draft notes "
            "from XML/text exported in this same run. Requires --check-pmc-full-text."
        ),
    )
    parser.add_argument(
        "--generate-chatgpt-note-packet",
        action="store_true",
        help="Generate an API-free manual ChatGPT note packet under the run folder.",
    )
    parser.add_argument(
        "--copy-packet-to-downloads",
        action="store_true",
        help="Copy the ChatGPT packet Markdown and ZIP artifacts to ~/Downloads.",
    )
    parser.add_argument(
        "--reveal-packet",
        action="store_true",
        help="Reveal the copied ZIP packet in Finder on macOS when possible.",
    )
    parser.add_argument(
        "--screening-backend",
        choices=("heuristic", "mock"),
        default="heuristic",
        help="Local deterministic screening backend. No external AI APIs are called.",
    )
    parser.add_argument(
        "--ai-backend",
        default="disabled",
        type=validate_ai_backend,
        help=(
            "Safety-gated AI backend interface: disabled, heuristic, mock, "
            "prompt_packet, or openai. OpenAI requires separate live opt-in flags."
        ),
    )
    parser.add_argument(
        "--allow-live-openai-api",
        action="store_true",
        help="Explicitly allow the disabled-by-default live OpenAI Responses API adapter.",
    )
    parser.add_argument(
        "--confirm-public-ai-export",
        action="store_true",
        help="Confirm the backend packet contains only public PubMed/PMC content for export.",
    )
    parser.add_argument(
        "--openai-model",
        default=DEFAULT_OPENAI_MODEL,
        type=validate_openai_model,
        help="OpenAI model for --ai-backend openai. The default is gpt-5.5.",
    )
    parser.add_argument(
        "--output-root",
        default=str(DEFAULT_OUTPUT_ROOT),
        type=Path,
        help="Output root. Defaults to exports/pubmed_ai_triage.",
    )
    parser.add_argument(
        "--timestamp",
        default=default_timestamp(),
        type=validate_timestamp,
        help="Deterministic timestamp token for tests or review runs.",
    )
    parser.add_argument(
        "--retmax",
        default=50,
        type=positive_int,
        help="Maximum PubMed records to retrieve for live queries.",
    )
    parser.add_argument(
        "--abstract-top-n",
        default=5,
        type=nonnegative_int,
        help="Number of top abstract-level draft notes to generate.",
    )
    parser.add_argument(
        "--full-text-top-n",
        default=5,
        type=nonnegative_int,
        help="Compatibility planning value; --pmc-top-n controls Phase 3b draft count.",
    )
    parser.add_argument(
        "--pmc-top-n",
        default=5,
        type=nonnegative_int,
        help="Number of screened candidates to check for public PMC XML/text export.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path.cwd()
    try:
        if (args.copy_packet_to_downloads or args.reveal_packet) and not args.generate_chatgpt_note_packet:
            raise ValueError(
                "--copy-packet-to-downloads and --reveal-packet require "
                "--generate-chatgpt-note-packet"
            )
        run_folder = create_triage_export(
            goal=args.goal.strip(),
            topic_slug=args.topic_slug,
            output_root=args.output_root,
            timestamp=args.timestamp,
            retmax=args.retmax,
            abstract_top_n=args.abstract_top_n,
            full_text_top_n=args.full_text_top_n,
            query=args.query.strip(),
            sort_mode=args.sort,
            input_pubmed_json=args.input_pubmed_json,
            input_pmc_fixtures=args.input_pmc_fixtures,
            check_pmc_full_text=args.check_pmc_full_text,
            generate_full_text_drafts=args.generate_full_text_drafts,
            generate_chatgpt_note_packet=args.generate_chatgpt_note_packet,
            pmc_top_n=args.pmc_top_n,
            screening_backend=args.screening_backend,
            ai_backend=args.ai_backend,
            allow_live_openai_api=args.allow_live_openai_api,
            confirm_public_ai_export=args.confirm_public_ai_export,
            openai_model=args.openai_model,
            repo_root=repo_root,
        )
        downloads_paths: dict[str, Path] = {}
        reveal_succeeded = False
        packet_artifacts: dict[str, Path] = {}
        if args.generate_chatgpt_note_packet:
            packet_artifacts = find_chatgpt_packet_artifacts(run_folder)
            packet_md = packet_artifacts["deterministic_primary_packet"]
            packet_zip = packet_artifacts["zip_packet"]
            if args.copy_packet_to_downloads:
                downloads_paths = copy_packet_artifacts_to_downloads(
                    primary_packet_path=packet_md,
                    zip_packet_path=packet_zip,
                )
            if args.reveal_packet:
                reveal_target = downloads_paths.get("zip", packet_zip)
                reveal_succeeded = reveal_packet_in_finder(reveal_target)
    except FileExistsError:
        print("error: output run folder already exists", flush=True)
        return 2
    except (OSError, ValueError, ET.ParseError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", flush=True)
        return 2

    print(f"Created PubMed AI triage export: {run_folder}")
    print("Inspect these files next:")
    print(f"- {run_folder / 'PUBMED_TRIAGE_SUMMARY.md'}")
    print(f"- {run_folder / 'DISCUSS_IMPORT_TO_PAPERS.md'}")
    print(f"- {run_folder / 'selected_notes.yaml'}")
    print(f"- {run_folder / 'selected_notes_instructions.md'}")
    print(f"- {run_folder / 'pubmed_triage_manifest.json'}")
    print(f"- {run_folder / 'abstract_screening_results.json'}")
    print(f"- {run_folder / 'generated_notes' / 'abstract_level'}")
    if args.check_pmc_full_text:
        print(f"- {run_folder / 'pmc_availability_results.json'}")
        print(f"- {run_folder / 'pmc_full_text'}")
    if args.generate_full_text_drafts:
        print(f"- {run_folder / 'generated_notes' / 'full_text_level'}")
    if ai_backend_requested(args.ai_backend):
        print(f"- {run_folder / 'ai_backend'}")
    if args.generate_chatgpt_note_packet:
        packet_artifacts = packet_artifacts or find_chatgpt_packet_artifacts(run_folder)
        packet_folder = packet_artifacts["packet_folder"]
        packet_md = packet_artifacts["deterministic_primary_packet"]
        packet_zip = packet_artifacts["zip_packet"]
        print("ChatGPT drag-and-drop packet:")
        print(f"- run folder: {run_folder}")
        print(f"- packet folder: {packet_folder}")
        print(f"- packet Markdown: {packet_md}")
        print(f"- packet ZIP: {packet_zip}")
        if downloads_paths:
            print(f"- Downloads Markdown: {downloads_paths['md']}")
            print(f"- Downloads ZIP: {downloads_paths['zip']}")
        if args.reveal_packet and not reveal_succeeded:
            reveal_target = downloads_paths.get("zip", packet_zip)
            print(f"- Finder reveal was not available; ZIP path: {reveal_target}")
        print("Drag and drop the ZIP or Markdown packet into ChatGPT.")
        print("Do not commit generated exports or Downloads packet files.")
        print("Review generated notes before importing them with the repository workflow.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
