# PubMed Abstract Screening Packet Template

This template mirrors the generated `ABSTRACT_SCREENING_PACKET.md` structure from `scripts/run_search.py` when `--include-abstracts` is used.

## Search Configuration

- Original query: `[QUERY]`
- Topic slug: `[TOPIC_SLUG]`
- Retrieval date/time: `[UTC_TIMESTAMP]`
- Database: `PubMed`
- Sort mode: `[SORT_MODE]`
- Requested `retmax`: `[RETMAX]`
- Requested `deep-read`: `[DEEP_READ]`
- Total hit count: `[TOTAL_COUNT]`
- PMID order returned by PubMed: `[PMID_1, PMID_2, ...]`

## Source And Read-Depth Notes

This packet is derived from PubMed/NCBI metadata and abstracts. It is not a full-text review unless full text is explicitly supplied in a later workflow.

Use these labels carefully:

- `PubMed verified; abstract reviewed`: PMID and metadata came from PubMed/NCBI, and the abstract text in this packet may be screened.
- `Abstract reviewed; full text not available in this workflow`: abstract-level evidence was reviewed, but this script did not retrieve PMC full text, publisher full text, PDFs, figures, methods details, or supplements.
- `Full text not reviewed`: no full-text content was read in this workflow.

## AI Screening Instructions

Screen the top-N PubMed records below for relevance to the original query. Select the requested number of deep-reading candidates, but do not claim that these are the objectively top papers or that full text has been reviewed.

For each candidate, report:

- relevance: high, medium, low, or unclear
- evidence used from the provided abstract and metadata
- whether full text should be checked next
- the exact read-depth label used

Do not infer results beyond the supplied abstracts and metadata. Do not claim figure-level, methods-level, supplementary-material, or PDF review. PMCID and PMC URLs indicate availability metadata only; this workflow did not download or parse PMC full text.

## PubMed Records

### 1. `[TITLE]`

- PMID: `[PMID]`
- Authors: `[AUTHORS]`
- Year: `[YEAR]`
- Journal: `[JOURNAL]`
- DOI: `[DOI]`
- DOI URL: `[DOI_URL]`
- PMCID: `[PMCID]`
- PMC URL: `[PMC_URL]`
- PMC availability: `[PMC_AVAILABLE_OR_NOT]`
- Read-depth label: `PubMed verified; abstract reviewed`
- Full-text status: `Full text not reviewed`

Abstract:

`[ABSTRACT_TEXT]`

## Safety Notes

- This packet used public PubMed/NCBI metadata and abstracts only.
- No PDFs were downloaded.
- No PMC full text was fetched or parsed.
- No Bookends files were accessed.
- No `Papers/` notes or `Indexes/PAPER_SOURCE_MAP.yaml` entries were modified.
- No external AI APIs were called.
