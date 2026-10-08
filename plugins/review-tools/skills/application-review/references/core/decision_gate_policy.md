# Decision Gate Policy

## Purpose

Convert candidate comparison into implementation decisions.

## Decision Classes

- `auto-applied`: safe enough to implement during Sprint.
- `human-decision proposal`: high-upside or high-risk change requiring human
  approval before implementation.
- `deliberately not changed`: considered but rejected or deferred.
- `blocked`: cannot proceed without missing evidence, source access, or a
  human-only strategic choice.

## GatedSprint Decision Classes

For `GatedSprint`, classify every substantive proposed change before any file
edits:

- Green: clearly beneficial, low-risk, meaning-preserving.
- Yellow: likely beneficial but changes emphasis, interpretation, structure, or
  tradeoffs.
- Red: factually admissible but high-risk, such as a supported central-claim or
  hypothesis reframing, project removal, integration of authorized evidence,
  or budget/staffing change.

`BLOCKED` is not a fourth color and is not an approvable Red proposal.
Missing-evidence, invented-fact, unsupported-causality, unsupported-novelty,
unverified status/ownership, and evidence outside the authorized source packet
remain `support_status=BLOCKED`. They cannot advance by user approval in either
GatedSprint or self-driving Sprint.

Record domain risk separately from this color: a superficially logical proposal
that may be wrong, awkward, overstated, or field-naive is
`domain_risk=SPECIALIST_REVIEW_REQUIRED` and must name the specialist concern
and at least one safer alternative.

Assign each proposal a default recommendation: Adopt, Modify, Discuss, Hold, or
Reject. Even Green changes remain proposals until Phase 4 approval.

Do not overload risk color with authority or admissibility. Record these axes
independently for every material proposal:

- stable ID plus `proposal_revision` (for example `GS-003-r2`);
- `change_risk`: `GREEN`, `YELLOW`, or `RED` (displayed as Green, Yellow, or
  Red where helpful);
- `domain_risk`: `NONE`, `SPECIALIST_REVIEW_REQUIRED`, or `CLEARED`;
- `strategic_necessity`: `ESSENTIAL`, `HELPFUL`, or `OPTIONAL`;
- `support_status`: `SUPPORTED`, `NEEDS_CONFIRMATION`, or `BLOCKED`;
- `decision_state`: `PROPOSED`, `DISCUSSED`, `APPROVED`, `AUTHORIZED`,
  `IMPLEMENTED`, `VERIFIED`, `HELD`, `REJECTED`, or `SUPERSEDED`; and
- `source_impact`: `CURRENT`, `UNCHANGED`, `REVALIDATION_REQUIRED`, or
  `OBSOLETE`.

A Red proposal may be supported and ultimately authorized; a Green proposal is
not automatically approved. `NEEDS_CONFIRMATION` and `BLOCKED` cannot advance
to approval or implementation until evidence changes support status to
`SUPPORTED`. User approval cannot make unsupported content admissible.

For backward compatibility, a target overlay or legacy template that displays
`Domain-risk` means `domain_risk=SPECIALIST_REVIEW_REQUIRED`; it must also
assign an ordinary Green/Yellow/Red `change_risk`. Do not persist Domain-risk
as a fourth change-risk enum.

For GatedSprint, no change class grants edit authority. Every model-generated
textual change requires its own stable Phase 1 decision ID and explicit user
approval of that ID. This includes grammar, natural English, clarity,
concision, flow, tone, reviewer readability, and final polish. If it was not on
the agenda, do not edit it.

Do not launder multiple or unspecified changes through a broad decision label.
`Polish section`, `clarify the opening`, `address comments`, and `normalize
references` are not implementation-ready. Split them into exact, independently
decidable operations. Track Changes and comments authorize only their exact
expressed change. They do not imply permission for adjacent rewriting.

## Orthogonal Scientific Status

Keep scientific status independent from edit/action status:

```text
Scientific: Safe Baseline / Target / Speculative Seed / Reject
Edit/action risk: Green / Yellow / Red
Domain risk: None / Specialist review required / Cleared
```

`Target + Red` is valid: the idea may be scientifically strong while requiring
human approval before any document change. `Speculative Seed` is never silently
integrated. `Reject` is not implementation input. Human Position (`LOCKED`,
`PREFERRED`, `OPEN`, `DISLIKED`, `REJECTED_UNLESS_NEW_EVIDENCE`) and Change
Budget maturity further constrain action but do not rewrite the scientific
verdict.

## Human-Decision Proposal Format

Each GatedSprint textual proposal must include:

- stable decision ID;
- affected document and exact location;
- provenance: `model-proposed`, `user-requested`, `source-comment`, or
  `mechanical-preserving`;
- exact current wording;
- exact proposed wording;
- current issue and proposed operation;
- recommendation: strongly recommend, recommend, optional, or not recommended;
- benefit;
- risk;
- what would be sacrificed;
- whether approval is needed before implementation.
- scientific status and firewall verdict when scientifically substantive;
- scientific insight magnitude and recommended current edit magnitude;
- maturity, Human Position, and any reopen trigger.

An approval is bounded to those recorded fields. Similar meaning is not
authorization for alternate wording. When an approved proposal changes during
negotiation, update the exact proposed wording and obtain an unambiguous user
decision before implementation.

Also record the bound source ID/fingerprint, proposal fingerprint, protected
intent, dependencies, conflicts, affected locks, evidence assumptions, and
expected page/figure effect. A material proposal change increments
`proposal_revision`, supersedes the old revision, and requires new approval.

Approval and implementation authorization are separate user-originated events.
An explicit approve-and-implement instruction may append `APPROVED` and then
`AUTHORIZED` consecutively in one turn; it may not skip either event. Phase 3
is then a no-edit receipt rather than a redundant confirmation. Reconfirm only
if wording, source fingerprint, protected intent, evidence, dependencies,
conflicts, locks, or feasible implementation changed materially.

## Source Revalidation and Decision History

When a materially revised source becomes current, compare the scoped anchor,
protected intent, proposal fingerprint, and dependency set. Carry a decision
forward only when all remain materially unchanged and record the new source
binding as `UNCHANGED`. `REVALIDATION_REQUIRED` permanently invalidates that
proposal revision for implementation; create a new revision rather than
reviving it with later approval. `OBSOLETE` ends action on that revision.

Preserve held, rejected, superseded, obsolete, and accepted-tradeoff history.
Do not reintroduce any of it as a new recommendation merely because the
conversation persisted or a new file name appeared. Finding lifecycle remains
separate from proposal/implementation lifecycle: a finding is resolved only by
reviewing the actual revised passage against its recorded resolution condition.

## Dependencies, Conflicts, and Locks

Authorization requires authorized-or-later dependencies; implementation
requires implemented-or-later dependencies. Do not authorize cyclic dependency
sets. Conflicting decisions cannot both remain active without an explicit
evidence-backed compatibility resolution. An active user lock blocks affected
authorization/implementation until its recorded release condition is met.

If one authorized decision becomes blocked, independent compatible decisions
may proceed only when the candidate remains coherent and is not described as
final. Record skipped and blocked revisions explicitly.

## Phase 4 Allowed-Change Set

Build the allowed-change set only from explicitly approved decision IDs. Record
the ID/revision, current source fingerprint, document/location, provenance,
exact baseline wording, exact approved wording, proposal fingerprint, protected
intent, dependencies, and user authorization. Exclude held, rejected,
ambiguous, stale, unsupported, unlisted, and broad-label items.

After implementation, compare the final text to the frozen baseline and map
every textual delta to one allowed ID. Revert any unmapped model-generated
delta. The final report must list implemented approved IDs, approved IDs not
implemented with reasons, held/rejected IDs, and whether any textual delta
remains outside the allowed set.

Purely non-semantic fixes may use an explicitly authorized, enumerated local-fix
bundle limited to typos, punctuation, subject-verb agreement, abbreviation
consistency, formatting consistency, and exact-duplicate removal. Any change to
certainty, causality, novelty, significance, ownership, feasibility, emphasis,
or scientific scope requires a substantive decision revision. Deterministic
validation can prove that records and mappings are complete, not that a change
is scientifically or semantically harmless.

Legal forward transitions are:

- `PROPOSED` -> `DISCUSSED`, `APPROVED`, `HELD`, `REJECTED`, or `SUPERSEDED`;
- `DISCUSSED` -> `APPROVED`, `HELD`, `REJECTED`, or `SUPERSEDED`;
- `APPROVED` -> `AUTHORIZED`, `HELD`, `REJECTED`, or `SUPERSEDED`;
- `AUTHORIZED` -> `IMPLEMENTED`, `HELD`, or `SUPERSEDED`;
- `IMPLEMENTED` -> `VERIFIED` or `SUPERSEDED`;
- `VERIFIED` -> `SUPERSEDED`;
- `HELD` -> `DISCUSSED`, `APPROVED`, `REJECTED`, or `SUPERSEDED`; and
- `REJECTED` -> `SUPERSEDED` only when a new revision replaces it.

Never rewrite prior events to make a later action legal. A post-verification
edit creates a new artifact/hash and verification record.

## Default If Unsure

Keep the current scientific meaning, avoid unverified claims, and route the
change to human-decision proposals.
