<!-- SHARED CORE v2026-06-09 — canonical source: ai_research_os/shared_core.
     Do NOT edit in a downstream repo. Edit only in ai_research_os, then re-sync. -->

# Core AI Chat Access Policy

> **SHARED CORE** — canonical source: `ai_research_os/shared_core`. Do NOT edit in a
> downstream repo. Edit only in `ai_research_os`, then re-sync. Version: 2026-06-09.

Source: created from `SPEC_20260609_ai_chat_access_policy_alignment`.

This policy defines the shared repository access model for AI chat and coding
tools. ChatGPT, Claude, Codex, Cursor, future AI tools, and plain human-driven
workflows should follow the same conceptual policy. Tool brand does not
determine repository access.

## Core Principle

Protected does not mean impossible to read.

Protected means:

- do not read by default
- ask first when scope is unclear
- read only when the user explicitly requests the task and names the relevant
  file or folder, or when an approved `CHANGE_SPEC.md` places it in positive
  scope
- write or edit only with explicit user instruction and positive scope

Read access is never write/edit access.

## Normally Readable

AI tools may read committed, text-only repository files needed for the active
task when those files are free of secrets and local absolute paths.

Normally readable files may include:

- shared governance documents
- repository profile files
- AI entrypoint files
- README-style documentation
- source code
- tests
- templates
- schemas
- lightweight configuration without secrets
- small synthetic examples

Normally readable does not authorize editing. Editing still requires the active
task or approved spec to place the file in positive scope.

## Ask-First Or Explicit-Scope Readable

Repository-specific protected content that is not hard-deny content belongs in
this class unless a repository profile marks it more strictly.

This content is not read by default. It may be read only when:

- the user explicitly requests the task and names the relevant file or folder
- an approved `CHANGE_SPEC.md` places the file or folder in the positive file
  list
- the assistant asks a narrow clarification and the user authorizes that access

Examples may include private research notes, paper notes, drafts, protocols,
experiment records, analysis summaries, non-secret metadata, and other protected
repository content defined by the repository's `REPO_PROFILE.md`.

Do not inspect protected folders merely to decide whether their contents are
sensitive. If scope is unclear, ask first.

## Exact-File Explicit Only

Some high-risk but non-secret content needs narrower handling than ordinary
ask-first content. For this class, broad folder browsing is not appropriate.
Access requires an exact file path from the user or an exact positive-scope entry
in an approved spec.

Examples may include private applications, unpublished manuscript drafts,
identifiable correspondence, private paper notes, sensitive protocols, or any
repository-profile category marked exact-file-only.

Exact-file read access is not permission to read sibling files, parent folders,
embedded attachments, or linked local paths.

## Hard-Deny Content

Hard-deny content must not be read automatically and must not be relaxed merely
because a tool prefers broad indexing or broad local access.

Hard-deny includes:

- secrets
- credentials
- access tokens
- API keys
- private keys
- `.env` files
- local absolute paths
- local file URLs
- unsafe local environment state

Do not follow, expose, summarize, index, export, or commit local absolute paths
or local file URLs. Repo-relative paths are acceptable when needed for normal
repository work.

A human may intentionally provide sensitive material for immediate
troubleshooting. That does not make it repository content. Minimize exposure, do
not persist it, and ask how to proceed.

## Write And Edit Rules

Read access is not write/edit access.

- Normally readable files may be edited only when the active task or approved
  spec places them in positive scope.
- Protected files may be written or edited only with explicit user instruction
  and positive scope.
- Exact-file-only content may be edited only when the exact file is named in
  positive scope.
- Hard-deny content must not be edited, committed, summarized, exported, or used
  to generate persistent repository content.
- If scope is unclear, ask first.
- Generated review packets and summaries must not include secrets, local
  absolute paths, raw data, or protected content beyond the minimum necessary
  approved context.

## Claude Settings Mirror Rule

`.claude/settings.json` and similar tool-local settings are adapter
configuration, not repository policy. They should mirror repository policy, not
override it.

Claude settings should:

- allow low-risk reads of normally readable repository files
- avoid broad hard-deny rules that block repo-approved explicit-scope work
- reserve hard-deny patterns for secrets, credentials, tokens, private keys,
  `.env` files, local absolute paths, local file URLs, unsafe local environment
  state, and repository-specific hard-deny paths
- represent protected content as ask-first or explicit-scope where the settings
  model can do so
- keep write/edit permissions narrower than read permissions

If Claude settings hard-deny a path that repository policy and an approved spec
place in positive scope, Claude should ask the human for a narrow settings update
rather than requiring the user to switch to another AI tool. The requested update
must be specific to the approved task or path and must not broadly weaken
hard-deny protection.

## Downstream Adoption

`ai_research_os/shared_core/` is the canonical source for this policy.
Downstream repositories should copy `shared_core/` verbatim after a canonical
change is approved.

Downstream repositories should:

- keep repository-specific additions in `REPO_PROFILE.md`
- add stricter restrictions only in the repository profile
- never weaken the shared-core floor
- point `AGENTS.md`, `AI_SAFE.md`, `CLAUDE.md`, and similar entrypoints to this
  policy without making any one AI tool required
- mirror this conceptual policy in Claude settings only through repo-local,
  reviewed changes
- adopt changes through separate repository-local specs and reviews
