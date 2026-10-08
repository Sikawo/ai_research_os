# Selected Paper Note Import Workflow

This workflow is the shared landing zone for AI/API/script-generated paper-note
drafts. Future Workflow A (PubMed AI Triage Pipeline) and Workflow C (Bookends
Local Full-Text Note Pipeline) can both write generated Markdown drafts under
`exports/`; this importer only validates, reviews, and optionally copies
human-selected drafts into `Papers/`.

It does not search PubMed, call AI APIs, retrieve PMC full text, parse Bookends
XML, read PDFs, or interpret literature.

## Folder Shape

Generated drafts should live under a workflow export run folder:

```text
exports/<workflow_name>/<timestamp>/generated_notes/
exports/<workflow_name>/<timestamp>/selected_notes.yaml
```

The selection file uses the format in
`assets/selected_notes_template.yaml`.

## Dry Run

Run the importer without `--apply` first:

```bash
python3 scripts/review_selected_notes.py \
  --source exports/<workflow_name>/<timestamp> \
  --selection exports/<workflow_name>/<timestamp>/selected_notes.yaml
```

Dry run writes a review packet only:

```text
exports/selected_paper_note_import_review/<timestamp>/SELECTED_PAPER_NOTE_IMPORT_REVIEW_PACKET.md
```

No `Papers/` files are written in dry-run mode.

## Apply

After human review, add `--apply`:

```bash
python3 scripts/review_selected_notes.py \
  --source exports/<workflow_name>/<timestamp> \
  --selection exports/<workflow_name>/<timestamp>/selected_notes.yaml \
  --apply
```

Apply mode writes only validated selected notes with `import_action: new` or
`import_action: replace_abstract_only`. It still writes the review packet.

## Selection Rules

Each note entry should include:

```yaml
notes:
  - id: example_note_id
    source_note_path: generated_notes/example_note.md
    target_path: Papers/Example_2026.md
    import_action: new
    expected_note_depth: abstract_metadata_only
    expected_security_tier: public
    human_review_status: approved_for_import
```

Supported actions:

- `new`: import only when the target does not already exist.
- `replace_abstract_only`: replace an existing public
  `abstract_metadata_only` note only with a public full-text-reviewed upgrade.
- `skip`: document that the note is not selected.
- `review_only`: document the note without importing it.

## Safety Checks

The importer rejects:

- absolute or escaping `source_note_path` values
- target paths outside `Papers/`
- non-Markdown targets
- unsafe local-path or local-file URL markers, blocked source URL metadata
  fields, and obvious secret or token fields
- non-public, restricted, internal, private, unpublished, or confidential note
  depths
- abstract-only drafts that claim full-text review
- public full-text-reviewed drafts without public full-text provenance markers
- overwrite attempts through `new`

Generated notes should include these provenance fields:

- `note_depth`
- `security_tier`
- `read_depth`
- `source_provenance`
- `human_review_status`

## Git Boundary

The importer performs no Git actions. It does not stage, commit, push, switch
branches, create pull requests, or clean generated exports. Human review and
human Git control remain required.
