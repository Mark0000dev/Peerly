# Accepted external-delivery lifecycle

The release CLI keeps a previously stopped or absent external worker stopped.
It does not add a service, change profiles/replicas, register destinations, send
provider probes, run migrations, reset retries/leases, or change target settings.
The coordinator owns initial activation and actual acceptance. All deployment and
recovery operations use the existing stack-4 state directory and `stack4.lock`.
The production rollout and native signing remain separate.

## Baseline and activation are separate operations

`deployment/staging/external-delivery.compose.yml` is an explicit baseline addition
for the SAME Portainer stack 4, endpoint 1, project `peerly-staging`. It is not
implicitly loaded by the CLI. Combine it with the reviewed actual core source,
not a stale public template substituted for that source. The initial addition has
both `deploy.replicas: 0` and profile `external-delivery`. The core source currently
has no external service; do not assume a daemon or another stack exists.

Required names, with no assigned values: `EXTERNAL_DELIVERY_IMAGE`,
`EXTERNAL_DELIVERY_RELEASE`, `EXTERNAL_DELIVERY_COLLECTOR_ORIGIN`,
`EXTERNAL_UMAMI_REVISION`, `EXTERNAL_UMAMI_ORIGIN`, `EXTERNAL_UMAMI_WEBSITE_ID`,
`EXTERNAL_UMAMI_HOSTNAME`, plus
the existing `PEERLY_DATABASE_URL`. Select a CI-published immutable backend digest
and its actual source SHA. An existing older digest is usable only if its source
and image actually contain the required worker/configuration/probe contracts.
Prove image/config/OCI bindings and preload exact images through the parent-owned
process. The overlay requires `pull_policy: never`; the helper performs no pull. Never choose `latest` or an unverified tag.

For staging the explicit hostname is `peerly-staging.aleksei-orlov.dev`. The
actual Umami settings require `UMAMI__HOSTNAME` in addition to revision/origin/
website. Hostname remains outside the canonical destination fingerprint, so
private-config comparison also checks it explicitly. User-Agent and automated
application provenance are fixed in the reviewed sender/transport/projection
code, not configurable environment flags. The image must contain that code.

The proposed overlay is Umami-only. It contains no Telegram token, chat, fake
placeholder or destination registration. A previously accepted configured set
may also include Telegram: runtime settings and pre-existing target fingerprints
must match its acceptance exactly. An unconfigured sink remains unconfigured.
Do not activate Telegram as part of a backend upgrade.

Before any initial activation, the coordinator establishes actual endpoint and
native-host ownership, the existing registered revision/fingerprint, database,
network reachability, bounded graceful behavior, collector identity and natural
cycle progress. A one-shot provider-send receipt is not permanent-worker
acceptance. Preserve the product activation check: a retained historical dead row
is not removed, retried or globally ignored here. Any explicitly reviewed recovery/
preflight for a known row belongs to the coordinator before initial acceptance;
this helper does not invoke or weaken that activation check. The helper proves Docker endpoint singleton state; it cannot discover
an arbitrary renamed/native host consumer. Host ownership remains a prerequisite.

For accepted active operation, the coordinator's separate reviewed activation
source must explicitly set replicas 1 and REMOVE the external profile. Accepted
active source may have no profiles and no ambient `COMPOSE_PROFILES`. This avoids
assuming Portainer selects a profile from a rendered service's presence. The CLI
never performs that source transition. Verify actual Portainer behavior before
acceptance; a Compose renderer result alone is not execution evidence.

## Host-only acceptance contract

Only after actual acceptance, install `/etc/peerly-release-ssh/external-acceptance.json`
as a regular root-owned file, group equal to the dedicated release user's primary
group, mode 0640, beneath root-owned directories. No environment variable, SSH
request or CLI argument can override this path. Missing file means stopped
bootstrap; malformed, duplicate-key, untrusted or stale state fails closed. The complete root admission document is reread and
compared before signals, recovery starts and each stack write.
Do not put this private file, its contents, or direct secret-Env hashes in Git,
workflow outputs, logs or artifacts. No populated acceptance example is supplied.

The exact JSON fields are:

- `version`: integer 1.
- `accepted`: the actual acceptance record below.
- `service_spec`: the full resolved external-service object from the accepted
  combined source, including exact private environment. It must reference the
  independently pinned digest, have replicas 1, no profile/build and `pull_policy: never`.
- `upgrade_source`: empty string to preserve the accepted binary, or the ONE exact
  reviewed main source SHA to upgrade when that same source is selected for core
  promotion. It does not authorize activation.
- `compatible_sources`: exact reviewed external-worker source SHAs, including an
  old worker source only when explicitly compatible for rollback. Review durable
  routing/projection/target/retry/lease behavior; schema equality is insufficient.
- `core_compatible_sources`: SEPARATE exact core/API sources permitted against the
  accepted live schema/config/API contract. Worker-role evidence must never be
  copied into this list to authorize core/API upgrade.
- `role_schema_evidence`: mapping for every external compatible source, each with
  exactly `image` (immutable reference), `config` (image config digest),
  `database_schema` (the actual current schema), `image_schema_head` (actual baked
  migration-source head), `entrypoint` (`studymate.external_delivery_worker`),
  `sinks` (exact accepted configured set), `evidence_id` (actual reviewed witness),
  `witness_kind: immutable_image_role_compatibility`. Bind the witness to actual
  image bytes/config/source and existing-table role execution, not a health claim.
  A read-only PYTHONPATH/source-overlay witness cannot authorize the unmodified
  base image. Establish actual immutable-image/source equivalence or a new exact
  image witness through coordinator-owned operations; no developer provider loop.
  A worker image containing migration61 can have a specifically proven Umami-only
  existing-table path on live0060 while the core/API image remains unchanged. This
  does NOT authorize DDL, native routes or core/API recreation; actual SQL probes
  still require0060 and the core-source contract remains separate.

`accepted` has exactly `version: 1`, `stack_id: 4`, `endpoint_id: 1`,
`project: peerly-staging`, `acceptance_id`, `service: external_delivery`,
`container_id`, `image_config`, `started_at`, `pid`, `config`, `host_config`,
`destinations`. IDs, PID/start time and Docker `Config`/`HostConfig` must come from
actual singleton inspection. User must be `10001:10001`; command must be the
actual `studymate.external_delivery_worker` module. `config.Image` is the immutable
backend reference and its OCI source/revision must match actual local image/config.
`destinations` contains the exact configured sink set, each with `sink`, positive
`revision`, and canonical hex `fingerprint` already present in the database. It
contains no credentials. Store the full private Docker Config to preserve every
actual Env value; fingerprints deliberately exclude credentials and cannot replace
that comparison. Never mint acceptance from a newly observed running worker.

The nonroot state directory remains mode 0700, private JSON mode 0600. Successful
recreation atomically writes `external-lineage.private.json` under the SAME state
root, anchored to the root-owned acceptance ID. A new attempt validates the entire
recreation scope against that root receipt. Root receipt/policy changes and lineage
retirement require coordinator handling under the same lock; unknown lineage blocks.
The application has no invented external ownership-slot/heartbeat table.

## Ordinary promotion and accepted binary upgrade

Core/frontend phases preserve the independently pinned external image and resolved
service configuration. Fresh owned-runtime and registered-destination checks run
before every stack PUT, followed by fresh full source/Env comparison. The worker
must remain the accepted physical singleton with the same PID/start/config while
its actual available cycles advance. Whole queue/attempt counters are not frozen:
normal durable consumption and lease transitions may progress naturally.

A reviewed external image upgrade occurs only after core/frontend verification:

1. Verify accepted runtime, exact registered/configured sinks, full private config,
   source/schema compatibility, and the exact preloaded target image/config/OCI.
   Both worker and API registry probes verify the actual live schema and target DB.
   Fsync the private before record and owned-stop intent before a signal.
2. Send only `POST /api/endpoints/1/docker/containers/{exact-id}/kill?signal=SIGTERM`.
   This Docker endpoint sends TERM, not SIGKILL. Observe at most 45 seconds of grace,
   with individually bounded transport calls. A late/unproven exit is failure.
   Never escalate to stop/KILL/delete. Require zero exit, no OOM/restart/error,
   unchanged prior Config/identity, and no remaining external executor.
3. Fsync actual clean-exit proof. Recheck the existing destination registry through
   the owned API container with fixed SELECT-only read-only transactions. Then
   freshly CAS the full stack/source/Env and PUT only the independent image/release
   pins, with `Prune=false`, `PullImage=false`. Profiles/replicas remain unchanged.
4. Require exactly one compatible new owned container and physical absence/stopped
   status of the old executor. Compare every private Config/HostConfig field, allowing
   only the image/release, digest-bound baked OCI labels, generated hostname and
   verified Compose image/config-hash metadata. Unexpected fields block.
5. Require canonical configured targets equal the accepted set, unchanged full
   existing destination registry, and fresh available cycles plus available storage
   and cycle-age gauges from the same version/environment/series under stable
   physical identity. No synthetic sends/claims or health-only success. Persist
   verified lineage before returning success.

The collector contracts are `worker_external_cycles_total{storage="available"}`,
`worker_external_storage_available`, `worker_external_cycle_age_seconds`, service
`peerly-external-delivery-worker`. They are not the core workers' outcome counters.
The fixed probes import the product's real settings/target conversion/fingerprint;
they never call worker startup or registration and never write application data.
No target, retry/backoff, blocked/cooldown, lease, queue or AI ownership mutation is
performed by deployment code.

## Interruption, reconciliation and rollback

Keep `unresolved.json`, fsynced journal phases and private before/exit/after records.
A timeout, SSH disconnect, missing process, or accepted Portainer HTTP response is
not success. Do not retry promotion. Use the existing explicit CLI reconcile or
rollback operation and exact original private recovery record. The hosted SSH
protocol is unchanged and cannot supply an acceptance file, command, environment
or activation verb.

Reconciliation accepts only the exact known full stack/Env candidates and reviewed
image targets from that recorded attempt. It verifies the stop intent and actual
exit proof; an unproved/forced/changed exit stays blocked. A known already-applied
PUT is adopted only after exact runtime/config/registry/progress validation. After
an owned clean stop before PUT, explicit reconcile may complete that same reviewed
image update. Explicit rollback may restart ONLY the exact formerly-active old
container after fresh source/config/exit/registry checks. This cannot start a
worker that was stopped before the recorded attempt. Replacement convergence or
any unknown extra emitter remains a blocker; no lease deletion or broad cleanup.

Binary rollback uses the same ordered TERM/clean-exit/CAS/recreation/progress path,
and only an explicitly compatible old external/core source. It preserves ALL
approved frontend maps and does not restore old Env wholesale. Actual provider
outcomes, issued deliveries and durable attempts cannot be undone by binary
rollback; ambiguous outcomes remain ambiguous. The canonical AI worker is never
stopped/recreated/reanchored by this path.

## Schema boundary and integration checks

Ordinary promotion executes no DDL and retains the current explicit schema gate.
Future `0061_native_login` needs its separate reviewed actual image/head, backup,
postcheck and binary/API/config rollout/rollback barrier; do not add a schema
allowlist or bypass the broker's conservative native-source fence. Native attempts
and referenced expired/revoked sessions are intentionally retained by MVP policy;
there is no current session purger and the FK's RESTRICT behavior is not an
existing runtime defect. Any future purger needs coordinated retention design.

The installed root-owned SSH broker must include the new closed helper file list.
Regenerate/check `approved-tool-files.json` against the exact integrated main tree,
including its actual backend config/lock inputs. Preserve the existing PR/main
hosted quality gate and add the overlay path to its path filters. Run its inherited
Ruff/format/mypy across every implementation and test, offline regressions and
verified actionlint. Synthetic wire tests are not live Portainer/profile/worker,
systemd/SSH, database/provider or rollback acceptance. Actual execution and secrets
remain coordinator-owned; never install a repo-level selfhosted runner here.
