# Observability and identified analytics

Keep one correlated picture with distinct stores: PostgreSQL holds business/
canonical/client-observed truth and privileged access audit; private object
storage holds media; metrics, safe logs, traces and product exploration have
separate monitoring backends. Dashboards do not confer application operator role.

## Privacy and correlation

Analytics is mandatory and accurately account-linked. Use real action/request/
trace/span/job/resource references; never invent history, original intent,
consent, delivery or actor attribution. Private text/images, email addresses,
credentials, arbitrary bodies/headers, raw SQL/parameters and exception messages
are excluded from ordinary telemetry. Full content is read from business storage
under current audited operator authority.

Client batches are typed, bounded and deduplicated, with real observed time and
account checks. Source-frame IDs come only from the exact approved frontend
release map. Unknown release/frames stay unknown; do not relabel them to a new
build. Quality/loss signals describe observed unconfirmed/discarded records, not
definitively lost data; never recursively report quality-report failures.

## Instrumentation

API/workers own their SDK providers/resources and explicit spans. Domain and
application layers do not depend on telemetry SDKs. No global framework/SQL/body
capture. Metrics use bounded route/method/status/outcome dimensions, never
user/resource/job/email labels. Spans carry appropriate identity/source links.

Public SQLAlchemy events export query operation/duration and actual pool gauges,
not SQL text/parameters. Capacity labels distinguish configured base pool size
from maximum capacity; unknown values are omitted. SSE measures actual active
streams, frames, resets/closure/lag/send time without changing cancellation or
backpressure semantics. SDK callbacks only read cached state and never query DB.

Empty background publication polls retain query duration metrics without creating
query spans. This applies only to SELECTs in the publication task after it proves
there was no work. Writes, failures, cancellation, real work and other tasks retain
tracing; buffering is bounded and uses public SDK APIs. User-action tracing and
the worker polling cadence are unchanged.

Structured producer logs validate per-process release and allowlisted fields.
Safe errors include class, validated SQLSTATE and bounded application frames,
never exception text or SQL/params. Unknown legacy release is not replaced by a
static current version. Forward each log once; actual end-to-end relay acceptance
is separate from installing a daemon or observing an unrelated metric.

## Delivery, dashboards and alerts

Use a private collector and bounded async exporter queues. Monitoring outages
must not stall business transactions or hold SQL during inference. Expose sample
freshness, export/buffer failures and known gaps honestly. Archive collected
history before hot-store expiry with encryption, indexing and restore proof;
never promise physically impossible zero loss.

Dashboards cover API latency/errors, DB pool/query health, workers, AI backlog/
freshness/circuit, media/email/outbox delivery, SSE recovery and product outcomes.
Correlate permitted source→event→operation→trace/log drilldowns with privileged
inspection. Retained deleted accounts remain internally linked.

Technical alerts use grouped/deduplicated firing/resolution notifications through
the configured monitoring alert route. Application support delivery is a separate
destination/permission and must not become a generic technical-alert producer.
Never include private student content or secrets. Actual provider, destination,
archive, dashboard, alert and restore acceptance is required before external use;
quality/build success alone does not prove those operations.


### AI transaction failure metadata

`ai_transaction_failure` records expected SQL storage unavailability or a request
transaction timeout through the same `SafeJsonFormatter` allowlist. It exports
only typed, closed `ai_transaction_phase`, `ai_transaction_operation`,
`ai_transaction_stage`, `ai_transaction_cause` and a real boolean
`ai_transaction_deadline_expired`, with `ai_transaction_stage_semantics=last_entered`.
Request/action and trace/span identifiers use the existing validated correlation
fields when an execution origin is available. No SQL, parameters, input snapshots,
exception objects, messages or private user content enter this event.

`entry` means the transaction context has not yielded; `body` means it has yielded;
`commit` means the use-case body returned and transaction-context exit was entered.
The latter can include ORM flush and commit work. Operation/stage labels describe
the last instrumented adapter boundary entered, including identity read, clock,
source/candidate read, slot lock, admission observation, expiry event, dependent
admission write and owned-job read/event where supported. They do not prove the
exact SQL statement or failing internal substage, and remain last-entered if
caller code fails after a method returns. Inner helper statements are not traced.

Cause classification reads bounded, typed exception-chain facts; the deadline
flag reflects the actual request timeout context. A false deadline flag does not
assert that no other timeout occurred. Suppressed context is inspected only for
fixed cause categories, without changing general exception formatter behavior.
Business admission/quota/runtime denials and cancellation retain their existing
behavior; this event is not emitted for every AI HTTP503 or unexpected error.

The request budget remains two seconds and no retry is introduced. A commit-stage
failure is an uncertain outcome: a job may already exist despite an unavailable
response. It is not rollback or no-job proof. Preserve the original intent key,
authority checks and replay semantics when determining a durable outcome.
