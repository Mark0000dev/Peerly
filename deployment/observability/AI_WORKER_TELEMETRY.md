# AI worker telemetry

## Configuration

Supply these entries in the complete private worker configuration described in
[PROVISION_BOOTSTRAP.md](../backend/PROVISION_BOOTSTRAP.md):

```json
{
  "OBSERVABILITY__COLLECTOR_ORIGIN": "http://peerly-ai-otel:4318",
  "OBSERVABILITY__ENVIRONMENT": "staging",
  "OBSERVABILITY__RELEASE": "REPLACE_WITH_ACTUAL_RELEASE",
  "OBSERVABILITY__TRACE_QUEUE_CAPACITY": "512",
  "RUNTIME__MAX_PROCESSES": "40"
}
```

Replace RELEASE with the actual immutable source release. Environment accepts
`[a-z0-9-]+` (1–32 characters); release accepts `[A-Za-z0-9._-]+` (1–64).
Trace queue capacity is16–4096. The collector origin has no path, query,
fragment or userinfo. OTLP HTTP uses port4318 and `/v1/traces` and `/v1/metrics`.
The isolated `peerly-ai-otel` gateway is the AI route; do not substitute the
collector's application-network alias or attach a broad application network.
Gateway routing and fixed upstream restrictions are documented in
[OTLP.md](../ai-egress/OTLP.md).

## Resources and execution

Resource attributes identify service.name=`studymate-ai-worker`, a fresh UUID
service.instance.id, deployment.environment.name from ENVIRONMENT and
service.version from RELEASE. Generic OTEL variables are not the worker's
configuration interface.

The deployment budget is40 processes/threads,1GiB memory and0.5 CPU for the
singleton service, using dedicated UID/GID10002. The code default remains32;
40 must be explicit. Actual cgroup and child RLIMIT limits must match the
configured policy and verified resource evidence. Do not reuse a32-process
proof for40 or infer capacity from image publication. SDK export threads and
native CLI threads share this finite budget.

The runtime observes the same SQL queue and ExecuteNextJob inside the same
supervisor; telemetry creates no second executor. Admission uses its separate
pool2. The worker uses pool1 for short transactions, never holding a connection
through inference or media I/O.

## Sampling and export bounds

Queue sampling runs every5s with a1s whole acquisition/query deadline and15s
freshness TTL. SDK callbacks read immutable cached values and perform no SQL,
network or filesystem I/O. Unknown/stale business gauges are omitted, not zero.
`worker.ai.queue.sample.fresh` and `worker.ai.queue.sample.age` expose freshness.
Execution spans use `ai.execute` with stored origin links and safe identifiers.

The trace queue defaults512, export batches contain at most64 spans, schedule
delay is1s and export timeout2s. Metrics export every30s with timeout2s.
Exporter failure and backpressure may lose telemetry; they must not grant
business authority or block core traffic. Queue metrics do not imply provider
availability or successful inference.

There is no OTLP log exporter in this worker. Safe structured stdout requires
separately configured, bounded log transport. Do not route raw CLI output,
prompts, images, results, credentials or private configuration into telemetry.
Logs and traces must carry their actual release/resource identity; do not
fabricate missing source fields in a relay.

## Configuration lifecycle

Settings are read once; there is no hot reload. Apply changes through controlled
worker replacement with admission stopped and physical child termination
confirmed. Lease expiry does not establish physical termination. Preserve the
same-owner managed credential cache and use the existing uncertainty/recovery
protocol rather than starting a second worker or repeating login.

Before enabling execution, verify containment, resource limits, restricted
transport and provisioning against the final actual container namespaces,
image, policy and bindings. Validate received resource attributes, origin-linked
spans, fresh queue gauges and bounded exporter failure separately. Configuration
or image build success is not runtime acceptance.
