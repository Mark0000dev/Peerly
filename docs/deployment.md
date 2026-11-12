# Build, deployment and recovery

Use the checked-in Docker/Compose/workflow templates and actual immutable image
manifests. This guide contains no production credentials, live receipts, private
host paths or assumed readiness. Internal-team staging and external release are
separate decisions; neither a build nor a screenshot proves deployment.

## Services and boundaries

The static frontend and `/api/v1` share an HTTPS origin behind the existing TLS
proxy. API and email/media/request-expiry/change/external-delivery workers are
separate processes from the backend image. An explicit migration job and
reference-data CLI run administratively, never at API startup. Managed PostgreSQL
and private S3-compatible storage are external dependencies.

AI is a separately pinned nonroot isolated image with dedicated credential/cache
and per-job storage, restricted gateway/network, cgroup/namespace/resource limits
and actual proof/receipt/renewal lifecycle. Do not repurpose a developer home,
mount Docker socket or relax the whole host to make a child pass. See [AI](ai.md).

Core API, AI admission, singleton worker/heartbeat and other worker connection
budgets are explicit; adding replicas multiplies them. SSE clients do not each
hold a DB connection. Inference/storage/provider calls do not retain transactions.
Keep private endpoints, collectors, databases, admin interfaces and metrics off
public ingress. Configure only exact origins/proxy identities and provider
supported database/storage transport; preserve other projects on shared hosts.

## Configuration and first boot

Secrets are runtime inputs outside Git/build contexts/frontend configuration.
Templates contain placeholders only. Validate the actual settings and Compose
combination without printing secret values. Never expose credentials in shell
arguments, exception output, image layers or CI artifacts. API-only asset maps
must actually be injected into the API, not every worker.

1. Inventory and validate actual DNS/TLS, origin/callback, SMTP sender, DB role,
   private media/CORS, monitoring/archive and capacity. Preserve environment keys.
2. Build/check through repository pipelines and pin published digests/source
   revisions. Use controlled integration services; no secret/provider calls in CI.
3. Back up target data, confirm current database/head and privileges, then execute
   one reviewed migration with explicit bounded administrative time/lock limits.
   No create_all, force stamp, automatic downgrade or blind retry on uncertainty.
4. Validate and explicitly publish actual versioned policies/catalogue inputs:

   ```bash
   uv run python -m studymate.bootstrap_data_cli schema
   uv run python -m studymate.bootstrap_data_cli validate OWNER_INPUT.json
   uv run python -m studymate.bootstrap_data_cli apply OWNER_INPUT.json
   ```

   Schema/validate are offline. Apply uses the supplied DATABASE_URL and immutable
   owner-authored versions. No automatic user/operator/registration seed. Never
   rewrite an already published policy; publish a new version.

5. Start core roles only after schema/config compatibility checks. Preserve
   proxy SSE streaming, cache policy, actual frontend release-map/source binding,
   storage privacy and structured producer release. Independently prove workers,
   not just API liveness.
6. Activate external delivery only after actual destinations/recipient permissions
   are accepted: startup may create facts/send notifications. No historical replay
   without explicit source IDs or guessed technical-alert sink.

The root compose file is local development/test PostgreSQL, not a production
stack. Review environment-specific staging/observability/egress overlays together;
keep archive and AI telemetry networks/configuration when updating a collector.
Do not apply a partial historical overlay that silently removes newer controls.

## Promotion and rollback

Quiesce/drain deliberately and preserve immutable intents, queued work, leases and
uncertain outcomes. Check the actual image/PID/schema/service health after a
Portainer response; an accepted asynchronous update is not running-state proof.
Verify representative authenticated/unauthenticated flows and real providers.

Schema60 supports retained human decisions and triage source guards. Old binaries
may ignore newer facts, and guarded downgrades may correctly refuse retained
history. Prefer a forward fix; never purge/stamp or restore over new user data.
Account recreation requires retained active/retired claims; old global lookup is
not a safe rollback. Backups require actual restore testing.

Worker image replacement needs physically confirmed sole native/cache ownership,
new namespace-bound proof and root receipt, canonical retirement and updated
renewal binding. Same binary/policy does not transfer an old CID receipt. Never
clear a circuit/guard/lease by hand or treat expiry as physical stop.

## Release acceptance

Require repository quality and immutable publication, protected configuration,
provider/auth/media checks, observability/archive/alert/restore proof, exact
frontend asset mapping and meaningful browser/PG behavior comparisons. Native
signing/build/store validation remains separate. The owner's full design-v2
all-screen/state/mobile/animated-mascot/Taiga reconciliation is mandatory before
project completion; no CSS hacks or silently simplified replacement layouts.
