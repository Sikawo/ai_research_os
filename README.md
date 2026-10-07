# AI Research OS

AI Research OS is a clean-history public repository for reusable research
workflow infrastructure.

## Current status

This repository is a safety-only scaffold. It does not yet provide executable
research, career, document-review, or analysis capabilities. Future transfers
must be explicitly allowlisted, independently reviewed, and supported by
synthetic tests before they enter this public history.

## Repository boundaries

- Public, reusable implementation belongs here.
- Personal configuration, credentials, runtime state, reports, research data,
  application materials, and private scientific records do not.
- Examples and fixtures must be synthetic.
- No earlier repository history was imported into this repository.

See `AGENTS.md`, `AI_SAFE.md`, and `REPO_PROFILE.md` before proposing changes.

## Initial validation

Run:

```bash
python3 Scripts/validate_repository_safety.py --phase pre-commit
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

After the root commit exists, use `--phase post-commit` to verify the clean
history, branch, remote, and committed allowlist.

## License

Licensed under the Apache License, Version 2.0. See `LICENSE`.
