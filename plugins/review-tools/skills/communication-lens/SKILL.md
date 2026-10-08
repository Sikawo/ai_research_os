---
name: communication-lens
description: Review a professional message for clarity, tone, relationship calibration, burden, and actionability when the user asks for communication review. Use only supplied context and do not infer another person's private thoughts or preferences.
metadata:
  version: "1.0.0"
---

# Communication Lens

Review a message without inventing social context or rewriting more than the
user requested.

Read [communication_lens_engine.md](references/core/communication_lens_engine.md)
before producing a recommendation. Use the templates under `assets/templates/`
when a structured request or review record is useful.

## Core behavior

- Identify the sender, recipient relationship, purpose, requested action,
  urgency, and constraints only from supplied information.
- Separate clarity, tone, burden, and actionability findings.
- Prefer the smallest sufficient revision.
- Preserve factual content and the sender's intended level of formality.
- Do not claim to know how the recipient will feel or respond.
- Do not create or persist a personal communication profile in this public
  package.
