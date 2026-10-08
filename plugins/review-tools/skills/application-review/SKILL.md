---
name: application-review
description: Review the structure, evidence, integrity, reviewer readability, and compliance of an application or scientific proposal when the user requests a focused review that is not a full Sprint or GatedSprint run. Defer exact bare Sprint, GatedSprint, staged full review, and active GatedSprint continuations to the gated-sprint skill.
metadata:
  version: "1.0.0"
---

# Application Review

Provide a focused, evidence-preserving review without claiming edit authority.
This skill supplies reusable review components; it is not an alternative
Sprint entrypoint.

## Authority boundary

- Exact bare `Sprint` and any `GatedSprint` invocation belong exclusively to
  the `gated-sprint` skill.
- A focused review does not authorize source-document editing.
- Target-specific instructions, rubrics, profiles, and application context
  must be supplied separately and remain outside this public package.
- Never infer missing achievements, evidence, citations, eligibility, reviewer
  identity, private context, or experimental results.

## Focused review route

1. Confirm the document type, review question, available source, and requested
   depth.
2. Read [engine.md](references/core/engine.md) and only the modules needed for
   the requested review.
3. Use the relevant generic rubric under `references/rubrics/`.
4. Apply [evidence_and_integrity_rules.md](references/core/evidence_and_integrity_rules.md)
   before scoring or recommending changes.
5. When scientific argument quality is in scope, use
   [scientific_argument_gate.md](references/core/scientific_argument_gate.md).
6. When reviewer comprehension is in scope, use
   [tired_brilliant_outsider_test.md](references/core/tired_brilliant_outsider_test.md).
7. Return findings, evidence, uncertainty, and the smallest sufficient next
   action. Do not silently implement recommendations.

## Optional modules

- Career documents: `references/career-documents/`
- Review modes: `references/modes/`
- Scientific coherence and serendipity: the matching files under
  `references/core/`
- Reusable output structures: `assets/templates/`

Do not load private profiles, application instances, or unrelated scientific
material merely to enrich a review.
