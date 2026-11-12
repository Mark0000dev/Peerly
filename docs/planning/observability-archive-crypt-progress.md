# Native crypt archive gateway

## Parent actual staging acceptance — 11 November 2026

Parent activated the encrypted gateway and Collector archive fanout against the
provided S3 storage. Actual nonroot/read-only container resources, gateway auth,
ciphertext readback and cold offline restoration passed:12 selected encrypted
objects restored8 logs and4 spans with their original correlation identifiers.
Private keys/configuration and an independent crypt-options backup remain
outside Git. Historical Loki data before activation has not been backfilled;
these results do not claim otherwise. The accepted runtime manifest is retained
privately under sibling `.peerly-ops/noether/archive-integration-20261111-et2branq/`.
Its historical Collector base hash is superseded by subsequent accepted
stack/status/SQLSTATE and producer-release changes; retain all four overlays.

Parent approved NEW archive/crypt/** +deployment/observability/crypt.compose.yml +this ledger ONLY. Original seven archive paths remain immutable. No backend/Python/base Collector/real credentials/cloud calls/Git/deploy edits. Primary rclone1.76.0 sources support experimental SigV4 S3 serving over streaming crypt, waiting for native remote completion with cache off. Official image digest pinned7cbeec24...; this is client-side encryption, not fabricated Cloud.ru SSE.

Code complete: explicit bounded192MiB/GOMEMLIMIT160MiB/0.2CPU/PID64 gateway, isolated internal network/no ports/RC/cache; private config/independent gateway pair; immutable archive fanout plus late endpoint override; native encrypted virtual-bucket marker bootstrap parent-only. Offline password/salt/options backup and decryption documented. Proof definitions use only pinned native binaries/local S3, synthetic auth and secret material, outage/SIGKILL/restart/ciphertext/unique/wrongauth/wrongkey/tamper/offline restore. One coherent native batch pending; no acceptance claim yet. Parent owns actual Cloud.ru keys/TLS/IAM/marker/readback/activation and pre-existing Loki retention.

## Local final native receipt

Final bounded native proof PASS: /tmp/peerly-archive-crypt-5F58e0/receipt.json. It used actual pinned Collector and rclone binaries, authenticated native crypt gateway over a second native LOCAL S3 server, synthetic keys/configs only. Four archive objects plus encrypted bootstrap marker were stored as RCLONE-format ciphertext, never raw gzip/canary. Two private signal batches survived controlled outage/SIGKILL; gateway restart retained the virtual bucket. Four UUID-keyed archive objects had no overwrites. Native offline crypt decryption reproduced all gzip hashes; incorrect key and tampered ACTUAL archive-object reads failed with zero plaintext. Native OTLP restore verified exactly2 logs/2 spans and both trace/request IDs. Default Collector AWS checksum behavior interoperated: no compatibility override and no signature bypass.

The initial fixture used fetch forwarding that changed the signed Host and failed authentication. Only the synthetic forwarding adapter was corrected to preserve exact native request headers/bytes using Node HTTP; subsequent native chain passed. Final proof strengthened tamper selection from marker to an actual .json.gz archive object and complete restore counts. No product/native signature implementation changes.

Two offline credential-free Compose renders (base and remote-write) verified192MiB/160MiB/0.2CPU/PID64, UID10001/read-only/cap-drop/no exposed port/RC, private network and full config command arrays. Compose JSON serializes memory/CPU scalars as strings; diagnostics normalized numeric representation without changing limits. Host-binary transport proof does NOT claim kernel cgroup isolation or real Cloud.ru HTTPS/IAM/durability. All original seven archive hashes reverified unchanged.

Source is ready for parent review/activation. Real Cloud credentials, generated/backed-up crypt password/salt/options, encrypted virtual-bucket marker bootstrap, actual ciphertext/readback/TLS and scoped IAM remain parent-only. No live cloud access, real credentials, deployment, Git, backend/Python or base edits by this developer. Experimental native server limitations remain explicit.
