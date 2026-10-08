# Review rubrics and hard gates

Use these rubrics for `DIAGNOSE` and re-run the applicable parts on the actual implemented artifact during `IMPLEMENT`/`RELEASE`. Determine applicability from [deliverable-routing.md](deliverable-routing.md) before evaluating.

## 1. Result vocabulary

- Gate applicability: `APPLICABLE`, `NOT_APPLICABLE`, `NOT_ASSESSABLE`
- Major-unit opening result: `PASS`, `LATE`, `GENERIC`, `AMBIGUOUS`, `ABSENT`, `NOT_APPLICABLE`, `NOT_ASSESSABLE`
- Diagnostic readiness: `READY`, `NOT_READY`, `NOT_ASSESSABLE`
- Release result: `VERIFIED`, `UNVERIFIED`, `NOT_ASSESSABLE`
- Recommended content action: `Keep`, `Reframe`, `Move`, `Compress`, `Remove`, `Needs evidence`, `Needs user decision`

`NOT_APPLICABLE` means the document/unit registry excludes the check. `NOT_ASSESSABLE` means the check would apply but a required source, authority, criterion, rendering, or evidence item is missing.

## 2. Hard-gate registry

Run hard gates before scores.

| Gate | Applies to | Failure consequence |
|---|---|---|
| Scientific/factual integrity | Every route | Affected change is `support_status=BLOCKED`; artifact is `NOT_READY` if misleading as submitted |
| Current-source/content authority | Every route | Affected scope is `NOT_ASSESSABLE`; no implementation or release |
| Opening-surface motivation/significance/value | Units made applicable by the document registry and matrix below | `NOT_READY` |
| Supported claim/originality boundary | Central claims and novelty/originality judgments | Unsupported change is `BLOCKED`; affected judgment is `NOT_ASSESSABLE` where verification is required |
| Logical simplicity | Substantive prose documents and integrated edit bundles | Material failure is `NOT_READY` |
| Cumulative edit-set simplicity | Cover letters and interacting multi-edit bundles | Bundle cannot be recommended or released |
| Visual role/coverage | Documents with figures or a designated visual overview | `NOT_READY` only when failure is material to the declared role/overview |
| Authorization/source match | Implementation | No edit |
| Exact final artifact and applicable format | Release | `UNVERIFIED` or `NOT_ASSESSABLE`, never `VERIFIED` |

No numeric score can reverse a gate failure.

For an industry `RESUME` with `industry_resume.ai_ats_mode=true`, load
[industry-resume.md](industry-resume.md) and use its Gate 0-8 vocabulary in
addition to the global results above:

| Gate | Required result surface | Blocking condition |
|---|---|---|
| 0 — JD decomposition | Stable requirement IDs with required/preferred/contextual priority and preserved qualifiers | Missing or materially distorted screenable requirement |
| 1 — Eligibility | `met`, `probably_met_but_not_explicit`, `partial`, or `not_met`, bound to evidence | Evidence-free qualification presented as met |
| 2 — Evidence matrix | Evidence level 0-4, visibility, provenance, and explicit gap class | Unsupported or provenance-free claim |
| 3 — Semantic alignment | Exact terms, defensible synonyms, and candidate-native scientific wording | Keyword insertion or experience-equivalence inflation |
| 4 — ATS parse | Gate status `PASS`, `PASS_WITH_WARNINGS`, or `FAIL`, with raw chronology/reading-order checks | Critical loss, broken chronology, or identity/contact failure |
| 5 — Qualification simulation | Per requirement `MET`, `PARTIAL`, or `NOT_FOUND` using current resume only | Hidden candidate evidence used, or a requirement marked `MET` without explicit current-resume evidence |
| 6 — Recruiter/top-third | `STRONG`, `ACCEPTABLE`, or `WEAK` with explicit early-fit findings | Material target-identity mismatch or unusable skim surface |
| 7 — Hiring manager | `STRONG`, `ACCEPTABLE`, or `WEAK` with claim-level credibility findings | Material unsupported depth, ownership, leadership, or genericization |
| 8 — Integrity | `PASS`, `PASS_WITH_WARNINGS`, or `FAIL` with finding IDs | Any unsupported factual claim, metric, seniority, ownership, or direct experience |

A true gap is disclosed, not cosmetically converted to a pass. Counts by
required/preferred priority and evidence-level band are useful diagnostics;
there is no opaque aggregate match percentage and no proprietary-system score.

## 3. Motivation-and-Significance-First Gate

### Major units

A major unit is a reader-recognizable entry block such as the overall document/program; a major accomplishment or conceptual-advance section; the future-program overview; each Aim/project; a cover-letter research identity/discovery or future-program block; a recommendation-letter evaluative block; or another headed/functionally equivalent scientific block. It does not mean every paragraph.

### Opening-surface retrieval matrix

Use only the heading plus opening one to three sentences. Record the reader's actual reconstruction, not an assertion that the information exists elsewhere.

| Unit | Required for `PASS` | Conditional function |
|---|---|---|
| Overall document/program opening | Motivating problem/unmet need and primary stakes/value | Applicant anchor delta and why the future program is needed when the document function requires them |
| Major accomplishment/conceptual advance | Prior limitation, supported applicant contribution/delta, and resulting scientific consequence | Broader application only when central and supported |
| Future-program overview | Unresolved question, why resolving it matters, and organizing logic | Relationship to completed work when trajectory is an official/strategic criterion |
| Aim/project | Specific unanswered question and consequence/knowledge gain | Why it follows from a preceding argumentative unit only where such a unit exists |
| Cover-letter document opening | Applicant identity/direction, central value proposition, and one primary reason to care | Target fit only when the opening is responsible for it |
| Cover-letter research block | Research identity/contribution or future direction and one main reason to care | Fit, independence, or leadership only when the block is responsible for it |
| Recommendation-letter evaluative block | Candidate quality, concrete evidence, and why that quality matters to the recommendation | Comparative judgment and trajectory when supported/relevant |
| Overview visual/caption | Designated overview role, central program logic, and applicable major branches | Evidence-versus-hypothesis status for each represented element |

Originality/delta and sequence are conditional, not universal. Supporting paragraphs that are not entry units do not undergo this gate.

### Failure rules

Fail or qualify the gate when:

- significance appears only at the end (`LATE`);
- motivation is recoverable only from methods, body detail, or user explanation (`LATE` or `ABSENT`);
- technique arrives before problem and payoff;
- significance is interchangeable, application-list-like, or untethered to a specific knowledge consequence (`GENERIC`);
- only a domain insider can infer the value (`AMBIGUOUS`);
- the heading/opening promises a different point from the section; or
- a required function is missing (`ABSENT`).

For scientific problem/advance/program/Aim units, the reader must be able to state in one short sentence both the motivating problem/question and why resolving it matters. For other units, use the row-specific function instead of forcing a scientific-problem template. Body text cannot rescue the opening result.

### Repair order and anti-formula test

Prefer:

`move existing motivation/value forward → replace an ineffective opening → compress supporting detail → delete competing material → add only the missing proposition`

Explain why addition is needed when reordering, replacement, compression, or deletion could solve the problem. Do not add repetitive "This is important because" formulas or generic application lists.

## 4. Importance, originality, and claim strength

### Importance

Identify:

- the important unresolved problem;
- what cannot yet be explained, predicted, distinguished, or manipulated;
- the scientific decision, reader, system, or population affected;
- whether the primary value is conceptual, explanatory, clinical, technological, or enabling; and
- one primary value versus secondary consequences.

Do not equate importance with the number of applications mentioned.
Do not force clinical or public-health relevance when conceptual scientific significance is the supported primary value.

### Originality

Use the comparison:

`closest prior account → unresolved limitation → applicant's demonstrated delta → future-program delta`

Separate originality of completed accomplishments, current conceptual advance, independent future program, communication of originality, and verified global novelty. `First`, `unique`, and `unprecedented` require adequate verification; otherwise report `Not assessable without literature verification` rather than inventing a straw-man prior account.

### Strongest-defensible-claim comparison

For each core claim compare:

- safest wording;
- strongest evidence-supported wording;
- recommended wording;
- overstatement risk; and
- understatement cost.

State established findings directly. Reserve conditional language for interpretation, prediction, future work, or actual uncertainty. The preferred wording is the most direct fully supported version, not the rhetorically strongest version.

## 5. Logical Simplicity and Organization Gate

This gate is independent of grammar, natural English, tone, and skim performance.

### Document level

Test whether the reader can reconstruct the document-appropriate chain, often:

`problem → prior limitation → applicant contribution → future question → expected value`

Identify one primary message; normally no more than two secondary consequences on dominant surfaces; the role of each major section; and any unnecessary branches, duplicated rationales, or delayed premises.

### Paragraph/cluster level

Ask:

- What is the single dominant job?
- Does topic/motivation precede supporting detail?
- Does every sentence advance that job?
- Do caveats/rebuttals interrupt the main line before it is understood?
- Can the unit be summarized accurately in one short sentence?
- Does its first sentence prepare the reader for its last?

Technical density and necessary nuance are not failures; loss of hierarchy is.

### Baseline and cumulative regression

Compare proposed and integrated revisions with the current baseline, using a blind comparison when practical. A revision fails if it:

- makes the main point harder to state;
- adds more independent concepts than it resolves;
- requires more rereading without essential scientific benefit;
- turns a direct sentence into a defensive chain;
- increases length/qualification without changing reviewer understanding; or
- makes paragraph roles less distinct.

When added complexity is necessary for accuracy, keep a plain-language top layer with technical support beneath it. For cover letters, test both each edit and the fully integrated bundle; local rationales do not excuse cumulative clutter.

## 6. Tired-reader protocol v2

Run two independent components.

### A. Salience and reconstruction

- **10 seconds:** inspect title, headings, opening/closing sentences, designated overview/Figure 1, and dominant captions.
- **60 seconds:** reconstruct strongest accomplishment, central advance, future question, primary importance, and program integration.
- **Five minutes later:** record one retained idea, one likely confusion, and one forgotten component.

Do not use detailed body text to rescue a failed dominant-surface result.

### B. Sequential comprehension and friction

Read in order and mark where:

- motivation arrives after detail;
- rereading is required;
- a premise is delayed;
- a paragraph changes jobs;
- defensive explanation obscures the thesis;
- an acronym/new term interrupts understanding; or
- the document branches without hierarchy.

Passing A does not compensate for failing B, or vice versa.

## 7. Natural prose and proportionate tone

This is a reader-impression review, never an AI-authorship detector.

### Natural prose and structure

Look for formulaic/interchangeable significance language, repeated transitions, over-smooth abstraction, identical sentence rhythm, artificial Aim/paragraph symmetry, vague praise, inflated adjectives, consultant/application boilerplate, and manuscript-introduction style where direct application argument is needed.

### Confident, proportionate tone

Look for pre-emptive rebuttals, repeated caveats, apology-like language, repeated explanations of what was not done, generic feasibility reassurance, defensive chains that weaken supported claims, and self-congratulatory promotion. One necessary limitation stated once with its consequence or test is not a defect.

Target natural English in the voice of a careful, confident senior scientist: natural but not casual, formal but not stiff, confident but not arrogant, concise but not under-explained, specific, evidence-based, reviewer-facing, and field-accurate. Preserve meaningful applicant terminology, causal logic, and justified caution.

## 8. Evidence-backed scores

For `DIAGNOSE/FULL` on a substantive prose document, evaluate every applicable dimension; for `FOCUSED`, only the declared scope. During `RELEASE`, re-run every dimension that applied to the implemented document on the actual candidate. Use role-specific pass/fail checks for CV and resume list entries, standalone figures, and non-prose units. Ordinary resume bullets do not acquire scientific-narrative motivation, originality, or Aim requirements; enhanced industry resumes use their Gates 0-8 instead.

Dimensions:

1. natural prose and structure;
2. confident, proportionate tone;
3. importance/motivation visibility;
4. originality visibility; and
5. logical simplicity and organization.

| Score | Normative anchor |
|---|---|
| 1 | Function is absent, misleading, or seriously obstructs understanding. |
| 2 | Function is weak, late, or generic; a material reader problem remains. |
| 3 | Function is recoverable but needs inference, rereading, or localized restructuring. |
| 4 | Function is clear/effective; only a bounded non-material weakness remains. |
| 5 | Function is immediately retrievable, specific, proportionate, and has no material counterevidence on applicable surfaces. |

For every score report:

- score and short label;
- positive evidence;
- strongest counterevidence;
- confidence (`HIGH`, `MEDIUM`, or `LOW`);
- reader consequence; and
- smallest sufficient action or `Keep`.

Use `HIGH` confidence only with the exact authoritative artifact, relevant evidence/criteria, and convergent reviewers; `MEDIUM` with adequate evidence but interpretive/reviewer uncertainty; `LOW` with incomplete artifact, evidence, audience, or rendering. Use `NOT_ASSESSABLE` rather than a score when the needed source/authority is missing.

Dimension constraints:

- Natural prose 5 does not imply motivation or importance.
- Importance/motivation 5 requires a passed opening retrieval and specific consequence.
- Originality 5 requires a supported comparison/delta, not unverified global novelty.
- Logical simplicity 5 requires reconstructable hierarchy and no material cumulative regression.
- Tone 5 requires direct supported claims plus justified caution, not maximal certainty.
- A failed applicable opening-surface motivation/significance gate prohibits 5 for importance/motivation, originality visibility, and logical simplicity/structure where those judgments depend on that surface; readiness remains `NOT_READY` even if prose or tone is 5.
- Any relevant failed placement, reconstruction, evidence, or simplicity gate prohibits a 5 in the affected dimension.
- Score the actual current artifact, not a predicted revision.

Scores are diagnostic triggers, not optimization targets or evidence of external reviewer success. They measure communication visibility/execution in the current artifact, not the objective importance or novelty of the science. Do not average scores into a selection prediction, hide reviewer disagreement, or optimize toward 5 through cosmetic edits. Treat material external-expert feedback that contradicts an internal score as calibration evidence and a regression-case candidate.

## 9. Readiness

- `READY`: every applicable hard gate passes for the actual current artifact.
- `NOT_READY`: at least one material, actionable hard gate fails.
- `NOT_ASSESSABLE`: a source, evidence item, authority, or artifact required for the judgment is unavailable.

Readiness is a workflow judgment, not a selection prediction. `VERIFIED` is reserved for the exact release candidate after finalization and is stricter than `READY`.

## 10. Supporting rubrics

### Claim–evidence–inference

Audit likely reader inference from wording **and placement**, including headings, arrows, captions, adjacency, and visual hierarchy. A literally cautious sentence can still overstate. Never use a review or related paper as evidence for a mechanism it did not test. Classify citation-dependent claims as supported, plausible but unverified, needs reference, wording exceeds source, mismatched reference, or not assessable.

### Independence and robustness

Assess intellectual ownership, contribution ownership, programmatic differentiation, operational portability, and trainee-project potential separately. Distinguish thematic coherence from serial dependence: a coherent program should still yield interpretable knowledge when an upstream hypothesis or perturbation is null. Do not treat collaboration itself as weakness.

### Cross-document package

Define one anchor proposition, one primary significance statement, up to two secondary consequences, each document's role, facts/terms that must match, and details that belong in only one document. Each document remains minimally understandable alone; remove paragraph-level duplication while preserving deliberate repetition of the central hook.

### Page-budget test

Ask: if this paragraph, figure, or detail were removed, which official criterion, central story function, evidence boundary, or necessary specialist credibility would materially weaken? If none, consider removal, compression, relocation, or appendix treatment.

### Relevant reviewer functions

Use only needed lenses. In a full/high-stakes review, normally include a domain specialist, adjacent scientist, accomplishments/independence or target-equivalent reviewer, tired decision-maker, and factual/compliance reviewer. Outsider comprehension governs dominant surfaces; specialist nuance is preserved immediately underneath; target criteria govern relevance; page cost breaks close ties.
