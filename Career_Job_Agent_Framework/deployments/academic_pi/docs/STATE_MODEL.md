# Academic PI State Model

Scheduled discovery, manual evaluation, reporting, and handoff use one canonical
durable state. A deployment may use a sheet, Drive-backed store, database,
JSONL, or another configured adapter, but it must not create a separate store
for manual evaluations.

The standalone CLI requires `--state <private-json-path>` for `daily`,
`weekly`, source and institution scans, `verify`, `evaluate`, `reject`, and
`restore`, plus the state-reading `show`, `active`, `deadlines`, `coverage`, and
`handoff` operations. It never silently substitutes ephemeral state for those operations.
Keep that path in a private runtime directory outside the public checkout.
Direct library embeddings may inject another durable `StateStore`; `dry-run`
uses an isolated in-memory copy and does not persist changes or create a missing
state file.

## Logical tables

### Jobs

One row or record per canonical posting. Store normalized fields, official and
discovery URLs, provenance, verification, independence, search scope,
requirements, position details, separate evaluation layers, and application
state.

### Runs

One record per execution, including run ID and times, run type, attempted,
successful, and failed sources, email counts, discovered and canonical counts,
material updates, verification failures, active tier counts, and error summary.

### Changes

One structured record per material change with time, field, old value, new
value, source, and confidence. Punctuation, formatting, boilerplate order, and
tracking-only URL changes are not material.

### SourceCoverage

Track source ID, last attempt, last success, status, items seen, error, and next
due time.

### InstitutionCoverage

Track institution, last attempt, last success, official pages and domain queries
checked, status, and notes. A complete zero-result scan is successful.

### Applications

Application workflow is separate from discovery lifecycle. Document generation
does not imply submission.

## Canonical identity

Upsert rather than append. Resolve identity in this order:

1. normalized official institution plus official requisition/job ID;
2. canonical official URL;
3. institution plus normalized title, department, location, and deadline;
4. a conservative semantic fallback above a configured confidence threshold.

Title alone is never sufficient. Preserve all original discovery URLs after URL
normalization. Use requisition, deadline, department, description similarity,
and official status to distinguish an extension, reopening, annual search, and
new requisition.

## Verification states

Canonical records support:

- `verified_open`
- `verified_closed`
- `verified_expired`
- `verified_reopened`
- `verification_pending`
- `verification_failed_transient`
- `verification_failed_persistent`
- `official_source_not_found`
- `manual_review_required`

Transient failure preserves prior durable state. It may exclude a role from the
current-run active snapshot, but it never turns the role into closed. Definitive
official evidence is required for closure, expiration, or reopening.

## State safety

- Validate or read back important writes when the adapter supports it.
- Preserve prior verified values when current retrieval is incomplete.
- Keep provenance for important fields and raw discovery evidence where useful.
- Persist manual review decisions and human overrides.
- Manual evaluation upserts canonical state without incrementing scheduled
  discovery counts or generating duplicate alerts.
- A rejected role remains durable and does not re-alert without a material
  change or verified reopening.
- Report delivery and state mutation are separate outcomes.
- Never infer `submitted` from a package path or generated documents.

## Current active snapshot

Build one snapshot per run from normalized canonical state and reuse it in every
enabled channel. Include only Tier 1 or Tier 2 roles that were officially
verified active under the current-run verification policy and are not rejected,
blocked, closed, or expired.

A transient failure is surfaced in verification/coverage reporting and omitted
from that run's active snapshot while prior state remains intact. Snapshot
membership does not change new-job counts, material-change counts, or alert
routing.

## Application boundary

The Job Agent discovers, verifies, ranks, tracks, alerts, and creates a
structured handoff. Academic GatedSprint may draft or revise requested
materials. Only the human approves and submits an application.
