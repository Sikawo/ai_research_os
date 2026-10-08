# Paper Note Batch Checklist

Last updated: 2026-05-14

Use this checklist for small batches of public bibliographic XML supplied by
the user. Do not discover or read local reference-manager libraries.

## Before Running

- Choose a small batch size: `--limit 5` or `--limit 10`.
- Prioritize papers by the researcher, boss, former boss, and research program-relevant topics.
- Use abstract/metadata-only notes by default.
- Reserve PDF/full-text notes for high-priority papers only.
- Confirm that no PDF or attachment file will be opened, copied, or uploaded.

## Generate Prompt Packets

```bash
python3 scripts/build_bibliographic_note_packet.py \
  --source-mode bookends_xml \
  --bookends-xml path/to/export.xml \
  --bookends-root path/to/Bookends \
  --backend manual_prompt_packet \
  --limit 5 \
  --output-dir <explicit-temporary-output> \
  --papers-dir <explicit-synthetic-target-directory> \
  --source-map-output <explicit-temporary-source-map>
```

This is a dry run by default. Review the plan, then repeat with `--apply` only
when the explicit output locations are temporary public-data workspaces.

## Create Notes

- Review each prompt packet in the explicit temporary output directory.
- If an AI chat is used, upload only user-approved public material.
- Import reviewed notes only through a separate explicit workflow.
- Keep notes concise and grounded in the provided metadata and abstract unless deliberately doing a high-priority full-text pass.
- Keep any optional source map in the explicitly selected temporary output.

## Safety Check

- Do not commit temporary generated packets.
- Confirm that only expected files changed:

```bash
git status --short
```

- Check for local path or raw URL leakage:

```bash
rg '<local-absolute-path>|local-file URL|source_url' <explicit-temporary-output>
```

This command should return no matches.

## Commit Scope

Do not commit from this helper automatically. If a separate reviewed change is
later authorized, exclude:

- temporary prompt packets
- raw PDFs
- reference-manager files
- absolute local paths
- raw `local-file URL` URLs
- `source_url` fields
