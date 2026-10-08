# PubMed Search Packet Template

This template mirrors the generated `SEARCH_PACKET.md` structure from `scripts/run_search.py`.
For abstract-level AI handoff, use `assets/pubmed_abstract_screening_packet_template.md`.

## Search Configuration

- Original query: `[QUERY]`
- Retrieval date/time: `[UTC_TIMESTAMP]`
- Database: `PubMed`
- Sort mode: `[SORT_MODE]`
- Requested `retmax`: `[RETMAX]`
- Requested `deep-read`: `[DEEP_READ]`
- Total hit count: `[TOTAL_COUNT]`
- PMID order returned by PubMed: `[PMID_1, PMID_2, ...]`

## Metadata Table

| Rank | PMID | Year | Journal | Title |
| ---: | --- | --- | --- | --- |
| 1 | `[PMID]` | `[YEAR]` | `[JOURNAL]` | `[TITLE]` |

## Read-Depth Definitions

- `PubMed verified`: PMID, title, year, and journal were retrieved from PubMed/NCBI metadata.
- `Abstract screened`: relevance was judged from PubMed metadata and public abstract-level context only.
- `Full text reviewed`: use this only when PMC, publisher full text, or PDF content was actually read.

## AI Screening Instructions

Screen the top-N papers for relevance to the original query. Classify each paper as high, medium, low, or unclear relevance and explain the reason using only the provided metadata unless the human supplies additional public text.

## Deeper-Reading Selection Instructions

Choose the requested number of papers for deeper reading. Explain what evidence, methods, figures, or claims should be checked in the full text before creating any durable repository note.

## Safety Notes

- PubMed Best Match top-N is a candidate list, not a claim of scientific importance.
- AI may help judge relevance and support, but human scientific judgment remains primary.
- `Full text reviewed` must not be used unless full text was actually read.
- Optional DOI, PMCID, PMC URL, and abstract fields are PubMed/NCBI-derived metadata only.
- Generated `exports/` are temporary and should not be committed.
