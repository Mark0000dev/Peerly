# OPS02 technical observability developer progress

10 November2026. Exclusive deployment/observability/** plus this ledger. No backend
source, root compose, provider/secret access, remote monitoring config, Git or
deployment changes. Parent owns live inventory/runtime inputs and release.

## CODE COMPLETE candidate — local native validation pending

Implemented one private nonroot/read-only OTel Collector Contrib0.165.0 and Tempo
single-binary3.1.1 stack, both registry-index pinned. Actual Python SDK emits OTLP
HTTP traces/metrics and bounded source-sanitized JSON stdout. Collector has
independent trace/metric/log allowlists, no raw exception/body/debug export,
fixed service resources and bounded memory, batches, persistent queues/file caps,
HTTP message sizes and retry budgets. Parent acknowledged no-socket RFC5424
Docker syslog transport with bounded nonblocking buffers; no host log mounts,
privileged container, Docker socket or root initialization. App enabling/driver
changes are examples for parent review, not applied configuration.

Loki native OTLP exporter is template/runtime-input only: existing version/schema/
structured-metadata/auth/private link must be inventoried before deploy. Existing
Prometheus scrape config is a merge template, optional remote-write overlay is
mutually exclusive and requires a verified receiver. Existing Grafana import/
datasource templates use actual source metric names with explicit underscore/
no-suffix translation. Actual HTTP/worker/email/media/request/change/AI metrics
are inventoried; no fabricated DB-pool/SSE/backup/outbox-age metric panels.
Alerts/rule behavior definitions include low-volume/SSE exclusions, native
telemetry/worker signals and real filesystem headroom/missing capacity wiring.

Primary official release/source docs and registry metadata reviewed. Critical
Tempo source evidence: retention0 computes a cutoff at now and is NOT no-expiry.
Explicit compaction_disabled prevents retention jobs, also disables compaction;
README covers fragmentation, finite hot storage, saturation/drop risk and required
parent storage/backup/verified-archive policy. Local volume is not an infinite
retention/durability guarantee. Full monitoring/staging acceptance not claimed.

Meaningful bounded validation definitions are implemented: native collector+
remote-write/Tempo/compose parsers, promtool rule behavior/PromQL/config, hardening
startup, actual OTLP metric normalization/cardinality filtering, source formatter
JSON→RFC5424→native OTLP HTTP with controlled503/recovery and secret canary,
actual Tempo ingestion/query/redaction, owned container/network cleanup. All
infrastructure stdout/stderr/failures retained; no live endpoints/credentials or
application tests used. Target batch has NOT run at this checkpoint.

Remaining code in initial OPS02 scope: none. Next: one coordinated local native
config/transport batch, fix concrete failures if any, freeze source hashes/logs
and hand off parent resource/runtime contracts. Remote inventory, TLS/auth,
existing datasource rendering, actual capacity scrape and archive/recovery remain
parent acceptance prerequisites.

## Final bounded native/protocol evidence —10 November2026

CODE COMPLETE and local configuration/protocol proof complete. Final pipeline run
/tmp/peerly-ops02-validation-20261110-a7/result.json: CLI0,12.72s, source drift0,
all three owned containers/network removed. Actual source formatter sample,
Prometheus exposition, Tempo trace response, sanitized OTLP log export and raw
infrastructure stdout/stderr preserved. No backend/DB/browser/provider/remote
monitoring calls. Native checks cover collector/optional remote-write config,
Tempo config, compose, promtool rule behavior and dashboard PromQL, nonroot UID10001/
read-only startup, actual no-suffix metric/label translation, redaction canary,
controlled OTLP HTTP503→bounded retry→success, genuine Tempo ingest/query.

Concrete native/environment fixes retain original failure evidence in a1–a6:
syslog native minimum message64KiB; Tempo explicit config.verify=true argument;
promtool private writable tmpfs; generated inputs piped through stdin because
Docker Desktop does not share host/tmp bind mounts; Tempo joins the approved
monitoring network as well as internal telemetry (internal-only network did not
publish host port); explicit internal Tempo query/scheduler addresses; canonical
collector exporter name otlp_http replaces deprecated alias. No diagnostic filters,
validator relaxation, package/app changes or warning-level suppression.

Actual internal exposition/source metadata also showed collector counters use no
_total suffix. Corrected only failed-export rule and added an environment-scoped
missing-span-counter regression. One lightweight native promtool check/test/config
follow-up at /tmp/peerly-ops02-validation-20261110-alert-final: allCLI0/3.28s; no new
three-container protocol batch. Optional remote-write compose merge supplied and
validatedCLI0 with synthetic inputs; default does not enable forward mode. Parent
must select scrape OR verified remote-write, not duplicate series.

Known pinned Tempo startup warnings are preserved, NOT resolved/hidden: deliberately
disabled optional metrics-generator; WAL creates blocks subdirectory then reports
it as unowned during rescan (official source verified). Collector runtime stderr
is empty in final proof. Local protocol pass is not a warning-free whole-stack or
external-staging acceptance claim. No real Loki compatibility/auth/TLS, live
Prometheus receiver, remote Grafana render, storage/backup budget or retention/
archive/retrieval evidence is inferred. Capacity signal remains mandatory parent
wiring; finite queues/disk can drop/reject telemetry. Full deployment remains parent.

All checks ended and CPU released to Noether; no next runners planned. Final
source/config hashes and immutable copy are recorded in the OPS02 handoff manifest
under /tmp for selective parent checkpoint. Existing observability baseline docs,
root/staging compose and backend runtime configuration remain unmodified.

## Concrete Compose tmpfs correction and S3 preparation —10 November2026

Parent found a real deployment-config bug: YAML flow-list comma parsing had split
each tmpfs mount into five strings. Only those two lists were corrected to one
quoted scalar each. Previous55d6e7 handoff/proofs and original compose ec00ac65 hash
remain immutable; corrected compose hash24665b645e6d2f845d288290559a98b94889b5f7a1b12a2790061eece4f05096.

Unlike earlier custom Docker CLI protocol proof, a focused **actual docker compose
up** used the exact corrected repository compose, no override/custom service flags,
private synthetic runtime inputs/networks and private fixture data paths. Actual
render, daemon inspect, startup/readiness and down evidence are preserved under
/tmp/peerly-ops02-compose-proof-20261110-cnc6donl. HostConfig.Tmpfs exactlyone/tmp
16m/32m, UID10001/read-only/cap_dropALL; collector health and Tempo ready both200.
DownCLI0, no project containers, fixture networks/directories removed. Nonroot ACL
fixture access/cleanup used no host privileges; actual production data ownership/
capacity remains parent provisioning. Docker local client27.4.1/daemon27.3.1 is
recorded; this is not a remote Docker24 startup claim. CPUEND sent to both leads.

Owner actual monitoring inventory now rules out placing new services on the nearly
full monitoring host. No remote config or deployment attempted. Optional staging
Tempo S3 block-backend source prepared from official3.1.1 fields, explicit runtime
endpoint/region/bucket/prefix/access/secret inputs, TLS and bounded request attempts;
local durable WAL/live-store/scheduler paths stay under parent-provisioned bounded
storage. No invented total-WAL native limit: memory/block sizes are distinct.
Read-only nonroot/network-none one-shot filesystem-budget preflight fails closed
when actual statvfs size exceeds parent cap or headroom is insufficient; no quota/
mount/root operations. Existing15%/missing filesystem alerts require real staging
mount labels. Retention/compaction disabled; bucket lifecycle/backup/archive and
S3 auth/write/retrieval remain explicit parent checks, no inferred cloud readiness.

S3 work is configuration/runtime-input preparation, not actual S3 access. Its
field-compatibility check runs native config.verify before app/backend creation,
network disabled, with visibly synthetic values; no real secret or provider call.
Storage-budget behavior definitions cover bounded admission, fake directory quota,
absolute/percentage headroom and invalid inputs. No full protocol/browser/DB suite
is repeated for this extension; exact local Compose proof remains separately pinned.

Final extension evidence: /tmp/peerly-ops02-s3-prep-20261110-iaeoic04/result.json,
native S3 config.verify/network-noneCLI0, S3 compose mergeCLI0, four storage-budget
behavior testsCLI0, actual bounded-tmpfs preflightCLI0 and optional WAL alert native
syntaxCLI0. No S3 process startup/network/auth/write/flush/read was attempted.
Exact corrected base Compose daemon proof remains PASS at cnc6donl, source hash
24665b64 unchanged. All source artifacts/refinements are frozen in the new selective
handoff; original55d6e7 manifest is preserved unchanged. No active runner/container,
no root/staging compose edits or remote monitoring changes. Parent has actual
mount/quota provisioning, scoped credentials/policy, runtime budget and remote
inventory/deploy acceptance; this is CODE COMPLETE preparation only.

## OPS03 runtime configuration followup — code complete, native proof pending

10 November2026, parent reauthorized only collector/compose/Prometheus rules,
technical dashboard and coordinated native validator. Baseline S3/tmpfs1746 and
strict Python checkpoint435 retained; Nash exclusively patches/runs validate.py.
Frontend observation sources remain untouched in their /tmp checkpoint.

Collector now admits actual Noether-accepted db.query.duration (seconds;
finite pool/operation/outcome), db.pool.checked_out/configured_size (BASE only),
sse.connections.active/closed, sse.frames, sse.delivery.lag, sse.send.duration,
sse.resets and AI queue.sample.fresh/age. DB spans retain db.query with only
postgresql/fixed pool/AST operation metadata. SQL/parameters/error events remain
excluded; unknown metrics and attributes retain source-side rejection.

New hostmetrics/capacity receiver has ONLY filesystem scraper, virtual filesystems
included to observe overlay, strict mounts `/` and `/var/tempo-capacity`. Collector
mounts the actual Tempo data directory readonly at the latter path. No host root,
proc/socket mounts, caps, privilege, CPU/RAM/network/process scrapers or private file
reads. Dedicated capacity pipeline does not pass through the app source filter:
it only accepts native system.filesystem.usage and free/reserved/used states,
keeps only mountpoint/state labels, forces service peerly-collector-capacity plus
actual environment/release. OTLP cannot spoof filesystem measurements through the
application allowlist. Native underscore translation is PENDING proof, not assumed
accepted because a YAML parser succeeds.

Every app metric query scopes job=peerly-app-metrics; collector internal queries
scope peerly-collector; existing Tempo scrape remains peerly-tempo. All AI queue,
slot and circuit graphs/alerts require matching sample.fresh==1; missing and stale
freshness have separate signals. No old/unknown queue values are rendered as zero.
Dashboard adds actual DB/SSE measurements and namespace root/WAL headroom. Rules
replace node_exporter assumptions with native filesystem free/total, reserved bytes
excluded from usable headroom, root15%/1GiB and WAL15%/256MiB provisional alerts.
Parent still calibrates actual bounded filesystem/storage budget and live capacity.

Meaningful rule cases preserve existing REST volume/SSE/counter tests, add cross-SaaS
job collision negatives, AI stale/missing/fresh gating, native reserved/free capacity,
WAL absolute low headroom and healthy-capacity negatives. One bounded native batch
will prove actual names/labels, statfs-only two mounts, readonly same bounded Tempo
fixture, app allowlist/privacy/unknown rejection and rule counter behavior. No broad
backend/frontend suites or remote/service activation in this followup.

Known handoff-only stale documentation outside the delegated file set:
`prometheus/prometheus.yml.template` trailing comments and README older node-exporter
capacity guidance need parent integration refresh; their actual scrape jobs already
match required job names. Optional remote-write profile has not been expanded to
ship the dedicated capacity pipeline: default private pull is the owned target;
parent must consciously integrate capacity export before opting into remote-write.

Primary pinned0.165 sources: filesystem scraper metadata/config and implementation:
https://github.com/open-telemetry/opentelemetry-collector-contrib/blob/v0.165.0/receiver/hostmetricsreceiver/internal/scraper/filesystemscraper/metadata.yaml
https://github.com/open-telemetry/opentelemetry-collector-contrib/blob/v0.165.0/receiver/hostmetricsreceiver/internal/scraper/filesystemscraper/config.go
No live monitoring compatibility or Tempo S3 flush/query success is claimed.

### Actual native acceptance receipt

Nash executed the ONE bounded native batch: PASS14.19s,
`/tmp/peerly-ops03-native-yipc5ntx/proof/result.json`, source_drift[].
`source-manifest.json` pins the exact accepted configuration/driver and parent
inputs. `ops03-metrics.prom` and `namespace-capacity.prom` retain native metric
translation/privacy evidence; `promtool-rule-behavior.log` proves15 rule cases,
all26 expressions in25 panels parsed. Actual readonly shared bounded WAL filesystem
states sum to256MiB; only the two admitted mounts export. DB query span was retained,
private canaries/SQL were absent. Owned3containers/network/WALvolume were removed.

Not a zero-warning claim: raw collector runtime log retains hostmetrics alias
precation (canonical host_metrics in0.165) and unset root_path container-filesystem
notice. The latter reports precisely the intended namespace scope; no host access
was added or logs filtered. Official factory supports explicit root_path='/' for
current namespace, without host mounts; any alias/root_path correction needs its
own exact new candidate evidence rather than borrowing this receipt.

Concrete scrape integration issue FOUND in prior native exposition: exporter sets
job=studymate-api (and its actual worker/capacity service names). Existing template
honor_labels:true would replace peerly-app-metrics, making requested job-scoped
queries empty. Parent notified to set honor_labels:false/default, preserving actual
service_name and renaming conflicting exported_job. This template was outside the
explicit delegated file set, so no silent edit. Actual Prometheus scrape/job query
is NOT proven by rule fixtures or raw Collector exposition; parent/authorized tiny
focused followup must close it before monitoring-ready claims. No broad rerun.

### Final delegated scrape correction and focused Prometheus2.42 proof

Parent explicitly delegated the exact scrape-template/receiver correction after the
first freeze. `prometheus.yml.template` now sets honor_labels:false, so scrape job
peerly-app-metrics wins and the native resource job is preserved as exported_job;
service_name remains the actual application/worker/capacity service. Replaced the
template's old node-exporter comments with the concrete dedicated namespace metric.
Collector now uses canonical host_metrics/capacity and explicit root_path:'/' —
the CURRENT CONTAINER root, with no host root/proc/socket or additional permission.
Original9bc native receipt and both warnings remain untouched historical evidence.

Final focused proof PASS9.71s:
`/tmp/peerly-ops03-prom242-proof-PgCLP2/attempt4/result.json`, source_drift[].
Actual public Prometheus2.42.0 image (matching inventoried server version):
`prom/prometheus@sha256:d2ab0a27783fd4ad96a8853e2847b99a0be0043687b8a5d1ebfb2dd3fa4fd1b8`.
`query-evidence.json` shows actual scraped job=peerly-app-metrics,
exported_job=studymate-api, service_name=studymate-api; real dashboard counter rate
2.688/s; fresh-gated AI queue dashboard2 and actual AI-old rule expression600.
Both root/WAL dashboard headroom expressions are nonempty; native filesystem samples
expose ONLY '/' and '/var/tempo-capacity', exact bounded WAL total268435456 bytes.
Readonly mount, UID10001, readonly root and dropped capabilities were inspected.
Collector/Prometheus/helper warn-level runtime logs are empty; no log filters added.
The earlier14.19s complete protocol proof was not repeated; unchanged tests retain
that pinned receipt, while this proof covers only the concrete receiver/scrape delta.

Driver/environment failures were preserved, not erased: original proof directory
failed before startup because daemon cannot bind client /tmp; attempt2 found stopped
helper/tmpfs config was not retained; attempt3 found an internal-network ephemeral
port mapping absent. No product-source changes across those attempts. Final driver
uses a bounded16MiB config volume held by an owned32MiB helper and loopback-only
published ports on an owned Docker bridge. All helper/Collector/Prometheus containers,
network and both bounded volumes were removed; images and full evidence retained.
No shared Python driver, gateway/**, live monitoring or credentials were touched.

Final freeze: default private-pull configuration is locally proven. Parent still
owns remote inventory/auth/gateway/scrape activation and actual Tempo S3 flush/query
proof. Optional remote-write capacity export and older README guidance remain
explicit parent integration items, not claims of external monitoring readiness.
Frontend observations staging stayed untouched throughout this OPS followup.


## 11 November — actual S3 cold-read persistence proof

After the workspace move, parent ran a narrowly scoped real Tempo3.1.1 proof
against the owner's staging S3 bucket in an isolated operations prefix. Native
OTLP ingestion succeeded, a completed S3 block was observed, the writer was
removed, and a second instance with a fresh empty tmpfs WAL successfully read the
exact synthetic trace from S3. Both instances used the pinned image, UID10001,
read-only root, dropped capabilities, bounded512MiB memory and128MiB WAL.
The earlier historical attempt stopped at a five-second HTTP client timeout; this
proof allows a bounded30-second cold query and does not suppress failures.
No student data or application prefixes were involved. All owned probe objects
and containers were removed (both remaining counts0). Durable private result:
`../.peerly-ops/tempo-native-2cb46f501d55c26e7c1aa9f7/result.json`.

Parent also provisioned a dedicated1GiB ext4 loop-backed persistent WAL filesystem
on staging (actual filesystem capacity1020702720 bytes), preserving host partition
layout and existing application data. This is storage preparation, not a claim
that application telemetry, Grafana or alert delivery has passed acceptance.

## 11 November external compatibility candidate — CODE COMPLETE, proof pending

Parent delegated collector/Prometheus/dashboard/tests/docs; the ONLY base compose
delta explicitly authorized is PEERLY_AI_RELEASE defaultempty. Gateway/** and
alertmanager/** remain parent-exclusive; shared Python/native full driver untouched.
Noether/Nash confirmed exact10 worker.external instruments, service/pool, two sinks,
nine FailureCode values, snapshot freshness and separate completed-step semantics.
Collector now admits only those exact names/role/dimensions, rejects invalid sink/
state/reason and strips private extras. Queue/source/blocked panels and alerts use
fresh==1; missing/stale, oldest due/source backlog, dead/blocked and completed-cycle
visibility are separate. Existing app/job scoping and native FS pipeline retained.

Prometheus merge template matches actual gateway path-based HTTPS and peerly-read
basic_auth with a separate protected plaintext password_file, no stale Bearer input
or htpasswd reuse. Actual targets/CA/passwords remain parent runtime inputs.

Diagnostic source contract coordinated with Noether: ai_runtime_failure plus exactly
three finite ai_runtime_* fields. Wrong-service/invalid diagnostic packets rejected.
AI log release uses PEERLY_AI_RELEASE only; unknown/empty is omitted rather than
borrowing the core release. Current producer acceptance/image provenance remains
Noether/parent-owned and will be linked to the final receipt when provided.

New external-metrics.json supplies actual named positive and adversarial unknown/
Dev-sink/private-field/native OTLP cases. Rule definitions include fresh/stale/missing,
source backlog with empty materialized queue, exact sink reason, cross-SaaS freshness
collision and independent last-cycle storage/age checks. Code complete first: ONE
focused native Collector/Prometheus2.42 config/metric/log/rule proof follows; no
previous full protocol/PG/backend/frontend matrix is being restarted.

### External compatibility final local acceptance/freeze

ONE focused batch with bounded fixes: PASS17.51s, persistent evidence (not lost /tmp)
`../.peerly-ops/aquinas/ops-external-compat-20261111-6_f9uikb/attempt3/result.json`;
source_drift[]. Actual Collector0.165 native metric admission verifies all10 external
source instruments and worker_external DB pool, exact finite labels, private/unknown/
Dev rejection. Prometheus2.42 checks actual path-based HTTPS/reader password_file
config,20 rule cases and all36 expressions in35 dashboard panels. No actual remote
TLS/auth/provider acceptance inferred from configuration checks.

Noether's accepted typed producer was used directly through SafeJsonFormatter, not
a guessed log DTO: diagnostics packet SHAad20d26cfbf94dd9a61c0a0418876a806c0ee033600097b41ab4861e7bc2d7de,
formatter056dd9626b35975bf034201473748f3608e6d1b11411757ea86f8556559d6f58.
Native syslog→OTLP boundary retains the3finite fields and rejects invalid/incomplete
and wrong-service diagnostic packets. Two cases prove AI empty version OMITTED and
explicit AI release independent of core/external release. Warn-level runtime logs
are empty. All owned helper/sink/collector cases, network and bounded volumes removed.

A genuine prior resource-aliasing defect was reproduced: log-context assignment
mutated shared ResourceLogs identity for mixed services, accepting a wrong-service
AI packet and applying AI release policy to core. Receiver copy of appname into
resource.service.name BEFORE conversion/grouping fixes the actual boundary. The
negative attempt2/decode-1.log and source-manifest remain intact. First driver-only
read-only /tmp Promtool panic is also preserved; a bounded64MiB test tmpfs corrected
that harness issue without relaxing rules or changing product behavior.

Current infrastructure policy updated per parent: reader and log-writer are TWO
independent TLS roles. Dedicated64MiB Alertmanager is on MONITORING host at internal
peerly-alertmanager:9093, not a public stage alert-write gateway/role. Gateway/** and
alertmanager/** untouched; all compose changes are the single approved AI env entry.
No backend/Python/provider/runtime/API/source changes, no whole-suite/full protocol
repeats. Parent owns publication/live deployment/image provenance. Final nine-file
compatibility handoff is independent of the canonical backend publication exclusion.


### 2026-11-11 — actual health-route compatibility follow-up

Separate from frozen external-worker nine-file receipt `4b867d9657f126679398465ce9904ecff12fe09d6413d710b8f5f8bbf65194a4`. Actual `presentation/health.py` mounts `/api/health` and `/api/ready`; Collector metrics/log route and span-name allowlists now retain these exact paths instead of obsolete `/healthz` and `/readyz`. Span route attributes use the same closed route policy. Unknown/private route values are removed; unknown span names become `technical.operation`. REST dashboard and SLO expressions exclude both health probes and the existing SSE route.

Focused native proof: `../.peerly-ops/aquinas/ops-health-routes-20261111/result.json`: PASS, 36.99s including local Docker startup, no source drift. Exact candidate Collector exported both accepted paths and stripped five negative route cases across metrics, seven logs and seven spans. Actual Prometheus 2.42 passed two focused rule cases: abundant healthy readiness traffic cannot dilute REST failures; health-only failures cannot trigger the REST error SLO. Only isolated local fixtures, no remote monitoring/provider access. Owned containers/network/tmpfs volumes removed; previous native warnings/failure receipts remain unchanged. No repeat of unrelated protocol matrix; no external deployment claim. Explicit capacity root `/` remains container root, not host-root access; capacity mount scope remains exactly `/` and `/var/tempo-capacity`.
