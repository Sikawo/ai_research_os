<!-- SHARED CORE v2026-05-22 — canonical source: ai_research_os/shared_core.
     Do NOT edit in a downstream repo. Edit only in ai_research_os, then re-sync. -->

# Shared Core

> **SHARED CORE** — canonical source: `ai_research_os/shared_core`. Do NOT edit in a
> downstream repo. Edit only in `ai_research_os`, then re-sync. Version: 2026-05-22.

`shared_core/` is the canonical home for reusable AI-workflow governance rules
that downstream repositories may adopt through an explicit, reviewed sync.

## What this is

The files here hold the common floor of governance: design principles, the
spec-first workflow, the command policy, the AI chat access policy, the
external-AI sharing floor, the review policy, and the bounded autonomous
delivery contract. Each `CORE_*.md` file names its sources on a `Source:` line.

The autonomous-delivery contract is opt-in. Copying shared core into a
repository does not enable Git actions without a local adapter, capability
manifest, task scope, and explicit human activation.

## Edit and sync rule

- In `ai_research_os` (this repository) `shared_core/` is the canonical, editable
  source. Edit shared rules ONLY here.
- In a downstream repository, `shared_core/` is a verbatim, read-only copy. Do
  NOT edit it there. To change a shared rule, edit it here and re-sync.
- Sync is a verbatim folder copy, verified with `diff -r`. `diff -r` is the
  authoritative drift check; the marker version date is human-facing information
  only.

## The marker

Every file carries a marker in two forms — a visible blockquote note and an HTML
comment — so the "canonical source / do not edit downstream / version" message is
clear in both rendered Markdown and raw source.

## Floor, not ceiling

`shared_core/` sets the MINIMUM safety every repository must honor. Each
repository's `REPO_PROFILE.md` may ADD stricter restrictions, but it may never
weaken a `shared_core/` rule.

## Transition status

The entrypoints (`AGENTS.md`, `AI_SAFE.md`, `CLAUDE.md`) now reference
`shared_core/` for governance details. `shared_core/` is the canonical
governance source. `REPO_PROFILE.md` holds repository-specific additions.

`AI_INSTRUCTIONS.md` has not yet been thinned and retains its own inline
wording. If `AI_INSTRUCTIONS.md` and `shared_core/` appear to disagree,
`shared_core/` wins for shared governance rules; `AI_INSTRUCTIONS.md` wins
for repository-specific content (project IDs, experiment conventions,
repo-specific workflow descriptions).

See `Docs/shared_core_architecture.md` for the full design.
