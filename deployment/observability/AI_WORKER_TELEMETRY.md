# AI worker OTLP activation handoff

Status: AI execution signal composition is implemented and locally accepted.
The physical staging worker still uses its previously accepted image and has not
been restarted or enabled for OTLP. No live telemetry acceptance is claimed.
The focused composition/sampling batch passed32 unit and4 PostgreSQL cases; the
SDK measurement added2 kernel threads. Credentials/provider/isolation settings
remain unchanged; physical PID headroom still requires parent acceptance.

## Public configuration

Parent may merge these four public entries into the **complete private**
`worker-env.json` described in
[PROVISION_BOOTSTRAP.md](../backend/PROVISION_BOOTSTRAP.md):

```json
{
  "OBSERVABILITY__COLLECTOR_ORIGIN": "http://peerly-otel:4318",
  "OBSERVABILITY__ENVIRONMENT": "staging",
  "OBSERVABILITY__RELEASE": "REPLACE_WITH_ACTUAL_RELEASE",
  "OBSERVABILITY__TRACE_QUEUE_CAPACITY": "512"
}
```

The release placeholder must be replaced before use. Environment accepts
`[a-z0-9-]+` (1–32 characters); release accepts `[A-Za-z0-9._-]+` (1–64).
Queue capacity is 16–4096. Origin accepts HTTP/HTTPS with no path, query,
fragment, userinfo or whitespace. The SDK appends `/v1/traces` and `/v1/metrics`;
use OTLP HTTP port4318, not gRPC4317. This public fragment is not a runnable
worker configuration. Parent preserves all existing private entries and file
ownership/mode, and atomically replaces the file through its directory mount.
Do not print or share the filled configuration.

Resource attributes are fixed service.name=`studymate-ai-worker`, a fresh UUID
service.instance.id, deployment.environment.name from ENVIRONMENT and
service.version from RELEASE. Generic OTEL variables are not the bootstrap
configuration interface. No CLI/provider arguments or child environment changes
are needed or authorized.

## Implemented composition and sampled-state contract

`bootstrap.run_ai_worker` passes the actual owned tracer and meter to the runtime
factory. The factory wraps the same SQL queue with `ObservedAiQueue`, passes it to
the same `ExecuteNextJob`, and wraps that exact step with `ObservedAiStep` inside
the same single-executor supervisor. No parallel executor is created.

A bounded asynchronous sampler uses the existing one-connection pool:5-second
period,250ms total acquisition/query deadline and15-second freshness TTL. SDK
callbacks read immutable cached data and perform no SQL/network I/O. Unknown or
stale queue values are omitted rather than reported as zero. Existing attempt,
execution/wait duration, depth, oldest, occupied-slot and circuit signal names
remain unchanged. New `worker.ai.queue.sample.fresh` and
`worker.ai.queue.sample.age` signals distinguish freshness from business values;
collector allowlists and dashboards must accept/use them before activation.

Expected execution spans are `ai.execute` with actual stored origin links and
safe IDs/kind/state metadata. This local implementation and its tests do not
prove that the old physical staging worker emits these signals. Changing its
configuration alone cannot activate code absent from its immutable image.

## Network and resource prerequisites

The example hostname requires an approved route from the AI worker's isolated
network to the collector. Docker embedded DNS can resolve same-network aliases,
but the collector's ordinary application-network alias is not automatically
available on the AI network. Unknown upstream DNS is intentionally disabled.
Parent must establish the actual approved transport separately; do not attach a
broad application network, change provider allowlists, expose collector ports
publicly, or weaken the restricted gateway to make this example work.

The SDK adds background export threads. These count toward both cgroup PID32
and UID-wide RLIMIT_NPROC32 alongside the CLI. Retain UID10002, current CPU/RAM
limits and all accepted isolation controls; parent must confirm actual remaining
thread/process headroom before claiming live compatibility. No limit increase
is implied. Trace queue defaults512, batches at most64, export delay1s and
export timeout2s. Metrics export every30s with timeout2s. Backpressure can lose
telemetry; it must not become business admission or provider authority. There is
no OTLP log exporter here; Docker log routing is a separate parent-owned change.

## Restart and receipt semantics

There is no hot reload: ai_worker constructs frozen settings once. Bootstrap
execs the worker and no longer watches worker-env.json. Editing that file or
using `docker exec -e` does not change the running worker. No existing command
replaces the active worker safely in the same namespaces. Do not start a second
worker merely to apply telemetry configuration.

Parent's controlled transition must stop admission, gracefully stop the old
worker, confirm physical child termination and managed-cache checkpointing, and
resolve durable health ownership. Lease expiry alone is insufficient. Uncertain
termination retains the blocked slot and requires explicit physical-stop recovery.

Container restart/recreation must not assume namespace identity survives. Use
the existing bounded provisioning hold, compare actual live fingerprints, and
refresh containment/transport receipts for the final running namespaces before
activation. Preserve the persistent same-owner managed credential cache; adding
observability keys alone does not require a new login. Receipts do not contain
observability fields, but still validate deployment/boot/PID/network/cgroup,
image/CLI/policy, resources, model/account binding and freshness. Never reuse a
receipt from different live fingerprints. Parent decides whether unchanged
provider evidence can be retained under the existing acceptance procedure;
configuration edits alone do not grant acceptance. Adding an approved collector
route or SDK threads requires its actual containment/resource facts to be checked.

## Bounded later acceptance

After main-owner wiring and approved transport, parent checks actual received
resource attributes, one controlled execution span/origin link and corresponding
bounded metrics, plus refreshed queue gauges. Worker SQL readiness alone is not
telemetry readiness. Inspect only safe IDs/kind/state/reason/version metadata:
no prompts, images, results, credentials, CLI output or private configuration.
Confirm exporter failure remains bounded/nonblocking and actual PID headroom
remains adequate. This handoff performs no inference or remote validation and
makes no collector/Tempo delivery claim.
