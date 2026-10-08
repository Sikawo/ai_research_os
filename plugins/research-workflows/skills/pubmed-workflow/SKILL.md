---
name: pubmed-workflow
description: Search public PubMed metadata and prepare synthetic, reviewable screening packets with network activity explicitly requested and mockable. Use for public literature discovery; do not access private notes or write final paper records.
---

# PubMed Literature Workflow

Default to offline planning. Network retrieval occurs only when the user
explicitly runs a search command. Tests must mock all network activity, and
generated output remains outside tracked plugin content.

This workflow supports PubMed-only literature discovery while preserving the repository's private-research boundaries. It is for public PubMed metadata retrieval, AI-assisted screening, and human-supervised deeper reading.

## Current Priority Workflow

1. Discuss and refine the research question with AI chat.
2. Ask AI chat to propose a PubMed-only search plan using `assets/pubmed_ai_chat_search_prompt.md`.
3. Run the local PubMed metadata script.
4. Upload or paste `ABSTRACT_SCREENING_PACKET.md` or `SEARCH_PACKET.md` to ChatGPT or Claude for screening and deeper-reading planning.
5. Review AI-generated screening outputs locally.
6. Import only approved search-level Markdown records with `scripts/import_screening_record.py`.
7. Save durable paper notes only through a separate human-reviewed full-text workflow.

Generated `exports/` are temporary review artifacts and should not be committed.

## Local Metadata Script

Run:

```bash
python3 scripts/run_search.py \
  --query '[PUBMED_QUERY]' \
  --retmax 20 \
  --deep-read 5 \
  --topic-slug short_topic_name
```

For an AI handoff packet with abstracts, DOI links, PMC availability metadata, and a zip file:

```bash
python3 scripts/run_search.py \
  --query '[PUBMED_QUERY]' \
  --retmax 20 \
  --deep-read 5 \
  --topic-slug short_topic_name \
  --include-abstracts \
  --include-pmc-links \
  --include-doi \
  --zip-output \
  --timeout 120
```

The script writes a timestamped folder under:

```text
exports/pubmed_search/<timestamp>_<topic_slug>/
```

Generated files:

- `SEARCH_PACKET.md`
- `ABSTRACT_SCREENING_PACKET.md`, when `--include-abstracts` is used
- `pubmed_results.csv`
- `pubmed_results.json`
- `pubmed_ai_handoff.zip`, when `--zip-output` is used

The script uses NCBI E-utilities for public PubMed metadata and optional abstracts only. It does not download PDFs, fetch or parse PMC full text, access Bookends, modify `Papers/`, modify `Indexes/PAPER_SOURCE_MAP.yaml`, write to `Literature_Searches/`, or call external AI APIs.

## Script Options

- `--include-abstracts` retrieves PubMed abstracts when available and writes `ABSTRACT_SCREENING_PACKET.md`.
- `--include-pmc-links` includes PMCID values and PMC article URLs when PubMed metadata provides them. This is availability metadata only; the script does not retrieve PMC full text.
- `--include-doi` includes DOI values and `https://doi.org/...` links when PubMed metadata provides them.
- `--zip-output` creates `pubmed_ai_handoff.zip` containing safe generated files from the current workflow run.
- `--timeout 120` is recommended for larger or slower PubMed requests.

## Meaning of Read-Depth Labels

- `PubMed verified` means PMID, title, year, and journal were retrieved from PubMed/NCBI.
- `PubMed verified; abstract reviewed` means PMID and metadata came from PubMed/NCBI, and the abstract text in the generated packet may be screened.
- `Abstract reviewed; full text not available in this workflow` means abstract-level evidence was reviewed, but this workflow did not retrieve PMC full text, publisher full text, PDFs, figures, methods details, or supplements.
- `Full text reviewed` must not be used unless PMC, full text, or PDF content was actually read.

PubMed Best Match top-N is a candidate list, not a claim of scientific importance. AI may help judge relevance and support, but human scientific judgment remains primary.

## AI Screening

After generating a packet, paste or upload `ABSTRACT_SCREENING_PACKET.md` when abstracts were included. If abstracts were not included, use `SEARCH_PACKET.md`.

For a standardized abstract-screening output package, use `assets/pubmed_ai_screening_output_prompt.md` with `ABSTRACT_SCREENING_PACKET.md` or `pubmed_ai_handoff.zip`. The prompt asks AI chat to return a downloadable zip when supported, containing the five managed Markdown files used by the manual review/import workflow. If the chat interface cannot create a zip, ask it to present the same files as separate Markdown outputs.

Ask AI chat to:

- screen the top-N papers for relevance;
- separate high, medium, low, and unclear candidates;
- choose top papers for deeper reading;
- state what evidence should be checked in full text;
- avoid claiming full-text review unless full text was actually supplied and read.

Use `assets/pubmed_search_packet_template.md` and `assets/pubmed_abstract_screening_packet_template.md` as stable generated packet shapes. Use `assets/pubmed_paper_note_template.md` only after human review.

## Post-Screening Record Import

After AI chat screening, keep the generated outputs in a local review folder first. Expected reviewed search-level files are:

- `SEARCH_SUMMARY.md`
- `SCREENING_TABLE.md`
- `DEEP_READING_SELECTION.md`
- `ABSTRACT_REVIEW.md`
- `FULL_TEXT_READING_PLAN.md`

AI chat screening outputs may be downloaded either as a zip file or as an extracted folder. Prefer downloadable zip outputs when the chat tool supports them, because they reduce copy/paste errors and keep the five reviewed files grouped together. Generic browser download names such as `Archive.zip` or `Archive(1).zip` are acceptable if the zip contents are correct.

The AI output may also contain optional `paper_note_drafts/`, but those drafts are intentionally ignored and are not imported automatically.

Abstract-screening outputs and optional `paper_note_drafts/*.md` are not final paper notes. Save and review the returned zip or extracted Markdown files manually before importing the five managed files. Durable `Papers/` notes require a separate deliberate full-text workflow, and `full_text_reviewed` is allowed only after actual full-text reading by the AI or human during that workflow.

Recommended flow:

1. Run `scripts/run_search.py` to generate PubMed abstract handoff outputs.
2. Upload `ABSTRACT_SCREENING_PACKET.md` or `pubmed_ai_handoff.zip` to AI chat.
3. Save the AI chat screening outputs locally as a zip file or extracted folder.
4. Human-review the five search-level Markdown files.
5. Run the importer:

```bash
python3 scripts/import_screening_record.py \
  --source <explicit-output-path> \
  --topic-slug AAV6_primary_T_cell_HSPC \
  --date 2026-05-20
```

or:

```bash
python3 scripts/import_screening_record.py \
  --source <explicit-output-path> \
  --topic-slug AAV6_primary_T_cell_HSPC \
  --date 2026-05-20 \
  --apply
```

The first command is a dry run by default. After reviewing it, the second command
uses `--apply` to write only the five managed Markdown files to:

```text
Literature_Searches/YYYY-MM-DD_topic_slug/
```

Dry run is the default; `--dry-run` may be supplied explicitly for clarity. If the destination already exists and is non-empty, an apply run stops unless `--overwrite` is passed. With `--apply --overwrite`, only the five managed Markdown files are replaced; other destination files are left untouched.

The importer ignores `paper_note_drafts/`, `exports/`, ZIP files, CSV, JSON, XML, PDFs, Bookends-like paths, and unexpected files. It blocks source Markdown files that contain local paths, local file URLs, the blocked source URL metadata field, or exact full-text metadata claims such as `full_text_reviewed: yes` or `note_depth: full_text_reviewed`.

Do not import `paper_note_drafts/` automatically. Do not write to `Papers/` from this import workflow. `exports/` remain temporary and should not be committed. Full-text-reviewed labels should only be used after actual full-text review, not after abstract screening. Before commit, run focused tests and the repo safety check, then commit only the intended `Literature_Searches/YYYY-MM-DD_topic_slug/` records.

## Troubleshooting

macOS Framework Python may fail with SSL certificate verification errors during PubMed E-utilities access. `Install Certificates.command` may also fail with permission denied on some systems. When system Framework Python SSL is problematic, use miniforge or conda Python.

For conda/miniforge environments, update certificates with:

```bash
conda update -y certifi ca-certificates openssl
```

Do not disable SSL verification as a workaround. For slow PubMed requests, retry with `--timeout 120`.

## Durable Notes

Do not create durable `Papers/*.md` notes automatically from the script. If a paper should become a durable note, create it manually after human review and keep the read-depth fields honest.

## Future Options

Future option 1: Claude Code or Cursor with a PubMed MCP server. This may eventually support interactive PubMed query refinement and metadata retrieval inside coding tools. This change does not implement or configure MCP.

Future option 2: Gemini, NotebookLM, or a broader deep-research workflow. This may be useful for larger exploratory reviews that combine public sources with uploaded documents. This change documents the idea only and does not implement Gemini, NotebookLM, external AI APIs, cloud jobs, or unattended repository writes.
