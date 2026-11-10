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
