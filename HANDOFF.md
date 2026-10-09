# HANDOFF — Phase 11 Academic PI Production Contract

## Status

- Repository: `Sikawo/ai_research_os`
- Branch: `codex/phase-11-academic-production-contract`
- Base: latest `origin/main`
- Lifecycle: offline implementation complete; Draft PR publication pending
- Merge and live activation: human-controlled

## Public deployment requirements

- A live deployment must reuse its authorized task, canonical state, and run
  history instead of creating a parallel writer.
- A pilot that only performs RSS discovery must not be treated as the full
  Gmail-plus-RSS production workflow.
- Production state/report shape must add the full fit/Tier/salary/QOL and
  Academic-specific fields without replacing canonical state.
- Gmail input must remain read-only shadow ingestion until a separately
  approved label-activation gate passes.
- This public branch stores no live task, runtime, state, connector, account,
  resource, or external-output facts.

## Implemented public contract

- Added Academic-specific daily and runtime contracts with value-free
  configuration provenance and fail-closed no-fallback behavior.
- Combined configured Gmail and both AcademicJobsOnline RSS inputs into one
  canonical deduplication pipeline.
- Required official verification, evidence-based fit/Tier, salary/QOL,
  CURRENT ACTIVE Tier 1/2, and Academic-specific independence, tenure/faculty
  track, startup/lab-space, teaching, deadline, official URL, and verification
  confidence.
- Made the ChatGPT-visible report mandatory and Gmail digest delivery a
  separately recorded non-blocking action.
- Enforced Gmail shadow mode at the service boundary: no delete, archive, or
  label mutation until a later separate approval after RSS/email duplicate
  convergence is demonstrated.
- Made value-free configuration provenance mandatory in the renderer and
  deduplicated the current-active snapshot by canonical role identity.
- Defined additive state/schema handling, one-writer continuity, manual
  validation, exactly three scheduled continuity runs, normal 5:00 AM
  `America/New_York` restoration, and rollback.
- Added a deny-by-default Phase 11 manifest and safety tests for its exact
  19-path public boundary.

## Separate private configuration branch

`Sikawo/personal_config` branch
`codex/phase-11-academic-production-config` contains the private companion
change. It remains a separate PR and stores no account addresses, external
resource IDs, connector link IDs, credentials, state, reports, or message
content.

The private overlay is production-shadow ready, not live. It maps only the
minimum approved candidate fields from the existing verified profile in the
same private repository, enables QOL categories, selects AcademicJobsOnline
and academic-alert discovery, and enforces Gmail shadow guards.

## Validation

- Focused Academic deployment suite: 185 passed.
- Phase 11 manifest and repository safety tests: 34 passed, 2 subtests passed.
- Public repository safety validation: PASS.
- Public safety check and privacy scan: PASS.
- Full public pytest: 744 passed, 2 skipped, 282 subtests passed.
- Private repository safety validation: PASS.
- Private unittest suite: 19 passed.
- Cross-repository Academic overlay framework/schema/connector validation with
  synthetic host factories: PASS.
- `git diff --check`: PASS in both repositories.

## Rollback

Offline rollback is a normal revert of each repository's single Phase 11
feature-branch commit. No runtime or external state has changed.

For the later live cutover, preserve the prior authorized prompt/config
reference and normal schedule before editing. If manual validation or
any of the three scheduled continuity runs has a blocking `FAIL`/`UNKNOWN`,
restore only that prompt/config reference and normal schedule on the existing
task. Preserve the Sheet, State, Reports, bindings, and prior outputs.

Gmail label mutation is not part of this cutover and must remain disabled.

## Next steps after both human merges

1. Present and approve a new Desktop Operation Preflight for the live task and
   additive Sheet schema migration.
2. Update the existing task only; do not create a new task or writer.
3. Perform one manual validation with Gmail shadow ingestion and both RSS tabs.
4. If blocking gates pass, observe exactly three scheduled runs.
5. Restore daily 5:00 AM `America/New_York`; verify no fourth accelerated run.
6. Keep Gmail labels disabled. Consider label activation only after a separate
   review proves cross-source duplicate convergence.

## Human-controlled guardrails

- Do not merge or mark ready for review automatically.
- Do not change the live task, prompt, schedule, Sheet, State, connector,
  Gmail labels, or external delivery in this Git step.
- Do not touch Industry, create a task/state/writer, submit an application,
  perform cleanup, or archive anything.
