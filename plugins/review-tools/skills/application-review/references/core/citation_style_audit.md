# Citation Style and Reference-List Audit

## Scope and authority

Run this audit in **every Sprint and GatedSprint** for each authorized document containing scholarly in-text citations or a scholarly reference list (research statements, plans, proposals, manuscripts, and cited scientific sections of a mixed package). If none exists, report `Not applicable: no scholarly citations or reference list in the authorized scope`. This audit checks **how existing sources are cited and listed**. Run claim-to-citation sufficiency, source credibility, and factual verification separately; a correctly formatted citation does not establish that it supports a claim.

Resolve the exact destination, document type, submission stage, and any current instructions before selecting a style. Decide two axes separately: **in-text citation style** and **reference-list style**. Precedence on each axis is explicit current destination instructions and supplied official template > the user's explicit decision for that axis where permitted > a named journal profile explicitly selected for that axis > a consistent established style in a non-journal document. Do not infer one axis from the other or infer the required style from the journal in which a cited paper appeared. A tenure-track research statement is an NIH job-application document; Nature, Cell, and Science formats are supported options, **not NIH-imposed requirements**. Never label a user preference an official requirement.

In GatedSprint, ambiguous, unspecified, or hybrid style is a decision gate, not a
license to normalize. Ask and record two separate questions and decisions:

1. Which style controls in-text citations?
2. Which style controls the reference list?

The answers may legitimately differ. Do not implement either axis while its
decision remains ambiguous. Treat a current CV as authority for reference-list
form only after the user explicitly confirms that choice; never infer body
citation style from the CV. Preserve or remove applicant-specific annotations,
symbols, contribution notes, or selected-publication markers only after an
explicit separate confirmation. A broad instruction such as `normalize
references` is insufficient; decompose it into exact bounded decision IDs.

The profiles below are defaults for the named flagship journals and are subordinate to the exact journal's current author instructions, manuscript stage, article type, and template. “Cell Press” and “Nature Portfolio” do not imply that every sister journal uses the flagship style. Do not silently apply a journal profile when the target is a different title.

## Audit procedure

1. **Inventory and resolve two style decisions.** Record the document, file format, reference-list location, and any explicit exception. Record the in-text target/profile, authority, date checked, and decision ID separately from the reference-list target/profile, authority, date checked, and decision ID. If a reference list is absent, distinguish `no citations` from `citations present but list missing`. Record applicant-specific annotation treatment as a third decision when relevant.
2. **In-text form.** Check numeral versus author–date, superscript versus baseline, parentheses/brackets, italics, grouped citations, ranges, separation from punctuation, and any journal-specific note placement. Compare actual rich-text formatting where available. Do not classify years, equations, figure/panel labels, footnotes, or numeric results as literature citations.
3. **Number mapping and order.** Traverse the document in reading order, including headings, tables, boxes, captions, footnotes, supplementary/Methods sections only as directed by the target. Check the first citation of each distinct source, consecutive numbering, same-number reuse on later citations, sorted grouped numbers and valid ranges, no gaps/duplicate mappings, and exact one-to-one consistency between each in-text number and the numbered bibliography. Flag uncited list entries, cited numbers without an entry, and records that cite a different paper under the same number. Do not renumber solely from reference-list order without mapping every occurrence.
4. **Bibliography metadata.** For each item, inspect authors and order/et al. rule, article or chapter title, journal/book title and required abbreviation, publication year/date, volume, issue **only if required by that target or needed to identify the source**, page span or article/eLocator number, and DOI/URL where required or useful. Check preprints, datasets, books, and “in press” items against the target's separate rules. Verify metadata against authorized source material or a reliable bibliographic record when accessible; mark unverified fields instead of inventing them. Treat content errors independently from typography.
5. **Typography and punctuation.** Inspect journal-title italics, volume bold, author/title/year style, punctuation, spacing, en dashes, and number formatting against the chosen profile and exact target examples. In a DOCX, inspect run-level superscript/italic/bold (including citations split across runs) and render the result for visible QC. Text extraction or TXT alone cannot prove rich-text styling; PDF visual inspection supports appearance but not editable run properties. State `Typography not assessable from supplied format` for any uninspectable attribute rather than claiming a pass.
6. **Output and repair.** Give a verdict `PASS / CONDITIONAL PASS / FAIL / NOT ASSESSABLE / NOT APPLICABLE` and a compact finding table: axis, document/location, observed form, target rule, exact current form, exact proposed form, evidence/verification status, and decision ID. Separate global style migration from local mechanical errors. Never add a new source, change authorship or publication status, or claim that a paper supports a passage without verification. Under GatedSprint, every textual correction inherits the Explicit-Approval Invariant and remains unimplemented until its exact ID is approved.

## Supported journal profiles

| Target | In-text citations | Reference numbering | Reference-list fields and typography |
| --- | --- | --- | --- |
| **Nature** (flagship) | Unbracketed superscript numerals; place and group according to its current guide. | Number consecutively in first-mention order, including relevant text, tables, boxes, figure legends, Methods and Extended Data according to the guide; reuse the assigned number. | Surnames/initials; article title in roman type; abbreviated *journal title*; **volume**; page range or article number; year. Apply the current guide's author-count/et al. rule and punctuation. Issue number is not a universal mandatory field. |
| **Cell** (flagship) | Consecutive superscript numerals under Cell's current final-file instructions. | First occurrence assigns the number; reuse it and reconcile the list. | Check authors, year, full article title, journal title/abbreviation, volume, pages or article number, and DOI against Cell's current final-file instructions. Check bold/italic placement against the exact Cell template or current published example before marking typography `PASS`; this file does not assert an unverified universal Cell Press typography rule. |
| **Science** (flagship) | Numerals in *italicized parentheses*, such as *(1, 2)*, under the current Science manuscript instructions; do not turn these into Nature/Cell superscripts. | Number in first-citation order and reconcile text and list under current instructions. | Complete authors and article title; *journal title* and **volume**; year; pages or article number as applicable. Follow the current article-type/stage guidance for DOI, abbreviation, punctuation and exceptions. |

The examples in this table illustrate the distinctive styles, not a substitute for live instructions. Current sources checked 2026-09-24:

- Nature, [Formatting guide](https://www.nature.com/nature/for-authors/formatting-guide).
- Cell Press, [Referencing style announcement](https://www.cell.com/news-do/Cell-Press-referencing-style), and Cell, [Final files checklist](https://www.cell.com/pb-assets/journals/EM/MasterFFCs/CELLFFC-1781892688883.pdf). Verify the particular Cell journal's current guide and specimen before strict reference typography judgments.
- Science, [Instructions for preparing an initial manuscript](https://www.science.org/content/page/instructions-preparing-initial-manuscript) and [Instructions for authors of new research articles](https://www.science.org/content/page/instructions-authors-new-research-articles).

## Mode-specific behavior

- **GatedSprint Phase 1:** inspect and report the citation-style verdict and exact proposed fixes in the approval packet. No files are edited. Record separate in-text and reference-list decisions; ask separate user questions for every ambiguous, unspecified, or hybrid axis. A complete style conversion, annotation treatment, and any ambiguous renumbering remain explicit decisions. Repeat the audit on generated files after Phase 4 approval, including rendered and run-level QC when feasible, and map every textual delta to an approved ID.
- **Sprint:** include the same audit in QC before and after edits. Apply only a chosen, authorized, deterministic local correction that preserves source identity and meets the normal decision gate. For renumbering, build an old-number-to-source-to-new-number mapping, update every in-text occurrence and list entry together, then verify no dangling or duplicated mapping; otherwise propose the change for human decision. Report remaining typography or metadata uncertainty.
- A bare `Sprint` or `GatedSprint` with a research statement does not authorize choosing a different journal style merely to make the document look journal-like. For Sprint, keep a consistent existing style when no controlling rule or user selection exists and report the assumption. For GatedSprint, report the ambiguity and ask the two axis-specific questions before implementing a style choice.
