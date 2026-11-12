# Internal team staging

Owner update, 10 November 2026: the unresolved ResizeObserver diagnostic does not block preparation or deployment of this internal diagnostic staging. Keep the error visible in evidence and assess its functional/visual impact in the production build. Do not claim full acceptance or invite external users on this exception. Other provider, isolation and representative smoke requirements below still apply.

This stack is for the owner's development team and hackathon prototype. External student admission requires the complete monitoring and release acceptance described in the planning documents. Production uses separate credentials, database and media storage.

## Prepared files

- `compose.yml`: one API, static frontend, email/media/request-expiry/change-publication workers and an explicit one-shot migration service. No database container or published host ports; use the existing managed staging database and Traefik ingress network.
- `stack.env.example`: configuration names and synthetic placeholders. Store the filled environment outside the repository; do not put it in a Docker build context or command-line URL.
- `bootstrap/`: explicit versioned data inputs and provenance. Catalogue publication does not implicitly create accounts or registration receipts. Author/publish actual Terms and Privacy before signup.
- Repository-root `frontend/Dockerfile`: pinned Node build, lockfile install with the approved patch, production static build and an unprivileged Nginx runtime. There is no live SSR server. The public root serves the prerendered `index.html`; private/legal routes fall back to `index.csr.html`.

The backend and frontend images must be selected by verified manifest digest. The shared worker image must contain the same migration/runtime revision selected for the stack. The first head49 image does not include the later first-boot CLI or AI-worker work. Update the release record when those supplements are integrated; do not silently deploy a changing worktree.

## Deployment sequence

1. Finish the student candidate, then batch the agreed static/unit/browser/real-PostgreSQL checks and record any internal diagnostic restrictions. Build/publish exact checked revisions through CI. The prepared frontend Dockerfile and stack are code-only until this acceptance batch.
2. Inspect the existing host's free RAM/disk and Traefik entrypoint, resolver, ingress network and actual trusted proxy IPs. The per-container limits are initial bounds, not a claim that the stack and unrelated existing applications fit the shared two-CPU/4-GB server. Do not use `*` for trusted proxy headers. Revalidate trusted proxy IPs after a proxy replacement.
3. Prepare a private filled environment. Use the supplied staging database and percent-encode DSN credentials. The owner explicitly selected `ssl=disable` for the shared PostgreSQL instance; do not change the instance-wide setting or access `default_db`/production. Distinct random32-byte envelope/browser/code keys are deployment secrets, not sample constants.
4. Validate configuration without printing expanded secrets, for example `docker compose --env-file /secure/peerly-staging.env -f deployment/staging/compose.yml config --quiet`. Use the corresponding environment definitions when deploying through Portainer. Registry authentication stays outside Compose/source.
5. Run the explicit migration service with the selected migration URL, then the supported bootstrap CLI from that same verified image with read-only mounted, schema-validated inputs. Inspect current versions and replay behavior. The migration profile is not part of normal `up` and migration is not an API startup side effect. Verify staging is initially empty before first migration; never downgrade retained business data to reset a test.
6. Start API/frontend/workers. Confirm container health and actual `/api/ready`; worker HTTP healthchecks are deliberately disabled, so verify worker logs, durable state transitions and runtime signals instead. One API process and one sequential media processor are the initial resource assumptions. Do not start duplicate AI executors.
7. Check same-origin HTTPS/secure cookies, genuine Google callback, the approved user's institutional email code, actual registration documents, learner/helper activation, discovery, requests, text/image/recovery/report, feedback and self-deletion. Confirm native browser multipart goes directly to private S3 without application cookies/CSRF headers. The provider's small synthetic upload proof is not this full end-to-end acceptance.
8. Verify SSE through Traefik, reconnection and session revocation. Set up useful logs/metrics and error visibility for team diagnostics; finish collectors, product analytics, traces/archive, dashboards and alerts before external users. Bounded local Docker log rotation is not the promised permanent archive. No UI/runtime diagnostics may be silently filtered to claim acceptance.
9. Add the AI-worker deployment supplement only after the actual credential/tool boundary and resource fit are proven, then perform owner device authorisation in its dedicated runtime and synthetic text/image acceptance. Generic Codex flags, a successful login or the queue tests alone do not establish real AI readiness.
10. Only after the complete internal deployment and representative student smoke pass, parent sends the authorised Telegram announcement with the HTTPS link and truthful remaining restrictions. No credentials, login/device codes or private user data in the group.

## Recovery and updates

Record the current and previous image digests, schema head, policy/catalogue versions and environment key identifiers without values. For an application-only rollback, select the previous compatible digest; an image rollback does not reverse a schema change. Retention guards deliberately prevent destructive downgrades. Restore/backup drills and production release rollback remain required separately.

Pause email/media consumers before changing their credentials or migrating incompatible queue state. Keep the exact environment/key versions needed for outstanding encrypted work. Temporary provider probes may delete only their uniquely owned synthetic objects, never retained application objects. Do not reset shared test databases or unrelated host services as part of staging deployment.

Known pending implementation and defects belong in the current student readiness ledger. This document is a runbook, not evidence that the prepared stack has already been deployed or passed its acceptance batch.
