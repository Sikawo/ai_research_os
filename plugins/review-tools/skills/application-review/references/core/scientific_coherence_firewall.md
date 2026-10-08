# Scientific Coherence Firewall

## Purpose

Make scientific coherence a hard admission constraint before interestingness,
reviewer preference, narrative fluency, or memorability can influence selection.

## Verdicts

- `ADMISSIBLE`
- `ADMISSIBLE WITH MATERIAL UNCERTAINTY`
- `INADMISSIBLE`

Evaluate every conventional and unconventional candidate against:

1. internal logical consistency;
2. compatibility with authorized observations;
3. completeness of causal bridges;
4. evidence status;
5. hidden assumptions;
6. domain plausibility;
7. falsifiability or discriminability where scientifically appropriate;
8. alternative explanations;
9. prediction consistency;
10. scope and feasibility where relevant;
11. dependence on invented evidence;
12. whether apparent novelty is merely narrative relabeling.

Normally return `INADMISSIBLE` when a candidate contradicts a core observation
without explaining it, requires absent evidence, inserts an unexplained causal
jump, fabricates literature or results, presents a non-discriminating account
as a mechanism, over-transfers an analogy, or relies on a domain-invalid
assumption without a defensible bridge.

Interestingness must never rescue an `INADMISSIBLE` candidate.

## Firewall Record

```text
Candidate ID
Verdict
Observation compatibility
Causal bridges
Evidence statuses
Hidden assumptions
Domain plausibility
Domain risk: `NONE / SPECIALIST_REVIEW_REQUIRED / CLEARED`
Discriminating prediction
Alternative explanations
Feasibility and scope
Invented-evidence check
Scientific-versus-narrative check
Failure reasons
Evidence or bridge needed for reconsideration
```

## Interestingness And Leverage

Only after admission, profile each survivor on anchored ordinal axes from `0`
to `4`:

- Surprise
- Explanatory Leverage
- Prediction Delta
- Generativity
- Conceptual Compression
- Scientific Importance
- Memorability

Do not require or optimize one summed score. Use Pareto-style comparison and
qualitative scientific judgment. Surprise or memorability alone cannot create a
Target; at least one of explanatory leverage, prediction delta, generativity,
or scientific importance must be meaningfully strong.

Keep correctness, interestingness, importance, conceptual novelty, literature
novelty, and narrative novelty as distinct judgments. Literature status must be
one of `NOT CHECKED`, `CHECKED — NO NOVELTY CLAIM MADE`, or `VERIFIED WITH
EXPLICIT EVIDENCE`; the default is `NOT CHECKED`.

## Four-Quadrant Classification

| Coherence | Scientific interest | Scientific class |
| --- | --- | --- |
| coherent | low | `SAFE BASELINE` |
| coherent | high | `TARGET` |
| incoherent or incomplete | high | `SPECULATIVE SEED` |
| incoherent or incomplete | low | `REJECT` |

This scientific class never replaces change risk. `Scientific class: TARGET`
and `Change risk: RED` is valid and requires human approval.

## Speculative Seed Rule

An inadmissible but plausible high-value idea may be retained as a seed rather
than inserted or silently discarded. Record its failure, missing causal bridge,
missing and weakening evidence, rescue evidence, discriminating test, related
anomalies, human position, reopen condition, and status. Allowed statuses are
`DORMANT`, `WATCH`, `REOPENED`, `REJECTED`, and `PROMOTED`.

Promotion always requires genuinely new trigger evidence and a fresh firewall
evaluation. Age, familiarity, repetition, or memorability is never sufficient.
