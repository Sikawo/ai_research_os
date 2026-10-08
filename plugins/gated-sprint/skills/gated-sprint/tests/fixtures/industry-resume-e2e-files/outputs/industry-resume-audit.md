# Industry Resume AI/ATS Audit Package

Generated deterministically from the hash-bound structured sidecar. Private candidate excerpts remain in that protected sidecar and are not repeated here.

## Route And Binding

- Workflow version: `2.1.0`
- Run ID: `RUN-INDUSTRY-001`
- Execution: `GATEDSPRINT` / `RELEASE`
- Overall status: `PASS_WITH_WARNINGS`
- Current resume source: `SRC-CURRENT`
- Current resume hash: `sha256:e4a2653681ec78afd9af79fe4ef7468caee3192ffaaa25e17767d64742dca94b`
- Structured audit binding SHA-256: `cc8077f88c98393183467ad99b84a77259cecc7abc0b3847b42dd3abe68e2fd7`

## Job Description Analysis

| Requirement | Priority | Category | Screenable | Source | Source location | Concepts | Exact terms |
|---|---|---|---:|---|---|---|---|
| REQ-001 | required | leadership | true | SRC-JD | Responsibilities, item one | assay development, leadership | cross-functional, assay development |
| REQ-002 | required | method | true | SRC-JD | Requirements, item one | design of experiments, process optimization | design of experiments |
| REQ-003 | preferred | regulatory | true | SRC-JD | Preferred qualifications, item one | regulated production, analytics | regulated production analytics |
| REQ-004 | required | responsibility | true | SRC-JD | Requirements, item two | technology transfer | technology transfer |
| REQ-005 | preferred | communication | true | SRC-JD | Responsibilities, item two | technical communication, partner teams | communicate technical decisions |

## Eligibility Results

| Requirement | Classification | Evidence IDs | True gap |
|---|---|---|---:|
| REQ-001 | met | EV-001 | false |
| REQ-002 | probably_met_but_not_explicit | EV-002-SOURCE | false |
| REQ-003 | partial | EV-003 | true |
| REQ-004 | not_met | EV-004 | true |
| REQ-005 | met | EV-005 | false |

## Requirement Evidence Matrix

| Requirement | Evidence | Candidate facts | Source | Source location binding | Excerpt binding | Status | Level | Resume visibility | Alignment | Action | Confidence |
|---|---|---|---|---|---|---|---:|---|---|---|---|
| REQ-001 | EV-001 | FACT-001 | SRC-CURRENT | PROTECTED_SIDECAR_VALUE | HASH_BOUND_SIDECAR_EXCERPT | strong | 3 | explicit | DIRECT | keep | high |
| REQ-002 | EV-002-RESUME | FACT-002 | SRC-CURRENT | PROTECTED_SIDECAR_VALUE | HASH_BOUND_SIDECAR_EXCERPT | strong | 3 | explicit | DIRECT | keep | high |
| REQ-002 | EV-002-SOURCE | FACT-002 | SRC-PROFILE | PROTECTED_SIDECAR_VALUE | HASH_BOUND_SIDECAR_EXCERPT | strong | 3 | missing | DIRECT | add_if_true | high |
| REQ-003 | EV-003 | FACT-003 | SRC-CURRENT | PROTECTED_SIDECAR_VALUE | HASH_BOUND_SIDECAR_EXCERPT | partial | 2 | explicit | ADJACENT | leave_as_gap | medium |
| REQ-004 | EV-004 | — | — | NONE | NONE | absent | 0 | missing | NONE | leave_as_gap | high |
| REQ-005 | EV-005 | FACT-005 | SRC-CURRENT | PROTECTED_SIDECAR_VALUE | HASH_BOUND_SIDECAR_EXCERPT | strong | 3 | explicit | DIRECT | move_higher | high |

## Terminology And Revision Plan

| Alignment | Requirement | Relationship | Evidence IDs | Current term binding | Proposed wording binding | Approved for revision |
|---|---|---|---|---|---|---:|
| ALIGN-001 | REQ-001 | EXACT | EV-001 | PROTECTED_SIDECAR_VALUE | PROTECTED_SIDECAR_VALUE | true |
| ALIGN-002 | REQ-002 | SUPPORTED_SYNONYM | EV-002-SOURCE | PROTECTED_SIDECAR_VALUE | PROTECTED_SIDECAR_VALUE | true |
| ALIGN-003 | REQ-003 | NOT_EQUIVALENT | EV-003 | PROTECTED_SIDECAR_VALUE | NONE | false |
| ALIGN-004 | REQ-004 | CONTEXTUAL_ONLY | EV-004 | NONE | NONE | false |
| ALIGN-005 | REQ-005 | SUPPORTED_SYNONYM | EV-005 | PROTECTED_SIDECAR_VALUE | PROTECTED_SIDECAR_VALUE | true |

## Qualification Results

| Requirement | Classification | Evidence IDs | Confidence |
|---|---|---|---|
| REQ-001 | MET | EV-001 | high |
| REQ-002 | MET | EV-002-RESUME | high |
| REQ-003 | PARTIAL | EV-003 | medium |
| REQ-004 | NOT_FOUND | — | high |
| REQ-005 | MET | EV-005 | high |

## Evidence Coverage

| Surface | Met / Level 3-4 | Partial / Level 2 | Not found / Level 0-1 | Total |
|---|---:|---:|---:|---:|
| Required qualifications | 2 | 0 | 1 | 3 |
| Preferred qualifications | 1 | 1 | 0 | 2 |
| Evidence strength | 3 | 1 | 1 | 5 |

- Critical missing requirement IDs: `REQ-004`
- Opaque overall match percentage: prohibited

## Gap Report

| Gap | Requirement | Category | Resolution | Evidence IDs | Action |
|---|---|---|---|---|---|
| GAP-002 | REQ-002 | RESUME_GAP | RESOLVED | EV-002-SOURCE | add_if_true |
| GAP-003 | REQ-003 | TRUE_GAP | OPEN | EV-003 | leave_as_gap |
| GAP-004 | REQ-004 | TRUE_GAP | OPEN | EV-004 | leave_as_gap |
| GAP-005 | REQ-005 | POSITIONING_GAP | RESOLVED | EV-005 | move_higher |

## Gate Results

| Gate | Name | Enabled | Status | Blocking | Finding count |
|---|---|---:|---|---:|---|
| GATE_0 | JD decomposition | true | PASS | false | 0 |
| GATE_1 | Eligibility | true | PASS_WITH_WARNINGS | false | 1 |
| GATE_2 | Evidence mapping | true | PASS_WITH_WARNINGS | false | 1 |
| GATE_3 | Semantic alignment | true | PASS_WITH_WARNINGS | false | 1 |
| GATE_4 | ATS parse | true | PASS | false | 0 |
| GATE_5 | AI recruiter | true | PASS_WITH_WARNINGS | false | 1 |
| GATE_6 | Recruiter scan | true | PASS | false | 0 |
| GATE_7 | Hiring manager | true | PASS | false | 0 |
| GATE_8 | Integrity | true | PASS | false | 0 |

## Exact Candidate Audits

### Gate 4 — ATS Extraction

| Field | Value |
|---|---|
| Status | PASS |
| Resume source | SRC-CURRENT |
| Resume hash | sha256:e4a2653681ec78afd9af79fe4ef7468caee3192ffaaa25e17767d64742dca94b |
| Actual extraction performed | true |
| Logical order compared | true |
| Extraction method | TEXT_INPUT |
| OCR used | false |
| OCR reason | — |
| Chronology | PASS |
| Reading order | PASS |
| Critical text loss count | 0 |
| Anomaly count | 0 |

#### ATS Field Recovery

| Field | Recovery |
|---|---|
| candidate_name | RECOVERED |
| contact_information | RECOVERED |
| dates | RECOVERED |
| education | RECOVERED |
| employers | RECOVERED |
| job_titles | RECOVERED |
| publications | NOT_APPLICABLE |
| section_headings | RECOVERED |
| skills | RECOVERED |

### Gate 5 — AI Recruiter Qualification

| Field | Value |
|---|---|
| Status | PASS_WITH_WARNINGS |
| Evaluated resume source | SRC-CURRENT |
| Evaluated resume hash | sha256:e4a2653681ec78afd9af79fe4ef7468caee3192ffaaa25e17767d64742dca94b |
| Hidden context used | false |
| Qualification requirement IDs | REQ-001, REQ-002, REQ-003, REQ-004, REQ-005 |

### Gate 6 — Human Recruiter Scan

| Field | Value |
|---|---|
| Status | PASS |
| Evaluated resume source | SRC-CURRENT |
| Evaluated resume hash | sha256:e4a2653681ec78afd9af79fe4ef7468caee3192ffaaa25e17767d64742dca94b |
| Rating | STRONG |
| Target role recovered | true |
| Seniority recovered | true |
| Top capabilities | 3 protected values |
| Target connection obvious | true |
| Wrong identity signal | false |
| Relevant terms visible early | true |
| Easy to skim | true |

### Gate 6 — Top-Third Scan

| Field | Value |
|---|---|
| Status | PASS |
| Evaluated resume source | SRC-CURRENT |
| Evaluated resume hash | sha256:e4a2653681ec78afd9af79fe4ef7468caee3192ffaaa25e17767d64742dca94b |
| Rating | STRONG |
| Target role represented | true |
| Top domains | 5 protected values |
| Scientific identity | PROTECTED_SIDECAR_VALUE |

### Gate 7 — Hiring Manager Review

| Field | Value |
|---|---|
| Status | PASS |
| Evaluated resume source | SRC-CURRENT |
| Evaluated resume hash | sha256:e4a2653681ec78afd9af79fe4ef7468caee3192ffaaa25e17767d64742dca94b |
| Rating | STRONG |
| Target context | SCIENTIFIC_TECHNICAL |
| Technical depth | STRONG |
| Ownership clear | true |
| Claims credible | true |
| Generic after optimization | false |

#### Hiring Manager Dimensions

| Dimension | Applicability | Rating | Evidence binding |
|---|---|---|---|
| claim_credibility | APPLICABLE | STRONG | PROTECTED_SIDECAR_VALUE |
| collaboration | APPLICABLE | STRONG | PROTECTED_SIDECAR_VALUE |
| depth | APPLICABLE | STRONG | PROTECTED_SIDECAR_VALUE |
| development | APPLICABLE | STRONG | PROTECTED_SIDECAR_VALUE |
| independence | APPLICABLE | STRONG | PROTECTED_SIDECAR_VALUE |
| innovation | APPLICABLE | STRONG | PROTECTED_SIDECAR_VALUE |
| leadership | APPLICABLE | STRONG | PROTECTED_SIDECAR_VALUE |
| mechanistic_thinking | APPLICABLE | STRONG | PROTECTED_SIDECAR_VALUE |
| output_relevance | APPLICABLE | STRONG | PROTECTED_SIDECAR_VALUE |
| ownership | APPLICABLE | STRONG | PROTECTED_SIDECAR_VALUE |
| rigor | APPLICABLE | STRONG | PROTECTED_SIDECAR_VALUE |
| specificity | APPLICABLE | STRONG | PROTECTED_SIDECAR_VALUE |
| translation | APPLICABLE | STRONG | PROTECTED_SIDECAR_VALUE |

### Gate 8 — Integrity Review

| Field | Value |
|---|---|
| Status | PASS |
| Evaluated resume source | SRC-CURRENT |
| Evaluated resume hash | sha256:e4a2653681ec78afd9af79fe4ef7468caee3192ffaaa25e17767d64742dca94b |
| Unsupported claim IDs | — |
| Inflated ownership claim IDs | — |
| Inflated seniority claim IDs | — |
| Invented metric claim IDs | — |
| Unsupported direct-experience claim IDs | — |
| Semantic drift claim IDs | — |
| Caveat-loss claim IDs | — |
| Keyword stuffing | false |
| JD mimicry concern count | 0 |
| Duplicated-concept finding count | 0 |
| Related-vs-direct ambiguity count | 0 |

## Claim Provenance

| Claim | Revision relationship | Requirements | Candidate facts | Evidence IDs | Support | Represents met | Baseline source |
|---|---|---|---|---|---|---:|---|
| CLAIM-001 | STRENGTHENED | REQ-001 | FACT-001 | EV-001 | SUPPORTED | true | SRC-BASELINE |
| CLAIM-002 | INTRODUCED | REQ-002 | FACT-002 | EV-002-SOURCE, EV-002-RESUME | SUPPORTED | true | — |
| CLAIM-003 | UNCHANGED | REQ-003 | FACT-003 | EV-003 | SUPPORTED | false | SRC-BASELINE |
| CLAIM-005 | UNCHANGED | REQ-005 | FACT-005 | EV-005 | SUPPORTED | true | SRC-BASELINE |
| CLAIM-SUMMARY | STRENGTHENED | REQ-001, REQ-005 | FACT-001, FACT-005 | EV-001, EV-005 | SUPPORTED | true | SRC-BASELINE |

## Authorized Removals

| Removal | Requirements | Baseline source | Baseline hash | Authorization verified | Reason binding |
|---|---|---|---|---:|---|

## Evaluator Runs

| Evaluator run | Gate | Status | Attempts | Retries | Failure type |
|---|---|---|---:|---:|---|
| EVAL-AI-RECRUITER | GATE_5 | SUCCEEDED | 1 | 0 | NONE |
| EVAL-ATS | GATE_4 | SUCCEEDED | 1 | 0 | NONE |
| EVAL-EVIDENCE-MAPPING | GATE_2 | SUCCEEDED | 1 | 0 | NONE |
| EVAL-HIRING-MANAGER | GATE_7 | SUCCEEDED | 1 | 0 | NONE |
| EVAL-INTEGRITY | GATE_8 | SUCCEEDED | 1 | 0 | NONE |
| EVAL-JD-DECOMPOSITION | GATE_0 | SUCCEEDED | 1 | 0 | NONE |
| EVAL-RECRUITER-SCAN | GATE_6 | SUCCEEDED | 1 | 0 | NONE |
| EVAL-SEMANTIC-ALIGNMENT | GATE_3 | SUCCEEDED | 1 | 0 | NONE |

## Revision And Artifact Record

| Field | Value |
|---|---|
| Revision cycle | 2 |
| Maximum revision cycles | 3 |
| Revisions applied | true |
| Authorization verified | true |

### Output Artifacts

| Artifact | Path | Format | SHA-256 | Status |
|---|---|---|---|---|
| FINAL_RESUME | outputs/final-resume.txt | TXT | sha256:e4a2653681ec78afd9af79fe4ef7468caee3192ffaaa25e17767d64742dca94b | CREATED |
| MARKDOWN_AUDIT_PACKAGE | outputs/industry-resume-audit.md | MD | &lt;SELF_HASH_NORMALIZED&gt; | CREATED |
