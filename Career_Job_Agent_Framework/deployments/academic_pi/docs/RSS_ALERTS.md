# RSS discovery

RSS uses the existing discovery connector boundary. Network access stays in a
trusted host callback; parsing and deduplication remain credential-free.

`academic_jobs_online` has public feeds for tenured/tenure-track faculty and
open-rank searches. The RDF parser accepts `ads:` fields and keeps `ads:ID` as
a source-listing identifier, never as a global job ID. The injected adapter
tracks per-feed attempts, successes, conditional-request metadata, seen IDs
and links, errors, and the one-time bootstrap marker in private host state.

Feed failure is reported as a coverage failure. It does not erase seen state
or close a previously active job. Use `scan-rss academic_jobs_online` for a
focused run; `daily` remains the standard orchestration entry point.
