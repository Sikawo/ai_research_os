# User Profile Template

This template is the basis for a personal `USER_PROFILE.md` overlay. Copy it
to `USER_PROFILE.md` at the repository root and fill in the fields you want.

`USER_PROFILE.md` is gitignored. It is a personal, per-machine file. Only
this template is committed.

## Floor rule

This file is a personal overlay. It adds personal preferences on top of
`Docs/decision_delegation_protocol.md`. It must not weaken any Category 1
rule, any safety boundary in `AGENTS.md` or `AI_SAFE.md`, or any rule in
`shared_core/`.

The overlay is a ceiling: it may tighten the protocol (for example by
expanding what counts as Category 1 for this user) but it must not loosen
it.

## Fields

### User role and background

<!-- example: Wet-lab researcher and part-time programmer. Comfortable
     reading shell, Markdown, and short Python; not comfortable writing or
     debugging Python alone. Treats the repository as a research operations
     system, not a software product. -->

### Languages I read fluently

<!-- example: English and Japanese. Prefer English in repository content;
     Japanese is fine in chat. -->

### Decisions I want AI to always ask me about (personal Category 1 expansions)

<!-- example:
     - Any change that modifies a script under Scripts/ even if the active
       spec allows it.
     - Any change that touches shared_core/** for any reason.
     - Any new external dependency, even a single library.
     - Any change that introduces a new top-level directory. -->

### Decisions AI may handle silently (personal Category 2 expansions)

<!-- example:
     - Choosing between equivalent English synonyms inside an existing
       controlled vocabulary entry.
     - Formatting Markdown lists and tables.
     - Reordering bullet items where order is not semantically meaningful. -->

### Preferred verbosity and communication style

<!-- example: Short and concrete. Show concrete file paths and exact
     commands. Avoid long preambles. Summaries at the end should be one or
     two sentences. -->

### Hard limits (AI must never decide alone regardless of category)

<!-- example:
     - Never stage, commit, push, or open a pull request without an
       explicit human ask in the current task.
     - Never read or summarize files under raw_data/, RawData/, data/raw/,
       Data/raw/, or any path containing experimental records, papers,
       images, PDFs, or notebooks.
     - Never modify .env or any credentials file.
     - Never overwrite USER_PROFILE.md without explicit confirmation. -->
