---
name: paper-workflow
description: Prepare public-paper metadata and note-review packets using offline-first, dry-run workflows. Use for public bibliographic or user-supplied public full-text material; do not access protected papers or private repositories.
---

# Paper Workflow

This skill prepares reviewable artifacts for public papers. It does not contain
a paper corpus, discover local PDFs, read protected material, upload files, or
bind to a private repository. Generated outputs are temporary and remain
human-reviewed drafts.

## Safety boundary

- Work only with public metadata or public full text explicitly supplied by the
  user for the current run.
- Never search local storage for PDFs, notes, indexes, or reference-manager
  attachments.
- Never read, copy, upload, or summarize unpublished, confidential,
  under-review, licensed-only, or collaborator-private material.
- Do not infer an output workspace. Every mutable helper receives an explicit
  user-selected workspace root.
- Helpers default to planning, packet generation, or dry-run review. Any apply
  operation is a separate explicit human action after inspecting the packet.
- No helper stages, commits, pushes, opens a pull request, or changes a
  scheduled task.

## Available routes

### Public PDF instruction packet

Create instructions without reading or including a PDF:

```bash
python3 scripts/export_public_pdf_prompt.py \
  --batch-name public-paper-batch \
  --output-root <explicit-output-directory> \
  --output-zip <explicit-output-zip>
```

The user may later attach public PDFs manually to an AI chat. The helper does
not discover, copy, read, or upload them.

### Public bibliographic packet

Use `scripts/build_bibliographic_note_packet.py` with an explicitly supplied
public metadata/XML input, output directory, and optional synthetic target
workspace. This route represents abstract/metadata reading depth unless the
user separately supplies public full text. The command is a dry run by default;
writing requires `--apply`. A source map is produced only when the caller also
supplies `--source-map-output`.

### Returned-note review

The following helpers validate user-selected generated Markdown material:

- `scripts/review_imported_full_text_notes.py`
- `scripts/review_imported_generated_notes.py`
- `scripts/review_selected_notes.py`

Run without `--apply` first. Dry-run output must identify every proposed
destination and safety rejection. Apply mode may write only to the explicit
temporary workspace selected by the user; it is never automatic skill
behavior.

### Filename normalization plan

`scripts/plan_note_filename_normalization.py` produces a review plan before any
rename. Applying a reviewed plan requires explicit human action and a clean
target workspace. Git publication remains outside this helper.

## Reading depth

Use one of these labels:

- `abstract_metadata_only`
- `public_full_text_reviewed`

Restricted/internal reading depth is intentionally unsupported by this public
plugin. See `references/restricted_paper_note_workflow.md` for the stop rule.

## Assets and references

- `assets/Paper_Template.md` is the reviewed public note template.
- `assets/paper_note_template.md` is the adaptable workflow template.
- `assets/pdf_only_full_text_chatgpt_instructions.md` defines the public-PDF
  chat boundary.
- `assets/paper_note_quality_checklist.md` is the human review checklist.
- `references/paper_extraction_workflow.md` describes public metadata packets.
- `references/full_text_paper_note_workflow.md` describes user-supplied public
  full-text handling.
- `references/paper_note_import_workflow.md` describes dry-run import review.

## Output contract

Every note draft must distinguish bibliographic facts, paper claims,
interpretation, and speculation; record reading depth; preserve uncertainty;
and avoid local paths, private storage names, credentials, or claims of actions
that did not occur. A generated draft is not final until the user reviews and
saves it.
