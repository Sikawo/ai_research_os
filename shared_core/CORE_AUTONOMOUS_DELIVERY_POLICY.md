<!-- SHARED CORE v2026-08-03 — canonical source: ai_research_os/shared_core.
     Do NOT edit in a downstream repo. Edit only in ai_research_os, then re-sync. -->

# Core Autonomous Delivery Policy

> **SHARED CORE** — canonical source: `ai_research_os/shared_core`. Do NOT edit in a
> downstream repo. Edit only in `ai_research_os`, then re-sync. Version: 2026-08-03.

Source: created from `SPEC_20260803_cross_repo_autonomous_delivery_phase1` after
the `microscopy_quant` autonomous delivery pilot.

## Purpose

This policy defines the shared safety floor for an explicitly approved,
bounded autonomous delivery cycle:

```text
task approval
-> feature branch
-> implementation
-> validation
-> independent review
-> repository final review
-> scoped commit
-> feature-branch push
-> draft pull request
-> human merge decision
```

The policy reduces repeated operational approval prompts. It does not expand
content access, scientific authority, merge authority, or destructive Git
permissions.

## Adoption And Activation

Copying this file into a repository does not enable autonomous Git actions.
Autonomous delivery is available only when all of these conditions are true:

1. The repository has an explicit local autonomous-delivery adapter.
2. The repository capability manifest sets `enabled` to `true`.
3. The human explicitly approves the current autonomous cycle and Git
   Delegation Level.
4. A machine-readable task scope identifies the branch, allowed paths,
   forbidden paths, validation, commit message, and draft PR title.
5. Repository-specific preflight, review, and final-review gates pass.

The recommended Level 4 activation phrase is:

```text
Approved autonomous cycle. Git Level 4. Draft PR creation authorized for this task. Merge remains human-controlled.
```

Ordinary prompts such as `continue`, `next`, or `go ahead` do not activate
Level 4 by themselves.

## Policy Precedence

Apply the strongest applicable rule in this order:

1. secret, credential, privacy, protected-content, and destructive-operation
   prohibitions;
2. approved task positive and forbidden scope;
3. repository-specific scientific, data, and publication boundaries;
4. Reviewer and repository final-review gates;
5. repository autonomous-delivery adapter and capability manifest;
6. this shared contract;
7. general Git Delegation defaults.

A repository may narrow this contract. It must not use a local adapter or
manifest to weaken the shared safety floor.

## Git Delegation Ceiling

This contract supports these maximum actions when the human approves the
corresponding level and local policy allows it:

- Level 0: inspect repository state only.
- Level 1: prepare a Git and PR plan only.
- Level 2: create a named task feature branch, then edit and validate.
- Level 3: create reviewed local commits after Reviewer and final-review gates.
- Level 4: push the approved feature branch and create or update a draft PR.
- Level 5: reserved for separately approved merge, release, or administration.

No level inferred from this policy permits direct push to `main`, autonomous
merge, ready-for-review transition, force-push, history rewriting, branch
deletion, destructive recovery, or broad cleanup.

## Required Manifests

### Repository capability manifest

The version-controlled repository manifest declares:

- whether autonomous delivery is enabled;
- the maximum supported Git level;
- base branch and allowed feature-branch prefixes;
- allowed task classes;
- protected-content mode;
- blocked path patterns;
- required validation commands;
- policy documents and final-review command;
- permanent merge, force-push, and branch-deletion prohibitions.

### Task scope manifest

Each autonomous task declares:

- stable task ID and repository;
- requested Git level and change class;
- base and exact task branch;
- allowed paths and allowed new-file patterns;
- review-required and forbidden paths;
- protected-content mode;
- required validation commands;
- commit message and draft PR title.

Task scope can narrow repository permission. It cannot broaden it.

The reference helper permanently blocks `.env`, `.DS_Store`, generated
`exports/`, local `ai_artifacts/`, private-key files, and paths under
`credentials/` or `secrets/`. Repository manifests may add blocked patterns but
cannot remove this shared minimum.

## Preflight Gate

Before editing or publishing, verify:

- repository identity and starting commit are known;
- the exact `origin` URL and GitHub `owner/repository` identity match the local
  capability manifest;
- current branch is the exact task feature branch, not the base branch;
- branch prefix is locally allowed;
- requested Git level does not exceed the repository ceiling;
- task class and protected-content mode are locally allowed;
- every current changed path matches task scope;
- no changed path matches a task or repository forbidden pattern;
- every repository-required validation command is declared for the task;
- no unrelated staged, unstaged, untracked, deleted, or renamed file exists.

An uncertain or unclassified path is a stop, not an implied permission.

## Review And Commit Gate

Before a Level 3 or Level 4 commit:

1. Run the declared focused validation and repository safety checks.
2. Obtain an independent Reviewer `APPROVE` verdict.
3. Run and inspect the repository final-review workflow.
4. Confirm the final-review evidence reports safety and test PASS results.
5. Record Reviewer verdict, reviewed paths, starting merge-base commit, reviewed
   HEAD commit, content snapshot SHA256, final-review packet SHA256, and exact
   PR-body path and SHA256 in review evidence.
6. Compare actual paths and content snapshot with that evidence again.
7. On the first dry-run pass, propose staging exact reviewed paths only. Never
   use broad staging.
8. On a second pass, require an entirely staged tree with no unstaged mutation,
   and compare the staged path set and working snapshot to the same evidence.
9. Inspect the staged diff and staged path list before proposing the commit.
10. Use the task manifest's descriptive commit message.

Reviewer approval does not authorize Git actions above the approved level.

## Push And Draft PR Gate

Before a Level 4 push or draft PR:

- working tree must be clean;
- the feature branch must contain at least one commit beyond its base;
- all branch changes must remain inside task scope;
- final-review and Reviewer evidence must still pass;
- reviewed paths and content snapshot must still match exactly;
- the reference helper permits exactly one publication commit after the
  reviewed HEAD and checks every path recorded in that commit, preventing
  deleted intermediate content from escaping final-tree review;
- push must target only the exact task feature branch;
- PR must target the declared base branch and remain draft;
- existing PR updates require a successful read-only identity check proving the
  PR number, repository, draft state, head branch, and base branch;
- PR body must report summary, files, validation, Reviewer verdict, risks, and
  rollback point.
- a known existing draft PR must be updated explicitly rather than recreated.

Merge approval is separate from push and draft PR approval.

## Hard Stops

Stop the affected workstream before Git publication when any of these occurs:

- branch, repository, task, or working-tree state is ambiguous;
- an unrelated or unclassified path is present;
- protected, private, raw, generated, large, secret, or credential content is
  outside exact approved scope;
- validation, safety checks, Reviewer review, or final review fails;
- Reviewer returns `REQUEST CHANGES` or `BLOCK`;
- the requested action exceeds the approved Git level;
- dependency, network, security, privacy, scientific, or publication policy
  would change outside scope;
- credentials or external access required for push or PR creation are missing;
- recovery would require merge conflict judgment, reset, clean, force-push,
  history rewriting, deletion, or another destructive operation.

Stop only the blocked workstream when independent safe work remains elsewhere.

## Partial Failure Recovery

Recovery must preserve evidence and avoid duplicate publication:

- commit succeeds, push fails: preserve the local commit and report the exact
  retry command;
- push succeeds, PR creation fails: preserve the remote branch and retry PR
  creation without making a duplicate commit;
- draft PR already exists: update or report that PR rather than creating a
  duplicate;
- validation fails after a commit: do not push; fix through a new reviewed
  commit or ask for recovery guidance;
- remote state is ambiguous: stop and inspect before retrying.

Never automate rollback with force-push, hard reset, clean, or branch deletion.

## Dry-Run Tooling

`Scripts/autonomous_delivery.py` is the initial reference helper. It validates
manifests and Git/review evidence and prints proposed commands. It never stages,
commits, pushes, opens a PR, merges, deletes, cleans, or rewrites history.

Live execution must be introduced later through repository-local adapters and
separate reviewed specs.

## End-Of-Run Record

Report at minimum:

- repository, branch, and starting commit;
- changed and committed paths;
- validation commands and results;
- Reviewer verdict and final-review packet;
- commit hash, push status, and draft PR URL when applicable;
- known risks and rollback point;
- exact stop condition or completed-scope reason;
- pending human merge or policy decision.
