<!-- SHARED CORE v2026-05-22 — canonical source: ai_research_os/shared_core.
     Do NOT edit in a downstream repo. Edit only in ai_research_os, then re-sync. -->

# Core Review Policy

> **SHARED CORE** — canonical source: `ai_research_os/shared_core`. Do NOT edit in a
> downstream repo. Edit only in `ai_research_os`, then re-sync. Version: 2026-05-22.

Source: consolidated from `Docs/review_decision_policy.md`. No new policy is
introduced here.

Final review is a human-supervised gate. Automated summaries and AI reviewer
labels are advisory only. Reviewers compare the implementation against the
approved `CHANGE_SPEC.md`, the repository design principles, the actual changed
files, and validation results.

## Review criteria

Evaluate whether the change:

- follows the approved `CHANGE_SPEC.md`
- stays inside the positive file list or clearly explains any approved exception
- avoids negative-list files unless the current task explicitly approves them
- avoids forbidden files and protected data
- passes required validation or reports exact failures
- avoids raw/private/restricted data exposure
- avoids local-path, secret, token, credential, and generated-export leakage
- preserves the AI-tool-agnostic workflow and keeps Claude Code optional
- avoids duplicate memory, state, or work-log systems
- keeps final Git actions human-controlled
- remains minimal, modular, reversible, and reviewable

## Verdict labels

Use exactly one final verdict label.

- `APPROVE` — the change matches the approved spec, stays within scope, passes
  required validation, preserves safety boundaries, and is ready for the human to
  run the approved post-review commit-preparation workflow. Approval does not
  authorize an AI tool to stage, commit, push, clean generated files, upload, or
  open a pull request unless the human separately asks.
- `REQUEST CHANGES` — the change is close but needs limited fixes before commit
  (for example missing documentation links, incomplete design-intent coverage, a
  narrow validation issue, unclear handoff notes, or a small file-scope mismatch).
- `BLOCK COMMIT` — the change must not be committed because it violates safety,
  scope, validation, or design-principle requirements (for example forbidden file
  access, raw/private/restricted data exposure, secret/token leakage, generated
  exports intended for commit, failed safety checks, unapproved dependency
  changes, or unapproved staging/commit/push/upload/delete/move/rename/merge/PR
  automation).
- `REVERT OR EXPLAIN` — the change contains broad, unrelated, surprising, or
  hard-to-review modifications and must be reverted or convincingly explained and
  human-approved before review continues (for example a duplicate state/log
  system, making Claude Code required for ordinary workflow, rewriting
  established workflows without need, or changing files outside the approved
  design without explanation).
