# Deployment and delivery design

Status: deployment strategy only. No server, Portainer stack, registry, DNS record, alert receiver or production credential has been configured. Existing GitHub workflows run quality checks; release/deployment jobs and production manifests are future implementation work.

Known infrastructure: owner-managed VPS with Portainer, separate managed PostgreSQL cluster, an existing monitoring server with Prometheus/Alertmanager/Grafana/Umami/Loki, and the `aleksei-orlov.dev` domain. Pilot users are at APU in Malaysia. Capacity, versions, regions and connectivity are unknown.

## 1. Runtime topology

| Placement                 | Components                                                                                                              |
| ------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| Application VPS           | Existing TLS reverse proxy; static frontend container; API container; async worker container; local telemetry collector |
| Managed cluster           | Dedicated StudyMate production database/roles, separate staging database/roles; no shared app credentials               |
| Private storage           | Owner-provided external S3-compatible storage; credentials and endpoint/bucket details pending                          |
| Monitoring server         | Existing stack plus Tempo/trace storage; Grafana's product PostgreSQL views and operational datasource links            |
| GitHub Actions / registry | Isolated checks, test PostgreSQL, immutable image builds, release manifest, staged deployment and rollback record       |

API, worker and migration job use the same backend image with different entrypoints. The frontend is a static Angular build with public runtime configuration, so the exact image can be promoted across environments without rebuilding. No secrets are build arguments or frontend config.

Initially run one API process, one delivery worker and one separately resource-limited AI worker/supervisor. Each API process has a bounded SQL pool and, if supported, one dedicated LISTEN connection. Size pools only after learning the managed connection quota. Budget API + worker + listener + migration + monitoring connections plus reserve; adding replicas multiplies pools. SSE clients do not each consume a permanent PostgreSQL connection.

Use the existing reverse proxy when possible rather than adding another ingress. If none exists, choose one proxy with automatic TLS and configure it in the deployment stack. Public traffic uses only 80/443; API/worker/collector/metrics/Portainer stay on private networks. Database access uses verified TLS and an explicit provider/VPS network arrangement.

Production must not use the root `compose.yaml`: it is local development/test PostgreSQL only. Production Compose manifests, Dockerfiles and collector/proxy configuration will be added under a deployment directory after inventory, without embedding secrets or production addresses in examples.

## 2. Domain, origins and transport

Approved product name: **Peerly**. Owner-selected website: `peerly.aleksei-orlov.dev`. Keep API on that origin under `/api/v1`; the owner suggested `peerly-api.aleksei-orlov.dev` tentatively, but a separate browser API origin is not required by the current design. No DNS/TLS changes have been made. Proposed separate staging hostname: `peerly-staging.aleksei-orlov.dev`, still to confirm. Do not repurpose the production hostname as staging without an explicit environment plan. Brand/hostnames do not require renaming Python packages or previously applied migrations.

Google web callback for the selected site: `https://peerly.aleksei-orlov.dev/api/v1/auth/google/callback`; proposed staging callback: `https://peerly-staging.aleksei-orlov.dev/api/v1/auth/google/callback`. Register each only on the matching OAuth client/environment. Native package/bundle IDs remain to approve before signing.

Serve the web frontend and `/api/v1` on the same HTTPS origin. Proxy `/api/health` and `/api/ready` for operational probes according to the exposure policy; keep detailed internals/metrics private. Route `/telemetry` only through the bounded authenticated/origin-checked ingestion gateway, never directly expose a full collector.

For SSE: disable proxy response buffering/caching/compression behavior that delays events, preserve event-stream headers, support heartbeats and a suitable idle timeout. Test HTTP/2 where available, reconnects through the actual proxy and deploy-time draining. Stop/drain streams during shutdown; clients resume/refetch rather than losing acknowledged changes.

Web assets use content hashes and immutable caching; index/runtime config use revalidation so clients do not remain on a broken obsolete bootstrap. A service worker is not part of the initial deployment. Verify CORS/native origins only when native authentication/media/streaming are implemented; do not use wildcard credentialed origins.

## 3. Provider inventory needed before implementation

- VPS: CPU/RAM/disk, architecture, Docker/Portainer edition/version, existing networks/proxy, backup facilities and deployment access method.
- Managed PostgreSQL: region/version, dedicated database support, TLS CA, connection quota, pooler mode/direct listener endpoint, backup/PITR and restore capability, migration permissions.
- Monitoring server: regions, versions, endpoint/auth methods, datasource UIDs, existing collector, available trace/object storage, retention/capacity and private connectivity from the VPS.
- Media/email: object-store region/quota/backups, email provider and sender domain. The confirmed student email domain is exactly `mail.apu.edu.my`.
- GitHub: registry/repository visibility, branch workflow, runner connectivity and environment secrets; no secrets shared through source or PR logs.
- Operations: Telegram bot and destination IDs, support owner, incident owner, secondary alert channel, data-controller identity and hosting/provider locations for the privacy notice.

Use a dedicated application database, not cluster-superuser credentials. Separate runtime, migration and dashboard read-only credentials. Grafana's read-only SQL views prevent accidental writes/workload damage; all owner/developer viewers still see all provisioned dashboards. Exhaustive application content access belongs to the privileged operator interface.

## 4. GitHub Actions pipeline

PRs run without production secrets, using isolated services and synthetic data. Preserve the existing Ruff/mypy/import contracts, PostgreSQL unit/integration coverage, strict frontend static checks, browser unit coverage, production compilation and screenshot comparisons.

Extend checks as product behavior exists:

1. Verify lockfiles, reproducible OpenAPI/client generation and migration upgrades on an empty disposable PostgreSQL instance.
2. Run request/message races, idempotency and authorization tests against actual PostgreSQL.
3. Run two-account full-stack tests through REST + SSE, in addition to boundary-controlled screenshot tests. Test lost-response retries and hide/block effects.
4. Validate production Compose/proxy/collector configuration, Prometheus rules with promtool and dashboard schema/provisioning.
5. Scan dependencies and image artifacts, produce SBOM/build provenance, and fail according to a documented severity/exploitability policy; do not silently ignore the existing upstream advisory findings.

Trusted release workflow:

```text
required checks → build images once → push immutable images
→ record frontend/backend digests + commit + migration head
→ deploy the release to staging → readiness + synthetic smoke
→ deploy those same digests to production → health/version smoke
→ record release outcome and telemetry annotation
```

Map the repository's `develop`/`main` workflow to staging/production when the team starts merging. Only trusted branches/workflows receive deployment secrets; PR code must not run on a production-connected runner or receive its credentials. Reference GitHub environments for distinct target secrets and branch restrictions. Production approval policy can follow the owner's chosen workflow; this architecture does not require a new per-deploy approval process. [GitHub environments](https://docs.github.com/en/actions/concepts/workflows-and-actions/deployment-environments).

Serialize deployment per environment using workflow concurrency; do not cancel an in-progress migration/deployment to start a newer one. Publish a release manifest with image digests and compatible migration range. Never deploy floating `latest`, rebuild differently for production, or let a registry push alone choose an unvalidated release.

Use minimal workflow token permissions and pin action revisions when implementing the release workflow. Keep third-party actions and shell quoting reviewable. Upload test diffs/traces/reports and release manifests as artifacts; do not upload credentials, real user screenshots, production backups or chat contents.

## 5. Portainer integration

Use Portainer as the stack deployment authority, not a second independent reconciler beside manual `docker compose up`. Deployment jobs update the selected stack's manifest/image digests through a tested API/automation adapter and poll actual stack/container health before declaring success.

Do not assume a stack webhook exists in Community Edition: current Portainer documentation marks stack webhooks Business Edition only, and a webhook acknowledgement can arrive before deployment completes. A webhook may be an optional adapter after verifying edition/version, never a correctness dependency. [Portainer webhooks](https://docs.portainer.io/user/docker/stacks/webhooks).

Preferred access: GitHub-hosted checks build artifacts; a trusted deploy job reaches a restricted deployment entrypoint on the VPS through SSH/private connectivity. That entrypoint runs the approved migration image and calls the local/private Portainer API. Confirm host identity and restrict the deployment account/credential to the app's actual environment as the installed edition permits. A production-connected self-hosted runner is an alternative only if it never executes untrusted PR jobs.

Do not expose Portainer's administration API to the public internet just to support Actions, disable SSH host verification, or grant arbitrary PR scripts the Docker socket. Portainer API tokens inherit actual account permissions; verify them rather than assuming per-stack token scopes exist.

The API/worker containers read runtime secrets supplied outside Git. In standalone Docker/Portainer, environment variables are configuration, not a magic encrypted secret store. Prefer protected mounted secret files or an existing secret manager; use actual Swarm secrets only if the VPS is running Swarm. Never put production `.env` files, database URLs with passwords, webhook URLs or bot tokens in the repo/release artifact/build context.

## 6. Migrations, health and rollback

A migration job uses the exact backend image selected for the release and the migration credential. Run it once from the VPS/private database network under a deployment/migration lock, not independently in each API replica's startup. The API app does not run `create_all`.

Use expand/contract schema changes so the currently running and new image both work during rollout. Run migration → stack update → readiness check → version check → read-only production smoke. Staging additionally exercises synthetic email/request/chat flows without sending notifications to real users.

`/api/health` reports process liveness; `/api/ready` checks actual database reachability. Add separate observable worker heartbeat/queue health. Public availability needs an external synthetic probe as well as internal metrics; a dead process cannot report its own failure.

Retain the previous known-good image manifest. If the new app fails and the migration is backward-compatible, restore the previous image digests and verify health. Do not automatically run destructive downgrade migrations as an application rollback. Irreversible data recovery follows the backup/PITR procedure and an explicit recovery decision.

A single VPS with one API container can have a short restart interruption; the initial design does not promise zero downtime or high availability. If that becomes a requirement, add verified blue/green routing and spare capacity, rather than claiming Docker healthchecks alone provide it. SSE reconnect/idempotency preserve correctness through ordinary restarts.

## 7. Recovery and operational readiness

Initial targets for discussion: 99.5% monthly web/API availability; normal REST p95 under 500ms at the measured pilot load; change notifications normally visible within 2 seconds; recovery point at most 15 minutes if the provider supports it, and service recovery within 2 hours. These are proposed targets, not existing guarantees or contractual SLAs. Validate network latency from Malaysia before promising response times.

Inventory and test managed PostgreSQL backups/PITR. Back up media and the minimum deployment/observability configuration off the application VPS; keep credentials separately. Verify restore into a disposable environment, including media/DB references, not just that a backup job exits successfully. Document recovery steps, owners and last drill outcome.

Alert on missed worker heartbeats, aged delivery tasks, broken probes, database pressure and stale backup verification. Telegram support notifications and technical alerts use separate paths; configure a secondary critical channel. Dashboards and alerts are provisioned/reviewed with the release, not manually invented on the server and lost on recreation.

Before first recruitment, prove a staging path from deployment → two-account interaction → canonical event → trace/log → operator's full record inspection → support bot notification. Verify that user content does not enter telemetry and that no product account can reach Grafana/operator endpoints. Confirm data locations and the actual Terms/Privacy and registration notice described in [observability](observability.md).

## MVP Codex executor placement

Add a dedicated isolated executor runtime, not the developer host session. One active Codex invocation globally; fresh job context/workspace, bounded CPU/memory/PIDs/disk/output, dedicated auth secret storage and no application credentials or host Docker socket inside the agent. The trusted supervisor alone accesses the narrow job/storage adapters. Pin and smoke-test the deployed CLI, text/image structured output, authentication renewal and container process-tree shutdown before real jobs. Account access is supplied separately by the owner; do not copy local auth or read it during planning. A worker restart must terminate old children before replacement. See [AI operations and recovery](ai.md). API readiness and email delivery do not depend on executor readiness.

## Owner preparation

The consolidated owner-facing [setup checklist](planning/owner-setup-checklist.md) lists app registrations, exact web callback, promised infrastructure access, provider inputs and native-only prerequisites. Preparing these inputs does not authorise external changes, message sending or deployment.

## Repository access update

Owner confirms push access and authorises parent-coordinated working-branch commits/pushes as needed, never main. GitHub secret creation capability is expected but unverified. GHCR configuration may proceed when immutable image workflows are ready; no image publication is claimed yet. Portainer secrets are in workspace-root `../secrets`, outside Git and unread for now; credential presence does not authorise deployment.

AI saturation acceptance requires admission pool2 plus a separate singleton worker/heartbeat pool1 (up to3 AI database connections beyond core/delivery/listener/operations), with bounded waits. A shared admission/heartbeat pool failed the synthetic burst and must not be used in deployment composition; see `docs/ai.md`.
