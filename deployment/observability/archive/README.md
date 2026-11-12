# Sanitized native S3 archive (optional, prospective)

This overlay adds `awss3/archive` to the existing sanitized logs/traces pipelines of the pinned Collector0.165.0. It preserves Loki/Tempo delivery and all existing receivers/privacy processors. Metrics are not archived. No app SDK, host socket, inbound cloud service or runtime Python changes.

Use base `compose.yml` plus `archive.compose.yml`. If remote-write is enabled, use base + `remote-write.compose.yml` + `archive.compose.yml` + `archive/remote-write.compose.yml` LAST: Compose replaces command arrays, so the last supplement explicitly loads all three native configs. No base config is rewritten. Tempo S3 and gateway overlays remain independent.

Parent must provide an approved HTTPS S3 origin, region, archive-only bucket/prefix, path-style flag and scoped PutObject credentials through deployment inputs outside Git. Collector uses the AWS SDK credential chain; do not mount home credentials or enable instance metadata. Do not render Compose with real secrets into terminal/CI output. Prefix must be an isolated environment prefix, never user/resource-controlled routing. Do not share the prefix with Tempo's query storage layout.

The existing digest-pinned Collector image/nonroot10001/read-only/cap-drop/resource/network policy is inherited. Parent precreates `PEERLY_ARCHIVE_QUEUE_DIR` owned10001, private and on a separately budgeted persistent filesystem. Native fsync storage caps EACH signal's bbolt file at64MiB: two files permit128MiB plus filesystem/metadata overhead, not an aggregate volume quota. Each queue accepts16MiB serialized data, with one consumer. No compaction/recreation/purge policy silently deletes backlog. Parent verifies actual filesystem headroom/quota and existing exporter-failure/queue-near-full metrics before activation. These queues are outage buffers, not indefinite archives.

Collector retries use finite10s attempts, SDK one attempt and unlimited elapsed retry lifetime. Queue admission remains bounded and nonblocking; overflow/disk errors can lose records and are not repaired by exporter retry. Permanent authorization failures need operator intervention. Monitor enqueue failures too; existing send-failure/near-full rules do not prove successful archive coverage. Do not clear queues or shorten retention to silence failures. Retries and crash recovery can duplicate events; UUIDv7 object keys prevent ordinary same-minute overwrites, not exactly-once export.

Objects are native OTLP JSON compressed with gzip, partitioned by UTC upload time and distinct signal/key. Upload time is not event occurrence or commit order. Fixed prefix and random/time-based key do not contain actor IDs. This is durable object storage only after confirmed successful writes; it is not a Grafana query index, a product/business backup, historical Loki export or proof against SDK/stdout/pre-ingestion loss. Parent must separately preserve any pre-activation Loki history before its one-week hot expiry. Do not assume the overlay backfills it.

No exporter-specific SSE field exists in the pinned config/uploader. Parent must establish provider-side bucket default encryption and verify compatible policy/actual object metadata. Do not invent an `sse` YAML option or claim verified encryption from `disable_ssl:false`. The configured endpoint must actually be HTTPS with valid TLS; synthetic proof alone uses loopback HTTP. Parent owns provider behavior, Cloud.ru endpoint/path-style choices, encryption, lifecycle with NO expiration, backup and actual readback. Archive writer needs only scoped writes; parent uses separate read credentials for recovery.

## Native synthetic proof and restore

After code completion, run once from the repository:

```sh
node deployment/observability/archive/prove.mjs
```

It requires the pinned image already local; it does not pull or contact any cloud provider. It extracts that immutable image's Linux binary into a new `/tmp/peerly-archive-*` directory, then runs it as the current nonroot user with sanitized environment, synthetic signing strings, disabled metadata and `/dev/null` AWS config files. All HTTP/TCP endpoints bind loopback; no real credentials are read. A Node boundary double accepts bounded S3 PUTs, not an S3 compatibility/auth/encryption emulator. Native Collector validates the actual base+archive+proof overrides; only proof endpoints/directories/TLS are overridden. Privacy processors remain the actual base code.

The proof injects synthetic private canaries, verifies sanitization before object storage, observes failed PUTs, SIGKILLs the Collector, restarts using the same queue files, then checks both signals recover and a second pair creates distinct keys. It decompresses actual objects and feeds them to pinned native `otlp_json_file`, writing restored OTLP through the file exporter. It preserves receipt/object hashes/native logs/restored JSON in the temporary artifact. It does NOT prove container kernel read-only isolation, real IAM/TLS/encryption, bucket durability, zero loss, global throughput or production restore into Loki/Tempo.

For real offline recovery, parent downloads an explicit bounded approved object selection using separate read access, verifies hashes/object metadata, gzip-decompresses to one OTLP JSON record per `.json` file, and mounts that directory read-only at `/restore`. Run the pinned Collector with `archive/restore.yaml`, writable private `/output` and no network. The receiver may reread files on restart/modification; keep input immutable and expect possible duplicates. Never connect restore to live ingestion/archive (replay loop), overwrite hot data blindly or run unbounded history replays. Review restored IDs/times and decide any provider re-ingestion separately.

## Pinned primary sources

- [awss3 config0.165](https://github.com/open-telemetry/opentelemetry-collector-contrib/blob/v0.165.0/exporter/awss3exporter/config.go): supported uploader fields/formats and validation; no explicit SSE option.
- [awss3 factory0.165](https://github.com/open-telemetry/opentelemetry-collector-contrib/blob/v0.165.0/exporter/awss3exporter/factory.go): both signals use queue, retry and timeout helpers.
- [S3 writer0.165](https://github.com/open-telemetry/opentelemetry-collector-contrib/blob/v0.165.0/exporter/awss3exporter/s3_writer.go): SDK credentials, endpoint/path style, unique keys and uploader options.
- [Exporter helper0.165](https://github.com/open-telemetry/opentelemetry-collector/blob/v0.165.0/exporter/exporterhelper/README.md): persistent queues, byte sizing, finite admission and retry lifetime.
- [File storage0.165](https://github.com/open-telemetry/opentelemetry-collector-contrib/blob/v0.165.0/extension/storage/filestorage/README.md): per-database cap/fsync and storage failure semantics.
- [OTLP JSON file receiver0.165](https://github.com/open-telemetry/opentelemetry-collector-contrib/blob/v0.165.0/receiver/otlpjsonfilereceiver/README.md): native JSON restoration and reread behavior.
