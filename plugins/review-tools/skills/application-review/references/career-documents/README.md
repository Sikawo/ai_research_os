# Career-Document Review Support

## Authority Boundary

This directory is a subordinate library for focused career-document review. It
does not define a user-facing Sprint or GatedSprint workflow and does not
authorize edits or final artifact generation.

Exact bare Sprint and every GatedSprint route are owned by:

```text
plugins/gated-sprint/skills/gated-sprint/SKILL.md
```

The canonical workflow may consult these files for bounded diagnostics. The
standalone `application-review` skill may also use them when the user asks for a
focused review rather than the full canonical workflow.

## Supported Documents

- resumes and CVs;
- cover letters;
- recommendation, reference, and support letters;
- research statements and research plans; and
- mixed career-application packets.

## Support Modules

- `mode_config.md`: document-type and applicability configuration;
- `target_requirement_register.md`: source-labeled target requirements;
- `document_type_router.md`: document-type decision support;
- `career_document_review_checklist.md`: review checklist;
- `recommendation_letter_profile.md`: recommender-voice and evidence checks;
- `sprint_adapter.md`: diagnostic sequence supplied to the canonical caller.

For an explicitly authorized industry-resume evidence review, the canonical
caller may additionally use:

```text
plugins/gated-sprint/skills/gated-sprint/references/industry-resume.md
```

That module retains its own evidence and release rules; this directory does not
duplicate them.

## Source Boundary

Use only target descriptions, documents, and public guidance that the caller is
authorized to provide. Target-specific instructions override generic guidance
when the conflict is documented. Do not paste long source excerpts into output
or repository files, and do not infer missing achievements or requirements.

## Review Outputs

A focused review may return:

- a source-labeled target requirement register;
- document-type and applicability decisions;
- target-fit, structure, evidence, formatting, clarity, and integrity findings;
- bounded change proposals;
- unresolved questions and missing information; and
- human-decision items for high-tradeoff changes.

These outputs are diagnostic. The owning workflow decides whether any proposal
is approved or implemented.

## Writing Boundary

Language suggestions may improve clarity, concision, tone, and consistency, but
must not invent achievements, inflate ownership, change factual status, or turn
missing evidence into a claim.
