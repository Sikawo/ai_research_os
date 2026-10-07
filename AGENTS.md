# Repository Instructions

## Purpose

This repository owns public, reusable research-workflow infrastructure. It has
an independent clean history and is in a reviewed offline migration phase.

## Required behavior

- Treat all content as public and shareable.
- Read `AI_SAFE.md` and `REPO_PROFILE.md` before modifying the repository.
- Use explicit path allowlists for every migration or extraction.
- Use synthetic examples and fixtures only.
- Keep private configuration and external resource bindings outside this
  repository.
- Validate repository safety and tests before proposing a commit.
- Treat `manifests/phase6a_transfer_allowlist.yaml` as the deny-by-default
  source-to-destination boundary for Phase 6A.
- Apply `shared_core/CORE_AUTONOMOUS_DELIVERY_POLICY.md` together with
  `Docs/codex_autonomous_work_policy.md` for bounded autonomous delivery.

## Prohibited content

Do not add research data, scientific instance records, paper notes, candidate
or application material, reports, runtime state, credentials, tokens, private
URLs, local absolute paths, private configuration values, or imported Git
history.

Do not copy a directory, archive, branch, tag, commit, or `.git` object from an
earlier repository. A later transfer may copy only independently reviewed file
content named in an approved manifest.

## Git boundary

The initial root commit is a one-time clean-history bootstrap. After that
commit, changes use feature branches and review. Direct pushes to `main`,
merges, force pushes, history rewriting, branch deletion, and destructive
recovery require an explicit human-controlled boundary.

The repository manifest may enable a narrow exception to the normal
human-controlled Git boundary only after the governance-activation change has
been committed and merged by a human. A compliant Git Level 4 cycle requires
an exact task scope, successful validation, Independent Reviewer `APPROVE`,
exact staging, and final review. Direct push to `main`, merge,
ready-for-review transition, force push, history rewriting,
branch deletion, and destructive recovery remain prohibited.
