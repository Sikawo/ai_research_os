# Discuss Import To Papers

Use this template to decide which generated paper-note drafts should be listed
in `selected_notes.yaml`. Do not paste private paper text, PDF text, Bookends
paths, local file URLs, raw data, secrets, or collaborator context into this
discussion packet.

## Source Export

- workflow:
- export run folder:
- generated notes folder:
- selection file:

## Review Questions

- Which generated notes are approved for import?
- Which generated notes should be skipped or revised first?
- Are all approved notes public and safe for this shared importer?
- Does each approved note honestly represent its read depth?
- Is each target path a new `Papers/*.md` path, or an explicit
  `replace_abstract_only` upgrade?

## Selected Notes Draft

```yaml
notes:
  - id:
    source_note_path: generated_notes/
    target_path: Papers/
    import_action: new
    expected_note_depth: abstract_metadata_only
    expected_security_tier: public
    human_review_status: approved_for_import
```

## Import Command

Dry run first:

```bash
python3 scripts/review_selected_notes.py \
  --source exports/<workflow_name>/<timestamp> \
  --selection exports/<workflow_name>/<timestamp>/selected_notes.yaml
```

Apply only after human review:

```bash
python3 scripts/review_selected_notes.py \
  --source exports/<workflow_name>/<timestamp> \
  --selection exports/<workflow_name>/<timestamp>/selected_notes.yaml \
  --apply
```
