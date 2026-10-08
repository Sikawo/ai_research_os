# Focused Review Module Selector

## Authority Boundary

This subordinate selector chooses an internal review lens after another skill
or the user has already requested a focused review. It is not a command router
and must not activate Sprint or GatedSprint.

Exact bare Sprint and every GatedSprint route belong exclusively to:

```text
plugins/gated-sprint/skills/gated-sprint/SKILL.md
```

If that canonical package is unavailable or inconsistent with its manifest,
report the drift. Do not substitute this selector as a legacy execution path.

## Inputs

Select a module from the explicit review objective, authorized document type,
target requirements, supplied sources, and requested output. Never infer
permission to read additional material or edit a source.

## Module Selection

### Architecture Review

Select for structure, narrative spine, project order, deletion or compression
tradeoffs, and comparison of supported future directions. Return alternatives
and tradeoffs; do not implement them.

### Reviewer Stress Test

Select for strengths, concerns, dangerous questions, feasibility, target fit,
or panel-style critique. Use `plugins/review-tools/skills/reviewer-lens/` for the
core reviewer behavior. Do not impersonate a real reviewer.

### Rubric and Quality Control

Select for eligibility, required sections, page or format constraints,
cross-document consistency, publication status, figures, tables, references,
or submission readiness. Distinguish confirmed requirements from unknowns.

### Writing Review

Select for clarity, tone, flow, concision, and meaning-preserving language
suggestions. Do not add scientific content or restructure a program unless the
request separately includes architecture review.

### Career-Document Support

For a resume, CV, cover letter, recommendation letter, research statement, or
career packet, load the support index at:

```text
plugins/review-tools/skills/application-review/references/career-documents/README.md
```

For an industry resume with an explicitly authorized evidence or qualification
assessment, the canonical caller may also load:

```text
plugins/gated-sprint/skills/gated-sprint/references/industry-resume.md
```

That reference remains under the canonical workflow's authority.

## Scientific Support

When applicable, classify the Scientific Serendipity support level as `full`,
`narrative_only`, or `off`. Scientific grants, fellowships, manuscripts, and
research plans may use `full`; career prose may use `narrative_only`; resumes
and CVs default to `off`. These defaults do not authorize source access.

## Document-Type Applicability

Before review, label each requested gate `APPLICABLE`, `NOT_APPLICABLE`, or
`NOT_ASSESSABLE`. Keep content authority, layout authority, editable target,
and current/final designation separate. A generated preview does not establish
final layout authority.

## Ambiguity Rules

- A general request for reviewer judgment selects Reviewer Stress Test.
- A structural-change question selects Architecture Review.
- A readiness question selects Rubric and Quality Control and may recommend a
  separate reviewer stress test.
- A wording-only question selects Writing Review.
- If the objective or source authority is materially unclear, ask a narrow
  question instead of escalating scope.

## Output

Return the selected module, applicability decisions, diagnostics, evidence
labels, and unresolved inputs. No selection in this file authorizes source
edits, artifact generation, workflow-phase changes, or approval recording.
