---
name: verified-search
description: Verify consequential or time-sensitive claims with claim-specific authoritative sources, explicit applicability checks, and uncertainty handling. Use when current public evidence matters to a decision.
---

# Verified Search

Verified Search is a decision-ready real-life verification framework for consequential, current, or externally verifiable questions.

`GitHub is the source of truth; Custom GPT and Custom Instructions are deployment surfaces.`

## Positioning

Verified Search is not primarily a hallucination detector or post-hoc fact checker. It is a verification-first decision-support workflow that identifies the user's practical goal, checks what could make the action fail, selects claim-specific authoritative evidence, handles time-dependent uncertainty, and recommends the safest useful action now.

The progression in v1.2 is:

`factual verification -> governing applicability -> decision support -> action readiness`

The core framework name remains `Verified Search`. The recommended user-facing Custom GPT working name is `Actually Checked`, with the tagline: `Ask normally. It checks the right sources before you act.` Product branding may change without changing the policy architecture.

## Architecture

| Artifact | Role |
| --- | --- |
| [`verified_search_core.md`](references/verified_search_core.md) | Canonical normative policy, currently Verified Search Core v1.2.0 |
| [`custom_gpt_instructions.md`](references/custom_gpt_instructions.md) | Compact controlling Custom GPT deployment behavior, kept below the 8,000-character field limit |
| [`custom_gpt_setup.md`](references/custom_gpt_setup.md) | Human setup and version-sync guide |
| [`custom_instructions_free.md`](references/custom_instructions_free.md) | Compact universal and Free-friendly deployment |
| [`custom_instructions_full.md`](references/custom_instructions_full.md) | Richer Custom Instructions deployment for larger instruction fields |
| [`user_experience.md`](references/user_experience.md) | Human-readable interaction design |
| [`test_cases.md`](references/test_cases.md) | Behavioral acceptance, URL, and synchronization tests |
| [`CHANGELOG.md`](references/CHANGELOG.md) | Policy-version history |

The core is the only normative source. Derived artifacts may compress presentation or deployment detail, but they must preserve all mandatory invariants listed in the core.

The reviewed deployment references are byte-identical public source artifacts.
Some internal references retain the reviewed source-repository layout. Use
these explicit public-plugin translations instead of following a missing path:

| Historical source path | Public plugin path |
| --- | --- |
| `references/README.md` | this `SKILL.md` wrapper |
| `Scripts/validate_verified_search_deployments.py` | `scripts/validate_deployments.py` |
| `AI_INSTRUCTIONS.md` | this `SKILL.md` wrapper, which routes to `references/verified_search_core.md` |

Do not infer or follow a missing private or legacy repository path.

## Deployment Surfaces

### Actually Checked Custom GPT

The preferred novice-facing deployment. The Instructions field contains compact
controlling behavior and stays within a 7,500-character repository release
budget below the 8,000-character hard limit. Attach the current
`verified_search_core.md`, `test_cases.md`, and `user_experience.md` as Knowledge
for normative detail, acceptance/failure cases, and UX guidance. Instructions
remain controlling if the uploaded references are missing, stale, conflicting,
or ambiguous.

### Compact Custom Instructions

`custom_instructions_free.md` is the compact universal fallback for restrictive or Free-plan interfaces. Its paste-ready block stays within a conservative 1,400-character target and preserves the highest-value safety and decision behaviors.

### Full Custom Instructions

`custom_instructions_full.md` is a richer deployment for hosts or accounts with a larger instruction allowance. It preserves substantially more of the multi-pass workflow and Mandatory Source URL Policy while remaining shorter than the Custom GPT instructions.

### Repository-Linked Use

Best for maintainability, versioning, multi-model reuse, and expert workflows.
This `SKILL.md` routes relevant work to the canonical core. A repository link
is a reference for tools operating with repository context; it does not
automatically inject the policy into unrelated hosted-chat conversations.

## Mandatory Source URLs

Any answer based on external sources must visibly expose the actual URLs of the material sources used, unless the host genuinely prevents access to the underlying URL. In that case the limitation must be stated explicitly and no URL may be invented.

Rich citation UI does not replace this requirement when the actual URL is available. User-provided emails, SMS messages, screenshots, local files, and private portal messages are labeled as private or user-provided sources when no public URL exists.

## Multilingual Strategy

Repository policy remains English-only. A capable host model follows the user's current language while applying the same semantic rules and verification levels. Source-section headings are localized, while inspected URLs remain exact. Do not maintain translated policy forks or fixed multilingual trigger tables.

## Relationship to Scientific Evidence Mode

Verified Search and Evidence-Gated Research Discussion remain separate:

- current real-world factual claims use Verified Search;
- literature- and paper-specific claims use the
  [`evidence-mode` discussion contract](../evidence-mode/references/evidence_gated_research_discussion_prompt.md);
- mixed requests apply both systems at claim level.

Neither system weakens medical, legal, financial, privacy, repository-security, or platform requirements.

## Versioning and Maintenance

Use semantic policy versions. The current canonical version is `Verified Search Core v1.2.0`.

When the core changes:

1. Update `verified_search_core.md` and assign the policy version.
2. Update every derived artifact and its declared source version.
3. Update `CHANGELOG.md` with policy changes, not work-session notes.
4. Run the synchronization, URL, and behavioral checks in `test_cases.md`.
5. Run `python3 scripts/validate_deployments.py`; no artifact may
   be called Paste-Ready unless its exact fenced block passes its own deployment
   budget and any documented hard limit.
6. Manually update the Custom GPT Instructions and its three Knowledge files,
   then update and test every other hosted configuration.

Do not create a separate status, handoff, or work-log system for this policy.

## Limitations

Verified Search is a process guarantee, not a truth guarantee. Sources can be wrong, incomplete, stale, inaccessible, or changed after inspection. Future-dependent facts may be too early to determine. Host models and interfaces differ in browsing, citations, URL exposure, context, and configuration limits. The repository cannot automatically keep hosted deployments synchronized.
