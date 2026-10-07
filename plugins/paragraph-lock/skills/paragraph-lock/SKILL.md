---
name: paragraph-lock
description: Preserve all unapproved text while discussing and revising one explicitly bounded paragraph or passage at a time. Use when the user invokes ParagraphLock, paragraph lock, or asks to prevent collateral rewrites during iterative document editing.
---

# ParagraphLock

Use this skill for approval-gated editing of an existing text. It is intentionally lighter than a full staged review workflow.

Read [references/protocol.md](references/protocol.md) before starting a ParagraphLock session. Follow it as the normative contract.

## Essential behavior

1. Freeze the exact supplied source as the baseline before proposing a replacement.
2. Identify one active scope: a paragraph or a narrower user-selected span. Everything else is locked.
3. Discuss freely, but label each exact replacement candidate with a stable ID such as `P3-r2`. Discussion is not implementation.
4. Treat only an explicit adoption instruction as approval. A bare `adopt` is valid only when exactly one current candidate is unambiguous. Praise, agreement, silence, or a request to continue is not approval.
5. Record the exact approved before-and-after text. Approval does not extend to adjacent wording, punctuation, formatting, citations, or cleanup.
6. Move to another scope only when the user asks. Keep previously approved replacements in the session ledger.
7. When the user requests the full text, assemble it from the frozen baseline plus the approved replacements. Do not regenerate, polish, normalize, or retype locked text from memory.
8. When local files are available, use `scripts/verify_paragraph_lock.py` to assemble and verify the result. Report `PASS` only after exact verification.
9. If the baseline is unavailable, incomplete, or outside the current context, ask the user to reattach or repaste it. Never claim exact preservation from memory.
10. Do not save a user's source document, application, or manuscript into the plugin repository.

Keep the visible interaction small. A suitable status line is:

```text
ParagraphLock | baseline: B1 | active: P3 | candidate: P3-r2 | approved: 1
```

When verification succeeds, report:

```text
ParagraphLock check: PASS
Approved changes: <count>
Unapproved text changes: 0
```

When verification cannot run, label the result `Conversation-only` and do not describe it as exact or verified.
