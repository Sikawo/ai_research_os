# GatedSprint Explicit-Approval Regression Cases

All text in this file is invented for workflow regression testing. It is not an
application draft, scientific claim, citation recommendation, or instruction to
edit a real document.

## Case A — Approved citation insertion does not approve an opening rewrite

### Synthetic baseline

> Layered sensors lose calibration when ambient humidity changes.

Phase 1 decision `GS-CIT-01` proposes only adding the already verified citation
marker to that sentence. The user approves `GS-CIT-01`. During final polish,
the model prefers the new opening, “Humidity is a pervasive barrier to reliable
layered sensing.”

### Expected behavior

Add only the approved citation marker. The alternative opening has no decision
ID and must remain unimplemented. Record it as a new opportunity for a later
agenda. If it appeared in the generated file, classify it as an unmapped
model-generated textual delta and revert it.

## Case B — A citation-only source comment is exact and local

### Synthetic source comment

> Add the verified reference here.

### Expected behavior

The comment authorizes proposing the exact citation insertion at that location.
It does not authorize rephrasing the sentence, joining it to a neighboring
sentence, changing emphasis, or migrating the document's citation style. Record
the exact insertion under a stable decision ID and obtain explicit approval.

## Case C — An evidence-addition comment does not supply evidence

### Synthetic source comment

> Add evidence for long-term durability.

### Expected behavior

Do not invent a result, statistic, source, or claim. Record the missing evidence
and the required verification. Any proposed insertion needs verified source
material, exact wording, its own decision ID, and explicit user approval. The
comment does not authorize an adjacent rewrite.

## Case D — Ambiguous mixed citation styles require two questions

### Synthetic document state

The body contains both author–date citations and bracketed numbers. The
reference list resembles a CV entry list, but the user has not said that the CV
controls the document.

### Expected behavior

Ask separately which style controls in-text citations and which style controls
the reference list. Do not infer body style from the list or use a current CV as
reference-list authority without explicit user confirmation. Ask separately
about applicant-specific annotations when present. Implement no style migration
while either axis remains unresolved.

## Case E — A broad normalization label is not approval-ready

### Synthetic decision label

> GS-REF-ALL — Normalize references.

### Expected behavior

Reject the label as insufficient for implementation. Split it into exact,
bounded decisions with document/location, provenance, exact current form, exact
proposed form, benefit, risk, and assumptions. Approval of the broad label does
not authorize unlisted punctuation, typography, ordering, metadata, annotation,
or body-citation changes.
