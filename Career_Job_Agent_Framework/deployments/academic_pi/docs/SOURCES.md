# Academic Discovery Sources

Academic opportunities are distributed across aggregators, scientific boards,
regional portals, society channels, institution pages, and email alerts. The
deployment treats these as redundant discovery lanes feeding one verified
canonical state.

The production lanes are email alerts, RSS/web aggregators, and direct private
target-institution monitoring. AcademicJobsOnline uses two RSS feeds and a
one-time bootstrap. Nature Careers, Science Careers, JREC-IN, Academic
Positions, EURAXESS, jobs.ac.uk, HigherEdJobs, and ASM Career Connections are
first-class discovery sources. ASCB is intentionally not enabled.

## Source classes

The public catalog supports:

- `GENERAL_ACADEMIC_AGGREGATOR`
- `SCIENCE_JOB_BOARD`
- `REGIONAL_ACADEMIC_PORTAL`
- `SCIENTIFIC_SOCIETY`
- `INSTITUTION_DIRECT`
- `EMAIL_ALERT`
- `SEARCH_ENGINE_DISCOVERY`
- `MANUAL`

`config/source_catalog.yaml` provides generic examples and capability metadata.
Private overrides enable, disable, reprioritize, or refine those sources.

## Authority hierarchy

Use this order for factual job details:

1. official institution job-detail page;
2. official institution ATS or applicant portal;
3. official department recruitment page;
4. trusted aggregator;
5. email, newsletter, social, or other discovery message.

Aggregators and messages are discovery sources. They do not supersede an
available official posting for open status, title, department, deadline,
location, requirements, salary, or requisition ID.

## Query families

Every enabled strategy may draw from four bounded families:

1. **Role-first:** region-aware terms such as Assistant Professor, Faculty
   Position, Group Leader, Lecturer, W1 Professor, and Open Rank.
2. **Field-first:** prioritized private scientific terms combined with relevant
   role terms.
3. **Broad search:** institution-domain queries that intentionally omit private
   scientific keywords.
4. **Target institution:** career pages, department recruitment pages,
   institution-domain search, and known hiring platforms.

Query generation must use priority, rotation, per-source caps, semantic
deduplication, and coverage logs rather than the full Cartesian product. Negative
terms are private and conservative; they must not suppress a plausible broad
faculty call merely because it contains an unrelated department term.

## Coverage and cadence

Public defaults define high, medium, and low frequency classes. Private
configuration may override them per source and institution. For each attempt,
record the attempt time, success time, status, items seen, error, and next due
time.

A completed institution scan with zero current jobs is successful coverage.
Broken or stale URLs are recorded without deleting the institution. Repeated
failures and missed cadence must appear in the weekly coverage audit.

## Target institutions

Target institutions are private because their selection and ranking may reveal
personal priorities. Each entry may define aliases, country, priority, domains,
known career and department URLs, expected role terms, and scan frequency.

An initial URL is optional. A compatible scanner may discover and remember
successful official URLs in private state. InstitutionCoverage should record
both known-page checks and domain queries.

## Scientific societies

Society sources are field-dependent. Add them through private source overrides
with field relevance and source metadata rather than hard-coding one discipline
into the public engine.

## Adding or repairing a source

A source definition should expose:

- source ID, display name, class, base URL, and regions;
- enabled state, priority, and frequency class;
- discovery method and email/direct-search support;
- verification authority and expected cadence; and
- parser version.

Keep source-specific parsing isolated from verification, scoring, and state. If
a source changes, disable or repair that adapter without mutating prior canonical
jobs or unrelated sources.
