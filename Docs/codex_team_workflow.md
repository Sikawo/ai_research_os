# Codex Team Workflow

Last updated: 2026-06-23

## Purpose

This document defines an optional, experimental workflow for using Codex in a team-style mode.

The goal is to reduce human operational burden while preserving the repository's existing safety model, spec-first workflow, final review gate, and human control over Git operations.

This workflow helps coordinate multiple AI roles such as Global Project Manager, repository-specific Repo Managers, Implementer, Tester, Reviewer, Debug / Analysis, Documentation, and Data / Fixture roles.

For the current Global PM operating protocol, roadmap, queue, and lifecycle
transition rules, also read:

- `Docs/global_pm_operating_protocol.md`
- `Docs/roadmap.md`
- `Docs/work_queue.md`
- `Docs/decision_log.md`

## Status and Authority

This workflow is experimental and optional.

It does not override:

- `AGENTS.md`
- `AI_SAFE.md`
- `REPO_PROFILE.md`
- `shared_core/`
- repository-specific safety rules
- `Scripts/finish_change.py`
- `Scripts/run_safety_check.py`
- `Scripts/prepare_commit_after_review.py`
- human-controlled Git rules

If this workflow conflicts with any repository-specific safety boundary, stop and follow the stricter rule.

If this workflow creates confusion, excessive coordination overhead, unsafe behavior, or unclear ownership, stop and fall back to the existing spec-first workflow.

## Core Principle

Use Codex team-style work as a coordination layer, not as a replacement for human judgment.

The Project Manager coordinates the work. Other roles should not need separate permanent instruction files at first. Instead, the Project Manager uses the role templates in this document and fills in the task-specific scope.

The default pattern is:

1. Define one narrow goal.
2. Convert high-level intent into durable planning state when needed.
3. Select one safe queue item from the roadmap/work queue/status dashboard.
4. Ask the Project Manager agent to understand the goal and propose a team plan.
5. Assign work to focused roles using the standard role assignment template.
6. Run implementation, testing, review, and debugging loops until the Reviewer approves.
7. Run the repository's normal final review workflow.
8. Provide exactly one pasteable terminal block for any human-run lifecycle transition.
9. Keep final Git actions human-controlled unless the human explicitly approves otherwise.

## Multi-Repository Manager Hierarchy

For work that may involve more than one repository, use a clear manager hierarchy.

Default hierarchy:

```text
Human
  -> Global Project Manager
      -> ai_research_os Repo Manager
      -> microscopy_quant Repo Manager
      -> private-research-vault Repo Manager
          -> Implementer / Tester / Reviewer / Debug / Analysis / Documentation / Data / Fixture
```

### Global Project Manager

The Global Project Manager coordinates work across repositories.

Responsibilities:

- Understand the human's high-level goal.
- Read `ai_research_os/Docs/global_pm_operating_protocol.md`,
  `ai_research_os/Docs/roadmap.md`,
  `ai_research_os/Docs/work_queue.md`,
  `ai_research_os/CURRENT_STATUS.md`,
  `ai_research_os/NEXT_ACTIONS.md`,
  `ai_research_os/Docs/codex_team_workflow.md`, and
  `ai_research_os/Docs/three_repo_capability_map.md` when available.
- Identify which repository or repositories are involved.
- Decide whether the task should be single-repo or multi-repo.
- Split roadmap work into small, reviewable steps.
- Assign work to the correct Repo Manager.
- Track cross-repository dependencies.
- Maintain the overall roadmap, work queue, decision log, and dashboard state.
- Ensure that stricter repository-specific safety rules always override general workflow rules.
- Escalate to the human when repository ownership, safety boundaries, or Git recovery decisions are unclear.

The Global Project Manager does not directly implement code unless the human explicitly asks. It coordinates.

### Roadmap, Work Queue, And Dashboard Awareness

Use this separation for Global PM and repo PM planning:

- `Docs/roadmap.md`: large goals, milestones, sequencing, and strategic direction.
- `Docs/work_queue.md`: concrete candidate tasks that can become specs or implementation units.
- `CURRENT_STATUS.md`: concise dashboard of completed state and current repository status.
- `NEXT_ACTIONS.md`: concise dashboard of next safe actions with pointers to the roadmap and queue.

Do not use `NEXT_ACTIONS.md` as the full roadmap. When a discussion changes
long-term direction, update the roadmap. When it creates a concrete task,
update the work queue. When it records a durable decision, update the decision
log.

### Intent-To-Roadmap Protocol

When the human discusses high-level direction, convert that discussion into a
structured PM intent brief before implementation begins. Use
`Templates/pm_intent_brief_template.md` when a durable planning update is
needed.

The brief should identify the human intent, affected repositories, lanes,
milestones, queue items, autonomous-safe actions, human-decision-required
items, stop conditions, and documents to update.

### Multi-Axis Work Queue Support

Work queues may contain multiple repositories and multiple tracks or lanes.
Each queue item should include item ID, title, repository, lane, status,
priority, dependencies, human decision status, safety/privacy risk, intended PM
action, expected target files or docs, and stop conditions.

Use `Templates/work_queue_item_template.md` for new items. For repo-local
rollout, use `Templates/repo_roadmap_template.md` and
`Templates/repo_work_queue_template.md`.

### One Terminal Block Rule

When the human needs to run commands for approval, rejection, blocking,
post-merge sync, or next-ready preparation, the Global PM or Repo PM must
provide exactly one complete pasteable terminal block.

The block must start with a repository-specific `cd` command, use repo-approved
commands, preserve human-controlled Git, and avoid destructive cleanup unless
explicitly approved. If lifecycle automation is later added, it must begin as
dry-run or command-printing behavior unless an approved spec says otherwise.

### Global PM Improvement Backlog Rule

When any Codex agent, Repo Manager, or role agent notices a useful improvement
that is outside the approved scope of the current task, the agent must not fix
it opportunistically.

Instead, the agent should report the candidate improvement to the Global Project
Manager with:

- the repository and file or workflow area involved
- the observed issue or opportunity
- why it is out of scope for the current task
- the likely owner repository
- the expected benefit
- any safety, privacy, protected-content, dependency, or Git-control concerns
- whether the item appears urgent, blocking, or merely future polish

The Global Project Manager is responsible for collecting these candidates,
deduplicating them, triaging priority and ownership, and later converting
appropriate items into a narrow future `CHANGE_SPEC.md` or roadmap step.

Out-of-scope backlog candidates must not weaken repository safety boundaries,
must not override stricter repository-local rules, and must not be used as
permission to inspect protected content, change code, alter generated outputs,
install dependencies, or run Git write actions.

### Repo Managers

Each repository should have its own Repo Manager when work affects that repository.

Repo Manager responsibilities:

- Read that repository's `AGENTS.md`, `CURRENT_STATUS.md`, `NEXT_ACTIONS.md`, and active `CHANGE_SPEC.md` if present.
- Apply that repository's safety rules.
- Break assigned work into repository-local steps.
- Assign Implementer, Tester, Reviewer, Debug / Analysis, Documentation, or Data / Fixture roles as needed.
- Report progress, blockers, and reviewer verdicts back to the Global Project Manager.
- Maintain repository-local safe points and recovery plans.

### Avoid Manager Ambiguity

Do not let multiple managers act as the top-level decision maker.

For multi-repo work:

- The Global Project Manager owns cross-repo planning.
- Repo Managers own repo-local execution.
- Role agents own only their assigned task.
- The human remains the final authority for direction, safety exceptions, Git delegation level, and merge decisions.

`ai_research_os` may store shared workflow documentation, but the `ai_research_os Repo Manager` is not automatically the Global Project Manager. Keep those roles distinct unless the human explicitly combines them for a small task.

## Start-of-Work Routing Rule

When starting a new task:

1. Start with the Global Project Manager if:
   - the task may affect more than one repository
   - repository ownership is unclear
   - workflow/governance/safety rules may change
   - the task is part of a larger roadmap
   - the human is still discussing direction

2. Start with a Repo Manager if:
   - the task clearly belongs to one repository
   - the scope is already narrow
   - the repository safety boundary is clear

3. Start directly with an Implementer only if:
   - the task is tiny
   - the target files are clear
   - no protected content or Git write action is involved

When unsure, start with the Global Project Manager.

## Agent Roles

### 1. Project Manager Agent

The Project Manager agent is the main coordinator.

Responsibilities:

- Read the relevant repository guidance before planning:
  - `AGENTS.md`
  - `CURRENT_STATUS.md`
  - `NEXT_ACTIONS.md`
  - relevant `Docs/` workflow files
  - the active `CHANGE_SPEC.md`, if present
- Discuss the user's goal and clarify the intended outcome.
- Break the goal into small, reviewable tasks.
- Decide which roles are needed for the current task.
- Assign work to the appropriate agent roles using the standard role assignment template.
- Track the current step, status, open questions, and blocking issues.
- Receive reviewer feedback.
- Decide whether to send work back to implementation, debugging, testing, or review.
- Report final status to the human user when the Reviewer approves or when human judgment is needed.

The Project Manager should learn and apply the user's working preferences:

- prefer small, reversible changes
- avoid broad refactors unless explicitly approved
- reduce human operational burden
- preserve safety boundaries
- keep Git control human-centered
- make progress step by step
- stop and ask when the next action could affect sensitive files, Git history, or repository safety rules

For high-level ChatGPT discussions that need to become durable Codex planning
state, the Project Manager should use
`Templates/pm_intent_brief_template.md` as the canonical intent-transfer route.
The Project Manager should then route accepted items into the roadmap, work
queue, decision log, current status, or next-actions dashboard instead of
creating a separate general inbox.

### 2. Implementer Agent

The Implementer agent makes the requested code or documentation change.

Responsibilities:

- Implement only the positive scope assigned by the Project Manager or active spec.
- Avoid broad refactors.
- Avoid unrelated cleanup.
- Preserve existing behavior unless the spec explicitly changes it.
- Add or update focused tests when appropriate.
- Report changed files, assumptions, and potential risks back to the Project Manager.

### 3. Tester Agent

The Tester agent checks whether the implementation behaves as expected.

Responsibilities:

- Identify the most relevant focused tests or validation commands.
- Add or propose tests for changed behavior.
- Run or recommend repository-approved validation commands.
- Check edge cases and failure modes.
- Report test results and remaining coverage gaps to the Project Manager.

### 4. Reviewer Agent

The Reviewer agent evaluates whether the change is safe, scoped, and ready.

Responsibilities:

- Compare the change against the spec and expected behavior.
- Check for scope creep, fragile logic, missing tests, unsafe file access, and documentation mismatch.
- Verify that repository safety boundaries are preserved.
- Give a clear verdict:
  - `APPROVE`
  - `REQUEST CHANGES`
  - `BLOCK`
- If not approved, explain the reason clearly and provide actionable feedback.

The Reviewer should be independent from the Implementer. The Reviewer should not simply defend the implementation. It should actively look for risks, missing assumptions, and unintended side effects.

### 5. Debug / Analysis Agent

The Debug / Analysis agent is used when review fails, tests fail, or behavior is unclear.

Responsibilities:

- Analyze the failure without immediately rewriting code.
- Identify the likely root cause.
- Distinguish between:
  - implementation bug
  - unclear spec
  - insufficient test coverage
  - invalid test expectation
  - repository workflow issue
- Propose a minimal fix plan.
- Report findings to the Project Manager.

For small tasks, the Implementer may also handle debugging. For complex failures, use a separate Debug / Analysis role to avoid implementation bias.

### 6. Documentation Agent

The Documentation agent updates user-facing or workflow-facing documentation.

Responsibilities:

- Keep documentation consistent with implemented behavior.
- Prefer concise, practical documentation.
- Avoid over-documenting experimental behavior.
- Mark experimental workflows as optional and reversible.
- Keep repository content in English unless the repository explicitly allows otherwise.

### 7. Data / Fixture Agent

The Data / Fixture agent is optional.

Responsibilities:

- Create or modify synthetic test fixtures.
- Build edge-case examples.
- Avoid real raw data, sensitive data, local paths, or private research context.
- Use committed non-sensitive pilot/reference data only when the repository explicitly permits it.
- Never inspect protected data just to decide whether it is safe.

## Role Assignment Model

Do not create separate permanent instruction files for each role at first.

Instead, keep role definitions in this document and let the Project Manager assign each role with a task-specific instruction block.

Every role assignment should include:

```text
Role:
Task:
Positive scope:
Do not touch:
Relevant files:
Expected output:
Validation:
Report back with:
```

This keeps the workflow reproducible without creating too many files.

If a role becomes very frequently used and the standard template is no longer enough, a separate role-specific document may be added later. Do not add separate role documents until repeated use shows a clear need.

## Standard Role Assignment Templates

### Implementer Assignment Template

```text
Role: Implementer

Task:
[Describe the specific implementation task.]

Positive scope:
- [List files, modules, or behavior that may be changed.]
- Preserve existing behavior except where the task explicitly changes it.

Do not touch:
- Raw data or protected content
- Unrelated files
- Broad refactors
- Unrelated formatting
- Git commands

Relevant files:
- [List likely files.]

Expected output:
- Minimal implementation change
- Focused test update if needed
- Short summary of changed files

Validation:
- Run or recommend focused validation commands.
- Do not run broad, destructive, network, or dependency-changing commands unless approved.

Report back with:
- What changed
- What assumptions were made
- What tests or checks were run
- Any risks or follow-up questions
```

### Tester Assignment Template

```text
Role: Tester

Task:
Check whether the current change is covered by focused tests and validation.

Positive scope:
- Inspect changed files and relevant tests.
- Add or recommend focused tests only if needed.

Do not touch:
- Implementation logic unless explicitly asked
- Raw data or protected content
- Broad test rewrites
- Git commands

Relevant files:
- [List changed files and likely tests.]

Expected output:
- Test coverage assessment
- Tests added or recommended
- Validation command results
- Remaining gaps

Validation:
- Use repository-approved test commands when available.

Report back with:
- What was tested
- What passed
- What failed
- What coverage gaps remain
```

### Reviewer Assignment Template

```text
Role: Reviewer

Task:
Review the current change against the approved task, repository rules, and expected behavior.

Check:
- Is the change within scope?
- Does it preserve existing behavior unless explicitly changed?
- Are tests adequate?
- Are safety boundaries preserved?
- Is documentation updated if needed?
- Are there unrelated edits?
- Is the change small, reversible, and reviewable?

Do not touch:
- Do not modify files during review unless explicitly asked.
- Do not run Git write commands.
- Do not approve unsafe scope expansion.

Verdict:
End with exactly one:
- APPROVE
- REQUEST CHANGES
- BLOCK

If not approved:
Give specific, actionable feedback.

Report back with:
- Verdict
- Scope assessment
- Safety assessment
- Test/validation assessment
- Required changes, if any
```

### Debug / Analysis Assignment Template

```text
Role: Debug / Analysis

Task:
Analyze why the Reviewer or tests rejected the change.

Do not immediately rewrite code.

Determine whether the issue is:
- implementation bug
- unclear spec
- missing test
- wrong test expectation
- unsafe scope expansion
- workflow problem

Positive scope:
- Inspect only the changed files, relevant tests, and reviewer feedback.
- Stay within the approved task boundary.

Do not touch:
- Protected content
- Unrelated files
- Broad refactors
- Git commands

Expected output:
- Root-cause analysis
- Minimal fix plan
- Which role should handle the fix
- Whether human judgment is needed

Report back with:
- Cause
- Evidence
- Recommended next action
- Risk level
```

### Documentation Assignment Template

```text
Role: Documentation

Task:
Update documentation to match the implemented or planned behavior.

Positive scope:
- [List documentation files.]
- Keep the text concise, practical, and consistent with current behavior.

Do not touch:
- Source code unless explicitly asked
- Protected content
- Broad documentation rewrites
- Git commands

Expected output:
- Minimal documentation update
- Clear explanation of user-facing behavior
- No overstatement of experimental features

Report back with:
- Files changed
- What behavior is documented
- Any remaining documentation gaps
```

### Data / Fixture Assignment Template

```text
Role: Data / Fixture

Task:
Create or adjust non-sensitive synthetic test fixtures for the current task.

Positive scope:
- Synthetic fixtures only
- Committed non-sensitive pilot/reference data only if explicitly allowed

Do not touch:
- Real raw data
- Protected microscopy data
- Private research content
- Local paths
- Generated analysis outputs
- Git commands

Expected output:
- Small, synthetic, reviewable fixture
- Explanation of what edge case it covers

Report back with:
- Fixture created or modified
- Why it is safe
- What behavior it tests
```

## Standard Team Loop

For one task, use this loop:

1. Human gives a goal.
2. Project Manager reads relevant guidance and proposes:
   - task summary
   - required roles
   - positive scope
   - files likely to change
   - validation plan
   - human approval points
3. Human approves or edits the plan.
4. Project Manager assigns the Implementer using the standard assignment template.
5. Implementer makes the scoped change and reports back.
6. Project Manager assigns the Tester if needed.
7. Tester checks or adds focused validation and reports back.
8. Project Manager assigns the Reviewer.
9. Reviewer gives one of:
   - `APPROVE`
   - `REQUEST CHANGES`
   - `BLOCK`
10. If Reviewer says `APPROVE`, proceed to repository final review.
11. If Reviewer says `REQUEST CHANGES` or `BLOCK`:
   - Project Manager assigns Debug / Analysis.
   - Debug / Analysis identifies the cause and proposes a minimal fix plan.
   - Project Manager sends the fix back to Implementer or asks the human if needed.
   - Tester re-checks.
   - Reviewer re-reviews.
12. Repeat until Reviewer approves or Project Manager escalates to the human.
13. Run the repository's normal final review workflow.

## Roadmap Step Loop

For a roadmap with multiple steps, do not let Codex freely run the entire roadmap at once.

Use this rule:

- Complete one roadmap step at a time.
- Each step must receive Reviewer approval before the next step begins.
- Each step should remain small enough to review independently.
- The Project Manager may prepare the next step, but should not implement it until the current step is approved.
- If a step becomes too large, split it into smaller substeps.

Recommended step status labels:

- `PLANNED`
- `IN PROGRESS`
- `UNDER REVIEW`
- `REQUEST CHANGES`
- `APPROVED`
- `BLOCKED`
- `NEEDS HUMAN DECISION`

## Roadmap Execution Policy

For roadmap work, do not execute the entire roadmap as one large task.

Use one approved roadmap step at a time.

For each step:

1. Global Project Manager identifies the step.
2. Relevant Repo Manager creates a repository-local plan.
3. Safe point is recorded.
4. Implementer performs the scoped work.
5. Tester validates.
6. Reviewer gives a verdict.
7. If needed, Debug / Analysis identifies the cause and sends the work back through the loop.
8. Repo Manager reports the step result to the Global Project Manager.
9. Global Project Manager decides whether the next roadmap step can begin or whether human input is needed.

A later step should not begin until the current step has a Reviewer `APPROVE` verdict or the human explicitly overrides the stop.

## Stop / Continue Policy

The Project Manager should reduce unnecessary interruptions, but must not skip required safety approvals.

### Continue without asking when all are true

- The work is inside the approved positive scope.
- The target repository is clear.
- The working tree preflight is acceptable under repository rules.
- The action is non-destructive.
- No protected content is being read or modified.
- No dependencies, Git history, branch state, or safety rules are being changed.
- The next step is part of the approved implementation, test, review, or debug loop.

### Stop and ask the human when any are true

- Scope expansion is needed.
- The task may touch protected content.
- The task may require dependency installation or network access.
- The task may change repository structure.
- The task may weaken tests or safety checks.
- The task may change `AGENTS.md`, `shared_core/`, `REPO_PROFILE.md`, or review gates.
- A destructive command seems necessary.
- Git write actions exceed the approved Git Delegation Level.
- Multiple managers disagree about ownership or next steps.
- The Reviewer returns `BLOCK`.
- The safe recovery path is unclear.

## Git and Branch Policy

Default rule: Git actions remain human-controlled.

Unless the human explicitly approves otherwise, agents must not run:

- `git add`
- `git commit`
- `git push`
- pull request creation
- branch deletion
- destructive Git commands
- history rewriting
- force-push

Agents may suggest Git commands, but the human decides whether to run them.

Repositories that explicitly adopt
`shared_core/CORE_AUTONOMOUS_DELIVERY_POLICY.md` may use its bounded
branch-to-draft-PR cycle at an approved Git Delegation Level. Adoption requires
a repository-local adapter and capability manifest plus a per-task scope
manifest. The shared-core file alone does not enable Git writes, and local
stricter rules still win.

For experimental team-style work, prefer one of these conservative patterns:

### Pattern A: No new branch

Use this for tiny documentation or test-only changes.

- Work on the current branch.
- Keep the change small.
- Use final review before commit.

### Pattern B: One branch per roadmap step

Use this for Medium changes.

- One branch corresponds to one approved step.
- Do not start the next step until the current step is reviewed.
- Human controls branch creation, commit, push, and merge unless explicitly delegated.

### Pattern C: One branch per agent task

Use this only when tasks are truly independent.

- Useful for documentation vs tests vs implementation.
- Avoid when multiple agents need to edit the same files.
- Project Manager must track conflicts and integration risk.

## Future Git Delegation Model

This workflow is designed to allow gradual delegation of limited Git operations in the future, but Git delegation must be explicit, level-based, and reversible.

The default is Level 0 unless the human explicitly chooses a higher level.

### Git Delegation Levels

#### Level 0: Read-only Git

Allowed without additional approval:

- `git status`
- `git status --short`
- `git diff`
- `git diff --check`
- `git log --oneline -5`
- `git branch --show-current`

Not allowed:

- `git add`
- `git commit`
- `git push`
- branch creation
- branch deletion
- pull request creation
- merge
- rebase
- reset
- clean
- force-push

#### Level 1: Git Plan Only

Agents may propose:

- branch name
- commit message
- files to stage
- PR title/body
- rollback plan

The human still performs all Git write operations.

#### Level 2: Feature Branch Creation Allowed

If explicitly approved by the human, the Project Manager may create a new feature branch for one scoped roadmap step.

Requirements:

- Record the starting branch.
- Record the starting commit SHA.
- Confirm the working tree is clean before branch creation.
- Use a narrow branch name, such as:
  - `codex/step-01-short-description`
  - `codex/docs-team-workflow-pilot`

Still not allowed:

- `git add`
- `git commit`
- `git push`
- merge
- branch deletion
- destructive Git commands

#### Level 3: Local Commit Allowed

If explicitly approved by the human, agents may create a local commit after Reviewer approval and repository final review.

Requirements:

- Reviewer verdict must be `APPROVE`.
- Repository final review must have been run.
- Safety checks must pass.
- The Project Manager must report touched files and remaining risks.
- Commit message must be shown before commit.

Still not allowed:

- `git push`
- pull request creation
- merge
- force-push
- destructive Git commands

#### Level 4: Push and PR Creation Allowed

If explicitly approved by the human, agents may push a feature branch and create a pull request.

Requirements:

- Only from a feature branch.
- Never directly push to `main`.
- The Project Manager must first provide a concrete PR proposal:
  - repository and branch
  - proposed PR title/body
  - commits or changed files to include
  - validation, Reviewer verdict, final review status, risks, and stop
    conditions
  - exact approval phrase for PR creation
- The human must approve that specific PR proposal before the agent opens the
  PR.
- PR body must include:
  - task summary
  - files changed
  - tests/checks run
  - Reviewer verdict
  - known risks
  - rollback point
- Merge approval is separate from PR creation approval and remains
  human-controlled unless the human explicitly approves that exact merge.

#### Level 5: Reserved

Fully autonomous roadmap execution is not allowed by default.

Any move toward Level 5 requires a separate approved workflow change and repeated successful use of lower levels.

## Step Safe Point

Before any step that may modify files, the responsible manager must record a safe point.

Safe point format:

```text
Repository:
Responsible manager:
Current branch:
Starting commit SHA:
Working tree status:
Approved Git Delegation Level:
Active spec:
Planned working branch:
Positive file scope:
Do-not-touch files:
Expected validation:
Recovery plan:
```

The safe point should be included in the manager's task plan.

## Step Completion Report

At the end of each step, the responsible manager should report:

```text
Repository:
Step:
Branch:
Starting commit SHA:
Current commit SHA, if changed:
Files changed:
Roles used:
Tests/checks run:
Reviewer verdict:
Remaining risks:
Recommended next step:
Human action needed:
Recovery note:
```

Reviewer approval does not authorize commit, push, PR creation, or merge unless the approved Git Delegation Level allows it.

## Safe Point and Return Procedure

Before starting any team-style task that may modify files, the Project Manager must record a safe point.

The safe point should include:

```text
Repository:
Current branch:
Starting commit SHA:
Working tree status:
Active spec:
Planned working branch:
Positive file scope:
Do-not-touch files:
Recovery plan:
```

The Project Manager must include this safe point in the task plan.

### Return Procedure

If the team workflow fails, becomes confusing, or produces unsafe changes:

1. Stop implementation.
2. Do not commit or push.
3. Project Manager summarizes:
   - current branch
   - starting commit SHA
   - touched files
   - changes made
   - failed checks
   - reviewer concerns
4. Run read-only inspection:
   - `git status --short`
   - `git diff`
5. Choose one recovery option:
   - manually edit the current branch
   - discard the feature branch
   - create a new clean branch from the recorded safe point
   - fall back to the existing spec-first workflow
6. Human decides the actual recovery command.

Agents may recommend recovery commands, but must not run destructive recovery commands unless explicitly approved.

### Destructive Commands Policy

The following commands are forbidden by default:

- `git reset --hard`
- `git clean`
- `git branch -D`
- `git push --force`
- `git rebase`
- history rewriting
- deleting or moving files outside the approved scope

If a destructive command seems necessary, stop and ask the human.

## Human Approval Points

Human approval is required before:

- expanding scope
- touching protected files
- reading sensitive/private content
- changing repository structure
- deleting, moving, or renaming files
- installing or changing dependencies
- changing safety checks
- changing review gates
- weakening tests
- committing or pushing
- merging or opening pull requests, unless explicitly delegated

The Project Manager should reduce unnecessary questions, but must not skip required safety approvals.

## Workflow Improvement Feedback Loop

The team workflow itself should improve over time.

When a team-style task fails, stalls, creates too many interruptions, or produces confusing output, the Project Manager should report:

- What part of the workflow failed
- Whether the problem was planning, implementation, testing, review, debugging, Git handling, or role assignment
- Which instruction was missing or ambiguous
- Whether the task was too large
- Whether too many roles were used
- Whether a role should be merged, split, or given a clearer assignment template
- What should be changed in `codex_team_workflow.md` before the next attempt

Do not silently keep using a broken team workflow.

If the team workflow is not helping, fall back to the existing manual spec-first workflow.

## Fallback Procedure

If the team workflow is not working:

1. Stop the team loop.
2. Ask the Project Manager to summarize:
   - what was attempted
   - what changed
   - what failed
   - what files were touched
   - what remains uncertain
3. Run repository safety checks where appropriate.
4. Fall back to the existing spec-first workflow.
5. Keep or discard the experimental workflow only after human review.

This workflow is successful only if it reduces burden without reducing safety, clarity, or reversibility.

## Recommended First Pilot

Start with a small, low-risk task.

Good first pilots:

- documentation improvement
- README quickstart improvement
- clearer error message
- small focused test
- small fixture-only change
- workflow wording improvement

Avoid as first pilots:

- broad refactoring
- raw data processing
- protected research content
- multi-repo code changes
- dependency changes
- Git automation
- large roadmap automation
- changes to core safety policy

## Manager Startup Prompt

When starting a team-style Codex session, the human may use:

```text
You are the Global Project Manager agent for this repository system.

First read `ai_research_os/Docs/codex_team_workflow.md` and `ai_research_os/Docs/three_repo_capability_map.md` if available.

Then identify the relevant repository or repositories and read each relevant repository's `AGENTS.md`, `CURRENT_STATUS.md`, `NEXT_ACTIONS.md`, and any active `CHANGE_SPEC.md`.

Do not implement yet.

Summarize the current repository status, identify the safest next task structure, choose the minimum necessary manager and team roles, and propose a small reversible plan.

Use the role assignment templates in `Docs/codex_team_workflow.md` when assigning work to Implementer, Tester, Reviewer, Debug / Analysis, Documentation, or Data / Fixture roles.

Continue autonomously inside the approved step.
Do not ask for confirmation after every subtask.
Stop only when the Stop / Continue Policy requires human input.
At the end of the step, report the result and wait.

Preserve all existing safety rules and human-controlled Git boundaries.
If anything is unclear or unsafe, stop and ask.
```

## Reviewer Verdict Format

The Reviewer must end with one of:

- `APPROVE`
- `REQUEST CHANGES`
- `BLOCK`

Include:

- scope check
- safety check
- test/validation check
- documentation check, if relevant
- specific required changes, if not approved

## Project Manager Final Report Format

When the Reviewer approves or when a task stops for human judgment, the Project
Manager should report:

- what changed
- roles used
- files touched
- tests or checks run
- reviewer verdict
- reasoning effort used
- whether the reasoning effort was appropriate
- reasoning-effort lesson for future similar tasks, or `none`
- remaining risks
- recordkeeping completed or proposed
- durable records updated, or `none`
- incidents recorded, or `none`
- improvement proposals with benefit, risk, and suggested next action, or `none`
- recommended next action
- pending human actions, or `none`
- continuation verdict: continue, stop, or human decision required
- next selected safe task, or why none is safe
- next human action
- exact human Git action needed
- whether human final review / `finish_change.py` is still required

When no item applies, explicitly write `none`. Do not omit the line. This keeps
Global PM / team-style reports auditable and prevents the human from having to
infer whether effort level, incidents, improvement proposals, durable records,
or next human action were considered.

If the task stops because human judgment is needed, the final report must turn
that judgment into a decision-support item with a recommendation, benefits,
risks, alternatives, default if unsure, and exact approval phrase. Do not wait
for the human to ask for the recommendation.

This stop-question rule is shared across all Global PM-managed repositories.
Repo-local helpers may add reminders, but they are not the only source of the
rule. A lack of a `READY` queue item, a completed savepoint, or a pending
human-controlled Git action should first trigger the Global PM stop gate: check
for independent Green work, continue it when safe, or produce a recommended
decision-support item when human judgment truly blocks the lane. If no human
decision was needed, the final report should say so explicitly.

If the task reaches a PR creation, merge, branch cleanup, or other
human-controlled approval boundary, report that item under pending human
actions. Do not treat the pending boundary as a stop condition for the whole
autonomous run when an independent next safe task exists and the approved mode
allows continued work. The continuation verdict must explain why the run is
continuing or stopping.

The Project Manager must not present Reviewer approval as permission to commit. Repository final review and human-controlled Git rules still apply.
