# Approved-source PostgreSQL capture companion

The operator owns source approval and actual execution. This helper makes an ordinary
logical backup with an explicit READ ONLY exported snapshot, plus the existing
Peerly restore baseline. It never changes global TLS, database/server settings,
roles or application data. It adds no credential store, provider client or crypto.
The capture and restore helpers share the pinned baseline format.

## Managed source contract

The approved connection endpoint and observed PostgreSQL server are SEPARATE pins:

- `host`: approved connection/verification hostname, never selected from HOME;
- `endpoint_address`, `port`: exact approved connection IP/port, set through
  PGHOSTADDR/PGPORT; no hostname-resolution or alternate-endpoint fallback;
- `server_address`, `server_port`: expected inet_server_addr()/server port from
  the prior approved read-only preflight. They need NOT equal the endpoint.

Managed NAT and port forwarding are valid. Only single-IP pins are accepted.
A full-host /32 or /128 observed representation is canonicalized to the equivalent
IP, retaining the original value in `server_address_raw`; a /24 network is NOT an
acceptable substitute for an exact host pin. Database name/OID, login role, schema
head, server/client major16 and read-only transaction state are also checked.
Identity mismatch prevents pg_dump/baseline children from starting.

`sslmode=disable` is supported for the exact explicitly approved request, including
managed endpoints. It requires a nonempty `plaintext_approval` reference supplied
by the operator and recorded with that request's identity pins. There is no fallback
from failed TLS and no request to change the owner's global TLS policy. It does
not imply wire encryption. `sslmode=verify-full` instead requires an explicit CA
FD; client-cert/GSS auth and implicit service configuration are outside this helper.

`system_identifier` is an expected decimal string OR null. If a strong identifier
is supplied, the helper requires actual EXECUTE capability, reads the actual value
and compares it. No superuser status is required or assumed. If the role cannot
execute pg_control_system() and no strong pin is supplied, ordinary capture may
proceed with a null ID, cluster_identifier_verified=false and the explicit
cluster_identifier_unavailable limitation. If capability exists but no ID was
requested/pinned, no value is invented: null/not_requested is reported. The operator can
obtain and pin the real value through its approved read, then use it in preflight
and capture. The actual managed source was reported by the operator to permit this read;
the deliberately restricted-role test below is NOT a claim about that real source.

A logical-backup role needs CONNECT and read privileges on the captured data and
sequences. It need not own the database, have CREATEDB or be superuser. The helper
never grants missing privileges. Preflight reports CONNECT, unreadable public
base-table/sequence counts, RLS-table count, superuser/bypass-RLS status and control
function EXECUTE capability. Public-object capability counts are not a substitute
for pg_dump's own checks on the whole dump scope; native failure cannot publish a
completed capture. RLS and nonpublic objects need appropriate independent review.

## Private descriptors and source preflight

Install beside the frozen accept_restore.py and acceptance.sql. Exact SQL pin:
`f4be591e5a15edde65eba095a09c4161925be5babe554a6b02539de3cbf38a64`.
Use root-owned regular native PG16 binary paths, not PATH wrappers/symlinks. Actual
client --version strings and SHA256 are recorded; the operator owns tool provenance.

The CLI accepts ONLY integer FD numbers. The operator opens an owned regular mode0600
request JSON (<=16KiB), passfile (nonempty <=64KiB), and, for verify-full, PEM CA
file (nonempty <=64KiB). Password/CA descriptors are fstat-checked, not consumed;
the request descriptor is read. No password/URI fields are accepted in JSON.

Example request SHAPE ONLY; all values are synthetic placeholders:

```json
{
  "destination": "/private/backups/new-capture-uuid",
  "psql": "/usr/lib/postgresql/16/bin/psql",
  "pg_dump": "/usr/lib/postgresql/16/bin/pg_dump",
  "host": "approved-managed.example.test",
  "endpoint_address": "192.0.2.10",
  "port": 6543,
  "server_address": "10.20.30.40",
  "server_port": 5432,
  "database": "approved_database",
  "role": "approved_backup_reader",
  "system_identifier": "1234567890",
  "database_oid": "16384",
  "major": 16,
  "head": "0060_report_triage",
  "sslmode": "disable",
  "plaintext_approval": "operator-approved-exact-source-reference"
}
```

For a verify-full request set that sslmode, plaintext_approval=null and pass CA FD5.
Destination MUST NOT exist; immediate parent must be owned mode0700 and on healthy,
private local storage. Secure FD opening is operator-owned, with no shell tracing,
secret-bearing arguments or environment exports. Approved launcher invocation:

```sh
python -B -m deployment.restore.capture_backup --request-fd 3 --password-fd 4 --preflight
```

`--preflight` writes ONLY private preflight.json, no dump or completion marker.
It performs a READ ONLY metadata/capability snapshot, reports actual observations
and identity_mismatches for review, and closes the session. If a strong cluster pin
was requested but unavailable/mismatched, it fails closed. The operator reviews the real
metadata, approves exact pins and creates a NEW destination request for capture:

```sh
python -B -m deployment.restore.capture_backup --request-fd 3 --password-fd 4
```

The request descriptor must be freshly opened/rewound. Never reuse the preflight
output directory as a capture destination. Inspect private reports directly;
stdout contains only a closed status, never source IDs, credentials or native
stderr. Both modes retain the existing explicit FD/clean-environment safeguards:
fixed PATH, HOME=/nonexistent, explicit libpq identity/TLS/PGPASSFILE descriptors,
no PGPASSWORD/PGSERVICE/developer defaults, no implicit root/client cert, no GSS.
PGOPTIONS fixes read-only state, search path, connect/statement/lock/idle guards.

## Capture and publication

Keep a real REPEATABLE READ READ ONLY exporter open while BOTH native children
run: custom-format pg_dump and SELECT-only source baseline importing the EXACT
exported snapshot. Before children start, enforce actual approved identity and
known missing-read-capability failures. Wait for both child exit0 and validated
baseline; only then roll back/close the exporter and verify its exit0.

The frozen acceptance SQL uses a session-local function. The source adapter pins
its bytes and derives SELECT-only table SHA256 fingerprints via quoted %I/%L and
psql \gexec, reusing its exact media/relationship query. No source DDL/DML exists.
The final baseline is accepted by the unchanged restore checker.

Private source.dump and baseline.json files are flushed/hashed. Exclusive hard
links publish complete.json LAST after successful timeout scope exit; files are
never overwritten. Observed final-directory fsync failure removes only this
attempt's completion link. Existing destinations are rejected without cleanup.
A handled failure removes known .part files and records failed.json with
backup_complete=false. Partial publication can leave valid artifacts WITHOUT a
completion marker; these are not an accepted capture. SIGKILL/host loss can leave
unknown outcomes: quarantine the owned directory, do not rerun into it.

One attempt: outer180s async deadline, connect5s, statement120s, lock2s,
idle-in-transaction200s. Failure/cancellation TERM then KILL/reap uses3s+3s per
owned process group; all peers/exporter are closed. No retry/daemon/global kill.
SIGTERM/SIGINT use that cleanup; parent checks pg_stat_activity for interrupted or
unknown outcomes. Healthy local filesystem/resource quotas are external needs:
threaded bounded-byte hashing can finish after timeout on stalled storage, and
short final publication metadata/fsync is synchronous outside the async deadline
to avoid cancellation/publication races. This is not a hard production RTO claim.

Bounds remain dump2GiB, JSON8MiB, source identity16KiB, public tables256,
rows/table10000, references20000, object10MB and referenced media1GiB. Extra rows
are detected, never silently truncated; empty media is rejected. Larger sources
need a separately reviewed budget, not hidden exclusions. Baseline representation
uses fixed UTC/float settings and same PG major for restore comparison.

## Evidence and pending real backup/media work

Private complete.json records actual identity/head/version, approved endpoint and
observed server pins, capability report, available pinned cluster proof/limitations,
native binary hashes, SQL pin, snapshot/capture ID/times and actual artifact hashes.
`database_capture_complete=true` means only that bounded database step;
backup_complete/media_capture_complete/full_restore_proven remain FALSE.

Capture retained S3/media into a private offline tree and verify exact object sizes
and SHA256 digests against the captured baseline. Restore the database backup into
a unique owned disposable `*_test` database and run the restore verifier with that
media tree. Never enable application workers or provider delivery against the
restored database.

A database capture alone does not prove recoverability. Separately verify schema,
indexes, sequences, extensions, large objects, isolated application reads, recovery
keys, provenance, RPO and RTO before accepting a complete recovery procedure.
