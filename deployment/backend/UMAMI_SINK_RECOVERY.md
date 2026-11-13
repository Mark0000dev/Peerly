# Guarded Umami sink recovery

`python -m deployment.backend.umami_sink_recovery` is an owner-run staging maintenance command, not a public API. It has no provider transport. It only clears the Umami schedule's `destination_unavailable` block after exact approval. It never changes destination registration, dead delivery state, attempt counts, leases, retry timestamps, cooldowns, Telegram state or existing provider evidence. The ordinary worker may subsequently process pending deliveries; the dead delivery remains dead.

Run against the real pinned backend image with the deployed Umami environment (`UMAMI__REVISION`, `UMAMI__ORIGIN`, `UMAMI__WEBSITE_ID`, `UMAMI__HOSTNAME`) and `DATABASE_URL` already provided by the operator. Do not place tokens or database credentials in command arguments or targets. `--runtime-image` is an operator-supplied immutable image pin checked against the approved target; this helper does not inspect the container engine or independently attest deployment.

Prepare a private mode-0600 target JSON with these exact fields:

- `schema_version`: 1; fresh `operation_id` UUID; bounded `performed_by` operation label.
- `database`: `peerly_staging`; `database_schema`: `public`; `migration_revision`: `0060_report_triage`.
- `backend_image`: exact `ghcr.io/mark0000dev/peerly-backend@sha256:<64 lowercase hex>`.
- `revision`, collector `origin`, `website_id`, application `hostname`, existing registry `fingerprint` (64 lowercase hex), and `failed_delivery_id`.

The fingerprint must remain the existing origin+website target fingerprint. Hostname is explicit application metadata, never a target rebind or browser/session claim. The failed delivery must be Umami, dead, bound to that revision, with its final permanent `destination_unavailable` HTTP-200 attempt retained and no late acknowledgement. Any leased or unresolved Umami attempt rejects recovery. The highest registered Umami revision must match the configured target.

With a private mode-0700 journal directory and `umask 077`:

```sh
python -m deployment.backend.umami_sink_recovery plan --input target.json --runtime-image "$PINNED_BACKEND_IMAGE" > approved-plan.json
python -m deployment.backend.umami_sink_recovery apply --input approved-plan.json --runtime-image "$PINNED_BACKEND_IMAGE" --journal recovery-journal
```

Review the plan before apply. It binds all input metadata, the exact dead-attempt/schedule/registry snapshot and the three implementation files' combined source hash. Approval expires after five minutes. Apply uses a bounded serializable PostgreSQL transaction and schedule-first locks, rechecks the exact state and performs a conditional update of `blocked_reason` alone. Changed state, stale approval, wrong runtime metadata or mismatched source rejects; serialization failures never retry automatically.

The private journal fsyncs an immutable prewrite intent before opening the write transaction and an immutable receipt only after commit returns. It is an operational record, **not a transactional canonical event or authenticated operator audit**. `performed_by` is operator supplied, not application identity. No shared audit enum/schema is fabricated. A lost commit response or receipt failure can leave an unknown outcome. Never blindly retry apply:

```sh
python -m deployment.backend.umami_sink_recovery inspect --input approved-plan.json --runtime-image "$PINNED_BACKEND_IMAGE"
```

Inspection is read-only, reports observed block state, and explicitly leaves commit attribution unknown: without a durable database operation ID it cannot establish who cleared the block. It still requires the same source/config/image/registry/dead evidence; subsequent state changes may require direct owner-led reconciliation. An already cleared sink does not make a repeated apply successful.

Recovery is not provider acceptance. The owner separately controls worker activation and the next bounded provider trial. No historical Telegram send, dead replay, count reset or synthetic Umami success occurs here.
