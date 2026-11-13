# Recovery schema and application checks

These additive helpers complement `accept_restore.py` and its format-1 baseline.
They do not alter the capture/restore helpers or migrate/stamp a database. Execute
only against an owned isolated recovery container with no provider network,
background worker or external-delivery process. Use the released application
source and locked backend environment associated with the archive.

## Inputs and capture

`recovery_catalog.sql` emits one JSON record containing the migration head and
hashed catalog definitions for every non-system schema, including diagnostic
schemas. It compares columns/defaults, relations/views/partition bounds, constraints,
indexes and validity/readiness, user triggers, functions/procedures, enums and
sequence specifications/ownership. It excludes raw routine bodies/default literals
from output. Object names are still private metadata: keep outputs mode 0600.
Owners/ACLs, RLS policy definitions, extension provenance, domain types and external
foreign-server configuration are not fully inventoried; this is not a complete
pg_dump semantic comparator.

For future captures, collect the source catalog using the same retained exported
snapshot as the existing acceptance baseline and dump. Pass the snapshot using
psql's existing `backup_snapshot` variable. Keep the exporter's transaction alive
until all children finish; reject any child failure. This helper does not modify
that exporter or extend its deadline. Its source query is read-only and creates
no temporary function. A catalog from a later source snapshot cannot prove the
schema of an older backup. Existing archives without this catalog need their own
archive-derived schema evidence; never substitute a newly captured live catalog.

## Isolated restore invocation

Restore the whole archive first using the existing restore runner and its unique
`peerly_restore_<32 lowercase hex>_test` database. Do not create replacement tables
or disable triggers/constraints. Keep the existing public baseline/media acceptance.

Run each SQL file with native PostgreSQL 16 psql from the same isolated container:

```sh
umask 077
# PGHOST/PGPORT/PGUSER/PGDATABASE are explicit isolated trust-only inputs.
# Start the shell with env -i; set HOME to an empty owned directory.
# Never inherit libpq service/password/options files or developer configuration.
set -eu
psql -X --no-password --quiet --tuples-only --no-align \
  --set=ON_ERROR_STOP=1 --file=recovery_catalog.sql > restored-catalog.partial
mv restored-catalog.partial restored-catalog.json
psql -X --no-password --quiet --tuples-only --no-align \
  --set=ON_ERROR_STOP=1 --file=recovery_sequences.sql > restored-sequences.partial
mv restored-sequences.partial restored-sequences.jsonl
python -B -m deployment.restore.recovery_checks \
  baseline.json source-catalog.json restored-catalog.json restored-sequences.jsonl
```

Redirect native stderr to a protected bounded diagnostic file or discard it; do
not forward it into ordinary logs. Require native exit zero before publishing each
metadata file. Remove stale `.partial` files only from this owned run. The existing
runner must enforce the total process deadline and terminate child groups; SQL
statement/lock deadlines alone are not a total job deadline. There is no provider
access or production credential requirement for these restored-database commands.

Catalogs have at most 20,000 entries and the existing JSON loader's 8 MiB ceiling.
SQL limits at 20,001 entries to make overflow reject rather than silently truncate.
Schema/catalog identity and migration head must match the source baseline; every
public baseline table must be represented. Cross-database catalog comparison
normalizes identity by schema/object names and definitions, not unstable OIDs.

The sequence SQL accepts only the recovery database naming convention. It reads
`last_value` and `is_called` without calling `nextval` or `setval`, and checks the
next value against max/min of each owned integer column. Empty sequences are an
explicit valid case. Cycling, unowned, exhausted, duplicate, missing or potentially
colliding sequences fail for explicit investigation. No automatic repair occurs.
Sequence state is not MVCC/exported-snapshot consistent on a writing source; run
these safety checks on the quiescent restored database. A max/min scan is bounded
by the per-statement deadline and the existing restore baseline's public row caps;
large diagnostic tables may time out and require investigation, not bypass.

## Released application compatibility

`recovery_application.probe(engine, source=..., target=...)` is an async entry point
for the existing native runner. Supply a dedicated `postgresql+asyncpg` engine with
an explicit loopback host, the exact owned target database and no URL query
options. Use isolated trust authentication, an empty HOME, no inherited PG/libpq
variables, and `connect_args={"passfile": "/owned/private/empty.pgpass"}`. Use an owned empty regular mode-0600 passfile; asyncpg warns for /dev/null.
Dispose the engine in the
runner's `finally` block. The guard rejects remote hosts, unexpected databases and
source=target before opening a connection, then checks actual current_database.
Naming is a guard, not proof of resource ownership; the runner owns that proof.

The check opens a repeatable-read read-only transaction with 2-second statements,
1-second locks and a 90-second total bound. It resolves every released model's
columns against PostgreSQL with LIMIT 0, then reads up to 50 existing subjects via
the existing SqlSubjectReader and domain Subject mapping. An empty catalogue
rejects rather than claiming that mapping executed. Only counts/status leave the
helper. SQLAlchemy/native exceptions must be converted to closed failure codes by
the runner, never logged with SQL parameters or private rows.

This is model/repository/domain compatibility. Authenticated session recovery,
student/operator authorization, conversations, private media display, retained
jobs/leases/intents and controlled write/rollback journeys still need a separately
isolated application acceptance run with external transports disabled. Do not
reactivate restored real sessions, worker jobs or external delivery queues. None
of these helper results sets `full_restore_proven=true` or establishes RPO/RTO.


Catalog format 3 retains the PostgreSQL 16 logical-restore normalization of
constant varchar arrays cast to text arrays. It tokenizes definitions, preserves
literal/identifier/operator boundaries, and distributes only that exact cast over
constant varchar literal elements. Other casts/expressions remain exact. Raw
constraint/index definition text is transient private native metadata, checked
against its native hash; the capture artifact stores normalized hashes only.
Routine bodies/defaults remain server-hashed. Format 3 also handles ordered
associative CHECK-AND grouping; see [the exact scope and installation requirements](CATALOG-FORMAT3.md).
Historical format-1/2 catalog artifacts are rejected, never relabeled. The existing
row/media baseline remains format 1.
