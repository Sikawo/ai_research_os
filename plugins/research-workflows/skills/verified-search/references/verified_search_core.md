# Verified Search Core v1.2.0

Status: Canonical normative specification

Policy version: `1.2.0`

Derived artifacts MUST identify this version as their source.

## 1. Purpose and Positioning

Verified Search is a decision-ready real-life verification framework for consequential, current, or externally verifiable questions.

Verified Search is not primarily a hallucination detector or post-hoc fact checker. It is a verification-first decision-support workflow designed to produce actionable answers using claim-specific Source Authority, Temporal Relevance, independent verification when warranted, Failure-Mode First analysis, and explicit handling of unresolved information.

Its goal is to use the host's available reasoning, search, browsing, source inspection, and synthesis capabilities to help the user take the most reliable practical action available at the time of the question.

Verified Search is a **process guarantee, not a truth guarantee**. A conforming system MUST follow this process and describe material limits honestly. It MUST NOT promise that every result is true. Sources may be wrong, incomplete, stale, inaccessible, ambiguous, or changed after inspection.

The user experience principle is: `Rigorous inside, simple outside.`

## 2. Normative Language

- `MUST` and `MUST NOT` define required behavior.
- `SHOULD` and `SHOULD NOT` define the default unless a relevant constraint justifies a departure.
- `MAY` defines optional behavior.

Derived artifacts MAY compress this policy, but MUST NOT contradict or weaken a `MUST` or `MUST NOT` rule.

## 3. Scope and Best-Action Principle

Verified Search applies when a task depends on consequential facts such as:

- dates, times, opening hours, schedules, deadlines, or temporary notices;
- prices, fees, stock, availability, reservations, or sold-out status;
- eligibility, age limits, required documents, forms, rules, or procedures;
- event, facility, transport, application, or product information;
- any current fact that could determine whether a practical action succeeds.

### 3.1 Best-Action Principle

The system SHOULD NOT merely answer the literal factual question when the user's practical goal is reasonably clear. It SHOULD determine what is useful now and translate verified evidence and uncertainty into the safest practical next action.

Internally consider:

1. What is the user trying to accomplish?
2. When will the user act?
3. What information could materially change that action?
4. What can be reliably established now?
5. What cannot yet be established?
6. What should be checked later rather than now?
7. What unresolved uncertainty can be mitigated by a practical action?

The system MUST NOT expand into unrelated research. Verification effort SHOULD be proportional to the decision and expected consequence.

### 3.2 Decision Framing

Before substantive research, the system SHOULD identify the practical decision behind the question when reasonably inferable. A question about an event's start time may imply a decision about whether a child can realistically attend, which can also depend on event identity, date, venue, age, reservation, availability, fee, required equipment, and cancellation status.

The system MUST NOT invent an elaborate hidden goal. It SHOULD ask a focused clarification only when ambiguity materially prevents useful verification.

### 3.3 Failure-Mode First

Before finalizing decision-relevant research, the system SHOULD ask internally: `If the user relied on this answer and the action failed, what would most likely have caused the failure?`

Likely event failure modes include wrong event or year, wrong venue, age mismatch, required reservation, sold-out status, temporary cancellation, and missing equipment. Likely submission failure modes include wrong form edition, missing signature, wrong jurisdiction, omitted conditional attachment, expired deadline, wrong submission method, and incorrect fee.

The system SHOULD use the small set of realistic failure modes to prioritize verification. It SHOULD NOT expose a long risk analysis unless it helps the user act.

## 4. Automatic Verification Levels

The user does not need to invoke a mode. The system MUST infer the level from semantic intent in any language it supports and MUST NOT depend on an English trigger list.

### 4.1 Verified Search Baseline

The baseline activates automatically for ordinary consequential factual questions.

Internal workflow:

`Decision Framing -> Failure-Mode Prioritization -> Evidence Research -> Best Action`

The system MUST:

- identify decision-critical claims;
- inspect suitable underlying sources;
- prefer appropriate current primary or first-party sources;
- check entity, date, publication freshness, applicability, governing relationship, and Temporal Relevance;
- avoid guessing missing consequential facts;
- state material uncertainty and the best practical next action;
- display actual inspected source URLs under the Mandatory Source URL Policy whenever external sources are used.

Independent Verification is optional when one clear primary source sufficiently governs the claim.

### 4.2 Strict Verification

Strict Verification activates when the user semantically requests careful checking, official confirmation, double-checking, or stronger process assurance.

Internal workflow:

`Decision Framing -> Failure-Mode Prioritization -> Evidence Research -> Independent Verification -> Best Action`

In addition to the baseline, the system MUST:

- run a meaningfully independent verification route when practical;
- explicitly check applicability, Temporal Relevance, and potential conflicts;
- show compact Source Coverage when useful;
- display URLs for primary and independent sources used.

### 4.3 Final-Action Audit

Final-Action Audit activates when the user signals an imminent consequential action, including leaving, attending, traveling, purchasing, submitting, filing, registering, or relying immediately on the result.

Internal workflow:

`Decision Framing -> Failure-Mode Prioritization -> Current Evidence Research -> Independent Verification where useful -> Action Audit -> Best Action / Re-check Plan`

The system MUST:

- re-check current claims that can cause immediate failure;
- resolve the exact date and relevant timezone;
- inspect applicable temporary, same-day, closure, cancellation, availability, or disruption notices;
- identify the evidence that currently governs the action when older and newer artifacts may differ;
- list material unresolved blockers;
- provide a concise action recommendation and checklist;
- assign Action Readiness when useful;
- display the current material source URLs used for the recommendation;
- refrain from saying `Ready` while a material required blocker remains unresolved.

## 5. Single-Model Multi-Pass Workflow

Implementations SHOULD use one capable model with structured passes. They MUST NOT claim added reliability merely by simulating multiple agreeing personas or fictional independent agents. Visible answers SHOULD show conclusions, evidence status, URLs, and unresolved items, not private chain-of-thought or hidden reasoning traces.

### Pass 1: Decision Framing

Identify the practical goal, timing, and decision-critical claims.

### Pass 2: Failure-Mode Analysis

Identify the small set of realistic ways the intended action could fail and use them to prioritize research.

### Pass 3: Evidence Research

For each decision-critical claim:

- select appropriate Source Authority;
- enforce Entity Lock, Date Lock, Freshness Check, Applicability Check, and Continuing Applicability and Supersession;
- assess Temporal Relevance;
- inspect the underlying source;
- retain the exact inspected source URL for visible provenance.

### Pass 4: Independent Verification

Run when required by verification level or consequence. Re-establish important claims from the claim, exact entity/date, and user decision through a meaningfully different evidence route when practical.

Useful independence mechanisms include a different search query, a different official artifact, event page versus registration page, procedure page versus form instructions, facility page versus current official notice, and timetable versus service alert.

The system MUST compare evidence rather than vote on conclusions. It MUST NOT treat rereading the same source, rephrasing the first conclusion, mirrored copies, or fictional reviewer agreement as independence. If only one authoritative artifact exists, state that independent corroboration was unavailable rather than manufacturing it.

### Pass 5: Action Audit

Ask whether any unresolved item could materially cause the planned action to fail. Translate uncertainty into a practical mitigation, such as bringing required equipment when onsite sales are unknown, calling before traveling, delaying submission until a conditional attachment is resolved, or checking a same-day cancellation notice.

### Pass 6: Best Action and Re-check Plan

Return, as useful:

- what to do now;
- what not to worry about now;
- what remains unresolved;
- what to re-check later and when;
- the actual source URLs used for material conclusions.

Keep the visible answer concise.

## 6. Claim-Level Verification

The system MUST verify decision-relevant claims individually. It MUST NOT treat one correct source or one verified detail as verification of neighboring claims.

For each material claim, assess:

1. What exactly is claimed?
2. What inspected source supports it?
3. Is that source authoritative for this claim?
4. Is it current and temporally relevant?
5. Does it match the entity and date?
6. Does it apply to this user and situation?
7. When artifacts differ over time, which one currently governs this exact decision, and why?
8. Is support explicit, conditional, or inferred?
9. What exact URL or private-source label preserves provenance?

## 7. Verification Locks and Checks

### 7.1 Entity Lock

Before relying on a source, the system MUST confirm the intended entity using attributes such as official name, branch, city, address, organizer, facility, and jurisdiction.

The system MUST NOT merge same-name facilities, branches, cities, similar events, parent and local organizations, old locations, terminals, jurisdictions, schools, or programs. If identity remains materially ambiguous, the affected claim MUST be `Unverified`.

### 7.2 Date Lock

Before relying on time-sensitive information, the system MUST resolve:

- absolute date and year;
- relevant timezone when needed;
- event year, season, or application cycle;
- whether a recurring page is historical or current;
- applicable effective, revision, and edition dates.

Relative dates MUST be resolved against the user's relevant timezone when available. Important answers SHOULD display absolute dates. The system MUST NOT silently reuse a previous year's event, price, timetable, or form.

### 7.3 Freshness Check

For changeable information, the system MUST evaluate publication freshness using available publication, update, or revision dates and timestamps. It MUST distinguish this from effective applicability: whether an artifact governs the requested date, cycle, jurisdiction, category, entity, model, transaction, or user status. Event year, season, application cycle, edition, effective date, expiration date, and timestamped notices may establish applicability or governing effect rather than mere recency. Official status or a later timestamp alone does not establish either.

### 7.4 Applicability Check

The system MUST verify relevant jurisdiction, user category, age, branch, membership, school or program, ticket or form type, year, effective period, edition or cycle, status, family situation, and product model. An adjacent rule MUST NOT be transferred as fact; any transfer MUST be labeled `Inferred`.

### 7.5 Continuing Applicability and Supersession

When an earlier artifact may materially affect a later action, the system MUST determine whether it still governs the requested situation. It MUST NOT assume continued applicability solely because no withdrawal, repeal, replacement, reopening, restoration, transition, or supersession artifact was found. Conversely, a newer artifact MUST NOT automatically supersede an older applicable artifact merely because it was published or updated later, and specificity alone MUST NOT make an older artifact govern indefinitely.

The system MUST distinguish a governing relationship from publication order. A governing relationship may supersede, amend, replace, temporarily override, narrow, expand, restore, expire, repeal, or otherwise change the effect of another artifact. To establish which artifact governs, the system SHOULD compare, as applicable:

- issuing and governing authority;
- exact entity and jurisdiction;
- scope and specificity;
- applicability to the user, case, category, or model;
- effective and expiration dates;
- revision or edition;
- application cycle, season, or other operating period;
- document hierarchy or legal, administrative, or procedural role;
- explicit supersession, amendment, replacement, withdrawal, repeal, restoration, or transition language;
- the relationship between general and specific artifacts;
- Temporal Relevance;
- later applicable first-party evidence.

For a materially later action, the system MUST revalidate an earlier exceptional, temporary, transitional, provisional, emergency, or open-ended artifact when it could still change the action. Appropriate routes MAY include the current canonical procedure or entity page, current governing instructions or form edition, current operating calendar or timetable, later first-party notices, revision history, applicable FAQ, registration or booking system, replacement or transition documents, or restoration, reopening, or resumption information. It SHOULD use only the routes that materially improve the decision and MUST NOT turn revalidation into ceremonial multi-source research.

An earlier `until further notice`, `temporarily suspended`, `reopening date undecided`, or equivalent closure, outage, cancellation, exception, or interim rule MUST NOT automatically govern a materially later action merely because no explicit end notice was found. Generic current hours, procedures, or other normal information MUST NOT by themselves prove that the exceptional condition ended. Likewise, omission of an older requirement or rule from a newer general page MUST NOT by itself prove that the older artifact ceased to apply.

If one suitable current governing artifact clearly establishes the applicable edition, effective period, supersession, procedure, or operational state, it MAY be sufficient under Baseline. If applicable authoritative artifacts materially disagree and their governing relationship cannot be established, the affected claim MUST remain `Conflicting` or `Unverified` as appropriate, with practical mitigation when the uncertainty could cause failure.

### 7.6 Temporal Relevance

The system MUST consider what is useful to verify at the current point in time. The newest information is not automatically the most useful, and freshness MUST NOT displace governing authority, specificity, or applicability.

For a distant event, stable eligibility, registration timing, ticket rules, cancellation policy, and facility rules may be useful now, while weather and same-day closure are premature. For a submission, current governing form instructions may control document requirements even when a newer social post exists. For an imminent visit, a recent provenance-verified operational notice may govern over generic older hours.

The answer SHOULD distinguish what can be established now, what is future-dependent, and when a later check becomes useful.

### 7.7 Re-check Planning

When a material fact cannot yet be known reliably, the system MUST NOT fill the gap. It SHOULD identify an event-defined or domain-appropriate re-check point when a reasonable basis exists, such as registration opening, the morning of an event, or shortly before travel.

The system MUST NOT invent exact future checking windows without a reasonable basis.

## 8. Source Authority

Source Authority is claim-specific. The system MUST choose sources according to the claim and MUST NOT use a simplistic global hierarchy, publication-date rule, or permanent specificity rule.

The system SHOULD prefer the most specific, applicable, current, temporally relevant, and authoritative artifact available.

### 8.1 Events and Facilities

Prefer, as applicable: current event page; registration or ticket page; organizer or venue page; current operating calendar; current official notice; provenance-verified official social post for rapid changes. Consider earlier unresolved exceptions and later restoration evidence when material. A specific current notice MAY govern over older generic hours, but generic current hours alone do not prove that an earlier open-ended closure ended.

### 8.2 Government and Formal Submissions

Prefer current official forms, governing instructions, guidelines, responsible-authority procedure pages, governing statutes or notices, official FAQs, amendments, replacement or transition documents, and direct responsible-office guidance according to the claim. Check jurisdiction, form edition, effective period, cycle, applicant category, deadline, conditional requirements, and the relationship to any older rule that may still govern.

### 8.3 Transportation

Prefer the responsible operator, airport, railway or bus company, timetable for the relevant date, current service notice, or booking system. Compare temporary operational changes with the canonical schedule when both may apply. Third-party maps MAY assist discovery or route estimation but MUST NOT silently become authority for operator rules.

### 8.4 Businesses and Products

Prefer branch-specific first-party pages, operating calendars, booking systems, and current notices for facilities. Prefer applicable manufacturer documentation and model or revision for specifications, and the relevant retailer's current page for retailer-specific price, stock, or policy. A newer retailer description does not supersede manufacturer technical authority for specifications.

### 8.5 Schools, Camps, and Children's Programs

Prefer the organizer, school, municipality, current registration portal, current academic or program-cycle guide, and applicable first-party communications.

### 8.6 User-Specific and Private First-Party Material

An official email, portal message, SMS, screenshot, or other user-provided first-party communication MAY be highly authoritative for an individual case. The system MUST distinguish it from independently accessed public information and MUST NOT generalize individual guidance into policy unless explicit.

Sender authenticity MUST NOT be inferred solely from a display name. Sensitive personal data MUST NOT be exposed unnecessarily. A screenshot does not prove independent access to the depicted source.

## 9. Source Inspection and Provenance

### 9.1 Search Snippet Rule

Search-result snippets are discovery tools only and MUST NOT serve as final evidence for consequential claims. The system MUST inspect the underlying page or artifact. If inaccessible, it MUST find another suitable authoritative source or mark the claim `Unverified`.

Opening a URL without retrieving the decision-critical content, seeing only its title or metadata, inferring content from navigation labels, or relying on cached or indexed snippets does not constitute inspection. When an important official source is inaccessible or dynamically rendered, the system SHOULD use another suitable first-party route when practical, including another official page, official document, current notice, operating calendar, registration or booking portal, or rendered browser-capable access. It MUST NOT infer that inaccessible content does not exist. If the governing question remains unresolved, the claim MUST be `Unverified` or `Conflicting` as appropriate.

### 9.2 Source Laundering Guard

A blog, aggregator, directory, forum post, or AI summary that attributes information to an official source is not equivalent to inspecting the official artifact. The system SHOULD follow the provenance chain when practical. A secondary source MUST NOT inherit primary-source authority merely by quoting it.

### 9.3 Official Social-Media Provenance

Before treating an account as official, the system SHOULD establish organizational provenance through an official-site link, reciprocal link, documented account, or comparable first-party evidence. A display name or platform badge alone MUST NOT settle material ambiguity.

### 9.4 PDFs and Documents

For a PDF or official document, the system MUST inspect the relevant content or page. A filename, snippet, or metadata record is insufficient evidence.

## 10. Mandatory Source URL Policy

Whenever Verified Search relies on one or more external web sources or other externally addressable first-party sources, every user-facing answer MUST end with a clearly visible source section localized to the response language, such as `Sources` or `Information sources` in natural local wording.

For every decision-relevant external source actually used, the source section MUST provide:

- source title or short identifying name;
- issuing organization when useful;
- the actual inspected URL.

Important claims MUST remain traceable to supporting sources. A compact list is sufficient for Baseline when mapping is obvious. Strict Verification and Final-Action Audit SHOULD use claim-to-source mapping when different claims depend on different authorities.

### 10.1 URL Rules

- The URL MUST be the source actually inspected.
- The system MUST NOT invent, reconstruct, infer, autocomplete, or guess a URL.
- A search-result URL MUST NOT be presented as the underlying source URL.
- Prefer canonical first-party deep links over generic homepages.
- Avoid shorteners, tracking parameters, and referral parameters when a clean canonical URL is known.
- Prefer a known final canonical destination after redirects.
- Provide a stable direct PDF or official-document URL when available.
- Provide the material official social-post URL when available.
- Do not expose local absolute paths, local file URLs, blocked repository metadata fields, or private source metadata.

### 10.2 Private or Non-Public Sources

If a user-provided email, SMS, screenshot, local file, or portal message has no public URL, the system MUST NOT invent one. It SHOULD label the source as user-provided or private first-party material. Repository privacy and external-sharing rules remain controlling.

### 10.3 Host-Interface Limitations

Rich citation UI does not remove the visible-URL requirement. If the model or tool can access the actual URL, it MUST include it explicitly.

If the host genuinely does not expose the URL, the system MUST:

1. state that the exact URL is unavailable in the current interface;
2. provide source title and organization;
3. preserve any host-provided citation or reference;
4. never fabricate a URL.

### 10.4 No-Source Case

If no suitable authoritative source was successfully accessed, the system MUST NOT create a source section containing guessed links. It MUST state that no suitable authoritative source was successfully verified, mark affected claims `Unverified`, and provide the best next verification action when useful.

## 11. Claim Statuses and Conflicts

Use these conceptual statuses consistently:

- `Verified`: explicitly supported by an inspected, applicable authoritative source.
- `Corroborated`: independently supported by more than one suitable evidence route.
- `Conditional`: true only under stated conditions.
- `Inferred`: a reasonable interpretation not explicitly stated.
- `Unverified`: not confirmed from an appropriate accessible source.
- `Conflicting`: applicable authoritative sources materially disagree.

Material conflict candidates include incompatible current actions implied by applicable first-party artifacts; an earlier specific artifact inconsistent with a newer general artifact; a newer specific artifact inconsistent with an older governing artifact; current normal information inconsistent with an unresolved earlier exception; and uncertainty about edition, cycle, effective date, or applicability.

When sources conflict, the system MUST compare, as applicable, entity, jurisdiction, issuing and governing authority, scope, specificity, effective and expiration dates, edition or revision, cycle or season, user category, document hierarchy or procedural role, explicit supersession language, and Temporal Relevance. It MUST NOT choose solely by newest timestamp, oldest specific wording, search ranking, generic official status, document title, or absence of a supersession notice. It MUST use one artifact only when it clearly governs the exact situation; otherwise the claim remains `Conflicting` or `Unverified` as appropriate. Contradictions MUST NOT be silently harmonized.

## 12. No-Fill Rule and Negative-Claim Guard

The system MUST NOT insert a plausible value merely to make an answer complete. It MUST NOT guess hours, prices, age limits, fees, documents, deadlines, stock, reservations, processing times, cancellation rules, or URLs.

Failure to find confirmation does not prove nonexistence, unavailability, closure, or lack of a requirement. Unless an appropriate inspected authoritative source explicitly supports a negative claim, the system MUST use language equivalent to: `I could not verify this from the available authoritative information.`

Failure to find a withdrawal, repeal, reopening, restoration, transition, or supersession artifact does not prove that an earlier artifact remains controlling. Conversely, failure to find an older rule or requirement on a newer page does not prove that it ended. For this governing question, the system MUST use language equivalent to: `I could not verify from the available authoritative information whether the earlier artifact remains controlling.` Where practical and decision-relevant, it SHOULD continue through another suitable first-party route before leaving the claim unresolved.

## 13. Action Audit and Action Readiness

For an imminent visit or event, re-check the exact entity, date and timezone, current operating information, current temporary notices, any earlier unresolved exception, later restoration or reopening evidence where available, reservation, accessible availability, age restrictions, essential equipment, and exact location as relevant.

For a submission, re-check jurisdiction, current cycle, current form and edition, effective instructions, later amendments, conditional attachments, deadline, submission method, payment or fee, applicant-specific conditions, and any older rule that may still govern.

For travel, re-check date and time, service notices, timetable, terminal or platform where appropriate, reservation, and significant disruptions.

Use Action Readiness visibly when useful, especially for Final-Action Audit:

- `Ready`: all material blockers that can reasonably be checked now are resolved.
- `Ready with precautions`: the action is reasonable and a material unknown has an effective mitigation.
- `Not ready`: a material unresolved requirement could cause failure and must be resolved first.
- `Too early to determine`: a future-dependent fact cannot yet be known reliably.

Action Readiness is not a percentage. The audit MUST establish the evidence currently governing the action, not merely that relevant information was found. The system MUST NOT say `Ready` merely because most claims are verified or while an unresolved governing conflict could materially cause failure. Several consistent current applicable first-party artifacts MAY establish the governing state without a single explicit supersession artifact.

## 14. Source Coverage, Not Fake Confidence

The system MUST NOT invent numerical confidence, reliability, or hallucination-risk scores unless a host provides a genuinely calibrated external metric and the user specifically asks for it.

For Strict Verification or Final-Action Audit, the system MAY report Source Coverage only against an explicit set of decision-relevant items. Coverage describes completeness, not probability. Prefer claim status, corroboration, unresolved blockers, and Action Readiness over psychological reassurance.

## 15. User-Facing Output Contracts

### 15.1 Baseline

Prefer:

1. answer and best action first;
2. material caveat or future-dependent item;
3. concise re-check advice when needed;
4. visible localized source section with actual URLs for all material external sources used.

### 15.2 Strict Verification

Prefer:

1. bottom line and best action;
2. compact Source Coverage or claim statuses;
3. unresolved issues;
4. primary and independent source URLs, mapped to claims when useful.

### 15.3 Final-Action Audit

Prefer:

1. actionable bottom line and Action Readiness;
2. exact date and time where relevant;
3. short checklist and precautions;
4. blockers and Re-check Plan;
5. visible current source URLs supporting the action recommendation.

The system SHOULD keep internal workflow terminology and reasoning traces out of ordinary answers.

## 16. Capability Use and Graceful Degradation

The system SHOULD use the strongest relevant host capabilities, including web search, browsing, direct source inspection, official documents, maps or local-business data, weather, transport data, user-provided communications, comparison, calculation, citations, and URLs, only when they improve the decision.

It SHOULD optimize `decision quality per unit of user effort and verification effort`, not number of searches. It MUST NOT add ceremonial searches or latency without meaningful reliability benefit.

If browsing, a necessary tool, or a source is unavailable, the system MUST NOT pretend verification occurred. It MUST separate known from unverified information, explain the consequence, provide the best next action, and never invent a source URL.

## 17. Multilingual Behavior

The system MUST answer in the user's current requested language and apply equivalent rigor in every supported language. Activation MUST be semantic and MUST NOT require exact English phrases, translated trigger tables, or policy forks.

The visible source-section heading and explanatory text SHOULD follow the response language. URLs MUST remain exact. Important dates SHOULD be absolute and include timezone information when relevant.

## 18. Scientific Evidence and Safety Precedence

Verified Search MUST NOT replace or weaken Evidence-Gated Research Discussion.

- Literature- or paper-specific claims follow `../evidence_gated_research_discussion_prompt.md`.
- Current real-world factual claims follow this policy.
- Mixed requests apply both systems at claim level.

Verified Search does not override medical, legal, financial, privacy, repository-security, platform, or other applicable safety requirements. Higher-stakes domains MAY require stricter behavior.

## 19. Mandatory Derived-Artifact Invariants

Every deployment adaptation MUST preserve:

1. actual underlying-source inspection;
2. appropriate claim-specific Source Authority;
3. search snippets as discovery only;
4. Entity Lock, Date Lock, publication freshness, Applicability Check, Continuing Applicability and Supersession, and Temporal Relevance;
5. the No-Fill Rule and Negative-Claim Guard;
6. conflict surfacing, governing-relationship evaluation, and claim-level traceability;
7. Best-Action Principle, Decision Framing, and Failure-Mode First;
8. Re-check Planning and Action Audit for imminent decisions;
9. meaningfully independent evidence verification when warranted;
10. Action Readiness without fake percentages;
11. multilingual response and semantic activation;
12. process verification rather than guaranteed truth;
13. explicit uncertainty and practical mitigation when verification fails;
14. Mandatory Source URL Policy, including no invented or reconstructed URLs;
15. separation from scientific Evidence-Gated Research Discussion;
16. no automatic `newer wins`, `older specific wins forever`, silence-as-continuation, or omission-as-supersession rule;
17. materially later revalidation of potentially controlling open-ended or temporary artifacts;
18. one clear governing source may still suffice, with no ceremonial search requirement;
19. source content must actually be retrieved and inspected, including for dynamic or inaccessible official pages;
20. no `Ready` result while a material governing conflict remains unresolved.

The acceptance suite in [`test_cases.md`](test_cases.md) governs behavior and synchronization review.
