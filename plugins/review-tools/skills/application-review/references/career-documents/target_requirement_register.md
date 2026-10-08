# Target Requirement Register

## Purpose

Before reviewing or revising a career document, `Sprint` must extract the target
requirements and record them in a structured register.

## Sources

Allowed sources include:

- job ad;
- fellowship call;
- faculty posting;
- postdoc inquiry;
- user-provided target description;
- official application portal instructions;
- explicit user instructions.

Do not browse or infer hidden requirements unless the user requests research
into the target. Do not read protected application content unless explicitly
authorized.

## Extraction Fields

Record:

- target title;
- organization, lab, department, or program;
- document types requested;
- required qualifications;
- preferred qualifications;
- required materials;
- formatting or submission rules;
- deadline-sensitive requirements;
- skills and keywords;
- evidence the applicant should provide;
- disallowed or discouraged content;
- ambiguous requirements;
- missing information.

For an enabled industry-resume AI/ATS route, use the canonical
`JobRequirement` contract in
`plugins/gated-sprint/skills/gated-sprint/references/industry-resume.md`. In
addition to the human-readable fields above, record a stable requirement ID,
original and normalized wording, category, `required` / `preferred` /
`contextual` priority, screenability, concepts, exact terms, conservative
synonyms, expected evidence kinds, and compound-parent/facet identity.
Preserve important qualifiers and split only independently screenable facets;
do not reduce compound requirements to keyword atoms.

## Requirement Labels

Use:

- `must-have` for explicit requirements;
- `preferred` for explicit preferences;
- `contextual` for mission, audience, or role-fit signals;
- `formatting` for document limits and submission rules;
- `unknown` when the target is underspecified.

## Conflict Rule

When target instructions conflict with public career guidance summary guidance:

1. Follow the target instruction.
2. Record the conflict.
3. Explain the implication in the review report or change report.

## Minimum Register

If the user has not provided a full posting, create a minimal register from the
available target description and mark missing fields as `missing`. Ask only when
the missing information blocks safe review or revision.

For the enhanced industry-resume route, absence of an authorized job
description or target requirements prevents creation of the enhanced sidecar.
Record dependent applicability as `NOT_ASSESSABLE` in the shared workflow
state; it does not authorize inferred or generic requirements. Ordinary legacy
resume work does not require the enhanced register when `ai_ats_mode=false`.
