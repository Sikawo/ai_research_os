# Document Type Router

## Purpose

Decide whether the target calls for a resume, CV, cover letter,
recommendation letter, scientific research plan/statement, personal statement,
or mixed document packet before reviewing or revising text.

## Scientific Research Plan Or Statement

For this route, load `plugins/review-tools/skills/application-review/references/core/scientific_argument_gate.md`
and its report template for source-only reconstruction, motivation, significance,
focus, unresolved-finding tracking, and final consistency checking. This shared
contract applies without importing the grant-specific completeness gate or rubric.
Non-scientific routes below do not inherit it; route mixed packages per document.

Use this route for a faculty, PI, group-leader, fellowship, or comparable
scientific application document whose primary function is to explain past
discoveries, a current scientific model, or a future research program. Load the
shared `tired_brilliant_outsider_test.md` and, when page/layout planning is in
scope, the scientific-document behavior in `word_output_format_policy.md`.

Actively test one meaningful visual per substantive page and default toward one
only when it reduces cognitive load or increases evidentiary confidence. This is
not a quota. The same package's ordinary cover letter, CV, recommendation or
reference letter, and personal statement remain on their own non-scientific
routes and do not inherit forced-figure behavior.

## CV

Use CV when the target is:

- faculty;
- research-intensive;
- academic or scholarly;
- fellowship;
- grant;
- award;
- postdoc or research-training application where complete research history
  matters;
- explicitly asking for a CV.

CV review should prioritize academic/research audience fit, completeness of
scholarly sections, reverse chronological consistency, research trajectory,
publication clarity, and fit with the target.

## Resume

Use resume for most non-academic and non-research-intensive jobs unless the
posting explicitly asks for a CV.

Resume review should prioritize target relevance, ATS readability, concise
reverse chronological structure, strong PAR bullets, accurate quantification,
and section order responsive to the target.

When the target is an industry role and the user requests AI/ATS evidence
review, qualification matching, or tailoring against a supplied job
description, select `RESUME` and enable the conditional workflow in
`plugins/gated-sprint/skills/gated-sprint/references/industry-resume.md`.
Ordinary resume work with `ai_ats_mode` omitted remains on the legacy route.
Do not redirect a CV to this route unless the user explicitly requests an
industry resume derived from that CV.

## Cover Letter

Use cover-letter review when the target asks for or reasonably expects an
introductory letter, inquiry email, or email-body application note.

Cover-letter review should distinguish:

- business-letter submission;
- email-body variant;
- academic letter where more length may be justified;
- brief postdoc or lab inquiry.

## Recommendation Letter

Use recommendation-letter review when the prompt, target, or source scope asks
for or reasonably implies a recommendation letter, reference letter, letter of
support, referee letter, referee statement, LoR, recommendation draft,
`推薦書`, `推薦状`, or `レコメンデーションレター`.

When this document type is selected, load:

```text
plugins/review-tools/skills/application-review/references/career-documents/recommendation_letter_profile.md
```

Recommendation-letter review should prioritize recommender voice, relationship
credibility, evidence strength, claim boundaries, anti-CV-summary discipline,
bias-coded or vague praise, unsupported superlatives, applicant-authored or
AI-like phrasing, and missing information.

## Multi-Document Package

Use package review when the user supplies more than one document type. Check
target fit and cross-document consistency without duplicating every claim.
Route each document independently; the presence of a scientific research
statement does not activate visual-first planning for the rest of the package.

## Ambiguous Targets

If ambiguous:

1. mark document type as `unknown`;
2. recommend the safest likely document type;
3. ask only if the choice would materially change the revision;
4. record the recommendation and uncertainty in the report.

## U.S. Default

For U.S. career documents, do not include photo, marital or parental status,
birth date or place, Social Security number, salary requirements, references,
"references available upon request," personal pronouns in bullet prose, or
similar personal fields unless the target explicitly requires the information or
the user chooses to include a user-choice disclosure.
