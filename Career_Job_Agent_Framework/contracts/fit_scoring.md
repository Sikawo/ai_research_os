# Fit Scoring Contract

## Purpose

Score verified, active job postings against authorized candidate evidence without inventing missing experience.

## Recommended scoring dimensions

- scientific domain fit;
- technical and assay fit;
- drug-discovery or translational fit;
- seniority fit;
- required-qualification coverage;
- location and compensation fit;
- visa or work-authorization feasibility;
- employer stability.

Weights and thresholds are deployment-specific and belong in the private `fit_rubric.yaml`.

## Tier routing

A deployment may calibrate thresholds to achieve a desired review cadence, but must not lower standards silently.

Recommended routing:

- Tier 1: strong enough to justify application-document preparation;
- Tier 2: plausible enough to justify notification and quality-of-life analysis;
- Watchlist: interesting but missing one or more central requirements;
- Suppressed: below the configured notification threshold.

## Tier 1 guardrails

A numeric threshold alone is insufficient. Tier 1 should also require:

- no confirmed hard blocker;
- official career-page verification;
- active application status;
- no explicit sponsorship prohibition when sponsorship is required;
- meaningful overlap with the role's central scientific function, not only peripheral methods;
- enough verified evidence to produce a truthful targeted resume;
- a realistic seniority range.

## Hard blockers

Examples include:

- closed or expired posting;
- official page unavailable or unverified;
- explicit no-sponsorship language when sponsorship is required;
- mandatory credential or recency condition the candidate does not meet;
- location explicitly rejected by the user;
- role center dominated by an unverified specialty;
- legal or regulatory eligibility mismatch.

A hard blocker may retain a high scientific score for analysis, but it must prevent automatic Tier 1 document generation.

## Calibration

Track daily candidate counts, Tier 1 frequency, Tier 2 frequency, user Apply/Maybe/Skip decisions, recruiter responses, and interview conversion. Adjust thresholds only through a dated configuration change. Do not automatically chase a target number by progressively weakening fit standards.
