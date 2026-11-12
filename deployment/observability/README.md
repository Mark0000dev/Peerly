# OPS02 private technical observability bundle

## Parent integration — 11 November 2026

The staging layout now uses `gateway/staging.compose.yml` after the base and S3
overlays. It exposes authenticated GET/HEAD metric and Tempo query paths under
`/peerly-observe/` on the existing staging TLS host. The collector ingestion port
remains private. `gateway/monitoring.compose.yml` runs separately alongside the
existing Loki and forwards only authenticated POST requests at
`/peerly-ingest/staging/logs/v1/logs`. Reader and log-writer credentials are
independent; both ingress and the narrow nginx gateway verify authentication.

`alertmanager.compose.yml` is a standalone deployment on the **monitoring host**,
on its existing Prometheus/Grafana network. This keeps notifications independent
of the application VPS. Its unique service name is `peerly-alertmanager`; it
does not replace the old shared `alertmanager` service or expose public ports.
Render `alertmanager/alertmanager.yml.template` with the confirmed integer Peerly
Dev chat ID and mount the bot token as a protected UID65534-readable file. Only
`owner="peerly-team"` notifications reach that group; unrelated alerts use an
empty receiver. Native CI verifies both routes without any provider access.

Merge the scoped scrape jobs and alert groups into the existing Prometheus,
preserving other projects. Each TLS scrape job explicitly uses30s/15s interval/
timeout rather than inheriting another project's shorter global interval. The
reader password file contains the plain private service password, never its
server-side htpasswd entry. On single-file bind mounts, preserve the file inode
when replacing validated content, then send SIGHUP; retain rollback copies.
Prometheus and Grafana access the new Alertmanager directly at
`http://peerly-alertmanager:9093` on their existing private Docker network.

Actual remote acceptance and remaining application activation are recorded in
`docs/planning/observability-progress.md`. Native source tests alone do not prove
that application exporters, external-delivery consumers or historical archives
are active. The existing Loki hot retention still requires a verified archive
path before admitting external users; S3-backed Tempo blocks are primary storage,
not an independent backup.

Deployable configuration, not an inventory, remote deployment or monitoring-ready
claim. Application telemetry is currently optional; this task does not enable it.
Parent owns real endpoints/auth, network/proxy integration, storage/backup budget,
actual datasource UIDs, root compose changes and any deployment. Umami/product
analytics, public browser ingestion, operator inspection and live provider tests
are outside this bundle.

## Implemented topology and trust

One OTel Collector Contrib receives application OTLP HTTP traces/metrics on4318
on the actual private application network, alias `peerly-otel`. No OTLP port is
published. Tempo single-binary receives HTTP on its isolated telemetry network; Tempo also joins the approved monitoring access network for query-port binding;
its query/metrics3200, collector scrape8888/8889, health13133 and syslog5514 bind
host **127.0.0.1 only**. Existing remote Prometheus/Grafana need a parent-approved
private tunnel or authenticated TLS reverse proxy. Do not expose collector, Tempo
or Grafana to product users, publish these ports on0.0.0.0, or send browser data
directly to collector.

The parent-reviewed `application.override.yml.example` is a merge example, never
a standalone root stack or automatic deployment. Configure current API/email/
media/requests/changes services with actual `OBSERVABILITY__COLLECTOR_ORIGIN`,
`__ENVIRONMENT`, `__RELEASE` and `__TRACE_QUEUE_CAPACITY`. The exact Python runtime
appends `/v1/traces` and `/v1/metrics`, uses ALWAYS_ON spans, bounded512 SDK trace
queue by default, two-second export timeout,30s metrics cadence. Do not point the
origin at a URL with path, credentials, query or fragment. No second SDK or Alloy
is installed. AI configuration is a separate parent-owned worker stack; its actual
resource name `studymate-ai-worker` is allowed but is not created or enabled here.

## Sanitized logs without host privileges

Log releases come only from the producer's validated `service_release`: a
nonzero lowercase40-character Git SHA. The syslog receiver assigns it before
grouping resources, so rolling versions of one service and the separate AI
worker retain their own identities. Missing or invalid values omit
`service.version`; Collector deployment variables never invent a release for
legacy records. Trace and metric resources retain their original SDK versions.

Source `SafeJsonFormatter` emits `time`, `level`, enumerated `event`, optional
method/route template/status/duration_seconds, opaque IDs, outcome/worker and safe
stack frame metadata. It does **not** emit the arbitrary Python log message or
exception string. Those actual fields differ from the older aspirational docs.
`collector.yaml` drops malformed syslog/JSON quietly at ingress (avoiding payload
leakage in parser diagnostics), keeps a bounded schema, validates IDs/routes and
removes raw stack/unknown keys. Source stack frames are deliberately not collected
in this minimal bundle. Only fixed known service tags are accepted. Loki receives
only the sanitized OTLP payload, with service/environment/release resources;
request/actor/trace IDs remain body/structured data, never metric or Loki index
labels. No `debug` exporter or raw-content logger exists in the real pipeline.

Use Docker's **per-container** syslog driver, RFC5424micro over TCP to local5514,
with a fixed tag matching the actual SDK service name and nonblocking1MiB buffer.
No Docker socket, daemon-wide logging change, `/var/lib/docker` mount, host network,
root user or additional capability is needed. Parent acknowledged this transport.
Collector must be listening before containers are recreated: Docker initializes
its syslog connection at container start. Nonblocking mode protects business
latency but **can drop logs** when its buffer is full. Collector-down startup may
still fail connection initialization; parent must use collector-first ordering.
Do not route collector/Tempo own logs back into themselves or collect both stdout
and an OTLP log copy. Their local Docker logs rotate5MiB×2; this is bounded local
service diagnostics, not durable collection/archive or zero-loss retention.

## Runtime inputs and compatibility gates

`compose.yml` deliberately requires the actual environment, existing application
network, approved monitoring egress network and two dedicated data directories.
Parent precreates directories owned by10001:10001 with restrictive permissions;
containers run nonroot/read-only with cap_drop ALL/no-new-privileges. No root init
container/chown or privileged permission workaround is bundled. Existing volumes,
secrets, S3 or remote hosts are never mounted or inspected by these scripts.

`LOKI_OTLP_ENDPOINT` is the **existing** authenticated HTTPS OTLP base, normally
ending `/otlp`; the native exporter appends `/v1/logs`. It is not the legacy
`/loki/api/v1/push` endpoint. Inventory must confirm native OTLP support, actual
Loki version, compatible schema/store and structured-metadata settings before
use. Loki3 with TSDB/v13 is the documented baseline; that is **not** a claim about
the owner's existing installation. `LOKI_AUTHORIZATION` and `LOKI_TENANT_ID` are
owner runtime inputs (empty only when the actual server deliberately needs none).
Never commit or print resolved auth, run `compose config` with real secrets to a
log, disable TLS verification, or invent remote endpoints/tenant IDs. Custom CA/
mTLS can be provided by the parent in a reviewed mount/overlay after inventory;
no fake certificate is included. The OTLP HTTP boundary double in validation is
not a Loki server or proof of existing remote compatibility.

Existing Prometheus normally pulls the private8889 exporter plus collector8888
and Tempo3200. `prometheus/prometheus.yml.template` is a merge template requiring
the actual staging gateway TLS host:port, optional private CA and dedicated reader password file. It does not replace existing global jobs,
Alertmanager routing or credentials. `collector/remote-write.yaml` is an optional
second native `--config` only when the **actual** receiver URL/auth/support is
confirmed; provide `PROMETHEUS_REMOTE_WRITE_URL`/`PROMETHEUS_AUTHORIZATION` and
replace metrics exporters with remote-write. Do not scrape and remote-write the
same stream. Remote-write uses one consumer,64-item memory queue and60s retry
budget, no unbounded disk WAL; restart/outage can lose metrics. It is not enabled
in default compose. `remote-write.compose.yml` supplies the two command config paths, required receiver environment and read-only overlay mount when explicitly merged by the parent; no remote URL/auth is embedded. The scrape exporter expires unrefreshed series after2min so a
stopped producer is not kept apparently alive indefinitely.

## Exact source metrics and dashboard contract

Prometheus translation is explicitly `UnderscoreEscapingWithSuffixes`: original
instrument dots become underscores; monotonic counters acquire `_total`, unit `s`
acquires `_seconds`, native filesystem unit `By` acquires `_bytes`. Annotation units
`{request}`, `{step}`, `{hint}` add no unit token. Histograms expose `_bucket`,
`_sum`, `_count` after the canonical base. OpenMetrics and sampled exemplars stay
enabled: suffix-free counter families fail actual Prometheus 2.42 exemplar parsing.
`tests/sdk-metrics.json` records the closed source-declaration/native mapping and
real SDK protobuf fixtures, including adversarial View-filtered exemplar attributes.
Collector clears only `exemplar.filtered_attributes`; sampled trace/span IDs, value
and timestamp survive. Datapoint-only filtering does not sanitize exemplar attributes.

| Actual source instrument | Prometheus base | Dimensions |
| --- | --- | --- |
| http.server.requests | http_server_requests_total | http_request_method,http_route,http_response_status_code |
| http.server.request.duration | http_server_request_duration_seconds | same |
| worker.email.steps / worker.email.step.duration | worker_email_steps_total / worker_email_step_duration_seconds | outcome |
| worker.media.steps / worker.media.step.duration | worker_media_steps_total / worker_media_step_duration_seconds | worker,outcome |
| worker.requests.expiry.steps / worker.requests.expiry.duration | worker_requests_expiry_steps_total / worker_requests_expiry_duration_seconds | outcome |
| worker.requests.finalized | worker_requests_finalized_total | state |
| worker.changes.steps / worker.changes.duration | worker_changes_steps_total / worker_changes_duration_seconds | maintenance,outcome |
| worker.changes.hints | worker_changes_hints_total | maintenance |
| worker.ai.attempts / worker.ai.execution.duration | worker_ai_attempts_total / worker_ai_execution_duration_seconds | kind,outcome,reason when present |
| worker.ai.wait.duration | worker_ai_wait_duration_seconds | kind |
| worker.ai.queue.depth / worker.ai.queue.oldest | worker_ai_queue_depth / worker_ai_queue_oldest_seconds | none |
| worker.ai.slot.occupied / worker.ai.circuit.open | worker_ai_slot_occupied / worker_ai_circuit_open | none |

Only `service_name`, `service_version`, `deployment_environment_name` are promoted
resource labels. Random service.instance.id and user/resource/trace/request IDs
are excluded. Collector's own metrics are separate infrastructure signals. The native internal Prometheus reader also emits its counter names without `_total`; the failed-export rule uses `otelcol_exporter_send_failed_spans` / `otelcol_exporter_send_failed_log_records` from pinned exporterhelper metadata, and queue names are verified in the actual local exposition.
Sources: backend `infrastructure/observability/{runtime,tracing,email,media,requests,
changes}.py` and `infrastructure/ai/telemetry.py`. A queue gauge represents the
worker's last observed snapshot, not an uninstrumented DB live query. Email worker
success is service acceptance, **not inbox delivery**. Worker step counters are
observations, not unique business completions or a reconstructed canonical event.

Import `grafana/peerly-technical.json` into existing private Grafana and choose its
actual Prometheus datasource. `datasources.yml.template` has unresolved explicit
UID/URL inputs, not guessed live IDs; parent adds real auth/TLS/access policy.
No new Grafana is deployed. Drilldown templates correlate trace_id from log body
to Tempo. JSON/schema checks are not visual/datasource acceptance. Actual DB-pool,
SSE and external outbox instruments are now admitted; details and honest semantics
are below. Exporter log-drop/backup verification signals are not invented.

## Resources, retention, capacity and alerts

Pilot starting limits: collector256MiB/0.5CPU (memory limiter192MiB/spike32MiB),
Tempo512MiB/0.5CPU; measurement may require a parent-approved adjustment. Batch128,
max256, OTLP request1MiB, syslog message64KiB/16 connections (native receiver minimum). Each persistent
trace/log exporter has64 queued batches, one consumer,60s retry budget and a
64MiB bbolt-file cap (two files up to128MiB plus filesystem overhead). Parent
still budgets filesystem quotas/headroom: memory and disk are finite. Monitor
send failures/queue capacity. Exhaustion can reject/drop telemetry and cannot be
represented as healthy zero traffic. SDK/stdout losses before collector cannot be
reconstructed or fully measured by collector counters.

Tempo3.1.1 actual source computes retention cutoff as `now - retention`; **0h is
not no-expiry**. Explicit `overrides.defaults.compaction.compaction_disabled: true`
prevents both retention jobs and compaction. This avoids silent time-based trace
deletion but increases block/index fragmentation. It does not guarantee infinite
hot capacity, disk durability or backups. Local volume is a minimal single-node
trace store; parent must decide storage budget, verified archival/retrieval,
backup/restore, monitoring server location and future compaction/retention policy
before relying on full monitoring. Full disk can stop new collection. Do not
silently enable TTL, delete blocks or clear queues to recover space.

`prometheus/alerts.yml` is one owner-managed ruleset: telemetry scrape down; REST
5xx>5%/p95>1s with≥100 observations and10m hold (SSE excluded); repeated email
attempt failures; missing/stopped email step observations; AI queue age/circuit;
collector send failures/queue saturation; **Tempo filesystem below15% free** and
missing capacity signal. Thresholds are provisional, not an SLO guarantee. The namespace-only filesystem receiver exposes only collector root overlay and
readonly `/var/tempo-capacity`; `PeerlyCapacityTelemetryMissing` reports missing
native samples. No privileged host exporter, Docker socket or host CPU/RAM claim. Missing optional AI metrics are unknown, not evidence of a running worker.

Runbook: telemetry down→check private link/process/storage; export failure→check
Tempo/Loki status/auth and queue without discarding data; REST regression→route
metrics then trace/log IDs, never request bodies; email failures→owner SMTP checks
without OTP/recipient export; capacity→expand approved disk or verified archive,
never ad-hoc deletion. Parent adds actual dashboard/runbook URLs and Alertmanager
receivers/grouping/escalation. Telegram credentials/messages are not configured.

## One bounded local validation batch

After code complete and resource coordination:

```
python3 deployment/observability/validate.py --output /tmp/peerly-ops02-validation
```

This uses only pinned containers and synthetic canaries, no existing stack/network,
secrets, real provider, production source changes or remote monitoring endpoint.
It records native collector validation (including optional remote-write merge),
Tempo config verification, promtool checks/rule tests/dashboard PromQL parsing,
nonroot/read-only startup, actual OTLP→Prometheus names/labels, sanitized RFC5424
JSON→OTLP HTTP with one controlled503/recovery, and trace ingestion/query through
Tempo. Original failures and raw infrastructure stderr remain in the output;
no catch-and-pass or warning suppression. Owned containers/network are cleaned.
The fake sink proves transport/serialization, not real Loki compatibility.
Dashboard rendering, actual private TLS/auth/scrapes, capacity wiring, retention/
backup/restore and live end-to-end monitoring remain parent acceptance gates.

## Reviewed versions and primary sources

Pinned registry indexes and release links are in `images.json` (reviewed10Nov2026).
Official source/docs reviewed:

- [Collector releases](https://github.com/open-telemetry/opentelemetry-collector-releases/releases/tag/v0.165.0)
- [Syslog receiver](https://github.com/open-telemetry/opentelemetry-collector-contrib/blob/v0.165.0/receiver/syslogreceiver/README.md)
- [Prometheus exporter/translation](https://github.com/open-telemetry/opentelemetry-collector-contrib/blob/v0.165.0/exporter/prometheusexporter/README.md)
- [Remote-write exporter](https://github.com/open-telemetry/opentelemetry-collector-contrib/blob/v0.165.0/exporter/prometheusremotewriteexporter/README.md)
- [File storage bounds](https://github.com/open-telemetry/opentelemetry-collector-contrib/blob/v0.165.0/extension/storage/filestorage/README.md)
- [Docker syslog driver](https://docs.docker.com/engine/logging/drivers/syslog/)
- [Loki native OTLP requirements](https://grafana.com/docs/loki/latest/send-data/otel/)
- [Tempo3.1.1 single-binary configuration](https://github.com/grafana/tempo/blob/v3.1.1/example/docker-compose/single-binary/tempo.yaml)
- [Tempo retention scheduler](https://github.com/grafana/tempo/blob/v3.1.1/modules/backendscheduler/provider/retention.go)
- [Tempo retention cutoff](https://github.com/grafana/tempo/blob/v3.1.1/tempodb/retention.go)
- [Prometheus alert-rule tests](https://prometheus.io/docs/prometheus/latest/configuration/unit_testing_rules/)


## Native startup diagnostics retained

Pinned Tempo3.1.1 logs a warning when its optional metrics-generator is deliberately
unconfigured; no duplicate span-metrics/service-graph processor is enabled merely
to hide it. Its WAL New() creates a `blocks` subdirectory and RescanBlocks() then
warns that this directory is an unowned WAL entry (official tempodb/wal/wal.go).
These raw diagnostics are preserved and are not a claim of a clean warning-free
upstream runtime. Explicit query/scheduler addresses avoid the two automatic
single-binary address fallback warnings. No vendor patch/filter/log-level
suppression is used. Parent reviews these bounded limitations with storage policy.

[Collector exporter counter definitions](https://github.com/open-telemetry/opentelemetry-collector/blob/v0.165.0/exporter/exporterhelper/metadata.yaml).

## Parent inventory update and optional staging S3 block backend

Owner inventory received10Nov2026: existing Loki3.7.9, Grafana11.0.0,
Prometheus2.42.0, Umami3.3 and Docker24.0.2. Shared monitoring host has4GiB RAM,
about549MiB available and29GiB root at94% used/about1.9GiB free. **Do not place
collector or Tempo on that host.** Parent plans staging placement after checking
actual staging capacity/caps. These supplied version facts are not checks of Loki
v13/OTLP auth/private ingress, current datasource config or existing rule parser.
Native local parser proof used pinned Prometheus3.16; parent must validate the
actual2.42 rules/config before remote integration and verify dashboard import on
Grafana11. Existing templates intentionally use classic underscore metrics,
classic histograms and ordinary PromQL, not Prometheus3-only syntax/features.

`tempo-s3.compose.yml` optionally replaces Tempo's config with `tempo/tempo-s3.yaml`
and enables the native `-config.expand-env=true` loader. It uses actual3.1.1
`storage.trace.s3` fields: endpoint **host[:port] without scheme/path**, region,
bucket, prefix, access_key, secret_key, insecure=false (TLS) and optional
forcepathstyle. Inputs `PEERLY_TEMPO_S3_*` are required owner runtime values;
there is no endpoint/bucket/prefix/credential guess, remote access or automatic
migration of existing local blocks. Parent supplies scoped credentials later.
Avoid printing resolved compose/config/environment; envsubst is not a YAML
serializer, so parent must render a safely escaped config instead if credential
characters conflict with YAML syntax. No TLS skip or provider login is added.

S3 here is the **primary durable trace block backend**, not proof of an independent
archive/backup or a restore drill. WAL remains durable local staging storage at
`/var/tempo/wal` and actual3.x `live_store.wal.path=/var/tempo/live-store/traces`;
scheduler/shutdown data also stay under `/var/tempo`. All remain on the parent's
bounded persistent filesystem. `max_live_traces_bytes=64MiB`, block size16MiB,
query/complete concurrency2/1 and three bounded S3 request attempts are provisional
resource controls. They **do not bound aggregate WAL disk usage**. During an S3
outage local WAL can fill; no implicit time deletion, queue purge, infinite disk
promise or no-loss guarantee is made. Retention/compaction stay disabled in the
S3 config; parent must also verify that bucket lifecycle/retention rules do not
expire retained blocks. Archive/retrieval/encryption/backup/access policy remain
parent gates.

The optional S3 overlay adds a short-lived64MiB/0.1CPU nonroot, read-only,
network-none `tempo-storage-preflight`. It only reads statvfs, refuses an actual
filesystem larger than explicit `PEERLY_TEMPO_WAL_CAP_BYTES`, and requires≥15%
and `PEERLY_TEMPO_WAL_MIN_FREE_BYTES` free (default256MiB). Tempo starts only after
this succeeds. This makes an unsupported/unbounded shared root filesystem fail
closed; it does not set quotas or infer a per-directory project quota from global
statvfs. Parent provisions the dedicated bounded filesystem/mount with restrictive
UID10001 ownership; this bundle performs no privileged filesystem operation.
Project-quota-only deployments need a separate parent-verified enforcement path,
not a fake budget environment variable. Ongoing exhaustion is covered by the
existing actual-filesystem15% headroom/missing-capacity alerts; parent must label
the actual native `/var/tempo-capacity` filesystem metric and import `prometheus/tempo-s3-alerts.yml` for the provisional256MiB absolute headroom alert (adjust together with the runtime minimum). Parent adds approved disk-growth forecasting. Do not relabel the full monitoring host as this mount.

Official pinned source field references:
[Tempo S3 Config](https://github.com/grafana/tempo/blob/v3.1.1/tempodb/backend/s3/config.go),
[actual live-store WAL/resource fields](https://github.com/grafana/tempo/blob/v3.1.1/modules/livestore/config.go),
[native config/env expansion and verify-before-start](https://github.com/grafana/tempo/blob/v3.1.1/cmd/tempo/main.go).

## External delivery compatibility and private reader transport

Source contracts: infrastructure/observability/{external_delivery,delivery_queue}.py
and DatabasePool.EXTERNAL_DELIVERY, confirmed by Noether/Nash. Service is exactly
peerly-external-delivery-worker, pool worker_external (base1, no overflow).

| Actual instrument | Allowed point dimensions | Meaning |
| --- | --- | --- |
| worker.external.cycles | storage=available/unavailable | Completed loop step, NOT provider success |
| worker.external.storage.available | none | Last completed-step storage observation; unknown initially |
| worker.external.cycle.age | none | Seconds since completed step, NOT process heartbeat |
| worker.external.queue.depth | sink,state=pending/retry/dead | Exact retained-state counts, excludes leased/succeeded |
| worker.external.queue.oldest_due | sink | Seconds since oldest due pending/retry |
| worker.external.queue.blocked | sink,reason | One-hot actual finite FailureCode |
| worker.external.queue.sample.fresh/age | none | Current snapshot validity / seconds since last success |
| worker.external.sources.pending/oldest | none | Unmaterialized capture count / oldest age |

Only umami and telegram_support sinks exist. Nine reasons: transient, rate_limited,
credentials_unavailable, destination_unavailable, invalid_response, timeout,
lease_expired, cancelled, permanent. Unknown service/metric/sink/state/reason is
rejected; private extra point/resource attributes are stripped. No telegram_dev
application sink or application technical-alert producer was added.

Sampler:5s cadence,15s TTL,250ms total budget (75ms SQL/25ms lock). Failed reads
immediately invalidate snapshots; last-success age remains and is absent before
any success. Exact counts are not constant-cost with retained history. All queue,
blocked and source graphs/alerts require sample.fresh==1, never a zero default.
Source backlog is independent of materialized deliveries and remains visible if
routing stalls with zero delivery depth. Cycle/storage liveness is separate and
its30s stale threshold is provisional; exporter2min expiry still bounds visibility
if the entire SDK stops. Nothing here proves a provider accepted/read a message.

Prometheus jobs all retain their fixed scrape jobs (honor_labels:false). They use
HTTPS to the actual runtime `STAGING_OBSERVABILITY_TLS_TARGET`, with exact paths
`/peerly-observe/metrics/application`, `/collector`, `/tempo`. All authenticate as
peerly-read using a separate protected PLAIN reader password_file; never copy a
server htpasswd or separate log-writer password into it.
No credential value belongs in source. Reader/log-writer are two independent roles;
dedicated Alertmanager is monitoring-host private peerly-alertmanager:9093 and does
not need a public stage alert-write role. Parent renders target/CA/password-file
inputs, mounts them privately and owns gateway/Alertmanager activation. With a
publicly trusted certificate, parent may omit the custom ca_file stanza instead
of fabricating a CA file. Templates are not a live TLS/auth acceptance receipt.

Syslog provenance: PEERLY_RELEASE applies only to core/external services. AI uses
separately supplied PEERLY_AI_RELEASE from its actual running image provenance;
empty/unknown omits service.version. It never inherits a fabricated core release.
Actual finite ordinary diagnostic event ai_runtime_failure admits ONLY additional
ai_runtime_phase receipt_recheck/heartbeat/revoke/physical_cleanup/retire,
ai_runtime_code storage_unavailable/ownership_lost/receipt_rejected/
physical_stop_uncertain/credential_uncertain/cancelled/unexpected and
ai_runtime_failure_role primary/cleanup. Invalid/incomplete or wrong-service
diagnostic packets are rejected. Raw exception names/messages, SQL/DSNs/URLs,
provider tokens and private content remain outside the whitelist. Parent activates
actual source images; this packet is not an app-generated technical alert.

Focused local compatibility acceptance PASS17.51s is retained at
`.peerly-ops/aquinas/ops-external-compat-20261111-6_f9uikb/attempt3/` beside the repo.
It proves native metric filters, the actual typed source diagnostic, three service
identities, AI version omission/override,20 rule fixtures and36 dashboard expression
syntax checks using Prometheus2.42. Warn-level runtime logs are empty, cleanup done.
Initial driver tmpfs failure and genuine mixed-service resource alias failure are
preserved. Existing FS/Tempo/S3/syslog-retry receipts remain separate: no full-probe
repeat. Local BasicAuth/TLS config parsing is not actual remote TLS/auth or provider
acceptance; parent owns activation and runtime credentials.

Native focused acceptance exposed a prior mixed-service syslog resource grouping
defect. The receiver now copies attributes.appname to resource.service.name BEFORE
conversion/grouping; each service owns its resource identity before log transforms.
This prevents core/external packets inheriting AI version policy and stops a forged
core ai_runtime_failure from becoming an accepted AI packet. Native negative/raw
evidence is retained; finite body fields/privacy policy remain unchanged.


### Default CI SDK/exemplar regression

The existing `backend/.venv/bin/python deployment/observability/validate.py --output <new-owned-directory>` command now runs `sdk_metrics.py` automatically, in addition to the original native protocol/privacy/capacity checks. It reads the actual source Counter/Histogram/ObservableGauge declarations and units, fences them against the closed `tests/sdk-metrics.json` native mapping, and checks installed SDK/exporter versions against backend dependencies. JSON fixture presence alone is not acceptance: each run creates fresh actual Python SDK instruments and exports their real protobuf using the public OTLP HTTP exporter to the owned loopback Collector.

A bounded, hardened, isolated Prometheus2.42 instance must scrape every canonical SDK series and store all22 sampled counter/histogram exemplar series. The SDK View deliberately moves a private canary into exemplar filtered attributes. The stored exemplars must contain only the known trace/span IDs and original SDK value/timestamp (Prometheus millisecond precision). Missing canonical suffixes, a failed scrape, lost exemplars, extra exemplar labels or altered correlation/value/time fail the default command. Old `UnderscoreEscapingWithoutSuffixes` fails canonical selector checks and actual OpenMetrics parsing; disabling exemplars also fails the storage assertions. Public helper network endpoints are explicit loopback origins, redirects/proxies are excluded by the driver, output is synthetic only. No production SDK configuration, provider or credential is used. The unchanged CI workflow invokes this extended default command; no extra manual/private proof switch is required.
