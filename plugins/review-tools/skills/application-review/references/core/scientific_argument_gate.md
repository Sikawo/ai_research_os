# Scientific Argument Gate

## Applicability and authority

Run this shared contract for grant proposals and scientific research plans or
statements, including academic-job, faculty, PI, group-leader, and relevant
fellowship programs. Route by document function, not a keyword in the package.
In a mixed package, review each eligible document separately. Ordinary CVs,
resumes, cover letters, reference/recommendation letters, and personal
statements do not inherit this gate. Manuscript-wide review is unchanged.

This is the common motivation, significance, and focus contract, not a grant
rubric. Career documents do not load the generic grant rubric or the
grant-specific proposal-completeness gate. Grants retain those requirements,
including their background, literature, and structural-completeness checks.
Official criteria, scientific evidence, source access, and human scientific
ownership remain controlling. This gate neither permits new source access nor
authorizes edits.

## Execution order and evidence boundary

1. Resolve authorized sources, document type, target requirements, and human
   constraints. Inventory every major Aim/project, including unnumbered ones;
   distinguish current work from explicitly labeled future horizons.
2. Give the Cold Reader only the current authorized source and applicable
   review brief. Withhold previous scores, author explanations, revision
   history, and external criticism until its first reconstruction is recorded.
   The orchestrator may read authorized decision memory first, but must not
   pass that context into this source-only input. If isolation is unavailable,
   report `CONTEXT_EXPOSED`, not a blind or independent result.
3. Audit required functions before portfolio classification or architecture
   selection. For grants, integrate this audit with the existing early
   completeness check; do not execute it twice through inherited references.
4. Preserve Scientific Model, blind divergence, coherence firewall,
   interestingness, and architecture/reviewer ordering. An initial argument
   defect is a repair priority, not a veto on permitted scientific exploration.
5. Propose concrete repairs and carry forward unresolved findings. Compare
   candidates against Candidate 0 without turning familiarity into superiority.
6. After the last substantive or meaning-affecting revision and final polish,
   rerun the checks on the actual final source version. Phase 1 records an
   initial assessment; it never pretends that a proposed repair was applied.
7. Audit consistency before reporting readiness. When local execution is
   available, run `Scripts/validate_scientific_argument_review.py` on the
   explicit report file, and use `--previous` only for an explicitly authorized
   prior report. In text-only tools apply the same checklist and state
   `automated consistency validation: NOT RUN`.

Record document/version, route taken, available sources, checks actually
completed, isolation limitations, and unresolved findings. A list of loaded
filenames alone is not execution evidence. A shared-context role is not a
statistically independent expert. The Tired Brilliant Outsider Test remains a
separate summary-surface test: body text cannot rescue that pass. Simulated
10-second/60-second/five-minute judgments are not measured human recall.

## Five review responsibilities

| Responsibility | Question | Required output |
| --- | --- | --- |
| Motivation / Significance Reviewer | Why does this gap matter, and what remains unresolved if the work is not done? | Program and Aim-level chain, source evidence or absence, consequence |
| Focus / Program Coherence Reviewer | What is the primary goal, and what does each Aim contribute? | One-sentence reconstructed goal, Aim roles/priorities, competing goals or unknown author decisions |
| Cold Reader | What can a new reader actually recover from this document? | Reconstructed goal/significance, unsupported inferences, missing links, isolation status |
| Revision Architect | What smallest supported change would resolve the finding? | Candidate 0, minimum repair, materially different alternative only when useful, benefit and sacrifice |
| Calibration Auditor | Do evidence, unresolved findings, scores, and readiness agree? | Contradictions, coverage limits, criterion-specific maximum-score checks |

Keep existing specialist review. These responsibilities do not require five
agents, a particular vendor, or paid model calls. Do not impersonate a real
reviewer or fabricate criticism to populate a table. Strong positive controls
may pass.

## Required argument functions

For the program assess `problem`, `knowledge_gap`, `significance`,
`primary_goal`, and `integration_focus`. For every declared current Aim/project assess
`rationale`, `significance`, `expected_knowledge_gain`, and `contribution`. Use the exact
machine identifiers and evidence fields in
`plugins/review-tools/skills/application-review/assets/templates/scientific_argument_review_template.md`.

Test the chain: problem -> unresolved gap -> why the gap matters -> knowledge
gained -> contribution to the primary goal. Ask what important uncertainty or
limitation persists without the work. A method being available, a question
being unstudied, or a theme sounding important does not establish this chain.

### Opening significance test

Run a separate placement pass before the full read. Inspect the opening
paragraph, or the first compact rhetorical unit when formatting does not use
paragraphs, of the program overview, every current Aim/project or other major
scientific section, and each major argumentative paragraph that introduces a
new question, direction, or consequential claim. Before methods, technical
detail, or extended background, ask whether a new reader can answer:

- What is significant here?
- Why does it matter?
- Why should we care about resolving this gap or completing this Aim?

Record `EARLY`, `DELAYED`, `MISSING`, or `NOT_ASSESSABLE` for each opening, with
the opening locator and any later passage that supplies the significance. Later
text may prove that significance exists, but it does not rescue its rhetorical
placement. Map `DELAYED` to `WEAK` for the affected canonical
`program.significance` or `aim.<id>.significance` check, retain an unresolved
finding, and require `REVISION_REQUIRED`; use `MISSING` only when the reason is
absent throughout the reviewed scope. The check evidence may quote the later
passage, while its interpretation identifies the opening range inspected and
the reader consequence of encountering detail first.

Do not enforce a literal first-sentence formula or repeat generic impact claims
in every paragraph. A methods/detail paragraph that introduces no new argument
does not need its own significance sentence. An opening passes when the
significance is recoverable at the point the reader needs it, including through
a clear heading or an immediately preceding transition that the section
explicitly carries forward.
For a delayed but supported point, prefer moving, compressing, or previewing the
existing evidence-backed reason before technical detail. Do not invent broader
impact, inflate urgency, or add boilerplate merely to place a claim earlier.

Separate direct scientific impact, enabling impact, and qualified longer-term
impact. Concrete fundamental-science importance is sufficient; do not add
unsupported clinical or societal promises. Conditional target-specific impact
requirements remain separate from the universal checks.

Shared tools or topics do not themselves prove a shared objective. Conversely,
complementary independent Aims can serve one program; do not force a serial
dependency, single experimental system, or arbitrary reduction in Aim count.
An explicitly labeled future horizon is not automatically an immediate scope
commitment. If the primary goal is unknown, identify the author decision rather
than inventing a preferred research identity.

For each function report `EXPLICIT`, `IMPLICIT`, `WEAK`, `MISSING`, or
`NOT_ASSESSABLE`. The nine mandatory function types cannot be waived with
`NOT_APPLICABLE`; use that label only for conditional checks outside this
contract, with a reason. Evidence includes source identifier, section/paragraph
or verified page, and a short excerpt or explicit absence/unavailability
statement. Separate source observation, interpretation, and unknowns. Do not
infer visual quality when figures or rendered pages are unavailable.

## Readiness and scoring

Keep these separate: current argument readiness, review/source completeness,
change from baseline, remaining uncertainty, and criterion-specific scores.

| Readiness | Condition |
| --- | --- |
| `REVISION_REQUIRED` | An essential function is `IMPLICIT`, `WEAK`, or `MISSING`, or an unresolved major/blocking argument concern remains |
| `NOT_ASSESSABLE` | No known substantive failure, but an essential function or required coverage cannot be assessed |
| `READY` | All required functions and coverage are complete and supported, with no unresolved major/blocking argument concern |

A known failure takes precedence over incomplete assessment; disclose both.
`READY` applies only to this argument scope, not hiring/funding probability,
official submission compliance, scientific truth, or global perfection. Other
specialist, integrity, visual, and compliance verdicts remain separate. Missing
figures outside the declared textual scope do not automatically fail textual
readiness. A valid negative review can pass the consistency validator.

Do not average away a failed essential function. Improvement from an earlier
draft does not establish adequacy. Overall before/after merit scores are not
required for eligible documents; show evidence-based criterion changes and
readiness instead. Existing voice/tone scores and official target scales remain
separate dimensions and do not override this gate.

Optional argument-quality scores use higher-is-better anchors:

- 1: present evidence is substantively inadequate for the required function;
- 2: the function is weak;
- 3: the function is implicit or only partly supported;
- 4: explicit and supported, with a material concern remaining;
- 5: explicit and fully supported within the reviewed criterion and scope.

Missing/unavailable evidence receives no numeric score. Every maximum needs
source evidence and an explicit search for material counterconcerns. An
unresolved concern affecting that criterion prevents its maximum, even if
deferred or accepted. Unrelated criteria may remain strong. Never require all
5s to finish, or mechanically cap sound work to appear skeptical. Portfolio
`5 = central strength` is not a perfect quality score; risk scales have their
own stated direction and must not be averaged with quality.

## Constructive repairs and resolution

Every major finding needs a stable ID, source location/evidence or absence,
severity, affected criterion, reader consequence, cause category, minimum
supported repair, benefit, risk/lost nuance, assumptions or missing information,
edit class, default recommendation, and a testable resolution condition. Add a
structural alternative only when materially different. Cause categories are
explanation, structure/prioritization, evidence, or unresolved author decision.

"Strengthen motivation" and "tighten focus" are not complete repairs. Identify
the missing relationship and the passage/function that must communicate it.
Use existing evidence; if evidence or author priority is missing, give the
smallest decision question with options and tradeoffs, not invented claims,
citations, achievements, experiments, or intent. Preserve Candidate 0 and
state what should not be overcorrected.

For a placement finding, name the exact opening and the later supported passage,
then propose the smallest move, compression, or preview that lets the reader
recover the reason before detail. The resolution condition must require a fresh
opening-only read; copying an unsupported "important" or "innovative" sentence
to the first line is not a verified repair.

For eligible scientific documents, this rule overrides the inherited numeric
candidate quota in `architecture_candidate_engine.md` and workflow entrypoints:
retain Candidate 0, propose the supported minimum repair when needed, and add
materially distinct alternatives only when useful. Do not generate alternatives
to reach a fixed count or invent a repair for an already sufficient argument.
Other document types retain their existing candidate-generation rules.

Use the existing revision decision log/change ledger with stable IDs and
`OPEN`, `REPAIR_PROPOSED`, `EDITED_PENDING_REVIEW`, `RESOLVED_VERIFIED`,
`DEFERRED`, or `ACCEPTED_RISK`. Apply `change_memory_policy.md`: known advice
must not disappear merely because it was previously given. Verify actual
passage changes against the original resolution condition; filenames, prose
polish, and author agreement do not resolve a concern. Evidence-based
withdrawal/reclassification of a mistaken finding must be recorded distinctly
from a successful text repair. Retain the history, affected criteria, and
consequences; do not remap an ID or lower severity silently to unlock a score.

Sprint retains its existing edit permissions and change budgets. GatedSprint
Phase 1 produces proposals only; approved substantive edits and final source
files remain Phase 4-only. Analysis can continue with `REVISION_REQUIRED`, but
the final report must retain the failure and the next repair/decision. This
readiness gate does not create another application-edit approval ceremony.

## Report and validator limits

Use `plugins/review-tools/skills/application-review/assets/templates/scientific_argument_review_template.md`.
Keep structured reports as authorized local review artifacts and log only
necessary persistent findings through the existing memory policy. Do not
create a new database, duplicate status system, or automatic external upload.

The local validator checks declared coverage, schema, lifecycle evidence, and
logical consistency; it cannot prove that an excerpt supports an interpretation,
that the inventory includes every real Aim, or that the science matters. A
reviewer must inspect those semantic claims. Source-only synthetic smoke tests
are distinct from executable invariant tests and do not establish real-world
model accuracy. Human scientific judgment remains primary.
