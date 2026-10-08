# Canonical Workflow Review Support

## Status

The filename is retained for source-to-destination traceability. This document
is a subordinate support module, not an execution engine or user-facing command
definition. It must never
activate, route, or implement Sprint or GatedSprint.

Exact bare Sprint and every GatedSprint route are owned by:

```text
plugins/gated-sprint/skills/gated-sprint/SKILL.md
```

The canonical workflow may call the review-tools plugin for a bounded analysis.
That call does not transfer source-edit, approval-ledger, release, or artifact
authority to this module.

## Supported Diagnostic Sequence

When the canonical workflow delegates a full application review, return
diagnostics in this order:

1. Resolve the authorized document type, target, and constraints supplied by
   the caller.
2. Identify repeated-advice context only when it is explicitly provided.
3. Apply the configured Scientific Serendipity support level without widening
   source access.
4. Build a content portfolio when the document type benefits from one.
5. Compare the baseline with supported architecture alternatives.
6. Stress-test the alternatives using reviewer and rubric lenses.
7. Classify potential changes by evidence, factual risk, and tradeoff.
8. Return recommendations, blocked claims, unresolved risks, and missing inputs.

This sequence produces analysis only. It does not edit source files, create
final artifacts, advance a workflow phase, or record user approval.

## Scientific Argument Support

For grant proposals and scientific research plans or statements, the caller may
request `scientific_argument_gate.md`. Record a source-only cold-reader pass and
essential-function audit before architecture comparison, then report readiness,
coverage, evidence, and unresolved identifiers. Ordinary non-scientific career
documents do not inherit this gate.

## Architecture Comparison

Keep the baseline as a comparator. Only coherence-admitted scientific models
may enter narrative comparison. Separate scientific insight magnitude from the
size and risk of a possible edit. It is valid for the baseline to remain the
strongest option.

## Safety Boundary

- Unsupported claims, causality, novelty, status, ownership, or evidence remain
  `BLOCKED`.
- Central-hypothesis changes, new experiments, reinterpretations, and project
  merges or splits require human judgment in the owning workflow.
- Formatting suggestions must preserve official templates, page constraints,
  source meaning, and inspectable evidence.
- Persistent memory is outside this module unless separately authorized.

## Return Contract

Return a structured diagnostic package compatible with
`output_contract.md`, including findings, candidate comparisons, evidence
labels, bounded recommendations, and risks. The canonical caller owns all
subsequent implementation and release decisions.
