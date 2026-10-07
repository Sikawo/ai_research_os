# Codex Autonomous Work Policy

Status: active repository adapter
Owner: repository maintainers
Last updated: 2026-08-03
Scope: `ai_research_os` autonomous implementation and delivery.

## Shared contract and activation

This adapter applies `shared_core/CORE_AUTONOMOUS_DELIVERY_POLICY.md` to
`ai_research_os`. It does not broaden protected-content access or replace
`REPO_PROFILE.md`, the approved task scope, Independent Reviewer review, or the
repository final-review gate.

Autonomous delivery is active only when:

1. `config/autonomous_delivery.json` is valid and enabled;
2. the human explicitly approves this cycle and Git Delegation Level;
3. a machine-readable task scope declares the exact feature branch, path
   allowlist, forbidden paths, validation, commit message, and draft PR title;
4. every changed path is classified by that scope;
5. required validation, Independent Reviewer, and final-review gates pass.

The supported ceiling is Git Delegation Level 4. It permits an exact reviewed
commit, push to the approved feature branch, and creation or update of a draft
PR. It never permits direct push to `main`, merge, ready-for-review transition,
force push, history rewriting, branch deletion, destructive recovery, or broad
cleanup.

## Repository capability

- Base branch: `main`.
- Allowed branch prefixes: `agent/` and `codex/`.
- Allowed task classes: documentation, source, tests, config, and workflow.
- Protected-content mode: forbidden. Protected material may not be accessed or
  published by an autonomous delivery cycle; use a separate human-reviewed
  workflow when exact protected-content access is explicitly approved.
- Dependency installation: only inside the active project environment and only
  when the approved task requires it.
- Network validation: allowed only when required and when it does not upload
  repository or protected content.
- Shared-core edits: this repository is canonical; downstream copies must be
  synchronized separately in their own reviewed branches and PRs.
- Rollback: disable or lower the manifest, or use a normal revert PR. Preserve
  review evidence, branches, and draft PRs.
- Incident records: use repository coordination documentation without secrets,
  protected content, or local absolute paths.

## Required delivery gates

Before commit or publication:

1. inspect `git status --short`, the exact changed paths, and the exact staged
   paths;
2. reject unrelated, unclassified, generated, protected, secret-like, large,
   or local-path-heavy files;
3. run every repository and task validation command;
4. obtain an Independent Reviewer `APPROVE` verdict bound to the reviewed paths
   and content snapshot;
5. run `python3 Scripts/finish_change.py --active-spec` and verify safety and
   test PASS evidence;
6. run the shared autonomous-delivery review gate before and after exact
   staging;
7. inspect the staged diff and use the task scope's commit message;
8. push only the exact approved feature branch and create or update only a
   draft PR targeting `main`.

Generated `exports/` content is evidence only and must not be committed.

## Repository-specific hard stops

Stop the affected workstream when the next step would:

- read, modify, summarize, export, stage, commit, or upload protected content
  outside exact approved scope;
- publish private documents, papers, protocols, experiment data content, raw
  microscopy, sequencing, flow-cytometry, large dataset, or notebook content;
- include credentials, API keys, access tokens, private keys, `.env` files,
  local absolute paths, or local file URLs;
- create or change project IDs without the required registry update and scope;
- change dependency, security, privacy, institutional, scientific, or
  publication policy outside the approved task;
- combine changes for another repository into this repository's commit;
- bypass validation, Reviewer, final-review, task-scope, or staged-path gates;
- require direct `main` publication, merge, ready-for-review transition, force
  push, hard reset, broad clean, history rewrite, branch deletion, or other
  destructive recovery.

An uncertain or unclassified path is a stop. Independent safe workstreams may
continue.

## End-of-run record

Report repository, branch, starting commit, changed and committed paths,
validation results, Reviewer verdict, final-review packet, commit hash, push
status, draft PR URL, risks, rollback point, exact stop condition, and pending
human merge. Do not include protected content, secrets, or local paths.
