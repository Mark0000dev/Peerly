# Native sanitized logs/traces archive

Parent-authorized bounded source task,11 November2026. Own NEW deployment/observability/archive/**, archive.compose.yml and this ledger ONLY. No accepted base Collector/backend/Python/shared config, secrets, Git, live provider or deploy edits. Parent/Aquinas/Noether received the pinned typed config contract before implementation; base is frozen, privacy processors precede fanout.

Code complete: optional native0.165 awss3 OTLP JSON/gzip fanout for logs/traces, two16MiB persistent byte queues/consumer1, separate fsync storage64MiB per database (128MiB plus overhead),10s attempts/SDK1/unlimited elapsed retry. Fixed parent bucket/environment prefix, UTC partitions and UUIDv7 keys. No metrics archive, app technical producer, TTL purge or user-controlled routing. No explicit SSE field in pinned exporter: actual provider bucket encryption/lifecycle/TLS/readback remain parent responsibilities.

Native proof source is code complete: actual pinned image binary, actual base privacy processors, loopback S3 double, failed PUT→SIGKILL→persistent restart recovery, collision/privacy object checks, gzip readback and native otlp_json_file restore. Single coherent execution pending; no behavioral or cloud proof claimed yet. All fixtures/receipts outside Git in unique temporary directory; no backend or Python edits. Existing Loki pre-activation history requires a separate parent export before one-week expiry; this prospective overlay does not backfill.

## Local native proof receipt

Single native transport/recovery/restore batch PASS, artifact `/tmp/peerly-archive-PcSAso/receipt.json`. Actual pinned image digest e40d61...; both native merged configurations (base+archive and base+remote-write+archive) validated. Two credential-free Compose renders verified full config command arrays and inherited UID10001/read-only/cap-drop/no-host-socket policy. Native execution used the extracted binary; kernel container isolation is explicitly NOT claimed from that runtime proof.

Controlled loopback outage produced two failed PUT attempts; SIGKILL/restart recovered both persisted signal batches. A second pair produced four distinct compressed JSON objects with zero synthetic-key overwrites. Each actual object was gunzipped and decoded. Native otlp_json_file→file restore recovered exactly2 log records and2 spans, preserving both trace/request IDs and excluding the synthetic private canary. `restore-readback.json` records the complete readback; `objects[].key` in the transport receipt is the synthetic PUT request-target, including SDK query parameters, not a claim about a real provider object key.

No real cloud/S3 calls, credential-file reads, live IAM/encryption/lifecycle verification, Loki-history backfill, unbounded-capacity/zero-loss/exactly-once or provider-query-index proof. Parent owns actual activation and pre-expiry preservation of existing hot history. No base Collector/backend/Python/Git edits.
