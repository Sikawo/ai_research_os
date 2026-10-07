# Daily Run Contract

## Objective

Produce a daily report that separates today's newly discovered or materially changed jobs from the current active Tier 1 / Tier 2 portfolio; estimate family quality of life for every Tier 2 or better role; surface unusually strong-fit roles at credible employers that are not yet allowlisted; and prepare application materials for Tier 1 roles with the least possible human interaction.

## Daily sequence

1. Load the reusable framework contracts and deployment configuration through the configured private overlay. Public framework defaults must never contain candidate records or connector bindings.
2. Complete the configured regional search passes before ranking:
   - search every primary region in `search_preferences.yaml` independently on every run;
   - rotate through at least three secondary regions per run;
   - run a nationwide catch-all pass after regional searches;
   - do not stop early because any single region produced enough candidates.
3. Search approved-company career pages and discovery sources using the expanded title and domain families in `search_policy.yaml`. Search title terms and scientific-domain terms both independently and in combination so nonstandard titles are not missed.
4. Also allow provisional discovery of strong-fit roles at credible employers outside the permanent allowlist when the estimated fit is at least the Tier 2 threshold. These candidates must have a live official employer page and receive an employer stability/funding review. Mark them `company_approval_needed`; they may be reported and receive QOL analysis, but do not generate application documents until the user approves the employer.
5. Use LinkedIn and other aggregators only to discover candidates, then confirm every retained role on the official employer career page.
6. Normalize company, title, location, worksite, job ID, posting date, closing date, salary range, official URL, and requirements.
7. Deduplicate into canonical state using normalized company + official job ID, then canonical official URL, then normalized company + title + location as fallback.
8. Compare the role with verified candidate evidence and `fit_rubric.yaml`.
9. Apply hard blockers before routing.
10. Classify:
   - Tier 1: score at or above the configured threshold, all guardrails passed, and employer approved; create the application workspace and run career-document Sprint followed by GatedSprint Phase 1.
   - Tier 2: plausible fit at an approved employer; report the official URL, strengths, gaps, salary, and full economic / educational QOL analysis.
   - Provisional high-fit: estimated Tier 2 or better at a non-allowlisted but credible employer; report fit estimate, employer-stability notes, salary when available, QOL, and ask whether to add the employer to the allowlist.
   - Watchlist: record and include in a weekly summary, not the daily alert.
   - Below threshold: record internally and suppress.
11. For every Tier 2 or better approved role, and every provisional high-fit role, run the quality-of-life assessment using `qol_preferences.yaml`:
   - evaluate configured commute, housing, household, childcare, and education preferences;
   - omit any household category that is not explicitly configured;
   - estimate take-home pay and monthly surplus or deficit at the salary lower bound, midpoint, and upper bound;
   - include food, health care, transportation, parking, tolls, utilities, internet, and other necessities;
   - report economic QOL, educational QOL, major unknowns, and practical cautions.
12. For each approved Tier 1 role, create no more than five morning questions. Ask only about facts, preferences, or high-tradeoff choices that cannot be safely inferred.
13. After the user answers and explicitly authorizes Phase 4, generate application-ready resume and cover-letter files using the existing Application Review OS career-document adapter.
14. Save final outputs through the configured document-storage adapter and return:
   - official application URL;
   - output folder location;
   - filenames;
   - deadline and salary when available;
   - QOL report location;
   - any remaining application-form cautions.
15. Build one canonical `current_active_tier_1_2` snapshot from prior canonical state plus today's state updates. Reverify the official employer page for every otherwise-actionable approved Tier 1 / Tier 2 candidate, and list only roles verified active during this run.
16. Use that same snapshot object for every configured report and notification adapter. Render it after today's changes under `CURRENT ACTIVE TIER 1/2`, including unchanged roles; render `None.` when the set is empty.
17. Never submit the application.

## Daily report layers

Every enabled daily output has three separate layers:

1. Today's discoveries, material changes, alerts, counts, and action-required packets.
2. `PROVISIONAL HIGH-FIT DISCOVERY`, containing credible non-allowlisted employers that meet the configured fit threshold and need company approval.
3. `CURRENT ACTIVE TIER 1/2`, a compact current portfolio snapshot that includes unchanged approved roles.

The current-active snapshot does not change the headline, new-job count, material-change count, Tier alert counts, deduplication state, or approval-packet generation. Sort Tier 1 before Tier 2, then fit score descending, company, and title. Include tier, fit score, company, title, official job ID, location, verified salary when available, workflow status, strongest match, key gap, and official URL.

A role is snapshot-eligible only when it is at an approved employer, currently in scope, currently classified Tier 1 or Tier 2, not rejected, not hard-blocked, not closed or expired, not awaiting first-time official verification, and verified active on its official employer page during the current run.

## QOL source hierarchy

Prefer:

1. official employer posting for salary and worksite;
2. IRS and state or local tax authorities;
3. current rental listings plus current-year HUD FMR / SAFMR as a reference;
4. MIT Living Wage Calculator and official state childcare market-rate studies;
5. official state education report cards and NCES for public-school facts;
6. official school websites for private-school tuition and fees;
7. official transit planners or live routing sources for commute estimates.

Report source dates and distinguish official facts, current listings, benchmarks, and estimates. Do not infer school quality from price alone.

## Question minimization

Do not ask about grammar, wording, ATS keywords, formatting, document length, routine evidence selection, or low-risk edits. Resolve these through the existing workflow.

Ask only about:

- unverified required technical experience;
- relocation or location acceptance;
- salary expectation when required;
- visa or work-authorization wording;
- whether to approve a newly discovered employer;
- which of several real achievements should be emphasized;
- a substantive GatedSprint tradeoff;
- Phase 4 generation authorization.

## Failure behavior

- If an official job page cannot be confirmed, do not classify the role as active.
- If a source cannot be reached, record the company or QOL component as incomplete and continue.
- If reverification of a previously active Tier 1 / Tier 2 role fails or is ambiguous, omit it from the current-run snapshot, report the incomplete check or source failure, and preserve its prior durable state unless a definitive closed or expired result is obtained.
- If a provisional employer cannot be stability-reviewed, report it as incomplete rather than treating it as approved.
- If evidence is missing, ask or mark the requirement as a gap; never fabricate it.
- If commute, rent, childcare, school, tuition, or tax data are unavailable, label the estimate incomplete instead of substituting unsupported values.
- If document generation fails, preserve the completed fit report, QOL report, and question packet and report the failure clearly.
