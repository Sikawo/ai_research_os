# Academic PI Runtime Contract

Run the existing Academic PI scheduled task once each morning at the host-
configured local time. The production target is daily at 5:00 AM
`America/New_York`.

## Required ownership

- Reusable guidance: clean public `ai_research_os` Academic PI deployment.
- Private deployment configuration: the explicitly selected
  `personal_config/career_agents/academic_pi/` subtree.
- Canonical state and run history: the existing dedicated Academic Sheet.
- Writer identity: the existing Academic scheduled task only.

Do not create a replacement task, writer, Sheet, or state location during
activation. Do not use Industry state, configuration, outputs, or schedule.

## Preflight and provenance

Before every run, resolve the requested framework and private configuration by
reading their required files. The saved prompt is not proof of resolution.
Emit the value-free `CONFIGURATION PROVENANCE` block required by
`contracts/daily_run.md`. If resolution cannot be proved or fallback was used,
stop before discovery or writes.

Verify that both RSS inputs, canonical State, Reports history, Gmail input
account selection, official-web verification capability, ChatGPT-visible
reporting, and Gmail digest destination are unambiguous. Do not emit account
addresses, connector IDs, Sheet IDs, or private configuration values.

## Operational sequence

1. Read the two configured AcademicJobsOnline RSS inputs.
2. Read only the configured academic-alert Gmail scope in shadow mode.
3. Classify messages without deleting, archiving, or changing labels.
4. Canonicalize RSS and Gmail candidates together and deduplicate them before
   scoring or alerting.
5. Verify official sources and extract Academic-specific fields.
6. Evaluate fit, Tier, compensation, and QOL from authorized configuration.
7. Additively upsert State and append one Reports row.
8. Build and read back the complete ChatGPT-visible report.
9. Attempt the Gmail digest separately. Treat the delivery result as
   non-blocking and do not claim success without connector confirmation.

## Activation gate

1. Preserve a rollback copy of the prior task prompt/config reference and the
   daily 5:00 AM `America/New_York` schedule.
2. Run one explicitly approved manual validation on the existing task.
3. If all blocking fields pass, schedule exactly three bounded validation runs
   on the same task.
4. Blocking fields are framework/config resolution with no fallback, State
   continuity, Reports continuity, RSS and Gmail discovery, cross-source
   deduplication, official verification handling, complete ChatGPT-visible
   report/readback, zero-result versus failure handling, duplicate prevention,
   and schedule integrity.
5. Gmail label mutation remains disabled throughout this gate. Gmail digest
   delivery is recorded separately and is non-blocking.
6. After 3/3 PASS, retain production guidance/config and restore daily 5:00 AM
   `America/New_York`. Verify that no fourth accelerated run is configured.

If any blocking field is `FAIL` or `UNKNOWN`, restore only the recorded prior
prompt/config reference and normal daily schedule on the same task. Preserve
the existing task identity and all prior outputs. Preserve the existing Sheet, State, Reports, bindings,
and canonical-state location without replacement.

## Prohibited actions

- no new task, writer, Sheet, State, or output destination;
- no Industry changes;
- no Gmail delete, archive, or label mutation during shadow mode;
- no unconfirmed retry of a possibly dispatched external write;
- no retry of an uncertain write without reconciliation;
- no application drafting or submission;
- no cleanup, archive, or destructive schema migration.
