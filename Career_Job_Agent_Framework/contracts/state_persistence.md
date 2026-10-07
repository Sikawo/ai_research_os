# Canonical State Persistence Contract

## Purpose

Scheduled discovery, manual ChatGPT evaluation, and `CURRENT ACTIVE TIER 1/2` must use one canonical Career Job Agent state. A deployment may keep that state in Drive, a sheet, JSONL, or another configured backend, but it must not create a separate manual-evaluation store.

The framework owns deterministic eligibility and upsert behavior. The private deployment's existing state adapter owns loading the canonical rows and committing the mutated row collection to the authoritative backend.

## Manual-evaluation eligibility

A manually evaluated role must be persisted when all of these conditions hold:

- the role is verified currently active on the official employer career page during the manual evaluation;
- its final classification is actionable Tier 1 or Tier 2;
- it remains within the deployment's configured employer and source scope;
- it is not rejected, hard-blocked, closed, or expired; and
- manual persistence is enabled in private configuration.

LinkedIn and other aggregators are discovery aids only. An aggregator page, stale official verification, failed source check, or ambiguous official result cannot establish currently active status. A definitively closed or expired official posting is not persisted as an active actionable role under this rule.

## Upsert identity and precedence

Upsert; never blindly append. Try the following identities in order and stop at the first match:

1. normalized company + official job ID;
2. canonical official URL; and
3. normalized company + title + location.

A title-only match is never sufficient. Canonical URL comparison should remove tracking/query fragments and normalize host, scheme, and trailing slash consistently with the deployment's scheduled-run deduplication.

## Existing and new roles

For an existing role, update the matched canonical row with the latest verified values that are present in the manual evaluation, including identity fields, fit score, tier, strengths, gaps, salary evidence, official URL, verification fields, and workflow status as appropriate. Preserve unrelated canonical and historical fields, and do not add a duplicate row.

For a new role, insert one row using the deployment's existing canonical state schema. Do not require a broad state-schema migration merely to identify a row as manually evaluated. Missing values must not erase useful existing values during an update.

## Side-effect boundary

Manual persistence is state maintenance, not scheduled discovery. An insert or update through this path must not:

- increment the scheduled run's new-job, changed-job, or new-tier counts;
- rewrite historical daily discovery counts;
- create a duplicate daily alert solely because the role was manually persisted;
- generate or route an approval packet merely because persistence occurred; or
- generate or submit an application.

Application generation and submission remain governed by their existing approval gates. `CURRENT ACTIVE TIER 1/2` may consume a manually persisted row because it reads the same canonical state, but its normal current-run official reverification remains mandatory.

## Configuration

Private deployments should provide:

```yaml
state_persistence:
  manual_evaluations:
    enabled: true
    upsert_actionable_tier_1_2: true
    require_current_official_verification: true
```

Disabling either `enabled` or `upsert_actionable_tier_1_2` skips the manual write. When `require_current_official_verification` is enabled, prior verification alone is insufficient.

## Processing sequence

1. Complete the manual fit evaluation without changing the configured thresholds, weights, allowlist, visa rules, or QOL assumptions.
2. Obtain a current official-employer-page verification result.
3. Apply the actionable Tier 1 / Tier 2 and blocker gates.
4. Load the canonical rows through the deployment's existing state adapter.
5. Resolve identity using the required precedence.
6. Update one matched row or insert one new row.
7. Commit through the same canonical state adapter.
8. Return an explicit inserted, updated, or skipped result while leaving scheduled-run accounting, notifications, and application actions unchanged.

If the authoritative write fails, report the failure and do not claim persistence succeeded. Retrying must remain idempotent under the same identity rules.
