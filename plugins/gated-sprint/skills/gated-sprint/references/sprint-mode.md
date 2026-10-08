# Self-driving Sprint mode

Use this module only for an exact, otherwise-unqualified `Sprint` invocation or
when the user explicitly asks for the established self-driving Sprint. It is
implemented by the same installed skill so that one current authority governs
shared safety and quality rules, but it is not approval-gated GatedSprint.

## Route and authority

Record `SPRINT_SELF_DRIVING/FULL/STANDARD/<document_type>` unless the user
explicitly narrows scope or adds `TRIAGE`. Resolve the application/document
adapter and current source before analysis. Current user instruction, current
official requirements, the explicitly designated latest source, and authorized
evidence retain the question-specific authority defined in
[core-invariants.md](core-invariants.md).

Do not create a GatedSprint Phase 1 packet, wait for decision-ID approval, or
claim that a GatedSprint decision ledger exists merely because this skill was
selected. If the user explicitly requests GatedSprint, staged approval, or a
GatedSprint phase, leave this mode and use the approval-gated route.

For a routed industry `RESUME` with `industry_resume.ai_ats_mode=true`, load
[industry-resume.md](industry-resume.md). Its evidence and Gates 0-8 contract
is shared with GatedSprint; only the execution policy differs. With the mode
disabled or omitted, preserve the legacy resume path.

## Self-driving cycle

1. Register the current source, content/layout/editable-target authority, user
   locks, official constraints, and document type.
2. Run a source-bounded cold reconstruction before consulting stale assistant
   suggestions or old scores.
3. Apply the Motivation-and-Significance-First, strongest-supported-claim,
   logical-simplicity, cumulative-edit, and applicable figure/layout gates in
   [review-rubrics.md](review-rubrics.md).
4. Compare the unchanged baseline, the smallest sufficient supported repair,
   and only materially useful alternatives. The baseline may win.
5. Automatically implement only supported, meaning-preserving changes within
   existing Sprint auto-edit authority. Keep admissible high-impact choices as
   human-decision proposals. Classify missing-evidence, invented-fact,
   unsupported-causality, unsupported-novelty, and unresolved ownership/status
   changes as `BLOCKED`; neither Red classification nor user preference makes
   them admissible.
6. Test the fully integrated candidate against the baseline with a blind reader
   when available. If true isolation is unavailable, run a bounded
   source-only reconstruction and disclose `CONTEXT_EXPOSED`.
7. Create a new candidate and preserve the baseline. When a working parent is
   designated, follow [file-versioning.md](file-versioning.md) for collision,
   lock/conflict, companion-format, archival, and partial-failure behavior.
8. Inspect the actual candidate. Load [figures-and-layout.md](figures-and-layout.md)
   and [finalization.md](finalization.md) when those concerns apply. A generated
   preview does not become layout authority, and a later edit invalidates
   verification.

For the enhanced industry-resume route, the cycle above is concretized as:
decompose the JD (Gate 0), determine eligibility and evidence without
fabrication (Gates 1-2), align defensible terminology (Gate 3), draft and run
the bounded revision passes, then audit the exact candidate for parsing,
current-resume-only qualification visibility, top-third/recruiter fit,
hiring-manager credibility, and integrity (Gates 4-8). Automatically repair
only supported resume or positioning gaps. Preserve true gaps, stop on a
blocking integrity failure, and rerun every gate affected by a changed
candidate; do not continue stylistic rewrites after the functional gates pass.

## Output

Return a concise record of:

- route, current source, authorities, and exclusions;
- the primary reader problem and why it matters;
- baseline-versus-candidate simplicity and retrieval results;
- automatically implemented supported changes;
- high-impact admissible proposals requiring a human decision;
- `BLOCKED` or `NOT_ASSESSABLE` items and missing evidence;
- exact candidate identity, folder-promotion state, and artifact verification
  state.

For an enhanced industry resume, also return the structured analysis artifact,
gate-status dashboard, required/preferred coverage counts, evidence-level
counts, critical missing requirement IDs, and explicit gap classes. Do not
publish an opaque overall match percentage.

Self-driving means the safe cycle can continue without a GatedSprint approval
stop. It never means that scientific integrity, source authority, locks,
versioning safety, or exact-artifact verification may be bypassed.
