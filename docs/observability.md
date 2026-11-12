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
