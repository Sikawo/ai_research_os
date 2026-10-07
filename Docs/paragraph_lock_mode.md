# ParagraphLock Mode

## Status

ParagraphLock is a reusable, approval-gated editing mode packaged in this repository as a Codex and ChatGPT plugin skill.

The canonical operational contract is:

```text
plugins/paragraph-lock/skills/paragraph-lock/references/protocol.md
```

## User outcome

ParagraphLock prevents an assistant from silently rewriting untouched text after a user has discussed one paragraph or smaller passage in depth. The user can approve exact replacements one at a time and later request the full text without authorizing a general rewrite.

## Invocation

Invoke the installed skill directly:

```text
$paragraph-lock
```

Plain-language invocations such as `ParagraphLock` and `paragraph lock` are also supported by the skill metadata.

## Design summary

ParagraphLock separates three activities:

1. discussion, which may explore alternatives without changing the document;
2. approval, which records one exact replacement under a stable candidate ID;
3. assembly, which applies approved replacements to a frozen baseline and verifies the result.

The full document is never a fresh writing pass. It is the baseline plus the approved replacement ledger.

## Guarantee levels

- `Verified`: an exact UTF-8 baseline is available and the bundled deterministic verifier passes.
- `Conversation-only`: the assistant follows the approval rules but cannot prove exact preservation. It must not describe the output as verified.

The first release verifies UTF-8 plain text. Structured document internals such as DOCX runs, comments, fields, styles, and pagination remain outside its guarantee.

## Privacy boundary

The Git repository stores only the workflow, skill, verifier, and synthetic tests. User applications, manuscripts, proposals, and other source documents remain outside the plugin repository.

## Relationship to GatedSprint

ParagraphLock borrows the exact-approval and allowed-change-set invariants of approval-gated editing, but it does not run the analytical phases, review panels, decision packet, or final-file workflow of GatedSprint. It is a lightweight editing boundary for ordinary paragraph-by-paragraph collaboration.

## Human Desired Outcome Check

- Goal: discuss one passage deeply without collateral rewrites elsewhere.
- Minimum observable result: unapproved text remains unchanged when the full text is assembled.
- Failure condition: vague assent is treated as approval, the full document is regenerated, or exact preservation is claimed without verification.
- Verification: inspect the approved replacement ledger and run the deterministic verifier before presenting a result as `Verified`.
