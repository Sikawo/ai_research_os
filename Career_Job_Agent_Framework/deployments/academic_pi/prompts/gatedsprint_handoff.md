# Build an Academic GatedSprint Handoff

Create a schema-valid, evidence-backed handoff for one user-selected canonical
role. Do not draft application prose in this step, and do not submit anything.

## Preconditions

- Require `verified_open` or `verified_reopened`, a non-terminal lifecycle, a
  non-stale verification timestamp, and a currently verified official URL.
- Use the stored evaluation and authorized private evidence ledger.
- Preserve gaps, blockers, uncertainty, broad-search status, required documents,
  and reference-letter policy.
- Never add facts that are not present in the posting or candidate evidence.

## Output

Produce an object conforming to `gatedsprint_handoff.schema.json` with:

- verified job identity (`job.canonical_job_id`) and deadline;
- normalized role (`search.normalized_role_class`), independence evidence,
  declared search scope, and document
  requirements;
- fit score, tier, strongest matches, meaningful gaps, blockers, and
  uncertainty;
- evidence references with strength labels; and
- current application status and existing-material references.

Set `submission_authorized` to `false`. Academic GatedSprint may prepare or
revise materials after this handoff, but only the human may approve and submit
an application.

If a Tier 1/Tier 2 handoff or another positive fit claim has no authorized
evidence reference, stop instead of generating a claim-bearing handoff. An
explicitly unauthorized evidence reference must never cross this boundary.
