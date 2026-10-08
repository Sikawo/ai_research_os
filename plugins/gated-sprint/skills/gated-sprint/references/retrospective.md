# Retrospective and calibration

Load for `RETROSPECT`. Do not enter diagnostic/edit phases or rewrite a submitted artifact unless the user separately asks.

## Purpose

Explain where the workflow's prediction diverged from actual reviewer/user experience, identify the smallest generalizable process change, and turn demonstrated failures into regression evidence without contaminating the generic skill with case-specific science.

## Analysis record

For each material observation, record:

- prior workflow prediction, score, or recommendation;
- actual external feedback or observed usability problem;
- the exact mismatch;
- which gate/test failed to detect it;
- root cause rather than downstream wording symptoms;
- whether the lesson is case-specific, target-specific, generic, or still a hypothesis;
- proposed skill/process change;
- regression case and forbidden behavior;
- evidence still needed.

External feedback is calibration evidence, not automatically ground truth about scientific facts. Separate a reader's communication failure from factual or strategic disagreement.

## Promotion rule

Promote a lesson into the generic core only when it expresses a reusable failure mode and survives a negative control. Otherwise place it in a target/applicant overlay or a regression fixture.

Examples:

- A designated overview that omitted one program-defining branch becomes the
  generic missing-program-pillar test, not a content-specific instruction.
- `all internal scores were 5/5 but motivation was unclear` becomes retrieval-before-rating and hard-gate calibration.
- `a simple cover letter became cluttered after many defensible edits` becomes cumulative edit-set testing, not a universal short-letter word limit.
- `generated Word PDF differed from submitted PDF` becomes source/layout authority separation, not a ban on rendering.

## Retrospective output

Return:

1. observed failure and consequence;
2. root-cause diagnosis;
3. what should remain unchanged;
4. proposed core/overlay/eval changes;
5. risks of overcorrecting;
6. evidence needed for unresolved hypotheses;
7. implementation-ready change list when requested.

Do not claim the workflow is fixed until the change is implemented and passes the original regression plus a negative/held-out control.
