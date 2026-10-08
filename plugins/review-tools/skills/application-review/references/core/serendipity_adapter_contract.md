# Scientific Serendipity Adapter Contract

## Purpose

Resolve document/task behavior before scientific exploration while keeping the
generic Application Review OS reusable. Protected application adapters may opt
in only under later approved specs; this contract does not modify or authorize
their contents.

## Configuration

Use this repository-native Markdown/YAML-style block or a semantically
equivalent adapter representation:

```yaml
serendipity_mode: full | narrative_only | off
default_exploration_depth: light | standard | deep
document_maturity: explore | build | converge | lock | infer
change_risk_classes_allowed: [green, yellow, red]
domain_risk_statuses: [none, specialist_review_required, cleared]
persistent_serendipity_memory: yes | no | approval_required
external_novelty_verification: not_requested | allowed | required_before_claim
personal_cross_pollination: disabled
```

`narrative_only` may improve organization and reader comprehension but may not
generate or claim new scientific models. `off` bypasses the core. External
novelty verification never runs automatically.

## Defaults

| Document/task | Mode | Depth | Maturity | Required behavior |
| --- | --- | --- | --- | --- |
| Grant or research proposal | `full` | `standard` | `infer` | Prioritize significance, mechanistic coherence, aim integration, predictions, feasibility, and defensibility. Proposal Completeness, Significance, and Citation Gate stays before scientific architecture selection. |
| Fellowship | `full` | `standard` | `infer` | Also test trainee ownership, training logic, career-stage feasibility, and scope. |
| Manuscript | `full` | `standard` | `infer` | Never rewrite Results to fit a model; separate demonstrated results from Discussion interpretation; preserve anomalies and qualify new mechanisms. |
| Research statement/scientific vision | `full` | `standard` | `infer` | Integrate across authorized projects without inventing unperformed work. |
| Pure research ideation/hypothesis development | `full` | `deep` | `explore` | Retain more seeds while preserving all coherence and evidence labels. |
| CV/resume | `off` | `light` | `infer` | Never invent conceptual novelty. |
| Cover letter | `narrative_only` | `light` | `infer` | Keep every scientific claim source-based. |
| Recommendation letter | `narrative_only` | `light` | `infer` | Never manufacture interpretations, achievements, or novelty. |
| Other non-scientific document | `off` | `light` | `infer` | Remain off unless a future explicit adapter defines a valid use case. |

Document classification controls these defaults; keywords do not authorize
protected source access. Explicit, valid adapter settings may narrow behavior.
They may not weaken coherence, evidence, privacy, phase, Red-change,
unresolved-domain-risk, or human-owner gates.

## Exploration Depth Resolution

- `LIGHT`: wording-focused task, near-lock document, fixed scientific structure,
  or low expected conceptual value.
- `STANDARD`: substantive scientific Sprint/GatedSprint default.
- `DEEP`: early proposal design, explicit ideation, a major unexplained anomaly,
  coherent-but-generic story, or multiple evidence-compatible models.

Users normally do not select operators or depth. The orchestrator resolves them
from the adapter, maturity, anomaly burden, and task. Depth changes breadth, not
safety.

## Persistence And Access

`yes` permits a scoped memory update; `no` keeps artifacts run-local;
`approval_required` prepares a proposed update without writing it. Persistent
memory never broadens future read scope. Personal Cross-Pollination is disabled
unless a future run explicitly authorizes named sources.
