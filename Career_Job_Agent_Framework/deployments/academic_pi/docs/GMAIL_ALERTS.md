# Gmail and Email Alert Setup

Email is an ingestion bus, not an authoritative job source. Every candidate
found in an alert should be resolved to an official institution source when
possible.

Messages are classified before parsing as `JOB_ALERT`, `ACCOUNT_ADMIN`,
`AUTH_OTP`, `ALERT_CONFIRMATION`, `IRRELEVANT`, or `UNKNOWN`. Sender-domain
rules come from a private registry; the public synthetic template documents
provider domains without storing account addresses or connector IDs.
Registration, password, OTP, welcome, confirmation-only, and `PhDs by Email`
messages do not become job candidates or parser failures. Unknown messages
with plausible role links are retained under `Needs Review`.

## Account choice

Either of these models is supported:

- a dedicated Gmail account for academic job alerts; or
- dedicated labels in an existing Gmail account.

A dedicated account usually reduces noise, but it is not required. The system
must never assume or embed the user's email address.

## Default labels

```text
Academic PI Job Agent/Alerts
Academic PI Job Agent/Processed
Academic PI Job Agent/Needs Review
Academic PI Job Agent/Error
```

Labels are configurable privately. Inbox filters may add the Alerts label when
messages arrive from enabled academic boards, institutions, or societies.

## Connector safety

- Configure OAuth and account identifiers through the existing private
  connector mechanism.
- Grant only the permissions needed to read relevant messages and change
  labels.
- Do not store tokens, account addresses, client secrets, message bodies, or
  connector IDs in public configuration or logs.
- The deployment never archives or deletes messages by default.
- The deployment never sends application email or submits an application.

## Processing contract

Production activation begins in **shadow mode**. Shadow mode may read and
classify messages, extract candidates, and test cross-source deduplication, but
it must not delete, archive, or change labels. Label mutation is a later,
separately approved gate after RSS/Gmail duplicate convergence is demonstrated.

For each run:

1. Find unprocessed messages in the configured alert scope.
2. Parse every plausible job candidate; one message may contain many jobs.
3. Record the provider message ID as an ingestion-event identifier, not a job
   identifier.
4. Resolve candidate links and attempt official-source verification.
5. Normalize and upsert each canonical job while preserving discovery
   provenance.
6. Add `Processed` only after all parseable candidates were handled or each
   parse failure was recorded explicitly.
7. Add `Needs Review` for incomplete or ambiguous parsing and `Error` for a
   processing failure according to the connector policy.

The same message can be retried safely. Idempotency is based on the ingestion
event plus canonical job identity. Repeated alerts from multiple boards must
converge on one job record.

While shadow mode is active, steps 6 and 7 produce a label plan only. They do
not execute Gmail mutations. The run report must say `label_mutation: disabled
(shadow mode)`.

## Failure behavior

| Condition | Label/result | State behavior |
|---|---|---|
| All candidates handled | `Processed` | Upsert canonical jobs |
| Candidate recorded as explicit parse failure | `Processed` plus configured review visibility | Keep failure evidence |
| Parsing incomplete or ambiguous | `Needs Review` | Do not pretend completion |
| Authentication or connector failure | `Error` when possible | Preserve prior state |
| Official page unavailable | Verification failure/pending | Never close from this failure |

The run report must distinguish an empty alert queue from a connector or parsing
failure and expose backlog counts without copying private message content.
