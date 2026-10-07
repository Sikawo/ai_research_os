<!-- SHARED CORE v2026-05-22 — canonical source: ai_research_os/shared_core.
     Do NOT edit in a downstream repo. Edit only in ai_research_os, then re-sync. -->

# Core External-AI Sharing Floor

> **SHARED CORE** — canonical source: `ai_research_os/shared_core`. Do NOT edit in a
> downstream repo. Edit only in `ai_research_os`, then re-sync. Version: 2026-05-22.

Source: consolidated from `AI_SAFE.md`. No new policy is introduced here. This is
the MINIMUM external-AI sharing floor; a repository's `REPO_PROFILE.md` may add
stricter restrictions.

## Minimum-necessary context

Use external AI tools only with minimum-necessary context. Prefer generated
context/review packets over giving an external tool direct access to the
repository or to raw data.

## Generally safe to share

When free of secrets and local absolute paths:

- source code
- tests
- small synthetic examples
- documentation
- templates
- configuration without secrets

## Do not share without explicit, de-identified, human-approved minimization

- raw data and experiment data
- papers, PDFs, notebooks
- images and large data files
- experimental metadata
- local absolute paths
- secrets, credentials, tokens, private keys, `.env` content

Repository-specific protected content (for example a repository's local instrument
paths, acquisition folders, or export folders) belongs in that repository's
`REPO_PROFILE.md`, not in this shared floor.

## Review packets

External review packets should include only diffs, short summaries, expected
behavior, and minimal necessary source snippets. Never include secrets, tokens,
credentials, local absolute paths, or raw data. If real context is needed,
summarize it manually in de-identified form.

Per-tool memory/history and local chat state are not safe shared memory. Durable
shared memory belongs in reviewed repository files.
