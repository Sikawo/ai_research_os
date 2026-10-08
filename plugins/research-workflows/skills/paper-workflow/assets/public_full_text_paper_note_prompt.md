# Public Full-Text Paper Note Prompt

Use this prompt only for published papers where the human has intentionally supplied the public PDF or public full text for deeper reading.

Do not use this prompt for unpublished manuscripts, under-review manuscripts, confidential figures, reviewer comments, private drafts, or restricted internal material. Those belong in the restricted NIH-internal workflow.

Generated public full-text upgrade packets are context packets, not final paper notes. The human remains responsible for confirming the source is public, attaching the PDF or full text manually in the AI chat, reviewing any pasted existing abstract note text, and saving the final Markdown note manually.

---

## Prompt

You are helping me create a careful English Markdown paper note from a published paper.

Input context:

- Bookends XML bibliographic metadata
- A published public PDF or public full text intentionally supplied by the human in this chat
- Optional human-provided project or application relevance notes

Safety and accuracy rules:

- Do not invent citations, experiments, reagents, results, controls, or interpretations.
- Separate paper claims from interpretation and speculation.
- Preserve uncertainty and state when evidence is indirect.
- Do not include local paths, attachment paths, private storage locations, secrets, or credentials.
- Do not claim to have reviewed figures, supplementary material, methods, or full text unless they are present in the supplied public PDF or full text.
- Treat suggested experiments and follow-up papers as suggestions, not as facts.
- If existing abstract-note text is pasted, use it only as human-reviewed context and correct it against the supplied public paper.

Create a Markdown paper note using this frontmatter:

```yaml
---
title:
authors:
year:
doi:
pmid:
source: bookends_xml
note_depth: public_full_text_reviewed
security_tier: public
status: draft
priority:
projects:
tags:
---
```

Use this structure:

# Citation

# Concise Main Claim

# Background / Problem

# Why This Paper Matters

# Figure-by-Figure Summary

For each main figure or extended data figure that matters:

- question addressed
- experimental system
- assay or readout
- key observation
- control
- interpretation supported by the figure
- limitation or uncertainty

# Key Experiments and Controls

# Methods / Assays / Reagents That Matter for Interpretation

Include reagents, cell types, strains, models, perturbations, assays, imaging methods, sequencing methods, statistics, or analysis choices only when they are supported by the supplied public full text.

# Paper Claims

List claims directly supported by the paper.

# Interpretation

Explain what the results may mean, clearly separated from the paper's own claims.

# Speculation / Hypotheses

List possible ideas inspired by the paper. Label them as speculation.

# Limitations and Uncertainty

# Relevance to Ongoing Projects

# Relevance to research program / Application Thinking

Include only non-confidential, high-level relevance unless the human explicitly provides approved text.

# Suggested Follow-Up Papers

Clearly label these as suggestions.

# Suggested Follow-Up Experiments

Clearly label these as suggestions.

# AI-Ready Summary

Write a concise English summary suitable for future retrieval after human review.

# Human Checks Needed

List any claims, figure interpretations, reagent details, or citations that should be verified manually against the paper.

Also list any places where the draft depends on ambiguous figure panels, uncertain controls, missing supplementary information, or AI inference beyond the paper's stated claims.
