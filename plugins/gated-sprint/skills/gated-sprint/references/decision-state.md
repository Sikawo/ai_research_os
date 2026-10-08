# Decision state and deterministic validation

Load this reference for `NEGOTIATE`, `RECEIPT`, `IMPLEMENT`, and `RELEASE`, and whenever a diagnostic run must persist or reconcile decisions. The normative machine shape is [`../schemas/gatedsprint-state.schema.json`](../schemas/gatedsprint-state.schema.json). The validator is [`../scripts/validate_gatedsprint_state.py`](../scripts/validate_gatedsprint_state.py).

## What the state proves

The state keeps four questions separate:

1. **Support:** is the proposed content scientifically and factually admissible?
2. **Authorization:** did the user approve this exact proposal on this exact source revision?
3. **Implementation:** did a changed hunk implement an authorized decision or enumerated local fix?
4. **Verification:** did the required checks pass on the exact submission artifact hash?

Approval never changes scientific support. `BLOCKED` and `NEEDS_CONFIRMATION` are support states, not risk colors or user-decision states. A user may choose an admissible Red tradeoff, but user approval cannot legalize unsupported content.

## Files and immutability

A persisted implementation or release run uses four JSON sidecars:

- `gatedsprint-state.json`: versioned run, source, artifact, decision, lock, event, gate-applicability, attestation, and local-fix records.
- `baseline-manifest.json`: immutable input source IDs, hashes, roles, authority flags, and equivalence designations. Optional `observed_after_byte_hash` and `observed_after_text_hash` fields permit a read-only diagnostic check.
- `candidate-manifest.json`: candidate artifact IDs and hashes, relationship to the baseline, format, submission designation, and status.
- `diff-map.json`: every changed hunk classified as `SUBSTANTIVE` and mapped to one decision revision, or `LOCAL_FIX` and mapped to an authorized local-fix record.

Never edit an old record to make a new revision appear valid. Append a new event, source binding, proposal revision, or artifact. A post-verification edit creates a new artifact/hash with `UNVERIFIED` status; the old verified record remains historical.

### Industry-resume analysis sidecar

An industry `RESUME` with `industry_resume.ai_ats_mode=true` also uses the
route-neutral structured analysis sidecar defined by
[`../schemas/industry-resume-analysis.schema.json`](../schemas/industry-resume-analysis.schema.json).
It contains normalized requirements, evidence/provenance, gap classes, audit
results, evaluator failures, artifact references, and a non-opaque dashboard.
Validate it with
[`../scripts/validate_industry_resume_analysis.py`](../scripts/validate_industry_resume_analysis.py).

The analysis sidecar does not grant edit authority. On GatedSprint routes,
substantive proposed repairs still become source-bound decision records in
`gatedsprint-state.json`, and the state binds the sidecar/candidate by artifact
ID and hash before release. Exact bare Sprint uses the same sidecar for
evidence and audits but does not fabricate a GatedSprint approval ledger;
Sprint's own execution authority and change record remain controlling. Thus a
single machine contract serves both routes without collapsing their different
permission models.

## Source and artifact authority

Each source records independent boolean flags for content authority, layout authority, and editable target. `origin=GENERATED_PREVIEW` can never be layout authority. A user-supplied layout reference that is not also content authority requires both `equivalence_status=SAME_VERSION` and an explicit current/same-version designation.

A current content authority likewise needs `version_designation=EXPLICIT_CURRENT` or `SAME_VERSION_CONFIRMED`. For documents, layout authority must be a current user-supplied PDF; a DOCX or generated PDF may be an editable target or qualified preview, but cannot supply final layout proof. Figure routes may use the applicable user-supplied figure medium.

When current-version identity is unresolved, a diagnostic state may have no source flagged as content authority only if the `current_source_authority` gate is explicitly `NOT_ASSESSABLE`; this is surfaced as a warning and dependent judgments remain unavailable. Implementation and release still require a current content authority.

`run.current_source_ids` must exactly match sources marked `is_current`. Decision fingerprints may use the registered byte hash or extracted-text hash. The latter is useful when a decision is anchored to textual meaning while the byte encoding changes.

An artifact uses `DRAFT`, `UNVERIFIED`, or `VERIFIED`. Known filename suffixes and declared formats must agree (`.pdf`/`PDF`, `.docx`/`DOCX`, `.txt`/`TXT`, and `.md` or `.markdown`/`MD`). `VERIFIED` requires a verification record and `ARTIFACT_VERIFIED` event bound to the exact candidate hash. Every implementation result requires an exact `ARTIFACT_CREATED` event that precedes its `DECISION_IMPLEMENTED` event, including for an artifact still marked `DRAFT` or `UNVERIFIED`. For layout-relevant work, the actual artifact must have been inspected and `layout_result` must be `PASS`; a generated preview cannot supply this proof. An actual submission artifact identified as PDF by either its declared format or path suffix is necessarily layout-relevant and cannot opt out by self-declaring the layout gate inapplicable.

## Decision record

The stable identity is `(decision_id, proposal_revision)`, displayed as, for example, `GS-003-r2`. A material change retains the stable ID, increments the revision, receives a new proposal fingerprint, and reciprocally links the revisions with `SUPERSEDES`/`SUPERSEDED_BY`. `SUPERSEDES` always points to a lower revision and `SUPERSEDED_BY` to a higher revision; reverse cycles are invalid, and the latest revision cannot itself be `SUPERSEDED` without a later successor. Revisions are stored in ascending append order and older revisions are `SUPERSEDED`.

A decision records:

- original source ID/fingerprint and append-only `source_bindings`;
- scope, location, anchor, provenance, reason for action, root cause, and downstream symptoms;
- intervention, proposal fingerprint, protected intent, expected reviewer benefit, possible lost nuance, and evidence assumptions;
- orthogonal `change_risk`, `domain_risk`, `strategic_necessity`, `support_status`, `decision_state`, and `source_impact`;
- dependencies, conflicts, conflict resolutions, supersession links, and affected locks;
- a fingerprint-bound accepted tradeoff, when any;
- exact implementation and verification artifact/hash records, when reached.

Conditional rules:

- `SPECIALIST_REVIEW_REQUIRED` needs a specialist concern and safer alternative.
- `BLOCKED` needs the missing/contradictory evidence or integrity reason plus an unblock condition.
- `NEEDS_CONFIRMATION` needs the fact/evidence that must be confirmed. It cannot advance to `APPROVED` until a support-status event first records `SUPPORTED`.
- `APPROVED` and `AUTHORIZED` each require their own event with `authority_kind=USER`; one event cannot also change support or source impact. `AUTHORIZED` requires a preceding `APPROVED` event and an authorization event bound to the current proposal and latest source ID/fingerprint.
- `IMPLEMENTED` requires a mapped diff hunk and exact candidate hash.
- `VERIFIED` requires evidence and a verification event bound to that same hash.

## State transitions

| From | Allowed next states |
|---|---|
| `PROPOSED` | `DISCUSSED`, `APPROVED`, `HELD`, `REJECTED`, `SUPERSEDED` |
| `DISCUSSED` | `APPROVED`, `HELD`, `REJECTED`, `SUPERSEDED` |
| `APPROVED` | `AUTHORIZED`, `HELD`, `REJECTED`, `SUPERSEDED` |
| `AUTHORIZED` | `IMPLEMENTED`, `HELD`, `SUPERSEDED` |
| `IMPLEMENTED` | `VERIFIED`, `SUPERSEDED` |
| `VERIFIED` | `SUPERSEDED` |
| `HELD` | `DISCUSSED`, `APPROVED`, `REJECTED`, `SUPERSEDED` |
| `REJECTED` | `SUPERSEDED` only when a new revision replaces it |
| `SUPERSEDED` | none |

An approve-and-implement instruction may append consecutive `APPROVED` and `AUTHORIZED` events in one turn. It may not skip approval. Events are globally chronological and each decision's state events form a continuous chain beginning with `null → PROPOSED`. The `IMPLEMENTED` and `VERIFIED` transitions must use `DECISION_IMPLEMENTED` and `DECISION_VERIFIED`, respectively; a generic state event cannot impersonate either proof event.

## Source revalidation

The first source binding is `INITIAL`. Each later binding is `SOURCE_REVALIDATED` and identifies the immediately preceding source/fingerprint, the new source/fingerprint, anchor hashes when available, comparison result, actor, timestamp, authority basis, proposal fingerprint, and matching event ID. Binding events must occur in the same strict order as the binding array; equal timestamps do not permit reversed append order. Its `old_anchor_hash` must equal the preceding binding's `new_anchor_hash`, including when the comparison finds changed or obsolete content. Bindings also carry canonical hashes of `protected_intent` and the sorted dependency-reference set. Canonical values use UTF-8 JSON with sorted object keys and compact separators, then the `sha256:<hex>` digest.

Approval may carry to a new draft without a new proposal revision only when all of the following remain materially unchanged: the proposal, protected intent, dependency set, and scoped source text. Record `comparison_result=UNCHANGED`, set `source_impact=UNCHANGED`, and append a matching `SOURCE_REVALIDATED` event. A `REVALIDATION_REQUIRED` result permanently invalidates that exact proposal revision: a later unchanged hop or in-place reapproval cannot revive it, and work continues only through a new revision with a new fingerprint and approval. `OBSOLETE` likewise ends action on that revision.

## Dependencies, conflicts, locks, and local fixes

Authorization requires authorized-or-later dependencies; implementation requires implemented-or-later dependencies. This is replayed at every authorization transition, including reauthorization after a decision was held; a later dependency authorization cannot retroactively validate an earlier transition. Dependency cycles fail validation.

Two conflicting decisions cannot both be active (`AUTHORIZED`, `IMPLEMENTED`, or `VERIFIED`) unless an explicit resolution states `BOTH_COMPATIBLE` with rationale and authority. Event history is replayed, so moving one side to `HELD` later does not erase an earlier invalid period of co-activity. Resolution orientation is relative to the record that owns it: `THIS_SELECTED` selects the owner, `OTHER_SELECTED` selects the referenced decision, and `DEFERRED` requires the owner to be `HELD`. These resolutions do not permit both sides to remain active.

Locks remain separate from “items not to disturb.” A lock records type, scoped anchor, reason, creating authority, source fingerprint, active/released status, and explicit release condition. Creation and release each require exactly one canonical `LOCK_CREATED`/`LOCK_RELEASED` event bound by lock ID, actor, timestamp, and source fingerprint. A decision naming an affected lock cannot be authorized or implemented while that lock is active; event position resolves equal timestamps. A later release does not rewrite an earlier invalid transition, and a lock created later does not retroactively invalidate work completed before its creation.

The local-fix log is limited to `TYPO`, `PUNCTUATION`, `SUBJECT_VERB_AGREEMENT`, `ABBREVIATION_CONSISTENCY`, `FORMATTING_CONSISTENCY`, and `EXACT_DUPLICATE_REMOVAL`. Authorization requires a matching `LOCAL_FIX_AUTHORIZED` event with `authority_kind=USER`, and that event must occur before the exact candidate's `ARTIFACT_CREATED` event even when their timestamps are equal. Mapping is bidirectional: each implemented local hunk must map to an authorized log entry on the same candidate hash, and every hunk claimed by that log entry must exist in the exact candidate diff. Each implemented fix also needs an exact-artifact `PASS` attestation named `local_fix_semantics:<local_fix_id>`, strictly between creation and final verification; an out-of-window record is an error and a later exact-candidate failure cannot be ignored. The validator checks the record, not the semantic judgment. Any change to certainty, causality, novelty, significance, ownership, feasibility, emphasis, or scientific scope needs a substantive decision ID.

## Qualitative attestations

Scripts cannot determine scientific meaning, actual originality, voice, figure comprehension, logical simplicity, whether a fix is truly non-semantic, or cross-format semantic equivalence. Record those judgments as attestations with responsible actor, rubric/check, result, evidence, timestamp, and exact source or artifact hash.

`gate_applicability` records `APPLICABLE`, `NOT_APPLICABLE`, or `NOT_ASSESSABLE` before evaluation. A required applicable gate needs the latest current `PASS` attestation. Diagnostic and implementation attestations must bind a current source and follow the latest revalidation into that source (or the run start when no revalidation occurred). Release attestations must bind the exact candidate and fall after artifact creation but strictly before final artifact verification; an equal or later timestamp is not accepted. Scientific integrity and current-source authority are mandatory for implementation and release. Exact-final-artifact inspection, post-implementation blind review, and tired-reader review are also mandatory for release, and layout verification is mandatory whenever the current artifact is layout-relevant. Those gates cannot be suppressed as `NOT_APPLICABLE`. `NOT_ASSESSABLE` is permitted and warned during diagnosis, but it prevents implementation or release readiness. Release requires an explicit applicability record for each finalization surface, including integrity, authority, motivation, simplicity, voice, salience, visual/citation/format/layout checks, actual-artifact inspection, blind review, and tired-reader review. Inapplicable checks must be named rather than silently omitted.

## Validator CLI

```text
python scripts/validate_gatedsprint_state.py \
  --state gatedsprint-state.json \
  --baseline baseline-manifest.json \
  [--candidate candidate-manifest.json] \
  [--diff-map diff-map.json] \
  --check diagnostic|ready-to-implement|ready-to-release
```

- `diagnostic` checks schema, event/state integrity, source authority/fingerprints, and baseline immutability. Candidate sidecars are unnecessary.
- `ready-to-implement` additionally requires at least one exact, supported, source-current `AUTHORIZED` decision with resolved dependencies, conflicts, and locks.
- `ready-to-release` requires well-formed candidate and diff sidecars, with the current artifact present in the candidate manifest; a verified actual submission artifact; no authorized-but-unimplemented decision; verified current implemented decisions; complete two-way diff authorization; exact hash binding; applicable PASS attestations; and no late edit. Superseded implementation records and their old verified artifacts remain valid append-only history; they are not required to appear in the current candidate manifest or current diff map.

The validator writes one JSON result object to stdout and a concise human summary to stderr, including for malformed UTF-8/JSON and argument errors. Each issue contains `check_id`, `severity`, `affected_decision`, `affected_artifact`, and `explanation`. Exit status is `0` for pass, `1` for failed invariants, and `2` for unreadable/malformed inputs or invocation errors. Warnings do not cause failure.

Passing the validator proves record consistency only. It does not certify the scientific or qualitative judgments recorded in attestations.
