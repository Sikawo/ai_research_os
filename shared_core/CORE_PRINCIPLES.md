<!-- SHARED CORE v2026-05-22 — canonical source: ai_research_os/shared_core.
     Do NOT edit in a downstream repo. Edit only in ai_research_os, then re-sync. -->

# Core Principles

> **SHARED CORE** — canonical source: `ai_research_os/shared_core`. Do NOT edit in a
> downstream repo. Edit only in `ai_research_os`, then re-sync. Version: 2026-05-22.

Source: consolidated from `Docs/repo_design_principles.md`, `AI_INSTRUCTIONS.md`
(AI assistant behavior principles), and `AGENTS.md` (scope rules). No new policy
is introduced here.

## The workflow is the operating system

The repository workflow is the operating system. Individual AI tools — Claude
Code, ChatGPT, Codex, Cursor, future AI tools — and plain human command-line
workflows are adapter layers around that workflow. None of them is the operating
system, and the repository must remain usable without any specific tool.

## Repository files are durable shared memory

Git-tracked repository files are the durable shared memory for the project.
Claude Code memory, local chat history, in-app state, terminal history, and
per-computer settings are not source of truth: they may be absent, stale, private
to one computer, or unavailable to another AI tool.

Use these files for durable shared state:

- `HANDOFF.md` — current resumable work snapshot and safe next action.
- `CURRENT_STATUS.md` — broad project status and implemented capabilities.
- `NEXT_ACTIONS.md` — prioritized next work and deferred items.
- `AGENTS.md` — repository-wide implementation-side agent rules.
- `AI_INSTRUCTIONS.md` — durable AI behavior and safety guidance.
- `AI_SAFE.md` — concise AI safety and review-gate reminders.
- `CHANGE_SPEC.md` — an approved task specification, usually preserved during
  implementation at `exports/active_change/CHANGE_SPEC.md`.
- `FINAL_REVIEW_PACKET.md` — a generated review packet for human-supervised
  final review.

Do not create a new memory, status, or work-log system when these files already
cover the need.

## Human authority

The human remains the final scientific authority and the final Git authority.

AI tools may inspect, draft, validate, and generate review packets inside
approved scope. Final approval, generated-export cleanup, staging, committing,
pushing, merging, opening pull requests, and external uploads remain
human-controlled unless a current approved spec explicitly says otherwise.

## Adapter files are not higher authority

`CLAUDE.md` and files under `.claude/` are entrypoints/adapters for Claude Code.
They are not a daily work log, status file, or higher authority than repository
policy. If a tool-specific instruction conflicts with shared repository policy,
stop and ask the human to resolve the conflict.

## Change shape

Changes should be small, modular, reversible, and reviewable. Prefer
documentation, templates, metadata, focused tests, and lightweight scripts.
Avoid broad rewrites, duplicate coordination systems, and tool-specific
workflows that bypass the shared review gate.

## Temporary handoff space

`exports/` is temporary AI handoff and review space (active specs, review
packets, generated context). Generated `exports/` content must not be committed
and must not be used as durable memory.

## Repository content is English-only

Repository content (filenames, folder names, headings, body text, controlled
vocabulary) is English. The human may discuss the work in Japanese or English.
