# Academic PI Deployment Setup

This setup keeps the reusable engine public and all personal configuration and
state private. A user should not need to edit deployment code to change fields,
geography, institutions, source cadence, or scoring weights.

## Prerequisites

- A checkout containing the Career Job Agent Framework.
- A runtime that exposes the framework's state, discovery, verification, and
  report-adapter interfaces.
- A private directory or private repository that is not tracked by the public
  checkout.
- Connector credentials supplied through the existing private connector
  mechanism, never through public YAML.

## 1. Create the private overlay

Copy and rename the synthetic files from `templates/` into the academic section
of the private configuration location:

```text
academic_pi/
├── candidate_profile.yaml
├── preferences.yaml
├── target_institutions.yaml
├── source_overrides.yaml
├── scoring_overrides.yaml
└── connectors.yaml
```

In particular, copy `templates/connectors.example.yaml` to
`connectors.yaml`. Its declarations are disabled until the trusted host
registers the named factories and the private copy enables and binds them.

Do not edit the example templates with real personal data inside a public
checkout. The examples are intentionally synthetic and may be used unchanged
for tests or demonstrations.

## 2. Select the private directory

Set `ACADEMIC_PI_PRIVATE_CONFIG_DIR` to the directory containing the private
files. For example, when a private checkout sits beside the public checkout:

```bash
export ACADEMIC_PI_PRIVATE_CONFIG_DIR="../career-job-agent-private/academic_pi"
```

Resolution order is:

1. `ACADEMIC_PI_PRIVATE_CONFIG_DIR`;
2. existing private Career Job Agent configuration;
3. ignored `profiles/local/`;
4. synthetic example configuration for tests or demonstrations only.

The runtime should report which layer was selected without printing its private
contents.

`--allow-example` is an explicit exception to this resolution order: it forces
the synthetic templates and ignores environment, existing-private, and
repo-local overlays. It is accepted only by `validate-config` and `dry-run`, so
it cannot accidentally run a state-changing workflow against a private profile.

## 3. Describe evidence, not aspirations

Complete `candidate_profile.yaml` with factual fields, questions, systems,
methods, and authorized evidence references. Keep direct evidence distinct from
adjacent experience. Do not place unsupported claims in the profile.

Complete `preferences.yaml` separately. Scientific fit must not change merely
because a location or lifestyle preference changes.

## 4. Configure discovery

- Select entries from `config/source_catalog.yaml` through
  `source_overrides.yaml`.
- Add private target institutions, known domains, departments, and career URLs.
  A hand-entered URL is optional; successful official URLs may be learned into
  private state.
- Add field-relevant scientific societies privately. The public catalog does
  not assume one discipline.
- Configure email alerts as described in `GMAIL_ALERTS.md`.

## 5. Configure connectors privately

Use the allowlisted factory contract in `CONNECTORS.md`. The private
`connectors.yaml` selects factories registered by a trusted host program and
binds their declared discovery, verification, email, or report capabilities.
Configuration is never treated as a Python import path or executable
expression.

Keep addresses, destination IDs, OAuth material, API keys, tokens, and secrets
outside tracked public files. Connector options should contain only private
credential-profile selectors resolved by the host. Select only the channels
that should actually receive reports.

## 6. Validate configuration

Run the deployment's configuration-validation entry point before discovery.
If the private connector file enables host factories, invoke the trusted host
wrapper described in `CONNECTORS.md` so the allowlist is registered:

```bash
python3 private_academic_runtime.py \
  --private-config-dir "$ACADEMIC_PI_PRIVATE_CONFIG_DIR" validate-config
```

The direct `python3 -m Career_Job_Agent_Framework...` form is appropriate for
the connector-free synthetic example or a configuration whose connectors are
all disabled; it cannot register private host factories by itself.

It validates the candidate and preference files against the schemas, confirms
that referenced source and connector IDs exist, checks binding/capability
agreement, and reports missing or unregistered connector capabilities without
exposing secret values.

Resolve all schema errors before scheduling. An unavailable optional report
channel may be disabled; an unavailable authoritative state adapter must stop
state-mutating runs.

## 7. Run a dry daily scan

Run the non-mutating deployment check through that same trusted wrapper when
connectors are enabled:

```bash
python3 private_academic_runtime.py \
  --private-config-dir "$ACADEMIC_PI_PRIVATE_CONFIG_DIR" dry-run
```

Host adapters may expose the same operation as `academic-pi dry-run`. The
connector-free form requires `--allow-example` and is only a synthetic
demonstration. Confirm that a configured dry run:

- loads the intended private overlay;
- generates bounded role-first, field-first, broad, and institution queries;
- does not write state or apply email labels in dry-run mode;
- marks aggregators as discovery-only;
- leaves unknown values unknown; and
- reports coverage failures separately from a genuine zero-result scan.

The deterministic connector-free demonstration is:

```bash
python3 -m Career_Job_Agent_Framework.deployments.academic_pi \
  --allow-example dry-run
```

## 8. Inspect state and reports

All standalone commands that read or change job/run state require an explicit
private JSON state path. Keep it outside the public checkout, for example:

```bash
export ACADEMIC_PI_STATE_PATH="../career-job-agent-private/state/academic_pi.json"
python3 private_academic_runtime.py \
  --private-config-dir "$ACADEMIC_PI_PRIVATE_CONFIG_DIR" \
  --state "$ACADEMIC_PI_STATE_PATH" daily
```

The explicit path prevents a successful-looking operational or inspection
command from using ephemeral memory. A read command also requires the state
file to already exist. `dry-run` remains non-mutating and does not require
`--state`; if a state path is supplied for its snapshot, a missing file is not
created.

For a write-enabled test run, inspect Jobs, Runs, Changes, SourceCoverage,
InstitutionCoverage, and Applications. Confirm that repeated input upserts one
canonical job, the current-active snapshot contains only currently verified
roles, and no application is reported submitted.

## 9. Enable scheduling

After validation, connect daily and weekly operations to the existing scheduler
used by the host deployment. Suggested intent is daily high-frequency discovery,
a weekly full audit, and institution scans every three days, with per-source and
per-institution private overrides.

Credentials must remain in the connector mechanism rather than scheduler
configuration. Manual scans, single-job verification, and single-institution
scans remain available independently of the schedule.

## 10. Verify privacy before sharing

Complete the checklist in `SHARING_AND_PRIVACY.md`. In particular, verify that
private configuration, state, reports, application materials, and credentials
are ignored and that tracked-file privacy checks pass.
