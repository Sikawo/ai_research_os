# Career-Document Diagnostic Adapter

## Status

The filename is retained for migration traceability. This adapter is a
subordinate analysis module and cannot activate or execute Sprint, GatedSprint,
or any source-editing workflow.

Exact bare Sprint and every GatedSprint route belong to:

```text
plugins/gated-sprint/skills/gated-sprint/SKILL.md
```

## Inputs

Accept only the authorized documents, target description, document type,
public guidance, and constraints supplied by the caller. Missing information
must remain missing.

## Diagnostic Sequence

1. Extract and source-label target requirements.
2. Decide the document type: resume, CV, cover letter, recommendation letter,
   scientific research plan or statement, personal statement, or mixed packet.
3. For a specifically authorized industry-resume assessment, consult the
   canonical industry-resume module without duplicating its gates.
4. Review target fit, evidence strength, document structure, formatting,
   clarity, integrity, privacy, and bias.
5. For cited scholarly material, report citation-number, bibliography, and
   inspectable-typography issues separately from evidence strength.
6. For scientific research plans or statements, run the scientific argument
   support gate when requested by the caller; do not import grant-specific
   scoring into ordinary career documents.
7. Classify possible revisions by factual risk and tradeoff.
8. Return diagnostics, bounded suggestions, blocked claims, and missing inputs.

This sequence does not revise files or produce final artifacts.

## Industry Resume Reference

When applicable, use:

```text
plugins/gated-sprint/skills/gated-sprint/references/industry-resume.md
```

Preserve requirement-level counts, evidence bands, gate statuses, and explicit
gap types. Do not replace them with an opaque match percentage or a claim about
a proprietary recruiting system.

## Target Priority

Explicit instructions from a target posting, portal, fellowship call, or
faculty search override generic public guidance. Record the conflict and label
the target instruction as `official requirement` or `user-provided` according
to its source.

## Evidence Labels

Use `official requirement`, `public background`, `user-provided`, `inference`,
`uncertain`, and `missing`. Never guess applicant achievements or missing target
requirements.

## Return Sections

- target fit;
- document structure;
- evidence strength;
- formatting and ATS-relevant hygiene;
- writing clarity;
- integrity, privacy, and bias;
- missing information; and
- human or specialist decisions.

The canonical caller owns any approval, implementation, and release step.
