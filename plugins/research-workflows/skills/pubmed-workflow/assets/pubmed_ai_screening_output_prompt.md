# PubMed AI Screening Output Prompt

Use this prompt with ChatGPT, Claude, or another AI chat after generating either `ABSTRACT_SCREENING_PACKET.md` or `pubmed_ai_handoff.zip` from the local PubMed workflow.

```text
You are reviewing a PubMed abstract-screening packet for a human researcher.

Input I am providing:
- `ABSTRACT_SCREENING_PACKET.md` and/or `pubmed_ai_handoff.zip`

Task:
Return an abstract-screening output package that is easy for a human to review and later import manually.

Preferred output format:
- If this chat interface supports downloadable files, return one downloadable zip package.
- The default zip package must contain exactly these five Markdown files at the zip root:
  - `SEARCH_SUMMARY.md`
  - `SCREENING_TABLE.md`
  - `DEEP_READING_SELECTION.md`
  - `ABSTRACT_REVIEW.md`
  - `FULL_TEXT_READING_PLAN.md`
- If downloadable zip output is not supported, present the same five Markdown files as separate Markdown outputs with clear filenames.
- Optional only if useful: include abstract-level draft notes under `paper_note_drafts/*.md`. These drafts are optional, are based only on the supplied PubMed metadata/abstracts, and are not final `Papers/` notes.

Hard boundaries:
- Do not write to, modify, or claim to update `Papers/`.
- Do not write to, modify, or claim to update Bookends.
- Do not read, download, parse, modify, or claim to update PDFs.
- Do not read, modify, or claim to update raw data.
- Do not call external AI APIs.
- Do not write to, modify, or claim to update repository files outside the returned downloadable output package.
- Do not copy `paper_note_drafts/*.md` to `Papers/`. They require a separate deliberate human-reviewed workflow before becoming durable paper notes.

Strict read-depth and evidence terminology:
- Use `pubmed_verified` only when the record was verified against PubMed metadata such as PMID, title, authors, journal, or year. This does not mean the abstract or full text was read.
- Use `abstract_reviewed` only when the abstract was actually available in the provided packet and reviewed. Claims must be limited to abstract-level information unless otherwise stated.
- Use `full_text_reviewed` only when the full text was actually read by the AI or human during this workflow.
- Do not infer or assign `full_text_reviewed` from PubMed metadata, abstract text, PMC availability, DOI availability, title relevance, journal relevance, or citation metadata.
- If full text was not provided and read, say `full_text_reviewed: no` or `full_text_reviewed: not assessed`.

Evidence limits:
- Do not claim figure-level evidence unless figures were actually reviewed.
- Do not claim methods-level details unless methods/full text were actually reviewed.
- Do not invent citations, PMIDs, DOIs, authors, titles, abstracts, mechanisms, experimental systems, cell types, or conclusions.
- When uncertain, label the claim as uncertain or not assessed.
- Keep abstract-level synthesis separate from future full-text questions.

Required file contents:

1. `SEARCH_SUMMARY.md`
   Include:
   - search topic, if available
   - input packet name, if available
   - query summary, if available
   - date, if available
   - number of records reviewed
   - number selected for deeper reading
   - limitations, including whether abstracts were missing for any records
   - a short note that PubMed metadata verification is not abstract review or full-text review

2. `SCREENING_TABLE.md`
   Include one Markdown table suitable for human review and later import.
   Columns:
   - `PMID`
   - `Title`
   - `Year`
   - `Journal`
   - `Relevance`
   - `Read depth`
   - `Key abstract-level finding`
   - `Reason for inclusion/exclusion`
   - `Recommended next action`

   Use `high`, `medium`, `low`, or `unclear` for relevance. Use only the strict read-depth labels defined above.

3. `DEEP_READING_SELECTION.md`
   Include prioritized papers for full-text reading.
   For each paper, include:
   - PMID/title
   - priority level
   - rationale based on PubMed metadata and reviewed abstract content only
   - specific questions to answer from full text
   - what evidence would be needed before upgrading the record to `full_text_reviewed`

4. `ABSTRACT_REVIEW.md`
   Include abstract-level synthesis only.
   Group by theme where useful.
   Clearly mark:
   - supported by abstract
   - uncertain
   - not assessed
   - requires full-text review

5. `FULL_TEXT_READING_PLAN.md`
   Include a future full-text review plan.
   Specify:
   - which papers to read first
   - what evidence to extract from full text
   - methods, figures, tables, supplementary data, and limitations to check
   - what would be needed before any record can be upgraded to `full_text_reviewed`
   - confirmation that current abstract-screening output is not full-text review unless full text was actually supplied and read

Final response:
- Provide the downloadable zip package when supported.
- Also include a brief note listing the files included.
- State whether any optional `paper_note_drafts/*.md` were included.
- State that the outputs are abstract-screening materials for human review, not final paper notes.
```
