# Paper Note Quality Checklist

Use this checklist before treating an AI-assisted paper note as ready for repository use.

## Metadata

- Frontmatter includes `title`, `authors`, `year`, `doi`, `pmid`, `source`, `note_depth`, `security_tier`, `status`, `priority`, `projects`, and `tags` where available.
- `source` is `bookends_xml` for Bookends-derived public notes.
- `note_depth` is one of:
  - `abstract_metadata_only`
  - `public_full_text_reviewed`
  - `restricted_internal_full_text`
- `security_tier` is one of:
  - `public`
  - `restricted_internal`
- Public notes do not include local paths, attachment paths, private storage names, secrets, credentials, or restricted manuscript details.
- Restricted internal notes use `source: restricted_internal`, `note_depth: restricted_internal_full_text`, and `security_tier: restricted_internal`.

## Evidence Quality

- Main claim is concise and grounded in the paper.
- Paper claims, interpretation, and speculation are clearly separated.
- Figure-level evidence is present for full-text reviewed notes.
- Abstract/metadata-only notes clearly avoid claiming full-text review.
- Key controls and limitations are included when available.
- Reagents, methods, assays, and models are named only when supported by the supplied source.
- Public full-text reviewed notes include figure-by-figure interpretation only for figures actually present in the supplied public paper.

## Safety and Scope

- No unpublished manuscript contents, reviewer comments, confidential figures, or restricted full-text-derived details are included in public notes.
- Restricted internal notes are not committed to GitHub.
- Restricted outputs are stored outside the repository or in an explicitly approved internal/local-only ignored location.
- Restricted internal notes are not treated as ordinary `Papers/*.md` public notes.
- External-safe summary candidates have been reviewed and stripped of unpublished findings, figure-level specifics, confidential methods, exact datasets, reviewer-confidential information, sensitive mechanistic claims, local paths, attachment paths, private storage names, and unnecessary identifying context.
- AI-generated suggestions are labeled as suggestions.
- Project/application relevance is high-level unless the human has explicitly supplied approved text.
- The note remains in English and does not fabricate citations, results, protocols, or collaborator details.
- Public full-text upgrade packets are not treated as final paper notes.
- Generated packets and final notes contain no local paths, file URLs, attachment paths, or blocked metadata fields.
- The repository helper did not read or modify the target `Papers/*.md` note and did not accept, read, copy, parse, OCR, or upload a PDF.

## Final Human Review

- Human reviewer checked the source material for key claims.
- Human reviewer confirmed the route: public full-text, restricted internal full-text, or abstract/metadata-only.
- Human reviewer confirmed the PDF or full text used for public full-text review is published and public.
- Human reviewer confirmed any pasted existing abstract note text was safe to share externally.
- Human reviewer confirmed any publication-time public note was created from the published version, not copied from a restricted internal note.
- Human reviewer confirmed the note belongs in this repository before commit.
