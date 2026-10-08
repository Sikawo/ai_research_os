#!/usr/bin/env python3
"""Build manual AI prompt packets from Bookends EndNote XML exports.

This MVP is intentionally conservative:
- Bookends attachment files are read-only inputs.
- PDFs are never copied, renamed, moved, deleted, or modified.
- No external AI backend is called.
- One source record maps to one future Markdown paper note.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
import sys
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable


SKILL_ROOT = Path(__file__).resolve().parents[1]
STORAGE_ALIAS = "bookends_attachments"
WRITE_WRITTEN = "written"
WRITE_WOULD_WRITE = "would_write"
WRITE_UNCHANGED = "unchanged"


@dataclass
class Attachment:
    local_path: Path
    storage_alias: str
    relative_path: str | None
    original_filename: str
    exists: bool
    file_size_bytes: int | None = None
    sha256: str | None = None


@dataclass
class PaperRecord:
    record_id: str
    title: str = ""
    authors: list[str] = field(default_factory=list)
    first_author: str = ""
    journal: str = ""
    year: str = ""
    volume: str = ""
    issue: str = ""
    pages: str = ""
    doi: str = ""
    pmid: str = ""
    pmcid: str = ""
    pubmed_url: str = ""
    abstract: str = ""
    attachments: list[Attachment] = field(default_factory=list)


@dataclass
class RouteMetadata:
    source: str = "bookends_xml"
    note_depth: str = "abstract_metadata_only"
    security_tier: str = "public"
    status: str = "draft"
    priority: str = ""
    projects: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value).strip()


def element_text(element: ET.Element | None) -> str:
    if element is None:
        return ""
    return clean_text(" ".join(t for t in element.itertext() if t))


def raw_element_text(element: ET.Element | None) -> str:
    if element is None:
        return ""
    return "".join(t for t in element.itertext() if t).strip()


def direct_child(parent: ET.Element, *names: str) -> ET.Element | None:
    wanted = {name.lower() for name in names}
    for child in list(parent):
        if local_name(child.tag) in wanted:
            return child
    return None


def direct_children(parent: ET.Element, *names: str) -> list[ET.Element]:
    wanted = {name.lower() for name in names}
    return [child for child in list(parent) if local_name(child.tag) in wanted]


def text_from_path(parent: ET.Element, path_options: Iterable[tuple[str, ...]]) -> str:
    for path in path_options:
        current: ET.Element | None = parent
        for name in path:
            if current is None:
                break
            current = direct_child(current, name)
        text = element_text(current)
        if text:
            return text
    return ""


def all_text_for_tags(parent: ET.Element, names: Iterable[str]) -> list[str]:
    wanted = {name.lower() for name in names}
    values: list[str] = []
    for element in parent.iter():
        if local_name(element.tag) in wanted:
            text = element_text(element)
            if text:
                values.append(text)
    return values


def extract_authors(record: ET.Element) -> list[str]:
    authors_parent = None
    contributors = direct_child(record, "contributors")
    if contributors is not None:
        authors_parent = direct_child(contributors, "authors")
    if authors_parent is None:
        authors_parent = direct_child(record, "authors")

    authors: list[str] = []
    if authors_parent is not None:
        for child in list(authors_parent):
            if local_name(child.tag) in {"author", "style"}:
                text = element_text(child)
                if text:
                    authors.append(text)

    if not authors:
        authors = all_text_for_tags(record, ["author"])
    return dedupe(authors)


def dedupe(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = value.strip()
        if key and key not in seen:
            seen.add(key)
            result.append(key)
    return result


def first_author_name(authors: list[str]) -> str:
    if not authors:
        return ""
    first = authors[0].strip()
    if "," in first:
        return first.split(",", 1)[0].strip()
    return first.split()[-1].strip() if first.split() else first


def extract_year(record: ET.Element) -> str:
    text = text_from_path(record, [("dates", "year"), ("date",), ("year",)])
    match = re.search(r"(19|20)\d{2}", text)
    return match.group(0) if match else text


def normalize_doi(value: str) -> str:
    value = clean_text(value)
    value = re.sub(r"^https?://(dx\.)?doi\.org/", "", value, flags=re.I)
    value = re.sub(r"^doi:\s*", "", value, flags=re.I)
    return value.strip()


def extract_identifier(record: ET.Element, label_patterns: Iterable[str]) -> str:
    labels = [re.compile(pattern, re.I) for pattern in label_patterns]
    for element in record.iter():
        text = element_text(element)
        if not text:
            continue
        for label in labels:
            match = label.search(text)
            if match:
                return clean_text(match.group(1) if match.groups() else text)
    return ""


def extract_doi(record: ET.Element) -> str:
    candidates = all_text_for_tags(
        record,
        ["electronic-resource-num", "doi", "electronic-resource-number"],
    )
    for candidate in candidates:
        doi = normalize_doi(candidate)
        if doi:
            return doi
    text = element_text(record)
    match = re.search(r"\b10\.\d{4,9}/[^\s\"<>]+", text, flags=re.I)
    return normalize_doi(match.group(0)) if match else ""


def extract_pubmed_fields(record: ET.Element) -> tuple[str, str, str]:
    pmid = extract_identifier(record, [r"\bPMID\s*:?\s*(\d+)", r"pubmed.*?(\d{5,})"])
    pmcid = extract_identifier(record, [r"\bPMCID\s*:?\s*(PMC\d+)", r"\b(PMC\d+)\b"])

    pubmed_url = ""
    for value in collect_url_values(record):
        if "pubmed.ncbi.nlm.nih.gov" in value or "ncbi.nlm.nih.gov/pubmed" in value:
            pubmed_url = value.strip()
            if not pmid:
                match = re.search(r"/(\d{5,})(?:/|$|\?)", pubmed_url)
                if match:
                    pmid = match.group(1)
            break

    return pmid, pmcid, pubmed_url


def collect_url_values(record: ET.Element) -> list[str]:
    values: list[str] = []
    for element in record.iter():
        name = local_name(element.tag)
        is_leaf = len(list(element)) == 0
        is_url_field = name == "url" or name in {"file-url", "pdf-url", "link"}
        if not is_leaf or not is_url_field:
            continue

        text = raw_element_text(element)
        if text:
            values.extend(split_multi_value_field(text))
    return dedupe(values)


def collect_pdf_url_values(record: ET.Element) -> list[str]:
    urls = direct_child(record, "urls")
    if urls is None:
        return []
    pdf_urls = direct_child(urls, "pdf-urls")
    if pdf_urls is None:
        return []

    values: list[str] = []
    for url in direct_children(pdf_urls, "url"):
        text = raw_element_text(url)
        if text:
            values.extend(split_multi_value_field(text))
    return dedupe(values)


def split_multi_value_field(value: str) -> list[str]:
    normalized = value.replace("&#xD;", "\n").replace("\r", "\n")
    return [part.strip() for part in normalized.split("\n") if part.strip()]


def decode_file_url(value: str) -> Path | None:
    if not value.lower().startswith("file:"):
        return None
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme != "file":
        return None
    path = urllib.parse.unquote(parsed.path)
    if parsed.netloc and parsed.netloc not in {"localhost", ""}:
        path = f"//{parsed.netloc}{path}"
    return Path(path)


def attachment_from_url(value: str, root: Path, dry_run: bool) -> Attachment | None:
    local_path = decode_file_url(value)
    if local_path is None:
        return None

    exists = local_path.exists()
    try:
        relative_path = local_path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return None

    attachment = Attachment(
        local_path=local_path,
        storage_alias=STORAGE_ALIAS,
        relative_path=relative_path,
        original_filename=local_path.name,
        exists=exists,
    )
    if exists and local_path.is_file() and not dry_run:
        stat = local_path.stat()
        attachment.file_size_bytes = stat.st_size
        attachment.sha256 = sha256_file(local_path)
    elif exists and local_path.is_file() and dry_run:
        attachment.file_size_bytes = local_path.stat().st_size
    return attachment


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def find_records(root: ET.Element) -> list[ET.Element]:
    records = [element for element in root.iter() if local_name(element.tag) == "record"]
    return records


def parse_bookends_xml(xml_path: Path, bookends_root: Path, limit: int | None, dry_run: bool) -> list[PaperRecord]:
    tree = ET.parse(xml_path)
    records = find_records(tree.getroot())
    if limit is not None:
        records = records[:limit]

    parsed: list[PaperRecord] = []
    for index, record in enumerate(records, start=1):
        record_id = text_from_path(record, [("rec-number",), ("record-number",), ("id",)]) or str(index)
        authors = extract_authors(record)
        pmid, pmcid, pubmed_url = extract_pubmed_fields(record)
        paper = PaperRecord(
            record_id=record_id,
            title=text_from_path(record, [("titles", "title"), ("title",)]),
            authors=authors,
            first_author=first_author_name(authors),
            journal=text_from_path(
                record,
                [
                    ("titles", "secondary-title"),
                    ("periodical", "full-title"),
                    ("journal",),
                    ("secondary-title",),
                ],
            ),
            year=extract_year(record),
            volume=text_from_path(record, [("volume",)]),
            issue=text_from_path(record, [("number",), ("issue",)]),
            pages=text_from_path(record, [("pages",)]),
            doi=extract_doi(record),
            pmid=pmid,
            pmcid=pmcid,
            pubmed_url=pubmed_url,
            abstract=text_from_path(record, [("abstract",), ("notes", "abstract")]),
        )
        for url in dedupe([*collect_pdf_url_values(record), *collect_url_values(record)]):
            attachment = attachment_from_url(url, bookends_root, dry_run=dry_run)
            if attachment is not None:
                paper.attachments.append(attachment)
        parsed.append(paper)
    return parsed


def slugify(value: str, fallback: str) -> str:
    value = value.strip() or fallback
    value = re.sub(r"[^A-Za-z0-9]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    return value[:80] or fallback


def note_filename(paper: PaperRecord) -> str:
    first = slugify(paper.first_author or "unknown_author", "unknown_author")
    year = slugify(paper.year or "unknown_year", "unknown_year")
    title = slugify(paper.title or f"record_{paper.record_id}", f"record_{paper.record_id}")
    return f"{first}_{year}_{title}.md"


def yaml_scalar(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    text = str(value)
    if text == "":
        return '""'
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def yaml_list(values: list[str], indent: int = 0) -> str:
    prefix = " " * indent
    if not values:
        return f"{prefix}[]"
    return "\n".join(f"{prefix}- {yaml_scalar(value)}" for value in values)


def render_metadata_block(paper: PaperRecord) -> str:
    lines = [
        f"title: {yaml_scalar(paper.title)}",
        "authors:",
        yaml_list(paper.authors, indent=2),
        f"first_author: {yaml_scalar(paper.first_author)}",
        f"journal: {yaml_scalar(paper.journal)}",
        f"year: {yaml_scalar(paper.year)}",
        f"volume: {yaml_scalar(paper.volume)}",
        f"issue: {yaml_scalar(paper.issue)}",
        f"pages: {yaml_scalar(paper.pages)}",
        f"doi: {yaml_scalar(paper.doi)}",
        f"pmid: {yaml_scalar(paper.pmid)}",
        f"pmcid: {yaml_scalar(paper.pmcid)}",
        f"pubmed_url: {yaml_scalar(paper.pubmed_url)}",
    ]
    return "\n".join(lines)


def render_route_metadata_block(route_metadata: RouteMetadata) -> str:
    lines = [
        f"source: {yaml_scalar(route_metadata.source)}",
        f"note_depth: {yaml_scalar(route_metadata.note_depth)}",
        f"security_tier: {yaml_scalar(route_metadata.security_tier)}",
        f"status: {yaml_scalar(route_metadata.status)}",
        f"priority: {yaml_scalar(route_metadata.priority)}",
    ]
    if route_metadata.projects:
        lines.extend(["projects:", yaml_list(route_metadata.projects, indent=2)])
    else:
        lines.append("projects: []")
    if route_metadata.tags:
        lines.extend(["tags:", yaml_list(route_metadata.tags, indent=2)])
    else:
        lines.append("tags: []")
    return "\n".join(lines)


def render_attachment_block(paper: PaperRecord) -> str:
    if not paper.attachments:
        return "attachments: []"
    lines = ["attachments:"]
    for attachment in paper.attachments:
        lines.extend(
            [
                f"  - storage_alias: {yaml_scalar(attachment.storage_alias)}",
                f"    relative_path: {yaml_scalar(attachment.relative_path)}",
                f"    original_filename: {yaml_scalar(attachment.original_filename)}",
                f"    exists: {yaml_scalar(attachment.exists)}",
                f"    file_size_bytes: {yaml_scalar(attachment.file_size_bytes)}",
                f"    sha256: {yaml_scalar(attachment.sha256)}",
            ]
        )
    return "\n".join(lines)


def read_template(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def safe_display_path(path: Path) -> str:
    if not path.is_absolute():
        return path.as_posix()

    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        parts = path.parts
        if len(parts) >= 2:
            return Path(parts[-2], parts[-1]).as_posix()
        return path.name


def render_prompt_packet(
    paper: PaperRecord,
    note_path: Path,
    template_text: str,
    note_template_text: str,
    route_metadata: RouteMetadata,
) -> str:
    abstract = paper.abstract or "No abstract found in source metadata."
    attachments = render_attachment_block(paper)
    metadata = render_metadata_block(paper)
    route_metadata_block = render_route_metadata_block(route_metadata)
    citation = citation_line(paper)
    return template_text.format(
        title=paper.title or "Untitled paper",
        citation=citation,
        note_path=safe_display_path(note_path),
        route_metadata_block=route_metadata_block,
        metadata_block=metadata,
        attachment_block=attachments,
        abstract=abstract,
        paper_note_template=note_template_text.rstrip(),
    )


def citation_line(paper: PaperRecord) -> str:
    first = paper.first_author or "Unknown author"
    year = paper.year or "n.d."
    journal = paper.journal or "Unknown journal"
    return f"{first} et al., {journal}, {year}"


def source_key(paper: PaperRecord) -> str:
    if paper.doi:
        return f"doi:{paper.doi.lower()}"
    if paper.pmid:
        return f"pmid:{paper.pmid}"
    return f"bookends_record:{paper.record_id}"


def render_source_map(papers: list[PaperRecord], papers_dir: Path, xml_path: Path, bookends_root: Path) -> str:
    now = datetime.now().isoformat(timespec="seconds")
    lines = [
        "# Paper source map generated by scripts/build_bibliographic_note_packet.py",
        "# PDF paths use storage_alias + relative_path so local roots can move later.",
        f"last_updated: {yaml_scalar(now)}",
        "source_mode: bookends_xml",
        f"source_xml_name: {yaml_scalar(xml_path.name)}",
        f"storage_alias: {yaml_scalar(STORAGE_ALIAS)}",
        'storage_root_config: "config/local_paths.yaml"',
        "papers:",
    ]
    for paper in papers:
        note_path = papers_dir / note_filename(paper)
        lines.extend(
            [
                f"  {yaml_scalar(source_key(paper))}:",
                f"    note_path: {yaml_scalar(safe_display_path(note_path))}",
                f"    bookends_record_id: {yaml_scalar(paper.record_id)}",
                f"    title: {yaml_scalar(paper.title)}",
                f"    first_author: {yaml_scalar(paper.first_author)}",
                f"    year: {yaml_scalar(paper.year)}",
                f"    doi: {yaml_scalar(paper.doi)}",
                f"    pmid: {yaml_scalar(paper.pmid)}",
                "    attachments:",
            ]
        )
        if paper.attachments:
            for attachment in paper.attachments:
                lines.extend(
                    [
                        f"      - storage_alias: {yaml_scalar(attachment.storage_alias)}",
                        f"        relative_path: {yaml_scalar(attachment.relative_path)}",
                        f"        original_filename: {yaml_scalar(attachment.original_filename)}",
                        f"        exists: {yaml_scalar(attachment.exists)}",
                        f"        file_size_bytes: {yaml_scalar(attachment.file_size_bytes)}",
                        f"        sha256: {yaml_scalar(attachment.sha256)}",
                    ]
                )
        else:
            lines[-1] = "    attachments: []"
    return "\n".join(lines) + "\n"


def write_if_changed(path: Path, text: str, dry_run: bool) -> str:
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return WRITE_UNCHANGED
    if dry_run:
        return WRITE_WOULD_WRITE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return WRITE_WRITTEN


def reveal_in_finder(path: Path) -> None:
    if sys.platform != "darwin":
        print("Finder reveal is only supported on macOS")
        return
    try:
        subprocess.run(["open", "-R", str(path)], check=False)
    except OSError as error:
        print(f"Could not reveal in Finder: {error}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Create manual AI prompt packets from Bookends EndNote XML.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--source-mode", choices=["bookends_xml"], required=True)
    parser.add_argument("--bookends-xml", type=Path, required=True)
    parser.add_argument("--bookends-root", type=Path, required=True)
    parser.add_argument("--backend", choices=["manual_prompt_packet"], required=True)
    parser.add_argument("--limit", type=int)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        default=True,
        help="Preview packet and source-map changes without writing (the default).",
    )
    mode.add_argument(
        "--apply",
        dest="dry_run",
        action="store_false",
        help="Write reviewed outputs to the explicit output paths.",
    )
    parser.add_argument(
        "--reveal-in-finder",
        action="store_true",
        help="Reveal generated prompt packets in macOS Finder after creation.",
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--papers-dir", type=Path, required=True)
    parser.add_argument(
        "--source-map-output",
        type=Path,
        help="Optional explicit output path for the generated public source map.",
    )
    parser.add_argument("--priority", default="", help="Optional priority metadata for generated prompt packets.")
    parser.add_argument(
        "--project",
        action="append",
        default=[],
        help="Optional project metadata for generated prompt packets. May be supplied more than once.",
    )
    parser.add_argument(
        "--tag",
        action="append",
        default=[],
        help="Optional tag metadata for generated prompt packets. May be supplied more than once.",
    )
    args = parser.parse_args(argv)

    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be a positive integer")
    if not args.bookends_xml.exists():
        parser.error(f"--bookends-xml does not exist: {args.bookends_xml}")
    if not args.bookends_root.exists():
        parser.error(f"--bookends-root does not exist: {args.bookends_root}")

    prompt_template = read_template(SKILL_ROOT / "assets" / "paper_extraction_prompt_template.md")
    note_template = read_template(SKILL_ROOT / "assets" / "paper_note_template.md")

    papers = parse_bookends_xml(
        xml_path=args.bookends_xml,
        bookends_root=args.bookends_root,
        limit=args.limit,
        dry_run=args.dry_run,
    )

    print(f"Source mode: {args.source_mode}")
    print(f"Backend: {args.backend}")
    print(f"Records parsed: {len(papers)}")
    print(f"Dry run: {args.dry_run}")

    route_metadata = RouteMetadata(
        priority=args.priority,
        projects=args.project,
        tags=args.tag,
    )
    written_packets = 0
    would_write_packets = 0
    unchanged_packets = 0
    skipped_existing_notes = 0
    for paper in papers:
        note_path = args.papers_dir / note_filename(paper)
        packet_path = args.output_dir / f"{note_path.stem}_prompt_packet.md"
        if note_path.exists():
            skipped_existing_notes += 1
            print(f"SKIP existing paper note target: {note_path}")
            continue
        packet = render_prompt_packet(paper, note_path, prompt_template, note_template, route_metadata)
        write_status = write_if_changed(packet_path, packet, args.dry_run)
        if write_status == WRITE_WRITTEN:
            written_packets += 1
            print(f"Wrote: {packet_path}")
        elif write_status == WRITE_WOULD_WRITE:
            would_write_packets += 1
            print(f"DRY-RUN would write: {packet_path}")
        else:
            unchanged_packets += 1
            print(f"Unchanged: {packet_path}")

    if args.reveal_in_finder and not args.dry_run and (written_packets or sys.platform != "darwin"):
        reveal_in_finder(args.output_dir)

    if args.source_map_output is None:
        source_map_summary = "not requested"
    else:
        source_map = render_source_map(papers, args.papers_dir, args.bookends_xml, args.bookends_root)
        source_map_status = write_if_changed(args.source_map_output, source_map, args.dry_run)
        if source_map_status == WRITE_WOULD_WRITE:
            print(f"DRY-RUN would update: {args.source_map_output}")
            source_map_summary = "would update"
        elif source_map_status == WRITE_WRITTEN:
            print(f"Updated: {args.source_map_output}")
            source_map_summary = "updated"
        else:
            print(f"Unchanged: {args.source_map_output}")
            source_map_summary = "unchanged"

    print("")
    print("Summary")
    print(f"- records parsed: {len(papers)}")
    print(f"- prompt packets written: {written_packets}")
    print(f"- prompt packets would be written in dry-run mode: {would_write_packets}")
    print(f"- prompt packets unchanged: {unchanged_packets}")
    print(f"- existing Papers/*.md targets skipped: {skipped_existing_notes}")
    print(f"- source map status: {source_map_summary}")
    print("- external AI calls: 0")
    print("- Bookends attachment modifications: 0")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ET.ParseError as error:
        print(f"XML parse error: {error}", file=sys.stderr)
        raise SystemExit(2)
    except OSError as error:
        print(f"File error: {error}", file=sys.stderr)
        raise SystemExit(2)
