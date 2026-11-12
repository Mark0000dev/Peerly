# Staging canonical analytics backfill

`canonical_backfill.py` captures retained canonical event references for Umami
using the existing bounded `SeedUmamiBackfill` use case. It neither delivers events
nor starts the external-delivery worker. Historical support messages are never
sent to Telegram by this operation.

Only an authorized staging administrator may execute it. Use the locked backend
Python environment and an explicitly configured private `DATABASE_URL`. Both the
configured and actual database must be `peerly_staging`, schema `public`, at the
reviewed migration `0060_report_triage`. There is no production/test override.
Database-role permissions and the actual stopped worker are separate operator
checks; the helper does not grant privileges or stop running processes.

## Plan and apply

From the repository root, prepare a private persistent intent directory and plan:

```sh
umask 077
mkdir -m 700 /path/to/backfill-intents
backend/.venv/bin/python -m deployment.backend.canonical_backfill plan \
  --operation-id REPLACE_EXPLICIT_UUID --performed-by REPLACE_ADMIN_REFERENCE \
  --cutoff REPLACE_APPROVED_TIMEZONE_AWARE_CUTOFF \
  --journal-dir /path/to/backfill-intents > /path/to/approved-plan.json
```

Planning uses a read-only transaction. It selects at most 100 missing canonical
references under the explicit past cutoff, sorted by UUID. The plan contains only
IDs, event kinds and original timestamps, not private business content or actors.
It binds the operation UUID, administrative label, database/schema/head, cutoff,
server planning time, helper source hash and manifest fingerprint. A `more` marker
reports whether another bounded batch remains; it does not start one.

Review that exact plan/count/fingerprint before applying:

```sh
backend/.venv/bin/python -m deployment.backend.canonical_backfill apply \
  --plan /path/to/approved-plan.json --journal-dir /path/to/backfill-intents \
  > /path/to/capture-receipt.json
```

Input plans must be regular root/self-owned files, without group/world permissions
or a symlink leaf, at most 64KiB. The journal must be root/self-owned mode 0700,
without a symlink leaf. It retains mode-0600 full plans using fsync and atomic
no-overwrite links. Preserve the same directory across retries and back it up
privately. An operation cannot be rebound to a different plan in that journal;
separate directories do not establish global database operation uniqueness.

Keep stdout, plans and receipts private: they contain opaque source IDs. Do not
put credentials in argv, ordinary logs or committed files. The operation requires
no provider token. A real source file is needed for its hash; `python -c` is not
an equivalent invocation. A one-shot approved backend-image operations container
may mount the reviewed helper read-only and the private persistent plan/journal
with appropriate UID access and the actual approved DB network. Do not rely on
ephemeral container `/tmp` as the only journal copy.

## Atomicity and resume

Apply validates the exact source IDs/kinds/times under ordered share locks before
seeding in one transaction. Missing/changed sources roll back the whole batch.
The existing seeder inserts only actual canonical FK references in
`backfill_umami` mode, conflict-safe on canonical event ID. Existing LIVE/backfill
capture IDs, modes, times, materialization and delivery history remain unchanged.
Original events, actor ownership and occurrence times are never rewritten.

Success is reported only after commit, with actual retained source/capture
mappings, modes/times and counts inserted in this transaction. Replay can insert
zero and return the same mappings. It does not claim ownership of an earlier
uncertain commit. The database retains canonical FK/mode provenance; the private
plan/journal/receipt retains administrative intent. No fake canonical/audit events,
OTP consumption, actor rebinding or delivery success is generated.

For lost output, recover the original journal plan. For unknown commit, reconcile
or repeat the **same approved plan**; do not widen the cutoff or select new IDs
blindly. A recovered plan is not a fresh database scan. After a batch is accepted,
a new explicitly reviewed operation with the same approved cutoff can plan the
remaining missing rows. There is no automatic scan/apply/retry loop. An empty
plan proves only that no references were missing under that cutoff at observation.

One connection is bounded by 2s pool wait, 5s connect/statement, 1s lock and 30s
transaction budgets. Timeouts can be ambiguous; they never justify deleting
history, clearing attempts or editing fingerprints. Preserve the original helper
bytes for journal replay; later schema/helper changes require explicit review.

## Separate delivery acceptance

Capture does not prove materialization or actual Umami storage. Worker activation
still requires approved exact target revisions/fingerprints, real credentials,
backlog review, monitoring and bounded provider acceptance. The application routes
these historical canonical captures only to Umami; no support-case selection,
queue unblock, materialization or provider call occurs in this helper. Retained
manual membership confirmations keep their original evidence and are not relabeled
as OTP success. Deleted-account analytics remain attached to their original actor.

Unit and real PostgreSQL tests live under the backend external-delivery test
directories and use ordinary backend strict gates. Persistence acceptance uses
actual migrated isolated PostgreSQL fixtures; no SQLite, mocked SQL, dummy product
schema or live provider is substituted.
