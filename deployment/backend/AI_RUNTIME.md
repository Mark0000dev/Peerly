# Dedicated AI worker runtime

## Packaging

Build `backend/Dockerfile.ai-worker` from the immutable backend digest in
`backend/ai-base-image.txt`. Application source overlays are forbidden. Verify
inherited application bytes against that backend image's exact source revision.
Schema2 publication metadata records `runtime_overlay_applied=false`,
`base_source_sha` and `inherited_source_sha256`; old patch labels are not lineage.

The Linux x86_64 image pins native CLI0.167.0 and its bundled sandbox resources.
The outer launcher is
`/usr/local/lib/peerly-codex/vendor/x86_64-unknown-linux-musl/codex-resources/bwrap`.
Its SHA256 is `77360cb751ccedc5971391444ac86a8a33c15b04d6b4a6fe45f5d25496e62c4c`.
Do not substitute distro bubblewrap: the native integration requires `--argv0`
and the pinned adjacent resource layout. The fixed policy disables project
instruction loading with `project_doc_max_bytes=0`.

## Isolation and resources

Reserve UID/GID10002 for this singleton service. Other backend services use10001;
RLIMIT_NPROC is UID-wide and therefore requires a dedicated identity. Use a
read-only root, dropped capabilities, no-new-privileges, private PID namespace,
bounded writable workspace/tmpfs and no public ports or Docker socket.
The deployment budget is40 processes/threads,1GiB memory and0.5 CPU. Set
`RUNTIME__MAX_PROCESSES=40` explicitly; the source default is32. Policy, child
RLIMIT, actual cgroup limits and resource evidence must agree.

Nested user/PID/mount namespace operation requires the reviewed per-service
seccomp/AppArmor and proc-path configuration. Validate the exact engine contract
with both outer and nested-helper controls, including credential, descriptor,
proc, environment, write and network denials. Never use privileged mode,
unconfined profiles, restored capabilities or shared-host policy relaxation.
Startup success alone does not prove containment.

## Credentials and provisioning

Use a dedicated persistent same-owner managed credential cache, never a developer
home or API-key fallback. Trusted transport may refresh credentials; model tools
must not read that cache. Provision ownership10002:10002, directory0700 and
credential files0600. Keep job history/workspaces separate from credentials.
Follow [PROVISION_BOOTSTRAP.md](PROVISION_BOOTSTRAP.md) for bounded startup hold,
private configuration and execution. Final physical-runtime acceptance must bind
the actual image, namespaces, policy, resources, account/model and transport.
Do not reuse evidence across changed live fingerprints.

## Lifecycle and database use

AI admission uses pool2; the singleton worker uses pool1 for short transactions.
No SQL connection is held during inference or media I/O. Readiness on the
canonical executor slot has15s freshness. Expiry denies submission but does not
release an occupied physical slot. Predecessor ownership and uncertain child or
credential state require controlled physical-stop recovery; no automatic takeover.

Settings are immutable after startup. For replacement, stop admission, drain or
cancel through the existing lifecycle, confirm all children stopped and preserve
managed credential updates. Re-establish final-container acceptance before
execution; image publication alone grants no provider or authentication authority.
Telemetry configuration is documented in
[AI_WORKER_TELEMETRY.md](../observability/AI_WORKER_TELEMETRY.md).
