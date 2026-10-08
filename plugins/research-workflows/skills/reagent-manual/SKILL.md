---
name: reagent-manual
description: Convert a user-supplied public kit or reagent manual into a concise generic Markdown record. Use for public manual extraction; do not discover private files or save into a real inventory.
---

# Reagent Manual Extraction

Summarize a public kit or reagent manual that the user deliberately supplies as
text, a public URL, screenshot, or public PDF. Use
`assets/Kit_Reagent_Manual_Template.md` and return the draft to the user.

## Boundary

- Never search local storage or a repository for manuals.
- Never read or upload a PDF unless the user supplied that public PDF for this
  run.
- Do not write the result into a real manual index, inventory, or repository.
- Do not copy long copyrighted passages. Paraphrase operationally and quote
  only short text necessary for an exact warning or specification.
- Keep vendor facts, user comments, and experimental observations separate.

## Required extraction

Extract supported product identity, catalog number, manual version/date,
storage, preparation, critical timing, temperatures, compatibility limits,
controls, QC criteria, troubleshooting, and safety statements. Record every
distinct `Note`, `Important`, `Caution`, `Warning`, `Critical`, or equivalent
instruction rather than collapsing them into one vague summary.

Separately enumerate all materials required but not provided, including
reagents, buffers, additives, consumables, equipment, standards, controls, and
accessories. Preserve exact catalog numbers, concentrations, grades, volumes,
and handling instructions when stated. Mark missing information as `not found`
or `needs human review`; never infer it.

Return:

1. a generic proposed filename;
2. a completed Markdown draft;
3. an extraction-quality summary;
4. a `must verify before experiment` list; and
5. only the follow-up questions required for safety or correctness.
