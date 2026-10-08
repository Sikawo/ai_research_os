#!/usr/bin/env python3
"""Create a ChatGPT-ready ZIP for public PDF-only full-text paper notes."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path


DEFAULT_OUTPUT_ROOT = Path("exports/pdf_only_full_text_prompt")
DEFAULT_ZIP_OUTPUT_DIR = Path("exports/pdf_only_full_text_prompt")
DEFAULT_MAX_PDFS = 3
REPO_ROOT = Path(__file__).resolve().parents[1]
CHATGPT_INSTRUCTIONS_TEMPLATE = REPO_ROOT / "assets" / "pdf_only_full_text_chatgpt_instructions.md"


def timestamp_for_paths() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def slugify(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    slug = re.sub(r"_+", "_", slug).strip("._-")
    return slug or "public_pdf_full_text_notes"


def render_chatgpt_instructions(max_pdfs: int) -> str:
    if CHATGPT_INSTRUCTIONS_TEMPLATE.exists():
        template = CHATGPT_INSTRUCTIONS_TEMPLATE.read_text(encoding="utf-8").rstrip()
        return template + f"\n\nConfigured prompt ZIP maximum PDF count: {max_pdfs}.\n"

    return f"""# ChatGPT Instructions

Use this packet only for published public PDFs uploaded by the user in this chat.

Do not use this workflow for unpublished manuscripts, under-review manuscripts, confidential figures, reviewer comments, private drafts, NIH-internal restricted material, grants, collaborator-private content, or any material that is not already public.

Use only:

- the uploaded published public PDFs
- the instruction files included in this ZIP

Do not use local file paths, file URLs, attachment paths, private storage names, secrets, credentials, or hidden metadata. Do not invent citations, experiments, reagents, results, controls, figure interpretations, or bibliographic metadata.

Create exactly one English Markdown paper note per uploaded PDF. If multiple PDFs are uploaded, process each PDF separately and preserve one-paper-one-Markdown-note semantics.

Use this frontmatter route for every generated note:

```yaml
source: uploaded_public_pdf
note_depth: public_full_text_reviewed
security_tier: public
```

Separate paper claims, your interpretation, and speculation. State uncertainty clearly. Figure-by-figure details are required only when figures are visible and readable in the uploaded PDF. Do not claim supplementary-material review unless supplementary material was also uploaded.

Return a ZIP containing only the generated `.md` files and no README, prompt files, PDFs, exports, or other files. Prefer short, stable, English-only, filesystem-safe filenames using `FirstAuthor_JournalAbbrev_Year.md`, such as `Rivera_NatCommun_2016.md`. Avoid full article-title filenames by default. If a filename may collide, add a deterministic short suffix from a stable title phrase, DOI fragment, or PMID. Do not use random numbers, timestamps, or session-specific suffixes.

Recommended batch size: 1-3 PDFs for quality. Practical upper bound for figure-level review: 5 PDFs. This packet was configured for up to {max_pdfs} PDF(s).
"""


METADATA_VERIFICATION_INSTRUCTIONS = """# Metadata Verification Instructions

For each uploaded published public PDF, extract bibliographic metadata from the PDF:

- title
- authors
- journal
- year
- DOI
- PMID
- PMCID

Prefer DOI when present.

If DOI is absent, use a loose public search strategy when web/search access is available:

- title phrase
- first author + year
- journal + year
- key title words

Verify metadata approximately against public sources when available:

- DOI landing page
- PubMed
- PubMed Central
- publisher page
- Crossref or other DOI metadata

Do not fabricate missing metadata.

If public-source verification fails, still create the note from the uploaded public PDF, but set `metadata_verification: needs_human_check` and list fields requiring human verification.

If web/search access is unavailable, set `metadata_verification: pdf_only_not_externally_checked`.

If PDF metadata and public-source metadata disagree, preserve both in the note and set `metadata_verification: conflict_needs_human_check`.

If PubMed has no match but DOI, publisher, or Crossref metadata match, set `metadata_verification: partial` and explain the missing PubMed match.

If all important fields match across PDF and at least one reliable public source, set `metadata_verification: verified`.

Allowed `metadata_verification` values:

- `verified`
- `partial`
- `needs_human_check`
- `pdf_only_not_externally_checked`
- `conflict_needs_human_check`

Include frontmatter like:

```yaml
source: uploaded_public_pdf
note_depth: public_full_text_reviewed
security_tier: public
metadata_verification: verified
metadata_verified_against:
  - DOI
  - PubMed
metadata_verification_notes: ""
```
"""


PUBLIC_FULL_TEXT_NOTE_TEMPLATE = """# Public Full-Text Paper Note Template

Use English Markdown. Include YAML frontmatter with public bibliographic metadata and the required route fields:

```yaml
---
title:
authors:
year:
journal:
doi:
pmid:
pmcid:
source: uploaded_public_pdf
note_depth: public_full_text_reviewed
security_tier: public
metadata_verification:
metadata_verified_against: []
metadata_verification_notes: ""
status: draft
priority:
projects: []
tags: []
---
```

# Citation

# Concise Main Claim

# Background / Problem

# Why This Paper Matters

# Figure-by-Figure Summary

Include figure-by-figure details only when figures are visible and readable in the uploaded PDF. If figures are not readable, say so clearly.

# Key Experiments and Controls

# Methods / Assays / Reagents That Matter for Interpretation

# Paper Claims

# Interpretation

# Speculation / Hypotheses

# Limitations and Uncertainty

# Relevance to Ongoing Projects

# Relevance to research program / Application Thinking

# Suggested Follow-Up Papers

# Suggested Follow-Up Experiments

# AI-Ready Summary

# Human Checks Needed

List missing metadata, metadata conflicts, unreadable figures, unclear controls, missing supplements, or any claim that needs human verification.
"""


RETURN_ZIP_REQUIREMENTS = """# Return ZIP Requirements

Return one ZIP.

The ZIP must:

- include exactly one `.md` note per uploaded PDF
- include no README files
- include no PDFs
- include no prompt files
- include no local paths or file URLs
- include no generated exports
- prefer short filenames like `FirstAuthor_JournalAbbrev_Year.md`
- use English-only Markdown filenames
- keep filenames filesystem-safe
- avoid full article-title filenames by default
- preserve one-paper-one-Markdown-note semantics

Filename examples:

- `Rivera_NatCommun_2016.md`
- `Dahmane_NatCommun_2022.md`
- `Altan-Bonnet_Cell_2005.md`

If the preferred filename may collide with another paper, add a deterministic short suffix in this order when data are available:

1. a short stable title phrase, such as `FirstAuthor_JournalAbbrev_Year_STING_palmitoylation.md`
2. a DOI-derived suffix using the final DOI token or another short filesystem-safe DOI fragment
3. a PMID suffix such as `FirstAuthor_JournalAbbrev_Year_PMIDxxxxxx.md`

Do not use random numbers, timestamps, or session-specific suffixes for normal note filenames.

Do not include any file other than the generated Markdown notes.
"""


def build_manifest(args: argparse.Namespace, generated_at: str, timestamp: str) -> dict[str, object]:
    return {
        "generated_at": generated_at,
        "timestamp": timestamp,
        "route": "pdf_only_public_full_text",
        "source": "uploaded_public_pdf",
        "note_depth": "public_full_text_reviewed",
        "security_tier": "public",
        "batch_name": args.batch_name,
        "priority": args.priority,
        "projects": args.project,
        "tags": args.tag,
        "max_pdfs": args.max_pdfs,
        "recommended_pdf_batch_size": "1-3",
        "practical_pdf_upper_bound": 5,
        "external_ai_calls": 0,
        "pdf_files_read_copied_modified_uploaded": 0,
        "bookends_xml_required": False,
        "bookends_attachment_modifications": 0,
        "safety_scope": "published_public_pdfs_only",
    }


def write_text_files(handoff_dir: Path, manifest: dict[str, object], max_pdfs: int) -> dict[str, str]:
    files = {
        "CHATGPT_INSTRUCTIONS.md": render_chatgpt_instructions(max_pdfs),
        "METADATA_VERIFICATION_INSTRUCTIONS.md": METADATA_VERIFICATION_INSTRUCTIONS,
        "PUBLIC_FULL_TEXT_NOTE_TEMPLATE.md": PUBLIC_FULL_TEXT_NOTE_TEMPLATE,
        "RETURN_ZIP_REQUIREMENTS.md": RETURN_ZIP_REQUIREMENTS,
        "BATCH_MANIFEST.json": json.dumps(manifest, indent=2, sort_keys=True) + "\n",
    }
    handoff_dir.mkdir(parents=True, exist_ok=True)
    for filename, text in files.items():
        (handoff_dir / filename).write_text(text, encoding="utf-8")
    return files


def write_zip(zip_path: Path, files: dict[str, str]) -> None:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for filename, text in files.items():
            archive.writestr(filename, text)


def reveal_in_finder(path: Path) -> None:
    if sys.platform != "darwin":
        print("--reveal-in-finder is only available on macOS; ZIP was not revealed.")
        return
    result = subprocess.run(
        ["open", "-R", str(path)],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode != 0:
        output = "\n".join(part.strip() for part in (result.stdout, result.stderr) if part.strip())
        detail = f": {output}" if output else ""
        print(f"Warning: could not reveal ZIP in Finder{detail}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export a ChatGPT-ready prompt ZIP for public PDF-only full-text paper notes.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--batch-name", default="public_pdf_full_text_notes")
    parser.add_argument("--priority", default="medium")
    parser.add_argument("--project", action="append", default=[])
    parser.add_argument("--tag", action="append", default=[])
    parser.add_argument("--max-pdfs", type=int, default=DEFAULT_MAX_PDFS)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--output-zip", type=Path)
    parser.add_argument("--zip-output-dir", type=Path, default=DEFAULT_ZIP_OUTPUT_DIR)
    parser.add_argument("--reveal-in-finder", action="store_true")
    parser.add_argument("--timestamp", help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.max_pdfs < 1:
        print("Error: --max-pdfs must be at least 1.")
        return 1
    if args.max_pdfs > 5:
        print("Warning: --max-pdfs above 5 is outside the practical figure-level review upper bound.")

    timestamp = args.timestamp or timestamp_for_paths()
    generated_at = datetime.now().isoformat(timespec="seconds")
    batch_slug = slugify(args.batch_name)
    handoff_dir = args.output_root / timestamp
    zip_path = (
        args.output_zip.expanduser()
        if args.output_zip is not None
        else args.zip_output_dir.expanduser() / f"{batch_slug}_pdf_only_full_text_prompt_{timestamp}.zip"
    )

    manifest = build_manifest(args, generated_at, timestamp)
    files = write_text_files(handoff_dir, manifest, args.max_pdfs)
    write_zip(zip_path, files)

    print("PDF-only public full-text prompt ZIP")
    print(f"- ZIP: {zip_path}")
    print(f"- prompt folder: {handoff_dir}")
    print("- included instruction files: 5")
    print("- external AI calls: 0")
    print("- PDF files read/copied/modified/uploaded: 0")
    print("")
    print("Next step: upload this ZIP plus 1-3 published public PDFs to ChatGPT, then ask ChatGPT to return one ZIP containing only the generated Markdown notes.")
    if args.reveal_in_finder:
        reveal_in_finder(zip_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
