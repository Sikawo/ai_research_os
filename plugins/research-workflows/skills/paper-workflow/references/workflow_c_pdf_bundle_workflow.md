# Public PDF Bundle Boundary

The public bundle lane prepares instructions and reviews returned Markdown. It
does not automate PDF discovery, reading, copying, upload, download, or browser
interaction.

1. Generate an instruction ZIP with `scripts/export_public_pdf_prompt.py`.
2. The human may attach approved public PDFs manually outside this plugin.
3. Keep returned notes in a temporary, explicit review location.
4. Validate returned notes with
   `scripts/review_imported_full_text_notes.py` in dry-run mode.
5. Treat every returned note as `ai_draft_needs_human_review` until reviewed.

Restricted or non-public material is never eligible. Apply/import, repository
write, Git publication, and external delivery are separate human-controlled
actions.
