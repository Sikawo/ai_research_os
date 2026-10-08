# Daily Run Contract

## Daily sequence

1. Load the private user profile, search preferences, company allowlist, life preferences, fit rubric, storage destinations, and canonical prior state.
2. Discover new jobs from configured employers.
3. Verify every retained role on the official employer career page.
4. Normalize and deduplicate by normalized company + official job ID, canonical official URL, then normalized company + title + location as fallback.
5. Score against verified candidate evidence.
6. Apply hard blockers before routing.
7. For Tier 2 or better, run the quality-of-life assessment contract.
8. For Tier 1, create a target requirement register, initial resume and cover-letter drafts, and GatedSprint Phase 1 packet.
9. Ask no more than the configured maximum number of unresolved questions.
10. After today's alert processing, select every canonical role that is otherwise actionable and currently classified Tier 1 or Tier 2, including unchanged prior-day roles.
11. Reverify each selected role on its official employer page during the current run. Build one canonical `current_active_tier_1_2` snapshot containing only roles verified active during this run.
12. Render that same snapshot at the end of the Drive daily report and the ChatGPT, Gmail, and Slack digests.
13. After explicit document-generation approval, produce final files and return the official application URL and output location.
14. Never submit an application automatically.

## Two-layer report contract

Every enabled daily user-facing output contains two independent layers in this order:

1. **Today's changes / alerts**: new discoveries, material changes, action-required items, headline, counts, and packet links.
2. **`CURRENT ACTIVE TIER 1/2`**: the current portfolio snapshot, including eligible roles unchanged from earlier runs.

The second layer must be present even when there are no new jobs, no material changes, or a `[NO MATCH]` headline. If no role qualifies, render:

```text
CURRENT ACTIVE TIER 1/2
None.
```

If `reporting.current_active_tier_1_2.enabled` is `false`, omit the snapshot and preserve the deployment's prior report behavior.

Snapshot membership does not change the headline, new-job count, material-change count, Tier 1 / Tier 2 new-today counts, alert classification, deduplication state, or approval-packet generation. Unchanged snapshot roles are not fresh discoveries.

### Snapshot eligibility and verification

A role is eligible only when all conditions hold:

- the official employer page is verified active during the current run;
- the current fit classification is Tier 1 or Tier 2;
- the role is not rejected or hard-blocked;
- the role is not closed or expired;
- the role is not awaiting first-time official verification; and
- the role remains within configured employer and source scope.

The official employer page remains the source of truth; aggregators remain discovery-only. A failed, unavailable, or ambiguous official-page check must not be treated as active or silently converted to closed. Omit that role from the current-run snapshot, surface it through incomplete checks/source failures, and preserve prior state unless a definitive official result supports a state transition.

### Canonical payload, sorting, and fields

Build the snapshot once per run from normalized, deduplicated canonical state. Drive, ChatGPT, Gmail, and Slack renderers must consume that same object or list rather than recomputing channel-specific sets.

Sort Tier 1 before Tier 2, then fit score descending, company, and title. Each compact role entry includes tier, fit score, company, title, official job ID, location, verified salary/range when available, workflow/application status, one-line strongest match, one-line key gap, and official job/application URL.

## Report contents

The daily report should include:

- number of employers checked;
- number of active official jobs reviewed;
- number of new jobs after deduplication;
- Tier 1, Tier 2, Watchlist, suppressed, and blocked counts;
- strengths, gaps, fit score, salary, and official URL for each reported job;
- economic and educational QOL summaries for Tier 2 or better;
- incomplete employer checks and source failures;
- links to question packets and generated files when applicable.
- a final `CURRENT ACTIVE TIER 1/2` section from the shared current-run snapshot, even when empty.

## User feedback loop

Record Apply, Maybe, Skip, interview, rejection, location rejection, salary rejection, visa blocker, seniority mismatch, and domain mismatch. User feedback may inform a proposed rubric change, but the framework must not silently edit user preferences or thresholds.

## Error handling

Continue past one employer or data-source failure. Mark missing information explicitly. Do not invent active status, salary, commute time, rent, school quality, tuition, childcare cost, or candidate experience. A transient reverification failure excludes a role only from that run's current-active snapshot; it does not by itself erase prior durable status.

### External-delivery observability

Treat every external write as a separate logical action. The host records the
run ID and timestamp, logical action, destination type, redacted account
selector when available, whether account selection was unique, whether the
action was attempted, whether the connector was reached (`yes`, `no`, or
`unknown`), outcome (`success`, `failure`, or `uncertain`), sanitized failure
class and error code, retryability, result reference, readback status, and an
idempotency key when supported. Never persist credentials, connector link IDs,
full email bodies, or other sensitive payloads in delivery diagnostics.

Report an output as delivered only after the connector returns confirmed
success. A blocked or missing result is not success. If dispatch may have
occurred, or connector reachability is unknown, record the outcome as
`uncertain` and reconcile through a safe readback or status lookup before any
retry. Blind retry is allowed only for a confirmed pre-dispatch failure marked
retryable; otherwise require reconciliation or explicit human review.

Complete and verify canonical state and report-body persistence before
notification actions. Execute configured notification adapters one at a time
and record each result independently so one delivery failure does not hide or
rewrite another result. Delivery failures must not corrupt canonical state or
be reported as successful merely because another channel succeeded.
