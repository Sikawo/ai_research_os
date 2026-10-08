# B1 PDF-Only Public Full-Text Paper Note Instructions

Use these instructions when a user uploads one or more published public paper PDFs and asks for a Markdown paper note.

Natural trigger phrases include:

- "Please MD this paper PDF."
- "Please make a paper note from this PDF."
- "Please deeply read this public PDF."
- "Please convert this uploaded paper to a Markdown note."
- "このPDFを論文MD化して"
- "Please turn this uploaded public paper PDF into a Markdown paper note using my repo's PDF paper-note workflow."

## Safety Boundary

Use this workflow only for published public PDFs uploaded by the user in the current chat.

Do not use this workflow for unpublished manuscripts, under-review manuscripts, confidential figures, reviewer comments, private drafts, NIH-internal restricted material, grants, collaborator-private content, or any material that is not already public.

Use only:

- the uploaded published public PDFs
- these repository instructions
- public metadata sources when web/search access is available

Do not use local file paths, file URLs, attachment paths, private storage names, secrets, credentials, hidden metadata, or repository-private content. Do not invent citations, experiments, reagents, results, controls, figure interpretations, or bibliographic metadata.

## Output Contract

Create exactly one English Markdown paper note per uploaded PDF. If multiple PDFs are uploaded, process each PDF separately and preserve one-paper-one-Markdown-note semantics.

Use this frontmatter route for every generated note:

```yaml
source: uploaded_public_pdf
note_depth: public_full_text_reviewed
security_tier: public
```

Separate paper claims, interpretation, and speculation. State uncertainty clearly. Figure-by-figure details are required only when figures are visible and readable in the uploaded PDF. Do not claim supplementary-material review unless supplementary material was also uploaded.

Recommended batch size: 1-3 PDFs for quality. Practical upper bound for figure-level review: 5 PDFs. If a generated prompt packet states a configured maximum PDF count, follow that lower limit.

## Metadata Verification Rules

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

## Paper Note Template Requirements

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

Include these sections:

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

## Filename Guidance

Prefer short, stable Markdown filenames using:

```text
FirstAuthor_JournalAbbrev_Year.md
```

Examples:

```text
Rivera_NatCommun_2016.md
Dahmane_NatCommun_2022.md
Altan-Bonnet_Cell_2005.md
```

Use the first author surname, a short journal abbreviation, and the publication year. Keep filenames English-only and filesystem-safe. Avoid full article-title filenames by default. Preserve one-paper-one-Markdown-note semantics.

If the preferred filename may collide with another paper, add a deterministic short suffix. Prefer this order when data are available:

1. `FirstAuthor_JournalAbbrev_Year.md`
2. If ambiguous, add a short stable title phrase, such as `FirstAuthor_JournalAbbrev_Year_STING_palmitoylation.md`
3. If still ambiguous or if the title phrase is not stable enough, add a DOI-derived suffix using the final DOI token or another short filesystem-safe DOI fragment
4. If PMID is available and useful, use a PMID suffix such as `FirstAuthor_JournalAbbrev_Year_PMIDxxxxxx.md`

Do not use random numbers, timestamps, or session-specific suffixes for normal note filenames.

## Return ZIP Requirements

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

Do not include any file other than the generated Markdown notes.
