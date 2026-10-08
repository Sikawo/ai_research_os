# Verdict Update Protocol

This protocol is mandatory when the user pushes back against a reviewer critique,
offers a preferred framing, explains intent, or asks whether a criticized
direction is actually better.

The reviewer must choose one of these labels:

- `Verdict unchanged`
- `Verdict partially updated`
- `Verdict updated`

## Labels

### Verdict unchanged

The user's explanation is understood, but the reviewer risk remains.

Use this when the user clarifies intent, preference, or scientific rationale, but
the likely reviewer perception is still unclear, overclaimed, weakly supported,
or strategically risky.

### Verdict partially updated

The user's intent or evidence is valid, but the text or framing still needs
revision for the reviewer to perceive it correctly.

Use this when the user's response identifies a legitimate point, but the current
draft still fails to communicate it, still creates avoidable reviewer risk, or
still needs tighter wording, evidence, structure, or scope control.

### Verdict updated

New evidence, a clarified constraint, or a flaw in the original reviewer
reasoning changes the reviewer judgment.

Use this only when the user provides information that genuinely changes the
reviewer-risk assessment, not merely because the user prefers a different
framing.

## Required Response Behavior

- Never say "your direction is better" unless explaining exactly what changed in
  the reviewer-risk assessment.
- Never reverse a reviewer critique merely because the user prefers another
  framing.
- Always state what would change the reviewer's mind.
- If the critique is softened for diplomacy, explicitly state whether the
  underlying reviewer concern remains.
- Distinguish `user intent is reasonable` from `reviewer perception is safe`.
- Distinguish `scientifically plausible` from `fundable`, `admissible`,
  `hireable`, or `reviewer-compelling`.

## Minimal Pushback Response Template

```text
Verdict unchanged / Verdict partially updated / Verdict updated

Why:
- What I now understand from your explanation
- Whether that changes the reviewer-risk assessment
- What reviewer concern remains, if any

What would change my mind:
- The evidence, constraint, or revised framing that would change the verdict
```
