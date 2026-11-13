# Synthetic restored-application HTTP smoke

These helpers exercise the released root FastAPI application, its full lifespan,
request middleware, session/CSRF checks, use cases and PostgreSQL repositories on
an isolated restored synthetic database. They are not an administrative recovery
endpoint, real-session reactivation tool or replacement for full recovery acceptance.

Use an owned network-isolated PostgreSQL 16 runtime and a fresh unique
`peerly_restore_<32 lowercase hex>_test` destination, distinct from its synthetic
source. Keep all external workers/executors disabled. Seed test sessions, grants,
retained media and AI jobs/intents/attempt/slot metadata BEFORE native backup capture;
restore that archive and validate its baseline/media/schema evidence before smoke.
Do not create replacement application tables or alter schema to satisfy this check.
Never supply an actual customer/staging backup or real account/session credentials.

Construct RecoveryCase with `synthetic_not_real_backup=True` explicitly; the default
rejects execution. Source names must match `peerly_http_source_<32 hex>_test`.
Create a dedicated `postgresql+asyncpg` engine with explicit loopback host, exact
owned target name, no URL query options or password, finite connect timeout and
an owned empty regular0600 passfile. Run with empty HOME and no inherited developer,
PG service/credential, proxy, OTel or cloud environment. Naming and flags guard
inputs; the runner must independently attest ownership and network isolation.

Provide RestoredMedia with an immutable read-only local restored media tree and
its baseline path/size/SHA256 map. The adapter reads only expected retained keys,
bounds files to the existing10MB media cap/eight reads, checks size/hash and rejects
symlinks. All upload/retain/remove methods reject. It cannot manufacture a successful
S3 operation. Keep the tree immutable during execution; do not mount arbitrary
mutable/private host directories. The smoke's media boundary does not test S3.

`await recovery_http_app.run_http(engine, case, media)` composes the actual app
with synthetic-only auth configuration. It overrides only the media port and the
outbound HTTP client transport, which counts/rejects every provider request. It
never overrides auth dependencies, SQL repositories, route responses, jobs or
provider outcomes. Network-none remains the independent egress barrier. Dispose
the caller's dedicated engine in finally.

The helper sends real HTTP requests through HTTPX ASGITransport, using separate
cookie jars for every actor and entering/exiting the full application lifespan.
It does not open a TCP listener or prove TLS/browser/native cookie behavior.
The returned receipt names this transport explicitly.

Checks cover anonymous/malformed/expired/revoked/deleted session rejection; active
ordinary identity; student/inactive-grant operator denial; explicit privileged
retained-account/media/AI reads with canonical audit pairs; exact owner JPEG bytes
and cross-actor denial before media read; unchanged queued/running job, intent,
attempt and slot-fence snapshots under reads; Origin/CSRF denial; one intentional
queued-job cancellation with stable repeated result; and logout with old-token
rejection across a new application lifespan while another actor remains valid.

Only the queued job cancellation, audit/event records and session logout may mutate
the owned restored database. Running job/slot/intent/attempt hashes must remain
unchanged. No executor claims jobs or reports model success. The helper uses up to
32 rows per queue-state table, 2-second snapshot statements, 5-second HTTP/identity
preflight bounds and 90-second application deadline. These do not change product
API/SQL/queue limits. A failure raises closed codes without private response bodies.
Native exceptions/stderr must remain in protected bounded diagnostics, not logs.

Report HTTP results separately from catalog/sequence/remote-key gates. A schema
assertion before the HTTP phase is not HTTP acceptance. An explicit derived schema
proof must retain input hashes/version/provenance and cannot relabel the original
capture. No returned status establishes Google login, actual S3/model delivery,
production recovery, activation of real retained sessions/jobs or measured RPO/RTO.
