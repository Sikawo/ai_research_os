# User-Supplied Public Full-Text Workflow

This route applies only when the user deliberately supplies an already-public
paper or public full text for the current run.

- The plugin never discovers, opens, copies, or uploads a PDF on its own.
- Unpublished, under-review, confidential, licensed-only, and collaborator-
  private material is rejected.
- `scripts/export_public_pdf_prompt.py` produces instructions only; it does not
  include or inspect PDFs.
- Returned Markdown is an AI draft. Review it with
  `scripts/review_imported_full_text_notes.py` in dry-run mode before deciding
  whether to save it in a user-selected workspace.
- No Git or external-delivery action is part of this workflow.

Use `public_full_text_reviewed` only when the supplied public full text was
actually read. Otherwise use `abstract_metadata_only`.
