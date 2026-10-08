# PubMed AI Triage Workflow

This Workflow A helper supports Phase 2 public PubMed metadata/abstract
screening, Phase 3a public PMC full-text availability/retrieval/export, Phase
3b deterministic public PMC full-text Markdown draft generation, and a
safety-gated AI backend interface. It prepares reviewable exports only. The
default path does not call external AI APIs, retrieve publisher full text outside
PMC, read PDFs or supplements, parse Bookends, write to `Papers/`, import paper
notes, or perform Git actions.

## Phase 2 Abstract Screening

Offline fixture run:

```bash
python3 scripts/run_triage.py \
  --goal "Find public papers relevant to a one-sentence research goal" \
  --topic-slug example_topic \
  --input-pubmed-json path/to/synthetic_pubmed_results.json \
  --abstract-top-n 5 \
  --screening-backend heuristic
```

Manual live PubMed metadata run, when network use is appropriate:

```bash
python3 scripts/run_triage.py \
  --goal "Find public papers relevant to a one-sentence research goal" \
  --topic-slug example_topic \
  --query "public PubMed query" \
  --retmax 20 \
  --abstract-top-n 5 \
  --screening-backend heuristic
```

Tests use synthetic JSON input and synthetic PMC XML fixtures only. They do not
contact PubMed, NCBI, OpenAI, Claude, PMC, publisher sites, Bookends, PDFs, or
private repository notes.

## Phase 3a PMC Public Full-Text Availability

Offline fixture run:

```bash
python3 scripts/run_triage.py \
  --goal "Find public papers relevant to a one-sentence research goal" \
  --topic-slug example_topic \
  --input-pubmed-json path/to/synthetic_pubmed_results.json \
  --input-pmc-fixtures path/to/synthetic_pmc_fixtures \
  --check-pmc-full-text \
  --pmc-top-n 5
```

Manual live PubMed/PMC public retrieval, when network use is appropriate:

```bash
python3 scripts/run_triage.py \
  --goal "Find public papers relevant to a one-sentence research goal" \
  --topic-slug example_topic \
  --query "public PubMed query" \
  --retmax 20 \
  --abstract-top-n 5 \
  --screening-backend heuristic \
  --check-pmc-full-text \
  --pmc-top-n 5
```

Phase 3a records whether PMCID metadata is present, whether public PMC XML
retrieval or fixture loading was attempted, whether retrieval succeeded, whether
plain text was extracted, and whether a later draft-generation step generated a
full-text note. Fixture tests use synthetic PubMed records and synthetic PMC XML
only.

## Phase 3b Public PMC Full-Text Drafts

Offline fixture run:

```bash
python3 scripts/run_triage.py \
  --goal "Find public papers relevant to a one-sentence research goal" \
  --topic-slug example_topic \
  --input-pubmed-json path/to/synthetic_pubmed_results.json \
  --input-pmc-fixtures path/to/synthetic_pmc_fixtures \
  --check-pmc-full-text \
  --pmc-top-n 5 \
  --generate-full-text-drafts
```

Phase 3b generates deterministic Markdown draft notes under
`generated_notes/full_text_level/` only for eligible records with a PMCID,
successfully exported public PMC XML/text, and non-empty extracted text. Drafts
are marked:

```yaml
note_depth: public_full_text_reviewed
security_tier: public
read_depth: public_full_text_reviewed
human_review_status: ai_draft_needs_human_review
```

The drafts include public-PMC-derived summaries, section-level bullets, methods
or controls only when visible in public XML, figure captions only when visible
in public XML, relative PMC XML/text export paths, deterministic-generation
limitations, and import review reminders. They are not automatically importable,
and `selected_notes.yaml` remains `notes: []` until a human edits it.

## Output Folder

The script writes a timestamped folder under:

```text
exports/pubmed_ai_triage/<timestamp>_<topic_slug>/
```

Generated files and folders:

```text
PUBMED_TRIAGE_SUMMARY.md
pubmed_triage_manifest.json
pubmed_results.json
pubmed_results.csv
abstract_screening_results.json
pmc_availability_results.json
pmc_full_text/
pmc_full_text/xml/
pmc_full_text/text/
pmc_full_text/README.md
generated_notes/
generated_notes/abstract_level/
generated_notes/full_text_level/
DISCUSS_IMPORT_TO_PAPERS.md
selected_notes.yaml
selected_notes_instructions.md
```

`generated_notes/abstract_level/` contains up to `--abstract-top-n`
abstract-only draft notes. Each draft is marked:

```yaml
note_depth: abstract_metadata_only
security_tier: public
read_depth: pubmed_abstract_reviewed
human_review_status: ai_draft_needs_human_review
```

`pmc_availability_results.json` is generated when `--check-pmc-full-text` is
used. It records PMID, PMCID, title, year, journal, DOI, abstract screening
score/label when available, PMC status, public retrieval source, local XML/text
export paths, generated full-text draft path when present, text character count,
limitations, warnings, and `full_text_note_draft_generated`.

`pmc_full_text/xml/` and `pmc_full_text/text/` contain temporary public PMC
XML/plain-text review artifacts only under `exports/`. The text export is a
conservative extraction from public PMC XML. It does not OCR, parse PDFs, fetch
supplementary files, parse Bookends, or read private repository content.

`generated_notes/full_text_level/` contains a placeholder when
`--generate-full-text-drafts` is not used. With that flag, it also contains
deterministic `public_full_text_reviewed` draft notes based only on public PMC
XML/text exported under the same run folder.

## Screening Backend

`--screening-backend heuristic` is deterministic local scoring based on
title/abstract keyword overlap with the goal and query. `--screening-backend
mock` is a deterministic test backend. Neither backend calls OpenAI, ChatGPT,
Claude, or any other external AI API.

The screening results record PMID, title, year, journal, DOI, PMCID when present
as metadata, score, relevance label, backend, read depth, limitations, and a
reason string.

## Safe Import Discussion

`DISCUSS_IMPORT_TO_PAPERS.md` summarizes the goal, query or fixture input,
loaded record count, screening backend, abstract-level generated note counts,
public-PMC-full-text generated note counts, AI backend status, generated note
paths, PMC-available candidates, PMC XML/text export paths,
deterministic-generation limitations, and instructions that generated notes are
not automatically importable. It separates abstract-only draft candidates,
public PMC full-text draft candidates, candidates not ready for import, and
notes requiring further review before import.

`selected_notes.yaml` is intentionally safe and empty:

```yaml
notes: []
```

`selected_notes_instructions.md` shows safe selected-note examples for `new`,
`replace_abstract_only`, and `skip`. It also distinguishes abstract-only drafts
from public PMC full-text drafts:

```text
abstract-only: note_depth abstract_metadata_only; read_depth pubmed_abstract_reviewed
public PMC full text: note_depth public_full_text_reviewed; read_depth public_full_text_reviewed
```

Generated drafts must not be imported automatically. A human must review any
draft before adding it to `selected_notes.yaml` and using
`../paper-workflow/scripts/review_selected_notes.py`. If the importer requires the generated
note frontmatter to contain `human_review_status: approved_for_import`, the
human reviewer must edit the selected generated note draft after review.
`selected_notes.yaml` approval alone may not be enough while a draft still says
`human_review_status: ai_draft_needs_human_review`.

OpenAI output, if present, is an external AI suggestion only. It is not human
approval and should not change `human_review_status` without human review.

## API-Free Manual ChatGPT Note Packet

For manual ChatGPT-assisted drafting without an API call, add
`--generate-chatgpt-note-packet`. The script creates a local drag-and-drop
packet under:

```text
exports/pubmed_ai_triage/<timestamp>_<topic_slug>/chatgpt_note_packet/
```

Example:

```bash
python3 scripts/run_triage.py \
  --goal "Find public papers about extracellular-vesicle or vesicle-mediated collective transmission of enteroviruses." \
  --topic-slug ev_vesicle_manual_chatgpt \
  --query '("enterovirus" OR "poliovirus" OR "coxsackievirus") AND ("extracellular vesicles" OR vesicle OR "en bloc" OR "collective transmission")' \
  --sort best_match \
  --retmax 20 \
  --abstract-top-n 5 \
  --check-pmc-full-text \
  --pmc-top-n 3 \
  --generate-full-text-drafts \
  --generate-chatgpt-note-packet \
  --copy-packet-to-downloads \
  --reveal-packet
```

Expected packet outputs include `README_START_HERE.md`,
`CHATGPT_CREATE_NOTES_PACKET.md`, `expected_output_schema.md`,
`selected_notes_template.yaml`, `public_sources/`, `generated_context/`, and a
deterministic ZIP archive. With `--copy-packet-to-downloads`, the primary
Markdown packet and ZIP are copied to `<explicit-output-path>` using safe non-overwriting
filenames. With `--reveal-packet`, macOS Finder reveals the ZIP when possible;
on other systems the script prints the exact paths instead.

This mode is API-free: the script does not upload to ChatGPT, automate a
browser, call external AI APIs, read PDFs, parse Bookends, write to `Papers/`,
invoke importers, or perform Git actions. The packet is limited to public
PubMed metadata/abstracts, public PMC XML/text evidence exported by the same
run, relative run-folder paths, and workflow instructions. ChatGPT output is a
draft only; human review and the repository importer workflow remain separate.

## End-To-End Workflow A

```text
Goal -> triage run -> generated notes -> DISCUSS_IMPORT_TO_PAPERS.md
-> selected_notes.yaml -> dry-run import -> apply import -> final review
-> human commit
```

Recommended sequence:

1. Start from a one-sentence goal and run `scripts/run_triage.py`.
2. Review generated candidate notes under `exports/pubmed_ai_triage/.../generated_notes/`.
3. Discuss `DISCUSS_IMPORT_TO_PAPERS.md` with AI or review it manually.
4. Edit generated note frontmatter only after human review when import approval is appropriate.
5. Edit `selected_notes.yaml`; it remains `notes: []` until that human decision.
6. Run `../paper-workflow/scripts/review_selected_notes.py` first in dry-run mode.
7. Run the importer with `--apply` only after reviewing the dry-run packet.
8. Run final review and commit only intentional `Papers/` changes manually.

PubMed triage output is temporary and lives under `exports/`. Generated notes
are candidates, not committed paper notes. The import into `Papers/` is a
separate explicit step controlled by the human. Git add, commit, and push remain
manual.

## Relationship To Workflow A

Phase 0 is the selected paper-note importer, which validates and imports only
human-approved generated notes.

Phase 1 established the PubMed AI triage export folder skeleton.

Phase 2, described here, adds public PubMed metadata/abstract loading,
deterministic local screening, and abstract-metadata-only draft generation.

Phase 3a adds PMC public full-text availability checks plus public PMC XML/text
exports under `exports/pubmed_ai_triage/.../pmc_full_text/`.

Phase 3b adds deterministic full-text Markdown draft generation from public PMC
XML/text under `exports/`. This Phase 3b still does not use ChatGPT, OpenAI, or
Claude APIs. A future optional external AI backend may be added under a separate
approved spec with explicit API, secret, and safety boundaries.

Workflow C / Bookends local PDF reading remains separate and is not implemented
here.

## Safety-Gated AI Backend Interface

The optional `--ai-backend` flag is an interface boundary only. The default is
`disabled`, which creates no prompt packet, no mock response, no external AI
claim, no API-key handling, and no network AI request.

Local modes:

```bash
python3 scripts/run_triage.py \
  --goal "Find public papers relevant to a one-sentence research goal" \
  --topic-slug example_topic \
  --input-pubmed-json path/to/synthetic_pubmed_results.json \
  --input-pmc-fixtures path/to/synthetic_pmc_fixtures \
  --check-pmc-full-text \
  --generate-full-text-drafts \
  --ai-backend mock
```

- `disabled`: safe default; no AI backend packet or response is generated.
- `heuristic`: records the existing local deterministic pathway as an AI
  backend-interface run without calling an external service.
- `mock`: writes deterministic `mock_ai_backend` fixture output for tests and
  interface validation only.
- `prompt_packet`: writes a human-reviewable prompt/input packet under
  `ai_backend/` without sending it anywhere.
- `openai`: disabled-by-default live OpenAI Responses API adapter for public
  PubMed/PMC triage suggestions only. This mode requires
  `--allow-live-openai-api`, `--confirm-public-ai-export`, and an
  `OPENAI_API_KEY` value in the process environment.

Other live backend names such as `chatgpt`, `claude`, `anthropic`, or
`external_api` are rejected with a clear error. The OpenAI adapter uses Python
standard library HTTP only; it does not require the OpenAI SDK, read `.env`
files, upload files, upload PDFs, use OpenAI tools, use web/file search, create
vector stores, or use code interpreter.

Manual OpenAI live mode, only after the human has confirmed the packet contains
public PubMed/PMC content allowed by `AI_SAFE.md`:

```bash
python3 scripts/run_triage.py \
  --goal "Find public papers relevant to a one-sentence research goal" \
  --topic-slug example_topic \
  --input-pubmed-json path/to/public_pubmed_records.json \
  --input-pmc-fixtures path/to/public_pmc_fixtures \
  --check-pmc-full-text \
  --generate-full-text-drafts \
  --ai-backend openai \
  --allow-live-openai-api \
  --confirm-public-ai-export \
  --openai-model gpt-5.5
```

OpenAI mode fails closed unless all required flags are present, the public-only
gate passes, and `OPENAI_API_KEY` is available from the process environment. The
key is never written, printed, or serialized; manifests may record only booleans
such as whether a key was used and that it was not logged.

When a backend is requested, the script runs a conservative public-only gate
before writing backend packets. The gate blocks local absolute paths, local-file
URL schemes, source-url metadata fields, obvious secret/token/API-key markers,
private/internal/restricted labels, protected repository path markers, Bookends
markers, PDF path markers, raw data markers, and protected source-map references
in the backend input. Prompt packets are for human review only and any later
upload must follow `AI_SAFE.md`.

Backend interface files, when generated:

```text
ai_backend/
ai_backend/AI_BACKEND_INPUT_SUMMARY.md
ai_backend/AI_PROMPT_PACKET.md        # prompt_packet mode only
ai_backend/mock_ai_response.json      # mock mode only
ai_backend/OPENAI_REQUEST_REDACTED.json    # openai mode only
ai_backend/OPENAI_RESPONSE.json            # openai mode only
ai_backend/OPENAI_RESPONSE_SUMMARY.md      # openai mode only
ai_backend/ai_backend_manifest.json
```

`pubmed_triage_manifest.json` records the selected backend, whether the backend
was requested, whether the public-only gate passed, whether a prompt packet or
mock response was generated, and the invariant safety fields:

```yaml
external_ai_api_called: false
external_ai_network_request_performed: false
external_ai_api_key_used: false
```

In `openai` mode, OpenAI-derived output is labeled:

```yaml
external_ai_backend: openai
external_ai_review_status: ai_suggestion_needs_human_review
```

The response is a suggestion for later human review only. It does not approve
notes for import, does not call `../paper-workflow/scripts/review_selected_notes.py`, and
does not change the safe default:

```yaml
notes: []
```

Tests for the adapter use mocked HTTP responses and synthetic fixtures only.
They do not require an OpenAI API key and do not perform network calls. Workflow
C / Bookends local PDF reading remains separate and is not implemented here.

## Review Boundary

Generated `exports/` folders are temporary review artifacts. Human scientific
judgment and human Git control remain primary.
