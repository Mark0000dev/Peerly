# Sanitized telemetry archive

The optional native S3 overlay adds archive fanout to sanitized logs and traces
from the digest-pinned Collector. Loki/Tempo delivery and the existing privacy
processors remain; metrics are not archived. See the
[observability bundle](../README.md) and [pinned images](../images.json).

## Configuration

From `deployment/observability/`, merge `compose.yml` and `archive.compose.yml`.
With remote-write, use this order:

```text
compose.yml
remote-write.compose.yml
archive.compose.yml
archive/remote-write.compose.yml
```

The final supplement is necessary because Compose replaces command arrays; it
loads all three Collector configs. Tempo object storage and ingress overlays are
independent. For client-side encryption, use the separate
[crypt gateway](crypt/README.md) configuration and its final supplement instead.

Supply an approved HTTPS S3 origin, region, archive-only bucket, fixed environment
prefix, path-style setting and scoped write credentials through private deployment
inputs. Never print secret-bearing rendered Compose. Do not mount home AWS
credentials or enable instance metadata. Routing prefixes must not come from
users/resources or share Tempo's query-storage layout.

Precreate `PEERLY_ARCHIVE_QUEUE_DIR`, private and owned by UID 10001, on a budgeted
persistent filesystem. The Collector inherits its pinned image, nonroot/read-only,
capability and network/resource policy. Each signal's native fsync bbolt database
has a 64MiB cap: two permit 128MiB plus filesystem overhead, not a shared-volume
quota. Each sending queue accepts 16MiB serialized data with one consumer.
Verify actual disk headroom and queue/exporter alerts before activation. Do not
clear queues or shorten retention to hide errors; these buffers are not archives.

Attempts are bounded at 10s, the S3 SDK makes one attempt, and durable retries have
no elapsed-lifetime cutoff. Admission is bounded/nonblocking; overflow or storage
failure can lose records and retries cannot recover records never queued. Monitor
enqueue failures as well as sending failures and near-full queues. Permanent auth
errors need intervention. Retries/crashes may duplicate events; unique object keys
avoid ordinary overwrites but do not establish exactly-once export.

Objects are native OTLP JSON compressed with gzip, partitioned by UTC upload time
and signal, with UUIDv7 keys. Upload time is not event/commit order. Keys do not
embed actor IDs. Confirmed object writes provide storage, not a Grafana index,
business backup, historical Loki export or protection against pre-ingestion loss.
Preserve any required existing hot history before expiry; this overlay does not
backfill it.

The pinned exporter has no per-object SSE configuration field. HTTPS does not
prove encryption at rest: establish bucket encryption policy and verify actual
object metadata, lifecycle without archive expiration, durability and readback.
Use separate read credentials for recovery. Provider permissions and encryption
are deployment acceptance requirements, not conclusions from a local proof.

## Synthetic proof

With the pinned Collector image already local, from the repository root:

```sh
node deployment/observability/archive/prove.mjs
```

The proof extracts the native binary into an isolated temporary directory and
uses loopback HTTP endpoints, synthetic signing material, no home credentials
and disabled instance metadata. It validates actual base/archive privacy configs,
private-canary removal, failed PUTs, SIGKILL/restart with retained queues, recovery
of both signals, distinct keys, actual gzip objects and native offline JSON
restoration. It retains hashes, logs, restored JSON and a receipt.

The S3 boundary fixture is not an IAM, TLS, provider encryption or durability
emulator. Host-binary proof does not establish container isolation, zero loss,
production throughput or restoration into live Loki/Tempo.

## Offline restore

Download an explicit bounded object selection with separate read access. Verify
object metadata/hashes, decompress approved `.json.gz` objects into individual
`.json` files, then mount that directory read-only at `/restore`. Run the pinned
Collector using [restore.yaml](restore.yaml), private writable `/output` and no
network. The native receiver writes restored OTLP to `/output/restored.json`.

Keep inputs immutable: receiver restart/modification may reread files, so expect
possible duplicates. Review restored IDs/times before deciding on re-ingestion.
Never connect restore to live archive ingestion/export, overwrite hot data blindly
or replay unbounded history. The archive is not a substitute for business backups.

Protocol/config references: pinned
[S3 exporter](https://github.com/open-telemetry/opentelemetry-collector-contrib/blob/v0.165.0/exporter/awss3exporter/config.go),
[file storage](https://github.com/open-telemetry/opentelemetry-collector-contrib/blob/v0.165.0/extension/storage/filestorage/README.md)
and [OTLP JSON receiver](https://github.com/open-telemetry/opentelemetry-collector-contrib/blob/v0.165.0/receiver/otlpjsonfilereceiver/README.md).
