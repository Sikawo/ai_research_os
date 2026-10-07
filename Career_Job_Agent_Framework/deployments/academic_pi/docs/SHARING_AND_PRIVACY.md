# Sharing and Privacy

The sharing boundary is simple: the public repository contains the engine; the
private overlay contains the person.

## Public content

Public, reusable content may include framework code, schemas, generic source
metadata, title ontology, scoring defaults, report and prompt contracts, CLI
orchestration, tests, synthetic examples, and documentation.

## Private content

Keep these outside the public core:

- a real person's identity, CV, publications list, or research statements;
- immigration, work-authorization, family, salary, and identifying geographic
  preferences;
- target-institution rankings and private notes;
- email addresses and Gmail, Slack, or Drive destination identifiers;
- OAuth material, API keys, tokens, credentials, or secrets;
- canonical job state, application history, generated reports, and application
  materials; and
- local absolute paths or file URLs.

Private paths may be referenced inside the private overlay. They must not be
copied into public examples, reports intended for sharing, logs, or commits.

## Required ignore coverage

The repository-level ignore policy should cover the paths actually used by the
host deployment, including equivalents of:

```gitignore
.env
.env.*
profiles/local/
private/
state/
outputs/
reports/private/
application_materials/
credentials/
tokens/
*.token
*.secret
```

In this repository the built-in fallback resolves to
`Career_Job_Agent_Framework/profiles/local/`, so the repository-level ignore
file must name that actual path (and the framework-scoped private, state,
output, report, application-material, credential, and token directories), not
only a similarly named directory at repository root.

Do not rely on ignore rules alone. A tracked file remains tracked after a later
ignore rule is added.

`Scripts/run_safety_check.py` inventories the public Career Job Agent tree and
fails when a framework private-runtime prefix is tracked. It deliberately
prunes ignored private subtrees instead of opening their contents.

## Secret and personal-data guards

Use the repository's existing secret scanner when available and include Academic
PI private-path patterns. Otherwise, use a lightweight tracked-file check for
obvious connector-secret patterns.

Private configuration may define `privacy_guard.forbidden_literals` and
`privacy_guard.forbidden_regexes`. A public-release check should scan tracked
public files for those identifiers without printing matching secret values into
logs. Keep the guard configuration itself private when it contains personal
identifiers.

Run the repository gate with an explicitly named private JSON guard file:

```bash
python3 Scripts/run_safety_check.py --full-scan \
  --privacy-config ../career-job-agent-private/academic_pi/privacy_guard.json
```

The gate applies obvious secret patterns to every pending release file and the
configured personal identifiers to every tracked public file. It inventories
private and protected paths without opening them, fails closed when Git cannot
produce the inventory, and never prints configured values or matching text.

## Safe examples

Public fixtures and templates use placeholders, reserved example domains, or
clearly synthetic institutions. Never replace them in place with the current
user's profile. Copy them into the private overlay and edit the private copies.

The public deployment must continue to run in test or demonstration mode when
the private overlay is absent. Demonstration output must remain synthetic and
must not silently load another user's profile or state. `--allow-example`
forces the synthetic templates even when a private-overlay environment variable
or ignored repo-local profile exists; it is limited to validation and dry-run.
Operational state-changing commands require an explicit private `--state`
path.

## Pre-share checklist

Before publishing a branch or release:

1. List tracked files and confirm no private directory, state, report,
   application material, credential, or generated output is included.
2. Run the repository secret scanner and personal-data guard.
3. Search tracked public files for configured forbidden literals and regexes.
4. Confirm examples contain only synthetic names, fields, institutions, URLs,
   and evidence references.
5. Confirm logs and test snapshots do not contain email bodies, addresses,
   connector IDs, local paths, or state copied from a real run.
6. Confirm public configuration contains no enabled destination that could send
   a report to a real person or service.
7. Confirm application submission remains disabled.

If any check is uncertain, stop publication and inspect the exact tracked path.
