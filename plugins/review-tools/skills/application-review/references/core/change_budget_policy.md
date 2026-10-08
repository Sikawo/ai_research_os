# Change Budget Policy

## Purpose

Separate the magnitude of a scientific insight from the safe magnitude of the
current edit, using document maturity without suppressing exploration.

## Maturity Stages

- `EXPLORE`: major conceptual alternatives may be proposed, including central
  hypotheses, aim structures, project relationships, and narrative spines.
- `BUILD`: substantive alternatives remain available, with greater attention to
  implementation cost, evidence, and feasibility.
- `CONVERGE`: prefer clarification, linkage, selective emphasis, and local
  structural improvements. Major hypothesis or aim changes require unusually
  high expected value and an explicit human decision.
- `LOCK`: avoid destabilization except for serious correctness or
  submission-critical problems. Major new ideas normally become seeds,
  future-direction proposals, no-action insights, or minimal safe framing.

## Resolution

Resolve maturity after human constraints and before choosing an edit. An
adapter may set it explicitly or request `infer`. Infer conservatively from
authorized workflow signals such as stage, deadline, approved decisions, and
the requested task.

If inference is uncertain, do not suppress conceptual exploration and do not
auto-apply a major change. Surface the idea as a decision-gated proposal. Ask a
maturity question only when the answer materially changes the immediate action.

## Required Decision Fields

Record independently:

```text
Scientific insight magnitude: NONE / SMALL / MODERATE / MAJOR
Recommended current edit magnitude: NONE / LOCAL / MODERATE / MAJOR
Document maturity: EXPLORE / BUILD / CONVERGE / LOCK
Maturity source: explicit / inferred / uncertain
Reason
Required human decision
```

A major insight may validly have a small or zero current edit. Maturity affects
implementation, not truth or coherence classification.

## Safety Coupling

The Change Budget does not override evidence rules, the coherence firewall,
Green/Yellow/Red change-risk classification, the separate domain-risk status,
or GatedSprint phase boundaries. Feasibility remains an independent scientific
and reviewer constraint; novelty does not compensate for a proposal that
destroys feasibility.
