# Auto-Edit Policy

## Purpose

Decide which Sprint changes may be applied automatically and which require
human decision.

## Green Changes

Auto-apply green changes.

Examples:

- grammar;
- clarity;
- project numbering;
- figure references;
- formatting consistency;
- repeated phrases;
- awkward English;
- already-decided framing;
- low-risk wording changes;
- cross-document consistency fixes;
- paragraph transitions that do not change meaning.

## Yellow Changes

Auto-apply yellow changes only when the five-step comparison indicates a clear
net benefit and the core scientific intent is preserved. Otherwise list them as
human-decision proposals.

Examples:

- changing project emphasis;
- paragraph reordering;
- abstract narrative spine revision;
- moving material to decision-gated extension;
- target-fit reframing;
- publication-status reframing when status is already confirmed by the user;
- strengthening or softening claims;
- reorganizing sections while preserving content.

## Red Changes

Never auto-apply Red changes. Red is reserved for factually admissible,
evidence-supported high-impact choices. List those as human-decision proposals
with recommendation, benefit, risk, sacrifice, and approval requirement.

Examples:

- deleting a major project;
- merging aims;
- splitting aims;
- changing the central hypothesis;
- adding new experiments;
- changing publication status when the new status is explicitly evidenced;
- major budget or staffing changes;
- changing target institution or application fit;
- removing a major scientific theme entirely;
- integrating a consequential claim supported by authorized source material.

Serendipity-derived central-hypothesis changes, new mechanisms, new experiments,
major reinterpretations, and aim merge/split proposals are Red even when
scientifically classified as a `TARGET`. Record domain risk separately as
`SPECIALIST_REVIEW_REQUIRED` when appropriate.

## Scientific Serendipity Boundary

Exploration authority is broader than execution authority. Sprint may
automatically apply a serendipity-derived improvement only when it is
meaning-preserving and already qualifies as Green, or as an existing-policy
safe Yellow with clear benefit and no scientific tradeoff. Never auto-apply:

- an `INADMISSIBLE`, `SPECULATIVE SEED`, or `REJECT` candidate;
- a claim requiring absent evidence or external novelty verification;
- a change conflicting with a `LOCKED` or unreopened
  `REJECTED_UNLESS_NEW_EVIDENCE` position;
- a major conceptual change blocked by `CONVERGE` or `LOCK` maturity;
- a change with unresolved `domain_risk=SPECIALIST_REVIEW_REQUIRED`.

GatedSprint applies no substantive source change, including Green changes,
before Phase 4 approval.

## Blocked Changes

Do not auto-apply or offer approval as a way to implement a change that depends
on missing evidence, invented facts, unsupported causality or novelty,
unverified publication/status/ownership information, or material outside the
authorized source packet. Record `support_status=BLOCKED`, identify the missing
evidence or verification, and leave the artifact unchanged. This rule applies
equally to GatedSprint and self-driving Sprint; Red classification cannot
launder a blocked change into a human-approvable option.

## Uncertainty Rule

If uncertain, preserve the original scientific intent and document the
uncertainty.
