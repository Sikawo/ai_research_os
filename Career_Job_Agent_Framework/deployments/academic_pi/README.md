# Academic PI Deployment

The Academic PI deployment extends the shared Career Job Agent Framework for
independent academic opportunities across configured global regions. It uses the
same official-verification, canonical-state, deduplication, reporting, and
approval boundaries as the Industry deployment while adding academic title
normalization, broad-search handling, target-institution coverage, and an
Academic GatedSprint handoff.

## Design

Three independent discovery lanes converge on one canonical pipeline:

```text
email alerts ───────────────┐
web and aggregators ────────┼─> verify -> normalize -> dedupe -> evaluate
target institutions ───────┘              -> durable state -> reports
```

Discovery may be broad and redundant. Canonical state must be verified,
deduplicated, durable, and explainable. Official institution sources take
precedence over aggregators and alert messages.

## Public core and private overlay

This directory is safe to share because it contains only generic configuration,
schemas, prompts, synthetic templates, documentation, and deployment code. A
real user's identity, evidence, preferences, institution rankings, credentials,
state, reports, and application materials belong in a private directory or
private repository.

Private configuration is resolved in this order:

1. `ACADEMIC_PI_PRIVATE_CONFIG_DIR`;
2. the existing private Career Job Agent configuration location;
3. ignored `profiles/local/` configuration; and
4. synthetic examples for tests and demonstrations only.

`--allow-example` deliberately forces item 4 and ignores every private overlay.
It is limited to `validate-config` and `dry-run`; validation output reports only
the selected overlay kind, never overlay contents.

See [SHARING_AND_PRIVACY.md](docs/SHARING_AND_PRIVACY.md) before adding a real
profile.

## Included contracts

- `config/` contains generic defaults, source metadata, title/country rules,
  material-change fields, connector bindings, and report contracts.
- `schemas/` defines the candidate profile, preferences, source, canonical job,
  and Academic GatedSprint handoff payloads.
- `prompts/` defines safe daily, weekly, verification, evaluation, and handoff
  behavior for compatible orchestration runtimes.
- `templates/` contains synthetic starting points for private configuration.
- `docs/` explains setup, alert ingestion, sources, scoring, state, and sharing.

All public configuration is versioned. Private overrides may change scientific
terms, geography, target institutions, source cadence, and scoring weights
without editing deployment code.

## Operations

A host runtime may expose these operations as a console command, scheduled
workflow, or application action. The repository-local invocation is:

```bash
python3 -m Career_Job_Agent_Framework.deployments.academic_pi <command>
```

`academic-pi` is the recommended host-adapter alias. Supported command names
are:

```text
academic-pi --state <private-json-path> daily
academic-pi --state <private-json-path> weekly
academic-pi --state <private-json-path> scan-source <source>
academic-pi --state <private-json-path> scan-rss <source>
academic-pi --state <private-json-path> scan-email
academic-pi --state <private-json-path> scan-institution <institution>
academic-pi --state <private-json-path> verify <job-id-or-url>
academic-pi --state <private-json-path> evaluate <job-id-or-url>
academic-pi --state <private-json-path> refresh-qol <job-id-or-url>
academic-pi --state <private-json-path> show <canonical-job-id>
academic-pi --state <private-json-path> active
academic-pi --state <private-json-path> deadlines
academic-pi --state <private-json-path> coverage
academic-pi --state <private-json-path> source-health
academic-pi --state <private-json-path> target-health
academic-pi --state <private-json-path> reject <canonical-job-id>
academic-pi --state <private-json-path> restore <canonical-job-id>
academic-pi --state <private-json-path> handoff <canonical-job-id> \
  --evidence-ref <authorized-private-ledger-reference>
academic-pi validate-config
academic-pi dry-run
```

The standalone CLI validates the complete candidate-profile, preference, and
source schemas before constructing connectors or performing an operation.
All standalone state-dependent commands require the explicit durable state path
shown above; read operations never silently fall back to an empty in-memory
store. `handoff` additionally requires at least one explicitly authorized
private evidence-ledger reference. Use `dry-run` for a non-persisting
operational check. A host embedding the
service directly may intentionally supply a partial scoring context, but that
is a library integration and does not bypass strict CLI validation.

Use the repository's existing scheduler and register connector factories in a
trusted host wrapper. Configuration may select only those allowlisted
factories; it cannot dynamically import connector code. See
[CONNECTORS.md](docs/CONNECTORS.md). Schedule configuration expresses intent;
it never stores credentials.

## Safety invariants

- A transient retrieval or verification failure never closes a durable job.
- A broad faculty call is not penalized for omitting narrow specialty terms.
- Scientific fit, opportunity quality, QOL, eligibility, blockers, and
  confidence remain separate.
- Missing salary, startup, teaching, sponsorship, or deadline data remains
  unknown.
- Email processing is idempotent and never archives or deletes messages by
  default.
- Application generation and submission are different events. The Job Agent
  never submits an application; only the human does.
- No report channel is marked successful until its adapter confirms delivery.

## Start here

1. Follow [SETUP.md](docs/SETUP.md).
2. Register the host connector allowlist with [CONNECTORS.md](docs/CONNECTORS.md).
3. Configure alert ingestion with [GMAIL_ALERTS.md](docs/GMAIL_ALERTS.md).
4. Review [SOURCES.md](docs/SOURCES.md), [RSS_ALERTS.md](docs/RSS_ALERTS.md),
   [TARGET_INSTITUTIONS.md](docs/TARGET_INSTITUTIONS.md),
   [QOL.md](docs/QOL.md), and [SCORING.md](docs/SCORING.md).
5. Understand persistence in [STATE_MODEL.md](docs/STATE_MODEL.md).
6. Complete the release checks in
   [SHARING_AND_PRIVACY.md](docs/SHARING_AND_PRIVACY.md).
