# Scientific Argument Review Report

Use this local report for the shared
`plugins/review-tools/skills/application-review/references/core/scientific_argument_gate.md`. It extends the existing
revision decision log/change ledger with stable findings; it is not a new memory
database. Keep it under the source-specific access restrictions. The validator
does not grant permission to read a report or its sources.

## Execution and result

```text
python3 Scripts/validate_scientific_argument_review.py current_report.json
python3 Scripts/validate_scientific_argument_review.py current_report.json --previous previous_report.json
```

Both filenames must be explicitly authorized. The CLI opens only those JSON
files. It never resolves source identifiers, searches for documents or earlier
reports, follows URLs, calls models, or writes files. Source identifiers and
versions are opaque labels, not paths. Do not put local paths, file URLs,
credentials, or unapproved private material in the report.

- Exit `0`: internally consistent, including a consistent `REVISION_REQUIRED`
  or `NOT_ASSESSABLE` review. This is not scientific approval or application
  readiness.
- Exit `1`: schema or consistency failure; correct the report and rerun.
- Exit `2`: unreadable/malformed JSON or invalid CLI usage. Duplicate JSON keys,
  non-finite numbers, and invalid UTF-8 are rejected.

When local execution is available, run this check before claiming automated
consistency. In a text-only tool, apply the same requirements and state
`automated consistency validation: NOT RUN`. The conceptual workflow requires
no particular AI provider or runtime.

## Version 1 contract

Every object has exactly the documented fields: unknown fields fail closed.
All fields below are required unless marked optional or nullable. Text fields
must be nonempty strings; list fields must be actual JSON arrays and boolean
fields actual `true`/`false`. IDs and versions use letters, digits, dots,
underscores, or hyphens, starting with a letter or digit. IDs are unique within
their inventory. `schema_version` is the integer `1`.

| Top-level field | Value |
| --- | --- |
| `report_id` | Unique identifier for this assessment, distinct from the previous report |
| `document` | Object described below |
| `review` | Execution and isolation object described below |
| `checks` | Exactly the five program checks and four checks for each declared Aim/project |
| `findings` | Finding objects; empty only when no concern needs recording |
| `readiness` | `READY`, `REVISION_REQUIRED`, or `NOT_ASSESSABLE` |
| `improvement` | Evidence-based comparison with baseline, or explicit statement that none was assessed |
| `uncertainty` | List of remaining uncertainty/risk statements; may be empty |
| `score_scale` | Optional shared quality-scale object, required if any numeric score is used |

`document` contains:

- `id`, `version`: current reviewed source and its version. Version means a
  source version, not an improvement claim.
- `type`: `grant_proposal`, `research_plan`, or `research_statement`. Route by
  function, including eligible career/fellowship documents. Give each eligible
  part of a mixed package its own report. CVs, cover letters, reference letters,
  personal statements, and whole mixed packages are not this schema's types.
- `scope`: exact textual argument scope and relevant exclusions. A figure
  outside this scope does not automatically block textual readiness.
- `aims`: list of `{ "id": "A1", "label": "..." }` objects. Inventory
  every major current project/direction even if the source has no numbered Aims.
  Explicit future horizons can be excluded with an explanation in `scope`.
  Use `[]` only when the inventory itself cannot be assessed; never fabricate
  Aim names for unavailable source text. An empty inventory requires
  `source_coverage_complete: false`, either `execution_complete: false` or an
  `UNAVAILABLE` current primary source, non-`READY` readiness, and a nonempty
  `uncertainty` explanation identifying the unavailable inventory. Keep all
  five program checks, with honest `NOT_ASSESSABLE` ratings where appropriate.
  This exception cannot remove previously declared Aims through `--previous`.
- `sources`: nonempty list of `{ "id": "...", "version": "...", "access":
  "AVAILABLE", "required": true }`. `access` is `AVAILABLE` or `UNAVAILABLE`.
  Source/version pairs are unique. Declare the current primary document as
  required, plus versions cited by retained finding histories. `required`
  identifies sources necessary for this current assessment; historical or
  out-of-scope sources need not be required. Declaring access is not a request
  for the validator to open that source.

`review` contains:

- `execution_complete`, `source_coverage_complete`, `after_final_revision`:
  booleans. A completed initial Phase 1 review may have
  `after_final_revision: false`; this does not claim a proposed repair was made.
  Required unavailable sources prevent complete coverage. Record a new review
  after actual final revisions before making a final-version claim.
- `isolation`: `SOURCE_ONLY` or `CONTEXT_EXPOSED`.
- `isolation_note`: actual Cold Reader exposure, including prior scores,
  history, or author intent if visible. The orchestrator may hold history while
  an isolated Cold Reader receives only source and brief. Shared context does
  not establish independent expertise.
- `route`: nonempty list of actual route and completed-review observations,
  not just filenames said to have been loaded.

## Mandatory checks and evidence

Exact check IDs:

| Level | IDs |
| --- | --- |
| Program | `program.problem`, `program.knowledge_gap`, `program.significance`, `program.primary_goal`, `program.integration_focus` |
| Each Aim/project | `aim.<id>.rationale`, `aim.<id>.significance`, `aim.<id>.expected_knowledge_gain`, `aim.<id>.contribution` |

Every check contains `id`, `rating`, `evidence`, `interpretation`, `unknowns`,
and `consequence`, with optional `score`. `interpretation` states the reviewer
finding, separate from source observation. `unknowns` is a list of unknown
facts, empty when none. `consequence` explains the reader/reviewer implication.

For pure source-access limitations, record a `MINOR` access finding with
`cause: "EVIDENCE"`, the unknown information, and the next authorized access
step. An unavailable source is not evidence of a major document flaw. Multiple
unassessable checks may share one finding listing every affected criterion.
This preserves uncertainty without manufacturing substantive criticism.

`rating` is `EXPLICIT`, `IMPLICIT`, `WEAK`, `MISSING`, or `NOT_ASSESSABLE`.
All mandatory functions are essential. Version 1 intentionally has no extra
conditional checks: record such checks separately. `NOT_APPLICABLE` is never
valid for these mandatory functions, including primary goal and significance.

Every evidence object has exactly:

```json
{
  "source_id": "measurement-program",
  "source_version": "v1",
  "locator": "Program, paragraph 1",
  "kind": "EXCERPT",
  "text": "Separating drift from noise determines whether repeated readings reflect instrument change or random variation."
}
```

Use a section/paragraph or verified page locator. `kind` is `EXCERPT`, `ABSENCE`,
or `UNAVAILABLE`; `text` is respectively a short passage, explicit absence
statement within the reviewed area, or access limitation. Current check
evidence must identify the current primary document. `EXPLICIT`, `IMPLICIT`,
and `WEAK` need excerpts; `MISSING` needs an absence statement. Unavailable
evidence is `NOT_ASSESSABLE`, with the unknown information recorded in
`unknowns`. Every non-explicit check needs a retained active unresolved finding.

For `program.significance` and every `aim.<id>.significance`, also run the
opening significance test in `scientific_argument_gate.md`. Record the opening
and, when applicable, the later supporting passage in the human-readable review
as `EARLY`, `DELAYED`, `MISSING`, or `NOT_ASSESSABLE`. This placement verdict
does not add new machine IDs in schema version 1:

- `EARLY` can support `EXPLICIT` when the significance relationship is sound;
- `DELAYED` maps to `WEAK`, even when a clear reason appears later;
- `MISSING` maps to `MISSING` only when the reason is absent throughout scope;
- `NOT_ASSESSABLE` maps to `NOT_ASSESSABLE` when the opening cannot be read.

For `DELAYED`, cite the later excerpt in `evidence`, state the inspected opening
range in `interpretation`, and retain a finding whose minimum repair moves,
compresses, or previews that supported reason before detail. A generic adjective
inserted at the opening does not satisfy the resolution condition.

The report cannot silently compensate for a failure elsewhere. Readiness is
computed by precedence:

1. An `IMPLICIT`, `WEAK`, or `MISSING` check, or any active unresolved `MAJOR`
   finding: `REVISION_REQUIRED`.
2. Otherwise, any `NOT_ASSESSABLE` check or incomplete execution/required source
   coverage: `NOT_ASSESSABLE`.
3. Otherwise: `READY` within this argument-review scope only.

Mark a source-access uncertainty as such, rather than misclassifying an unknown
as a known major substantive defect. Unresolved `MINOR` concerns can coexist
with supported readiness, but still prevent a maximum affected score.

## Finding and lifecycle objects

Every finding, including a carried or withdrawn one, has these fields:

| Field | Contract |
| --- | --- |
| `id` | Stable finding ID, never reused/remapped to a different concern |
| `origin` | `{ "report_id": "review-1", "document_version": "v1" }` |
| `criteria` | Nonempty unique list of affected canonical check IDs |
| `severity` | `MAJOR` or `MINOR`; major includes blocking argument concerns |
| `status` | One of the six statuses below |
| `disposition` | `ACTIVE` or `WITHDRAWN`; withdrawn does not mean a text repair |
| `evidence` | Original document evidence, retaining origin version and locator |
| `finding`, `reader_consequence` | Specific concern and why it affects the reader |
| `cause` | `EXPLANATION`, `STRUCTURE_PRIORITY`, `EVIDENCE`, or `AUTHOR_DECISION` |
| `minimum_repair` | Concrete passage/function change or author decision; not merely "strengthen motivation" |
| `structural_alternative` | Materially different repair with tradeoff, or `null` |
| `expected_benefit`, `risk` | Benefit and lost nuance/overcorrection risk |
| `assumptions` | List of factual assumptions/missing information, possibly empty |
| `edit_class` | Existing `green`, `yellow`, or `red` classification; no new edit permission |
| `recommendation` | Default recommendation within existing human approval rules |
| `resolution_condition` | Original testable condition for resolving the finding |
| `last_reviewed_version` | Current report's document version; confirms current reassessment |
| `events` | Nonempty append-only lifecycle history |

The six statuses are `OPEN`, `REPAIR_PROPOSED`, `EDITED_PENDING_REVIEW`,
`RESOLVED_VERIFIED`, `DEFERRED`, and `ACCEPTED_RISK`. All except
`RESOLVED_VERIFIED` remain unresolved while disposition is `ACTIVE`. Deferred,
accepted, previously mentioned, and merely edited concerns retain readiness
and score consequences.

Each event has exactly these fields; nullable fields remain present as `null`:

```json
{
  "kind": "CREATED",
  "from_status": null,
  "to_status": "OPEN",
  "document_version": "v1",
  "reason": "The significance relationship is not stated in the current passage.",
  "evidence": null,
  "condition_test": null,
  "replacement_id": null,
  "reopen_trigger": null
}
```

- `CREATED` occurs once, first, from `null` to `OPEN` at the origin version.
  The finding's original evidence records the source observation.
- `STATUS_CHANGE` records a real change between unresolved statuses or reopens
  a verified concern. It cannot produce `RESOLVED_VERIFIED`. Reopening
  `DEFERRED`, `ACCEPTED_RISK`, or `RESOLVED_VERIFIED` requires a nonempty
  `reopen_trigger` explaining the existing policy's trigger. It is not blanket
  permission to reopen a human decision.
- `VERIFIED_REPAIR` is exactly `EDITED_PENDING_REVIEW` to `RESOLVED_VERIFIED`.
  It requires a revised document version, passage excerpt, and `condition_test`
  that applies the original resolution condition to the actual revised text.
  Merely renaming the source while repeating the original evidence fails.
  Current affected checks must also be `EXPLICIT`.
- `WITHDRAWN` explains an original concern shown to be mistaken. Retain the
  unresolved status and set disposition `WITHDRAWN`. Require a supporting
  excerpt and `condition_test` explaining why the original concern/condition
  was mistaken; do not claim a text repair.
- `RECLASSIFIED` does the same for the original concern and links
  `replacement_id` to a distinct retained finding originating at the
  reclassification version. The replacement remains `ACTIVE` (and may later
  be verified resolved). Its own criteria/severity control its effects. This
  records a correction without rewriting the original concern or creating a
  replacement cycle.

Withdrawal/reclassification of a deferred or accepted decision also requires
the recorded `reopen_trigger`; evidence does not silently erase a locked
decision. Withdrawal/reclassification ends that finding's event history. A genuinely new
concern needs a new ID. Decisive event evidence must be an available excerpt
of the primary document at the event version. `condition_test` is otherwise
`null`; `replacement_id` is only used for reclassification; `reopen_trigger`
only for a status change or mistaken-finding disposition. Final
status/disposition must agree with history.

With `--previous`, both reports must independently validate. Retain every
previous finding ID, including resolved/withdrawn history. Preserve its
`origin`, `criteria`, `severity`, `resolution_condition`, original `evidence`,
and original `finding` verbatim. Preserve the old events as an exact prefix;
append current-version events. Newly introduced IDs originate in the current
report/version. A new report ID, polished prose, or human acceptance does not
clear a concern.

Within a carry-forward chain keep document identity, function, declared scope,
and existing Aim/project IDs stable; new Aims may be added with all four checks.
This compact v1 schema does not model retirement of Aims or scope migration.
Do not hide a scope change by dropping the previous-report check. If a redesign
requires retiring an Aim, retain and explicitly review its original functional
role in the inventory until an authorized scope transition has been handled
outside this schema, with all prior concerns still accounted for in the
existing decision log.

## Optional numeric quality scores

If any check is scored, declare `score_scale` as an object with
`direction: "HIGHER_IS_BETTER"` and `anchors`, an object containing exactly
the string keys `"1"` through `"5"`, each with a nonempty definition. Use the
shared gate's quality meanings. The maximum means full support for the
criterion within scope, not universal perfection. No overall aggregate score
is defined. Portfolio strength, risk, voice/tone, and official scales remain
separate dimensions.

A check's optional `score` is:

```json
{
  "value": 5,
  "counterconcern": {
    "checked": true,
    "outcome": "NONE",
    "explanation": "No material counterconcern was found for this criterion after the source and unresolved findings were checked."
  }
}
```

`value` is an integer from 1 to 5 (booleans are not numbers). Every numeric score
requires an excerpt and a completed counterconcern check. Missing or
unassessable criteria receive no score, not zero. `outcome` is `NONE` or
`MATERIAL`; a material concern needs an affected unresolved finding. A 5
requires `EXPLICIT`, `NONE`, and no active unresolved finding affecting that
criterion, including minor/deferred/accepted concerns. Other criteria may
still receive a 5.

## Complete synthetic positive report

This benign measurement example illustrates the data shape, not a scientific
quality benchmark. Its initial review is complete without claiming a revision.

```json
{
  "schema_version": 1,
  "report_id": "measurement-review-1",
  "document": {
    "id": "measurement-program", "version": "v1", "type": "research_statement",
    "scope": "Textual argument of one current measurement project; no visual-quality verdict.",
    "aims": [{"id": "A1", "label": "Separate drift from noise"}],
    "sources": [{"id": "measurement-program", "version": "v1", "access": "AVAILABLE", "required": true}]
  },
  "review": {
    "execution_complete": true, "source_coverage_complete": true, "after_final_revision": false,
    "isolation": "SOURCE_ONLY", "isolation_note": "Cold Reader received only the synthetic source and brief.",
    "route": ["Research-statement route: source-only reconstruction, all program and Aim checks, and calibration completed."]
  },
  "checks": [
    {"id": "program.problem", "rating": "EXPLICIT", "evidence": {"source_id": "measurement-program", "source_version": "v1", "locator": "Program paragraph 1", "kind": "EXCERPT", "text": "Repeated readings combine instrument drift and random noise."}, "interpretation": "The measurement problem is stated.", "unknowns": [], "consequence": "The reader can identify the problem."},
    {"id": "program.knowledge_gap", "rating": "EXPLICIT", "evidence": {"source_id": "measurement-program", "source_version": "v1", "locator": "Program paragraph 1", "kind": "EXCERPT", "text": "The relative drift and noise contributions are unknown."}, "interpretation": "The specific uncertainty is stated.", "unknowns": [], "consequence": "The knowledge gap is identifiable."},
    {"id": "program.significance", "rating": "EXPLICIT", "evidence": {"source_id": "measurement-program", "source_version": "v1", "locator": "Program paragraph 1", "kind": "EXCERPT", "text": "Separating them determines whether repeated readings reflect instrument change or random variation."}, "interpretation": "The unresolved distinction has an interpretive consequence.", "unknowns": [], "consequence": "Fundamental measurement significance is explicit."},
    {"id": "program.primary_goal", "rating": "EXPLICIT", "evidence": {"source_id": "measurement-program", "source_version": "v1", "locator": "Program paragraph 1", "kind": "EXCERPT", "text": "The program aims to explain the sources of variability in repeated readings."}, "interpretation": "One primary objective is stated.", "unknowns": [], "consequence": "The program goal is recoverable."},
    {"id": "program.integration_focus", "rating": "EXPLICIT", "evidence": {"source_id": "measurement-program", "source_version": "v1", "locator": "Program paragraph 2", "kind": "EXCERPT", "text": "The current project separates drift and noise as contributions to that variability."}, "interpretation": "The project serves the primary objective.", "unknowns": [], "consequence": "The shared objective is explicit."},
    {"id": "aim.A1.rationale", "rating": "EXPLICIT", "evidence": {"source_id": "measurement-program", "source_version": "v1", "locator": "Project paragraph 1", "kind": "EXCERPT", "text": "Because drift and noise are confounded, the project estimates their separate contributions."}, "interpretation": "The gap motivates the project.", "unknowns": [], "consequence": "The rationale can be reconstructed."},
    {"id": "aim.A1.significance", "rating": "EXPLICIT", "evidence": {"source_id": "measurement-program", "source_version": "v1", "locator": "Project paragraph 1", "kind": "EXCERPT", "text": "Their separation distinguishes instrument change from random variation."}, "interpretation": "The project addresses a consequential uncertainty.", "unknowns": [], "consequence": "Its importance does not depend on a generic impact adjective."},
    {"id": "aim.A1.expected_knowledge_gain", "rating": "EXPLICIT", "evidence": {"source_id": "measurement-program", "source_version": "v1", "locator": "Project paragraph 2", "kind": "EXCERPT", "text": "The expected knowledge is the relative drift and noise contributions."}, "interpretation": "The expected knowledge gain is stated.", "unknowns": [], "consequence": "The reader can identify what will be learned."},
    {"id": "aim.A1.contribution", "rating": "EXPLICIT", "evidence": {"source_id": "measurement-program", "source_version": "v1", "locator": "Project paragraph 2", "kind": "EXCERPT", "text": "Those contributions explain the sources of variability targeted by the program."}, "interpretation": "The project contribution to the goal is explicit.", "unknowns": [], "consequence": "The project has a clear role in the program."}
  ],
  "findings": [], "readiness": "READY",
  "improvement": "Initial assessment; no baseline comparison.",
  "uncertainty": ["Consistency validation does not establish that the source claims are scientifically correct."]
}
```

Human/semantic review must still verify the inventory, excerpts, reasons,
counterconcerns, actual repairs, and scientific importance. The validator can
reject an unsupported field or contradiction; it cannot prove that a nonempty
explanation is true. Separate source-only behavioral smoke review from these
mechanical invariant checks.
