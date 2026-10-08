# AI Research OS

AI Research OS is a clean-history public repository for reusable research
workflow infrastructure.

## Current status

The clean-history bootstrap is complete. Phase 6A activates public governance
and a deny-by-default transfer manifest before reusable capabilities are ported
offline. A manifest entry permits review and implementation; it does not imply
that a capability is already present or live.

## Repository boundaries

- Public, reusable implementation belongs here.
- Personal configuration, credentials, runtime state, reports, research data,
  application materials, and private scientific records do not.
- Examples and fixtures must be synthetic.
- No earlier repository history was imported into this repository.

See `AGENTS.md`, `AI_SAFE.md`, and `REPO_PROFILE.md` before proposing changes.

## Validation

Run:

```bash
python3 Scripts/validate_repository_safety.py --phase working-tree
python3 -m pytest -q -p no:cacheprovider
```

Use `--phase repository` after a commit to verify the independent root history,
origin, branch boundary, public tree, and transfer manifest.

## Public plugins

- **ParagraphLock** provides approval-gated exact text replacement.
- **GatedSprint 2.1.0** provides approval-gated application review and the
  exact bare `Sprint` self-driving route from one reviewed skill package. Its
  bundled fixtures are synthetic, and its deterministic runtime uses only the
  Python standard library.
- **Review Tools 1.0.0** provides focused application review, calibrated
  reviewer critique, and professional communication review. It deliberately
  defers exact bare `Sprint` and every `GatedSprint` route to the GatedSprint
  plugin, and it contains no target-specific profiles or application context.

All plugins are registered in `.agents/plugins/marketplace.json` and licensed
under Apache-2.0 with the rest of this repository.

## License

Licensed under the Apache License, Version 2.0. See `LICENSE`.
