# Repository Instructions

## Purpose

This repository owns public, reusable research-workflow infrastructure. It is
currently a safety-only clean-history scaffold.

## Required behavior

- Treat all content as public and shareable.
- Read `AI_SAFE.md` and `REPO_PROFILE.md` before modifying the repository.
- Use explicit path allowlists for every migration or extraction.
- Use synthetic examples and fixtures only.
- Keep private configuration and external resource bindings outside this
  repository.
- Validate repository safety and tests before proposing a commit.

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

The autonomous-delivery manifest remains disabled until a later reviewed
change explicitly enables it.
