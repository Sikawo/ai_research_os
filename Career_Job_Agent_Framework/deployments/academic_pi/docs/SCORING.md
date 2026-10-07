# Academic Fit Scoring

Academic evaluation answers separate questions. A single opaque number cannot
represent whether the role is real, independent, scientifically suitable,
eligible, or worthwhile.

## Separate layers

Always retain these layers independently:

- **Scientific fit:** candidate-program and department-search alignment.
- **Independence and stage:** whether the role supports the targeted career
  stage and an independent program.
- **Opportunity quality:** tenure, funding structure, startup, space, protected
  time, teaching, facilities, contract, compensation, and sponsorship.
- **QOL/preferences:** private geography, household, commute, country, partner,
  visa, and purchasing-power considerations.
- **Eligibility/blockers:** explicit constraints that can prevent routing.
- **Confidence:** strength and completeness of evidence for each conclusion.

Unknown opportunity or QOL information remains unknown; it is not silently
converted into a penalty.

## Default scientific-fit rubric

| Dimension | Points |
|---|---:|
| Scientific program fit | 30 |
| Department search fit | 20 |
| Independence and career-stage fit | 15 |
| Method or model-system relevance | 10 |
| Strategic research-environment fit | 10 |
| Evidence of candidate distinctiveness | 10 |
| Translational or collaborative fit | 5 |

Private overrides may change weights and thresholds. They must remain explicit,
versioned, and explainable.

## Broad-search rule

Never penalize a genuinely broad faculty search merely because the advertisement
does not repeat a candidate's specialty terms. For a call covering all areas of
biology or another broad scope, evaluate whether the candidate could credibly
strengthen the declared department or program with a coherent independent
research program.

Keyword absence in a broad call is not negative evidence. An explicit exclusion
or incompatible scope may still be a gap or blocker.

## Evidence discipline

Every major positive match must cite authorized candidate evidence. Use these
strength labels:

- strong direct evidence;
- credible adjacent evidence;
- uncertain; and
- no evidence.

Adjacent evidence must not be rewritten as direct experience. Major gaps and
uncertainty must be explicit. Missing evidence should lower confidence before it
is turned into a claim.

## Blockers and tiering

A hard blocker is independent of the raw fit score. Examples include a clearly
non-independent role, elapsed fixed deadline, unmet explicit citizenship rule,
excluded rank, or a privately configured hard geographic exclusion.

Default thresholds are:

- Tier 1: fit at least 80, no blocker, and sufficient official verification;
- Tier 2: fit at least 68, no blocker, and manageable gaps;
- Watchlist: fit at least 55 or material ambiguity/incomplete evidence;
- Blocked: explicit blocker, while preserving the raw fit score; and
- Below threshold: retained only when configured, with a reason.

Never promote roles simply to fill a report.

## Rescoring and overrides

Changing the scoring rubric or candidate profile may trigger an explicit rescore
of active jobs. A rescore:

- does not create a new discovery;
- records score and tier movement as `evaluation_change`;
- remains distinct from changes in the posting; and
- preserves the prior score when the state backend supports history.

Human overrides to tier, interest, independence, blockers, fit notes, or target
priority include value, reason, timestamp, and `source = human`. Automation does
not silently overwrite an override unless the human clears it or a defined
safety condition such as verified expiration applies.
