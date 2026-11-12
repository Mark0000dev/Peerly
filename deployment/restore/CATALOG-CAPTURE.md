# Same-snapshot recovery catalog capture

Install `recovery_catalog.sql` and `recovery_checks.py` beside `capture_backup.py`.
The capture module pins the exact SQL SHA256 and rejects a changed SQL file or
invalid exported snapshot token before starting capture consumers. Keep installed
code and SQL root-owned and immutable to the runtime account. Update the configured
capture-module hash when installing this version; never reuse an older code pin.

The existing read-only exporter retains its snapshot until all three native
children finish successfully: pg_dump, the public row/media baseline and the
recovery catalog. Every child receives the same snapshot. A failed, interrupted,
oversized or invalid catalog prevents the database completion marker. Native child
cleanup, source identity/TLS policy and the 180-second total capture deadline are
unchanged. Preflight does not capture a catalog.

A successful directory contains `source.dump`, `baseline.json`,
`source-catalog.json` and `complete.json`, all mode 0600. The completion receipt
adds `source_catalog_sha256`, `source_catalog_sql_sha256` and
`source_catalog_snapshot`. Verify these fields against the installed pin and
captured file before recovery acceptance. The catalog's database/head must match
the source request. The snapshot token is provenance for this completed attempt,
not a reusable token after its exporter closes.

Catalog format 2 checks definition metadata across all non-system schemas. Native
constraint/index definitions are hashed and token-normalized as documented in
RECOVERY-CHECKS.md. The published catalog contains hashes, not definition bodies.
Keep transient native metadata and any diagnostic output private; do not log it.
Format-1 catalogs and historical captures without a same-snapshot catalog are not
upgraded, relabeled or substituted with a later live source catalog.

The catalog native output remains within the existing 8 MiB JSON cap and 20,000
entries. It is a third concurrent native child and an additional payload file,
not another plaintext payload tree. The operational backup manifest/streamed
verification already enumerates all payload files. Its existing transfer and disk
caps remain enforced; adding catalog metadata can cause a near-limit generation
to fail its existing cap. Do not silently increase that cap or omit the catalog.
The capture receipt alone still does not prove media backup, encrypted remote
readback, key recovery, application journeys or RPO/RTO.

Sequence checking is deliberately non-mutating. Explicit seed IDs can leave serial
sequence values behind retained keys; this must be investigated as an application
schema/default-use question. A rejection is not permission to run setval on a real
source or restored archive. Synthetic regression setup may exercise both unsafe
and safe states, but that cannot establish that an unmodified archive is safe.
