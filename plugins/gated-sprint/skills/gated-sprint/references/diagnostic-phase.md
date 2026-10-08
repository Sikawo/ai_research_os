# Diagnostic phase (`DIAGNOSE` / Phase 1)

Use this module only for diagnostic work. Phase 1 is source-read-only and approval-gated: it may quote short excerpts or show a short illustrative rewrite, but it must not create a clean revised application artifact.

Read [core-invariants.md](core-invariants.md), [deliverable-routing.md](deliverable-routing.md), and [review-rubrics.md](review-rubrics.md) first. Load [figures-and-layout.md](figures-and-layout.md) only when visuals, rendering, or file authority are in scope, and [decision-state.md](decision-state.md) when recording proposals or persistent state.

## 1. Register the run

Record:

- operation, depth, urgency, document type, and declared scope;
- current authoritative source(s) and fingerprints when available;
- content authority, layout authority, and editable target as separate fields;
- official criteria/constraints and their authority;
- active locks and approved decisions still valid for this source;
- included and excluded documents/sections;
- missing evidence, unresolved version relationships, and affected judgments; and
- each candidate gate/score dimension as `APPLICABLE`, `NOT_APPLICABLE`, or `NOT_ASSESSABLE` before evaluation.

Do not ask again for material already supplied. Proceed on available material where safe; mark excluded or unsupported scopes rather than blocking an otherwise useful diagnostic.

## 2. Build the current-source packet and cold pass

Create the bounded packet defined in [core-invariants.md](core-invariants.md). For `FULL` or high-stakes review, run the blind protocol before reading the user's explanation of intended meaning.

From only the current artifact and applicable official criteria, reconstruct:

- scientific identity or document purpose;
- strongest accomplishment/contribution;
- current conceptual advance;
- future organizing question/direction;
- primary reason the work matters;
- relationship among major projects/documents;
- independence/ownership when relevant; and
- one idea likely retained five minutes later, one likely confusion, and one likely forgotten component.

Record what is visible, absent, buried, ambiguous, or unsupported. Later reconcile the cold reconstruction with the intended story and evidence boundary; do not let later explanation retroactively rescue a failed artifact surface.

## 3. Reconstruct the intended and text-supported scientific models

For scientific narratives, separate:

- established observation/evidence;
- interpretation;
- causal model and its evidentiary strength;
- unresolved anomaly, limitation, or gap;
- hypothesis or organizing question;
- proposed tests/experiments;
- assumptions and dependencies;
- alternative explanations; and
- expected knowledge gain.

Compare the applicant's intended trajectory with what the current text supports. Preserve tracked-change/comment intent unless it conflicts with evidence, official requirements, or current user instruction.

Create a compact claim–evidence–inference ledger only for central claims, major figures, and high-risk ownership/independence statements. For each, capture the exact claim, status, strongest evidence/source, relevant biological/system limits, causal versus associative status, publication/preliminary/proposed status, ownership, wording ceiling, likely reader inference, and where the claim appears. Check both `claim → evidence → boundary` and `major evidence/figure → conclusion → program consequence`.

## 4. Inventory major units before scoring

Identify reader-entry scientific/evaluative blocks—not every paragraph. Use source anchors. For each applicable unit record:

- unit name and anchor;
- motivating problem/question or required evaluative function;
- specific stakes/consequence;
- supported originality/delta where relevant;
- first visible location of each function;
- the reader's one-sentence reconstruction from the heading plus opening one to three sentences;
- result: `PASS`, `LATE`, `GENERIC`, `AMBIGUOUS`, `ABSENT`, `NOT_APPLICABLE`, or `NOT_ASSESSABLE`; and
- smallest sufficient action or `Keep`.

Run the exact unit matrix and failure rules in [review-rubrics.md](review-rubrics.md). Detailed body text cannot rescue a failed opening-surface result.
Keep the full inventory internal unless the user asks for it; summarize only entries that reveal a material failure so the output does not become another checklist.

## 5. Run the hard gates

For a routed industry `RESUME` with `industry_resume.ai_ats_mode=true`, use
[industry-resume.md](industry-resume.md) as the role-specific hard-gate
sequence. In `DIAGNOSE`, run Gates 0-3 against the bounded JD, authorized
candidate sources, and current resume; run Gates 4-8 against the exact current
resume when its bytes or faithful extracted representation are available.
Produce the requirement IDs, evidence matrix, gap classes, gate results, and
proposed revision IDs, but do not create a clean revised resume. Gate 5 receives
only the current resume and the normalized job requirements; evidence sources
used by Gates 1-3 must not leak into that simulation.

Evaluate in precedence order:

1. scientific/factual/ethical integrity and claim support;
2. current-source/content authority;
3. applicable Motivation-and-Significance-First retrieval;
4. importance, originality, and strongest-defensible-claim boundaries;
5. logical simplicity and organization;
6. cumulative edit-set simplicity when comparing a revision with a baseline;
7. visual role/coverage when applicable; and
8. official compliance to the extent assessable.

Do not score the document into readiness before these gates. Record failures, the concrete reader consequence, and the minimum intervention that would actually resolve them.

## 6. Diagnose architecture and page budget only as needed

Start with the current architecture as Candidate 0, but give it no presumption of adequacy after a material gate failure.

- Generate an alternative only when a defined gate fails and structural change could solve it.
- Zero alternatives is valid.
- Show only alternatives that materially outperform Candidate 0.
- Treat interacting local edits that change emphasis as one structural decision.
- Apply the zero-based test: if removing a paragraph, figure, or detail would not materially weaken an official criterion, central story function, evidence boundary, or necessary specialist credibility, consider removal, compression, relocation, or appendix treatment.

For each viable alternative, state the solved failure, preserved intent, lost nuance, page/figure cost, scientific/voice risk, and why local repair is insufficient.

## 7. Apply relevant reviewer functions

Select only reviewer functions useful for the declared document and scope. A full/high-stakes review should normally include:

- domain specialist;
- adjacent/cross-disciplinary scientist;
- accomplishments/independence or target-equivalent reviewer;
- tired decision-maker/committee reader; and
- compliance/factual-integrity reviewer.

Add sponsor-, leadership-, training-, recommendation-, or document-specific functions only when relevant. Do not emit repetitive personas. Reconcile disagreements using [core-invariants.md](core-invariants.md); keep conflicting material evidence visible.

For independent-investigator materials, assess intellectual ownership, contribution ownership, differentiation from mentors/collaborators, operational portability, and capacity for trainee-owned projects separately. Ask internally whether the core question and first launchable project remain recognizable without a mentor or one unique external resource. Collaboration is not itself a weakness, and the prose does not need R01-style contingency catalogs.

## 8. Run tired-reader and prose reviews

Run both independent tired-reader components in [review-rubrics.md](review-rubrics.md): rapid salience/reconstruction and sequential comprehension/friction. Neither compensates for failure of the other.

For applicable substantive prose, assess separately:

- natural prose and structure;
- confident, proportionate tone;
- importance/motivation visibility;
- originality visibility; and
- logical simplicity and organization.

Use evidence-backed scores only after hard gates. For focused review, score
only the declared applicable scope. For CV or resume list entries, standalone
figures, and non-prose units, use role-specific checks rather than forcing
prose scores. For an enhanced industry resume, the top-third, recruiter-scan,
hiring-manager, parse, coverage, and integrity results replace generic
narrative scoring where they conflict.

## 9. Convert findings into decisions

Classify content internally as `Keep`, `Reframe`, `Move`, `Compress`, `Remove`, `Needs evidence`, or `Needs user decision`. Name protected strengths explicitly, but do not convert them into user locks automatically.

Create decision IDs only for material changes. Keep risk color (`GREEN|YELLOW|RED`), domain risk, strategic necessity (`ESSENTIAL|HELPFUL|OPTIONAL`), support status, recommendation, and decision state separate. `SPECIALIST_REVIEW_REQUIRED` must name the specialist concern and a safer alternative. Use [decision-state.md](decision-state.md) for complete records and legal states.

Recommendations must:

- address a demonstrated root cause rather than accumulate symptomatic caveats;
- preserve the verified claim ceiling and user intent;
- state reader benefit, risk/lost nuance, evidence assumptions, and page/figure effect;
- compare against the current baseline when a revision is proposed;
- strengthen supported central claims when understatement is costly;
- block unsupported content rather than labeling it merely high-risk; and
- prefer move, replace, compress, or delete before adding prose when those actions solve the problem.

Pure stylistic taste is not a decision item. A strong passage should receive `Keep`, not a novelty rewrite.

## 10. Deliver the Phase 1 packet

Internal analysis may be comprehensive; user-facing output should be decision-efficient:

1. current source, authority, scope, and missing-input summary;
2. one-screen dashboard with route, hard-gate results, and readiness;
3. cold-reader reconstruction and material intended/text-supported gaps;
4. integrity/compliance blockers;
5. the top three `ESSENTIAL` decisions in full detail, or all of them if fewer than three exist;
6. concise index of all remaining material issues/IDs;
7. one recommended compatible decision package;
8. protected strengths/items not to disturb;
9. unresolved evidence or authority questions; and
10. optional appendix for detailed rubrics and lower-priority findings.

For an enhanced industry resume, the packet must also identify the structured
analysis artifact, critical missing requirement IDs, `TRUE_GAP`, `RESUME_GAP`,
and `POSITIONING_GAP` items, and the exact Gates 0-8 results. Never summarize
these as a proprietary ATS prediction or a single opaque match percentage.

The top-three display prioritizes; it does not hide other material issues. Show architecture candidates only when the architecture gate failed and a superior alternative exists.

End by asking the user to approve, modify, discuss, hold, or reject identified decisions. Do not create a clean revised artifact or imply that a predicted revision has already passed.
