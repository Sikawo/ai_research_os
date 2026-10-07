# ParagraphLock Protocol

## Purpose

ParagraphLock supports close discussion and revision of one bounded passage while preserving all unapproved text exactly. It is designed for application forms, manuscripts, proposals, letters, and other prose where an assistant may otherwise rewrite untouched material when reconstructing the full document.

ParagraphLock is an editing boundary, not a quality-review framework. It does not run a full application review, generate an approval packet, or require multi-phase ceremony.

## Activation and exit

Activate the mode when the user invokes `ParagraphLock`, `paragraph lock`, `$paragraph-lock`, or clearly requests the same behavior.

The mode remains active until the user explicitly exits it or starts a clearly separate task. Suggested commands are:

- `adopt`: approve the only unambiguous current candidate;
- `adopt P3-r2`: approve a named candidate;
- `next`: select another scope without broadening the current approval;
- `show full text`: assemble the baseline plus approved replacements;
- `unlock`: leave ParagraphLock mode.

These commands are conveniences, not exact required wording. The approval decision must still be explicit and unambiguous.

## State model

Maintain one session state with:

- `baseline_id`: a stable label such as `B1`;
- `baseline_sha256`: the SHA-256 digest of the exact UTF-8 baseline when deterministic tools are available;
- `active_scope`: the only passage currently open for revision;
- `candidates`: exact proposed replacements with stable revision IDs;
- `approved_replacements`: the exact candidate revisions explicitly adopted by the user;
- `held_suggestions`: useful out-of-scope observations that have not been approved for implementation;
- `verification_level`: `Verified` or `Conversation-only`.

Do not create a second document state by repeatedly rewriting the whole text. The baseline plus the approved replacement ledger is the document state.

## Scope rules

The user may select a paragraph, sentence, clause, heading, caption, or another exact span. Use the narrowest clearly intended scope.

- Text outside the active scope is immutable.
- Reading adjacent text for context does not authorize editing it.
- An instruction about one sentence does not authorize rewriting the rest of its paragraph.
- An instruction about wording does not authorize formatting, citation, reference, numbering, or structural changes.
- A newly discovered improvement outside scope may be recorded as a held suggestion, but it must not appear in assembled text.
- Scope expansion requires an explicit user instruction.

If the user identifies a passage ambiguously, quote the proposed active span and obtain confirmation before treating it as editable.

## Candidate and approval rules

Each candidate must include:

- a stable ID, such as `P3-r1`;
- the exact current text;
- the exact proposed replacement;
- a short reason;
- any meaning, evidence, tone, or factual risk.

A later revision of the same passage receives a new revision suffix. Only the adopted revision enters the approved replacement ledger.

The following are not approval by themselves:

- praise or positive reaction;
- `looks good`, `interesting`, or equivalent conversational language;
- a request to explain, compare, continue, or show alternatives;
- silence;
- approval of the underlying idea without approval of the exact wording.

A bare `adopt` may approve the current candidate only when exactly one candidate is current and no reasonable ambiguity exists. Otherwise require its ID.

User-authored replacement text is still scoped approval. Record it as the approved after-text for the selected span; do not adjust it silently.

## Full-text assembly

`show full text` is a construction operation, not a writing pass.

1. Start with the exact frozen baseline.
2. Apply only explicitly approved replacements.
3. Preserve all other bytes exactly when deterministic file access is available.
4. Do not run grammar cleanup, style normalization, citation normalization, voice adjustment, formatting cleanup, or final polish during assembly.
5. Verify the assembled result against the baseline and approved replacement ledger.
6. Emit the full text only after verification passes.

If verification fails, do not repair the result through free-form rewriting. Return to the baseline, report the mismatch, and correct the replacement ledger or assembly inputs.

## Deterministic verifier

Use `scripts/verify_paragraph_lock.py` for UTF-8 plain-text files. The verifier operates on byte offsets so untouched line endings, whitespace, punctuation, and Unicode bytes remain exact.

The change manifest has this shape:

```json
{
  "schema_version": 1,
  "baseline_sha256": "<sha256>",
  "replacements": [
    {
      "id": "P3-r2",
      "start_byte": 120,
      "end_byte": 184,
      "before": "Exact baseline text",
      "after": "Exact approved text",
      "approved": true
    }
  ]
}
```

Only entries with `approved: true` are applied. The verifier rejects duplicate IDs, invalid byte ranges, overlapping approved replacements, baseline hash mismatches, and before-text mismatches.

Example commands:

```bash
python3 scripts/verify_paragraph_lock.py fingerprint --baseline baseline.txt
python3 scripts/verify_paragraph_lock.py assemble --baseline baseline.txt --changes changes.json --output assembled.txt
python3 scripts/verify_paragraph_lock.py verify --baseline baseline.txt --changes changes.json --candidate assembled.txt
```

Assembly refuses to overwrite an existing output file unless `--force` is supplied.

## Verification levels

### Verified

Use this label only when the exact baseline is available and the deterministic verifier confirms that the candidate equals the baseline plus approved replacements.

### Conversation-only

Use this label when deterministic file assembly is unavailable. Continue to respect all approval and scope rules, but do not claim byte-exact preservation. If the user needs the complete document, ask for the baseline again when necessary and state the limitation plainly.

## Structured-document boundary

The first version verifies UTF-8 plain text only. It does not prove preservation of DOCX runs, tracked changes, comments, fields, tables, footnotes, styles, pagination, or reference-manager metadata.

For a structured document:

- preserve the original file;
- treat extracted text as a discussion surface, not proof of file-level identity;
- require a format-aware document workflow before claiming verified preservation;
- do not silently convert the document to plain text and back.

## Failure behavior

Fail closed when:

- the baseline is missing or its digest changed;
- the selected scope cannot be identified exactly;
- approval is ambiguous;
- approved replacements overlap;
- the recorded before-text does not match the baseline;
- the assembled or candidate text includes an unapproved difference;
- the requested guarantee exceeds the available verification method.

On failure, preserve the baseline and approved ledger, explain the smallest corrective action, and do not present an unverified full text as final.
