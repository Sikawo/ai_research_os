# Connector Factory Contract

The standalone CLI does not import connector code named by configuration.
Instead, a trusted host registers a small allowlist of already imported factory
callables. A private `connectors.yaml` may select one of those registered names,
but it cannot provide a module, class, entry point, or arbitrary expression.

This boundary keeps connector code, credentials, and network policy under host
control while allowing normal CLI commands to construct real adapters instead
of silently running with an empty connector list.

## Configuration shape

The public `config/connectors.yaml` contains an empty, disabled-by-absence
baseline. Copy `templates/connectors.example.yaml` into the private overlay as
`connectors.yaml`, replace its placeholder factory selectors, then enable and
bind only connectors registered by the trusted host. A private overlay can
provide declarations such as:

```yaml
version: 1

plugins:
  - id: institution_direct
    factory: official_search_v1
    enabled: true
    capabilities: [discovery, verification]
    options:
      credential_profile: academic-search

  - id: email_alert
    factory: academic_alerts_v1
    enabled: true
    capabilities: [email]
    options:
      account_profile: academic-alerts

bindings:
  discovery: [institution_direct]
  verification: institution_direct
  email: email_alert
  report: []
```

A discovery connector ID must match an ID in `source_catalog.yaml`, including a
private society source added through `source_overrides.yaml`. Verification and
email accept at most one bound connector. Report and discovery bindings may
contain multiple connector IDs.

`options` may contain non-secret selectors for the private host. Do not place
tokens, OAuth material, passwords, or destination identifiers in a public
file. A host should resolve a selector through its own private credential
mechanism.

## Host allowlist

Each factory receives a copy of its connector declaration and returns one
connector object. Construction should be local and side-effect free; network
access belongs in connector methods such as `discover` or `verify`.

```python
from Career_Job_Agent_Framework.deployments.academic_pi.cli import main
from private_academic_runtime import make_alert_connector, make_official_connector


FACTORIES = {
    "academic_alerts_v1": make_alert_connector,
    "official_search_v1": make_official_connector,
}


raise SystemExit(main(connector_factories=FACTORIES))
```

The imports above are fixed by the trusted host program. The YAML file cannot
change them. Factory results are checked against their declared capability:

- discovery: `discover`;
- verification: `verify`;
- email: `fetch_unprocessed`, `mark_processed`, `mark_needs_review`, and
  `mark_error`; and
- report: `deliver`.

The returned object's `connector_id` (or `id`) must exactly match the configured
plugin ID.

## Failure behavior

`validate-config` reports duplicate IDs, unknown capabilities, unregistered
factories, disabled or missing binding targets, capability/binding mismatches,
unknown source references, and connector objects missing required methods.

Without an injected service, normal discovery commands stop with a clear
configuration error when their required connector capability is absent:

- `scan-source` and `scan-institution` require discovery;
- `verify` and `evaluate` require verification; and
- `daily` and `weekly` require discovery or email plus verification.

`--allow-example dry-run` is the one connector-free demonstration path. It is
explicitly synthetic and does not claim live coverage.
