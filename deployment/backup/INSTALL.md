# Install and operate scheduled encrypted backups

This companion installs a fixed Python/SQL runtime closure and inactive systemd
units. It adds metadata-only status publication and an escrow-canary reader to the
existing PostgreSQL/media capture, native crypt readback and retention tools.
Neither installation nor a canary receipt proves application recovery or an RPO.

## Runtime and configuration

Use a Linux systemd host with a dedicated unprivileged `peerly-backup` user/group,
a root-controlled Python 3.11+ runtime with Linux memfd/seals, PostgreSQL 16 native
clients and the pinned rclone 1.76.0 binary. The Python executable, its libraries,
installed source and their ancestor directories must be root-controlled and not
writable by the backup account. The installer downloads nothing and does not
install global dependencies. Existing native tools and their exact configured pins
must be staged before a manual run.

Stage these root-owned private regular files under `/etc/peerly-backup`, mode
0600, with root-controlled ancestor directories:

- `plan.json`: existing plan schema, actual installed capture SHA256, pinned rclone
  path/SHA256, state `/var/lib/peerly-backup`, key generation and escrow reference.
- `source-request.json`: exact database name/OID/role/released head/PG major,
  actual system identifier when available, independently pinned connection endpoint
  and observed server address/port. NAT can make the latter different. Preserve
  the source's explicit `ssl=disable` policy where configured; no fallback occurs.
- `pgpass`: only the required source password entry.
- `rclone.conf`: existing source-media read-only credential and separate backup
  prefix-scoped credential with business-backup crypt settings.
- `pg-ca.pem`: only when the source explicitly requires `verify-full`.

Keep the existing one-payload admission budget: 3,373,268,992 bytes plus existing
quarantined spool usage within the configured allowance (example 3.5 GiB). The
2 GiB dump/1 GiB media limits, streamed readback, 512 MiB/half-CPU/64-task/35-minute
capture limits and no-delete retention behavior are unchanged. Admission is not a
filesystem reservation; allocation overhead, concurrent writes and inode pressure
can still fail a run. Never skip readback or raise caps automatically.

## Prepare, verify and install inactive units

From the root of the reviewed source tree, prepare a new bundle. Preparation reads
only the fixed source allowlist; it opens no credentials and executes no helpers:

```sh
python3 deployment/backup/install_backup.py prepare \
  --source /srv/peerly-backup-source --output /srv/peerly-backup-bundle
```

The output includes the exact `source_manifest_sha256`. Review and pin this value
through the deployment channel; the manifest binds 12 runtime files and three unit
templates, including `recovery_and.py` and both SQL files. Capture-module SQL pins
must match those bytes. Place the reviewed installer and bundle on the host under
root control. Substitute the reviewed manifest digest and actual Python path:

```sh
sudo /usr/bin/python3 /srv/peerly-backup-source/deployment/backup/install_backup.py install \
  --bundle /srv/peerly-backup-bundle \
  --manifest-sha256 REPLACE_REVIEWED_MANIFEST_SHA256 --python /usr/bin/python3
```

Add `--with-ca` only for `verify-full`. The installer checks credential metadata
without opening their contents. It creates a content-addressed release under
`/usr/local/lib/peerly-backup/releases/`, verifies local imports and rendered units,
and creates owned state mode 0700 and metadata mode 0755. It refuses existing unit
files, state with the wrong ownership/mode, existing release names, symlink source
components, missing closure members and hash mismatches. It does not reload
systemd, start/enable services or contact providers. Installation is initial-only;
inspect vendor/transient units and overrides before use. Existing deployments need
manual reconciliation rather than an installer overwrite.

`install-receipt.json` is private and records capture/SQL/manifest pins and inactive
installation. It is not a backup receipt. The source manifest is a pin, not a
signature or substitute for trusted deployment. A failure may leave an exclusive
partial release, state directory or some installed unit files; no rollback/deletion
is attempted. Inspect those exact owned paths and reconcile them before retrying.
Do not activate a partial installation or recursively remove shared directories.

## Independent key recovery and rotation

Keep an independent access-controlled escrow copy of the business crypt password,
salt, standard filename/directory settings, versioned root, endpoint and generation
mapping. Rclone-obscured passwords are reversible; treat the entire configuration
as secret. Preserve every historical key/root required by retained generations;
never reuse telemetry keys or change keys in an existing root.

A recovery profile contains only `[backup_s3]` and `[backup_crypt]`, explicit
HTTPS/credentials and the existing scope. Exclude source-media and PostgreSQL
credentials. Recovery credentials should permit only required historical reads.
The root form is `backup_s3:BUCKET/business-backups/crypt-vN`. Unknown options,
default inheritance, endpoint paths/userinfo and TLS bypass are rejected.

For each generation, keep a separately recorded synthetic canary specification
with exactly these fields: `key_generation`, `canary_reference`, `size`, `sha256`,
`crypt_root_sha256`, `endpoint_sha256`. Size must be 1..4096 bytes. SHA256 binds the
exact plaintext `KEY-RECOVERY.json` bytes; root/endpoint hashes bind the exact
configured strings. The object lives beneath
`backup_crypt:key-recovery/CANARY_REFERENCE/KEY-RECOVERY.json`. Its content is
synthetic, contains no user data or credentials and must be published through the
controlled key-establishment process. This reader creates/uploads no canary and
cannot establish its provenance from a matching hash alone.

Recover the profile from escrow independently of the producer's working copy.
Use a private mode-0700 receipt directory and new receipt filename. From the
installed release directory, invoke the reviewed runtime with FD-only inputs:

```sh
exec 3</etc/peerly-backup/plan.json
exec 4</secure-recovery/escrow-readonly.conf
exec 5</secure-recovery/canary-spec.json
env -i PATH=/usr/bin:/bin HOME=/nonexistent PYTHONPATH="$PWD" \
  /usr/bin/python3 -s -B -m deployment.backup.key_recovery verify \
  --plan-fd 3 --escrow-fd 4 --spec-fd 5 --receipt /secure-recovery/receipts/canary.json
exec 3<&- 4<&- 5<&-
```

Replace Python with the same root-controlled runtime used for installation. Keep
shell tracing disabled. No credential values/configuration filenames enter child
argv; only FD numbers do. The reader checks native binary hash/version, exact
before/after listing, bounded sizes and downloaded SHA256 using existing native
streaming code. It writes a new private receipt only after success. Wrong keys,
extra/missing objects, hash mismatch, nonzero native exit or cancellation cannot
produce a success receipt. No archive payload is downloaded to disk.

`native_key_readback_verified=true` proves this particular native readback.
`independent_custody_proven=false` remains explicit: custody and independent
retrieval need separate operational evidence. `escrow_drill_reference` alone is
only a reference. A canary does not verify an archive, historical keys, all backup
files, provider durability or application restore.

Before rotation, open old/new plans on FDs 3/4 and their minimal escrow profiles on
FDs 5/6, then use `key_recovery check-rotation --old-plan-fd 3 --new-plan-fd 4
--old-escrow-fd 5 --new-escrow-fd 6 --receipt NEW_PRIVATE_RECEIPT`. Preserve the same
sanitized invocation and receipt permissions. A changed generation needs a higher
versioned root, changed password/salt encodings and new drill reference; scope,
binary pin, retention and spool budget must remain unchanged. Changed encodings do
not prove different cleartext keys. Establish and independently read the new canary
before switching the producer configuration. Keep historical roots/keys readable.
The helper never rotates credentials, rewrites a plan, uploads or deletes objects.

## Status, scheduling and alerts

The main unit publishes `/var/lib/peerly-backup-metrics/backup.prom` atomically after
exit. A separate credential-free failure oneshot covers early service failures,
including missing credentials. Both run as the dedicated account. The mode-0644
file contains only six fixed numeric gauges: status validity, verified timestamp,
attempt timestamp/success and known unit result/success. It contains no run IDs,
paths, keys, database identities, object names or payloads. Missing/corrupt/future
or inconsistent receipts are invalid rather than successful. Stale data retains
its original timestamp. The catalog and final status timestamps legitimately differ
and are checked against the bounded run interval, not assumed equal.

Merge `metrics-gateway.location.conf` only into the existing authenticated gateway
server, preserving inherited reader authentication/TLS. Merge the readonly metadata
mount example into the existing gateway service; never mount the state/payload or
credentials. Append the scrape snippet to the existing Prometheus configuration.
No new daemon, port, exporter or provider sender is required. Merge backup rules
into the existing technical rule set with `owner=peerly-team`; preserve unrelated
routes and the existing Alertmanager receiver.

Choose the freshness policy explicitly by configuring the seconds threshold in
`backup-alerts.yml` before loading it. The supplied 108000-second/30-hour value is
an editable daily-schedule example, not an RPO/SLO or measurement. Rules detect
missing scrape/status, unknown unit result, failure and old/unverified generations.
Monitor disk/quarantine pressure separately using existing host monitoring. Validate
merged nginx/Prometheus/Alertmanager configuration and exercise firing and resolved
notifications through the existing technical route. Source snippets do not prove
notification delivery. The included `backup-alerts.test.yml` is a promtool behavior
fixture; run `promtool check rules backup-alerts.yml` and
`promtool test rules backup-alerts.test.yml` with the matching pinned monitoring
version before deployment.

After host permission checks, source preflight, independent escrow recovery,
manual real capture/readback and status/alert acceptance, reload systemd and start
one manual `peerly-backup.service`. Inspect its exit status and private verified
catalog. Then enable `peerly-backup.timer`; it runs at 02:00 UTC with up to 15 minutes
jitter and catch-up after downtime. Stop/disable the timer to suspend future
attempts; this does not stop an in-flight capture or delete backups. Quarantined
plaintext and uncertain remote commits require exact owned-path reconciliation.
Retention remains plan-only (14 daily/8 weekly/12 monthly), with no remote deletion.
Full isolated archive/schema/index/sequence/application/media restore and measured
recovery remain separate acceptance gates. A schedule is not a freshness guarantee.
