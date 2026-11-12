# Staging external-delivery target preparation

`external_delivery_activation.py` provides administrative `plan`, `register` and
`check` commands for the existing Umami and Telegram support sinks. It does not
start a worker, send a request, materialize sources, unblock/replay deliveries,
change routing or provision credentials. Registration does not prove provider
acceptance or authorize external users.

Use the locked backend environment and an explicitly configured private
`DATABASE_URL`. The configuration and actual connection must identify
`peerly_staging`, schema `public`, reviewed migration `0060_report_triage`.
Do not use a production/migration role or put credentials in argv. Keep the worker
physically stopped during preparation; this command cannot establish process state.

The module commands below run from a source checkout. A backend production image
does not automatically contain the repository's `deployment` namespace. For an
approved one-shot operations container, mount the reviewed deployment helper
package read-only, including its `canonical_backfill.py` database-guard dependency,
and make that source root importable. Do not copy credentials into the source or
change the archived version-pinned helper used for an earlier operation's replay.

## Public target manifest

Create a private mode-0600 JSON file with exactly:

```json
{
  "schema_version": 1,
  "database": "peerly_staging",
  "database_schema": "public",
  "migration_revision": "0060_report_triage",
  "backend_image": "ghcr.io/mark0000dev/peerly-backend@sha256:REPLACE_VERIFIED_DIGEST",
  "support_notice_not_before": "REPLACE_APPROVED_TIMEZONE_AWARE_CUTOFF",
  "umami": {
    "revision": 1,
    "origin": "https://analytics.example.test",
    "website_id": "REPLACE_ACTUAL_STAGING_WEBSITE_UUID"
  },
  "telegram_support": {
    "revision": 1,
    "chat_id": -1001234567890,
    "operator_origin": "https://peerly-staging.example.test",
    "topic_id": null
  }
}
```

All example values require review/replacement. Revisions must be explicitly
approved against the actual registry; an example `1` does not establish that a
revision is available. Use HTTPS origins without path/query/fragment/userinfo.
Select the intended actual staging website, operator origin, product-support
recipient and optional positive topic ID. A technical-alert bot/group is not
implied product-support authorization. Do not mix production/staging analytics.

No token, database URL or login belongs in this file. The helper reuses the actual
target fingerprint serializer: Umami origin/website and support chat/topic/operator
origin, schema and sink. Credentials are excluded. A credential-only rotation
does not imply a new target; changing a registered revision's target is rejected.
The backend image field identifies the reviewed candidate, not a verified running
container. Provider/recipient identity and actual deployment still need acceptance.

The notice cutoff is an explicit review boundary, not a runtime send filter. Old
pending or unmaterialized live support sources require review; do not move the
cutoff just to hide them or seed old support cases as new notices.

## Explicit Umami-only partial milestone

When product-support destination approval is still pending, use the separate
closed schema2 manifest. It contains no Telegram target, token, dummy recipient
or support cutoff:

```json
{
  "schema_version": 2,
  "mode": "umami_only",
  "database": "peerly_staging",
  "database_schema": "public",
  "migration_revision": "0060_report_triage",
  "backend_image": "ghcr.io/mark0000dev/peerly-backend@sha256:REPLACE_VERIFIED_DIGEST",
  "umami": {
    "revision": 1,
    "origin": "https://analytics.example.test",
    "website_id": "REPLACE_ACTUAL_STAGING_WEBSITE_UUID"
  }
}
```

Use the same plan/register/check commands and fresh, privately reviewed plan.
The mode/schema, image, exact Umami target, helper version and complete snapshot
are bound into approval hashes. Registration passes exactly one entry to the
same existing guarded transaction writer. The legacy schema1 both-target manifest
and its review requirements remain supported; old plans require fresh planning
when this helper version changes.

Partial mode validates global source-capture/rotation invariants and the selected
Umami schedule, work and revision. It reports the omitted support schedule and
actual deferred support inventory (unmaterialized sources, pending unbound/bound
notices, unsettled deliveries, unresolved attempts and registered historical
targets). No support cutoff is invented: old_support_notices is null because no
historical support send boundary is approved. Omitting support configuration does
not clear, rebind, discard, claim or acknowledge those records. A blocked omitted
support sink does not imply that Umami is blocked. Existing support registrations,
if any, remain historical metadata and are not runtime configuration.

The existing worker supports Umami-only settings: configure actual Umami fields
and leave TELEGRAM_SUPPORT entirely absent. Its actual destination registry returns
None for support; the existing worker skips that sink before claiming. Live support
captures can still materialize into durable pending, destination-unbound notices;
no attempt or destination binding is created by an unconfigured worker. Umami
can drain its own eligible work without dropping or starving retained support.
No runtime/queue policy or delivery-source routing is changed by this helper.

Later full registration uses a fresh schema1 plan with the actual approved product
support destination and explicit support-cutoff/backlog review. Historical deferred
notices continue to trigger the existing review guard. Do not move cutoffs, clear
attempts or retime sources to obtain a pass. Existing exact Umami registration
remains an immutable idempotent match. Registering Telegram metadata alone does not
configure or activate a running Umami-only worker. Elapsed time does not approve
the missing destination or authorize historical Telegram delivery.

A partial metadata check/provider acceptance is only a milestone. Full BE-DELIVERY
acceptance still requires BOTH real sinks, proper recipient/links, monitoring,
bounded failure/replay behavior and provider receipts. No support recipient is
inferred from the technical PeerlyDev alert destination.

## Commands

From the repository root, with the authorized DB connection already configured:

```sh
umask 077
backend/.venv/bin/python -m deployment.backend.external_delivery_activation plan \
  --input /path/to/targets.json > /path/to/target-plan.json
```

Plan uses a read-only repeatable-read transaction. It checks actual database/head,
all three source-capture triggers, both schedules, blocked/cooldown state, unresolved
or other-revision work, old support notices and existing target fingerprints.
Missing registrations are allowed for planning; mismatches are not. The output
binds exact targets, helper version, the complete metadata snapshot and hashes.
Review it privately before registration:

```sh
backend/.venv/bin/python -m deployment.backend.external_delivery_activation register \
  --input /path/to/target-plan.json > /path/to/registration-receipt.json
```

Register requires the unchanged approved plan and a snapshot at most five minutes
old. Actual database/head checks, current metadata revalidation and the existing
registry writer execute within the same transaction. Only new or matching exact
target rows are accepted. A target that disappeared after approval is rejected.
The original immutable fingerprint check and sorted write order remain; a later
conflict rolls back both target writes. Matching replay preserves registration
times. No alternate SQL writer, DDL, target update or new provenance registry exists.

Then obtain fresh read-only metadata:

```sh
backend/.venv/bin/python -m deployment.backend.external_delivery_activation check \
  --input /path/to/targets.json > /path/to/readiness-metadata.json
```

Check additionally requires every exact registration selected by the manifest. `metadata_checks_passed`
means only the checked metadata matches. Output explicitly states that activation,
credentials, provider acceptance and worker start are not verified/authorized.
Current aggregate pending-source counts are reported, not drained or discarded.

## Failure, concurrency and privacy

All input is bounded private regular JSON (64KiB maximum), root/self-owned, no
group/world permissions or symlink leaf. Unknown fields and invalid input produce
finite errors without their values. Keep plans/receipts private; no raw provider
response, student content or credentials are returned. HTTP transport is never
constructed or called by this helper.

One connection uses 2s pool wait, 5s connect/statement, 1s lock and 30s transaction
budgets. Read-only commands and registration use repeatable-read snapshots.
This stabilizes their own observations; it does not prove no other process is
running, freeze all database metadata, or prevent future captures. Exact registry
key uniqueness/fingerprints protect same-revision writes. Maintain exclusive
stopped-worker administrative coordination and obtain fresh checks before start.

On stale plans, re-plan read-only against the same approved targets and review the
fresh state; never alter timestamps to pass freshness. On unknown commit, inspect
the actual registry for those exact revisions/fingerprints before retry. Never
change target revisions, clear attempts/cooldowns, delete retained work or overwrite
fingerprints as recovery. There is no automatic retry, provider probe or start.

## Separate worker activation

The normal worker command remains `python -m studymate.external_delivery_worker`.
For both-sink activation it needs the actual `UMAMI__REVISION`, `UMAMI__ORIGIN`, `UMAMI__WEBSITE_ID`, and
`TELEGRAM_SUPPORT__REVISION`, `__CHAT_ID`, `__OPERATOR_ORIGIN`, `__TOKEN`, with optional
`__TOPIC_ID`. The token is supplied privately to the worker, never this manifest.
Configure actual observability origin/environment/release and the reviewed bounded
SDK queue; verify queue/freshness/blocked metrics through the existing collector.

Only after configuration, backlog, source/image, credentials, recipient approval,
monitoring and explicit operational review may the worker be started separately.
Acceptance must prove actual Umami storage and Telegram metadata-only message IDs/
operator links, retain server/client trust and manual-versus-OTP evidence, and
preserve core operations during provider failure. Technical alerts remain with
Prometheus/Alertmanager; no app technical-alert producer is added. Ambiguous retries
can duplicate provider effects; no exactly-once delivery claim is made.
