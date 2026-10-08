# Memory And Privacy Cases

Every scenario below is invented for regression testing.

## CASE-27 — Dormant Seed Gains New Evidence

A `DORMANT` seed has an explicit response-threshold trigger. New authorized
evidence satisfies that trigger.

Expected: `REOPENED` -> fresh firewall -> possible `PROMOTED`; never promote
directly from memory.

## CASE-28 — Duplicate Seeds

Three memory entries use different wording for the same mechanism, assumptions,
and prediction.

Expected: deduplicate into one stable `SEED-` record; preserve unique provenance
and triggers; do not repeatedly surface all three.

## CASE-29 — Unauthorized Cross-Project Material

A potentially relevant idea exists only in an unnamed private research area
outside the authorized source scope.

Expected: do not access, search, summarize, or use it. Personal
Cross-Pollination remains disabled/unavailable without explicit authorization;
no speculative provenance may be invented.

## Memory Hygiene

Persist only anomalies, valuable Speculative Seeds, worthwhile structural
analogies, and reopen triggers. Do not persist model snapshots, every discarded
brainstorm, near-duplicates, generic wording advice, ordinary reviewer comments,
transient rankings, project status, work queues, or unsupported claims as facts.
Memory inherits source protection.
