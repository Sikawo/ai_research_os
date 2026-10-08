# Sprint Output Contract

## Required Output Package

Every Sprint must produce these files when source files and format tooling make
them possible:

1. Revised document files.
   - Use DOCX when source documents are DOCX.
   - Preserve original formatting as much as practical.
   - Use clear, versioned filenames.
2. Revised plain-text files.
   - Produce one TXT file per revised document.
   - Match the revised DOCX content as much as practical.
3. Change report.
   - What changed.
   - Current root version-group identity, candidate and archived group
     paths/names, promotion and verification status, storage destination, and
     whether an independent backup was available.
   - Why it changed.
   - Which changes were auto-applied.
   - Which changes were deliberately not made.
   - For eligible scientific documents, criterion-level evidence and argument
     readiness before/after; do not require an overall score. Other documents
     retain their before/after score estimate. Preserve separate 1–5
     natural-prose/structure and confident/proportionate-tone rows with evidence
     for prose documents; use `— Not assessable` when appropriate.
   - Remaining reviewer risks.
   - Scholarly citation-style verdict, selected profile, number mapping, bibliography/typography findings, repairs, and unverified fields when applicable.
   - Word Layout Summary when DOCX creation or material reformatting occurred.
   - Tired Reviewer Reconstruction Summary for scientific proposals, research
     plans, research statements, and PI/group-leader programs.
4. Human-decision proposals.
   - Recommendation, benefit, risk, sacrifice, and approval requirement.
5. Internal logs.
   - Content portfolio matrix.
   - Architecture candidates.
   - Reviewer comparison scorecard.
   - Revision decision log.
   - Change ledger.
   - Repeated-advice memory.
   - Do-not-change registry.
   - Compact Scientific Model run artifact when `serendipity_mode: full`.
   - Authorized Serendipity Memory update or proposed update when applicable.

## Conditional Industry Resume AI/ATS Package

When document routing selects an industry `RESUME` and
`industry_resume.ai_ats_mode=true`, also produce the route-neutral artifacts
defined in
`plugins/gated-sprint/skills/gated-sprint/references/industry-resume.md`:

- the exact resume candidate when the selected execution policy permits file
  generation;
- job-description analysis and structured requirements;
- requirement-to-evidence matrix with provenance and Level 0-4 evidence;
- ATS extraction audit;
- qualification-evidence audit that reads only the exact candidate resume;
- recruiter/top-third and role-specific hiring-manager audits;
- integrity audit;
- `TRUE_GAP`, `RESUME_GAP`, and `POSITIONING_GAP` report;
- concise dashboard with required/preferred counts, evidence bands, and gate
  statuses; and
- one schema-valid structured sidecar, conventionally
  `industry-resume-analysis.json`.

The Markdown package follows
`plugins/gated-sprint/skills/gated-sprint/references/industry-resume.md`.
Do not expose private evidence excerpts in public review packets or INFO logs.
Do not report a single opaque match percentage or claim equivalence to a
proprietary recruiting system. When `ai_ats_mode=false` or omitted for
ordinary legacy resume work, this package is not required.

## Scientific Argument Review

Complete for each eligible grant proposal or scientific research plan/statement;
ordinary non-scientific documents state `Not applicable`. Execute
`plugins/review-tools/skills/application-review/references/core/scientific_argument_gate.md` and use
`plugins/review-tools/skills/application-review/assets/templates/scientific_argument_review_template.md`.

- Document/version and actual route/checks completed:
- Source-only reconstructed primary goal; context exposure if any:
- Argument readiness: `READY / REVISION_REQUIRED / NOT_ASSESSABLE`
- Review execution and source coverage; remaining assessment limits:
- Program and per-Aim evidence/absence; reader consequence:
- Opening significance audit for the program, every Aim/project, and each major
  argumentative paragraph that introduces a new question, direction, or claim, with
  `EARLY / DELAYED / MISSING / NOT_ASSESSABLE`, opening and later locators, and
  the minimum supported move/compression/preview when needed:
- Concrete repairs, tradeoffs, and resolution conditions by finding ID:
- Carried-forward, deferred, accepted, and verified-resolved IDs:
- Evidence-based change from baseline, separate from present adequacy:
- Criterion scores/counterconcerns only when assessable; no overall merit total:
- Automated consistency validation: `PASS / FAIL / NOT RUN` and actual evidence:

A consistency PASS may accompany `REVISION_REQUIRED`; it validates the report,
not the document's quality. Phase 1 suggestions are not implemented repairs.
After final revisions and polish, re-review the actual source and retain
unresolved risks. Official criteria, submission compliance, voice/tone, and
visual verdicts remain separate; none may erase argument-readiness failures.

## Scientific Opportunity Summary

For normal scientific Sprint/GatedSprint output in `full` mode, include a
concise decision-facing section:

1. **Best Current Scientific Model** — one concise description.
2. **Coherent Unconventional Survivors** — normally at most 2–3, each with idea,
   why interesting, why it survives scrutiny, new discriminating prediction,
   main weakness/kill condition, scientific insight magnitude, current edit
   magnitude, and recommendation.
3. **Important Speculative Seeds** — normally at most 1–3, only with plausible
   value and explicit failure/rescue conditions.
4. **Important Anomalies** — only those materially affecting the story.
5. **No-Action Insights** — useful ideas withheld because of maturity, scope,
   evidence, or human constraints.

Do not show every operator, rejected candidate, full score table, repetitive
analogy, or memory entry by default. Literature novelty remains `NOT VERIFIED`
unless a separate authorized workflow verified it.

## Human-Facing Final Response

After a Sprint, the final response must include only:

- Files produced.
- One-sentence application identity.
- Best architecture decision.
- Auto-applied changes.
- Human-decision proposals.
- Required QC fixes, including citation-style issues when applicable.
- Before/after criterion evidence and argument readiness for eligible scientific
  documents; other documents retain the score estimate. Keep the two anchored
  voice/tone rows for prose documents (actual original and revised scores,
  exact examples, reviewer effect, and smallest safe action or `keep`).
- Scientific Argument Review summary for eligible documents, with unresolved
  finding IDs, concrete repairs, resolution conditions, and validation status.
- What was deliberately not changed.
- Scientific Opportunity Summary when full serendipity applies.
- Word Layout Summary when Word output was created or materially reformatted.
- Tired Reviewer Reconstruction Summary when a scientific proposal, research
  plan, research statement, or PI/group-leader program was reviewed.
- Industry Resume Audit Summary and visible gap report when the conditional
  AI/ATS evidence route is enabled.

Do not dump long internal logs into the final response unless the user asks.

## Tired Reviewer Reconstruction Summary

For an eligible scientific document, report separately:

- Full-read comprehension;
- Importance / impact comprehension;
- 10-second reconstruction;
- 60-second reconstruction;
- 5-minute memory;
- Rapid-skim comprehension;
- Visual narrative;
- Figure-by-figure reviewer-question test;
- Skim-to-full-text consistency;
- most memorable scientific idea;
- most likely tired-reviewer misinterpretation;
- smallest safe corrective action.

When layout planning is in scope, include a page-level visual plan with page or
section, narrative job, main reviewer doubt, visual recommended yes/no, visual
function, figure/placeholder type, take-home message, evidence/provenance
boundary, approximate page-area budget, and reason for omission when no visual
is recommended. Do not add this scientific-visual section to ordinary
non-scientific career documents.

## Formatting Preservation Disclosure

If DOCX formatting preservation is incomplete, say so in the change report and
name the affected file or element.

## Word Layout Summary

When applicable, report only the decision-relevant format facts:

- controlling official/template constraints;
- resolved body font/alignment, line spacing, paragraph spacing, and margins;
- final page count and page-specific visual/placeholder plan;
- deviations from the defaults and why;
- unresolved page-limit, rendering, or format-preservation risks;
- confirmation that any placeholder is concept-only and contains no invented
  data, result, experiment, citation, or quantitative relationship.

Do not list every small pagination adjustment.
