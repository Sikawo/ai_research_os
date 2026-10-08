# Application Review Support Engine

## Authority Boundary

This file is a subordinate review module. It does not activate, route, or
execute Sprint or GatedSprint, and it does not authorize edits, file creation,
or approval-state transitions. Exact bare Sprint and every GatedSprint route
belong exclusively to the canonical entrypoint:

```text
plugins/gated-sprint/skills/gated-sprint/SKILL.md
```

The canonical workflow may delegate a bounded review question to this module.
Outside that delegation, the public `application-review` skill performs focused
review only.

## Purpose

Coordinate reusable diagnostic layers without creating a competing workflow:

- Scientific Serendipity support for explicitly eligible scientific material;
- public-background review perspectives without reviewer impersonation;
- target-specific rubric and constraint checks;
- architecture, reviewer, quality-control, and writing lenses; and
- evidence, integrity, and uncertainty labels.

## Non-Negotiable Rules

- Treat all supplied material as read-only unless the owning workflow separately
  authorizes a specific edit.
- Scientific coherence is a hard gate; novelty and fluent prose cannot rescue an
  incoherent model.
- Do not invent requirements, evidence, achievements, reviewer opinions, or
  selection outcomes.
- Keep scientific critique, target fit, structural strategy, rubric compliance,
  writing clarity, and uncertainty as separate judgments.
- Do not read protected material unless an owning workflow has explicit scope to
  provide it.
- Return recommendations and structured diagnostics to the caller; do not make
  workflow-state decisions here.

## Diagnostic Layers

### Scientific Serendipity Support

When the caller selects `full`, build a compact Scientific Model and Anomaly
Register, explore alternatives without reviewer-ranking anchors, apply the
Scientific Coherence Firewall, and return admitted candidates. For
`narrative_only`, limit exploration to framing. For `off`, skip the layer.
This work never broadens content access or edit authority.

### Reviewer Background Support

Use public information to describe field priorities, institutional mission
signals, common concerns, and technical standards. Never infer private opinions
or an actual reviewer assignment.

### Focused Review Lenses

- Architecture: compare structure and narrative strategy.
- Reviewer: stress-test clarity, evidence, feasibility, and impact.
- Rubric and QC: check explicit constraints and cross-document consistency.
- Writer: suggest meaning-preserving language improvements.

### Rubric Status

Label each requirement `confirmed`, `working`, `unknown`, or `not applicable`.
Keep the source of every confirmed requirement inspectable.

## Repeated-Advice Control

When authorized prior-decision context is available, classify advice as `new`,
`deepened`, `already known`, or `retired`. Do not fill the response with advice
that adds no new value.

## Return Contract

Return only the requested diagnostics, including:

- findings separated by review lens;
- evidence and uncertainty labels;
- unresolved questions or missing inputs;
- bounded recommendations; and
- risks that require human or specialist judgment.

The caller decides whether these diagnostics become proposals, edits, or no
action.
