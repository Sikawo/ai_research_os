# Custom GPT Setup Guide

Derived from: `Verified Search Core v1.2.0`

This guide describes manual configuration. It does not publish or remotely modify a GPT.

## Purpose and Positioning

Recommended name: `Actually Checked`

Recommended tagline: `Ask normally. It checks the right sources before you act.`

Recommended description:

> Ask normally. Actually Checked verifies the right current sources, checks what could make your plan fail, and tells you what to do now, what remains uncertain, what to check later, and which sources were actually used.

`Actually Checked` is user-facing branding. The canonical framework remains `Verified Search` so branding can change without forking the policy.

## Manual Setup

1. Open the host's Custom GPT creation or configuration screen.
2. Create a GPT named `Actually Checked`.
3. Use the description above or a faithful shorter version.
4. Copy the content under `Paste-Ready Instructions` from [`custom_gpt_instructions.md`](custom_gpt_instructions.md) into the GPT instructions field.
5. Enable web search or browsing when available.
6. Attach the current versions of these three files as Knowledge:
   - [`verified_search_core.md`](verified_search_core.md)
   - [`test_cases.md`](test_cases.md)
   - [`user_experience.md`](user_experience.md)
7. Treat the Instructions field as controlling when Instructions and Knowledge
   are ambiguous or appear inconsistent. Knowledge supplies detail and
   reference cases; it does not replace the controlling deployment behavior.
8. Do not add external actions, APIs, or integrations merely for this policy.
9. Save the configuration and run the deployment checklist before sharing it.

The three Knowledge files are part of the intended Custom GPT architecture and
must be updated together with the Instructions when the canonical version
changes. Uploads do not guarantee instruction priority or version
synchronization; the compact Instructions explicitly remain controlling.

## Conversation Starters

- `Can I take my child to this event tomorrow?`
- `Double-check this before I leave.`
- `Is this application actually ready to submit?`
- `What should I verify now, and what should I check later?`

These are examples only. Users should be able to ask normally in any supported language.

## Deployment Checklist

- Instructions identify `Verified Search Core v1.2.0`.
- The exact Paste-Ready Instructions block passes
  `python3 scripts/validate_deployments.py`, is at most 7,500
  characters under the repository release budget, and is below the 8,000
  Custom GPT hard limit.
- Current `verified_search_core.md`, `test_cases.md`, and `user_experience.md`
  are attached as Knowledge.
- Web/search capability is enabled when available.
- Verified Search Baseline activates without a mode phrase.
- Best-Action Principle and Decision Framing shape the answer around the practical goal.
- Failure-Mode First prioritizes blockers without unnecessary research.
- Temporal Relevance distinguishes useful-now facts from premature facts.
- Older and newer artifacts are compared for governing applicability rather than selected by date or specificity alone.
- Open-ended exceptions are revalidated, silence does not prove continuation or termination, and unresolved governing conflicts block `Ready`.
- Strict Verification uses a meaningfully different evidence route when practical.
- Final-Action Audit produces blockers, mitigation, and Action Readiness.
- Re-check Planning explains what should be checked later and when.
- Search snippets are never accepted as evidence.
- Entity Lock, Date Lock, publication Freshness Check, Applicability Check, and Continuing Applicability and Supersession remain active.
- No-Fill Rule, Negative-Claim Guard, conflict handling, and scientific-mode separation remain active.
- Responses follow the user's language without exposing private reasoning traces.
- Every browsed answer ends with a localized source section displaying the actual URLs of all material external sources used.
- The model never invents or reconstructs a URL when the host does not expose it.
- Representative prompts from [`test_cases.md`](test_cases.md) produce acceptable behavior.

## Custom Instructions Alternatives

- [`custom_instructions_free.md`](custom_instructions_free.md) is the compact universal and Free-friendly deployment for restrictive instruction fields.
- [`custom_instructions_full.md`](custom_instructions_full.md) is a richer deployment for larger instruction fields.
- [`custom_gpt_instructions.md`](custom_gpt_instructions.md) is the preferred complete user-facing deployment.

## Version Synchronization

When [`verified_search_core.md`](verified_search_core.md) changes:

1. Read the new core and its [`CHANGELOG.md`](CHANGELOG.md) entry.
2. Update every derived artifact so all mandatory invariants remain present.
3. Update each source-version declaration.
4. Run `python3 scripts/validate_deployments.py` to validate the
   exact Custom GPT, Compact, and Full paste-ready blocks against their
   independent budgets.
5. Manually replace the hosted Instructions and all three Knowledge files.
6. Run the deployment checklist and representative acceptance tests.

The repository cannot automatically guarantee that a hosted Custom GPT or Custom Instructions configuration remains synchronized. A human maintainer must update and verify each deployment. Host behavior, browsing access, citations, URL exposure, limits, and product features can change independently.

## End-User Guidance

Do not require users to learn verification levels or internal terminology. They should be able to ask `Can I go tomorrow?` and receive an answer-first recommendation, unresolved blockers, a practical re-check plan, and the actual URLs used.
