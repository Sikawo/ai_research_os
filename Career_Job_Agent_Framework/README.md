# Career Job Agent Framework

Career Job Agent Framework is a reusable, approval-gated workflow for discovering jobs, evaluating candidate fit, estimating family quality of life near the workplace, and preparing application documents while minimizing routine human interaction.

## Separation of concerns

The framework contains only reusable workflow logic:

- official-source job discovery and deduplication;
- configurable fit scoring and tier routing;
- economic and educational quality-of-life assessment;
- question minimization;
- Sprint / GatedSprint integration contracts;
- state and report schemas;
- example configuration files.

User-specific content must live outside this framework in a private profile repository or ignored local folder:

- identity and contact details;
- resume, CV, publications, and employment history;
- verified evidence registers;
- visa and work-authorization details;
- target roles and company allowlists;
- family composition, housing, schooling, and commute preferences;
- application drafts and generated files.

## User experience

The intended daily workflow is:

1. Search configured employers and official career pages.
2. Deduplicate and score new roles.
3. For every Tier 2 or better role, estimate economic and educational quality of life within the configured commute limit.
4. For Tier 1 roles, prepare the requirement register, draft documents, and GatedSprint Phase 1 packet.
5. Ask only unresolved factual or high-tradeoff questions.
6. End every daily report and ChatGPT, Gmail, and Slack digest with one shared `CURRENT ACTIVE TIER 1/2` snapshot containing all actionable Tier 1 / Tier 2 roles reverified active that run, including unchanged roles.
7. After explicit approval, generate final documents and return the official application URL and output folder.
8. Never submit an application automatically.

The current-active snapshot is a portfolio view, not a new-job alert. It remains present as `None.` when empty and never changes today's headline, discovery counts, material-change counts, alerts, or approval-packet routing. Deployments should build it once from canonical state and render the same role set in every configured channel.

Manual ChatGPT evaluations use that same canonical state. When an official employer page is verified currently active and the final role is an actionable Tier 1 or Tier 2, the deployment upserts it using the identity precedence in `contracts/state_persistence.md`. This manual state maintenance does not count as scheduled discovery, duplicate a daily alert, or trigger application generation or submission. A later `CURRENT ACTIVE TIER 1/2` run may include the role after its normal current-run official reverification.

## Configuration contract

A deployment should provide private instances of:

- `user_profile.yaml`
- `search_preferences.yaml`
- `life_preferences.yaml`
- `company_allowlist.yaml`
- `fit_rubric.yaml`
- storage and notification destinations

Examples are under `templates/`. They contain placeholders only.

## Privacy model

The reusable framework may be shared. User profiles, application evidence, generated documents, feedback history, and state records remain private. A public release must not include real application materials, personal addresses, immigration records, salary negotiations, family details, local paths, tokens, or credentials.

## Core contracts

- `contracts/daily_run.md`
- `contracts/fit_scoring.md`
- `contracts/qol_assessment.md`
- `contracts/state_persistence.md`

## Shared runtime

The additive `core/` package turns the existing contracts into reusable,
deployment-neutral primitives without changing the Industry workflow:

- canonical job/source/verification/run/change/coverage/application models;
- conservative URL normalization and identity-first deduplication;
- official-source verification transitions that preserve durable state on
  transient retrieval failures;
- material and evaluation change detection;
- layered public/private configuration loading;
- in-memory and atomic JSON state stores;
- injected discovery, email, verification, and report connector protocols;
- configurable public-release privacy checks.

The runtime uses the Python standard library and keeps unknown model fields for
backward-compatible deployment extensions.

## Academic PI deployment

`deployments/academic_pi/` is a sibling deployment built on the same core. It
supports email-alert ingestion, runtime-injected web/aggregator discovery,
target-institution scans, US/European title normalization, contextual
independence inference, official verification, academic scoring, daily and
weekly reports, and structured Academic GatedSprint handoff. Discovery and
application state stay separate, and application submission is never
performed.

Run the synthetic credential-free example from the repository root:

```bash
python3 -m Career_Job_Agent_Framework.deployments.academic_pi \
  --allow-example validate-config
python3 -m Career_Job_Agent_Framework.deployments.academic_pi \
  --allow-example dry-run
```

For real use, set `ACADEMIC_PI_PRIVATE_CONFIG_DIR` to a private directory and
inject the host runtime's Gmail, web/search, verification, and report
connectors. See `deployments/academic_pi/README.md` and its `docs/` folder.
