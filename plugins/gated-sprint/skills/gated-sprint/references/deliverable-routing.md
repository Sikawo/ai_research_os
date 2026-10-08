# Deliverable and operation routing

Use this registry before evaluating content. Route on four independent axes and record gate/score applicability before review.

## 1. Execution policy, routing axes, and precedence

Resolve execution policy before applying the GatedSprint axes:

- exact, otherwise unqualified `Sprint`, or an explicit request for the
  established self-driving Sprint: `SPRINT_SELF_DRIVING/FULL/STANDARD`; read
  [sprint-mode.md](sprint-mode.md);
- explicit `GatedSprint`, `$gated-sprint`, approval-gated/staged-sprint
  wording, an active GatedSprint continuation, or an explicit GatedSprint
  phase: use the approval-gated axes below.

`SPRINT_SELF_DRIVING` is an execution policy, not a GatedSprint operation. It
must not be converted to `DIAGNOSE` or stopped at a Phase 1 approval packet.

- `operation`: `DIAGNOSE`, `NEGOTIATE`, `RECEIPT`, `IMPLEMENT`, `RELEASE`, `RETROSPECT`
- `depth`: `FULL`, `FOCUSED`
- `urgency`: `STANDARD`, `TRIAGE`
- `document_type`: `PACKAGE`, `RESEARCH_STATEMENT`, `RESEARCH_PLAN`, `COVER_LETTER`, `RESUME`, `CV`, `RECOMMENDATION_LETTER`, `GRANT_NARRATIVE`, `FELLOWSHIP_NARRATIVE`, `FIGURE`, or `OTHER`

`TRIAGE` overlays an operation; it is not an operation. Phase aliases: Phase 1=`DIAGNOSE`, Phase 2=`NEGOTIATE`, Phase 3=`RECEIPT`, Phase 4=`IMPLEMENT`.

Resolve ambiguity in this order:

1. explicit current-user operation or phase;
2. explicit implementation authorization or release/finalization request;
3. stated deadline or decision limit;
4. explicitly bounded scope; and
5. `DIAGNOSE/FULL/STANDARD` for an otherwise unqualified GatedSprint invocation.

An ordinary grammar request, typo fix, proofreading request, or isolated local edit does not launch GatedSprint unless the user explicitly invokes it or asks to continue an active run.

Filename/version-folder management is a separate operational concern, not a reason by itself to launch GatedSprint. Whenever an authorized operation creates, promotes, archives, or identifies current working files, load [file-versioning.md](file-versioning.md) in addition to the route-specific modules.

## 2. Intent-to-route contract

| User intent | Route | Load | Output and stop |
|---|---|---|---|
| `GatedSprint`, `run GatedSprint`, or approval-gated equivalent without narrower instruction | `DIAGNOSE/FULL/STANDARD` | Core, diagnostic, routing, rubrics; figures when present; state for decisions | Phase 1 packet; no source edit; stop for decisions |
| Exact otherwise-unqualified `Sprint`, or explicit self-driving Sprint | `SPRINT_SELF_DRIVING/FULL/STANDARD` | Core, Sprint mode, routing, rubrics; relevant figure/finalization/versioning modules | Complete the supported self-driving cycle; report automatic changes, proposals, blockers, and exact artifact status |
| Review one section, Aim, claim, or figure | `DIAGNOSE/FOCUSED/STANDARD` | Core plus relevant diagnostic/rubric/document module | Bounded findings/IDs; do not imply whole-document readiness |
| Short deadline or explicit decision cap | Requested operation/depth + `TRIAGE` | Core, authority, this overlay, selected high-impact gates | `SUBMISSION_BLOCKING` / `HIGH_VALUE_SAFE` / `DEFER`; preserve QA time |
| Discuss, approve, reject, hold, or modify existing IDs | `NEGOTIATE` | State and negotiation/implementation plus relevant evidence | Updated ledger/receipt; stop unless implementation is also authorized |
| Summarize authorized set and test compatibility before editing | `RECEIPT` | State, source fingerprints, dependencies/conflicts, negotiation/implementation | No-edit receipt; continue only if already authorized and compatible |
| Apply approved/authorized changes | `IMPLEMENT` | State, negotiation/implementation, relevant document/rubric/figure module | New candidate/diff and verification; no new substantive edits without authorization |
| Check the exact submission version | `RELEASE` | Finalization, state, authority/layout, prior decisions | `VERIFIED`, `UNVERIFIED`, or `NOT_ASSESSABLE` for the exact artifact |
| Review the process or external feedback | `RETROSPECT` | Retrospective and minimum prior evidence | Classified lessons/regression proposals; no rewrite unless separately requested |

## 3. Missing-input behavior

- `DIAGNOSE`: continue on available material when safe; mark excluded scopes and dependent judgments `NOT_ASSESSABLE`.
- `NEGOTIATE`: require identifiable proposal IDs/revisions. Reconstruct only from an authoritative saved ledger; otherwise ask for the missing record.
- `RECEIPT`: require an authorized decision set and matching current source. A mismatch stops before editing and routes affected items to negotiation/revalidation.
- `IMPLEMENT`: require current-source fingerprint match and `AUTHORIZED`, supported, compatible decisions. Otherwise stop without editing.
- `RELEASE`: require the exact candidate artifact and applicable official constraints. Without them return `NOT_ASSESSABLE`, never `VERIFIED`.
- `RETROSPECT`: may use supplied observations, but separate confirmed failure from hypothesis.

Missing layout authority does not necessarily block content review. Use [figures-and-layout.md](figures-and-layout.md) to qualify previews and file relationships.

## 4. Authoritative document-type applicability registry

Later rubrics refine an applicable check but must not broaden it to a document type or unit excluded here.

| Document type | Primary success criteria | Motivation/Significance-First | Special rules |
|---|---|---|---|
| Complete package | Coherent anchor proposition; non-duplicative document roles; factual consistency | Yes, at package and applicable prose-unit levels | Define cross-document contract and visual portfolio |
| Research statement/plan | Accomplishments; specific value/originality; trajectory; independent future program; simple causal logic | Yes, at document, major accomplishment, program, and Aim/project entries | Claim/evidence, independence, program robustness, figures |
| Cover letter | Clear identity; contribution/future direction; main reason to care; fit/leadership where relevant | Yes, at document opening and major functional research blocks | Cumulative simplicity; never use Aim-completeness by default |
| Industry resume | Accurate, target-relevant, machine-recoverable evidence; rapid recruiter fit; credible technical depth | No for ordinary bullets; use top-third identity, qualification evidence, and technical-credibility gates | When `ai_ats_mode=true`, load [industry-resume.md](industry-resume.md) and preserve the GatedSprint/Sprint policy boundary |
| CV | Accurate, current, scannable factual evidence and consistent status/format | No for ordinary entries; only narrative summaries when present | Do not invent context; no prose score for list entries |
| Recommendation letter | Credible relationship; concrete evidence; calibrated comparative judgment; candidate trajectory | At major evaluative blocks where motivation/value is relevant | Preserve recommender voice; do not impose applicant-ownership language mechanically |
| Grant/fellowship narrative | Important problem; supported premise; specific objectives/Aims; approach logic and impact | Yes, at project and Aim/project entries | Apply sponsor criteria; do not import target-specific criteria |
| Standalone figure | Role-specific accuracy, evidence status, legibility, and relation to designated overview | Only when it is an overview/entry surface | Do not infer whole-package readiness |
| Other scientific-career document | Declared function and target criteria | Only for reader-entry scientific/evaluative units | State the chosen analogy and excluded gates |

For every route, explicitly record each candidate gate and score dimension as `APPLICABLE`, `NOT_APPLICABLE`, or `NOT_ASSESSABLE`, with a short reason for the latter two.

## 5. Document-specific operating rules

### Complete package

Define:

- one anchor proposition that may recur deliberately;
- one primary significance statement and up to two secondary consequences;
- the distinct job of each document;
- facts and terms that must match; and
- details that should appear in only one document.

Typical division: cover letter = identity, central idea/discovery, why it matters, relevant fit/leadership/mentoring; research statement = evidence, causal logic, trajectory, independent future program; CV = factual proof, chronology, output, contribution, and status. Each document remains minimally understandable alone, but paragraph-level duplication should be removed.

### Research statement or plan

Apply the opening-surface gate to the document/program opening, major accomplishment/conceptual-advance sections, future-program overview, and each Aim/project. Keep research accomplishments, proposed important problem, and potential for independent trainee-centered leadership distinct when those are target criteria.

Assess:

- past → current → future trajectory;
- completed-work delta versus future-program delta;
- claim/evidence/inference boundaries;
- intellectual and contribution ownership;
- differentiation and resource portability;
- whether projects form a coherent program without hidden serial dependence; and
- the designated overview and figure roles.

Do not turn the statement into an R01 or require exhaustive contingencies merely to display rigor.

### Cover letter

The letter complements rather than compresses the research statement. Before acronym-heavy detail, the opening research block should communicate the problem/prevailing assumption, central contribution or future question, changed understanding, and one primary reason it matters.

Each paragraph should have one dominant function. Flag paragraphs carrying research summary, multiple applications, patent/status, feasibility, fit, and independence simultaneously. Acronyms/framework names must earn their cognitive cost through compression, prediction, or memorability; definition alone is insufficient.

When a simple baseline exists, state the function of every added detail. Compare both each edit and the fully integrated edit set with the baseline. Ask a blind reader to reconstruct the primary message, central contribution, future direction, and main reason to care from both. More checklist items do not make the result better.

### CV

Prioritize factual accuracy, status, chronology, contribution, reference-format consistency, and scanability. Do not force narrative motivation, Aim logic, prose scores, or independent-lab rhetoric onto ordinary list entries. Apply prose/value rubrics only to genuine narrative summaries. When a supplied CV is the user's reference-style authority, preserve that style unless the user requests another.

### Industry resume

Use `RESUME` rather than `CV` for a concise industry-targeted employment
document. When `industry_resume.ai_ats_mode=true`, load
[industry-resume.md](industry-resume.md) and run its ordered Gates 0-8. The
qualification matrix and early-fit surface replace narrative motivation/Aim
gates for ordinary bullets. A resume derived from an academic CV may use the CV
as authorized evidence, but the AI recruiter simulation must see only the
exact current resume. With the mode disabled, retain the legacy career-resume
checks and do not require the enhanced sidecar.

### Recommendation letter

Preserve the recommender's voice and relationship to the candidate. At each applicable evaluative block, require a named quality, concrete evidence, and why that quality matters to the recommendation; require comparative judgment and trajectory only when supported and relevant. Avoid mechanically rewriting the letter in applicant-owned or grant-style language.

### Grant or fellowship narrative

Use current sponsor criteria. Apply the gate at the project and Aim/project entries; test supported premise, objective, approach logic, discriminating knowledge gain, and impact. Maintain evidence/hypothesis/proposed-work distinctions. Do not import a named program's or another target's criteria without authorization.

### Standalone figure

First declare its role. Apply full overview coverage only if it is the designated overview/entry surface. Otherwise test its own question, supported conclusion, evidence status, program relationship, and final-size legibility. Do not require every Aim in a data/evidence figure or infer readiness of unseen prose/package material. Read [figures-and-layout.md](figures-and-layout.md).

### Other declared scientific-career document

State the closest functional analogy, why it fits, which gates apply, and which are excluded. Do not silently import a more demanding document rubric.

## 6. `TRIAGE` urgency overlay

Classify remaining work as:

- `SUBMISSION_BLOCKING`
- `HIGH_VALUE_SAFE`
- `DEFER`

When the constraint is known, state it. Surface approximately three immediate decisions unless a blocker requires more. Establish an architecture/content freeze point, reserve a protected final-QA window, and stop unfinished improvement work when a verified artifact is safer. Explicitly recommend submitting the current verified version when further change has negative expected value.

After the freeze:

- require a targeted diff for every edit;
- re-render after layout-affecting edits;
- invalidate verification for any changed artifact; and
- do not let urgency relax scientific-integrity or authorization gates.

## 7. Scope-safe conclusions

- A focused result applies only to the named scope.
- A content review without authoritative layout cannot certify layout.
- A figure-only review cannot certify a package.
- A CV review cannot establish narrative readiness of the research statement.
- Diagnostic `READY` is not release `VERIFIED` and neither predicts selection.
- When current official criteria are absent, state which judgments remain provisional rather than inventing requirements.
