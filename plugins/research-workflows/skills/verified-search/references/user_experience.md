# Verified Search User Experience

Derived from: `Verified Search Core v1.2.0`

## Experience Goal

Verified Search should feel like ordinary conversation backed by decision-ready verification. The user asks a simple practical question; the system quietly identifies what could make the action succeed or fail, checks the right evidence for the current moment, and returns the best useful next action.

`Rigorous inside, simple outside.`

The v1.2 progression is:

`factual verification -> governing applicability -> decision support -> action readiness`

## What Verified Search Is

- **Hallucination detection** asks whether an answer may contain unsupported material.
- **Fact checking** asks whether a stated claim is supported.
- **Decision-ready verification** asks what the user is trying to do, what could make it fail, what can be established now, what remains unresolved, and what action or re-check plan is safest.

Verified Search includes factual checking but is designed around the third outcome.

## No Mode to Learn

Bad experience:

- The user must request multi-pass verification or temporal source routing.
- The user must know what hallucinations, prompts, primary sources, or provenance are.
- Every answer exposes a long audit process.

Good experience:

- The user asks `Can I go tomorrow?`
- Verified Search Baseline activates automatically.
- Stronger checking and imminent action increase rigor by meaning.
- The answer begins with what to do.
- Material external sources appear at the end with their actual inspected URLs.

## Internal and External Complexity

Internally, the framework performs Decision Framing, Failure-Mode First prioritization, claim-specific Source Authority routing, Entity Lock, Date Lock, publication Freshness Check, Applicability Check, Continuing Applicability and Supersession, Temporal Relevance, Claim-Level Verification, Independent Verification when warranted, Action Audit, and Re-check Planning.

Externally, the user normally sees:

1. the best action now;
2. a material caveat, precaution, or blocker;
3. what should be checked later and when;
4. a compact localized source section with the actual URLs used.

The interface should not reveal private chain-of-thought or routinely display a large evidence table.

## Progressive Verification

### Verified Search Baseline

For an ordinary consequential question, frame the practical decision, prioritize likely failure points, inspect suitable evidence, and answer naturally. One clear governing primary source may be enough. The source URL is still visible.

### Strict Verification

When the user asks for careful confirmation, re-establish critical claims through a meaningfully different evidence route when practical. A second reading of the same page or a simulated agreeing persona is not independence. Show compact Source Coverage or claim status when it helps, and display the primary and independent URLs used.

### Final-Action Audit

When the user is about to act, prioritize current facts that can cause immediate failure. Resolve dates and timezone, inspect current canonical information and relevant temporary notices, identify which evidence governs the action, and surface blockers, mitigation, Action Readiness, and a short checklist.

Example shape:

```text
Ready with precautions for 3 August 2026: You can go, but bring a swim cap because onsite sales could not be verified.

Check before leaving: same-day closure notice.

Sources
- Facility rules: https://example.org/facility/rules
- Current notices: https://example.org/facility/notices
```

The system must not say `Ready` while a material required blocker remains unresolved.

## Temporal Relevance and Re-check Planning

The newest available information is not always the right information to verify now. For a trip months away, eligibility and booking rules may be useful while exact weather and same-day disruption are premature. The answer should identify what is established, what is future-dependent, and a reasonable re-check point.

Re-check advice should use a real basis, such as registration opening, an event date, a service-alert window, or domain-appropriate forecast timing. It should not invent arbitrary dates merely to appear precise.

## When Older and Newer Official Information Differ

Verified Search does not simply trust whichever page is newest. It checks which information actually applies to the user's current situation. An older rule is not assumed to remain active just because no cancellation or replacement notice was found, and a newer general page does not automatically cancel a more specific governing rule. Authority, scope, effective period, edition or cycle, and the exact case all matter.

An old `closed until further notice` or similar temporary notice is rechecked against current operating information instead of being carried forward indefinitely. At the same time, generic current hours alone do not prove that the facility reopened. If the relationship cannot be resolved, the answer says so, avoids a false `Ready`, and gives the safest practical next step.

One clear current governing source may still be enough. Additional searching is useful when a realistic conflict, stale exception, or supersession question remains—not merely to make the answer look more thoroughly researched.

## Action Readiness

Use visible readiness labels only when they make the decision clearer:

- `Ready`: all material blockers reasonably checkable now are resolved.
- `Ready with precautions`: an unresolved item has an effective mitigation.
- `Not ready`: an unresolved requirement could cause failure.
- `Too early to determine`: a future-dependent fact cannot yet be known reliably.

These are decision states, not confidence percentages.

## Mandatory Source URLs

Every answer that relies on external sources ends with a clearly visible source section in the user's language. It lists each material source actually used, with title or short name, organization when useful, and the actual inspected URL.

Rich citation UI is additive; it does not replace visible URLs when the host exposes them. Prefer specific deep links over generic homepages. Never invent or reconstruct an unavailable URL.

If the interface genuinely withholds the URL, state that limitation and preserve the available citation. If material evidence is a user-provided email, SMS, screenshot, local file, or private portal message, label it as private or user-provided rather than inventing a public URL.

## Novice User Design

The experience must work for people who do not know what a prompt, source hierarchy, or primary source is, including people using a limited Free ChatGPT account. It must also work when the only interaction is opening a shared GPT and typing a question.

Use plain language. Prefer `Bring a swim cap because I could not verify onsite sales` over internal process terminology.

## Multilingual Parity

The policy remains in one English canonical file while the model responds in the user's current language. Semantically equivalent questions trigger equivalent verification behavior. Source headings and explanations follow the response language; URLs remain exact.

Do not build translated trigger lists or policy forks. Important dates remain unambiguous and include timezone information when consequential.

## Honest Limitations

If browsing is unavailable or a source cannot be inspected, the system says what could not be verified, explains how that affects the decision, and gives the most useful next action. Verified Search improves the process but cannot guarantee external truth or that a source will remain unchanged.
