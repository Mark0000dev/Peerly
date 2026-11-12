# Client-encrypted archive gateway

This optional layer encrypts archive object contents and names with native rclone
crypt before HTTPS S3 transport. It provides client-side encryption, not provider
SSE. The [base archive](../README.md) retains its sanitization, durable queues and
restore format. The gateway uses the digest-pinned rclone 1.76.0 image in
[crypt.compose.yml](../../crypt.compose.yml); native `serve s3` is experimental.

```text
sanitized Collector -- private archive_crypto --> authenticated rclone S3 gateway
                                                    --> crypt --> HTTPS S3
```

## Configuration and keys

From `deployment/observability/`, merge `compose.yml`, `archive.compose.yml`, then
`crypt.compose.yml`. With remote-write, also load its base overlay and put
`archive/crypt/remote-write.compose.yml` last so all four Collector configs load.
There are no host ports, app-network gateway membership, remote-control endpoint,
file cache or anonymous fallback.

The Collector uses only a dedicated random gateway SigV4 pair. Provider credentials
and crypt passwords stay in a private UID-10001-owned read-only configuration at
`/run/secrets/rclone.conf`, shaped by [rclone.conf.example](rclone.conf.example).
Supply `RCLONE_AUTH_KEY` as the required CSV-quoted `"identifier,secret"`, matching
the Collector pair; never omit authentication. The legacy archive placeholders
must still resolve using gateway credentials, not provider credentials. SigV4 gives
access to the whole isolated namespace, not a PUT-only ACL. Verify unsigned and
wrongly signed requests fail.

The example maps `encrypted:` to `raw:peerly-archive/crypt-v1`. The physical bucket
name is `peerly-archive`, not a bucket UUID. `ingest` is a virtual bucket/directory
inside crypt, not another provider bucket. Seed a small encrypted
`encrypted:ingest/.gateway-format` marker with native `rclone rcat` before ingestion
so the directory persists across gateway restarts. Do not create/delete the cloud
bucket or mix raw gzip objects into the encrypted root.

Use generated high-entropy password and distinct salt, stored with native
`rclone obscure`. Obscuring is reversible and does not encrypt the configuration.
Back up the passwords, salt, exact crypt options, root mapping, pinned version and
configuration securely offline, independently of the gateway. Losing these values
loses decryptability. Do not rotate keys in place; use a deliberate versioned root
for new keys while preserving old recovery material. No automatic data TTL/deletion
is configured; multipart cleanup must not delete accepted archive objects.

## Bounds and acknowledgement

The container has a 192MiB hard limit, 160MiB Go memory target, 0.2 CPU and PID 64.
Cache/read buffers are off; streaming cutoff is 1MiB, S3 chunks 5MiB/concurrency one,
shared buffers 32MiB, at most two multipart uploads, reordered-part limits
5MiB/upload and 10MiB/user, and metadata bound 128 objects. Read/write timeouts
are 15s, connection/idle 5s, with one retry setting. Inbound connection count is
not capped: private isolation and two trusted Collector consumers are assumptions,
not a hostile-client availability guarantee. Memory exhaustion may still kill the
gateway; finite Collector queues retain unacknowledged work within their limits.

Cache-off PUT waits for native close/remote completion before acknowledging.
Do not enable asynchronous VFS writeback. Provider permissions must cover required
prefix-scoped List/HEAD/PUT and multipart operations; this is not pure PutObject-only
compatibility. Keep HEAD integrity checks and normal TLS verification. Confirm
actual endpoint/path-style/region permissions and ciphertext readback. Name lookup
is deterministic, content encryption randomized; ambiguous retries can duplicate
records and do not provide exactly-once delivery.

## Synthetic proof and offline recovery

With both pinned images already local, from the repository root:

```sh
node deployment/observability/archive/crypt/prove.mjs
```

The proof uses native binaries, loopback endpoints, isolated temporary synthetic
configs and an outage fixture that preserves signatures. It checks invalid auth,
ciphertext format, durable Collector recovery after SIGKILL, gateway/virtual-bucket
restart, unique objects, native offline decryption with gzip hash equality,
wrong-key/tamper failure without plaintext, and native OTLP JSON restoration.
It reads no real credentials or encryption keys and contacts no provider. It does
not establish kernel container isolation or actual cloud compatibility/durability.

For recovery, download a bounded approved selection of encrypted paths/objects
from the scoped root, then stop network access. Configure a local crypt remote
over that ciphertext tree using the identical backed-up options/password/salt:

```sh
rclone copy local-crypt:ingest/approved-selection offline-plain/
```

The result is the original `.json.gz` archive. Verify hashes, counts and IDs,
decompress the bounded selection and use [the offline restore configuration](../restore.yaml).
No gateway/provider credentials are needed after ciphertext download. Do not
connect restoration to the production archive exporter, infer completeness from
a listing or run an unbounded replay.

Pinned references: native [S3 server](https://github.com/rclone/rclone/blob/v1.76.0/cmd/serve/s3/s3.go),
[PUT completion](https://github.com/rclone/rclone/blob/v1.76.0/cmd/serve/s3/backend.go)
and [crypt format](https://github.com/rclone/rclone/blob/v1.76.0/docs/content/crypt.md).
