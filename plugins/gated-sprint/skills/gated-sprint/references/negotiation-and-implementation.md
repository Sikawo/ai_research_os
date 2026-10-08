# Negotiation, receipt, and implementation

Load this reference for `NEGOTIATE`, `RECEIPT`, and `IMPLEMENT`. Also load [decision-state.md](decision-state.md). Load the relevant document rubric and [figures-and-layout.md](figures-and-layout.md) only when affected.

## NEGOTIATE

Use the current proposal revision, source binding, dependencies, and evidence. Do not rerun the whole diagnostic unless the user supplies a new source, new evidence, or a material objection.

For each discussed decision:

1. state the root reviewer problem and expected reader consequence;
2. state the proposed intervention, protected intent, and real tradeoff;
3. resolve dependencies/conflicts with other decisions;
4. record `APPROVED`, `HELD`, `REJECTED`, or a new proposal revision;
5. record implementation authorization separately unless the same user message clearly grants both.

If the user selects a supported but non-recommended option after one clear warning, record `accepted_tradeoff` bound to the proposal/source fingerprints. Do not repeat it without new evidence or a material revision.

A materially changed proposal increments `proposal_revision`, receives a new fingerprint, and supersedes the prior record. Approval does not carry automatically. A user cannot approve a change whose `support_status` is `NEEDS_CONFIRMATION` or `BLOCKED`.

## RECEIPT (Phase 3)

This is a no-edit implementation preflight, not a routine second approval gate. Report concisely:

- exact authorized decision IDs/revisions;
- current source and fingerprint;
- protected intent and active locks;
- dependencies/conflicts and compatible subset;
- files/artifacts to be created or changed;
- when managed working files are in scope: the working parent, folder-level naming authority, logical family stem, current root version group, proposed version token, candidate path, companion formats, and predecessor archive plan;
- expected content/layout effects;
- anything that now prevents faithful implementation.

Proceed directly to `IMPLEMENT` when the user already authorized implementation and all checks match. Return to negotiation/revalidation only when the proposal, source, evidence, dependency set, or feasible implementation changed materially.

## IMPLEMENT

Before editing, require:

- exact current source registered and matched;
- each substantive decision `decision_state=AUTHORIZED` and `support_status=SUPPORTED`;
- `source_impact` not `REVALIDATION_REQUIRED` or `OBSOLETE`;
- all dependencies satisfied and no authorized conflicts;
- a declared editable target and output path;
- when the output is a managed working file, a resolved working parent/current version group and a collision-free name under [file-versioning.md](file-versioning.md);
- an enumerated local-fix bundle if local fixes are authorized.

If any requirement fails, do not edit that scope. Independent authorized decisions may proceed only when the result remains coherent and is not misleadingly labeled final.

### Editing rules

- Preserve the authoritative input; create a new version.
- For a managed working family, create the candidate without overwriting the current root version, verify the candidate, then move only the superseded version group to `previous/`. If current-version identity is ambiguous or an archive collision exists, leave every file in place and stop for resolution.
- This promotion establishes the candidate only as the **working-current** version. It remains `UNVERIFIED` for submission until the exact artifact passes `RELEASE`; report folder-current and release status separately.
- Apply only the authorized proposal revision. Do not substitute a seemingly better alternative silently.
- Map every substantive diff hunk to one authorized decision revision.
- Map every local hunk to the authorized local-fix log.
- Treat changes to certainty, causality, novelty, significance, ownership, feasibility, emphasis, or scientific scope as substantive.
- Preserve applicant-owned voice and strong passages marked `keep`.
- If implementation reveals a new substantive problem, stop that change and create a new `PROPOSED` decision; do not smuggle it into grammar cleanup.

### Enhanced industry-resume implementation

For a routed `RESUME` with `industry_resume.ai_ats_mode=true`, load
[industry-resume.md](industry-resume.md) and apply only authorized, evidence-
supported repairs. A `RESUME_GAP` or `POSITIONING_GAP` may be repaired only
within the recorded claim ceiling and provenance; a `TRUE_GAP` must remain
visible and must not be rewritten into apparent qualification. Validate the
structured analysis sidecar after each material update.

Gate 5 is an isolated current-resume-only simulation. Do not pass candidate
facts, source CV text, evidence excerpts, earlier drafts, or hidden reviewer
context into it. If implementation changes the current resume, rerun Gate 5
and every other affected Gate 4-8 audit against the exact new candidate.
Malformed evaluator output, exhausted bounded retries, or an unavailable
required audit is visible failure or `NOT_ASSESSABLE`, never a silent pass.

### Integrated regression check

After composing all authorized edits, compare the full candidate with the baseline. Re-run the applicable why-first, logical-simplicity, cumulative-edit, scientific-integrity, voice/tone, cross-document, and visual checks. Individually valid edits do not pass if the bundle weakens the central hierarchy.

For an enhanced industry resume, also rerun the applicable Gate 0-8 checks,
confirm claim provenance, and compare required/preferred coverage counts,
critical missing IDs, top-third identity, parse order, and integrity against
the baseline. Stop bounded revision once the functional gates pass.

For a cover letter, explicitly compare primary message, paragraph jobs, concept branches, acronym load, qualifier load, and first-pass reconstruction against the simple baseline.

### Implementation output

Return:

- output artifact path(s);
- for managed working files, the working parent, family stem/token, promoted current path(s), and archived predecessor path(s); if promotion did not complete, report the candidate and unchanged current paths explicitly;
- implemented, skipped, and blocked decision revisions;
- concise semantic diff/change log;
- local-fix log;
- unresolved limitations;
- candidate artifact hash/status;
- checks run and failures;
- next step: further negotiation or `RELEASE`.

The enhanced industry-resume output also names the validated structured
analysis artifact, gate-status dashboard, gap-class changes, and any audit
failure. It must not claim to reproduce a proprietary screening product or
reduce the decision to an opaque match percentage.

Do not call an implemented candidate `VERIFIED`; that status belongs to exact-artifact release verification.
