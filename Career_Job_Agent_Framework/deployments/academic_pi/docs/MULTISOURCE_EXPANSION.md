# Academic Multi-source Expansion

## Boundary

This phase designs an offline, fail-closed source registry. It does not fetch a
site, read mail, mutate external state, send a notification, or change a task or
schedule. Institution selections and domains belong in `personal_config`;
reusable schemas, planning, normalization, deduplication, and health contracts
belong here.

## Selection and rollout

The target portfolio is 100 institutions: 40 US, 40 Europe, 10 Japan, and 10
other-region institutions. Selection favors major life-science research
employers, institutions likely to advertise independent faculty or group-leader
roles, geographic breadth, and sources that can share a platform adapter.

Rollout is gated rather than all-at-once:

1. **10-source pilot:** US 4, Europe 4, Japan 1, other 1. Verify every official
   entry point before activation and compare RSS, official-site, and Gmail hits
   against one canonical state.
2. **25-source expansion:** add adapter-compatible institutions only after the
   pilot produces stable health and dedup evidence.
3. **50-source expansion:** add the next regional cohort and audit adapter
   failure isolation.
4. **100-source expansion:** activate the full reviewed registry in batches.

All registry entries begin `enabled: false` and `verification_status: pending`.
Merging configuration is therefore not runtime activation.

When no official recruitment entry point has been established, retain
`mode: discovery_pending`, `adapter: unassigned`, and `url: null`. Do not use an
institutional homepage as a substitute for a recruitment source.

## Adapter, batching, and health

Prefer official RSS or APIs, then reusable ATS adapters such as Workday,
Interfolio, Taleo, SuccessFactors, PeopleAdmin, or PageUp. Use the bounded
generic HTML adapter only for stable official listing pages. An institution-
specific adapter requires a separate review and synthetic failure-isolation
test.

A trusted runtime should execute batches of at most ten institutions rather
than asking ChatGPT to browse 100 pages. Priority-1 sources are due within 24
hours; the remaining portfolio must complete within 48 hours.

Every attempt records `last_checked`, `source_health`, `items_seen`, and
`failure_reason`. A successful retrieval with zero relevant jobs is valid zero
coverage. A failed retrieval has `items_seen: null` plus a reason; it must never
be represented as zero jobs.

## Verification, deduplication, and rollback

An entry point is authoritative only when its host is institution-owned or an
explicitly reviewed official ATS host. Aggregators and Gmail are discovery
lanes. Official job IDs take precedence for identity, followed by normalized
official URLs, then institution, title, location, and deadline. All lanes upsert
the same canonical record and retain provenance.

Stop a rollout wave if official ownership is unverified, an adapter repeatedly
fails, duplicates remain unresolved, failure is represented as zero, or the
48-hour coverage promise is missed. Rollback disables only that wave and
retains prior canonical State, Runs, Reports, messages, and history.
