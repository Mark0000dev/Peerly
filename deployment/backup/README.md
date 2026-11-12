# PostgreSQL and media backups

This job captures a logical PostgreSQL archive and matching retained media,
encrypts them with rclone crypt, and verifies the decrypted remote bytes before
recording a successful generation. A successful job is byte-verification evidence;
application recovery and RPO/RTO require separate restore acceptance.

## Install and configure

Install the `deployment/backup` package and its `deployment/restore` dependencies, including
`capture_backup.py` and `acceptance.sql` under `/usr/local/lib/peerly-backup`. Use the
Python runtime required by those packages, PostgreSQL 16 client tools, and a
root-owned, pinned rclone 1.76.0 binary. The runtime account must not be able to
modify installed code or binaries. Create the dedicated `peerly-backup` account.

Copy `plan.json.example` and `rclone.conf.example` to root-controlled files under
`/etc/peerly-backup`, replacing all placeholders. Keep configuration and credential
files mode 0600. Set the exact installed capture-module and rclone SHA256 pins in
`plan.json`; mismatches reject execution. Keep the state directory exclusive to
this job, mode 0700, with no concurrent backup process.

Supply the capture helper's source-request JSON with the exact database name,
role, OID, migration head, server major and available system identifier. Pin the
connection endpoint separately from the observed server address and port: managed
NAT may make these different. Preserve the source's explicit SSL policy. An
explicitly configured `disable` is supported; `verify-full` additionally needs its
CA credential. There is no automatic TLS downgrade or hostname fallback.

Provide the PostgreSQL password as a dedicated pgpass credential. Use a media
credential limited to reading the required source objects and a backup credential
limited to its separate destination prefix. Avoid developer HOME, libpq service
files and inherited rclone configuration. `run-backup.sh` opens only the systemd
credentials and passes file descriptors to the Python entry point; do not put
credential values in command arguments or logs.

Configure a distinct crypt password and salt for business backups. Native rclone
obscuring is reversible and does not protect a stolen configuration. Store an
independent, access-controlled recovery copy of the password, salt, crypt settings,
namespace and key-generation identifier. Exercise recovery from that independent
copy and record its receipt in `escrow_drill_reference` before scheduled use. Keep
historical keys for every retained generation. Do not reuse telemetry archive keys.

Install `peerly-backup.service.template` as `peerly-backup.service`, retaining its
credential mappings and confinement. Add the optional `pg-ca` mapping only for
`verify-full`. Run `systemd-analyze verify` on the installed unit and reload systemd.
Start one service invocation and inspect its exit status and state receipts before
enabling the example timer. Installation alone does not enable scheduling.

## Capture, space and verification

The source transaction is read-only and retains its exported snapshot until both
native pg_dump and baseline capture complete. The full archive, including
nonpublic schemas, is retained. Media selection follows the captured baseline;
local sizes and SHA256 hashes must match before encryption/upload.

Limits are 2 GiB dump, 1 GiB retained media, 8 MiB baseline and 20,016 verification
files. The maximum payload is 3,239,051,264 bytes; metadata allowance is 134,217,728
bytes. Required run space is 3,373,268,992 bytes, about 3.142 GiB. The example spool
allowance is 3,758,096,384 bytes (3.5 GiB). Existing spool usage plus the run budget
must fit that allowance, and current free space must cover the run budget.
These are admission checks, not a filesystem reservation: concurrent writes,
allocation overhead or inode exhaustion can still cause failure. Investigate disk
pressure rather than increasing limits automatically.

Only one plaintext payload is stored. Each unique encrypted generation receives:

1. An unfiltered recursive listing checked against the exact expected file set and
   each available size. Unknown sizes are counted explicitly.
2. Native `rclone hashsum SHA256 PREFIX --download`, which decrypts and hashes every
   file without creating a plaintext readback tree. Each expected hash must occur
   exactly once; malformed, duplicate, missing, unexpected or mismatching entries
   and any nonzero command exit reject the generation.
3. A second exact listing, followed by upload and streamed verification of
   `COMMITTED.json`. Only then is the local verified catalog updated.

Credentials and unique immutable generation paths must prevent concurrent writers;
listing and hashing cannot prove immutability against a hostile writer. Metadata
output is bounded to 16 MiB and hash lines to 512 bytes. Native stderr is suppressed
and failure messages contain closed codes, not object contents.

Native phases have 600-second deadlines, 5-second connect and 15-second I/O
limits, one checker/transfer, zero read buffer, a 32 MiB buffer budget, a 160 MiB
Go memory target and bounded retries. Process groups receive bounded termination
and kill cleanup. The service limits are 512 MiB memory, half a CPU, 64 tasks and
35 minutes total. Large archives or slow storage can exceed these limits and fail;
verification is never skipped to meet a schedule.

## Failure, recovery and retention

Failed or interrupted runs do not enter the verified catalog. Failed plaintext
runs remain quarantined within the bounded state directory. A late failure can
leave a remote commit whose local status is uncertain; inspect receipts and
independently verify that generation before using it. Never infer a usable backup
from an upload exit alone. Remove only explicitly identified owned leftovers after
investigation. The job removes its successful owned plaintext payload only after
verification/catalog publication.

For recovery, use independently escrowed keys to decrypt the selected committed
generation, verify its manifest and hashes, then use the restore acceptance helper
against a new owned disposable `*_test` database and isolated media directory.
Never restore over source or shared data. Check schema, application behavior and
relationships before any recovery cutover. Readback hashes alone do not establish
provider durability, key recoverability or application readiness.

Retention produces `retention-plan.json` from the verified local catalog: 14 daily,
8 weekly and 12 monthly generations by default. It performs no remote deletion.
Remote accumulation therefore continues until a separately controlled retention
operation is implemented and authorized. Preserve keys needed by retained backups.

## Schedule and monitoring

The example timer runs at 02:00 UTC with up to 15 minutes randomized delay and
`Persistent=true`. Enable it only after credentials, escrow recovery, disk capacity
and a manual run have been checked. A persistent timer may run after downtime;
its calendar does not guarantee backup freshness.

Monitor systemd failures/timeouts and the state-directory `last-result.json`, `last-verified.json` and catalog receipts.
Alert on failed attempts, stale last verified success, disk/quarantine pressure and
unverified commit uncertainty. Connect these signals to the existing alerting
system; the template does not install an alert route. Do not log credentials or
private payloads while diagnosing failures. Establish freshness thresholds and
RPO/RTO from actual capture, remote readback and full recovery measurements.
