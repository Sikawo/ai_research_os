# GatedSprint v2 canonical skill staging package

Current workflow identifier: `gated-sprint 2.1.0`.

This directory is the single Git-tracked source package for the installed
`$gated-sprint` skill. `SKILL.md` is the concise router, `references/` contains
progressively disclosed workflow modules, and the deterministic state/eval
support lives beside them. The active user skill must be installed from these
exact bytes and must match `skill-package-manifest.json`.

Historical repository adapters and compatibility references outside this
public plugin must not override this package or form a second authoritative
workflow. Exact bare `Sprint` is still self-driving, but it uses this same
skill package for shared authority and safety rules; `GatedSprint` remains
approval-gated.

Version 2.1 adds the opt-in, evidence-grounded industry-resume AI/ATS profile.
`industry_resume.ai_ats_mode=true` runs the shared Gates 0-8 analysis and audit
contract while preserving those distinct execution policies. Omitted or false
keeps legacy resume behavior; ordinary academic CV work is not silently
rerouted. The simulator is repository-native and non-proprietary: it reports
per-requirement evidence and visible counts, never an opaque overall match
percentage or a claimed replica of an external screening product.

The implementation uses only the Python standard library. All bundled fixtures are synthetic: they use generic Pillars A/B/C, fictitious sensors and cues, and generic acronym examples. They must not contain applicant-specific science, names, target-program details, local paths, or protected research content.

## Contents

- `SKILL.md`: skill discovery metadata and route selector.
- `agents/openai.yaml`: UI metadata and default explicit invocation.
- `references/`: route-specific runtime modules, including exact bare Sprint.
- `references/industry-resume.md`: opt-in industry-resume Gates 0-8,
  evidence/provenance, prompt, artifact, privacy, and release contract.
- `skill-package-manifest.json`: deterministic hashes for the complete staged
  package, excluding only the manifest itself and transient Python caches.
- `schemas/gatedsprint-state.schema.json`: versioned state and release-sidecar schema.
- `schemas/industry-resume-analysis.schema.json`: route-neutral structured JD,
  evidence, gap, audit, and dashboard contract for enhanced industry resumes.
- `scripts/validate_gatedsprint_state.py`: deterministic schema and cross-record invariant validator.
- `scripts/validate_industry_resume_analysis.py`: strict structured-analysis
  validator, canonical privacy-minimized audit-package renderer, and optional
  compact Markdown dashboard renderer.
- `scripts/build_skill_manifest.py`: write or verify the package manifest.
- `tests/test_state_validation.py`: state-transition, source-binding, approval, implementation, and exact-artifact regression tests.
- `tests/test_industry_resume_validation.py`: synthetic unit, boundary,
  failure-mode, and end-to-end industry-resume checks.
- `evals/cases.json`: the versioned 33-case behavioral catalog.
- `evals/fixtures/`: synthetic catalog inputs with file hashes bound in the catalog.
- `scripts/run_gatedsprint_evals.py`: expectation-free prepare/capture/grade harness with externally keyed execution receipts. It never calls a model and never treats an unexecuted or untrusted case as a pass.

## Validation

From the repository root:

```bash
python3 /path/to/skill-creator/scripts/quick_validate.py plugins/gated-sprint/skills/gated-sprint
python3 plugins/gated-sprint/skills/gated-sprint/scripts/build_skill_manifest.py verify
python3 -m unittest discover -s plugins/gated-sprint/skills/gated-sprint/tests -p 'test_*.py'
python3 plugins/gated-sprint/skills/gated-sprint/scripts/validate_industry_resume_analysis.py \
  --analysis plugins/gated-sprint/skills/gated-sprint/tests/fixtures/industry-resume-e2e.json \
  --bundle-root plugins/gated-sprint/skills/gated-sprint/tests/fixtures/industry-resume-e2e-files
python3 plugins/gated-sprint/skills/gated-sprint/scripts/run_gatedsprint_evals.py validate
```

The first command validates the skill package structure. The second verifies
the complete package manifest. The third exercises both state engines against
bundled valid and invalid fixtures. The fourth validates a deterministic
mocked-evaluator/drafter golden run, including the real hashes and placement of
its synthetic sources, generated resume, and audit package. It does not call an
external model. The fifth validates the behavioral catalog, schema, artifact
hashes, and JSON selectors.

The industry-resume validator emits exactly one JSON result object on stdout,
a concise summary on stderr, and exit status `0` for pass, `1` for invariant
failure, or `2` for malformed input/invocation error. Use `--dashboard <path>`
to write the deterministic human-readable gate and coverage dashboard. Use
`--bundle-root <path>` when the relative source and output files are available
to verify safe paths, existence, exact SHA-256 values, and the presence of each
recorded requirement/evidence/claim excerpt in its bound source text rather
than trusting artifact metadata alone. It also proves one-to-one atomic
coverage of baseline-to-current claim/removal deltas and byte-for-byte equality
of `MARKDOWN_AUDIT_PACKAGE` with `build_audit_package()`. The renderer binds the
complete structured sidecar by digest while protecting candidate free text and
normalizing only the Markdown package's self-referential output hash.
Successful final AI/ATS `RELEASE` and `SELF_DRIVING` cycles require this check.

## Behavioral evaluation lifecycle

The harness separates execution inputs from grading expectations and uses an
external runner-controlled HMAC key. The key path is a command input only and
is never persisted in packets, captures, records, or suite reports.

1. `prepare --case E-01 --run-id ... --issued-at ... --expires-at ...` emits an expectation-free packet signed for one run, one execution window, one trusted runner identity/provenance, and the externally supplied current skill version/hash.
2. Run the system under evaluation outside this harness.
3. `new-capture --packet <packet.json>` verifies that issuance and creates a post-run capture and independent-grader template.
4. After the runner has captured the completed turn, `seal-capture --packet <packet.json> --capture <capture.json> --captured-at ...` signs the capture payload and binds it to the exact prepared-packet hash.
5. `grade --capture <sealed.json>` verifies the receipt against the external key, trusted runner, and current skill before applying deterministic and cited qualitative checks.
6. `record` refuses an unsealed, tampered, stale-skill, wrong-runner, or out-of-window capture, then binds a verified capture to current catalog, schema, and fixture hashes.
7. `suite --records-dir <records>` re-verifies every record and receipt before enforcing required one-shot, hard-invariant, and user-requirement coverage.

A suite pass requires real, externally sealed recorded runs. Raw captures and
self-authored receipt objects cannot be recorded or counted. Catalog validation
alone does not imply behavioral success. All JSON inputs reject duplicate keys
and non-finite numeric constants. Captures/records also reject embedded local
paths and file URLs; RFC 6901 pointers are exempt only in explicit selector or
validated RFC 6902 patch contexts.

## Release-byte and diff verification

For `ready-to-release`, pass `--source-root` and `--artifact-root` (or use the
baseline/candidate manifest directories as their defaults). The validator
resolves and re-hashes the current authoritative source and exact candidate
bytes. For TXT/MD artifacts, the diff map uses
`comparison_mode: UTF8_TEXT_LINES`, zero-based half-open line spans, and hashes
of both line slices. For PDF, DOCX, and other binary artifacts it uses
`comparison_mode: BINARY_BYTES`, zero-based half-open byte spans, and hashes of
the exact byte slices. The historical JSON field names `baseline_lines_hash`
and `candidate_lines_hash` are retained for compatibility in both modes. The
validator derives canonical non-equal line opcodes for TXT/MD. For binary
artifacts, it validates the declared monotone byte spans directly in linear
time: unchanged gaps must be byte-identical, replacement bounds must not
absorb stable edge bytes, directly adjacent hunks are boundary-checked as one
composite edit, and large comparisons and slice hashes are processed in
bounded chunks. Both modes re-hash the full artifacts and every mapped
slice and require exact authorized coverage; missing, overlapping, extra,
stable-edge-overbroad, or stale hunks fail closed with `STATE.DIFF_COVERAGE`.
This linear binary proof establishes complete byte coverage, not a globally
minimal edit script; a hunk with different boundary bytes may include an
unchanged interior. Byte-exact coverage does not establish semantic or layout
equivalence, so applicable qualitative attestations remain required.

## Maintenance invariants

- Keep the runtime standard-library-only.
- Update every catalog artifact hash after changing a referenced fixture.
- Preserve expectation-free execution packets; expected and forbidden behavior belong only in post-run grading.
- Keep receipt keys outside stored evaluation artifacts, and supply the current skill version/hash and trusted runner identity/provenance independently at every verification boundary.
- Canonical dependency references are approval-fingerprinted. Every USER `APPROVED` or `AUTHORIZED` transition must also record `details.source_binding_hash`, the canonical hash of all implementation-controlling source-binding fields active at that event; current-source authorization rechecks that exact hash.
- Lock scope matching is conservative and token-boundary aware: either contiguous scope phrase can be the broader parent, so a lock on `Future program` also covers `Future program opening` unless the lock is explicitly released.
- Keep this complete staged package as the canonical skill source. Install the
  exact package, verify the manifest at both locations, and treat legacy
  workflow documents only as adapters/supporting references.
- Keep fixtures synthetic and repository-neutral.
