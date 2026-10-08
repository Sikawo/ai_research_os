# Figures, visual coverage, and layout authority

Load this reference when the artifact contains figures, visual models, captions, or a layout request, or during release of a formatted document.

## Register authority first

Record separately:

- `content_authority`;
- `layout_authority`;
- `editable_target`;
- content/version equivalence among files;
- which artifact the user calls current, final, or submitted.

| Files | Content authority | Layout authority |
|---|---|---|
| Current/final PDF only | PDF | PDF |
| DOCX only | DOCX | `NONE / NOT_ASSESSABLE`; generated render is a proxy |
| DOCX plus explicitly current, same-version, content-equivalent user PDF | DOCX for editing; either for content verification | user PDF |
| User identifies a non-equivalent PDF as current/final | PDF; reconcile before using DOCX as editable target | current/final PDF |
| DOCX is newer than a non-equivalent PDF | DOCX | `NONE / NOT_ASSESSABLE`; PDF is historical only |
| Current/equivalence status unresolved | `UNRESOLVED` | `NONE / NOT_ASSESSABLE` |

Text equivalence alone does not establish that a PDF is current. Never silently blend content from one version with layout from another. If authority cannot be resolved, continue content review only where safe and label layout not assessable.

A tool-generated PDF is non-authoritative unless verified against the user's actual export. Do not spend diagnostic time fixing proxy-only pagination, line breaks, or figure positions. Render only when layout is relevant, after layout-affecting edits, or for final verification.

## Program-to-surface coverage

Create an internal matrix whose rows are the program-defining concepts/Aims/pillars and whose columns include title, headings, designated overview surface, Figure 1, other figures, captions, and closing significance surface. Mark each cell `EXPLICIT`, `IMPLICIT`, `ABSENT`, or `INTENTIONALLY_OMITTED`.

Flag:

- a major pillar absent from all dominant surfaces;
- visual area or hierarchy that misrepresents conceptual importance;
- a prose-heavy pillar with no retrievable visual/textual overview presence;
- established evidence, interpretation, and future hypothesis shown without a visible status distinction.

A prior omission of a program-defining branch is a regression class, not a
universal requirement that every figure contain every branch.

## Figure 1 role test

Classify Figure 1 before judging completeness:

- program overview;
- central mechanism/model;
- anchor evidence;
- another explicitly justified role.

If Figure 1 is the designated program overview, every major program branch must appear at the correct evidentiary status. If it is not an overview, do not force every Aim into it. Instead determine whether another explicitly designated visual or textual surface integrates the program.

## Reader tests

### Designated-overview reconstruction

Using only the designated overview surface, ask an adjacent tired reader to identify the applicable items:

- core discovery or prior limitation;
- organizing future question;
- major future branches;
- primary importance;
- what is established versus proposed.

The overview may be textual. Full-program reconstruction from every figure is not required.

### Non-overview figure test

For each data/evidence/mechanism figure, ask whether the reader can identify:

- the figure's question/role;
- the exact supported conclusion;
- evidence/interpretation/hypothesis status;
- relationship to the program;
- visual reading order.

Also inspect label size at final size, contrast, ambiguous arrows/colors, caption burden, panel order, callouts, clipping, and page balance. Do not impose cosmetic rules such as one figure per page or one figure per Aim without an official constraint.

## Release rule

Layout can be `VERIFIED` only on the exact current submission artifact. A stale PDF or proxy cannot verify a newer editable source. Any layout-affecting edit creates a new `UNVERIFIED` candidate and requires another export/render and inspection.
