# Proposal Completeness, Significance, and Citation Gate

## Purpose

This gate runs at the beginning of `GatedSprint` Phase 1 for grant proposals,
before Portfolio Curator classification, architecture analysis, reviewer-panel
stress testing, or writer-polish scans.

It detects essential proposal functions that are absent, assumed, weakly
framed, or unsupported by references. It must be applied in addition to the
target-program rubric, institution overlay, and reviewer-background overlays.
The generic grant rubric is a mandatory baseline for grant proposals, not a
fallback.

Default grant-proposal baseline:

```text
Universal Grant Baseline
+ Target-Program Rubric
+ Institution-Specific Overlay
+ Domain-Specialist Reviewer Overlays
```

## Shared argument contract

Delegate motivation, significance, program focus, constructive repairs, and
unresolved-finding readiness to
`plugins/review-tools/skills/application-review/references/core/scientific_argument_gate.md`. Run the common audit
once and reuse its evidence here. This grant gate retains its required rubric,
background, citation audit, component table, and structural verdicts. Career
research statements use the common contract without importing this grant gate.
Map common `EXPLICIT / IMPLICIT / WEAK / MISSING` to this component table's
`Present / Implicit / Weak / Missing`; preserve `NOT_ASSESSABLE` explicitly
instead of calling it Present. Grant structural PASS cannot override a shared
`REVISION_REQUIRED` or `NOT_ASSESSABLE` argument verdict.

## Required Rubric Stack

For any grant-proposal `GatedSprint`, load at least:

```text
plugins/review-tools/skills/application-review/references/rubrics/generic_grant_rubric.md
plugins/review-tools/skills/application-review/references/core/proposal_completeness_significance_citation_gate.md
```

Then load the relevant target-program rubric, institution overlay, reviewer
background layer, and authorized source documents.

For program-specific grant-proposal runs, the minimum stack is:

```text
plugins/review-tools/skills/application-review/references/rubrics/generic_grant_rubric.md
plugins/review-tools/skills/application-review/references/core/proposal_completeness_significance_citation_gate.md
an authorized private application context
an authorized private application context
```

## Independent Reviewer Role

Add an independent role before the existing domain-specialist panel:

```text
Skeptical Proposal Completeness Reviewer
```

This reviewer focuses first on missing information rather than improving prose
that is already present. Keep these tasks distinct:

```text
Evaluate the quality of content that is present.
Detect essential content that is absent.
```

The Skeptical Proposal Completeness Reviewer must answer:

1. What essential information is completely absent?
2. What does the author assume the reviewer already knows?
3. Which established claims or prior findings lack literature support?
4. Is the scientific significance explicit?
5. Is the human-health or societal relevance explicit and credible?
6. Why does each Aim matter?
7. Which missing component would most reduce the review score despite otherwise
   strong aims?
8. Are foundational concepts introduced and supported, or merely treated as
   givens?

## Component Ratings

Evaluate each required component by function, not by heading. Use exactly one
rating per component:

```text
Present
Implicit
Weak
Missing
Not applicable with justification
```

At minimum, audit:

- broad biological, biomedical, technical, or societal problem;
- relevant background and current field knowledge;
- critical knowledge gap;
- overall scientific significance;
- human-health or societal relevance;
- central hypothesis or organizing question;
- innovation or conceptual advance;
- preliminary support;
- aim-specific rationale;
- aim-specific significance;
- expected knowledge gained;
- risks and alternatives;
- literature and reference support;
- cross-aim integration.

Do not determine significance from the presence of a heading named
`Significance`. Determine whether a reviewer can answer these questions without
supplying external knowledge or reconstructing unstated reasoning:

```text
What problem is being addressed?
What is already known?
What remains unknown?
Why does the missing knowledge matter?
Why should the target program or institute care?
What changes scientifically, technically, medically, or socially if the project succeeds?
```

## Structural Completeness Verdict

After the canonical v2 decision-efficient front matter, the grant-specific
detail of every grant-proposal `GatedSprint` approval packet must begin with:

```text
Structural Completeness Verdict:
PASS
CONDITIONAL PASS
FAIL
```

Default verdict rules:

- Use `FAIL` when any required component is `Missing` and the omission would
  prevent a reviewer from understanding the problem, gap, significance,
  aim-specific rationale, or literature basis.
- Do not assign `PASS` when any of these are `Missing`: overall problem or
  background, explicit knowledge gap, overall significance, aim-specific
  rationale, or literature support for major prior-knowledge blocks.
- Use `CONDITIONAL PASS` when all essential functions are present but one or
  more are `Implicit` or `Weak` enough to require correction before submission.
- Use `PASS` only when the proposal is reviewer-complete at the structural
  level. The prose may still need architecture, reviewer, QC, or writer work.
- Mark human-health or societal relevance as `Not applicable with
  justification` only when justified by the application type, research field,
  and target-program requirements.

The system may praise strong aims while still issuing `FAIL`. Positive comments
about aim coherence must not suppress structural omissions. For example:

```text
The aims are distinct and internally coherent. However, the proposal is not yet
reviewer-complete because its background, overall significance, human-health
relevance, or literature anchoring is insufficient.
```

## Proposal Anatomy And Completeness Audit

For each component, report:

- component;
- rating;
- evidence found in the authorized source;
- missing or weak function;
- reviewer consequence;
- recommended action;
- proposed change packet classification.

Structural-omission recommendations must also appear in the Proposed Change
Packet with `change_risk` set to `Green`, `Yellow`, or `Red` and domain risk
recorded separately as `NONE`, `SPECIALIST_REVIEW_REQUIRED`, or `CLEARED`.
Adding or substantially reorganizing a `Significance` section is usually
`Yellow` because it changes structure or emphasis.

## Significance Chain Audit

Execute the program and per-Aim chain from `scientific_argument_gate.md` and
reuse its evidence in `Overall Significance Chain` and `Aim-Level Significance
Audit`. Do not repeat an independent scoring pass or treat a heading as proof.
Preserve the grant-specific known-background and literature context alongside
the shared problem, gap, significance, knowledge gain, and contribution checks.

Recommendations may integrate significance into the opening or an Aim rather
than add a new heading. Do not force one section structure, clinical impact,
or serial Aim dependencies. Every major repair needs evidence, tradeoffs, and
a testable resolution condition; missing support requires verification, not
invented claims or citations.

## Claim-To-Citation Audit

Do not use biology-specific terms, current-application terms, gene names,
pathway names, disease names, vesicle language, or other hard-coded domain
keywords to decide whether a citation is needed.

The audit unit is a meaningful paragraph, passage, or sequence of related
sentences rather than each sentence in isolation.

Classify relevant content as:

1. Established prior fact or field knowledge
2. Specific prior mechanistic or empirical finding
3. Applicant preliminary result
4. Working hypothesis
5. Speculation or future implication
6. General framing or common knowledge

Flag a passage only when all of the following apply:

- It describes previously established facts, prior findings, or field
  knowledge.
- The passage supports the proposal's rationale, significance, mechanistic
  premise, interpretation, or experimental design.
- No supporting citation appears within the passage or in a reasonably nearby
  location.

Suitable output language includes:

```text
Established prior knowledge is presented in this paragraph without a supporting reference.
This passage summarizes prior findings that support the proposal rationale, but no citation is provided.
A foundational concept is treated as established without literature anchoring.
```

Do not automatically classify these as missing citations:

- content clearly identified as the applicant's preliminary data;
- statements explicitly framed as hypotheses, predictions, or proposed models;
- research objectives or planned experiments;
- broad common-knowledge statements that normally do not require citation;
- passages reasonably supported by a citation immediately before or after the
  relevant text block;
- multi-sentence paragraphs with a citation at the beginning or end that
  plausibly supports the whole block.

When possible, distinguish:

```text
A citation is present.
The available citation appears to support the main claims of this passage.
```

Do not invent references or perform uncontrolled citation insertion during
Phase 1. When the exact supporting reference cannot be verified, record:

```text
Citation needed; exact supporting reference requires verification.
```

Only suggest a candidate reference when it exists in an authorized source,
approved paper library, or source explicitly provided by the user.

## Required Approval-Packet Sections

Place these sections near the top of every grant-proposal `GatedSprint`
approval packet:

```text
## Structural Completeness Verdict
## Critical Structural Omissions
## Proposal Anatomy Audit
## Overall Significance Chain
## Aim-Level Significance Audit
## Claims or Passages Requiring References
```

For each entry under `Claims or Passages Requiring References`, include when
available:

- Document
- Section or page
- Paragraph or passage identifier
- Claim type
- Why a citation is needed
- Whether a nearby citation may already support it
- Required action
- Exact-reference verification status
