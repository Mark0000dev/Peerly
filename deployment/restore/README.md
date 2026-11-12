# Peerly bounded PostgreSQL and retained-media restore acceptance

This bundle prepares a reviewable command script; generating it performs local file
reads/writes only. Running it is a separate operator action. It does not provision
infrastructure, fetch backups, contact S3, read application credentials or launch
workers. Scope is the existing public PostgreSQL schema and immutable profile/chat
image renditions. This is not a telemetry archive restore or a production recovery
switch-over tool.

## Required external inputs and ownership

The backup owner must supply an authenticated custom-format `pg_dump` archive, its
independently recorded SHA256, and `baseline.json` from the SAME exported PostgreSQL
snapshot. Record source database/cluster identity, exact PostgreSQL/client versions,
backend image and Alembic head, capture interval and backup provenance. Hashes only
prove equality to that supplied material; they do not authenticate its origin.
Do not invent a baseline from the destination, write expected counts manually, or
use a list of object names as proof that bytes were backed up.

For a future approved capture, the backup operator keeps an exporter session open:
`BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY; SELECT pg_export_snapshot();`.
Use that returned snapshot with BOTH `pg_dump --format=custom --snapshot=...` and
`psql --no-psqlrc --set=ON_ERROR_STOP=1 -Atq --set=backup_snapshot=... --file=acceptance.sql`.
End the exporter transaction only after both succeed. Native CLI credentials and
source access belong to the separately authorized backup owner, not this helper.
Capture files under umask 077 with no shell tracing. The SQL temporarily creates a
session-local function and rolls back; it never modifies application rows/schema.

Supply an offline, private, immutable media tree preserving exact object keys.
Back up retained objects without deletion/expiration across the snapshot/copy
window; preserve version IDs and readback hashes if the storage system supports
them. Scope includes `retained/<upload-or-image-uuid>/<attempt-uuid>/original` and
`photo.jpg`, derived from actual ready processing attempts in PostgreSQL. Original
bytes must match source size/digest, and display bytes must match the processing
attempt's display size/digest. Historical ready attempts are included. Do not run
cleanup, public application traffic or workers against the restore.

The infrastructure owner supplies a dedicated disposable PostgreSQL instance on
literal loopback with an explicit nondefault port and matching native binaries at
/usr/bin. An unused port number is not proof that a cluster is isolated. The drill
role must be nonsuperuser with CREATEDB and local trust access to maintenance DB
`postgres`; it must not have production/shared access. No password/service/home
configuration is inherited by generated native commands. This intentionally does
not accept arbitrary DSNs, remote hosts, production credentials or existing target
DB names. Coordinate any Docker/resource-heavy preparation with the coordinating operator first.
The owner must budget cgroup memory/CPU, scratch-disk quota and free space before
execution; SQL deadlines do not cap PostgreSQL memory or archive expansion.
A coordinated isolated PG16.15 smoke has exercised the generated script and SQL
against released migrations through 0060 with synthetic profile/chat data,
four actual local JPEG objects, same-snapshot concurrency and native failure guards.
That smoke is not a genuine backup or complete recovery proof.

## Prepare, inspect and run

Use the existing backend virtualenv's Python; pass absolute owned local paths:

```sh
python -B accept_restore.py plan \
  --directory /private/new-owned-run \
  --source source_database_name --port 55433 --role restore_drill \
  --dump /private/backup.dump --sha256 RECORDED_ARCHIVE_SHA256 \
  --baseline /private/baseline.json --media /private/offline-media
```

The destination directory MUST NOT already exist. Plan creation rechecks the dump
hash and validates the baseline shape. It creates a mode-0700 directory/script.
Review the exact script, artifact hashes, native tool provenance/version and
isolation before executing through `env -i PATH=/usr/bin:/bin /bin/bash /private/new-owned-run/restore.sh`.
No command was executed merely by creating that file.

The script uses a freshly generated `peerly_restore_<uuid>_test`, explicitly rejects
source=target and has no name lookup or reusable target option. `createdb` uses
template0 and fails if the database exists; the script never drops or empties an
existing destination. It checks nonsuperuser CREATEDB authority, sets connection
limit 1, revokes PUBLIC CONNECT, and restores only into its new owned DB. No clean,
create-from-dump, ownership replay, ACL replay or disabled-trigger option is used.
Restore errors fail the single transaction. Native command timeouts are 180s with
5s kill grace, connect timeout 3s; SQL statement/lock deadlines are 30s/2s. Media
verification is bounded to 600s. Run only trusted backup SQL on the isolated cluster:
a PostgreSQL dump is executable input, not an untrusted document.

The EXIT trap calls bounded, non-force `dropdb` only after this script's successful
createdb. Creation timeout/ambiguous success or a killed shell can leave an owned
orphan; record its generated exact name and inspect it manually, never retry with
clean/drop-all. If another session prevents cleanup, the script fails and requires
operator cleanup. All subordinate commands have independent bounds; no daemon or
unbounded retry loop is created. Full wall time is the finite sum of those bounds.
Do not treat a leftover evidence file as success when the script exit status fails.

## What is actually checked

`acceptance.sql` produces a private JSON inventory from a repeatable-read snapshot:
actual Alembic head, every public table's actual row count plus SHA256 of sorted
SHA256 row representations, explicit current/historical photo and message/image
joins, constraint validation and trigger status, and exact ready-attempt object
keys/sizes/digests. Equal counts with changed rows fail. Row representations use
PostgreSQL JSONB with UTC time and fixed float formatting; require identical major
versions/settings for baseline and restored capture. This fingerprint is not a
portable cross-version canonical encoding or a schema/sequence fingerprint.

`verify` requires exact source/destination inventory equality and hashes every
referenced local media file. Missing, truncated, altered, duplicate or symlinked
objects fail. Any nonzero broken relationship, unvalidated constraint or disabled
trigger fails. Empty media cannot establish media acceptance and fails; an empty
installation needs an explicit separate evidence decision, not a vacuous pass.
No object payload, account ID, object key or SQL row content goes into the summary.
Private inventory files still contain object IDs/digests and need restricted storage.
Native error text is retained only in `native.stderr.private`; never publish it.

Hard bounds: custom dump <=2GiB; inventory <=8MiB; <=256 public tables, <=10,000
rows/table, <=20,000 object references, <=10MB/object, <=1GiB referenced media.
Bounds are rejection thresholds, not permission to omit rows. SQL uses one extra
row/object to detect overflow. Larger backups require a separately reviewed drill,
not truncated inventories. Extra unreferenced retained files are not deleted;
expired transport objects and incomplete/retry attempts are outside this media
check and must be recorded separately if pending-work recovery is required.

## Evidence and remaining release acceptance

Success writes `restored.json` and closed `evidence.json` after actually reading
the restored target and offline media. `full_restore_proven` deliberately remains
false: this bounded relational/byte check alone does not prove complete disaster
recovery. Retain script exit/cleanup status, dump/baseline/inventory hashes,
source provenance, actual PG versions, schema/constraint/index/sequence comparison,
large-object/extension inventory, and isolation/resource measurements separately.
Verify actual restored media read through the isolated product adapter and scoped
application flows without providers or outbox/AI/email dispatch. No count or
synthetic fixture substitutes for those steps.

Pending external prerequisites include an approved coherent backup and encryption
key recovery, secure offline artifact transfer/readback, genuine isolated native
PG restore, schema/sequence validation, application authorization/media read
acceptance, pending work disposition, RPO/RTO measurements and final owner signoff.
Never switch production pointers, restore over current user data, or restart
services merely to manufacture evidence. Existing telemetry crypt/archive proof
has a separate format and cannot stand in for PostgreSQL+business-media recovery.
