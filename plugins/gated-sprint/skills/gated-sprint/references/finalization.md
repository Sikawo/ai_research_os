# Finalization and release

Load for `RELEASE`, and after `IMPLEMENT` when the user asks for the exact submission-ready artifact. Also load [decision-state.md](decision-state.md), the relevant deliverable rubric, and [figures-and-layout.md](figures-and-layout.md) when formatted artifacts or figures exist.

## Workflow installation and authority audits

When the release target is GatedSprint itself rather than an application artifact, use exactly one lifecycle status:

- `SPEC_ONLY`: only an implementation contract exists;
- `BUILT_NOT_INSTALLED`: a complete validated staging artifact exists outside an active skill location;
- `INSTALLED_NOT_ACTIVATED`: the skill is installed, but active project authority still points to the legacy workflow;
- `ACTIVATED_UNVERIFIED`: project authority points to v2, but the unqualified fresh-task authority test has not passed;
- `MIGRATED`: installation and project authority are active and both fresh-task smoke tests passed;
- `FAILED`: a required build, validation, installation, authority, or smoke-test step failed.

Do not collapse `INSTALLED_NOT_ACTIVATED` to `INSTALLED`. Installing files does not supersede a project instruction that still declares the old standalone workflow authoritative. During this compatibility period, require explicit `$gated-sprint` invocation and provide the exact project-instruction patch/manual step:

```text
GATEDSPRINT V2 AUTHORITY
When the user invokes GatedSprint, exact bare Sprint, or an equivalent full-workflow request, use the installed $gated-sprint skill as the authoritative workflow specification. Exact bare Sprint follows the skill's self-driving Sprint route; it is not converted into approval-gated GatedSprint. `sources/GatedSprint_Standalone_Instructions.md` is retained as legacy reference material and MUST NOT override the active v2 skill. Current user instructions, the explicitly designated latest draft or final artifact, and the active GatedSprint decision ledger override older drafts, legacy workflow text, and prior assistant recommendations. If the v2 skill is unavailable, disclose that fact rather than silently substituting the legacy workflow.
```

An explicit `$gated-sprint` fresh-task run proves installation only. To claim `MIGRATED`, also run a separate fresh task in the target project with an unqualified prompt such as `Run GatedSprint Phase 1 on the attached fixture. Do not edit it.` and confirm that it selects v2 without being named. Retain task ID, timestamp, exact prompt, skill version/hash, active-authority result, and observations for both tests. If the environment cannot run the second test, stop at `ACTIVATED_UNVERIFIED`.

## Entry conditions

Register:

- approved content baseline and manifest;
- exact editable source, if any;
- exact candidate artifact and hash;
- official constraints and whether they are current;
- content/layout authority;
- allowed remaining correction scope.
- when a managed working file will be promoted: the working parent, naming authority, logical family/current root version group, intended version token, companion-format membership, and collision-free archive destinations.

Without the exact candidate or required authoritative constraints, report `NOT_ASSESSABLE`/`UNVERIFIED`; never infer `VERIFIED` from an editable source or planned fix.

For a routed industry `RESUME` with `industry_resume.ai_ats_mode=true`, also
register the normalized job requirements, exact structured analysis sidecar,
and their hashes. Load [industry-resume.md](industry-resume.md). A legacy resume
with the mode disabled or omitted retains the legacy release contract.

## Release sequence

1. Compare the candidate with the approved baseline.
2. Identify every textual and visual difference.
3. Map substantive hunks to authorized decision revisions and local hunks to the approved local-fix log.
4. Reject or resolve unmapped changes.
5. Recheck scientific/factual status, certainty, causality, novelty, ownership, publication status, citations, and cross-document consistency.
6. Check acronym first use, term consistency, punctuation, agreement, accidental duplication, headings, numbering, captions, and cross-references.
7. Check page/font/word/file-size and other official constraints when authoritative information is available.
8. Inspect the exact final PDF/submission artifact at final size for clipping, page order, figure placement, caption separation, whitespace balance, and legibility.
9. Run a fresh blind opening-surface/reconstruction pass and the sequential tired-reader pass.
10. Run logical-simplicity and cumulative-edit regression on the complete candidate.
11. Validate the state, baseline/candidate manifests, event log, diff map, and qualitative attestations.
12. Set the exact candidate hash to `VERIFIED` only if every applicable hard gate passes.
13. Reconcile release status with folder state under [file-versioning.md](file-versioning.md). If the exact candidate was already promoted as the working-current artifact during `IMPLEMENT`, verify it in place and do not repeat the archive move. If `RELEASE` creates a new candidate or the candidate remains staged, promote it only after the exact artifact passes the applicable release gates. Never overwrite an archive entry. If promotion fails or current identity is ambiguous, preserve all files, report the partial state, and do not describe the folder as clean.

For the enhanced industry-resume route, `VERIFIED` additionally requires:

- the exact sidecar passes `validate_industry_resume_analysis.py`;
- Gate 4 validates the exact candidate's parse order and critical-text
  preservation (including real extraction when PDF or DOCX bytes exist);
- Gate 5 is rerun with only that current resume plus normalized requirements;
- Gates 6-7 pass or expose bounded, non-blocking warnings;
- Gate 8 has no unsupported factual claim, metric, seniority, ownership, or
  direct-experience assertion; and
- the dashboard reports counts and critical IDs without an opaque headline
  match percentage or a claim of proprietary screening-system equivalence.

An enabled required audit that is malformed, unavailable, or exhausted after
the bounded retry policy prevents release. A visible `TRUE_GAP` alone does not
authorize invention and does not become a hidden pass.

Scores cannot override a failed release gate. `VERIFIED` means this exact artifact passed the declared checks; it does not predict selection or external reviewer agreement.

## Late edits

Any post-verification change creates a new candidate and hash with `artifact_status=UNVERIFIED`. Preserve the prior verified artifact and record. Re-run at least:

- exact diff and authorization mapping;
- affected dependencies and scientific/factual checks;
- mechanical checks;
- export/render and layout inspection when layout can change;
- broader blind/retrieval checks when the edit changes a central term, acronym, Aim, figure, claim, citation, status, or ownership statement.

Do not call a one-word or acronym edit harmless automatically. A late acronym
addition that changes meaning is a regression pattern for this rule.

## Release output

Report:

- exact artifact path, hash, and status (`VERIFIED`, `UNVERIFIED`, or `NOT_ASSESSABLE`);
- for managed working files, the family stem/token, exact promoted path(s), exact archived predecessor path(s), and any unresolved duplicate-current state;
- folder-current status separately from exact-artifact release status, including an explicit warning when the root working version remains `UNVERIFIED`;
- content and layout authorities;
- checks completed and evidence/attestations;
- authorized decisions present;
- unmapped or unresolved differences;
- official-constraint limitations;
- any remaining user action.

For an enhanced industry resume, also report the validated sidecar path/hash,
Gates 0-8, required/preferred coverage counts, evidence-level bands, critical
missing requirement IDs, all three gap classes, and any evaluator failure.
