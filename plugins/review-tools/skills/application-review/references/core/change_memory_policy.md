# Change Memory Policy

## Purpose

Prevent repeated generic advice and preserve high-tradeoff decisions across
Sprint runs without creating a duplicate repository status system.

## Files To Check Before Advice

When available, read:

- `repeated_advice_memory.md`;
- `do_not_change_registry.md`;
- `revision_decision_log.md`;
- `change_ledger.md`.

For an eligible scientific run, also read only the authorized relevant portion
of Serendipity Memory under `serendipity_memory_policy.md`.

Do not expose these records to the source-only cold reader before its first
reconstruction. The orchestrator may inspect them after the cold pass to
reconcile current findings with prior decisions. Conversation persistence,
earlier assistant prose, repeated scores, and an old filename are not evidence
that an earlier recommendation remains correct.

## Current-Source Packet and Fingerprint Reset

At the start of a full run, register the explicitly designated current source
and fingerprint. Build the review packet from the current draft, applicable
official requirements, authorized evidence, active user locks, and only those
approved decisions whose source bindings remain valid. Older drafts, retired
recommendations, rejected alternatives, prior scores, and assistant-generated
prose remain history and do not enter the source-only reviewer context.

Reset this packet and revalidate affected records when the user designates a
new current draft, architecture or central story changes materially, the user
reports recommendation drift, implementation ends and release begins, or a
long thread contains enough superseded material to anchor the evaluator. When
true isolation is unavailable, disclose `CONTEXT_EXPOSED` rather than calling
the pass blind.

## Repeated Advice Rule

If advice has already been given:

- do not repeat it generically;
- either add a concrete implementation detail;
- or mark it as already known and move on to its next concrete action.

For eligible scientific reviews, apply
`plugins/review-tools/skills/application-review/references/core/scientific_argument_gate.md`: suppress repetitive
wording, never the unresolved finding or its effect on readiness and affected
scores. Keep stable finding IDs in the existing revision decision log/change
ledger; do not add a new durable memory store. Carry forward origin, criteria,
severity, resolution condition, last reviewed version, and verification evidence.

Use `OPEN`, `REPAIR_PROPOSED`, `EDITED_PENDING_REVIEW`, `RESOLVED_VERIFIED`,
`DEFERRED`, and `ACCEPTED_RISK`. Only a re-review of the actual revised passage
against the recorded condition establishes verified resolution. A new filename,
polished wording, earlier advice, or author agreement is not evidence of repair.
Deferred and accepted risks stay visible and still constrain verdicts. If the
original finding was mistaken, record an evidence-backed withdrawal or
reclassification event with the original history and any replacement ID;
do not pretend that text was repaired or silently lower severity/remap criteria.

Keep this finding lifecycle distinct from GatedSprint's implementation decision
lifecycle (`PROPOSED` through `VERIFIED`, with held/rejected/superseded states).
An approved or implemented decision does not itself resolve the finding; only
review evidence from the actual revised source can move it to
`RESOLVED_VERIFIED`. Conversely, a finding may remain open while one proposed
repair is rejected or superseded.

Every substantive decision uses a stable ID plus proposal revision and retains
its original source binding. On a new source, carry it forward only when scoped
text/anchor, proposal fingerprint, protected intent, and dependency set remain
materially unchanged; append a source-revalidation event. Mark changed records
`REVALIDATION_REQUIRED` and issue a new proposal revision when appropriate.
Mark no-longer-relevant records `OBSOLETE`. Do not revive a stale revision with
a later unchanged comparison.

Use the shared report template for explicit previous/current report comparison.
Do not discover private prior reports automatically. The source-only reviewer
receives history only after its first reconstruction; the orchestrator remains
responsible for reconciling all prior unresolved IDs.

## Do-Not-Change Registry

Use the registry for decisions that should not be reopened without new
evidence. Examples:

- a project remains a decision-gated extension unless the user asks to reopen
  it;
- publication status must not change without explicit confirmation;
- the applicant's scientific identity and independent trajectory must be
  preserved.

Record Human Position as `LOCKED`, `PREFERRED`, `OPEN`, `DISLIKED`, or
`REJECTED_UNLESS_NEW_EVIDENCE` when needed. Do not reopen locked or rejected
decisions without the required human action or genuinely new evidence meeting a
recorded trigger.

## Serendipity Memory Boundary

Use existing files above for ordinary advice, revision decisions, and
do-not-change state. Use Serendipity Memory only for durable anomalies,
Speculative Seeds, valuable structural analogies, and reopen triggers. Do not
duplicate project status, revision logs, work queues, or transient rankings.

## Log Discipline

Keep logs concise and free of private scientific details unless those details
are explicitly authorized for the Sprint. Do not use these files as daily work
logs, status dashboards, or replacements for repository coordination files.

Preserve held, rejected, deferred, accepted-risk, superseded, obsolete, and
withdrawn history append-only. This prevents the same unhelpful suggestion from
returning in a long conversation while allowing a recorded reopen trigger or
genuinely new evidence to justify a new revision.
