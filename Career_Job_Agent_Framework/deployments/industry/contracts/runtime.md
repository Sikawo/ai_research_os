# Daily Career Job Agent Runtime Contract

Run once each morning in the user's local time zone.

## Daily sequence

1. Read approved-company, search, fit-rubric, question-policy, and output-location configuration through the deployment's private overlay.
2. Complete the configured regional search passes before ranking. Do not stop early because any single region produced enough candidates.
3. Search discovery sources using both title-family and domain-family queries. Search them independently and in combination so nonstandard titles such as Founding Scientist, Staff Scientist, Investigator, and Senior Research Scientist are not missed.
4. Search approved companies normally. In addition, surface provisional high-fit roles at credible non-allowlisted employers when estimated fit is at least Tier 2, the official employer page is live, and an employer-stability review can be performed. Mark these `company_approval_needed`; do not generate application documents until the user approves the employer.
5. Verify every newly discovered candidate on a live official company or employer career page. Do not retain an unverified candidate as active.
6. Normalize company, job ID, title, location, official URL, dates, salary, and sponsorship wording.
7. Deduplicate against the configured canonical state adapter using normalized company + official job ID, canonical official URL, then normalized company + title + location.
8. Evaluate fit only against authorized candidate evidence. Missing evidence receives no credit.
9. Record new roles and the run summary through the configured state adapter.
10. Save a concise report through the configured report adapter and notify the user even when no qualified roles were found today.
11. Tier 2: report fit, strengths, gaps, official URL, and QOL.
12. Provisional high-fit: report estimated fit, strengths, gaps, salary when available, employer-stability notes, QOL, and ask whether to approve the employer.
13. Tier 1: create the target requirement register and initial resume/cover-letter drafts, run the existing career-document Sprint and GatedSprint Phase 1, save the packet under `Needs Answers`, and ask no more than five blocking questions with recommended defaults.
14. Independently of today's alert set, load every canonical role that is otherwise actionable and currently Tier 1 or Tier 2 at an approved employer. Reverify each role on its official employer page during this run.
15. Build one deduplicated `current_active_tier_1_2` payload containing only approved-employer roles verified active during this run and still in scope, not rejected, not hard-blocked, not closed or expired, and not awaiting first-time verification.
16. Render the same payload through every configured report and notification adapter under `CURRENT ACTIVE TIER 1/2`. Include unchanged roles and render `None.` when empty.
17. Keep today's headline and all new, materially changed, provisional-high-fit, and Tier-alert counts independent from the snapshot. An unchanged role must not create a new alert or duplicate approval packet.

## After answers

1. Apply only confirmed answers and defaults explicitly approved by the user.
2. If the user approves a provisional employer, add it to the approved-company configuration before routing that employer's Tier 1 role into document generation.
3. Recalculate fit when a mandatory qualification is absent.
4. Run GatedSprint Phase 4 only after explicit approval.
5. Generate matching DOCX/PDF resume and cover-letter files and final integrity/ATS/format checks.
6. Save the package in a role-specific location through the configured document-storage adapter.
7. Return the official application URL and configured output location.
8. Never submit an application.

## Failure policy

- Unverified official page: mark `verification_pending`; do not generate documents.
- Current-active reverification source failure: omit the role from that run's snapshot, report it with incomplete checks/source failures, and do not mark it closed solely because of the transient failure.
- Provisional employer stability cannot be confirmed: keep it provisional and report the uncertainty.
- Missing evidence: ask one concise question; never infer it.
- Closed role: stop document generation and mark closed.
- Output-adapter failure: report the error and retry on the next run.
