# Career-Document Support Configuration

## Status

This file configures subordinate review modules. It does not activate Sprint or
GatedSprint, select a workflow phase, authorize edits, or record approval.
Canonical workflow authority remains at:

```text
plugins/gated-sprint/skills/gated-sprint/SKILL.md
```

## Applicability Triggers

Career-document support applies when the authorized scope includes a resume,
CV, curriculum vitae, cover letter, recommendation or reference letter, letter
of support, research statement, job application, faculty application, industry
application, postdoctoral inquiry, or related career packet.

Application-specific rules supplied by the caller take priority. Do not load a
private profile, context, or binding merely because a document category is
recognized.

## Internal Review Layers

1. Register target requirements and their sources.
2. Decide the document type.
3. Select the relevant public guidance or recommendation-letter profile.
4. Review target fit and evidence.
5. Review structure and formatting or ATS-relevant hygiene.
6. Review integrity, privacy, and bias risks.
7. Return bounded suggestions and unresolved decisions to the caller.

The caller, not this configuration, determines whether suggestions may be
implemented.

## Industry Resume Support

For an explicitly authorized industry resume evidence or qualification review,
the canonical caller may load:

```text
plugins/gated-sprint/skills/gated-sprint/references/industry-resume.md
```

Without an authorized target description, dependent applicability is
`NOT_ASSESSABLE`. A CV remains a CV unless the caller explicitly requests a
resume derivation. Do not duplicate the canonical module's gates, sidecar,
revision loop, or release rules here.

## Change-Risk Classification

### Green

- grammar, spelling, and punctuation corrections;
- consistent dates, headings, and section formatting;
- accurate stronger verbs;
- repetition trimming without meaning change; and
- unsupported generic phrasing converted into a missing-evidence flag.

### Yellow

- section reordering;
- evidence-based bullet restructuring;
- page-target compression;
- target-aware expansions using supplied evidence; and
- choosing between CV and resume when the target is ambiguous.

### Red

- invented achievements, funding, titles, metrics, status, or requirements;
- unsupported changes to dates, publication status, employment, degrees, or
  role scope;
- sensitive disclosures not explicitly chosen by the user; and
- removal of major experience when the tradeoff is unclear.

These labels describe risk only. They do not grant edit authority.
