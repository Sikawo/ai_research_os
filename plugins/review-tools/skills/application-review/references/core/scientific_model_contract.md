# Scientific Model Contract

## Purpose

Build a compact, evidence-disciplined representation of the authorized science
before conceptual divergence. The model is a run artifact, not an exhaustive
field ontology and not normally durable memory.

## Epistemic Types

Every material statement must retain one of these types:

- `Observation`: a result directly present in the authorized source.
- `Established knowledge`: prior knowledge supported in the authorized source.
- `Interpretation`: a meaning assigned to an observation.
- `Inference`: a relationship reasoned from observations but not directly shown.
- `Hypothesis`: a testable proposed explanation.
- `Assumption`: a premise required by the current model.
- `Speculation`: an idea with material unsupported bridges.
- `Unknown`: an unresolved quantity, relation, or state.
- `Prediction`: an expected observation conditional on a model.
- `Mechanistic relation`: a causal or functional link with its evidence status.
- `Anomaly`: an authorized observation that the current model does not explain.

Never silently convert inference into observation, speculation into established
knowledge, or hypothesis into result. Attach one evidence status to each
material claim: `SOURCE-SUPPORTED`, `INFERRED`, `HYPOTHETICAL`, `SPECULATIVE`, or
`EXTERNAL VERIFICATION NEEDED`.

## Required Compact Model

When present in authorized material, record:

1. central scientific question;
2. current organizing model;
3. major observations and evidence-supported relationships;
4. inferred relationships and explicit hypotheses;
5. hidden or explicit assumptions;
6. unresolved unknowns;
7. anomalies;
8. major predictions;
9. source-evident alternative explanations;
10. current narrative spine.

Keep exact source boundaries and uncertainty visible. Missing content remains
missing; do not complete a causal chain by invention.

## Anomaly Register

For every materially relevant mismatch, create an entry with:

```text
Anomaly ID
Observed result
Current model expectation
Nature of mismatch
Possible mundane explanation
Possible model-changing interpretation
Evidence status
Distinguishing test or observation
Current disposition
Revisit trigger
```

The model-building pass must explicitly answer: **What observation is hardest
for the current model to explain?**

Do not automatically relabel inconvenient evidence as noise, technical
variability, a secondary finding, or future work. A mundane explanation should
prevail when supported, but both the explanation and its evidentiary basis must
remain explicit.

## Scientific And Narrative Spaces

Label changes independently:

- `SCIENTIFIC SPACE`: new model, mechanism, relationship, interpretation,
  prediction, or organizing principle.
- `NARRATIVE SPACE`: section ordering, story structure, emphasis, reader memory,
  reviewer clarity, or presentation.
- `BOTH`: a scientific difference with a consequential narrative expression.

A reordered document is not a new scientific model. Literature novelty is also
independent. Unless an authorized verification workflow actually ran, record:

```text
Literature novelty: NOT VERIFIED
```

The controlling distinctions are: `Interesting != Novel`, `Novel != Important`,
and `Important != Correct`.

## Persistence Boundary

Scientific Model snapshots normally remain reproducible run artifacts. Persist
only durable anomalies, seeds, analogies, and reopen triggers through
`serendipity_memory_policy.md`; do not create a second source of truth.
